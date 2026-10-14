"""Actual QEMU timer functions: fake clock, notifications and callback threads."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = ['timer_expired_ns','timerlist_next_deadline_ns','timerlist_deadline_ns',
             'timer_del_locked','timer_mod_ns_locked','timerlist_rearm',
             'timer_mod_with_wake_ns','timer_mod_ns','timer_mod_coalesced_ns',
             'timer_mod_anticipate_ns','timerlist_run_timers']


def function(text, name):
    # Function definitions in this upstream file start at a line boundary.
    import re
    match = re.search(r'^.*\b' + name + r'\([^;]*?\)\n\{', text, re.M)
    if not match:
        raise ValueError(name)
    start, opening = match.start(), match.end() - 1
    depth = 1
    end = opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


class TimerWakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='p2d-timer-wake-')
        directory = Path(cls.temp.name)
        source = (ROOT / 'qemu/util/qemu-timer.c').read_text()
        actual = '\n\n'.join(function(source,n) for n in FUNCTIONS)
        harness = (ROOT / 'tests/timer-wake-harness.c').read_text()
        generated = directory / 'timer.c'
        generated.write_text(harness.replace('/* ACTUAL_TIMER_FUNCTIONS */', actual))
        cls.binary = directory / 'timer'
        subprocess.run(['cc','-O2','-std=gnu11','-pthread',str(generated),
                        '-o',str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def check(self, scenario):
        result=json.loads(subprocess.check_output([str(self.binary),str(scenario)],text=True))
        self.assertTrue(result['passed'])

    def test_wake_minimum_and_nonhead_registration_notifies(self):
        self.check(0)

    def test_same_callback_phase_advance_does_not_self_notify(self):
        self.check(1)

    def test_earlier_own_rearm_notifies(self):
        self.check(2)

    def test_other_timer_rearm_notifies(self):
        self.check(3)

    def test_ordinary_api_anticipation_deletion_and_disabled_clock(self):
        self.check(4)

    def test_replay_and_icount_keep_logical_deadlines(self):
        self.check(5)

    def test_external_thread_rearm_still_notifies_during_callback(self):
        self.check(6)

    def test_nested_callback_restores_previous_notification_context(self):
        self.check(7)

if __name__=='__main__':
    unittest.main()
