"""Catch wrong-image execution and guest writes escaping the experiment."""
from pathlib import Path
import importlib
import sys
import tempfile
import unittest

EXPERIMENT = Path(__file__).resolve().parents[1]
PROJECT = EXPERIMENT.parents[1]
sys.path.insert(0, str(EXPERIMENT))
try:
    probe = importlib.import_module("run_probe")
except ModuleNotFoundError:
    probe = None


class InputContractTests(unittest.TestCase):
    def require_probe(self):
        self.assertIsNotNone(probe, "run_probe input validation is not implemented")
        return probe

    def setUp(self):
        self.runs = EXPERIMENT / "results/runs"

    def test_exact_baseline_rom_is_accepted(self):
        data = self.require_probe().validate_inputs(PROJECT, self.runs)
        self.assertEqual(data["rom_sha256"], "b6ca519070e84da0bf6886fb3bde606ce098a0cfaffff436b8faf46a9a580bf7")
        self.assertEqual(data["rom_bytes"], 100663296)
        self.assertEqual(Path(data["run_root"]), self.runs.resolve())

    def test_same_named_v610_rom_is_rejected(self):
        candidate = PROJECT / "PC windows mobile 6 Files/Roms and files/pocket pc/DeviceemulationV610/0409/PPC_USA (240x320).BIN"
        with self.assertRaisesRegex(ValueError, "identity"):
            self.require_probe().validate_inputs(PROJECT, self.runs, rom_path=candidate)

    def test_truncated_rom_is_rejected(self):
        folder = EXPERIMENT / "results/test-inputs"
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder) as temporary:
            candidate = Path(temporary) / "PPC_USA.BIN"
            candidate.write_bytes(b"bad")
            with self.assertRaisesRegex(ValueError, "size"):
                self.require_probe().validate_inputs(PROJECT, self.runs, rom_path=candidate)

    def test_run_root_cannot_be_the_original_rom_directory(self):
        original = PROJECT / "PC windows mobile 6 Files/Roms and files/pocket pc/Deviceemulation/0409"
        with self.assertRaisesRegex(ValueError, "run root"):
            self.require_probe().validate_inputs(PROJECT, original)

    def test_run_root_cannot_escape_the_experiment(self):
        with self.assertRaisesRegex(ValueError, "run root"):
            self.require_probe().validate_inputs(PROJECT, PROJECT / "SOURCE")

    def test_path_traversal_cannot_escape_the_run_root(self):
        with self.assertRaisesRegex(ValueError, "run root"):
            self.require_probe().validate_inputs(PROJECT, self.runs / "../../../../SOURCE")

    def test_each_run_has_a_distinct_new_directory(self):
        engine = self.require_probe()
        first = engine.create_run_dir(self.runs)
        second = engine.create_run_dir(self.runs)
        self.assertNotEqual(first, second)
        self.assertTrue(first.is_dir())
        self.assertTrue(second.is_dir())
        self.assertTrue(first.is_relative_to(self.runs.resolve()))

    def test_directory_creation_rejects_production_source(self):
        with self.assertRaisesRegex(ValueError, "run root"):
            self.require_probe().create_run_dir(PROJECT / "SOURCE")


if __name__ == "__main__":
    unittest.main()
