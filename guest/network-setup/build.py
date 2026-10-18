"""Reproducible ARMv4 CE executable for this small freestanding helper only.

LLVM links normal ARM ELF with relocation records. This bounded packer wraps its
single allocated section, imports and explicit HIGHLOW fixups in a CE PE image.
It rejects unsupported relocations; it is not a general Windows linker.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
BASE, CODE, IDATA, RELOC = 0x10000, 0x1000, 0x10000, 0x11000
IMPORTS = ('CloseHandle', 'CreateFileW', 'CreateProcessW', 'ExitThread', 'GetProcAddressW',
           'LoadLibraryW', 'ReadFile', 'RegCloseKey', 'RegCreateKeyExW',
           'RegDeleteValueW', 'RegOpenKeyExW', 'RegQueryValueExW', 'RegSetValueExW', 'Sleep', 'WriteFile')
# Stable CE5 SDK import-library ordinals, independently read from the user's
# official Pocket PC SDK (_6coredll_lib). No SDK binary is copied into output.
ORDINALS = dict(zip(IMPORTS, (553, 168, 493, 6, 530, 528, 170, 455, 456, 458, 461, 463, 464, 496, 171)))


def align(n, size):
    return (n+size-1) & -size


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def imports():
    data = bytearray(40)
    def append(raw, alignment=1):
        data.extend(bytes(align(len(data), alignment)-len(data)))
        at = len(data)
        data.extend(raw)
        return IDATA+at
    dll = append(b'coredll.dll\0')
    names = [0x80000000 | ORDINALS[name] for name in IMPORTS]
    thunks = struct.pack('<'+'I'*(len(names)+1), *names, 0)
    ilt = append(thunks, 4)
    iat = append(thunks, 4)
    struct.pack_into('<IIIII', data, 0, ilt, 0, 0, dll, iat)
    return bytes(data), {name: BASE+iat+i*4 for i, name in enumerate(IMPORTS)}, iat, len(thunks)


def elf_sections(data):
    if data[:7] != b'\x7fELF\x01\x01\x01' or struct.unpack_from('<H', data, 18)[0] != 40:
        raise ValueError('Expected little-endian ELF32 ARM')
    offset = struct.unpack_from('<I', data, 32)[0]
    size, count, names = struct.unpack_from('<HHH', data, 46)
    if size != 40 or count > 128 or offset+size*count > len(data):
        raise ValueError('Invalid ELF section table')
    sections = [struct.unpack_from('<IIIIIIIIII', data, offset+i*size) for i in range(count)]
    strings = sections[names]
    strings = data[strings[4]:strings[4]+strings[5]]
    return {strings[s[0]:].split(b'\0', 1)[0].decode(): s for s in sections}, sections


def pack_elf(elf):
    sections, all_sections = elf_sections(elf)
    section = sections['.p2d']
    address, offset, length = section[3:6]
    if address != BASE+CODE or not 0 < length <= IDATA-CODE:
        raise ValueError('Helper code/data outside bounded image')
    body = elf[offset:offset+length]
    if len(body) != length:
        raise ValueError('Truncated ELF code')
    entry = struct.unpack_from('<I', elf, 24)[0]-BASE
    if not CODE <= entry < CODE+length or entry % 4:
        raise ValueError('Invalid ARM entry point')
    absolute = {}
    # Only ABS32 needs a PE base fixup. Remaining entries are already-resolved
    # ARM relative branches/data references or the ARMv4 BX compatibility tag.
    relative = {1, 3, 28, 29, 40}
    for rel in all_sections:
        if rel[1] != 9:
            continue
        if rel[9] != 8 or rel[5] % 8:
            raise ValueError('Invalid ELF relocation table')
        for pos in range(rel[4], rel[4]+rel[5], 8):
            location, info = struct.unpack_from('<II', elf, pos)
            kind = info & 255
            if kind not in relative | {2}:
                raise ValueError('Unsupported ARM relocation '+str(kind))
            if not address <= location <= address+length-4 or location % 4:
                raise ValueError('Relocation outside helper code/data')
            if kind == 2:
                value = struct.unpack_from('<I', body, location-address)[0]
                if not BASE+CODE <= value < BASE+RELOC:
                    raise ValueError('Absolute relocation targets unowned memory')
                absolute[location-address] = value
    return link_coff(body, entry-CODE, absolute)


def link_coff(body, entry, absolute):
    """Retain ARM code; let the proven COFF linker construct the PE tables."""
    body = bytearray(body)
    strings = bytearray(4)
    symbols = bytearray()
    def symbol(name, value, section):
        index = len(symbols)//18
        encoded = name.encode()
        if len(encoded) > 8:
            field = struct.pack('<II', 0, len(strings))
            strings.extend(encoded+b'\0')
        else:
            field = encoded.ljust(8, b'\0')
        symbols.extend(field+struct.pack('<IhHBB', value, section, 0, 2, 0))
        return index
    symbol('_start', entry, 1)
    own = symbol('p2d_body', 0, 1)
    imported = {value: symbol('__imp_'+name, 0, 0) for name, value in imports()[1].items()}
    relocs = bytearray()
    for offset, value in sorted(absolute.items()):
        if BASE+CODE <= value < BASE+CODE+len(body):
            sym, addend = own, value-(BASE+CODE)
        elif value in imported:
            sym, addend = imported[value], 0
        else:
            raise ValueError('Unresolved absolute relocation')
        struct.pack_into('<I', body, offset, addend)
        relocs.extend(struct.pack('<IIH', offset, sym, 1))  # ARM_ADDR32
    struct.pack_into('<I', strings, 0, len(strings))
    raw = 60
    rel = raw+len(body)
    sym = rel+len(relocs)
    obj = struct.pack('<HHIIIHH', 0x1c4, 1, 0, sym, len(symbols)//18, 0, 0)
    obj += struct.pack('<8sIIIIIIHHI', b'.text', 0, 0, len(body), raw, rel, 0,
                       len(relocs)//10, 0, 0xe0000060)
    obj += body+relocs+symbols+strings
    with tempfile.TemporaryDirectory(prefix='p2d-ce-link-') as temp:
        temp = Path(temp)
        (temp/'code.obj').write_bytes(obj)
        (temp/'coredll.def').write_text('LIBRARY coredll.dll\nEXPORTS\n'+''.join(
            name+' @'+str(ORDINALS[name])+' NONAME\n' for name in IMPORTS))
        linker = shutil.which('lld-link-17')
        subprocess.run([linker, '/lib', '/machine:arm', '/def:'+str(temp/'coredll.def'),
                        '/out:'+str(temp/'coredll.lib')], check=True, stdout=subprocess.PIPE)
        subprocess.run([linker, '/machine:arm', '/entry:_start', '/subsystem:windows,4.0',
                        '/base:0x10000', '/fixed:no',
                        '/nodefaultlib', '/timestamp:0', '/stack:65536,4096',
                        '/out:'+str(temp/'helper.exe'), str(temp/'code.obj'), str(temp/'coredll.lib')],
                       check=True, stdout=subprocess.PIPE)
        result = bytearray((temp/'helper.exe').read_bytes())
    pe = struct.unpack_from('<I', result, 60)[0]
    # LLD's ARM COFF front end is ARMNT; instructions remain the verified ARMv4
    # ELF body. CE uses the older ARM machine and Windows CE subsystem stamps.
    struct.pack_into('<H', result, pe+4, 0x1c0)
    struct.pack_into('<H', result, pe+24+68, 9)
    struct.pack_into('<H', result, pe+24+70, 0)  # Legacy CE characteristics.
    struct.pack_into('<I', result, pe+24+16, struct.unpack_from('<I', result, pe+24+16)[0] & ~1)
    count = struct.unpack_from('<H', result, pe+6)[0]
    for i in range(count):
        at = pe+24+224+i*40
        if result[at:at+8].rstrip(b'\0') == b'.text':
            text_rva, text_raw = struct.unpack_from('<I4xI', result, at+12)
            break
    else:
        raise ValueError('Linked PE has no ARM body')
    # ARMNT COFF tags symbols in executable sections as Thumb. This ELF body is
    # ARMv4 code with embedded data, so preserve each exact original pointer's
    # offset, including legitimately odd byte-string offsets. HIGHLOW fixups
    # remain valid; only the inferred Thumb tag was incorrect for this body.
    for offset, value in absolute.items():
        if BASE+CODE <= value < BASE+CODE+len(body):
            struct.pack_into('<I', result, text_raw+offset, BASE+text_rva+value-(BASE+CODE))
    return bytes(result)


def build(output, source=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    sources = [Path(source)] if source else [HERE/'net_setup.c', HERE/'net_setup_policy.c']
    # LLVM's linker selects its flavor from argv[0]; retain the ld.lld symlink.
    tools = {n: Path(shutil.which(n)).absolute() for n in ('clang-17', 'ld.lld-17', 'lld-link-17')}
    _, addresses, _, _ = imports()
    asm = output/'imports.S'
    asm.write_text('.syntax unified\n.arch armv4t\n.arm\n.text\n'+''.join(
        '.global '+n+'\n.type '+n+',%function\n'+n+':\n ldr ip,[pc,#4]\n ldr ip,[ip]\n bx ip\n .word __iat_'+n+'\n'
        for n in IMPORTS))
    script = output/'helper.ld'
    script.write_text('ENTRY(_start)\nSECTIONS { . = 0x11000; .p2d : { *(.text*) *(.rodata*) *(.data*) *(.bss*) *(COMMON) . = ALIGN(4); } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) } }\n'+''.join(
        '__iat_'+name+' = '+hex(value)+';\n' for name, value in addresses.items()))
    objects = []
    for i, path in enumerate([*sources, asm]):
        obj = output/('source'+str(i)+'.o')
        subprocess.run([str(tools['clang-17']), '--target=armv4t-none-eabi', '-mcpu=arm920t',
                        '-marm', '-Os', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
                        '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '-fshort-wchar',
                        '-I'+str(HERE), '-c', str(path), '-o', str(obj)], check=True)
        objects.append(obj)
    elf = output/'helper.elf'
    subprocess.run([str(tools['ld.lld-17']), '--emit-relocs', '--no-undefined',
                    '-T', str(script), *map(str, objects), '-o', str(elf)], check=True)
    executable = output/'autorun.exe'
    executable.write_bytes(pack_elf(elf.read_bytes()))
    report = {'executable_sha256': sha(executable), 'machine': 'ARMv4', 'subsystem': 9,
              'sources': {str(p): sha(p) for p in [*sources,*sorted(HERE.glob('*.h'))]},
              'builder_sha256': sha(Path(__file__)), 'tools': {n: sha(p) for n, p in tools.items()},
              'imports': {'coredll.dll': ORDINALS}}
    (output/'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.out, args.source)))
