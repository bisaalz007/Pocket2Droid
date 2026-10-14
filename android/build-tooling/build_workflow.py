#!/usr/bin/env python3
"""Incremental Pocket2Droid build driver. Python standard library."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
APK = 'Pocket2Droid-V6.52-Persistent-JIT-UNSIGNED.apk'
TARGET = ['-target', 'aarch64-linux-android23']
ALIGN = ['-Wl,-z,max-page-size=16384', '-Wl,-z,common-page-size=16384']
COMPILER_ENV = ('PATH', 'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH',
                'OBJC_INCLUDE_PATH', 'LIBRARY_PATH', 'COMPILER_PATH',
                'GCC_EXEC_PREFIX', 'SDKROOT', 'SOURCE_DATE_EPOCH',
                'LANG', 'LC_ALL', 'LC_CTYPE', 'LD_LIBRARY_PATH', 'LD_PRELOAD',
                'CLANG_CONFIG_FILE_SYSTEM_DIR', 'CLANG_CONFIG_FILE_USER_DIR',
                'CCC_OVERRIDE_OPTIONS')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local_dependencies(root, source, seen=None):
    """Follow quoted includes, including C files included by retained tests.

    These sources use literal quoted local includes. System headers belong to
    the selected toolchain; use --force after changing its system headers/libs.
    """
    seen = set() if seen is None else seen
    source = Path(source).resolve()
    if source in seen:
        return seen
    seen.add(source)
    content = source.read_text(encoding='utf-8')
    for include in re.findall(r'^\s*#\s*include\s*"([^"]+)"', content, re.M):
        options = [source.parent / include, root / include, root / 'src' / include]
        found = next((p for p in options if p.is_file()), None)
        if found is None:
            raise FileNotFoundError(f'{source}: missing local include {include}')
        local_dependencies(root, found, seen)
    return seen


class Cache:
    def __init__(self, root, force=False):
        self.root = Path(root).resolve()
        self.directory = self.root / 'build' / 'incremental'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.force = force
        self.records = []
        self.mutex = threading.Lock()

    def record(self, name, status, started):
        row = {'stage': name, 'status': status, 'seconds': round(time.perf_counter() - started, 4)}
        with self.mutex:
            self.records.append(row)
            print(f'{status:6} {name}: {row["seconds"]:.3f}s', flush=True)

    def execute(self, name, command):
        start = time.perf_counter()
        try:
            result = subprocess.run(command, cwd=self.root, check=True, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if result.stdout:
                with self.mutex:
                    print(result.stdout, end='', flush=True)
        except subprocess.CalledProcessError as exc:
            if exc.stdout:
                print(exc.stdout, end='', flush=True)
            self.record(name, 'FAIL', start)
            raise
        self.record(name, 'RUN', start)

    def run(self, name, command, inputs, outputs, identity='', action=None):
        start = time.perf_counter()
        inputs = sorted(set(Path(p).resolve() for p in inputs))
        outputs = [Path(p).resolve() for p in outputs]
        payload = {'command': command, 'identity': identity,
                   'inputs': [(str(p), digest(p)) for p in inputs],
                   'outputs': [str(p) for p in outputs]}
        key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        stamp = self.directory / (hashlib.sha256(name.encode()).hexdigest() + '.json')
        try:
            prior = json.loads(stamp.read_text())
        except (OSError, ValueError):
            prior = {}
        if not isinstance(prior, dict):
            prior = {}
        current = {str(p): digest(p) for p in outputs if p.is_file()}
        if not self.force and prior.get('key') == key and len(current) == len(outputs) and prior.get('outputs') == current:
            self.record(name, 'REUSE', start)
            return False
        # Remove the success record BEFORE running: failed or interrupted work
        # must never leave metadata that authorizes reuse.
        stamp.unlink(missing_ok=True)
        for output in outputs:
            output.parent.mkdir(parents=True, exist_ok=True)
        if action:
            action()
            self.record(name, 'RUN', start)
        else:
            self.execute(name, command)
        result = {'key': key, 'outputs': {str(p): digest(p) for p in outputs}}
        temporary = stamp.with_suffix('.tmp')
        temporary.write_text(json.dumps(result, indent=2))
        temporary.replace(stamp)
        return True


def tool(variable, default, root):
    command = shlex.split(os.environ.get(variable, default))
    if not command:
        raise ValueError(f'{variable} must name a compiler')
    executable = shutil.which(command[0])
    if not executable:
        raise FileNotFoundError(f'{command[0]} not found; use the Linux toolchain in TOOLCHAIN.lock')
    command[0] = str(Path(executable).resolve())
    version = subprocess.check_output(command + ['--version'], cwd=root, text=True)
    # Covers replacement of the compiler in place, not just its version string.
    identity = {'command': command, 'version': version, 'binary': digest(command[0]),
                'environment': {name: os.environ.get(name) for name in COMPILER_ENV}}
    # Store only a digest; environment values (potential credentials) are never logged.
    return command, hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def parallel(jobs, actions):
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        # Consume every result and wait for all workers even when one fails.
        futures = [pool.submit(action) for action in actions]
        errors = []
        for future in futures:
            try:
                future.result()
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise errors[0]


def native(cache, jobs):
    compiler, identity = tool('CLANG', 'clang-17', cache.root)
    linker = shutil.which('ld.lld', path=str(Path(compiler[0]).parent) + os.pathsep + os.environ.get('PATH', ''))
    if not linker:
        raise FileNotFoundError('ld.lld not found; install the pinned LLD toolchain')
    link_identity = identity + digest(linker)
    root = cache.root
    shared = [root / 'TOOLCHAIN.lock', Path(__file__)]
    actions = []
    for stem in ['libandroid', 'libc']:
        command = compiler + TARGET + ['-shared', '-nostdlib', '-fuse-ld=lld', f'-Wl,-soname,{stem}.so'] + ALIGN + [f'src/{stem}_stub.c', '-o', f'build/{stem}.so']
        deps = local_dependencies(root, root / f'src/{stem}_stub.c') | set(shared)
        actions.append(lambda s=stem, c=command, d=deps: cache.run(s, c, d, [root / f'build/{s}.so'], link_identity))
    flags = {
        'wm6android': ['-O2', '-mllvm', '-inline-threshold=150', '-mno-outline-atomics'],
        'arm_core': ['-O3', '-fno-vectorize', '-fno-slp-vectorize'],
        'folder_share_host': ['-O2'],
    }
    for stem, optimization in flags.items():
        command = compiler + TARGET + optimization + ['-fPIC', '-ffreestanding', '-fno-builtin', '-std=c99', '-I./src', '-c', f'src/{stem}.c', '-o', f'build/{stem}.o']
        deps = local_dependencies(root, root / f'src/{stem}.c') | set(shared)
        actions.append(lambda s=stem, c=command, d=deps: cache.run(s, c, d, [root / f'build/{s}.o'], identity))
    parallel(jobs, actions)
    objects = [f'build/{stem}.o' for stem in flags]
    command = compiler + TARGET + ['-shared', '-nostdlib', '-fuse-ld=lld', '-Wl,--build-id'] + ALIGN + ['-Wl,-soname,libwm6android.so', '-Wl,-z,now', '-L./build'] + objects + ['-landroid', '-lc', '-o', 'build/libwm6android.so']
    cache.run('link', command, [root / p for p in objects + ['build/libandroid.so', 'build/libc.so']] + shared,
              [root / 'build/libwm6android.so'], link_identity)
    resources(cache)


def resources(cache):
    root = cache.root
    for script, output in [('build_manifest.py', 'apk/AndroidManifest.xml'), ('build_resources.py', 'apk/resources.arsc')]:
        cache.run(script, [sys.executable, script], [root / script, Path(__file__)], [root / output], sys.version)
    icon = root / 'apk/res/drawable/pocket2droid_icon.png'
    cache.run('icon', ['copy', 'Pocket2Droid_App_Icon.png'], [root / 'Pocket2Droid_App_Icon.png'], [icon],
              action=lambda: shutil.copyfile(root / 'Pocket2Droid_App_Icon.png', icon))
    notice = root / 'apk/assets/PLACE_ROM_HERE.txt'
    text = 'Place PPC_USA.BIN in /storage/emulated/0/Pocket2Droid/data/\n'
    cache.run('ROM notice', ['write', text], [], [notice], action=lambda: notice.write_bytes(text.encode()))


def package(cache):
    root = cache.root
    inputs = ['package_v652.py', 'apk/AndroidManifest.xml', 'apk/resources.arsc',
              'apk/res/drawable/pocket2droid_icon.png', 'apk/assets/PLACE_ROM_HERE.txt', 'build/libwm6android.so']
    cache.run('package', [sys.executable, 'package_v652.py'], [root / p for p in inputs], [root / APK], sys.version)
    # Verification runs even when the package itself is reused.
    cache.execute('verify unsigned APK', [sys.executable, 'verify_apk_v640_unsigned.py', APK,
                                         digest(root / 'build/libwm6android.so')])


def checks(cache, mode, jobs):
    root = cache.root
    compiler, identity = tool('CC', 'gcc', root)
    flags = shlex.split(os.environ.get('CFLAGS', '-std=c99 -O2 -I.'))
    suites = json.loads((root / 'tests/active_suites.json').read_text(encoding='utf-8-sig'))
    def check(name):
        source = root / 'tests/active' / name
        output = root / 'build/tests' / Path(name).stem
        deps = local_dependencies(root, source) | {root / 'TOOLCHAIN.lock', Path(__file__)}
        cache.run('compile ' + name, compiler + flags + [str(source), '-o', str(output)], deps, [output], identity)
        # Executables are cached, results are not: always exercise current code.
        cache.execute('test ' + name, [str(output)])
    parallel(jobs, [lambda n=name: check(n) for name in suites[mode]])
    sources = ['src/arm_core.c', 'src/wm6android.c', 'src/folder_share_host.c']
    deps = {Path(__file__), root / 'TOOLCHAIN.lock'}
    for source in sources:
        deps |= local_dependencies(root, root / source)
    cache.run('syntax', compiler + ['-std=c99', '-O0', '-I./src', '-fsyntax-only'] + sources, deps, [], identity)
    print(f'active_checks=PASS mode={mode}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=['native', 'apk', 'check'])
    parser.add_argument('mode', nargs='?', choices=['quick', 'full'], default='quick')
    parser.add_argument('--jobs', type=int, default=int(os.environ.get('JOBS', '4')))
    parser.add_argument('--force', action='store_true', help='rebuild all selected targets without deleting outputs')
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    cache = Cache(ROOT, args.force)
    lock = cache.directory / 'running.lock'
    try:
        lock.mkdir()
    except FileExistsError:
        parser.error(f'Another workflow may be running. If a previous process was killed, remove {lock} after confirming it stopped.')
    started = time.perf_counter()
    success = False
    try:
        if args.target == 'check':
            checks(cache, args.mode, args.jobs)
        else:
            native(cache, args.jobs)
            if args.target == 'apk':
                package(cache)
        success = True
    finally:
        report = {'target': args.target, 'success': success,
                  'wall_seconds': round(time.perf_counter() - started, 4), 'stages': cache.records}
        (cache.directory / 'last-run.json').write_text(json.dumps(report, indent=2))
        lock.rmdir()
        print(f'Total wall time: {report["wall_seconds"]:.3f}s; success={success}', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'Build failed: {error}', file=sys.stderr)
        sys.exit(1)
