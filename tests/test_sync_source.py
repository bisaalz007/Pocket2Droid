"""Incremental cache reconciliation must include reverted and removed changes."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import sync_source


class SourceSyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='p2d-sync-')
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name) / 'source'
        self.cache = Path(self.temporary.name) / 'cache'
        self.source.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.source)], check=True)
        (self.source / 'tracked.c').write_text('base\n')
        self.git('add', '.')
        self.git('-c', 'user.name=Prototype fixture', '-c', 'user.email=fixture@invalid',
                 'commit', '-qm', 'fixture base')
        self.base = self.git('rev-parse', 'HEAD').strip()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.source), *args], text=True)

    def sync(self):
        # The current script exposes only fixed globals. Rebinding these for the
        # isolated fixture reproduces the stale-cache behavior without touching /opt.
        old = sync_source.SOURCE, sync_source.CACHE, sync_source.BASE
        try:
            sync_source.SOURCE, sync_source.CACHE, sync_source.BASE = self.source, self.cache, self.base
            sync_source.main()
        finally:
            sync_source.SOURCE, sync_source.CACHE, sync_source.BASE = old

    def test_reverted_tracked_file_restored_in_cache(self):
        (self.source / 'tracked.c').write_text('changed\n')
        self.sync()
        self.git('checkout', '--', 'tracked.c')
        self.sync()
        self.assertEqual((self.cache / 'tracked.c').read_text(), 'base\n')

    def test_removed_local_addition_removed_from_cache(self):
        (self.source / 'added.c').write_text('added\n')
        self.sync()
        (self.source / 'added.c').unlink()
        self.sync()
        self.assertFalse((self.cache / 'added.c').exists())

    def test_unowned_cache_addition_rejected(self):
        self.sync()
        (self.cache / 'unexpected.c').write_text('stale unowned source\n')
        with self.assertRaisesRegex(ValueError, 'unowned'):
            self.sync()
