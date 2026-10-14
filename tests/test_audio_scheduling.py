"""Actual media code against frozen V6.56; adapter is test-only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'tests/reference/v656-iis-dma.c'
BASE_SHA = 'dcdabe28838723a420972260c132e6f51922ba5d9e533cace3e2a69883fa7a36'
SOURCE = ROOT / 'qemu/hw/dma/p2d-iis-dma.c'


def compile_model(source, directory, name):
    text = source.read_text()
    model = text[text.index('typedef struct P2DMedia'):text.index('static const MemoryRegionOps')]
    model += text[text.index('static void media_clock'):text.index('static void media_reset')]
    soc = (ROOT / 'qemu/hw/misc/p2d-devemu-services.c').read_text()
    reset_end = text.index('static void media_realize') if 'static void media_realize' in text else text.index('static void media_init')
    model += text[text.index('static void media_reset'):reset_end]
    model += soc[soc.index('static void timer_before_update'):soc.index('static void p2d_timer_expired')]
    harness = (ROOT / 'tests/audio-model-harness.c').read_text()
    generated = directory / (name + '.c')
    prefix = '#define P2D_AUDIO_MODEL 1\n' if 'media_output_sample' in text else ''
    generated.write_text(prefix + '#include "hw/arm/p2d-audio.h"\n' + harness.replace('/* MODEL */', model))
    output = directory / name
    subprocess.run(['cc', '-O2', '-std=gnu11', '-I'+str(ROOT/'qemu/include'), str(generated),
                    str(ROOT/'qemu/hw/dma/p2d-audio.c'), '-o', str(output)], check=True)
    return output


def run_model(binary, scenario):
    return json.loads(subprocess.check_output([str(binary), str(scenario)], text=True))


class AudioSchedulingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if hashlib.sha256(BASELINE.read_bytes()).hexdigest() != BASE_SHA:
            raise ValueError('Frozen V6.56 media source changed')
        cls.temporary = tempfile.TemporaryDirectory(prefix='p2d-audio-model-')
        cls.directory = Path(cls.temporary.name)
        cls.old = compile_model(BASELINE, cls.directory, 'old')
        cls.new = compile_model(SOURCE, cls.directory, 'new')

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_overdue_work_avoids_per_halfword_queue_updates(self):
        old, new = run_model(self.old, 0), run_model(self.new, 0)
        self.assertEqual(new['digest'], old['digest'])
        self.assertEqual(new['reads'], old['reads'])
        self.assertEqual(new['errors'], 0)
        # Same 100ms of guest audio, materially fewer general timer updates.
        self.assertLess(new['timer_mods'], old['timer_mods'] // 8)
        self.assertLess(new['callbacks'], old['callbacks'] // 8)

    def test_host_poll_avoids_per_halfword_wakeups(self):
        old, new = run_model(self.old, 11), run_model(self.new, 11)
        self.assertEqual(new['digest'], old['digest'], (old, new))
        self.assertEqual(new['errors'], 0)
        self.assertLess(new['host_wakes'], old['host_wakes'] // 8)

    def test_mmio_progress_between_audio_batches_matches_clock(self):
        old, new = run_model(self.old, 12), run_model(self.new, 12)
        self.assertEqual(new['digest'], old['digest'], (old, new))
        self.assertEqual(new['errors'], 0)

    def test_other_device_deadlines_and_dma_state_match_v656(self):
        for scenario in range(1, 10):
            with self.subTest(scenario=scenario):
                old, new = run_model(self.old, scenario), run_model(self.new, scenario)
                self.assertEqual(new['digest'], old['digest'], (old, new))
                for field in ['reads','irqs','first_irq','remaining','current_address','fifo_level','errors']:
                    self.assertEqual(new[field], old[field], (old, new))

    def test_late_peer_registration_synchronizes_deferred_logical_predecessors(self):
        old, new = run_model(self.old, 13), run_model(self.new, 13)
        self.assertEqual(old['first_irq'], 19)
        self.assertEqual(new['first_irq'], 19, (old, new))
        self.assertEqual(new['digest'], old['digest'], (old, new))

    def test_clock_change_synchronizes_deferred_samples_at_old_rate(self):
        old, new = run_model(self.old, 14), run_model(self.new, 14)
        self.assertEqual(new['digest'], old['digest'], (old, new))

    def test_reset_clears_deferred_audio_without_spurious_queue_drains(self):
        new = run_model(self.new, 15)
        self.assertEqual(new['errors'], 0)

    def test_randomized_register_clock_stop_reload_and_memory_boundaries(self):
        old, new = run_model(self.old, 10), run_model(self.new, 10)
        self.assertEqual(new['digest'], old['digest'], (old, new))
        self.assertEqual(new['errors'], 0)

    def test_export_enabled_preserves_all_guest_state(self):
        import struct
        for scenario in range(16):
            path=self.directory/'enabled.bin';data=bytearray(67648)
            struct.pack_into('<5I',data,0,0x41443250,1,67648,64,65536);path.write_bytes(data)
            enabled=json.loads(subprocess.check_output([str(self.new),str(scenario),str(path)],text=True))
            disabled=run_model(self.new,scenario)
            self.assertEqual(enabled,disabled,(scenario,enabled,disabled))


if __name__ == '__main__':
    unittest.main()
