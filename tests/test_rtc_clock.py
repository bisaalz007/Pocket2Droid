"""Deterministic RTC calendar and WinCE-style elapsed timer regressions."""
from pathlib import Path
import os, socket, subprocess, tempfile, time, unittest

class RtcClockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='p2d-brh2-clock-')
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name); (d/'idle.bin').write_bytes(bytes.fromhex('feffffea'))
        self.process = subprocess.Popen([os.environ.get('P2D_QEMU','/opt/pocket2droid-tcg-build/host/qemu-system-arm'),
            '-M','p2d-devemu','-accel','qtest','-bios',str(d/'idle.bin'),'-display','none','-serial','none','-monitor','none',
            '-rtc','base=2026-12-31T23:59:58,clock=vm','-qtest',f'unix:{d}/q.sock,server=on,wait=off','-qtest-log','/dev/null'],
            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        self.addCleanup(self.close)
        self.sock=socket.socket(socket.AF_UNIX); self.sock.settimeout(3)
        for _ in range(100):
            try: self.sock.connect(str(d/'q.sock')); break
            except (FileNotFoundError,ConnectionRefusedError):
                if self.process.poll() is not None: self.fail(self.process.stderr.read().decode())
                time.sleep(.02)
        else: self.fail('QTest did not start')
        self.f=self.sock.makefile('rwb')
    def close(self):
        if hasattr(self,'f'): self.f.close()
        if hasattr(self,'sock'): self.sock.close()
        self.process.terminate(); self.process.wait(timeout=5); self.process.stderr.close()
    def request(self,cmd):
        self.f.write(cmd.encode()+b'\n'); self.f.flush(); r=self.f.readline().decode().split()
        self.assertEqual(r[0],'OK',r); return r[1:]
    def calendar(self):
        return [int(self.request(f'readl {0x57000070+4*i:#x}')[0],0) for i in range(7)]
    def test_calendar_advances_across_year_boundary(self):
        self.assertEqual(self.calendar(),[0x58,0x59,0x23,0x31,0x05,0x12,0x26])
        self.request('clock_step 3000000000')
        self.assertEqual(self.calendar(),[0x01,0,0,0x01,0x06,0x01,0x27])
    def test_elapsed_timer_can_pass_splash_deadline(self):
        # SDL 1.2 WinCE resynchronizes its OS-tick origin to calendar time.
        def seconds(c): return (c[0]>>4)*10+(c[0]&15)
        start=seconds(self.calendar()); origin=0; elapsed=0
        for tick in range(100,4100,100):
            self.request('clock_step 100000000')
            date=((seconds(self.calendar())-start)%60)*1000
            offset=date-(tick-origin)
            if offset < -1000 or offset > 1000: origin-=offset
            elapsed=tick-origin
        self.assertGreaterEqual(elapsed,3000)
if __name__=='__main__': unittest.main(verbosity=2)
