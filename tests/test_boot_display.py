"""Real board boot arguments: defaults, explicit sizes, reset and validation."""
import os, socket, subprocess, tempfile, unittest
from pathlib import Path
from run_probe import QMP

BINARY = os.environ.get('P2D_QEMU', '/opt/pocket2droid-tcg-build/host/qemu-system-arm')

class BootDisplayTests(unittest.TestCase):
    def check_size(self, options, width, height):
        with tempfile.TemporaryDirectory(prefix='p2d-display-') as tmp:
            root=Path(tmp); (root/'idle.bin').write_bytes(bytes.fromhex('feffffea'))
            process=subprocess.Popen([BINARY,'-M','p2d-devemu'+options,'-accel','qtest',
                '-bios',str(root/'idle.bin'),'-display','none','-serial','none','-monitor','none',
                '-qtest',f'unix:{root}/qt,server=on,wait=off','-qtest-log','/dev/null',
                '-qmp',f'unix:{root}/qmp,server=on,wait=off'],stderr=subprocess.PIPE)
            qmp=None
            try:
                qmp=QMP(root/'qmp',process)
                if qmp:
                    sock=socket.socket(socket.AF_UNIX);sock.connect(str(root/'qt'))
                    with sock, sock.makefile('rwb') as stream:
                        def request(command):
                            stream.write((command+'\n').encode());stream.flush()
                            result=stream.readline().decode().strip().split()
                            self.assertEqual(result[0],'OK');return result[1:]
                        for repeat in range(2):
                            self.assertEqual(int(request('readl 0x30020044')[0],0),0xde12de34)
                            self.assertEqual(int(request('readw 0x30020048')[0],0),width)
                            self.assertEqual(int(request('readw 0x3002004a')[0],0),height)
                            self.assertEqual(int(request('readw 0x3002004c')[0],0),16)
                            request('writew 0x30020048 0x1');qmp.request('system_reset')
            finally:
                if qmp:qmp.close()
                process.terminate();process.wait(timeout=5);process.stderr.close()

    def test_backward_default(self): self.check_size('',240,320)
    def test_all_presets_and_reset(self):
        for width,height in [(176,220),(240,240),(240,320),(320,240),(320,320),
                             (240,400),(480,480),(480,640),(480,800)]:
            with self.subTest(width=width,height=height):
                self.check_size(f',screen-width={width},screen-height={height}',width,height)
    def test_invalid_dimensions_fail_closed(self):
        for option in ['screen-width=0','screen-width=-1',
                       'screen-height=0','screen-height=not-a-number','screen-width=65536']:
            result=subprocess.run([BINARY,'-M','p2d-devemu,'+option,'-display','none'],
                                  capture_output=True,timeout=5)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('Invalid screen-',result.stderr.decode())

    def test_custom_sizes_are_not_capped_by_the_old_transport(self):
        for width,height in [(1280,960),(3840,2160),(65535,65535)]:
            with self.subTest(width=width,height=height):
                self.check_size(f',screen-width={width},screen-height={height}',width,height)

if __name__=='__main__': unittest.main()
