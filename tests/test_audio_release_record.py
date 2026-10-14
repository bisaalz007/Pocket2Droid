"""A sound release cannot claim passed checks from stale or incomplete evidence."""
import importlib.util, unittest
from pathlib import Path
class SoundReleaseTests(unittest.TestCase):
    def test_current_complete_record_required(self):
        path=Path(__file__).resolve().parents[1]/'android/tests/audio_release_checks.py'
        self.assertTrue(path.exists(),'Missing current sound release evidence validator')
        spec=importlib.util.spec_from_file_location('soundcheck',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        expected={'version':'6.60','apk_sha256':'a'*64,'native_sha256':'b'*64,'source_hashes':{'Engine.java':'c'*64}}
        record=dict(expected,checks={k:True for k in m.REQUIRED})
        m.validate_record(record,expected)
        for key in ['version','apk_sha256','native_sha256','source_hashes']:
            bad=dict(record);bad[key]='stale'
            with self.assertRaises(ValueError):m.validate_record(bad,expected)
        for key in m.REQUIRED:
            bad=dict(record,checks=dict(record['checks']));bad['checks'][key]=False
            with self.assertRaises(ValueError):m.validate_record(bad,expected)
if __name__=='__main__':unittest.main()
