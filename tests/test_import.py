"""Actual device protocol checks, not filesystem mocks."""
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_devices

BASE = 0x500f4000
PB = 0x30008000

class ImportTests(test_devices.DeviceTests):
    # Inherit only the QTest transport, not its device tests.
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='p2d-import-')
        self.addCleanup(self.temp.cleanup)
        self.cab = Path(self.temp.name) / 'input.cab'
        self.content = b'MSCF' + bytes(4) + struct.pack('<I', 8192) + bytes(range(256)) * 31 + bytes(244)
        self.assertEqual(len(self.content), 8192)
        self.cab.write_bytes(self.content)
        original = test_devices.subprocess.Popen
        def launch(args, **kwargs):
            args = list(args)
            args[args.index('-M') + 1] += ',import-file=' + str(self.cab)
            return original(args, **kwargs)
        with patch('test_devices.subprocess.Popen', side_effect=launch):
            super().setUp()
        self.pb = bytearray(1068)
        struct.pack_into('<H', self.pb, 0, 1068)

    def put(self, addr, raw):
        self.request('write 0x%x %d 0x%s' % (addr, len(raw), raw.hex()))

    def get(self, addr, size):
        return bytes.fromhex(self.request('read 0x%x %d' % (addr, size))[0].removeprefix('0x'))

    def command(self, code, path=None):
        if path is not None:
            raw = path.encode('utf-16le')
            self.pb[36:548] = bytes(512)
            struct.pack_into('<H', self.pb, 34, len(raw))
            self.pb[36:36+len(raw)] = raw
        self.put(PB, self.pb)
        self.write(BASE, PB)
        self.write(BASE + 4, code)
        self.assertEqual(self.read(BASE + 8), 0)
        self.pb[:] = self.get(PB, len(self.pb))
        return self.read(BASE + 12)

    def open_cab(self):
        self.assertEqual(self.command(6, '\\RagingThunder.cab'), 0)
        return struct.unpack_from('<H', self.pb, 10)[0]

    def test_import_mount_open_read_cross_page_and_eof(self):
        self.assertEqual(self.command(4), 0)
        self.assertEqual(self.command(0x15), 65536)
        handle = self.open_cab()
        struct.pack_into('<H', self.pb, 10, handle)
        struct.pack_into('<III', self.pb, 16, 2000, 100, 0x30010ff0)
        self.assertEqual(self.command(7), 0)
        self.assertEqual(self.get(0x30010ff0, 2000), self.content[100:2100])
        struct.pack_into('<III', self.pb, 16, 100, len(self.content)-5, 0x30018000)
        self.assertEqual(self.command(7), 0)
        self.assertEqual(struct.unpack_from('<I', self.pb, 16)[0], 5)
        self.assertEqual(self.get(0x30018000, 5), self.content[-5:])
        self.assertEqual(self.command(0xa), 0)
        self.assertEqual(self.command(7), 6)
        self.assertEqual(self.cab.read_bytes(), self.content)

    def test_import_rejects_paths_mutations_and_unsafe_guest_buffers(self):
        for name in ('\\..\\input.cab', '\\sub\\RagingThunder.cab', '\\unknown.cab'):
            self.assertNotEqual(self.command(6, name), 0)
        for code in (5, 8, 9, 0xc, 0xd, 0xe, 0xf, 0x10):
            self.assertEqual(self.command(code, '\\RagingThunder.cab'), 19)
        self.open_cab()
        struct.pack_into('<III', self.pb, 16, 32, 0, 0x4a000000)
        self.assertEqual(self.command(7), 30)
        struct.pack_into('<III', self.pb, 16, 32, 0, 0xfffffff0)
        self.assertEqual(self.command(7), 30)
        self.assertEqual(self.read(0x4a000008), 0xffffffff)
        self.assertEqual(self.cab.read_bytes(), self.content)

    def test_import_enumeration_and_metadata(self):
        struct.pack_into('<Ih', self.pb, 4, 0xffffffff, -1)
        self.assertEqual(self.command(0x11, '\\'), 0)
        self.assertEqual(struct.unpack_from('<H', self.pb, 28)[0] & 16, 16)
        struct.pack_into('<Ih', self.pb, 4, 3, 0)
        self.pb[32] = 1
        self.assertEqual(self.command(0x11, '\\*.*'), 0)
        self.assertEqual(struct.unpack_from('<I', self.pb, 16)[0], len(self.content))
        length = struct.unpack_from('<H', self.pb, 34)[0]
        self.assertEqual(self.pb[36:36+length].decode('utf-16le'), 'RagingThunder.cab')
        struct.pack_into('<Ih', self.pb, 4, 3, 1)
        self.assertEqual(self.command(0x11), 18)
        struct.pack_into('<Ih', self.pb, 4, 39, 1)
        self.assertEqual(self.command(0x11), 31)

    def test_import_parameter_block_malformed_and_rom_target_rejected(self):
        struct.pack_into('<H', self.pb, 0, 1067)
        self.assertEqual(self.command(6, '\\RagingThunder.cab'), 1)
        struct.pack_into('<H', self.pb, 0, 1068)
        self.open_cab()
        struct.pack_into('<III', self.pb, 16, 8, 0, 0)
        before = self.get(0, 8)
        self.assertEqual(self.command(7), 30)
        self.assertEqual(self.get(0, 8), before)

    def test_import_handle_commands_ignore_unused_name_fields(self):
        self.open_cab()
        struct.pack_into('<H', self.pb, 34, 513)
        struct.pack_into('<III', self.pb, 16, 8, 64, 0x30018000)
        self.assertEqual(self.command(7), 0)
        self.assertEqual(self.get(0x30018000, 8), self.content[64:72])
        self.assertEqual(self.command(0xb), 0)
        self.assertEqual(self.command(0x13), 0)
        struct.pack_into('<H', self.pb, 34, 513)
        self.assertEqual(self.command(0xa), 0)

def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for name in ImportTests.__dict__:
        if name.startswith('test_import_'):
            suite.addTest(ImportTests(name))
    return suite

if __name__ == '__main__':
    unittest.main()
