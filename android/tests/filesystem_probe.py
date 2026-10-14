"""Reproduce guest filesystem failures on a disposable PC copy, never phone data."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile, time

HERE = Path(__file__).resolve().parents[1]
PROJECT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
from run_probe import QMP

class Owner:
    def poll(self): return None

def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['launch', 'capture', 'tap', 'key', 'quit'])
    p.add_argument('--run', type=Path)
    p.add_argument('--x', type=int); p.add_argument('--y', type=int)
    p.add_argument('--key'); p.add_argument('--seconds', type=int, default=300)
    p.add_argument('--snapshot', type=Path)
    a = p.parse_args()
    allowed = Path('/opt/pocket2droid-android-tools/filesystem-runs')
    if a.action == 'launch':
        allowed.mkdir(exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix='probe-', dir=allowed))
        fixture = PROJECT/'EXPERIMENTS/qemu-devemu/benchmarks/game-import/results/native-runs/20261007T213708Z-638c3f4415d3/ram-fmd-final.bin'
        expected = '8865961036fcb3f9033d2a1d7ff6f7731ed1f6521ce7cbe13d80d601f5a8eebd'
        if a.snapshot:
            snapshot = a.snapshot.resolve(strict=True)
            assert snapshot.is_relative_to((HERE/'build/filesystem-phone').resolve())
            metadata = json.loads((snapshot/'snapshot.json').read_text())
            assert metadata['read_only_source'] is True and metadata['ram-fmd.bin']['bytes'] == 33554432
            fixture = snapshot/'ram-fmd.bin'; expected = metadata['ram-fmd.bin']['sha256']
        assert hashlib.sha256(fixture.read_bytes()).hexdigest() == expected
        shutil.copyfile(fixture, root/'ram-fmd.bin')
        rom = PROJECT/'PC windows mobile 6 Files/Roms and files/pocket pc/Deviceemulation/0409/PPC_USA.BIN'
        assert hashlib.sha256(rom.read_bytes()).hexdigest() == 'b6ca519070e84da0bf6886fb3bde606ce098a0cfaffff436b8faf46a9a580bf7'
        cab = PROJECT/'DOCUMENTATION/PHONE_EVIDENCE/v644/game-files/rt_filao_efigs_retail_ppc.cab'
        args = [str(HERE/'build/qemu-host'), '-machine', f'p2d-devemu,storage={root}/ram-fmd.bin,import-file={cab},parent-pid={os.getpid()}',
                '-bios', str(rom), '-m', '128M', '-accel', 'tcg,thread=single', '-display', 'none', '-serial', 'none', '-monitor', 'none',
                '-S', '-qmp', f'unix:{root}/control.sock,server=on,wait=off', '-d', 'unimp', '-D', str(root/'mmio.log')]
        with (root/'engine.log').open('wb') as log:
            child = subprocess.Popen(args, stdout=log, stderr=log)
            try:
                q = QMP(root/'control.sock', child); q.request('cont'); q.close()
                record = {'pid': child.pid, 'args': args, 'engine_sha256': hashlib.sha256(Path(args[0]).read_bytes()).hexdigest(),
                          'copied_storage_sha256':expected, 'original_storage':str(fixture)}
                (root/'owner.json').write_text(json.dumps(record, indent=2))
                print(str(root), flush=True)
                try: child.wait(timeout=a.seconds)
                except subprocess.TimeoutExpired:
                    q = QMP(root/'control.sock', child); q.request('quit'); q.close(); child.wait(timeout=5)
            finally:
                if child.poll() is None: child.terminate(); child.wait(timeout=5)
        return
    root = a.run.resolve(strict=True)
    assert root.parent == allowed.resolve() and root.name.startswith('probe-')
    record = json.loads((root/'owner.json').read_text())
    actual = Path(f'/proc/{record["pid"]}/cmdline').read_bytes().split(b'\0')[:-1]
    assert actual == [x.encode() for x in record['args']], 'Recorded engine ownership lost'
    q = QMP(root/'control.sock', Owner())
    try:
        if a.action == 'quit': q.request('quit'); return
        if a.action == 'tap':
            assert 0 <= a.x < 240 and 0 <= a.y < 320
            q.request('input-send-event', {'events': [
                {'type': 'abs', 'data': {'axis': 'x', 'value': round(a.x*32767/239)}},
                {'type': 'abs', 'data': {'axis': 'y', 'value': round(a.y*32767/319)}},
                {'type': 'btn', 'data': {'button': 'left', 'down': True}}]})
            time.sleep(.15)
            q.request('input-send-event', {'events': [{'type': 'btn', 'data': {'button': 'left', 'down': False}}]})
        if a.action == 'key':
            assert a.key in ['up','down','left','right','tab','ret','esc','spc']
            for down in [True, False]:
                q.request('input-send-event', {'events': [{'type':'key','data': {'down':down,'key':{'type':'qcode','data':a.key}}}]})
                if down: time.sleep(.15)
        if a.action in ['tap', 'key']: time.sleep(.5)
        q.request('stop')
        stamp = time.time_ns(); image = root/f'{stamp}.ppm'
        q.request('screendump', {'filename':str(image), 'format':'ppm'})
        shutil.copyfile(image, HERE/'build/filesystem-probe-current.ppm')
        report = {'image':str(image), 'registers':q.request('human-monitor-command', {'command-line':'info registers'}),
                  'interrupts':q.request('human-monitor-command', {'command-line':'xp /8wx 0x4a000000'})}
        (root/f'{stamp}.json').write_text(json.dumps(report, indent=2))
        q.request('cont'); print(json.dumps(report), flush=True)
    finally: q.close()

if __name__ == '__main__': main()
