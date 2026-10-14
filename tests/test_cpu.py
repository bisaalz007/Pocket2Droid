"""Run privileged ARMv4T fixtures through actual system TCG, not Unicorn."""
import hashlib
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(os.environ.get('P2D_QEMU', '/opt/pocket2droid-tcg-build/host/qemu-system-arm'))


class CPUFixtureTests(unittest.TestCase):
    def test_privileged_cpu_memory_and_flash(self):
        self.run_fixture('cpu-basic')

    def test_flash_id_mapping_invalidates_cached_header(self):
        self.run_fixture('cpu-flash-cache')

    def test_mmu_fcse_permissions_and_partial_faults(self):
        self.run_fixture('cpu-mmu')

    def test_mmu_disable_prefetched_branch(self):
        self.run_fixture('cpu-mmu-switch')

    def test_mmu_enable_prefetched_branch(self):
        self.run_fixture('cpu-mmu-enable')

    def test_clock_mode_bits_do_not_change_irq_instruction_set(self):
        self.run_fixture('cpu-irq')

    def test_fault_addresses_preserve_unaligned_va_and_fcse_mva(self):
        self.run_fixture('cpu-faults')

    def run_fixture(self, name):
        output = ROOT / 'results' / 'test-inputs'
        output.mkdir(parents=True, exist_ok=True)
        image = output / f'{name}.bin'
        source = ROOT / 'tests' / f'{name}.S'
        subprocess.run(['clang-17', '--target=armv4t-none-eabi', '-mcpu=arm920t',
                        '-nostdlib', '-fuse-ld=lld-17', '-Wl,-Ttext=0',
                        '-Wl,--oformat=binary', str(source), '-o', str(image)],
                       check=True)
        before = hashlib.sha256(image.read_bytes()).hexdigest()
        result = subprocess.run([str(BINARY), '-M', 'p2d-devemu', '-cpu', 'arm920t',
                                 '-bios', str(image), '-display', 'none',
                                 '-serial', 'none', '-monitor', 'none',
                                 '-semihosting-config', 'enable=on,target=native'],
                                timeout=15, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'PASS {name}', result.stderr)
        self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(), before)


if __name__ == '__main__':
    unittest.main()
