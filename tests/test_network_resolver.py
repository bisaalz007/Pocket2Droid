"""Real private-file resolver and UDP forwarding through pinned libslirp."""
from pathlib import Path
import os, socket, subprocess, tempfile, threading, unittest
ROOT=Path(__file__).resolve().parents[1]
class ResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prefix=ROOT/'android/build/networking'/os.environ.get('P2D_SLIRP_VARIANT','host')
        cls.binary=prefix/'resolver-probe'
        flags=subprocess.check_output(['pkg-config','--cflags','--libs','glib-2.0'],text=True).split()
        subprocess.run(['cc','-Wall','-I'+str(prefix/'include'),str(ROOT/'tests/network_resolver_probe.c'),str(prefix/'lib/libslirp.a'),*flags,'-o',str(cls.binary)],check=True)
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='p2d-dns-');self.addCleanup(self.tmp.cleanup);self.file=Path(self.tmp.name)/'resolv.conf'
        self.proc=subprocess.Popen([str(self.binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,env=dict(os.environ,P2D_SLIRP_RESOLV_CONF=str(self.file)))
        self.addCleanup(self.close)
    def close(self):
        self.proc.stdin.close();self.proc.wait(timeout=3);self.proc.stdout.close()
    def put(self,data):
        temp=self.file.with_suffix('.tmp');temp.write_bytes(data);temp.replace(self.file)
    def query(self,mode='4'):
        self.proc.stdin.write(mode+'\n');self.proc.stdin.flush();lines=[]
        while True:
            line=self.proc.stdout.readline().strip()
            if line=='done':return lines
            self.assertTrue(line,'probe terminated unexpectedly');lines.append(line)
    def test_missing_empty_malformed_oversized_and_recovery(self):
        for data in [None,b'',b'nameserver not-an-address\n',b'x'*4097]:
            if data is not None:self.put(data)
            self.assertEqual(self.query(),['resolver none'])
        self.put(b'nameserver 127.77.0.1\n');self.assertEqual(self.query(),['resolver 127.77.0.1'])
    def test_same_length_atomic_replacement_and_ipv6(self):
        self.put(b'nameserver 127.77.0.1\n');self.assertEqual(self.query(),['resolver 127.77.0.1'])
        self.put(b'nameserver 127.77.0.2\n');self.assertEqual(self.query(),['resolver 127.77.0.2'])
        self.put(b'nameserver ::1\n');self.assertEqual(self.query(),['resolver none']);self.assertEqual(self.query('6'),['resolver ::1'])
    def server(self,address,answer):
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind((address,53));sock.settimeout(.1)
        stop=threading.Event()
        def serve():
            while not stop.is_set():
                try:data,peer=sock.recvfrom(4096)
                except socket.timeout:continue
                response=data[:2]+b'\x81\x80\0\1\0\1\0\0\0\0'+data[12:]+b'\xc0\x0c\0\1\0\1\0\0\0\1\0\4'+socket.inet_aton(answer)
                sock.sendto(response,peer)
        thread=threading.Thread(target=serve);thread.start()
        def close():stop.set();thread.join();sock.close()
        self.addCleanup(close)
    def test_actual_nat_dns_and_network_replacement(self):
        self.server('127.77.0.1','192.0.2.1');self.server('127.77.0.2','192.0.2.2')
        for server,tail in [('127.77.0.1','c0000201'),('127.77.0.2','c0000202')]:
            self.put(('nameserver '+server+'\n').encode());lines=self.query('n')
            self.assertEqual(lines[0],'resolver '+server);self.assertTrue(any(x.startswith('packet ') and x.endswith(tail) for x in lines),lines)
        self.put(b'nameserver 127.77.0.3\n');self.assertIn('timeout',self.query('n'))
        self.put(b'nameserver ::1\n');self.assertIn('timeout',self.query('n')) # IPv4 guest cannot use IPv6-only upstream
if __name__=='__main__':unittest.main()
