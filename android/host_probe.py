"""Bounded actual-OS shared-display and private storage/lifecycle verification."""
from pathlib import Path
import ctypes
import fcntl
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
from run_probe import QMP

ROM = PROJECT / 'PC windows mobile 6 Files/Roms and files/pocket pc/Deviceemulation/0409/PPC_USA.BIN'
BINARY = HERE / 'build/qemu-host'
SIZE = 64 + 1024 * 800 * 4

def main():
    assert hashlib.sha256(ROM.read_bytes()).hexdigest() == 'b6ca519070e84da0bf6886fb3bde606ce098a0cfaffff436b8faf46a9a580bf7'
    runs = Path('/opt/pocket2droid-android-tools/host-runs')
    runs.mkdir(exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='frontend-', dir=runs))
    os.chmod(root, 0o700)
    storage, frames, control = [root / n for n in ['ram-fmd.bin', 'frames.bin', 'control.sock']]
    with storage.open('wb') as f: f.truncate(32 * 1024 * 1024)
    with frames.open('wb') as f: f.truncate(SIZE)
    args = [str(BINARY), '-machine', f'p2d-devemu,storage={storage},frame-file={frames},parent-pid={os.getpid()}',
            '-m', '128M', '-bios', str(ROM), '-accel', 'tcg,thread=single', '-display', 'none',
            '-monitor', 'none', '-serial', 'none', '-S', '-qmp', f'unix:{control},server=on,wait=off']
    report = {'run': str(root), 'engine_sha256': hashlib.sha256(BINARY.read_bytes()).hexdigest()}
    log = (root / 'engine.log').open('wb')
    handle = storage.open('r+b')  # Retained before guest can dirty pages.
    process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)
    qmp = None
    try:
        qmp = QMP(control, process)
        duplicate_args = args.copy()
        duplicate_args[-1] = f'unix:{root / "duplicate.sock"},server=on,wait=off'
        duplicate = subprocess.run(duplicate_args, capture_output=True, timeout=5)
        assert duplicate.returncode != 0 and b'owned' in duplicate.stderr, duplicate.stderr
        report['second_storage_owner_rejected'] = True
        qmp.request('cont')
        deadline = time.monotonic() + 35
        observed = set()
        last = None
        with frames.open('rb', buffering=0) as image:
            while time.monotonic() < deadline:
                fcntl.lockf(image.fileno(), fcntl.LOCK_SH)
                try:
                    image.seek(0); raw = image.read(64)
                    if raw[:4] == b'P2DF':
                        version, w, h, fmt = struct.unpack_from('<IIII', raw, 4)
                        seq = struct.unpack_from('<Q', raw, 24)[0]
                        assert version == 1 and fmt == 1 and 0 < w <= 1024 and 0 < h <= 800
                        pixels = image.read(w*h*4)
                        assert len(pixels) == w*h*4
                        observed.add(seq); last = (w,h,seq,pixels)
                finally: fcntl.lockf(image.fileno(), fcntl.LOCK_UN)
                if last is not None and last[2] >= 2 and len(set(struct.iter_unpack('<I',last[3]))) > 4: break
                time.sleep(.05)
        assert last is not None and last[2] >= 2, 'Guest display never published multiple frames'
        qmp.request('stop')
        assert not qmp.request('query-status')['running']
        os.fsync(handle.fileno())
        seq = struct.unpack_from('<Q', frames.read_bytes(),24)[0]
        time.sleep(.15)
        assert struct.unpack_from('<Q',frames.read_bytes(),24)[0] == seq, 'Paused display changed'
        w,h,_,pixels = last
        rgb = bytearray(w*h*3)
        for i in range(w*h): rgb[i*3:i*3+3] = pixels[i*4:i*4+3][::-1]
        (HERE/'build/host-display.ppm').write_bytes(f'P6\n{w} {h}\n255\n'.encode()+rgb)
        report.update(display_width=w, display_height=h, sampled_sequences=len(observed), published_sequence=seq, stop_sync=True,
                      different_pixels=len(set(struct.iter_unpack('<I',pixels))))
        assert report['different_pixels'] > 4
        qmp.request('cont'); assert qmp.request('query-status')['running']
        qmp.request('stop'); os.fsync(handle.fileno())
        qmp.request('quit'); process.wait(timeout=5)
        assert process.returncode == 0
        qmp.close(); qmp = None
        retained = hashlib.sha256(storage.read_bytes()).hexdigest()
        # Reopen stopped engine; no guest execution or previous data conversion.
        process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)
        qmp = QMP(control,process)
        assert hashlib.sha256(storage.read_bytes()).hexdigest() == retained
        qmp.request('quit'); process.wait(timeout=5)
        report['retained_backing_reopens'] = True
    finally:
        if qmp: qmp.close()
        if process.poll() is None:
            process.terminate(); process.wait(timeout=5)
        handle.close(); log.close()
    # Parent guard: only processes created here, with child adoption for reaping.
    ctypes.CDLL(None).prctl(36,1,0,0,0)  # PR_SET_CHILD_SUBREAPER.
    child_control = root/'child.sock'
    child_args = args.copy()
    child_args[-1] = f'unix:{child_control},server=on,wait=off'
    driver = """import os,subprocess,sys,time
args=__import__('json').loads(sys.argv[1]); args[2]=args[2].rsplit('parent-pid=',1)[0]+'parent-pid='+str(os.getpid())
p=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
sys.path.insert(0,sys.argv[2]);from run_probe import QMP
q=QMP(sys.argv[3],p);print(p.pid,flush=True);time.sleep(.1)
os._exit(0)
"""
    controller = subprocess.Popen([sys.executable,'-c',driver,json.dumps(child_args),str(HERE.parent),str(child_control)],stdout=subprocess.PIPE,text=True)
    pid = int(controller.stdout.readline()); controller.wait(timeout=5)
    deadline = time.monotonic()+5
    while time.monotonic()<deadline:
        waited, status = os.waitpid(pid,os.WNOHANG)
        if waited:
            report['parent_death_exit_status'] = status; break
        time.sleep(.03)
    else:
        os.kill(pid,15); os.waitpid(pid,0)
        raise AssertionError('Engine outlived owning controller')
    (HERE/'build/host-probe.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__ == '__main__': main()
