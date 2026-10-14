import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('probe', ROOT / 'run_probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class BootRunnerGuards(unittest.TestCase):
    def test_cold_storage_is_isolated_and_cannot_overwrite(self):
        run = probe.create_run_dir(ROOT / 'results/runs')
        storage = probe.create_ram_fmd(run)
        self.assertEqual(storage.parent, run)
        self.assertEqual(storage.stat().st_size, 32 * 1024 * 1024)
        with storage.open('r+b') as stream:
            stream.write(b'preserve')
        with self.assertRaises(FileExistsError):
            probe.create_ram_fmd(run)
        with storage.open('rb') as stream:
            self.assertEqual(stream.read(8), b'preserve')

    def test_refuses_production_run_directory_before_launch(self):
        with self.assertRaisesRegex(ValueError, 'isolated'):
            probe.run_boot(probe.PROJECT / 'SOURCE', 1)

    def test_refuses_unbounded_or_negative_capture(self):
        for value in (0, -1, 601):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'timeout'):
                probe.run_boot(ROOT / 'results/runs/guard', value)


if __name__ == '__main__':
    unittest.main()
