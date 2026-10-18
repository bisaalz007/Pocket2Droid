"""Real ARM artifact checks for the one-shot Windows Mobile setup helper."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / 'guest/network-setup/build.py'


class NetSetupBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='p2d-net-setup-build-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'entry.c'
        self.source.write_text('extern void ExitThread(unsigned);\n'
                               'static unsigned short text[]={112,50,100,0};\n'
                               'unsigned short *volatile message=text;\n'
                               'void _start(void){ExitThread(*message==112?0:1);}\n')

    def build(self, name):
        out = self.root / name
        result = subprocess.run(['python3', str(BUILDER), '--source', str(self.source),
                                 '--out', str(out)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, 'Helper builder failed: '+result.stderr)
        return out, (out / 'autorun.exe').read_bytes()

    def test_real_arm_pe_imports_entry_and_relocations(self):
        out, data = self.build('one')
        self.assertEqual(data[:2], b'MZ')
        pe = struct.unpack_from('<I', data, 60)[0]
        self.assertEqual(data[pe:pe+4], b'PE\0\0')
        machine, count, timestamp = struct.unpack_from('<HHI', data, pe+4)
        self.assertEqual((machine, count, timestamp), (0x1c0, 3, 0))
        opt = pe+24
        self.assertEqual(struct.unpack_from('<H', data, opt)[0], 0x10b)
        self.assertEqual(struct.unpack_from('<H', data, opt+68)[0], 9)
        entry = struct.unpack_from('<I', data, opt+16)[0]
        self.assertGreaterEqual(entry, 0x1000)
        sections = []
        for i in range(count):
            s = opt+224+i*40
            size, rva, rawsize, raw = struct.unpack_from('<IIII', data, s+8)
            self.assertLessEqual(raw+rawsize, len(data))
            sections.append((rva, size, raw))
        def offset(rva):
            for start, size, raw in sections:
                if start <= rva < start+size:
                    return raw+rva-start
            self.fail('Unmapped RVA '+hex(rva))
        offset(entry)
        imports, n = struct.unpack_from('<II', data, opt+96+8)
        self.assertGreaterEqual(n, 40)
        desc = offset(imports)
        ilt, _, _, dll, iat = struct.unpack_from('<IIIII', data, desc)
        self.assertEqual(data[offset(dll):].split(b'\0', 1)[0], b'coredll.dll')
        names = []
        at = offset(ilt)
        while struct.unpack_from('<I', data, at)[0]:
            name = struct.unpack_from('<I', data, at)[0]
            self.assertTrue(name & 0x80000000, 'CE SDK binds coredll APIs by stable ordinal')
            names.append(name & 0xffff)
            at += 4
        self.assertIn(6, names)  # ExitThread, independently verified SDK ordinal.
        offset(iat)
        reloc, size = struct.unpack_from('<II', data, opt+96+5*8)
        self.assertGreaterEqual(size, 12)
        at = offset(reloc)
        end = at+size
        fixups = []
        while at < end:
            page, length = struct.unpack_from('<II', data, at)
            self.assertGreaterEqual(length, 8)
            self.assertEqual(length % 4, 0)
            self.assertLessEqual(at+length, end)
            for j in range(at+8, at+length, 2):
                v = struct.unpack_from('<H', data, j)[0]
                if not v:
                    continue
                self.assertEqual(v >> 12, 3)
                address = page+(v & 0xfff)
                target = struct.unpack_from('<I', data, offset(address))[0]
                self.assertGreaterEqual(target, 0x10000)
                fixups.append(address)
            at += length
        self.assertTrue(fixups, 'Actual absolute pointers require base relocation')
        manifest = json.loads((out / 'manifest.json').read_text())
        self.assertEqual(manifest['executable_sha256'], hashlib.sha256(data).hexdigest())
        self.assertIn(hashlib.sha256(self.source.read_bytes()).hexdigest(), manifest['sources'].values())

    def test_reproducible_executable(self):
        _, first = self.build('one')
        _, second = self.build('two')
        self.assertEqual(first, second)

    def test_unknown_elf_relocation_is_rejected(self):
        out, _ = self.build('one')
        data = bytearray((out / 'helper.elf').read_bytes())
        shoff = struct.unpack_from('<I', data, 32)[0]
        shsize, count = struct.unpack_from('<HH', data, 46)
        changed = False
        for i in range(count):
            at = shoff+i*shsize
            kind, offset, size = struct.unpack_from('<I8xII', data, at+4)
            if kind == 9 and size:
                info = struct.unpack_from('<I', data, offset+4)[0]
                struct.pack_into('<I', data, offset+4, (info & ~255) | 255)
                changed = True
                break
        self.assertTrue(changed, 'Fixture must contain real ELF relocations')
        spec = importlib.util.spec_from_file_location('p2d_net_setup_builder', BUILDER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with self.assertRaisesRegex(ValueError, 'relocation'):
            module.pack_elf(bytes(data))

    def test_actual_arm920t_import_bridge_calls_thumb_and_returns(self):
        out, _ = self.build('bridge')
        assembly = out/'bridge.S'
        imported = json.loads((out/'manifest.json').read_text())['imports']['coredll.dll']
        assembly.write_text('''
.syntax unified
.arch armv4t
.arm
.text
.global _start
_start:
 ldr sp, =0x30010000
 mov r0,#7
 bl ExitThread
 cmp r0,#42
 bne failed
 ldr r1, =passed
 mov r0,#4
 svc #0x123456
 mov r0,#0x18
 ldr r1, =0x20026
 svc #0x123456
failed: b failed
.thumb
.thumb_func
thumb_target:
 adds r0,#35
 bx lr
.align 2
passed: .asciz "PASS CE ARM Thumb import bridge\\n"
.align 2
''' + ''.join('.global __iat_'+name+'\n__iat_'+name+': .word thumb_target\n' for name in imported))
        image = out/'bridge.bin'
        subprocess.run(['clang-17', '--target=armv4t-none-eabi', '-mcpu=arm920t',
                        '-nostdlib', '-fuse-ld=lld-17', '-Wl,-Ttext=0', '-Wl,--oformat=binary',
                        str(assembly), str(out/'imports.S'), '-o', str(image)], check=True)
        binary = os.environ.get('P2D_QEMU', '/opt/pocket2droid-network-integration/host/qemu-system-arm')
        try:
            result = subprocess.run([binary, '-M', 'p2d-devemu', '-cpu', 'arm920t',
                                     '-bios', str(image), '-display', 'none', '-serial', 'none',
                                     '-monitor', 'none', '-semihosting-config', 'enable=on,target=native'],
                                    timeout=5, capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            self.fail('ARM920T import bridge did not return from Thumb code')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PASS CE ARM Thumb import bridge', result.stderr)

    def test_actual_arm920t_linked_pe_reads_aligned_data(self):
        out, data = self.build('pe-execution')
        pe = struct.unpack_from('<I', data, 60)[0]
        opt = pe+24
        sections = [struct.unpack_from('<8sIIIIIIHHI', data, opt+224+i*40)
                    for i in range(struct.unpack_from('<H', data, pe+6)[0])]
        entry = 0x10000+struct.unpack_from('<I', data, opt+16)[0]
        assembly = out/'pe-start.S'
        assembly.write_text('''.syntax unified
.arch armv4t
.arm
.global _start
_start:
 ldr sp, =0x30010000
 ldr pc, ='''+hex(entry)+'''
.org 0x40
exit_hook:
 cmp r0,#0
 bne failed
 mov r0,#4
 ldr r1,=passed
 svc #0x123456
 mov r0,#0x18
 ldr r1,=0x20026
 svc #0x123456
failed: b failed
passed: .asciz "PASS linked CE PE data\\n"
''')
        start = out/'pe-start.bin'
        subprocess.run(['clang-17', '--target=armv4t-none-eabi', '-mcpu=arm920t',
                        '-nostdlib', '-fuse-ld=lld-17', '-Wl,-Ttext=0', '-Wl,--oformat=binary',
                        str(assembly), '-o', str(start)], check=True)
        image = bytearray(0x10000+struct.unpack_from('<I', data, opt+56)[0])
        raw = start.read_bytes();image[:len(raw)] = raw
        for s in sections:
            address = 0x10000+s[2]
            image[address:address+s[3]] = data[s[4]:s[4]+s[3]]
        iat, size = struct.unpack_from('<II', data, opt+96+12*8)
        for offset in range(0, size-4, 4):
            struct.pack_into('<I', image, 0x10000+iat+offset, 0x40)
        path = out/'pe-execution.bin';path.write_bytes(image)
        binary = os.environ.get('P2D_QEMU', '/opt/pocket2droid-network-integration/host/qemu-system-arm')
        try:
            result = subprocess.run([binary, '-M', 'p2d-devemu', '-cpu', 'arm920t',
                                     '-bios', str(path), '-display', 'none', '-serial', 'none',
                                     '-monitor', 'none', '-semihosting-config', 'enable=on,target=native'],
                                    timeout=5, capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            self.fail('Linked CE PE did not read its aligned data and exit successfully')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PASS linked CE PE data', result.stderr)

    def test_policy_preserves_custom_and_only_marks_verified_setup(self):
        program = self.root/'policy-test'
        result = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                                 '-fshort-wchar', '-I'+str(ROOT/'guest/network-setup'),
                                 str(ROOT/'tests/net_setup_policy_test.c'),
                                 str(ROOT/'guest/network-setup/net_setup_policy.c'),
                                 '-o', str(program)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(program), str(ROOT/'tests/fixtures/network-setup')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PASS setup policy', result.stdout)

    def test_actual_ce_adapter_removes_partial_marker_after_flush_failure(self):
        program=self.root/'marker-test'
        result=subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fshort-wchar',
                               '-I'+str(ROOT/'guest/network-setup'),str(ROOT/'tests/net_setup_marker_test.c'),
                               str(ROOT/'guest/network-setup/net_setup_policy.c'),'-o',str(program)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        result=subprocess.run([str(program)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('PASS actual CE marker adapter',result.stdout)


if __name__ == '__main__':
    unittest.main()
