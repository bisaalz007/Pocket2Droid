"""Seal V6.55 from explicit current evidence; retain all earlier releases."""
from pathlib import Path
import argparse
import base64
import ctypes
import errno
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROJECT = ROOT.parents[1]
BUILD = HERE / 'build'
NATIVE = Path('/opt/pocket2droid-android-tools/bionic/qemu-source')
TOOLS = Path('/opt/pocket2droid-android-tools/bionic')
SDK = Path('/opt/pocket2droid-android-tools/android-16')
LEGACY_TOOLS = PROJECT / 'SOURCE/review-v640/Pocket2Droid-V6.40-Clean-Source'
VERSION = '6.55'
VERSION_CODE = 655
SIGNER = '85d6f87a557def48710b8e295ed58513888a99852843a90106b3b7f18e39681b'
CHECKS = ('android_storage_migration', 'android_shared_folder_read_write',
          'android_pause_storage_sync', 'retained_storage_reopen', 'android_orderly_exit')
ARTIFACT_MARKERS = {'engine-key-art': 'PASS actual Engine ART',
                    'storage-layout-tests': 'PASS StorageLayout',
                    'storage-publish-art': 'PASS Android no-replace publication'}

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def require(value, message):
    if not value:
        raise ValueError(message)

def load(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def local(relative, base=HERE):
    name = Path(relative)
    require(not name.is_absolute() and '..' not in name.parts, 'Path escapes allowed source root: ' + str(relative))
    path = (base / name).resolve(strict=True)
    require(path.is_relative_to(base.resolve()) and path.is_file(), 'Input is outside allowed source root: ' + str(relative))
    return path

def tested_source_hashes():
    paths = [HERE / 'AndroidManifest.xml'] + list((HERE / 'src').rglob('*.java'))
    paths += [p for p in (HERE / 'native').rglob('*') if p.suffix in ('.c', '.h')]
    return {str(p.relative_to(HERE)): sha(p) for p in sorted(paths)}

def validate_evidence(path, source_hashes, smoke_hash):
    evidence = load(path)
    require(evidence.get('version') == VERSION, 'Integration evidence must identify V' + VERSION)
    require(evidence.get('smoke_apk_sha256') == smoke_hash, 'Integration evidence belongs to a different smoke APK')
    require(evidence.get('source_hashes') == source_hashes, 'Integration evidence is stale or has incomplete Android source hashes')
    checks = evidence.get('checks', {})
    for name in CHECKS:
        require(checks.get(name) is True, 'Current integration check missing or failed: ' + name)
    require(checks.get('original_user_data_accessed') is False, 'Integration must explicitly preserve original user data')
    artifacts = evidence.get('artifacts', {})
    require(isinstance(artifacts, dict) and artifacts, 'Explicit current test artifacts are required')
    for name, record in artifacts.items():
        require(Path(name).name == name and name not in ('.', '..'), 'Invalid evidence artifact name')
        file = local(record['path'])
        require(file.suffix.lower() in ('.txt', '.log', '.json'), 'Phone UI, binary guest data and images are excluded: ' + name)
        require(record.get('kind') in ('test-log', 'validation-record', 'integration-summary'), 'Unclassified evidence: ' + name)
        require(sha(file) == record.get('sha256'), 'Evidence artifact changed: ' + name)
    for name, marker in ARTIFACT_MARKERS.items():
        require(name in artifacts, 'Current test artifact missing: ' + name)
        text = local(artifacts[name]['path']).read_text(encoding='utf-8-sig')
        require(marker in text, 'Test did not pass: ' + name)
        if name == 'engine-key-art':
            require('import/start Activity ownership' in text, 'Engine ART evidence predates storage ownership changes')
            require('private storage-lock argument/inode retained' in text, 'Engine ART evidence predates the private lock fix')
    require(isinstance(evidence.get('observations', {}), dict), 'Observations must be a current structured summary')
    return evidence

def parse_manifest(apk):
    spec = importlib.util.spec_from_file_location('p2d_release_manifest', LEGACY_TOOLS / 'verify_signed_apk.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with zipfile.ZipFile(apk) as archive:
        elements = module.parse_manifest(archive.read('AndroidManifest.xml'))
    result = {}
    for name, attrs in elements:
        result.setdefault(name, []).append(attrs)
    return result

def validate_apk(apk, package, test_only, libraries, expected_dex):
    with zipfile.ZipFile(apk) as archive:
        require(archive.testzip() is None, 'APK content failed CRC verification')
        names = archive.namelist()
        require(len(names) == len(set(names)), 'Duplicate APK entries')
        require({n for n in names if n.startswith('lib/')} == {'lib/arm64-v8a/' + n for n in libraries},
                'APK contains missing or extra native libraries (previous engine must be absent)')
        for name, digest in libraries.items():
            require(hashlib.sha256(archive.read('lib/arm64-v8a/' + name)).hexdigest() == digest, 'APK native identity changed: ' + name)
        require(hashlib.sha256(archive.read('classes.dex')).hexdigest() == expected_dex, 'APK Java code differs from current compiled source')
    by_name = parse_manifest(apk)
    manifest, app, sdk = by_name['manifest'][0], by_name['application'][0], by_name['uses-sdk'][0]
    require(manifest['package'] == package and manifest['versionCode'] == VERSION_CODE
            and manifest['versionName'] == VERSION, 'APK release identity differs')
    require(sdk['minSdkVersion'] == 24 and sdk['targetSdkVersion'] == 36, 'Unexpected Android API contract')
    require(bool(app.get('debuggable', 0)) == test_only and app.get('extractNativeLibs') == 0xffffffff, 'Unexpected APK application flags')
    require(not any(a.get('name') == 'android.app.NativeActivity' for a in by_name.get('activity', [])), 'Previous engine activity is still packaged')
    permissions = {p['name']: p for p in by_name.get('uses-permission', [])}
    require('android.permission.MANAGE_EXTERNAL_STORAGE' in permissions, 'All-files access permission is missing')
    for name in ('android.permission.READ_EXTERNAL_STORAGE', 'android.permission.WRITE_EXTERNAL_STORAGE'):
        require(permissions.get(name, {}).get('maxSdkVersion') == 29, 'Legacy storage permission must be bounded to SDK29')
    require(app.get('requestLegacyExternalStorage') == 0xffffffff, 'SDK29 external storage flag is missing')
    verification = subprocess.check_output(['java', '-jar', str(SDK / 'lib/apksigner.jar'), 'verify', '--verbose', '--print-certs', str(apk)], text=True)
    require(SIGNER in verification, 'Original signer identity differs')
    subprocess.run([str(SDK / 'zipalign'), '-c', '-P', '16', '4', str(apk)], check=True)
    return verification

def validate_inputs(evidence_path):
    app, smoke = load(BUILD / 'candidate-build.json'), load(BUILD / 'smoke-build.json')
    native, runtime, storage = (load(BUILD / n) for n in ('bionic-engine.json', 'runtime.json', 'storage-runtime.json'))
    require(app.get('package') == 'com.samsixx.wm6android' and app.get('test_only') is False
            and app.get('version') == VERSION and app.get('previous_engine_packaged') is False, 'A verified production V6.55 build is required')
    require(smoke.get('package') == 'com.samsixx.p2dtest' and smoke.get('test_only') is True
            and smoke.get('version') == VERSION and smoke.get('previous_engine_packaged') is False, 'A matching disposable V6.55 integration build is required')
    apk = BUILD / ('Pocket2Droid-V' + VERSION + '-TCG-CANDIDATE-SIGNED.apk')
    smoke_apk = BUILD / ('Pocket2Droid-V' + VERSION + '-TCG-SMOKE-SIGNED.apk')
    require(sha(apk) == app['apk_sha256'] and sha(smoke_apk) == smoke['apk_sha256'], 'Signed APK differs from build record')
    require(native['builder_sha256'] == sha(HERE / 'build_bionic.py'), 'Native builder changed since compilation')
    require(native['binary_sha256'] == sha(BUILD / 'libp2dengine-bionic.so'), 'Native compiler output identity differs')
    for name, digest in native['source']['paths'].items():
        require(sha(local(name, ROOT / 'qemu')) == digest, 'Canonical native source changed: ' + name)
    for name, digest in native['runtime_source_hashes'].items():
        require(sha(local(name, NATIVE)) == digest, 'Generated Android native source changed: ' + name)
    for name, digest in native['support_sources'].items():
        require(sha(local(name, BUILD / 'termux-reference/setjmp-aarch64')) == digest, 'Android setjmp input changed: ' + name)
    patch = (BUILD / 'termux-reference/0016-Add-workaround-for-tagged-pointers-on-Android-12.patch').read_text().replace('#ifdef __TERMUX__', '#ifdef __ANDROID__')
    require(hashlib.sha256(patch.encode()).hexdigest() == native['termux_patch_sha256'], 'Android heap-tag adaptation changed')
    require(runtime['native_engine_record_sha256'] == sha(BUILD / 'bionic-engine.json')
            and runtime['packager_sha256'] == sha(HERE / 'package_runtime.py')
            and runtime['tools_record_sha256'] == sha(BUILD / 'bionic-tools.json'), 'Native runtime packaging inputs changed')
    libraries = {}
    for name, record in runtime['files'].items():
        require(sha(local(name, BUILD / 'runtime')) == record['sha256'], 'Packaged native library changed: ' + name)
        require(sha(local(name + '.unstripped', BUILD / 'runtime')) == record['symbols_sha256'], 'Native symbols changed: ' + name)
        libraries[name] = record['sha256']
    helper = local(storage['binary_path'])
    require(helper == (BUILD / 'storage-runtime/libp2dstorage.so').resolve(), 'Unexpected storage helper path')
    require(storage['builder_sha256'] == sha(HERE / 'build_storage.py')
            and storage['binary_sha256'] == sha(helper), 'Storage helper build identity differs')
    for name, digest in storage['sources'].items():
        require(sha(local(name)) == digest, 'Storage helper source changed: ' + name)
    libraries[helper.name] = storage['binary_sha256']
    require(app.get('engine_sha256') == libraries['libp2dengine.so'] == smoke.get('engine_sha256'), 'Smoke and production engines differ')
    require(app.get('storage_helper_sha256') == storage['binary_sha256'] == smoke.get('storage_helper_sha256'), 'Smoke and production storage helpers differ')
    expected_dex = sha(BUILD / 'dex/classes.dex')
    evidence = validate_evidence(evidence_path, tested_source_hashes(), smoke['apk_sha256'])
    signature = validate_apk(apk, 'com.samsixx.wm6android', False, libraries, expected_dex)
    validate_apk(smoke_apk, 'com.samsixx.p2dtest', True, libraries, expected_dex)
    return dict(app=app, native=native, runtime=runtime, storage=storage, helper=helper,
                apk=apk, evidence=evidence, signature=signature)

def write_archive_file(archive, source, name, inventory):
    require(name not in inventory, 'Duplicate source snapshot entry: ' + name)
    source = Path(source)
    info = zipfile.ZipInfo(name, date_time=(2026, 10, 8, 12, 0, 0))
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    if source.is_symlink():
        data = os.readlink(source).encode()
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
    else:
        data = source.read_bytes()
        info.external_attr = (stat.S_IFREG | stat.S_IMODE(source.stat().st_mode)) << 16
    archive.writestr(info, data)
    inventory[name] = hashlib.sha256(data).hexdigest()

def snapshot_sources(target, records):
    inventory = {}
    native, runtime = records['native'], records['runtime']
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=4) as archive:
        def put(source, name):
            write_archive_file(archive, source, name, inventory)
        for base, dirs, files in os.walk(NATIVE, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in ('.git', '__pycache__', '.venv', '.cache'))
            for name in sorted(files):
                p = Path(base) / name
                put(p, 'qemu-android-exact/' + str(p.relative_to(NATIVE)))
            for name in list(dirs):
                p = Path(base) / name
                if p.is_symlink():
                    put(p, 'qemu-android-exact/' + str(p.relative_to(NATIVE)))
                    dirs.remove(name)
        for name in native['source']['paths']:
            put(local(name, ROOT / 'qemu'), 'qemu-canonical-changes/' + name)
        for name in ('sync_source.py', 'sources.lock.json', 'board_contract.json'):
            put(ROOT / name, name)
        put(ROOT / 'run_probe.py', 'run_probe.py')
        for test in sorted(p for p in (ROOT / 'tests').rglob('*') if p.is_file() and p.suffix in ('.py', '.S', '.c', '.h')):
            put(test, 'tests/' + str(test.relative_to(ROOT / 'tests')))
        selected = list(HERE.glob('*.py')) + [HERE / 'AndroidManifest.xml', HERE / 'PLAN.txt']
        selected += list((HERE / 'src').rglob('*.java'))
        selected += [p for p in (HERE / 'res').rglob('*') if p.is_file()]
        selected += list((HERE / 'tests/dependencies').glob('json-*.jar'))
        selected += [p for p in (HERE / 'tests').rglob('*') if p.suffix in ('.java', '.c', '.h', '.py')]
        selected += list((HERE / 'tests/fixtures').glob('*.json'))
        selected += [p for p in (HERE / 'native').rglob('*') if p.suffix in ('.c', '.h')]
        selected += list((BUILD / 'termux-reference').glob('*.patch')) + [BUILD / 'termux-reference/build.sh']
        selected += list((BUILD / 'termux-reference/setjmp-aarch64').iterdir())
        selected += [BUILD / n for n in ('bionic-engine.json', 'runtime.json', 'bionic-tools.json', 'storage-runtime.json')]
        for p in sorted(selected):
            if p.is_file():
                put(p, 'android/' + str(p.relative_to(HERE)))
        # Generic build tools remain imported by build.py. No previous emulator
        # implementation, activity, library, ROM or save is bundled.
        for name in ('build_workflow.py', 'verify_signed_apk.py'):
            put(LEGACY_TOOLS / name, 'android/build-tooling/' + name)
        tools = load(BUILD / 'bionic-tools.json')
        originals = {r['original_name'] for r in runtime['files'].values()}
        used = {'libglib-2.0.so.0': 'glib', 'libpcre2-8.so': 'pcre2', 'libiconv.so': 'libiconv',
                'libandroid-support.so': 'libandroid-support', 'libpixman-1.so': 'libpixman', 'libz.so.1': 'zlib'}
        for original in sorted(originals & used.keys()):
            record = tools['packages'][used[original]]
            p = TOOLS / 'downloads' / record['url'].rsplit('/', 1)[1]
            require(sha(p) == record['sha256'], 'Downloaded Android dependency input changed')
            put(p, 'android/dependency-inputs/' + p.name)
        license_root = TOOLS / 'sysroot/data/data/com.termux/files/usr/share/doc'
        for p in sorted(license_root.rglob('*')):
            if p.is_file() and not p.is_symlink() and 'license' in p.name.lower():
                put(p, 'android/dependency-licenses/' + str(p.relative_to(license_root)))
        archive.writestr('SOURCE_SHA256.json', json.dumps(inventory, indent=2) + '\n')
    with zipfile.ZipFile(target) as archive:
        require(archive.testzip() is None, 'Source snapshot verification failed')
    return inventory

def publish_release(stage, release):
    # A final check followed by Path.rename would still replace an empty
    # concurrently created directory on Linux. Publish with kernel no-replace.
    require(stage.resolve().is_relative_to(PROJECT.resolve())
            and release.parent.resolve().is_relative_to(PROJECT.resolve())
            and stage.parent.resolve() == release.parent.resolve(), 'Release move must stay within one workspace directory')
    libc = ctypes.CDLL(None, use_errno=True)
    operation = libc.renameat2
    operation.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    operation.restype = ctypes.c_int
    result = operation(-100, os.fsencode(stage), -100, os.fsencode(release), 1)
    if result != 0:
        code = ctypes.get_errno()
        if code in (errno.EINVAL, errno.ENOSYS, errno.ENOTSUP) and os.environ.get('WSL_DISTRO_NAME'):
            # DrvFS does not implement renameat2 for directories. Windows'
            # Directory.Move is an atomic same-volume move that refuses any
            # existing destination. Do not fall back to overwrite-capable rename.
            source = subprocess.check_output(['wslpath', '-w', str(stage.resolve())], text=True).strip()
            target = subprocess.check_output(['wslpath', '-w', str(release.parent.resolve() / release.name)], text=True).strip()
            quote = lambda text: "'" + text.replace("'", "''") + "'"
            script = "$ErrorActionPreference='Stop';[System.IO.Directory]::Move(" + quote(source) + ',' + quote(target) + ')'
            encoded = base64.b64encode(script.encode('utf-16le')).decode()
            process = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-EncodedCommand', encoded], capture_output=True, text=True)
            if process.returncode:
                if release.exists():
                    raise FileExistsError(errno.EEXIST, 'Release destination already exists', str(release))
                raise RuntimeError('Windows no-replace release move failed: ' + process.stderr.strip())
            return
        raise OSError(code, os.strerror(code), str(release))

def finalize(records, evidence_path):
    release = PROJECT / 'apk' / VERSION
    require(not release.exists(), 'V6.55 release already exists; preserve it instead of overwriting')
    previous = PROJECT / 'apk/6.54'
    require(previous.is_dir(), 'Protected V6.54 rollback release is missing')
    previous_hashes = {p.name: sha(p) for p in previous.iterdir() if p.is_file()}
    stage = Path(tempfile.mkdtemp(prefix='.seal-' + VERSION + '-', dir=release.parent))
    try:
        app, runtime, helper, evidence = (records[n] for n in ('app', 'runtime', 'helper', 'evidence'))
        apk = stage / ('Pocket2Droid-V' + VERSION + '-TCG-SIGNED.apk')
        shutil.copy2(records['apk'], apk)
        for name in ('candidate-build.json', 'bionic-engine.json', 'runtime.json', 'bionic-tools.json', 'storage-runtime.json'):
            shutil.copy2(BUILD / name, stage / name)
        (stage / 'candidate-signature.txt').write_text(records['signature'])
        shutil.copy2(evidence_path, stage / 'RELEASE_EVIDENCE.json')
        evidence_dir = stage / 'evidence'
        evidence_dir.mkdir()
        for name, artifact in evidence['artifacts'].items():
            source = local(artifact['path'])
            shutil.copy2(source, evidence_dir / (name + source.suffix))
        sources = stage / ('Pocket2Droid-V' + VERSION + '-TCG-Source.zip')
        source_inventory = snapshot_sources(sources, records)
        for name, digest in records['native']['source']['paths'].items():
            require(source_inventory['qemu-canonical-changes/' + name] == digest, 'Archived canonical source differs from compiled source: ' + name)
        for name, digest in records['native']['runtime_source_hashes'].items():
            require(source_inventory['qemu-android-exact/' + name] == digest, 'Archived Android adaptation differs from compiled source: ' + name)
        for name, digest in evidence['source_hashes'].items():
            require(source_inventory['android/' + name] == digest, 'Archived Android source differs from tested source: ' + name)
        source_bytes = sources.stat().st_size
        symbols = stage / ('Pocket2Droid-V' + VERSION + '-TCG-Symbols.zip')
        with zipfile.ZipFile(symbols, 'w', zipfile.ZIP_DEFLATED, compresslevel=4) as archive:
            for name in runtime['files']:
                archive.write(BUILD / 'runtime' / (name + '.unstripped'), name + '.unstripped')
            archive.write(helper, helper.name + '.unstripped')
            archive.write(BUILD / 'runtime.json', 'runtime.json')
            archive.write(BUILD / 'storage-runtime.json', 'storage-runtime.json')
        with zipfile.ZipFile(symbols) as archive:
            require(archive.testzip() is None, 'Symbols snapshot verification failed')
            for name, record in runtime['files'].items():
                require(hashlib.sha256(archive.read(name + '.unstripped')).hexdigest() == record['symbols_sha256'], 'Archived symbols identity changed: ' + name)
            require(hashlib.sha256(archive.read(helper.name + '.unstripped')).hexdigest() == records['storage']['binary_sha256'], 'Archived storage JNI identity changed')
        require(sha(apk) == app['apk_sha256'], 'Copied APK changed')
        validate_evidence(evidence_path, tested_source_hashes(), evidence['smoke_apk_sha256'])
        require(previous_hashes == {p.name: sha(p) for p in previous.iterdir() if p.is_file()}, 'Protected V6.54 artifacts changed during sealing')
        scope = dict(app, delivered_apk=apk.name, source_archive_sha256=sha(sources), symbols_archive_sha256=sha(symbols),
                     previous_engine_packaged=False, previous_release_artifacts=previous_hashes,
                     source_snapshot_files=len(source_inventory), integration_checks=evidence['checks'],
                     observations=evidence.get('observations', {}), source_hashes=evidence['source_hashes'],
                     original_package_updated=False, exact_game_fps_known=False,
                     legacy_save_conversion=False, sound_output_enabled=False)
        (stage / 'RELEASE_SCOPE.json').write_text(json.dumps(scope, indent=2) + '\n')
        sums = [p for p in sorted(stage.rglob('*')) if p.is_file()]
        (stage / 'SHA256SUMS.txt').write_text(''.join(sha(p) + '  ' + str(p.relative_to(stage)) + '\n' for p in sums))
        require(not release.exists(), 'Release destination appeared during sealing; preserve it')
        publish_release(stage, release)
        return dict(apk=str(release / apk.name), sha256=app['apk_sha256'], source_zip_bytes=source_bytes,
                    source_snapshot_files=len(source_inventory), previous_engine_packaged=False, previous_release_preserved=True)
    finally:
        if stage.exists():
            require(stage.resolve().parent == release.parent.resolve() and stage.name.startswith('.seal-' + VERSION + '-'), 'Unexpected staging cleanup path')
            shutil.rmtree(stage)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True, help='Explicit current V6.55 integration record; no inherited V6.54 claims')
    parser.add_argument('--validate-only', action='store_true', help='Read-only verification; do not create release artifacts')
    args = parser.parse_args()
    evidence_path = args.evidence.resolve(strict=True)
    require(evidence_path.is_relative_to(HERE.resolve()), 'Evidence record must be inside android workspace')
    records = validate_inputs(evidence_path)
    if args.validate_only:
        print(json.dumps(dict(version=VERSION, validated_only=True, apk_sha256=records['app']['apk_sha256'],
                              checks=records['evidence']['checks']), indent=2), flush=True)
    else:
        print(json.dumps(finalize(records, evidence_path), indent=2), flush=True)

if __name__ == '__main__':
    main()
