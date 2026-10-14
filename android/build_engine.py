"""Reuse native build caches; preserve all earlier measured engine artifacts."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent
spec = importlib.util.spec_from_file_location('sync_source', EXPERIMENT / 'sync_source.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)
out = HERE / 'build'
out.mkdir(exist_ok=True)
for label, cache, build in [
    ('host', '/opt/pocket2droid-tcg-build/source', '/opt/pocket2droid-tcg-build/host'),
    ('arm64', '/opt/pocket2droid-tcg-build/source-arm64', '/opt/pocket2droid-tcg-build/host-arm64')]:
    sync.CACHE = Path(cache)
    sync.main()
    deps = Path('/opt/pocket2droid-tcg-build/arm64-deps')
    env = dict(os.environ)
    if label == 'arm64':
        config = sync.CACHE / 'configs/devices/arm-softmmu/p2d.mak'
        config.write_text(config.read_text() + '\nCONFIG_GENERIC_LOADER=y\n')
        env.update(PKG_CONFIG='/usr/bin/pkg-config',
                   PKG_CONFIG_LIBDIR=str(deps / 'usr/lib/aarch64-linux-gnu/pkgconfig'),
                   PKG_CONFIG_SYSROOT_DIR=str(deps))
    with (out / (label + '-engine.log')).open('w') as log:
        subprocess.run(['ninja', '-j12', 'qemu-system-arm'], cwd=build, env=env,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    binary = out / ('libp2dengine.so' if label == 'arm64' else 'qemu-host')
    shutil.copy2(Path(build) / 'qemu-system-arm', binary)
    record = {'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
              'source': json.loads(sync.CACHE.with_name(sync.CACHE.name + '.sync.json').read_text()),
              'platform': 'static Linux/glibc engine; Android frontend owns separate process'}
    (out / (label + '-engine.json')).write_text(json.dumps(record, indent=2) + '\n')
    print(label, 'engine built:', binary, flush=True)
