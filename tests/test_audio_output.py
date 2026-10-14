"""Actual C producer against independent protocol and file-lock fixtures."""
import fcntl, mmap, os, struct, subprocess, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SIZE = 67648
class AudioOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert (ROOT/'qemu/hw/dma/p2d-audio.c').exists(), 'Missing bounded audio producer'
        cls.tmp = tempfile.TemporaryDirectory(prefix='p2d-audio-')
        cls.bin = Path(cls.tmp.name)/'producer'
        subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(ROOT/'qemu/include'),
            str(ROOT/'tests/audio-output-test.c'),str(ROOT/'qemu/hw/dma/p2d-audio.c'),'-o',str(cls.bin)],check=True)
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(); self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name)/'audio.bin'
        data = bytearray(SIZE); struct.pack_into('<5I',data,0,0x41443250,1,SIZE,64,65536)
        self.path.write_bytes(data)
    def run_producer(self,n=1,path=None):
        return subprocess.run([str(self.bin),str(path or self.path),str(n)],capture_output=True,text=True,timeout=3)
    def test_actual_signed_stereo_bytes(self):
        r=self.run_producer(); self.assertEqual(r.returncode,0,r.stderr); self.assertIn('PUBLISHED 1',r.stdout)
        data=self.path.read_bytes(); self.assertEqual(struct.unpack_from('<4h',data,2112),(32767,-32768,123,-456))
        self.assertEqual(struct.unpack_from('<4I',data,64),(7,48000,2,0))
        self.assertEqual(struct.unpack_from('<4I',data,20),(1,0,8,0))
    def test_overflow_discards_whole_packets_and_caps_duration(self):
        r=self.run_producer(100); self.assertEqual(r.returncode,0,r.stderr)
        data=self.path.read_bytes(); wp,rp,wb,rb=struct.unpack_from('<4I',data,20)
        self.assertEqual(wp,100); self.assertLessEqual(wp-rp,20); self.assertEqual(wb-rb,(wp-rp)*1920)
        self.assertGreater(struct.unpack_from('<I',data,40)[0],0)
        for seq in range(rp,wp):
            epoch,rate,frames,start=struct.unpack_from('<4I',data,64+(seq%64)*32)
            self.assertEqual((epoch,rate,frames),(7,48000,480)); self.assertEqual(start%4,0)
            first=2112+start%65536
            self.assertEqual(struct.unpack_from('<2h',data,first),(32767,-32768))
    def test_single_packet_cannot_exceed_duration_bound(self):
        before=self.path.read_bytes()
        r=self.run_producer(-1)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('PUBLISHED 0',r.stdout)
        self.assertEqual(self.path.read_bytes(),before)
    def test_counter_wrap_preserves_complete_packet(self):
        data=bytearray(self.path.read_bytes()); struct.pack_into('<4I',data,20,0xffffffff,0xffffffff,0xfffffffc,0xfffffffc)
        self.path.write_bytes(data); self.assertEqual(self.run_producer().returncode,0)
        data=self.path.read_bytes(); self.assertEqual(struct.unpack_from('<4I',data,20),(0,0xffffffff,4,0xfffffffc))
        self.assertEqual(struct.unpack_from('<2h',data,2112+65532),(32767,-32768))
        self.assertEqual(struct.unpack_from('<2h',data,2112),(123,-456))
    def test_contention_returns_before_lock_released(self):
        before=self.path.read_bytes()
        with self.path.open('r+b') as f:
            fcntl.lockf(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            r=self.run_producer(); self.assertEqual(r.returncode,2); self.assertIn('OPEN_FAILED',r.stdout)
            self.assertEqual(self.path.read_bytes(),before)
    def test_missing_symlink_wrong_size_and_nonregular_rejected(self):
        for p in [Path(self.dir.name)/'absent',Path(self.dir.name)]: self.assertEqual(self.run_producer(path=p).returncode,2)
        link=Path(self.dir.name)/'link'; link.symlink_to(self.path); self.assertEqual(self.run_producer(path=link).returncode,2)
        self.path.write_bytes(bytes(17)); self.assertEqual(self.run_producer().returncode,2)
    def test_corrupt_queue_not_used(self):
        for offset,value in [(0,37),(8,1),(20,65),(28,65540),(44,999)]:
            self.setUp(); data=bytearray(self.path.read_bytes()); struct.pack_into('<I',data,offset,value); self.path.write_bytes(data)
            self.assertEqual(self.run_producer().returncode,2,(offset,value))
            self.assertEqual(self.path.read_bytes(),data)
if __name__=='__main__': unittest.main()
