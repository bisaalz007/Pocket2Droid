"""ROM identity queries must not make unchanged ROM code recompile forever."""
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from run_probe import QMP

BINARY = os.environ.get('P2D_QEMU', '/opt/pocket2droid-tcg-build/host/qemu-system-arm')


def rom_loop(query, reset=False, word_reset=False):
    # ARM code at 0x10000; ROM offset0 branches there before any ID query.
    words = [0xe3a00000]  # mov r0,#0
    literals = []

    def load(register, value):
        literals.append((len(words), register, value))
        words.append(0)

    if query:
        for address, value in [(0xaaaa, 0xaaaa), (0x5554, 0x5555), (0xaaaa, 0x9090)]:
            load(1, address)
            load(2, value)
            words.append(0xe1c120b0)  # strh r2,[r1]
        if reset or word_reset:
            load(1, 0)
            load(2, 0xf0f0)
            words.append(0xe5812000 if word_reset else 0xe1c120b0)
    load(3, 0x30010000)
    words.extend([0xe2800001, 0xe5830000, 0xeafffffc])  # add/store/branch
    for index, register, value in literals:
        offset = (len(words) - index - 2) * 4
        words[index] = 0xe59f0000 | (register << 12) | offset
        words.append(value)
    image = bytearray(0x10000)
    struct.pack_into('<I', image, 0, 0xea003ffe)
    image.extend(struct.pack('<' + 'I' * len(words), *words))
    return image


class RomCacheTests(unittest.TestCase):
    def exercise(self, query, reset=False, word_reset=False):
        with tempfile.TemporaryDirectory(prefix='p2d-rom-cache-') as directory:
            directory = Path(directory)
            rom = directory / 'loop.bin'
            rom.write_bytes(rom_loop(query, reset, word_reset))
            path = directory / 'qmp'
            process = subprocess.Popen([
                BINARY, '-M', 'p2d-devemu', '-accel', 'tcg,thread=single',
                '-bios', str(rom), '-S', '-display', 'none', '-serial', 'none',
                '-monitor', 'none', '-qmp', f'unix:{path},server=on,wait=off',
            ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            qmp = None
            try:
                qmp = QMP(path, process)

                def hmp(command):
                    return qmp.request('human-monitor-command', {'command-line': command})

                iterations = 0
                for _ in range(20):
                    qmp.request('cont')
                    time.sleep(0.01)
                    qmp.request('stop')
                    counter = hmp('xp /1wx 0x30010000')
                    iterations = int(counter.rsplit('0x', 1)[1].strip(), 16)
                    if iterations >= 512:
                        break
                self.assertGreaterEqual(iterations, 512, 'Fixture failed to execute its ARM loop')
                identity = int(hmp('xp /1wx 0').rsplit('0x', 1)[1].strip(), 16)
                id_active = query and not reset
                self.assertEqual(identity, 0x225b0001 if id_active else 0xea003ffe)
                # Device reads beyond the ID bytes retain their original values.
                self.assertEqual(int(hmp('xp /1wx 4').rsplit('0x', 1)[1].strip(), 16), 0)
                self.assertEqual(int(hmp('xp /1wx 0x10000').rsplit('0x', 1)[1].strip(), 16), 0xe3a00000)
                stats = hmp('info jit')
                code_bytes = int(re.search(r'gen code size\s+(\d+)/', stats)[1])
                result = {'identity_query': query, 'iterations': iterations,
                          'generated_code_bytes': code_bytes, 'jit': stats}
                print(json.dumps(result), flush=True)
                # This tiny immutable loop needs only a few cached blocks.
                # A one-instruction MMIO fetch path consumes fresh code space
                # each iteration instead; the generous bound catches that bug.
                self.assertLess(code_bytes, 16 * 1024, result)
                qmp.request('system_reset')
                self.assertEqual(int(hmp('xp /1wx 0').rsplit('0x', 1)[1].strip(), 16), 0xea003ffe)
            finally:
                if qmp is not None:
                    try:
                        qmp.request('quit')
                    finally:
                        qmp.close()
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=5)
                process.stderr.close()

    def test_normal_rom_reuses_translated_loop(self):
        self.exercise(False)

    def test_identity_query_keeps_unchanged_rom_loop_cacheable(self):
        self.exercise(True)

    def test_halfword_reset_restores_rom_header(self):
        self.exercise(True, reset=True)

    def test_word_reset_does_not_change_halfword_command_semantics(self):
        self.exercise(True, word_reset=True)


if __name__ == '__main__':
    unittest.main()
