"""Device Emulator navigation-key SPI protocol through real QMP/QTest."""
import unittest, json
from pathlib import Path
from test_devices import DeviceTests

class KeyboardTests(DeviceTests):
    def keypad_sequences(self):
        return json.loads((Path(__file__).resolve().parents[1]/'android/tests/fixtures/sdk-keypad.json').read_text())['sequences']

    def test_keyboard_digits_make_break(self):
        self.write(0x59000020, 1 << 5)
        for name,seq in self.keypad_sequences().items():
            if name.startswith('f'): continue
            for phase in ('make','break'):
                self.key(name,phase=='make')
                self.assertEqual([self.pop() for _ in seq[phase]],seq[phase])
                self.assertEqual(self.pop(),0)

    def test_keyboard_star_hash_make_break(self):
        self.write(0x59000020, 1 << 5)
        for name in ('f8','f9'):
            for phase in ('make','break'):
                self.key(name,phase=='make')
                self.assertEqual([self.pop() for _ in range(3)],self.keypad_sequences()[name][phase])
                self.assertEqual(self.pop(),0)

    def test_keyboard_symbol_sequences_atomic_at_capacity(self):
        self.write(0x59000020, 1 << 5)
        for name in ('f8','f9'):
            for down in (True,False):
                for _ in range(30):self.key('tab')
                self.key(name,down)
                self.assertEqual([self.pop() for _ in range(31)],[0x0b]*30+[0])
                for _ in range(29):self.key('tab')
                self.key(name,down)
                self.assertEqual([self.pop() for _ in range(29)],[0x0b]*29)
                self.assertEqual([self.pop() for _ in range(4)],self.keypad_sequences()[name]['make' if down else 'break']+[0])

    def test_keyboard_keypad_with_other_keys(self):
        self.write(0x59000020, 1 << 5)
        expected=[]
        for name,down in [('up',True),('8',True),('f8',True),('8',False),('f8',False),('up',False)]:
            self.key(name,down)
            expected.extend(([0x6c if down else 0xec] if name=='up' else self.keypad_sequences()[name]['make' if down else 'break']))
        self.assertEqual([self.pop() for _ in range(len(expected)+1)],expected+[0])
    def key(self, name, down=True):
        self.qmp.request('input-send-event', {'events': [
            {'type': 'key', 'data': {'key': {'type': 'qcode', 'data': name}, 'down': down}}]})

    def pop(self):
        self.write(0x59000030, 0xff)
        return self.read(0x59000034)

    def test_keyboard_disabled_and_navigation_make_break(self):
        self.key('down')
        self.assertEqual(self.pop(), 0)
        self.write(0x59000020, 1 << 5)  # SPI1 interrupt mode.
        for name, code in [('up', 0x6c), ('down', 0x6a), ('left', 0x6d),
                           ('right', 0x6f), ('ret', 0x5a), ('esc', 0x29), ('spc', 0x6e),
                           ('tab', 0x0b), ('backspace', 0x69)]:
            self.key(name)
            self.key(name, False)
            self.assertTrue(self.read(0x4a000000) & 2)
            self.assertEqual(self.pop(), code)
            self.write(0x4a000000, 2)
            self.assertTrue(self.read(0x4a000000) & 2)
            self.assertEqual(self.pop(), code | 0x80)
            self.assertEqual(self.pop(), 0)

    def test_keyboard_spi_poll_does_not_consume_and_reset_drops_queue(self):
        self.write(0x59000020, 1 << 5)
        self.key('ret')
        self.write(0x59000030, 0)
        self.assertEqual(self.read(0x59000034), 0)
        self.assertEqual(self.pop(), 0x5a)
        self.key('down')
        self.qmp.request('system_reset')
        self.assertEqual(self.pop(), 0)

    def test_keyboard_full_queue_never_overwrites_unread_events(self):
        self.write(0x59000020, 1 << 5)
        for _ in range(32):
            self.key('tab')
        self.key('ret')  # Overflow must preserve the already queued sequence.
        for _ in range(32):
            self.assertEqual(self.pop(), 0x0b)
        self.assertEqual(self.pop(), 0)

    def test_keyboard_phone_keys_match_original_emulator(self):
        self.write(0x59000020, 1 << 5)
        # F1-F4 in the SDK skin become Fn + 1/2/3/4 in the CE keyboard.
        for name, code in [('f1', 0x31), ('f2', 0x39), ('f3', 0x2f), ('f4', 0x37)]:
            self.key(name)
            self.key(name, False)
            self.assertTrue(self.read(0x4a000000) & 2)
            self.assertEqual([self.pop() for _ in range(6)],
                             [0x63, code, 0xe3, 0x63, code | 0x80, 0xe3])
            self.assertEqual(self.pop(), 0)
        self.key('meta_l')
        self.key('meta_l', False)
        self.assertEqual([self.pop(), self.pop(), self.pop()], [0x60, 0xe0, 0])

    def test_keyboard_phone_sequence_is_atomic_at_queue_capacity(self):
        self.write(0x59000020, 1 << 5)
        for _ in range(30):
            self.key('tab')
        self.key('f1')  # Never leave a partial Fn sequence at the queue tail.
        self.assertEqual([self.pop() for _ in range(30)], [0x0b] * 30)
        self.assertEqual(self.pop(), 0)
        for _ in range(29):
            self.key('tab')
        self.key('f2', False)
        self.assertEqual([self.pop() for _ in range(29)], [0x0b] * 29)
        self.assertEqual([self.pop() for _ in range(4)], [0x63, 0xb9, 0xe3, 0])
        for _ in range(31):
            self.key('tab')
        self.assertEqual([self.pop() for _ in range(30)], [0x0b] * 30)
        self.key('f1')  # The sequence wraps across the circular buffer's end.
        self.assertEqual([self.pop() for _ in range(5)], [0x0b, 0x63, 0x31, 0xe3, 0])

    def test_keyboard_phone_key_sequences_preserve_other_held_keys(self):
        self.write(0x59000020, 1 << 5)
        for name, down in [('up', True), ('f3', True), ('f4', True),
                           ('f3', False), ('up', False), ('f4', False)]:
            self.key(name, down)
        self.assertEqual([self.pop() for _ in range(15)],
                         [0x6c, 0x63, 0x2f, 0xe3, 0x63, 0x37, 0xe3,
                          0x63, 0xaf, 0xe3, 0xec, 0x63, 0xb7, 0xe3, 0])

    def test_keyboard_direction_select_and_soft_key_together(self):
        self.write(0x59000020, 1 << 5)
        self.qmp.request('input-send-event', {'events': [
            {'type': 'key', 'data': {'key': {'type': 'qcode', 'data': name}, 'down': True}}
            for name in ['left', 'ret', 'f1']]})
        self.key('ret', False)
        self.key('f1', False)
        self.key('left', False)
        self.assertEqual([self.pop() for _ in range(11)],
                         [0x6d, 0x5a, 0x63, 0x31, 0xe3, 0xda, 0x63, 0xb1, 0xe3, 0xed, 0])

def load_tests(loader, tests, pattern):
    return unittest.TestSuite(KeyboardTests(name) for name in KeyboardTests.__dict__
                              if name.startswith('test_keyboard_'))

if __name__ == '__main__':
    unittest.main()
