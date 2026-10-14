"""Disposable RAM-FMD persistence and malformed backing-file rejection."""
from pathlib import Path
import os
import errno
import socket
import subprocess
import tempfile
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from run_probe import QMP, create_run_dir

BINARY = os.environ.get('P2D_QEMU', '/opt/pocket2droid-tcg-build/host/qemu-system-arm')


class StorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # LD_PRELOAD treats spaces as separators, so keep its real library on Linux /tmp.
        cls.lock_directory = tempfile.TemporaryDirectory(prefix='p2d-storage-lock-')
        cls.lock_probe = Path(cls.lock_directory.name)
        source = cls.lock_probe / 'flock_fault.c'
        source.write_text('''#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <stdio.h>
int flock(int fd, int operation) {
    char name[64], path[4096];
    const char *target = getenv("P2D_TEST_FLOCK_PATH");
    snprintf(name, sizeof(name), "/proc/self/fd/%d", fd);
    ssize_t n = readlink(name, path, sizeof(path)-1);
    if (n >= 0) {
        path[n] = 0;
        if (target && !strcmp(path, target)) {
            errno = atoi(getenv("P2D_TEST_FLOCK_ERRNO")); return -1;
        }
    }
    return ((int (*)(int,int))dlsym(RTLD_NEXT, "flock"))(fd, operation);
}
''')
        cls.lock_library = cls.lock_probe / 'flock_fault.so'
        subprocess.run(['cc', '-shared', '-fPIC', str(source), '-ldl', '-o', str(cls.lock_library)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.lock_directory.cleanup()

    def lock_fixture(self):
        run = create_run_dir(ROOT / 'results/runs')
        storage = run / 'ram-fmd.bin'
        with storage.open('xb') as stream:
            stream.truncate(32 * 1024 * 1024)
        return storage, run / 'private-engine.lock'

    def lock_command(self, storage, guard=None):
        command = self.command(storage)
        if guard is not None:
            command[2] += f',storage-lock={guard}'
        return command

    def lock_environment(self, storage, error):
        return dict(os.environ, LD_PRELOAD=str(self.lock_library),
                    P2D_TEST_FLOCK_PATH=str(storage.resolve()), P2D_TEST_FLOCK_ERRNO=str(error))

    def test_unsupported_external_lock_without_guard_fails_closed(self):
        storage, _ = self.lock_fixture()
        result = subprocess.run(self.lock_command(storage), env=self.lock_environment(storage, errno.ENOSYS),
                                capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'cannot be locked', result.stderr)
        self.assertEqual(storage.stat().st_size, 32 * 1024 * 1024)
        self.assertEqual(storage.read_bytes(), bytes(32 * 1024 * 1024))

    def test_private_guard_protects_unsupported_storage_and_releases_on_exit(self):
        storage, guard = self.lock_fixture()
        guard_identity = None
        for error, abrupt in ((errno.ENOSYS, False), (errno.EOPNOTSUPP, True), (errno.ENOSYS, False)):
            with self.subTest(error=error, abrupt=abrupt):
                qmp_path = Path('/tmp') / f'p2d-private-lock-{uuid.uuid4().hex}.sock'
                environment = self.lock_environment(storage, error)
                process = subprocess.Popen(self.lock_command(storage, guard) +
                    ['-qmp', f'unix:{qmp_path},server=on,wait=off'], env=environment,
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                qmp = None
                try:
                    qmp = QMP(qmp_path, process)
                    self.assertIsNone(process.poll(), 'Unsupported shared-storage locking must not prevent startup')
                    identity = (guard.stat().st_dev, guard.stat().st_ino)
                    if guard_identity is None: guard_identity = identity
                    self.assertEqual(identity, guard_identity, 'Reopen must retain the same guard inode')
                    contender = subprocess.run(self.lock_command(storage, guard), env=environment,
                                               capture_output=True, timeout=5)
                    self.assertNotEqual(contender.returncode, 0, 'Two engines must never own one private guard')
                    self.assertIn(b'private storage guard', contender.stderr)
                    self.assertIsNone(process.poll())
                    if abrupt:
                        process.kill()
                    else:
                        qmp.request('quit')
                    process.wait(timeout=5)
                finally:
                    if qmp: qmp.close()
                    if process.poll() is None:
                        process.kill(); process.wait()
                    process.stderr.close()
                    qmp_path.unlink(missing_ok=True)
        self.assertTrue(guard.is_file(), 'Guard must persist rather than be unlinked/recreated')
        self.assertEqual(storage.read_bytes(), bytes(32 * 1024 * 1024))

    def test_busy_or_io_error_on_external_storage_is_not_ignored(self):
        storage, guard = self.lock_fixture()
        for error in (errno.EWOULDBLOCK, errno.EIO, errno.EPERM):
            with self.subTest(error=error):
                result = subprocess.run(self.lock_command(storage, guard), env=self.lock_environment(storage, error),
                                        capture_output=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b'cannot be locked', result.stderr)
        self.assertEqual(storage.read_bytes(), bytes(32 * 1024 * 1024))

    def test_private_guard_refuses_symlink_directory_or_storage_inode(self):
        storage, guard = self.lock_fixture()
        target = guard.with_name('unchanged.txt')
        target.write_bytes(b'preserve this file')
        guard.symlink_to(target)
        for path in (guard, target.parent, storage):
            with self.subTest(path=path):
                result = subprocess.run(self.lock_command(storage, path), capture_output=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b'private storage guard', result.stderr)
        self.assertEqual(target.read_bytes(), b'preserve this file')
        self.assertEqual(storage.read_bytes(), bytes(32 * 1024 * 1024))

    def command(self, storage):
        return [BINARY, '-M', f'p2d-devemu,storage={storage}', '-accel', 'qtest',
                '-bios', str(ROOT / 'results/test-inputs/cpu-basic.bin'),
                '-display', 'none', '-monitor', 'none', '-serial', 'none']

    def test_wrong_sized_file_rejected_without_modification(self):
        run = create_run_dir(ROOT / 'results/runs')
        storage = run / 'invalid-fmd.bin'
        storage.write_bytes(b'preserved invalid input')
        result = subprocess.run(self.command(storage), capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'exactly 32MiB', result.stderr)
        self.assertEqual(storage.read_bytes(), b'preserved invalid input')

    def test_ram_fmd_normal_close_reopen_and_interrupted_exit(self):
        run = create_run_dir(ROOT / 'results/runs')
        storage = run / 'ram-fmd.bin'
        with storage.open('xb') as stream:
            stream.truncate(32 * 1024 * 1024)
        for index, abrupt in enumerate((False, True, False)):
            qtest_path = Path('/tmp') / f'p2d-storage-{uuid.uuid4().hex}.sock'
            qmp_path = Path('/tmp') / f'p2d-storage-qmp-{uuid.uuid4().hex}.sock'
            command = self.command(storage) + [
                '-qtest', f'unix:{qtest_path},server=on,wait=off', '-qtest-log', '/dev/null',
                '-qmp', f'unix:{qmp_path},server=on,wait=off']
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            qmp = sock = stream = None
            try:
                qmp = QMP(qmp_path, process)
                sock = socket.socket(socket.AF_UNIX)
                sock.settimeout(3)
                sock.connect(str(qtest_path))
                stream = sock.makefile('rwb')
                def request(text):
                    stream.write((text + '\n').encode())
                    stream.flush()
                    response = stream.readline().decode().strip()
                    self.assertTrue(response.startswith('OK'), response)
                    return response.split()[1:]
                if index:
                    self.assertEqual(int(request('readl 0x34000020')[0], 0), 0x12340000 + index - 1)
                request(f'writel 0x34000020 0x{0x12340000 + index:x}')
                if abrupt:
                    process.kill()
                else:
                    qmp.request('quit')
                process.wait(timeout=5)
            finally:
                if stream:
                    stream.close()
                if sock:
                    sock.close()
                if qmp:
                    qmp.close()
                if process.poll() is None:
                    process.kill()
                    process.wait()
                process.stderr.close()
                qtest_path.unlink(missing_ok=True)
                qmp_path.unlink(missing_ok=True)
        with storage.open('rb') as stream:
            stream.seek(0x20)
            self.assertEqual(stream.read(4), (0x12340002).to_bytes(4, 'little'))
