"""Actual VCEFS MMIO: unsupported rename, interruption, collisions and recovery."""
import hashlib,os,struct,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import test_shared_folder as shared
import test_devices

class MoveCompatibilityTests(shared.SharedFolderTests):
    @classmethod
    def setUpClass(cls):
        cls.fault_temp=tempfile.TemporaryDirectory(prefix='p2d-move-faults-')
        cls.fault_library=Path(cls.fault_temp.name)/'faults.so'
        subprocess.run(['cc','-shared','-fPIC',str(Path(__file__).with_name('move_faults.c')),
                        '-ldl','-o',str(cls.fault_library)],check=True)
    @classmethod
    def tearDownClass(cls):cls.fault_temp.cleanup()
    def launch(self,original,args,kwargs,faults):
        args=list(args);self.private=Path(self.temp.name)/'private';self.private.mkdir(exist_ok=True)
        self.store=self.private/'ram-fmd.bin'
        if not self.store.exists():
            with self.store.open('xb') as f:f.truncate(33554432)
        args[args.index('-M')+1]+=f',storage={self.store},storage-lock={self.private}/engine-storage.lock'
        env=dict(os.environ)
        if faults:
            env.update(LD_PRELOAD=str(self.fault_library),P2D_TEST_MOVE_RENAME_FAIL='1')
            if 'partial' in self._testMethodName:env['P2D_TEST_MOVE_WRITE_TARGET']=str(self.root/'moved.bin')
            if 'complete' in self._testMethodName:
                env.update(P2D_TEST_MOVE_SYNC_TARGET=str(self.root),P2D_TEST_MOVE_SYNC_NTH='0')
            if 'retirement' in self._testMethodName:
                env.update(P2D_TEST_MOVE_SYNC_TARGET=str(self.private),P2D_TEST_MOVE_SYNC_NTH='2')
            if 'normal_boundary' in self._testMethodName:
                name='readme.txt' if 'source' in self._testMethodName else 'moved.bin'
                env.update(self.swap_env(name))
        self.engine_args=args
        return original(args,**dict(kwargs,env=env))
    def setUp(self):
        original=test_devices.subprocess.Popen
        with patch('test_devices.subprocess.Popen',side_effect=lambda args,**kwargs:self.launch(original,args,kwargs,True)):
            super().setUp()
    def restart(self):
        self.qmp.request('quit');self.process.wait(timeout=5);self.cleanup();self._cleanups.pop()
        original=test_devices.subprocess.Popen
        def launch(args,**kwargs):
            args=list(args);args[args.index('-M')+1]+=f',shared-folder={self.root}'
            return self.launch(original,args,kwargs,False)
        with patch('test_devices.subprocess.Popen',side_effect=launch):test_devices.DeviceTests.setUp(self)
    def move(self):
        self.name('\\moved.bin',second=True);return self.command(0xf,'\\readme.txt')
    def records(self):return list(self.private.glob('.guest-move-*.pending'))
    def recovery_record(self,target='moved.bin',claimed=False,target_stat=None):
        source=self.root/'readme.txt';st=source.stat();payload=source.read_bytes()
        record=self.private/'.guest-move-0123456789abcdef.pending'
        text=(f'[Move]\nSource=readme.txt\nTarget={target}\n'
              f'SHA256={hashlib.sha256(payload).hexdigest()}\nBytes={len(payload)}\n'
              f'SourceDevice={st.st_dev}\nSourceInode={st.st_ino}\nClaimed=false\n')
        if claimed:
            text+=f'TargetDevice={target_stat.st_dev}\nTargetInode={target_stat.st_ino}\nClaimed=true\n'
        record.write_text(text)
        return record
    def swap_env(self,name):
        return dict(P2D_TEST_MOVE_SWAP_DIR=str(self.root),P2D_TEST_MOVE_SWAP_NAME=str(self.root/name),
                    P2D_TEST_MOVE_SWAP_REPLACEMENT=str(self.root/'replacement'),P2D_TEST_MOVE_SWAP_BACKUP=str(self.root/'backup'))
    def recovery_rejected(self,faults=None):
        self.qmp.request('quit');self.process.wait(timeout=5);self.cleanup();self._cleanups.pop()
        env=dict(os.environ)
        if faults:env.update(LD_PRELOAD=str(self.fault_library),**faults)
        result=subprocess.run(self.engine_args,stderr=subprocess.PIPE,stdout=subprocess.PIPE,timeout=5,env=env)
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b'SD-card move recovery incomplete',result.stderr)
        self.path.unlink(missing_ok=True);self.qmp_path.unlink(missing_ok=True)
    def test_move_complete_bytes_and_no_record(self):
        # This method deliberately tests a failed directory fsync after a full copy.
        self.assertEqual(self.move(),31)
        self.assertEqual((self.root/'moved.bin').read_bytes(),b'hello')
        self.assertEqual((self.root/'readme.txt').read_bytes(),b'hello')
        self.assertEqual(len(self.records()),1)
        self.assertEqual(self.info('\\moved.bin'),31,'Incomplete publication blocks card reads')
        self.restart()
        self.assertFalse((self.root/'readme.txt').exists())
        self.assertEqual((self.root/'moved.bin').read_bytes(),b'hello')
        self.assertEqual(self.records(),[])
    def test_move_successful_regular_file(self):
        (self.root/'readme.txt').write_bytes(bytes(range(256))*300)
        self.assertEqual(self.move(),0)
        self.assertFalse((self.root/'readme.txt').exists())
        self.assertEqual((self.root/'moved.bin').read_bytes(),bytes(range(256))*300)
        self.assertEqual(self.records(),[])
    def test_move_existing_destination_preserved(self):
        (self.root/'moved.bin').write_bytes(b'existing-save')
        self.assertEqual(self.move(),80)
        self.assertEqual((self.root/'moved.bin').read_bytes(),b'existing-save')
        self.assertEqual((self.root/'readme.txt').read_bytes(),b'hello')
        self.assertEqual(self.records(),[])
    def test_move_partial_copy_preserves_source_and_blocks_card(self):
        (self.root/'readme.txt').write_bytes(b'original-complete-save')
        self.assertEqual(self.move(),31)
        self.assertEqual((self.root/'moved.bin').read_bytes(),b'origina')
        self.assertEqual((self.root/'readme.txt').read_bytes(),b'original-complete-save')
        self.assertEqual(len(self.records()),1)
        self.assertEqual(self.command(5,'\\other'),31)
        self.recovery_rejected()
        self.assertEqual((self.root/'readme.txt').read_bytes(),b'original-complete-save')
        self.assertEqual((self.root/'moved.bin').read_bytes(),b'origina')
        self.assertEqual(len(self.records()),1)
    def test_move_recovery_unclaimed_matching_destination_preserved(self):
        (self.root/'moved.bin').write_bytes(b'hello')
        record=self.recovery_record()
        self.recovery_rejected()
        self.assertEqual((self.root/'readme.txt').read_bytes(),b'hello')
        self.assertEqual((self.root/'moved.bin').read_bytes(),b'hello');self.assertTrue(record.exists())
    def test_move_recovery_case_only_alias_preserved(self):
        record=self.recovery_record('README.TXT')
        self.recovery_rejected()
        self.assertEqual((self.root/'readme.txt').read_bytes(),b'hello');self.assertTrue(record.exists())
    def test_move_recovery_claimed_inode_alias_preserved(self):
        os.link(self.root/'readme.txt',self.root/'moved.bin')
        record=self.recovery_record(claimed=True,target_stat=(self.root/'moved.bin').stat())
        self.recovery_rejected()
        self.assertEqual((self.root/'readme.txt').read_bytes(),b'hello');self.assertTrue(record.exists())
    def test_move_recovery_claimed_destination_replaced(self):
        target=self.root/'moved.bin';target.write_bytes(b'hello')
        record=self.recovery_record(claimed=True,target_stat=target.stat())
        replacement=self.root/'replacement';replacement.write_bytes(b'hello');replacement.replace(target)
        self.recovery_rejected()
        self.assertEqual((self.root/'readme.txt').read_bytes(),b'hello')
        self.assertEqual(target.read_bytes(),b'hello');self.assertTrue(record.exists())
    def test_move_recovery_torn_claim_preserves_files(self):
        (self.root/'moved.bin').write_bytes(b'hello')
        record=self.recovery_record()
        with record.open('a') as f:f.write('Claimed=true\nTargetDevice=')
        self.recovery_rejected()
        self.assertEqual((self.root/'readme.txt').read_bytes(),b'hello')
        self.assertEqual((self.root/'moved.bin').read_bytes(),b'hello');self.assertTrue(record.exists())
    def test_move_recovery_absent_destination_rolls_back(self):
        self.recovery_record()
        self.restart()
        self.assertEqual((self.root/'readme.txt').read_bytes(),b'hello');self.assertEqual(self.records(),[])
    def test_move_normal_boundary_source_replacement_preserved(self):
        (self.root/'replacement').write_bytes(b'new-save')
        self.assertEqual(self.move(),32)
        self.assertEqual((self.root/'readme.txt').read_bytes(),b'new-save')
        self.assertEqual((self.root/'backup').read_bytes(),b'hello')
        self.assertEqual((self.root/'moved.bin').read_bytes(),b'hello');self.assertEqual(len(self.records()),1)
    def test_move_normal_boundary_target_replacement_preserved(self):
        (self.root/'replacement').write_bytes(b'new-save')
        self.assertEqual(self.move(),32)
        self.assertEqual((self.root/'readme.txt').read_bytes(),b'hello')
        self.assertEqual((self.root/'moved.bin').read_bytes(),b'new-save')
        self.assertEqual((self.root/'backup').read_bytes(),b'hello');self.assertEqual(len(self.records()),1)
    def test_move_recovery_boundary_target_replacement_preserved(self):
        (self.root/'moved.bin').write_bytes(b'hello');(self.root/'replacement').write_bytes(b'new-save')
        self.recovery_record(claimed=True,target_stat=(self.root/'moved.bin').stat())
        self.recovery_rejected(self.swap_env('moved.bin'))
        self.assertEqual((self.root/'readme.txt').read_bytes(),b'hello')
        self.assertEqual((self.root/'moved.bin').read_bytes(),b'new-save');self.assertEqual(len(self.records()),1)
    def test_move_recovery_boundary_source_replacement_preserved(self):
        (self.root/'moved.bin').write_bytes(b'hello');(self.root/'replacement').write_bytes(b'new-save')
        self.recovery_record(claimed=True,target_stat=(self.root/'moved.bin').stat())
        self.recovery_rejected(self.swap_env('readme.txt'))
        self.assertEqual((self.root/'readme.txt').read_bytes(),b'new-save')
        self.assertEqual((self.root/'moved.bin').read_bytes(),b'hello');self.assertEqual(len(self.records()),1)
    def test_move_recovery_absent_source_requires_directory_sync(self):
        target=self.root/'Games/moved.bin';target.write_bytes(b'hello')
        record=self.recovery_record('Games/moved.bin',claimed=True,target_stat=target.stat())
        (self.root/'readme.txt').unlink()
        self.recovery_rejected(dict(P2D_TEST_MOVE_SYNC_TARGET=str(self.root),P2D_TEST_MOVE_SYNC_NTH='0'))
        self.assertEqual(target.read_bytes(),b'hello');self.assertTrue(record.exists())
    def test_move_recovery_restores_source_metadata_before_commit(self):
        source=self.root/'readme.txt';source.chmod(0o444)
        os.utime(source,ns=(1234567890123456789,1234567891987654321));before=source.stat()
        target=self.root/'moved.bin';target.write_bytes(b'hello');target.chmod(0o600)
        self.recovery_record(claimed=True,target_stat=target.stat())
        self.restart()
        self.assertFalse(source.exists());self.assertEqual(target.read_bytes(),b'hello')
        self.assertEqual(target.stat().st_mode&0o777,before.st_mode&0o777)
        self.assertEqual(target.stat().st_mtime_ns,before.st_mtime_ns);self.assertEqual(self.records(),[])
    def test_move_open_writer_preserved(self):
        self.open('\\readme.txt',2)
        self.assertEqual(self.move(),32)
        self.assertFalse((self.root/'moved.bin').exists())
        self.assertEqual((self.root/'readme.txt').read_bytes(),b'hello')
        self.assertEqual(self.records(),[])
    def test_move_read_handle_retains_identical_bytes(self):
        self.open('\\readme.txt',0)
        self.assertEqual(self.move(),0)
        struct.pack_into('<III',self.pb,16,5,0,shared.DTA)
        self.assertEqual(self.command(7),0);self.assertEqual(self.get(shared.DTA,5),b'hello')
    def test_move_retirement_failure_preserves_committed_destination(self):
        self.assertEqual(self.move(),31)
        self.assertEqual((self.root/'moved.bin').read_bytes(),b'hello')
        self.assertFalse((self.root/'readme.txt').exists())
        self.restart();self.assertEqual((self.root/'moved.bin').read_bytes(),b'hello')
    def test_move_directory_refused_without_partial_creation(self):
        self.name('\\moved.bin',second=True)
        self.assertNotEqual(self.command(0xf,'\\Games'),0)
        self.assertTrue((self.root/'Games'/'Ärger😀.dat').exists())
        self.assertFalse((self.root/'moved.bin').exists());self.assertEqual(self.records(),[])

def load_tests(loader,tests,pattern):
    return unittest.TestSuite(MoveCompatibilityTests(n) for n in dir(MoveCompatibilityTests) if n.startswith('test_move_'))
