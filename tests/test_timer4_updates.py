"""Timer4 must retain its event when shared PWM registers serve other timers."""
import struct
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import test_devices


class Timer4UpdateTests(test_devices.DeviceTests):
    def setUp(self):
        if '_late_' not in self._testMethodName:
            return super().setUp()
        if 'frequency' in self._testMethodName:
            words = [0xe59f000c, 0xe3a01000, 0xe2211c01,
                     0xe5801000, 0xeafffffc, 0x51000000]
        else:
            words = [0xe59f0008, 0xe59f1008, 0xe5801000,
                     0xeafffffd, 0x51000008, 0x00590000]
        fixture = test_devices.ROOT / 'results/test-inputs/timer-shared-writer.bin'
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_bytes(struct.pack('<6I', *words))
        original_popen = test_devices.subprocess.Popen
        def launch(args, **kwargs):
            args = list(args); args[args.index('-bios') + 1] = str(fixture)
            return original_popen(args, **kwargs)
        with patch('test_devices.subprocess.Popen', side_effect=launch):
            super().setUp()

    def deadline(self):
        return self.qmp.request('qom-get', {'path': '/machine/p2d-soc', 'property': 'timer4-deadline-ns'})

    def start_timer(self, count=1000):
        self.write(0x5100003c, count)
        self.write(0x51000008, (1 << 21) | (1 << 22))
        self.write(0x51000008, (1 << 20) | (1 << 22))

    def test_other_timer_registers_do_not_rephase_timer4(self):
        self.start_timer()
        original = self.deadline()
        self.request('clock_step 111')  # Fractional Timer4 tick exposes rounding.
        for address, value in [(0x51000000, 7), (0x51000004, 3),
                               (0x51000008, 0x00590000),
                               (0x51000030, 1234), (0x51000034, 567),
                               (0x5100003c, 2000)]:
            self.write(address, value)
            self.assertEqual(self.deadline(), original, hex(address))
        self.request('clock_step %d' % (original - 111))
        self.assertTrue(self.read(0x4a000000) & (1 << 14))
        self.assertEqual(self.read(0x51000040), 2000)

    def test_autoreload_toggle_preserves_current_period(self):
        self.start_timer()
        original = self.deadline()
        self.request('clock_step 111')
        self.write(0x51000008, 1 << 20)
        self.assertEqual(self.deadline(), original)
        self.request('clock_step %d' % (original - 111))
        self.assertTrue(self.read(0x4a000000) & (1 << 14))
        self.assertEqual(self.read(0x51000040), 0)

    def test_timer4_manual_reload_stop_and_prescaler_still_apply(self):
        self.start_timer()
        self.request('clock_step 1000')
        self.write(0x51000008, 0)
        stopped = self.read(0x51000040)
        self.request('clock_step 1000')
        self.assertEqual(self.read(0x51000040), stopped)
        self.write(0x5100003c, 2000)
        self.write(0x51000008, (1 << 21) | (1 << 22))
        self.assertEqual(self.read(0x51000040), 2000)
        self.write(0x51000008, (1 << 20) | (1 << 22))
        original = self.deadline()
        self.write(0x51000000, 1 << 8)
        self.assertEqual(self.deadline() - 2000, 2 * (original - 2000) - 1)

    def test_stop_resume_uses_counter_until_explicit_manual_update(self):
        self.start_timer()
        self.request('clock_step 1000')
        self.write(0x51000008, 0)
        stopped = self.read(0x51000040)
        self.write(0x5100003c, 2000)
        self.write(0x51000008, 1 << 20)
        self.assertEqual(self.read(0x51000040), stopped)
        self.write(0x51000008, (1 << 20) | (1 << 21))
        self.assertEqual(self.read(0x51000040), 2000)

    def check_late_writer(self, count=60000):
        self.start_timer(count)  # Default1ms vs the 50ms host suspension.
        self.run_late_host_service()
        previous = self.deadline()
        self.write(0x4a000000, 1 << 14)
        self.run_late_host_service()
        self.assertTrue(self.read(0x4a000000) & (1 << 14))
        self.assertGreater(self.deadline(), previous)

    def test_late_running_shared_tcon_writes_do_not_lose_system_tick(self):
        # A real guest repeatedly writes Timer3's controls while Timer4 runs.
        # Old code cancels the overdue Timer4 at count=0 before host service.
        self.check_late_writer()

    def test_late_frequency_writes_do_not_discard_expiration(self):
        self.check_late_writer()

    def test_late_frequency_writes_with_short_period_keep_ticks_alive(self):
        self.check_late_writer(100)  # 1.667us: callback/snapshot can cross a period.


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(Timer4UpdateTests(name) for name in Timer4UpdateTests.__dict__ if name.startswith('test_'))


if __name__ == '__main__':
    unittest.main()
