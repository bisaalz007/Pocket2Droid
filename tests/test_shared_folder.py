"""Read/write VCEFS ServerPB tests through the actual QEMU MMIO endpoint."""
import struct
import tempfile
import subprocess
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import test_devices

BASE = 0x500f4000
PB = 0x30008000
DTA = 0x30010ff0


class SharedFolderTests(test_devices.DeviceTests):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='p2d-shared-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'card'
        self.root.mkdir()
        (self.root / 'Games').mkdir()
        (self.root / 'Games' / 'Ärger😀.dat').write_bytes(b'original-data')
        (self.root / 'readme.txt').write_bytes(b'hello')
        self.outside = Path(self.temp.name) / 'outside'
        self.outside.mkdir()
        (self.outside / 'secret').write_bytes(b'untouched')
        (self.root / 'escape').symlink_to(self.outside, target_is_directory=True)
        (self.root / 'link').symlink_to(self.outside / 'secret')
        original = test_devices.subprocess.Popen
        def launch(args, **kwargs):
            args = list(args)
            args[args.index('-M') + 1] += ',shared-folder=' + str(self.root)
            return original(args, **kwargs)
        with patch('test_devices.subprocess.Popen', side_effect=launch):
            super().setUp()
        self.pb = bytearray(1068)
        struct.pack_into('<H', self.pb, 0, 1068)

    def put(self, addr, raw):
        self.request('write 0x%x %d 0x%s' % (addr, len(raw), raw.hex()))

    def get(self, addr, size):
        return bytes.fromhex(self.request('read 0x%x %d' % (addr, size))[0].removeprefix('0x'))

    def name(self, path, second=False):
        raw = path.encode('utf-16le')
        off, length = (550, 548) if second else (36, 34)
        self.assertLessEqual(len(raw), 512)
        self.pb[off:off+512] = bytes(512)
        struct.pack_into('<H', self.pb, length, len(raw))
        self.pb[off:off+len(raw)] = raw

    def command(self, code, path=None):
        if path is not None:
            self.name(path)
        self.put(PB, self.pb)
        self.write(BASE, PB)
        self.write(BASE + 4, code)
        self.assertEqual(self.read(BASE + 8), 0)
        self.pb[:] = self.get(PB, len(self.pb))
        return self.read(BASE + 12)

    def open(self, path, mode=0):
        struct.pack_into('<H', self.pb, 30, mode)
        self.assertEqual(self.command(6, path), 0)
        return struct.unpack_from('<H', self.pb, 10)[0]

    def info(self, path, txn=0xffffffff, index=-1):
        struct.pack_into('<Ih', self.pb, 4, txn, index)
        self.pb[32] = 1
        return self.command(0x11, path)

    def returned_name(self):
        length = struct.unpack_from('<H', self.pb, 34)[0]
        return self.pb[36:36+length].decode('utf-16le')

    def test_shared_mount_event_and_nested_unicode_case_lookup(self):
        self.assertEqual(self.read(0x500f5004), 1 << 30)
        self.assertEqual(self.command(4), 0)
        self.assertEqual(self.command(0x15), 65536)
        self.assertEqual(self.info('\\games'), 0)
        self.assertEqual(struct.unpack_from('<H', self.pb, 28)[0] & 16, 16)
        self.open('\\GAMES\\ärger😀.DAT')
        struct.pack_into('<III', self.pb, 16, 4096, 0, DTA)
        self.assertEqual(self.command(7), 0)
        self.assertEqual(struct.unpack_from('<I', self.pb, 16)[0], 13)
        self.assertEqual(self.get(DTA, 13), b'original-data')

    def test_shared_nonempty_navigation_and_search_exhaustion(self):
        self.assertEqual(self.info('\\games\\*.*', 3, 0), 0)
        self.assertEqual(self.returned_name(), 'Ärger😀.dat')
        self.assertEqual(self.info('unused', 3, 1), 18)
        self.assertEqual(self.info('unused', 3, 2), 31)
        self.assertEqual(self.info('\\missing\\*.*', 4, 0), 3)
        self.assertEqual(self.info('\\Games\\*.cab', 4, 0), 2)
        self.assertEqual(self.info('\\', 0, -1), 1)
        self.assertEqual(self.info('\\', 40, 0), 31)
        self.assertEqual(self.info('\\', 0xffffffff, -2), 31)
        self.assertEqual(self.info('\\', 0xffffffff, -1), 0)

    def test_shared_create_write_read_seteof_rename_delete_and_directories(self):
        self.assertEqual(self.command(0xc, '\\New'), 0)
        self.assertEqual(self.command(5, '\\new\\Save.bin'), 0)
        self.assertEqual(self.command(5, '\\NEW\\save.BIN'), 80)
        self.open('\\new\\SAVE.bin', 2)
        data = bytes(range(256)) * 9
        self.put(DTA, data)
        struct.pack_into('<III', self.pb, 16, len(data), 0, DTA)
        self.assertEqual(self.command(8), 0)
        self.assertEqual((self.root / 'New' / 'Save.bin').read_bytes(), data)
        struct.pack_into('<I', self.pb, 20, 7)
        self.assertEqual(self.command(9), 0)
        self.assertEqual(self.command(0x13), 0)
        self.assertEqual(struct.unpack_from('<I', self.pb, 16)[0], 7)
        self.assertEqual(struct.unpack_from('<I', self.pb, 20)[0], len(data))
        self.assertEqual(struct.unpack_from('<H', self.pb, 30)[0], 2)
        self.assertEqual(self.command(0xa), 0)
        self.name('\\New\\Moved.bin', second=True)
        self.assertEqual(self.command(0xf, '\\new\\save.bin'), 0)
        self.assertEqual((self.root / 'New' / 'Moved.bin').read_bytes(), data[:7])
        self.assertNotEqual(self.command(0xd, '\\New'), 0)
        self.assertEqual(self.command(0x10, '\\NEW\\moved.BIN'), 0)
        self.assertEqual(self.command(0xd, '\\new'), 0)
        self.assertFalse((self.root / 'New').exists())

    def test_shared_invalid_buffers_do_not_mutate_host_or_mmio(self):
        self.open('\\readme.txt', 2)
        for address in (0x4a000000, 0xfffffff0, 0x37fffff0, 0):
            struct.pack_into('<III', self.pb, 16, 32, 0, address)
            self.assertEqual(self.command(8), 29)
            self.assertEqual((self.root / 'readme.txt').read_bytes(), b'hello')
            self.assertEqual(self.command(7), 30)
        self.assertEqual(self.read(0x4a000008), 0xffffffff)
        struct.pack_into('<H', self.pb, 0, 1067)
        self.assertEqual(self.command(5, '\\bad'), 1)
        self.assertFalse((self.root / 'bad').exists())

    def test_shared_path_traversal_symlink_and_normalization(self):
        for path in ('\\..\\outside\\secret', '\\Games\\..\\..\\outside\\secret',
                     '\\escape\\secret', '\\link'):
            self.assertNotEqual(self.command(6, path), 0)
            self.assertNotEqual(self.command(5, path), 0)
            self.assertNotEqual(self.info(path), 0)
        self.assertNotEqual(self.command(0x10, '\\link'), 0)
        self.assertTrue((self.root / 'link').is_symlink())
        self.assertEqual((self.outside / 'secret').read_bytes(), b'untouched')
        self.open('\\Games\\.\\..\\README.TXT')

    def test_shared_eof_cap_and_handle_permissions(self):
        self.open('\\readme.txt')
        self.put(DTA, b'x')
        struct.pack_into('<III', self.pb, 16, 1, 0, DTA)
        self.assertEqual(self.command(8), 5)
        self.assertEqual(self.command(9), 5)
        struct.pack_into('<III', self.pb, 16, 9, 100, DTA)
        self.assertEqual(self.command(7), 0)
        self.assertEqual(struct.unpack_from('<I', self.pb, 16)[0], 0)
        self.assertEqual(self.command(0xa), 0)
        self.assertEqual(self.command(7), 6)
        self.open('\\readme.txt', 1)
        self.assertEqual(self.command(7), 5)
        self.assertEqual(self.command(0xa), 0)
        self.assertEqual(self.command(5, '\\large.bin'), 0)
        self.open('\\large.bin', 2)
        self.put(DTA, b'x' * 65536)
        struct.pack_into('<III', self.pb, 16, 70000, 0, DTA)
        self.assertEqual(self.command(8), 0)
        self.assertEqual(struct.unpack_from('<I', self.pb, 16)[0], 65536)
        self.assertEqual((self.root / 'large.bin').stat().st_size, 65536)

    def test_shared_handle_exhaustion_reset_and_space(self):
        for _ in range(40):
            self.open('\\readme.txt')
        self.assertEqual(self.command(6, '\\readme.txt'), 4)
        self.assertEqual(self.info('\\Games\\*', 2, 0), 0)
        self.qmp.request('system_reset')
        self.assertEqual(self.command(7), 6)
        self.assertEqual(self.info('unused', 2, 1), 31)
        self.open('\\readme.txt')
        self.assertEqual(self.command(0xb), 0)
        free, total = struct.unpack_from('<II', self.pb, 16)
        self.assertGreater(total, 0)
        self.assertLessEqual(free, total)

    def test_shared_unicode_invalid_names_and_metadata(self):
        for raw in (b'\x00\xd8', b'A\x00\x00\x00B\x00'):
            struct.pack_into('<H', self.pb, 34, len(raw))
            self.pb[36:36+len(raw)] = raw
            self.assertEqual(self.command(5), 123)
        self.assertEqual(self.info('\\readme.txt'), 0)
        self.assertEqual(struct.unpack_from('<H', self.pb, 28)[0] & 32, 32)
        # 2026-10-08 12:34:56 in DOS timestamp format.
        timestamp = ((46 << 9 | 10 << 5 | 8) << 16) | (12 << 11 | 34 << 5 | 28)
        struct.pack_into('<IH', self.pb, 12, timestamp, 0)
        struct.pack_into('<H', self.pb, 28, 1)
        self.assertEqual(self.command(0xe, '\\readme.txt'), 0)
        self.assertEqual(self.info('\\readme.txt'), 0)
        self.assertEqual(struct.unpack_from('<H', self.pb, 28)[0] & 1, 1)
        self.assertEqual(struct.unpack_from('<I', self.pb, 12)[0], timestamp)
        self.assertEqual(self.command(6, '\\readme.txt'), 0)
        struct.pack_into('<H', self.pb, 28, 0)
        self.assertEqual(self.command(0xe, '\\readme.txt'), 0)

    def test_shared_independent_root_searches_and_unused_handle_names(self):
        self.assertEqual(self.info('\\*.*', 1, 0), 0)
        first = self.returned_name()
        self.assertEqual(self.info('\\*.*', 2, 0), 0)
        self.assertEqual(self.returned_name(), first)
        self.assertEqual(self.info('unused', 1, 1), 0)
        second = self.returned_name()
        self.assertEqual(self.info('unused', 2, 1), 0)
        self.assertEqual(self.returned_name(), second)
        self.assertEqual({first, second}, {'Games', 'readme.txt'})
        self.assertEqual(self.info('unused', 1, 2), 18)
        self.assertEqual(self.info('unused', 2, 2), 18)
        self.open('\\readme.txt')
        struct.pack_into('<H', self.pb, 34, 513)
        struct.pack_into('<III', self.pb, 16, 1, 0, DTA)
        self.assertEqual(self.command(7), 0)
        self.assertEqual(self.command(0xb), 0)
        self.assertEqual(self.command(0x13), 0)
        struct.pack_into('<H', self.pb, 34, 513)
        self.assertEqual(self.command(0xa), 0)

    def test_shared_fcb_position_saturates_at_32bit_limit(self):
        self.open('\\readme.txt', 2)
        self.put(DTA, b'ab')
        struct.pack_into('<III', self.pb, 16, 2, 0xffffffff, DTA)
        self.assertEqual(self.command(8), 0)
        self.assertEqual(self.command(0x13), 0)
        self.assertEqual(struct.unpack_from('<I', self.pb, 20)[0], 0xffffffff)
        self.assertEqual(struct.unpack_from('<I', self.pb, 16)[0], 0xffffffff)

    def test_shared_invalid_attribute_timestamp_preserves_host_mode(self):
        before = (self.root / 'readme.txt').stat().st_mode
        struct.pack_into('<I', self.pb, 12, 0xffffffff)
        struct.pack_into('<H', self.pb, 28, 1)
        self.assertEqual(self.command(0xe, '\\readme.txt'), 123)
        self.assertEqual((self.root / 'readme.txt').stat().st_mode, before)

    def test_shared_rename_collision_preserves_files_and_moves_nonempty_directory(self):
        (self.root / 'Save.dat').write_bytes(b'source-save')
        (self.root / 'Existing.dat').write_bytes(b'destination-save')
        self.name('\\EXISTING.DAT', second=True)
        self.assertEqual(self.command(0xf, '\\save.dat'), 80)
        self.assertEqual((self.root / 'Save.dat').read_bytes(), b'source-save')
        self.assertEqual((self.root / 'Existing.dat').read_bytes(), b'destination-save')
        self.name('\\Existing.dat', second=True)
        self.assertEqual(self.command(0xf, '\\Save.dat'), 80)
        self.name('\\Renamed', second=True)
        self.assertEqual(self.command(0xf, '\\Games'), 0)
        self.assertEqual((self.root / 'Renamed' / 'Ärger😀.dat').read_bytes(), b'original-data')
        self.assertFalse((self.root / 'Games').exists())

    def test_shared_findfirst_trailing_separator_lists_directory_children(self):
        self.assertEqual(self.info('\\Games\\', 2, 0), 0)
        self.assertEqual(self.returned_name(), 'Ärger😀.dat')
        self.assertEqual(self.info('unused', 2, 1), 18)

    def test_shared_intermediate_symlink_replacement_race_is_contained(self):
        volatile = self.root / 'volatile'
        holder = self.root / 'holder'
        volatile.mkdir()
        stop = threading.Event()
        errors = []
        swaps = []
        def replace_directory():
            try:
                while not stop.is_set():
                    volatile.rename(holder)
                    volatile.symlink_to(self.outside, target_is_directory=True)
                    volatile.unlink()
                    holder.rename(volatile)
                    swaps.append(1)
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=replace_directory)
        thread.start()
        try:
            for i in range(80):
                self.assertIn(self.command(5, '\\volatile\\new%d' % i), (0, 3, 5))
        finally:
            stop.set()
            thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors, errors)
        self.assertGreater(len(swaps), 0)
        self.assertEqual(sorted(p.name for p in self.outside.iterdir()), ['secret'])
        self.assertEqual((self.outside / 'secret').read_bytes(), b'untouched')


