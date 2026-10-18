"""Clean-cache reproducibility: only the verified archive is preseeded."""
from pathlib import Path
import importlib.util, json, shutil, subprocess, sys, tempfile, unittest
ROOT=Path(__file__).resolve().parents[1]
class SlirpBuildTests(unittest.TestCase):
    def test_clean_host_and_android_cache(self):
        spec=importlib.util.spec_from_file_location('clean_slirp_builder',ROOT/'android/build_slirp.py')
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        archive=builder.ROOT/'libslirp-4.9.5.tar.gz'
        with tempfile.TemporaryDirectory(prefix='p2d-slirp-clean-') as temp:
            builder.ROOT=Path(temp)/'deps';builder.ROOT.mkdir();shutil.copy2(archive,builder.ROOT/archive.name)
            builder.OUT=Path(temp)/'out';old=sys.argv
            try:
                for platform in ['host','android']:
                    sys.argv=['build_slirp.py','--platform',platform];builder.main()
                    record=json.loads((builder.OUT/platform/'provenance.json').read_text())
                    self.assertTrue(record['patched']);self.assertEqual(record['archive_sha256'],builder.DIGEST)
                    self.assertTrue((builder.OUT/platform/'lib/libslirp.a').is_file())
            finally:sys.argv=old
if __name__=='__main__':unittest.main()
