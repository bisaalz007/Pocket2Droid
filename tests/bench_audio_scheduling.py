"""Bounded actual-QEMU synthetic audio workload; no phone/FPS claims."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from run_probe import QMP
from test_rom_cache import rom_loop


def stat(path):
    s=path.read_text()
    return s[s.rindex(')')+2:].split()


def run(binary, audio=True, seconds=4):
    with tempfile.TemporaryDirectory(prefix='p2d-audio-bench-') as directory:
        directory=Path(directory);rom=directory/'loop.bin'
        rom.write_bytes(rom_loop(False))
        qpath=directory/'qtest';mpath=directory/'qmp'
        p=subprocess.Popen([str(binary),'-M','p2d-devemu','-bios',str(rom),
            '-accel','tcg,thread=single','-S','-display','none','-monitor','none',
            '-serial','none','-qtest',f'unix:{qpath},server=on,wait=off',
            '-qtest-log','/dev/null','-qmp',f'unix:{mpath},server=on,wait=off'],
            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        qmp=None;sock=None
        try:
            qmp=QMP(mpath,p);sock=socket.socket(socket.AF_UNIX)
            sock.settimeout(5);sock.connect(str(qpath));stream=sock.makefile('rwb')
            def qt(cmd):
                stream.write((cmd+'\n').encode());stream.flush()
                response=stream.readline().decode().strip()
                if not response.startswith('OK'):raise RuntimeError(response)
                return response
            def wr(addr,val):qt(f'writel 0x{addr:x} 0x{val:x}')
            def rd(addr):return int(qt(f'readl 0x{addr:x}').split()[1],0)
            wr(0x4c000004,0xa1031);wr(0x4c000014,3)
            wr(0x5100003c,25350);wr(0x51000008,(1<<21)|(1<<22))
            wr(0x51000008,(1<<20)|(1<<22))
            if audio:
                for addr,val in [(0x4b000080,0x300ac000),(0x4b000088,0x55000010),
                     (0x4b00008c,3),(0x4b000090,0x8090c350),
                     (0x55000000,0x23),(0x55000004,0xad),(0x55000008,0x42),
                     (0x5500000c,0xa000),(0x4b0000a0,2)]:wr(addr,val)
            qmp.request('cont');time.sleep(.3)
            qmp.request('stop');start_counter=rd(0x30010000)
            before={t.name:stat(t/'stat') for t in Path(f'/proc/{p.pid}/task').iterdir()}
            qmp.request('cont');begin=time.monotonic();time.sleep(seconds)
            qmp.request('stop');wall=time.monotonic()-begin
            after={t.name:stat(t/'stat') for t in Path(f'/proc/{p.pid}/task').iterdir()}
            end_counter=rd(0x30010000);hz=os.sysconf('SC_CLK_TCK')
            tasks=[]
            for tid,a in before.items():
                if tid not in after:continue
                b=after[tid]
                tasks.append({'tid':tid,'name':(Path(f'/proc/{p.pid}/task')/tid/'comm').read_text().strip(),
                    'user_seconds':(int(b[11])-int(a[11]))/hz,
                    'kernel_seconds':(int(b[12])-int(a[12]))/hz})
            return {'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
                'audio':audio,'wall_seconds':wall,'tasks':tasks,
                'guest_loop_iterations':(end_counter-start_counter)&0xffffffff,
                'loop_iterations_per_second':((end_counter-start_counter)&0xffffffff)/wall,
                'dma_count':rd(0x4b000094),'dma_address':rd(0x4b000098),
                'nominal_halfword_period_ns':11361}
        finally:
            if qmp:
                try:qmp.request('quit')
                finally:qmp.close()
            if sock:sock.close()
            if p.poll() is None:p.terminate()
            p.wait(timeout=5);p.stderr.close()


if __name__=='__main__':
    report={'scope':'Synthetic actual x86 Linux/WSL QEMU; IRQ masked tight ARM loop and real-game IIS/clock settings. Not game FPS/Android timing.'}
    report['baseline_audio']=run(ROOT/'results/audio-scheduling/qemu-v656-host',True)
    report['candidate_audio']=run(Path('/opt/pocket2droid-tcg-build/host/qemu-system-arm'),True)
    report['candidate_no_audio']=run(Path('/opt/pocket2droid-tcg-build/host/qemu-system-arm'),False)
    report['baseline_no_audio']=run(ROOT/'results/audio-scheduling/qemu-v656-host',False)
    out=ROOT/'results/audio-scheduling/host-benchmark.json'
    out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