class SharedFolderConfigurationTests(unittest.TestCase):
    def test_rejects_conflicting_modes_non_directory_and_root_symlink(self):
        with tempfile.TemporaryDirectory(prefix='p2d-shared-config-') as directory:
            root = Path(directory)
            bios = root / 'idle.bin'
            bios.write_bytes(bytes.fromhex('feffffea'))
            link = root / 'link'
            link.symlink_to(root, target_is_directory=True)
            for option, expected in (
                (',shared-folder=' + str(bios), 'Cannot open shared-folder directory'),
                (',shared-folder=' + str(link), 'Cannot open shared-folder directory'),
                (',shared-folder=' + str(root) + ',import-file=' + str(bios),
                 'mutually exclusive'),
            ):
                result = subprocess.run([test_devices.BINARY, '-M', 'p2d-devemu' + option,
                                         '-bios', str(bios), '-display', 'none', '-serial', 'none'],
                                        capture_output=True, text=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)

    def test_shared_mmu_ram_dma_preserves_spans_and_invalidates_native_code(self):
        # Existing actual-CPU fixture executes overwritten ARM code and performs
        # a DMA read whose first chunk rewrites a descriptor for a later chunk.
        # Reuse its independent literals with the new host-directory backend.
        with tempfile.TemporaryDirectory(prefix='p2d-shared-cpu-') as directory:
            root = Path(directory)
            data = bytearray(8192)
            struct.pack_into('<II', data, 64, 0xe3a00002, 0xe12fff1e)
            struct.pack_into('<I', data, 128, 0x50000c12)
            struct.pack_into('<I', data, 128 + 1028, 0x12345678)
            (root / 'RagingThunder.cab').write_bytes(data)
            fixture = root / 'cpu-shared.bin'
            subprocess.run(['clang-17', '--target=armv4t-none-eabi', '-mcpu=arm920t',
                            '-nostdlib', '-fuse-ld=lld-17', '-Wl,-Ttext=0',
                            '-Wl,--oformat=binary',
                            str(test_devices.ROOT / 'tests/cpu-import.S'), '-o', str(fixture)],
                           check=True)
            result = subprocess.run([test_devices.BINARY, '-M', 'p2d-devemu,shared-folder=' + str(root),
                                     '-bios', str(fixture), '-display', 'none', '-serial', 'none',
                                     '-monitor', 'none', '-semihosting-config', 'enable=on,target=native'],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('PASS cpu-import-mmu-native-invalidation', result.stderr)
            self.assertEqual((root / 'RagingThunder.cab').read_bytes(), data)


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite(SharedFolderTests(name) for name in SharedFolderTests.__dict__
                               if name.startswith('test_shared_'))
    suite.addTests(loader.loadTestsFromTestCase(SharedFolderConfigurationTests))
    return suite


if __name__ == '__main__':
    unittest.main()
