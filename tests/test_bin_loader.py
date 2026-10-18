"""Device Emulator B000FF loading, reset and fail-closed input checks."""
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import unittest

from run_probe import QMP

BINARY = os.environ.get('P2D_QEMU', '/opt/pocket2droid-tcg-build/host/qemu-system-arm')
BASE = 0x80070000
CODE = bytes.fromhex('feffffea')


def image(records=None, entry=BASE + 0x20, base=BASE, size=0x100):
    if records is None:
        records = [(BASE, bytes.fromhex('78563412')),
                   (BASE + 0x20, CODE)]
    out = b'B000FF\n' + struct.pack('<II', base, size)
    for address, data in records:
        out += struct.pack('<III', address, len(data), sum(data) & 0xffffffff) + data
    return out + struct.pack('<III', 0, entry, 0)


class BinLoaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='p2d-bin-loader-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def start(self, data, storage=False, retained=False):
        rom = self.root / 'test.bin'
        rom.write_bytes(data)
        machine = 'p2d-devemu,screen-width=480,screen-height=640'
        if storage:
            with (self.root / 'storage.bin').open('wb') as f:
                f.truncate(32 * 1024 * 1024)
                f.write(b'SAVE')
            machine += f',storage={self.root}/storage.bin'
        if retained:
            ram = self.root / 'retained.bin'
            with ram.open('wb') as f:
                f.truncate(128 * 1024 * 1024)
                f.write(b'KEPT')
            stat = ram.stat()
            machine += f',ram-path={ram},ram-identity={stat.st_dev:x}:{stat.st_ino:x}'
        p = subprocess.Popen([BINARY, '-M', machine, '-accel', 'qtest', '-bios', str(rom),
            '-display', 'none', '-serial', 'none', '-monitor', 'none',
            '-qtest', f'unix:{self.root}/qt,server=on,wait=off', '-qtest-log', '/dev/null',
            '-qmp', f'unix:{self.root}/qmp,server=on,wait=off'],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.addCleanup(self.close_process, p)
        qmp = QMP(self.root / 'qmp', p)
        self.addCleanup(qmp.close)
        sock = socket.socket(socket.AF_UNIX)
        sock.connect(str(self.root / 'qt'))
        self.addCleanup(sock.close)
        stream = sock.makefile('rwb')
        self.addCleanup(stream.close)

        def request(command):
            stream.write((command + '\n').encode())
            stream.flush()
            result = stream.readline().decode().split()
            self.assertEqual(result[0], 'OK', result)
            return result[1:]
        return qmp, request

    @staticmethod
    def close_process(p):
        if p.poll() is None:
            p.terminate()
        p.wait(timeout=5)
        p.stderr.close()

    def test_records_and_entry_load_into_ram(self):
        qmp, request = self.start(image())
        self.assertEqual(int(request('readl 0x30070000')[0], 0), 0x12345678)
        self.assertEqual(int(request('readl 0x30070020')[0], 0), 0xeafffffe)
        self.assertEqual(int(request('readl 0x30070010')[0], 0), 0)
        regs = qmp.request('human-monitor-command', {'command-line': 'info registers'})
        self.assertIn('R15=30070020', regs)

    def test_reset_reloads_records_preserves_storage_and_boot_arguments(self):
        qmp, request = self.start(image(), storage=True)
        request('writel 0x30070000 0xdeadbeef')
        request('writel 0x34000000 0x87654321')
        qmp.request('system_reset')
        self.assertEqual(int(request('readl 0x30070000')[0], 0), 0x12345678)
        self.assertEqual(int(request('readl 0x34000000')[0], 0), 0x87654321)
        self.assertEqual(int(request('readl 0x30020044')[0], 0), 0xde12de34)
        self.assertEqual(int(request('readw 0x30020048')[0], 0), 480)
        self.assertEqual(int(request('readw 0x3002004a')[0], 0), 640)
        regs = qmp.request('human-monitor-command', {'command-line': 'info registers'})
        self.assertIn('R15=30070020', regs)

    def test_raw_images_keep_existing_load_address_and_reset(self):
        qmp, request = self.start(CODE)
        self.assertEqual(int(request('readl 0')[0], 0), 0xeafffffe)
        qmp.request('system_reset')
        self.assertEqual(int(request('readl 0')[0], 0), 0xeafffffe)
        regs = qmp.request('human-monitor-command', {'command-line': 'info registers'})
        self.assertIn('R15=00000000', regs)

    def test_unsorted_records_load_and_reset(self):
        records = [(BASE + 0x20, CODE), (BASE, bytes.fromhex('78563412'))]
        qmp, request = self.start(image(records=records))
        for repeat in range(2):
            self.assertEqual(int(request('readl 0x30070000')[0], 0), 0x12345678)
            self.assertEqual(int(request('readl 0x30070020')[0], 0), 0xeafffffe)
            request('writel 0x30070020 0')
            qmp.request('system_reset')

    def test_upper_sdram_boundary_does_not_touch_storage(self):
        last = 0x83fffffc
        qmp, request = self.start(image(records=[(last, CODE)], entry=last,
                                       base=last, size=4), storage=True)
        self.assertEqual(int(request('readl 0x33fffffc')[0], 0), 0xeafffffe)
        self.assertEqual(int(request('readl 0x34000000')[0], 0), 0x45564153)
        regs = qmp.request('human-monitor-command', {'command-line': 'info registers'})
        self.assertIn('R15=33fffffc', regs)

    def test_record_limit_boundary_is_accepted(self):
        records = [(BASE + i * 4, CODE) for i in range(4096)]
        qmp, request = self.start(image(records=records, entry=BASE, size=4096 * 4))
        self.assertEqual(int(request(f'readl {0x30070000 + 4095 * 4:#x}')[0], 0), 0xeafffffe)

    def test_retained_ram_is_existing_identity_checked_and_separate_from_fmd(self):
        qmp, request = self.start(image(), storage=True, retained=True)
        self.assertEqual(int(request('readl 0x30000000')[0], 0), 0x5450454b)
        self.assertEqual(int(request('readl 0x34000000')[0], 0), 0x45564153)
        request('writel 0x31001234 0x11223344')
        qmp.request('system_reset')
        self.assertEqual(int(request('readl 0x31001234')[0], 0), 0x11223344)
        self.assertEqual(int(request('readl 0x30070000')[0], 0), 0x12345678)
        qmp.request('quit')
        with (self.root / 'retained.bin').open('rb') as f:
            f.seek(0x1001234)
            self.assertEqual(f.read(4), bytes.fromhex('44332211'))

    def test_retained_ram_missing_replaced_symlink_or_wrong_size_is_not_mapped(self):
        rom = self.root / 'image.bin'
        rom.write_bytes(image())
        storage = self.root / 'save.bin'
        with storage.open('wb') as f:
            f.truncate(32 * 1024 * 1024)
            f.write(b'SAVE')
        ram = self.root / 'ram.bin'
        with ram.open('wb') as f:
            f.truncate(128 * 1024 * 1024)
            f.write(b'KEPT')
        st = ram.stat()
        expected = f'{st.st_dev:x}:{st.st_ino:x}'
        link = self.root / 'link.bin'
        link.symlink_to(ram)
        short = self.root / 'short.bin'
        short.write_bytes(b'KEPT')
        ss = short.stat()
        for name, path, identity in [('missing', self.root/'missing.bin', expected),
                ('replaced', ram, '0:0'), ('symlink', link, expected),
                ('size', short, f'{ss.st_dev:x}:{ss.st_ino:x}'),
                ('identity-missing', ram, ''), ('identity-invalid', ram, 'x:0')]:
            with self.subTest(name=name):
                result = subprocess.run([BINARY, '-M', f'p2d-devemu,storage={storage},ram-path={path},ram-identity={identity}',
                    '-bios', str(rom), '-S', '-display', 'none', '-serial', 'none', '-monitor', 'none'],
                    capture_output=True, timeout=3)
                self.assertEqual(result.returncode, 1)
                self.assertIn('Invalid WM5 retained RAM', result.stderr.decode())
                self.assertFalse((self.root/'missing.bin').exists())
                with ram.open('rb') as f:
                    self.assertEqual(f.read(4), b'KEPT')

    def test_malformed_record_images_are_rejected_before_execution(self):
        good = image()
        cases = {
            'short-header': b'B000FF\n\0',
            'missing-terminator': good[:-12],
            'truncated-data': good[:28],
            'bad-checksum': good[:23] + struct.pack('<I', 0) + good[27:],
            'no-records': image(records=[]),
            'outside-ram': image(records=[(0x84000000, CODE)], entry=0x84000000),
            'outside-image': image(records=[(BASE + 0x100, CODE)], entry=BASE + 0x100),
            'overlapping': image(records=[(BASE, CODE), (BASE, CODE)], entry=BASE),
            'entry-in-gap': image(entry=BASE + 0x10),
            'unaligned-entry': image(entry=BASE + 0x21),
            'wrapped-image': image(base=0xfffffff0, size=0x100),
            'trailing-bytes': good + b'x',
            'nonzero-terminator-checksum': good[:-4] + struct.pack('<I', 1),
            'reserved-boot-arguments': image(records=[(0x80020044, CODE)],
                entry=0x80020044, base=0x80020044, size=4),
            'excessive-record-count': image(records=[(BASE + i * 4, CODE)
                for i in range(4097)], entry=BASE, size=4097 * 4),
        }
        for name, data in cases.items():
            with self.subTest(name=name):
                rom = self.root / f'{name}.bin'
                rom.write_bytes(data)
                try:
                    p = subprocess.run([BINARY, '-M', 'p2d-devemu', '-bios', str(rom),
                        '-S', '-display', 'none', '-serial', 'none', '-monitor', 'none'],
                        capture_output=True, timeout=2)
                except subprocess.TimeoutExpired:
                    self.fail(f'{name}: malformed image was accepted')
                self.assertNotEqual(p.returncode, 0)
                self.assertIn('Invalid Device Emulator B000FF', p.stderr.decode())


if __name__ == '__main__':
    unittest.main(verbosity=2)
