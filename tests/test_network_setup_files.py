"""Helper overlay through real VCEFS MMIO, with real filesystem collisions."""
from pathlib import Path
import errno
import fcntl
import importlib.util
import os
import shutil
import struct
import tempfile
from unittest.mock import patch
import test_devices
import test_shared_folder

ROOT=Path(__file__).resolve().parents[1]


class NetworkSetupFilesTests(test_shared_folder.SharedFolderTests):
    @classmethod
    def setUpClass(cls):
        cls.build_temp=tempfile.TemporaryDirectory(prefix='p2d-setup-fixture-')
        spec=importlib.util.spec_from_file_location('p2d_setup_fixture_builder',ROOT/'guest/network-setup/build.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        cls.built=Path(cls.build_temp.name);module.build(cls.built)
        cls.denied_mode=cls.built/'deny-net-setup-fchmod.so'
        test_devices.subprocess.run(['cc','-shared','-fPIC','-Wall','-Werror',
                                    str(ROOT/'tests/deny_net_setup_fchmod.c'),
                                    '-ldl','-o',str(cls.denied_mode)],check=True)

    @classmethod
    def tearDownClass(cls):cls.build_temp.cleanup()

    def setUp(self):
        self.asset_temp=tempfile.TemporaryDirectory(prefix='p2d-setup-asset-')
        self.addCleanup(self.asset_temp.cleanup)
        self.helper=Path(self.asset_temp.name)/'setup.exe'
        shutil.copy2(self.built/'autorun.exe',self.helper)
        self.expected=self.helper.read_bytes()
        original=test_devices.subprocess.Popen
        def launch(args,**kwargs):
            args=list(args);m=args.index('-M')+1
            path=str(self.helper)+('.missing' if 'missing_helper' in self._testMethodName else '')
            args[m]+=(',network=on' if 'offline' not in self._testMethodName else '')+',network-setup='+path
            args+=['-nic','none']
            if 'denied_memfd_mode' in self._testMethodName:
                kwargs['env']=dict(os.environ,LD_PRELOAD=str(self.denied_mode))
            return original(args,**kwargs)
        with patch('test_devices.subprocess.Popen',side_effect=launch):super().setUp()

    def virtual_read(self,handle,count=64,position=0):
        struct.pack_into('<H',self.pb,10,handle)
        struct.pack_into('<III',self.pb,16,count,position,test_shared_folder.DTA)
        self.assertEqual(self.command(7),0)
        n=struct.unpack_from('<I',self.pb,16)[0]
        return self.get(test_shared_folder.DTA,n)

    def test_setup_readonly_stat_open_and_directory(self):
        self.assertEqual(self.info('\\2577'),0)
        self.assertEqual(struct.unpack_from('<H',self.pb,28)[0]&17,17)
        self.assertEqual(self.info('\\2577\\AUTORUN.EXE'),0)
        self.assertEqual(struct.unpack_from('<I',self.pb,16)[0],len(self.expected))
        self.assertTrue(struct.unpack_from('<H',self.pb,28)[0]&1)
        h=self.open('\\2577\\AuToRuN.ExE')
        self.assertEqual(self.virtual_read(h),self.expected[:64])
        self.assertEqual(self.info('\\2577\\missing.exe'),2)
        self.assertFalse((self.root/'2577').exists(),'Overlay never publishes into actual card')

    def test_setup_enumeration_has_each_virtual_name_once(self):
        names=[];index=0;result=self.info('\\*.*',7,0)
        while result==0:
            names.append(self.returned_name());index+=1
            result=self.info('unused',7,index)
        self.assertEqual(result,18)
        self.assertEqual(names.count('2577'),1)
        self.assertIn('readme.txt',names)
        self.assertEqual(self.info('\\2577\\*.*',8,0),0)
        self.assertEqual(self.returned_name(),'autorun.exe')
        self.assertEqual(self.info('unused',8,1),18)

    def test_setup_hidden_metadata_preserves_autorun_access(self):
        self.assertEqual(self.info('\\2577'),0)
        self.assertEqual(struct.unpack_from('<H',self.pb,28)[0],0x13,
                         'Virtual helper directory must be hidden and read-only')
        self.assertEqual(self.info('\\2577\\autorun.exe'),0)
        self.assertEqual(struct.unpack_from('<H',self.pb,28)[0],0x23)
        attrs={};index=0;result=self.info('\\*.*',7,0)
        while result==0:
            attrs[self.returned_name()]=struct.unpack_from('<H',self.pb,28)[0]
            index+=1;result=self.info('unused',7,index)
        self.assertEqual(result,18)
        self.assertEqual(attrs['2577'],0x13)
        self.assertFalse(attrs['readme.txt']&2,'Ordinary user files stay visible')
        self.assertEqual(self.info('\\2577\\*.*',8,0),0)
        self.assertEqual(self.returned_name(),'autorun.exe')
        self.assertEqual(struct.unpack_from('<H',self.pb,28)[0],0x23)
        handle=self.open('\\2577\\AUTORUN.EXE')
        self.assertEqual(self.virtual_read(handle),self.expected[:64],
                         'Hidden metadata must not prevent autorun from reading the helper')
        self.assertFalse((self.root/'2577').exists())

    def test_setup_real_2577_folder_keeps_user_visibility(self):
        folder=self.root/'2577';folder.mkdir()
        (folder/'autorun.exe').write_bytes(b'user-owned autorun')
        self.assertEqual(self.info('\\2577'),0)
        self.assertFalse(struct.unpack_from('<H',self.pb,28)[0]&2,
                         'A real user folder must not inherit virtual hidden metadata')
        self.assertEqual(self.info('\\2577\\autorun.exe'),0)
        self.assertFalse(struct.unpack_from('<H',self.pb,28)[0]&2)
        handle=self.open('\\2577\\autorun.exe')
        self.assertEqual(self.virtual_read(handle),b'user-owned autorun')
        self.assertEqual((folder/'autorun.exe').read_bytes(),b'user-owned autorun')

    def test_setup_rejects_mutation_and_leaves_user_files_writable(self):
        for mode in (1,2):
            struct.pack_into('<H',self.pb,30,mode)
            self.assertEqual(self.command(6,'\\2577\\autorun.exe'),5)
        for command in (5,0xc,0xd,0xe,0x10):
            self.assertEqual(self.command(command,'\\2577\\autorun.exe'),5)
        self.name('\\2577\\replacement.exe',True)
        self.assertEqual(self.command(0xf,'\\readme.txt'),5)
        self.assertEqual((self.root/'readme.txt').read_bytes(),b'hello')
        self.assertEqual(self.command(0xc,'\\NewUserFolder'),0)
        self.assertTrue((self.root/'NewUserFolder').is_dir())
        self.assertEqual(self.info('\\2577\\..\\..\\secret'),123)

    def test_setup_real_collision_takes_ownership_but_open_snapshot_survives(self):
        h=self.open('\\2577\\autorun.exe')
        (self.root/'2577').mkdir();(self.root/'2577/AUTORUN.EXE').write_bytes(b'owned-user-file')
        real=self.open('\\2577\\autorun.exe')
        self.assertEqual(self.virtual_read(real),b'owned-user-file')
        self.assertEqual(self.virtual_read(h),self.expected[:64])
        self.assertEqual((self.root/'2577/AUTORUN.EXE').read_bytes(),b'owned-user-file')

    def test_setup_symlink_collision_preserves_outside(self):
        (self.root/'2577').symlink_to(self.outside,target_is_directory=True)
        self.assertEqual(self.info('\\2577\\autorun.exe'),5)
        self.assertEqual((self.outside/'secret').read_bytes(),b'untouched')
        self.assertEqual(self.info('\\readme.txt'),0)

    def test_setup_offline_ignores_helper(self):
        self.assertIn(self.info('\\2577\\autorun.exe'),(2,3))
        self.assertEqual(self.info('\\readme.txt'),0)

    def test_setup_missing_helper_keeps_normal_card_usable(self):
        self.assertIn(self.info('\\2577\\autorun.exe'),(2,3))
        self.assertEqual(self.info('\\readme.txt'),0)

    def test_setup_snapshots_bytes_before_source_mutation(self):
        self.helper.write_bytes(b'changed source')
        h=self.open('\\2577\\autorun.exe')
        self.assertEqual(self.virtual_read(h),self.expected[:64])

    def test_setup_denied_memfd_mode_keeps_sealed_guest_readonly(self):
        self.assertEqual(self.info('\\2577\\autorun.exe'),0,
                         'Android chmod denial must not hide a sealable helper')
        self.assertTrue(struct.unpack_from('<H',self.pb,28)[0]&1)
        handle=self.open('\\2577\\autorun.exe')
        self.assertEqual(self.virtual_read(handle),self.expected[:64])
        self.assertEqual(self.command(0xe,'\\2577\\autorun.exe'),5)
        snapshots=[fd for fd in Path('/proc',str(self.process.pid),'fd').iterdir()
                   if 'memfd:p2d-network-setup' in str(fd.readlink())]
        self.assertTrue(snapshots,'The helper has an immutable backing file')
        fd=os.open(snapshots[0],os.O_RDWR)
        try:
            expected=fcntl.F_SEAL_WRITE|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL
            self.assertEqual(fcntl.fcntl(fd,fcntl.F_GET_SEALS)&expected,expected)
            for mutation in (lambda:os.pwrite(fd,b'X',0),
                             lambda:os.ftruncate(fd,len(self.expected)+1),
                             lambda:os.ftruncate(fd,len(self.expected)-1)):
                with self.assertRaises(OSError) as failure:mutation()
                self.assertEqual(failure.exception.errno,errno.EPERM)
            self.assertEqual(os.pread(fd,len(self.expected),0),self.expected)
        finally:os.close(fd)


# Borrow the existing transport/filesystem helpers without rediscovering their
# entire test class here. The original suites still run in their own modules.
for _name in dir(test_shared_folder.SharedFolderTests):
    if _name.startswith('test_') and not _name.startswith('test_setup_'):
        setattr(NetworkSetupFilesTests,_name,None)
