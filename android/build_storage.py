"""Build the small API24 no-clobber publication helper, separate from QEMU."""
from pathlib import Path
import hashlib
import json
import subprocess

HERE = Path(__file__).resolve().parent
NDK = Path('/opt/pocket2droid-android-tools/bionic/android-ndk-r30')
CC = NDK / 'toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android24-clang'

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    output = HERE / 'build/storage-runtime'
    output.mkdir(parents=True, exist_ok=True)
    source = HERE / 'native/storage_publish.c'
    library = output / 'libp2dstorage.so'
    command = [str(CC), '-std=c11', '-O2', '-fPIC', '-shared', '-Wall', '-Wextra', '-Werror',
               '-Wl,-z,max-page-size=16384', '-Wl,-z,common-page-size=16384',
               '-Wl,-z,relro,-z,now', '-Wl,--no-undefined', '-Wl,-soname,libp2dstorage.so',
               str(source), '-o', str(library)]
    subprocess.run(command, check=True)
    record = {'binary_path': str(library.relative_to(HERE)), 'binary_sha256': digest(library),
              'sources': {str(source.relative_to(HERE)): digest(source)}, 'builder_sha256': digest(__file__),
              'compiler_sha256': digest(CC.resolve()), 'minimum_api': 24,
              'max_page_size': 16384, 'command': command}
    (HERE / 'build/storage-runtime.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))

if __name__ == '__main__':
    main()
