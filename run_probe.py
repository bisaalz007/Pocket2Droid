"""Validate immutable inputs and isolate every writable guest run."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import socket
import subprocess
import time
import uuid


EXPERIMENT = Path(__file__).resolve().parent
PROJECT = EXPERIMENT.parents[1]
ROM_RELATIVE = Path("PC windows mobile 6 Files/Roms and files/pocket pc/Deviceemulation/0409/PPC_USA.BIN")
ROM_BYTES = 100663296
ROM_SHA256 = "b6ca519070e84da0bf6886fb3bde606ce098a0cfaffff436b8faf46a9a580bf7"


def _checked_run_root(project_root: Path, run_root: Path) -> Path:
    project_root = Path(project_root).resolve(strict=True)
    if project_root != PROJECT.resolve(strict=True):
        raise ValueError("project root does not match the isolated experiment")
    allowed = project_root / "EXPERIMENTS/qemu-devemu/results/runs"
    candidate = Path(run_root).resolve()
    if not candidate.is_relative_to(allowed):
        raise ValueError("run root must stay within the isolated experiment results/runs")
    if candidate.exists() and not candidate.is_dir():
        raise ValueError("run root is not a directory")
    return candidate


def validate_inputs(project_root: Path, run_root: Path, *, rom_path: Path | None = None) -> dict:
    run_root = _checked_run_root(project_root, run_root)
    rom = Path(rom_path or (Path(project_root) / ROM_RELATIVE)).resolve(strict=True)
    if not rom.is_file() or rom.stat().st_size != ROM_BYTES:
        raise ValueError("ROM size must be exactly 100663296 bytes")
    with rom.open("rb") as stream:
        identity = hashlib.file_digest(stream, "sha256").hexdigest()
    if identity != ROM_SHA256:
        raise ValueError("ROM identity does not match the preserved V6.52 baseline image")
    return {
        "rom_path": str(rom),
        "rom_bytes": ROM_BYTES,
        "rom_sha256": identity,
        "run_root": str(run_root),
        "rom_access": "read-only",
        "status": "PREFLIGHT_PASS",
    }


def create_run_dir(run_root: Path) -> Path:
    run_root = _checked_run_root(PROJECT, run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    directory = run_root / suffix
    directory.mkdir(exist_ok=False)
    return directory


def create_ram_fmd(run_dir: Path) -> Path:
    run_dir = _checked_run_root(PROJECT, run_dir)
    storage = run_dir / 'ram-fmd.bin'
    with storage.open('xb') as stream:
        stream.truncate(32 * 1024 * 1024)
        stream.flush()
        os.fsync(stream.fileno())
    return storage


class QMP:
    def __init__(self, path: Path, process: subprocess.Popen):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        deadline = time.monotonic() + 8
        while True:
            try:
                self.socket.connect(str(path))
                break
            except (FileNotFoundError, ConnectionRefusedError):
                if process.poll() is not None or time.monotonic() >= deadline:
                    self.socket.close()
                    raise RuntimeError('QEMU did not open its local QMP socket')
                time.sleep(0.05)
        self.socket.settimeout(8)
        self.stream = self.socket.makefile('rwb')
        self.greeting = json.loads(self.stream.readline())
        self.request('qmp_capabilities')

    def request(self, command: str, arguments: dict | None = None):
        self.stream.write(json.dumps({'execute': command, 'arguments': arguments or {}}).encode() + b'\n')
        self.stream.flush()
        while True:
            result = json.loads(self.stream.readline())
            if 'error' in result:
                raise RuntimeError(result['error'])
            if 'return' in result:
                return result['return']

    def close(self):
        self.stream.close()
        self.socket.close()


def run_boot(run_dir: Path, timeout_seconds: int = 600) -> dict:
    if not 1 <= timeout_seconds <= 600:
        raise ValueError('timeout must be between 1 and 600 seconds')
    run_dir = _checked_run_root(PROJECT, run_dir)
    if not run_dir.is_dir():
        raise ValueError('isolated run directory must already exist')
    if any(run_dir.iterdir()):
        raise ValueError('cold boot requires a fresh empty isolated run directory')
    inputs = validate_inputs(PROJECT, run_dir)
    binary = Path(os.environ.get('P2D_QEMU', '/opt/pocket2droid-tcg-build/host/qemu-system-arm')).resolve(strict=True)
    storage = create_ram_fmd(run_dir)
    qmp_path = Path('/tmp') / ('p2d-qmp-' + uuid.uuid4().hex + '.sock')
    command = [str(binary), '-M', f'p2d-devemu,storage={storage}', '-cpu', 'arm920t',
               '-bios', inputs['rom_path'], '-display', 'none', '-monitor', 'none',
               '-serial', 'none', '-S', '-qmp', f'unix:{qmp_path},server=on,wait=off']
    command += ['-d', 'unimp', '-D', str(run_dir / 'mmio.log')]
    result = {**inputs, 'status': 'BOOT_OBSERVED_SHELL_UNVERIFIED',
              'qemu_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
              'command': command, 'guest_progress_evidence': [], 'screenshot_paths': [],
              'disposable_ram_fmd_path': str(storage),
              'storage_reopen': False, 'original_inputs_unchanged': False}
    process = None
    qmp = None
    try:
        with (run_dir / 'qemu.log').open('xb') as log:
            process = subprocess.Popen(command, stdout=log, stderr=log)
            qmp = QMP(qmp_path, process)
            result['qemu_greeting'] = qmp.greeting
            qmp.request('cont')
            begin = time.monotonic()
            for duration in range(0, timeout_seconds, 5):
                time.sleep(min(5, timeout_seconds - duration))
                qmp.request('stop')
                regs = qmp.request('human-monitor-command', {'command-line': 'info registers'})
                result['guest_progress_evidence'].append({'host_elapsed_seconds': time.monotonic() - begin, 'registers': regs})
                qmp.request('cont')
            qmp.request('stop')
            registers = qmp.request('human-monitor-command', {'command-line': 'info registers'})
            pc_match = re.search(r'R15=([0-9a-fA-F]+)', registers)
            if pc_match:
                page = int(pc_match[1], 16) & ~0xfff
                result['active_code_page_va'] = hex(page)
                result['active_code_capture'] = qmp.request('human-monitor-command', {
                    'command-line': f'memsave 0x{page:x} 4096 "{run_dir / "active-code.bin"}"'})
            result['device_registers'] = qmp.request('human-monitor-command', {
                'command-line': 'xp /8wx 0x4a000000'})
            result['timer_registers'] = qmp.request('human-monitor-command', {
                'command-line': 'xp /17wx 0x51000000'})
            result['spi_registers'] = qmp.request('human-monitor-command', {
                'command-line': 'xp /8wx 0x59000020'})
            screenshot = run_dir / 'screen.ppm'
            qmp.request('screendump', {'filename': str(screenshot), 'format': 'ppm'})
            result['screenshot_paths'].append(str(screenshot))
            # The legacy framebuffer address is diagnostic until LCD registers are modelled.
            qmp.request('human-monitor-command', {'command-line': f'pmemsave 0x33f00000 153600 "{run_dir / "framebuffer.raw"}"'})
            qmp.request('quit')
            process.wait(timeout=8)
    except Exception as error:
        result['status'] = 'BOOT_FAILED'
        result['error'] = str(error)
    finally:
        if qmp is not None:
            qmp.close()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        qmp_path.unlink(missing_ok=True)
        result['original_inputs_unchanged'] = validate_inputs(PROJECT, run_dir)['rom_sha256'] == inputs['rom_sha256']
        (run_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["preflight", "boot"])
    parser.add_argument("--run-root", type=Path, default=EXPERIMENT / "results/runs")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    if args.command == 'preflight':
        print(json.dumps(validate_inputs(PROJECT, args.run_root), indent=2))
    else:
        run_dir = create_run_dir(args.run_root)
        result = run_boot(run_dir, args.timeout)
        print(json.dumps({'run_dir': str(run_dir), 'status': result['status'],
                          'original_inputs_unchanged': result['original_inputs_unchanged']}, indent=2))


if __name__ == "__main__":
    main()
