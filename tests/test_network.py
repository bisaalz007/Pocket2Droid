"""Stock SDK PC Card contract, exercised through real MMIO and packet ingress."""
import os, socket, struct, subprocess, time, unittest, uuid
from pathlib import Path
import test_devices as fixture

class NetworkTests(unittest.TestCase):
    request=fixture.DeviceTests.request
    read=fixture.DeviceTests.read
    write=fixture.DeviceTests.write
    cleanup=fixture.DeviceTests.cleanup
    def setUp(self):
        self.path=Path('/tmp')/('p2d-net-'+uuid.uuid4().hex+'.sock')
        self.qmp_path=Path(str(self.path)+'.qmp')
        self.addCleanup(self.cleanup)
        idle=fixture.ROOT/'results/test-inputs/idle.bin';idle.parent.mkdir(parents=True,exist_ok=True);idle.write_bytes(bytes.fromhex('feffffea'))
        online='offline' not in self._testMethodName
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0));self.port=probe.getsockname()[1]
        extra=['-M','p2d-devemu,network=on','-netdev',f'socket,id=p2dnet,listen=127.0.0.1:{self.port}','-net','nic,model=ne2k_pcmcia,netdev=p2dnet,macaddr=02:12:34:56:78:90'] if online else ['-M','p2d-devemu','-nic','none']
        self.process=subprocess.Popen([fixture.BINARY,*extra,'-accel','qtest','-bios',str(idle),'-display','none','-serial','none','-monitor','none','-qtest',f'unix:{self.path},server=on,wait=off','-qmp',f'unix:{self.qmp_path},server=on,wait=off','-qtest-log','/dev/null'],stderr=subprocess.PIPE)
        self.sock=socket.socket(socket.AF_UNIX);self.sock.settimeout(3)
        for _ in range(100):
            try:self.sock.connect(str(self.path));break
            except (FileNotFoundError,ConnectionRefusedError):
                if self.process.poll() is not None:self.fail(self.process.stderr.read().decode())
                time.sleep(.03)
        else:self.fail('QTest not ready')
        self.stream=self.sock.makefile('rwb');self.irq_levels={};self.qmp=fixture.QMP(self.qmp_path,self.process)
    def rb(self,a):return int(self.request(f'readb {a:#x}')[0],0)
    def wb(self,a,v):self.request(f'writeb {a:#x} {v:#x}')
    def pd(self,r,v=None):
        self.wb(0x110003e0,r)
        if v is None:return self.rb(0x110003e1)
        self.wb(0x110003e1,v)
    def io(self,r,v=None):
        if v is None:return self.rb(0x11000300+r)
        self.wb(0x11000300+r,v)
    def enable(self):
        self.pd(2,0x90);self.pd(3,0x41)
        for r,v in [(8,0),(9,3),(10,31),(11,3),(6,0x40)]:self.pd(r,v)
        self.wb(0x100003f8,0x20)
    def dma_event(self):
        self.io(0,0x22);self.io(0xa,0);self.io(0xb,0);self.io(0,0x0a)
    def test_offline_empty_slot_and_no_nic(self):
        self.assertEqual(self.pd(1),0)
        info=self.qmp.request('human-monitor-command',{'command-line':'info network'})
        self.assertNotIn('ne2k',str(info))
    def test_presence_power_and_cis(self):
        self.assertEqual(self.pd(1)&0xc,0xc)
        self.pd(2,0x10);self.assertEqual(self.pd(1)&0x20,0)
        self.pd(2,0x90);self.assertEqual(self.pd(1)&0x20,0x20)
        pos=0;tuples=[]
        while pos<256:
            kind=self.rb(0x10000000+2*pos)
            self.assertEqual(int(self.request(f'readw {0x10000000+2*pos:#x}')[0],0),kind*257)
            if kind==255:break
            length=self.rb(0x10000000+2*(pos+1));tuples.append(kind);pos+=length+2
        self.assertLess(pos,256);self.assertIn(0x14,tuples);self.assertIn(0x1a,tuples)
    def test_disabled_windows_and_cor(self):
        self.enable();self.assertEqual(self.io(0)&1,1)
        self.pd(6,0);self.assertEqual(self.io(0),255)
        self.pd(6,0x40);self.wb(0x100003f8,0);self.assertEqual(self.io(0),255)
        self.wb(0x100003f8,0x20);self.pd(3,1);self.assertEqual(self.io(0),255)
    def test_shared_ram_remote_dma(self):
        self.enable();self.request('writew 0x10004000 0x3412')
        self.io(0,0x22);self.io(0xe,1);self.io(8,0);self.io(9,0x40);self.io(0xa,2);self.io(0xb,0);self.io(0,0x0a)
        self.assertEqual(int(self.request('readw 0x11000310')[0],0),0x3412)
        self.io(8,2);self.io(9,0x40);self.io(0xa,2);self.io(0,0x12);self.request('writew 0x11000310 0xabcd')
        self.assertEqual(int(self.request('readw 0x10004002')[0],0),0xabcd)
    def test_stop_reset_write_and_power_cycle(self):
        self.enable();self.io(0,0x22);self.assertEqual(self.io(7)&0x80,0)
        self.io(0,0x21);self.assertEqual(self.io(7)&0x80,0x80)
        self.request('writew 0x10004000 0x1234');self.io(8,77);self.io(0x1f,0)
        self.assertEqual(self.io(0)&1,1);self.assertEqual(self.io(7),0x80);self.assertEqual(self.io(8),0)
        self.assertEqual(int(self.request('readw 0x10004000')[0],0),0)
        self.io(0,0x22);self.pd(2,0x10);self.assertEqual(self.io(0),255)
        self.pd(2,0x90);self.assertEqual(self.io(0)&1,1)
    def test_masked_irq_unmask_held_level_and_fcsr_ack(self):
        self.enable();self.write(0x560000a4,0);self.dma_event()
        self.assertEqual(self.read(0x560000a8)&0x100,0)
        self.assertEqual(self.rb(0x100003fa)&2,2)
        self.wb(0x100003fa,1);self.assertEqual(self.rb(0x100003fa)&3,0)
        self.io(0xf,0x40);self.assertEqual(self.read(0x560000a8)&0x100,0x100)
        self.write(0x560000a8,0x100);self.assertEqual(self.read(0x560000a8)&0x100,0x100)
        self.io(7,0x40);self.write(0x560000a8,0x100);self.assertEqual(self.read(0x560000a8)&0x100,0)
    def test_management_irq_read_clear(self):
        self.pd(5,8);self.assertEqual(self.read(0x4a000000)&8,8)
        self.assertEqual(self.pd(4),8);self.assertEqual(self.pd(4),0)
        self.write(0x4a000000,8);self.assertEqual(self.read(0x4a000000)&8,0)
    def test_socket_reset_clears_held_irq_and_releases_fresh_chip(self):
        self.enable();self.write(0x560000a4,0);self.io(0xf,0x40);self.dma_event()
        self.assertEqual(self.read(0x560000a8)&0x100,0x100)
        self.pd(3,1);self.assertEqual(self.io(0),255)
        self.write(0x560000a8,0x100);self.assertEqual(self.read(0x560000a8)&0x100,0)
        self.pd(3,0x41);self.assertEqual(self.io(0)&1,1);self.assertEqual(self.io(7),0x80);self.assertEqual(self.rb(0x100003fa)&3,0)
    def test_power_off_drops_receive(self):
        self.enable();self.io(1,0x40);self.io(2,0x80);self.io(3,0x40);self.io(0xc,0x10);self.io(0,0x62);self.io(7,0x41);self.io(0,0x22)
        peer=socket.create_connection(('127.0.0.1',self.port));self.addCleanup(peer.close)
        packet=b'\xff'*6+b'\x02\0\0\0\0\1'+b'\x08\x00'+bytes(46)
        peer.sendall(struct.pack('!I',len(packet))+packet);time.sleep(.05)
        self.io(0,0x62);self.assertEqual(self.io(7),0x42)  # positive receive control
        self.pd(2,0);peer.sendall(struct.pack('!I',len(packet))+packet);time.sleep(.05)
        self.pd(2,0x90);self.io(0,0x62);self.assertEqual(self.io(7),0)
        self.io(0,0x22);self.io(1,0x40);self.io(2,0x80);self.io(3,0x40);self.io(0xc,0x10);self.io(0,0x62);self.io(7,0x41);self.io(0,0x22)
        self.pd(3,1);peer.sendall(struct.pack('!I',len(packet))+packet);time.sleep(.05)
        self.pd(3,0x41);self.io(0,0x62);self.assertEqual(self.io(7),0) # reset-held ingress discarded

if __name__=='__main__':unittest.main()
