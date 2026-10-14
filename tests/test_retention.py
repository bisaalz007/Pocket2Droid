"""Refuse importing arbitrary snapshots or overwriting writable run files."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import interactive_probe as probe
from run_probe import PROJECT, create_run_dir


class RetentionGuards(unittest.TestCase):
    def test_reopen_refuses_production_source_before_copy(self):
        target = create_run_dir(ROOT / 'results/runs')
        with self.assertRaisesRegex(ValueError, 'run root'):
            probe.copy_retained_memory(PROJECT / 'SOURCE', target)
        self.assertEqual(list(target.iterdir()), [])

    def test_reopen_refuses_missing_prototype_manifest(self):
        source = create_run_dir(ROOT / 'results/runs')
        target = create_run_dir(ROOT / 'results/runs')
        with self.assertRaises(FileNotFoundError):
            probe.copy_retained_memory(source, target)
        self.assertEqual(list(target.iterdir()), [])
