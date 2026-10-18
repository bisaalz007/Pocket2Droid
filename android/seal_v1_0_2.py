"""Seal the final 1.0.2 release, promoting test10 without behavior changes."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
ROOT, BUILD = HERE.parent, HERE / 'build'
PROJECT = ROOT.parents[1]
VERSION, CODE = '1.0.2', 682
PRIOR = PROJECT / 'apk/1.0.2-test10'
OLD_APK = PRIOR / 'Pocket2Droid-v1.0.2-test10-Hidden-Helper-StorageCard.apk'
OLD_SOURCE = PRIOR / 'Pocket2Droid-v1.0.2-test10.Source.zip'
spec = importlib.util.spec_from_file_location('v102_integrity', HERE / 'finalize_release.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.VERSION, m.VERSION_CODE = VERSION, CODE
digest = lambda data: hashlib.sha256(data).hexdigest()


def snapshot(target, native, runtime):
    raw = target.with_name('.current-source.zip')
    m.snapshot_sources(raw, {'native': native, 'runtime': runtime})
    inventory = {}
    with zipfile.ZipFile(raw) as current, zipfile.ZipFile(OLD_SOURCE) as prior, zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=4) as final:
        for archive in (current, prior):
            for info in archive.infolist():
                name = info.filename
                if name == 'SOURCE_SHA256.json' or name.endswith('-TEST-BUILD.txt') or name in inventory:
                    continue
                data = archive.read(info)
                final.writestr(info, data)
                inventory[name] = digest(data)
        note = (
            'Pocket2Droid 1.0.2/code682 final release.\n'
            'Promotes signed1.0.2-test10 with version metadata changes only.\n'
            'Java behavior, native engines, guest helper, resources and storage formats\n'
            'are unchanged. Hidden2577, per-ROM StorageCard hint and red warning retained.\n'
            'Existing accepted tests are reused by exact source/payload identity; no\n'
            'new gameplay or phone browsing validation is claimed for this promotion.\n'
            'Original package/signer and16KiB APK/ELF alignment are verified.\n'
            'README unchanged; no ROM, save, private probe output or signing key bundled.\n'
            'Build recipes retain documented maintainer workspace/tool/signing assumptions.\n'
        ).encode()
        final.writestr('V1_0_2_RELEASE-BUILD.txt', note)
        inventory['V1_0_2_RELEASE-BUILD.txt'] = digest(note)
        final.writestr('SOURCE_SHA256.json', json.dumps(inventory, indent=2) + '\n')
    raw.unlink()
    with zipfile.ZipFile(target) as archive, zipfile.ZipFile(OLD_SOURCE) as prior:
        old = json.loads(prior.read('SOURCE_SHA256.json'))
        m.require(archive.testzip() is None and len(archive.namelist()) == len(set(archive.namelist())), 'Source CRC/duplicates failed')
        for name, expected in inventory.items():
            m.require(digest(archive.read(name)) == expected, 'Source differs: ' + name)
        changed = sorted(n for n in set(old) & set(inventory) if old[n] != inventory[n])
        m.require(changed == ['android/AndroidManifest.xml', 'android/build.py'], 'Unexpected source changes: ' + repr(changed))
        m.require(set(inventory) - set(old) == {'android/seal_v1_0_2.py', 'V1_0_2_RELEASE-BUILD.txt'}, 'Unexpected added source')
        m.require(set(old) - set(inventory) == {'HIDDEN-STORAGE-TEST-BUILD.txt'}, 'Unexpected removed source')
        m.require(archive.read('README.md') == prior.read('README.md'), 'README changed')
    return inventory


def main():
    release = PROJECT / 'apk' / VERSION
    m.require(not release.exists(), 'Preserve existing release')
    m.require(m.sha(OLD_APK) == 'f02efd8ff7d5b533277e5de03de103fe7f75f5deb5877026e37f791987a127b9', 'Test10 APK changed')
    m.require(m.sha(OLD_SOURCE) == 'd3fb6de5f66e8dc8c485342fde9e8fca16a229c97a3108ac95639414f668614a', 'Test10 source changed')
    protected = {p.relative_to(PRIOR).as_posix(): m.sha(p) for p in PRIOR.rglob('*') if p.is_file()}
    app, native, runtime, storage = (m.load(BUILD / n) for n in ('candidate-build.json', 'bionic-engine.json', 'runtime.json', 'storage-runtime.json'))
    for name, record in (('bionic-engine.json', native), ('runtime.json', runtime), ('storage-runtime.json', storage)):
        m.require(record == m.load(PRIOR / name), 'Tested native/runtime/storage changed: ' + name)
    for name, expected in native['source']['paths'].items():
        m.require(m.sha(ROOT / 'qemu' / name) == expected, 'Stale canonical source: ' + name)
    for name, expected in native['runtime_source_hashes'].items():
        m.require(m.sha(m.NATIVE / name) == expected, 'Stale compiled source: ' + name)
    tested = m.tested_source_hashes()
    with zipfile.ZipFile(OLD_SOURCE) as old:
        for name in tested:
            data = (HERE / name).read_bytes()
            if name == 'AndroidManifest.xml':
                data = data.replace(b'android:versionCode="682"', b'android:versionCode="681"').replace(b'android:versionName="1.0.2"', b'android:versionName="1.0.2-test10"')
            m.require(data == old.read('android/' + name), 'Untested product source change: ' + name)
        builder = (HERE / 'build.py').read_bytes().replace(b"VERSION = '1.0.2'", b"VERSION = '1.0.2-test10'").replace(b'VERSION_CODE = 682', b'VERSION_CODE = 681')
        m.require(builder == old.read('android/build.py'), 'Unexpected builder changes')
        resources = {n.removeprefix('android/'): digest(old.read(n)) for n in old.namelist() if n.startswith('android/res/')}
        m.require(resources == {p.relative_to(HERE).as_posix(): m.sha(p) for p in (HERE / 'res').rglob('*') if p.is_file()}, 'Resources changed')
    libraries = {name: row['sha256'] for name, row in runtime['files'].items()}
    libraries['libp2dstorage.so'] = storage['binary_sha256']
    for name, expected in libraries.items():
        file = BUILD / ('storage-runtime' if name == 'libp2dstorage.so' else 'runtime') / name
        m.require(m.sha(file) == expected, 'Native payload differs: ' + name)
        loads = [line for line in subprocess.check_output(['readelf', '-lW', str(file)], text=True).splitlines() if 'LOAD ' in line]
        m.require(loads and all(int(line.split()[-1], 16) >= 16384 for line in loads), 'ELF alignment failed')
    apk = Path(app['signed_apk'])
    m.require(app['version'] == VERSION and app['package'] == 'com.samsixx.pocket2droid' and not app['test_only'] and app['apk_sha256'] == m.sha(apk), 'APK identity differs')
    signature = m.validate_apk(apk, app['package'], False, libraries, m.sha(BUILD / 'dex/classes.dex'))
    parsed = m.parse_manifest(apk)
    m.require(not parsed.get('instrumentation') and not parsed.get('provider'), 'Test fixtures packaged')
    with zipfile.ZipFile(OLD_APK) as old, zipfile.ZipFile(apk) as current:
        payload = lambda z: {n: digest(z.read(n)) for n in z.namelist() if n != 'AndroidManifest.xml' and not n.startswith('META-INF/')}
        m.require(payload(old) == payload(current), 'APK behavior/resources differ from test10')
    vector = subprocess.check_output([str(m.SDK / 'aapt2'), 'dump', 'xmltree', str(apk), '--file', 'res/drawable/storage_card_warning.xml'], text=True)
    m.require('ffd32f2f' in vector.lower() and 'ffffffff' in vector.lower(), 'Red warning icon missing')
    stage = Path(tempfile.mkdtemp(prefix='.seal-v102-', dir=release.parent))
    try:
        delivered = stage / 'Pocket2Droid-v1.0.2.apk'
        shutil.copy2(apk, delivered)
        source = stage / 'Pocket2Droid-v1.0.2.Source.zip'
        print('Signed1.0.2/code682 verified; test10 behavior/payload unchanged; archiving matching source.', flush=True)
        inventory = snapshot(source, native, runtime)
        for name, expected in tested.items():
            m.require(inventory['android/' + name] == expected, 'Frontend snapshot differs')
        for name, expected in native['source']['paths'].items():
            m.require(inventory['qemu-canonical-changes/' + name] == expected, 'Canonical snapshot differs')
        for name, expected in native['runtime_source_hashes'].items():
            m.require(inventory['qemu-android-exact/' + name] == expected, 'Native snapshot differs')
        for name in ('candidate-build.json', 'bionic-engine.json', 'runtime.json', 'bionic-tools.json', 'storage-runtime.json'):
            shutil.copy2(BUILD / name, stage / name)
        shutil.copy2(Path(__file__), stage / 'release-recipe.py')
        (stage / 'signature.txt').write_text(signature)
        (stage / 'warning-vector.txt').write_text(vector)
        prior_record = m.load(PRIOR / 'FINAL_VERIFICATION.json')
        evidence = stage / 'evidence'
        evidence.mkdir()
        shutil.copy2(PRIOR / 'FINAL_VERIFICATION.json', evidence / 'test10-verification-reused.json')
        record = dict(version=VERSION, version_code=CODE, package=app['package'], apk_sha256=m.sha(delivered), source_archive_sha256=m.sha(source), source_snapshot_files=len(inventory), original_signer=m.SIGNER,
                      signature_verified=True, apk_and_elf_alignment_16k=True, exact_native_and_dex_identity=True, behavior_and_resources_identical_to_test10=True,
                      hidden_virtual_2577=True, storage_card_hint=True, red_warning_icon=True, readme_unchanged=True,
                      prior_test10_preserved=True, phone_accessed=False, new_phone_validation=False, tests_reused_by_exact_identity=True,
                      reused_overlay_tests=prior_record['overlay_tests'], reused_native_tests=prior_record['native_tests'], build_seconds=app['seconds'])
        (stage / 'FINAL_VERIFICATION.json').write_text(json.dumps(record, indent=2) + '\n')
        (stage / 'INSTALL.txt').write_text('Pocket2Droid1.0.2/code682.\nExit the active ROM normally, then install as an update.\nKeep the existing app installed; do not clear its data.\nOfficial package/signer and storage formats are retained.\nThis release promotes test10 with version metadata changes only.\n')
        m.require(protected == {p.relative_to(PRIOR).as_posix(): m.sha(p) for p in PRIOR.rglob('*') if p.is_file()}, 'Test10 changed')
        (stage / 'SHA256SUMS.txt').write_text(''.join(m.sha(p) + '  ' + p.relative_to(stage).as_posix() + '\n' for p in sorted(stage.rglob('*')) if p.is_file()))
        m.publish_release(stage, release)
        print(json.dumps(dict(apk=str(release / delivered.name), **record), indent=2), flush=True)
    finally:
        if stage.exists():
            m.require(stage.parent.resolve() == release.parent.resolve() and stage.name.startswith('.seal-v102-'), 'Unsafe stage cleanup')
            shutil.rmtree(stage)


if __name__ == '__main__':
    main()
