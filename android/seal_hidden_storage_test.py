"""Seal test10: hidden virtual helper, StorageCard hint and red warning icon."""
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
PROOF = BUILD / 'network-setup/hidden-overlay'
UI = BUILD / 'storage-card-setting'
VERSION, CODE = '1.0.2-test10', 681
spec = importlib.util.spec_from_file_location('hidden_release_integrity', HERE / 'finalize_release.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.VERSION, m.VERSION_CODE = VERSION, CODE
digest = lambda data: hashlib.sha256(data).hexdigest()


def snapshot(target, native, runtime, previous):
    raw = target.with_name('.current-source.zip')
    m.snapshot_sources(raw, {'native': native, 'runtime': runtime})
    inventory = {}
    with zipfile.ZipFile(raw) as current, zipfile.ZipFile(previous) as prior, zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=4) as final:
        for archive in (current, prior):
            for info in archive.infolist():
                name = info.filename
                if name == 'SOURCE_SHA256.json' or name.endswith('-TEST-BUILD.txt') or name in inventory:
                    continue
                data = archive.read(info)
                final.writestr(info, data)
                inventory[name] = digest(data)
        note = (
            'Pocket2Droid 1.0.2-test10/code681.\n'
            'Virtual 2577 and autorun.exe gain hidden metadata; autorun names and access stay intact.\n'
            'Real shared-folder entries retain their existing visibility and ownership.\n'
            'StorageCard row includes the per-ROM change hint; warning uses a red vector icon.\n'
            '11 overlay and182 native tests pass; fresh disposable WM6 verifies hidden\n'
            'attributes and automatic diagnostic autorun. Bionic build and runtime seal pass.\n'
            'UI polish compiled and verified in the APK; prior36 Android card checks\n'
            'precede this cosmetic change and were not rerun. No phone validation yet.\n'
            'Show all files can reveal hidden entries. No new HTTP/provisioning test claim.\n'
            'README unchanged. No ROM, save, private probe output or signing key bundled.\n'
            'Build recipes retain their documented WSL/cache/signing assumptions.\n'
        ).encode()
        final.writestr('HIDDEN-STORAGE-TEST-BUILD.txt', note)
        inventory['HIDDEN-STORAGE-TEST-BUILD.txt'] = digest(note)
        final.writestr('SOURCE_SHA256.json', json.dumps(inventory, indent=2) + '\n')
    raw.unlink()
    with zipfile.ZipFile(target) as archive:
        m.require(archive.testzip() is None and len(archive.namelist()) == len(set(archive.namelist())), 'Source CRC/duplicates failed')
        for name, expected in inventory.items():
            m.require(digest(archive.read(name)) == expected, 'Source differs: ' + name)
    return inventory


def main():
    prior, release = PROJECT / 'apk/1.0.2-test9', PROJECT / 'apk' / VERSION
    m.require(not release.exists(), 'Preserve existing release')
    old_apk = prior / 'Pocket2Droid-v1.0.2-test9-StorageCard.apk'
    old_source = prior / 'Pocket2Droid-v1.0.2-test9.Source.zip'
    m.require(m.sha(old_apk) == '196140a1f1025171e2afa8ae4251652528f87f89d91a34c53e5650876f2b268b', 'Test9 APK changed')
    m.require(m.sha(old_source) == '567604accaaa0c7c2900e41ab48b836e2a4c65be11bfad5d46894714f6fa37a9', 'Test9 source changed')
    protected = {p.relative_to(prior).as_posix(): m.sha(p) for p in prior.rglob('*') if p.is_file()}
    app, native, runtime, storage = (m.load(BUILD / name) for name in ('candidate-build.json', 'bionic-engine.json', 'runtime.json', 'storage-runtime.json'))
    m.require(storage == m.load(prior / 'storage-runtime.json'), 'Storage helper changed')
    before_native = m.load(prior / 'bionic-engine.json')
    m.require(native['source']['base'] == before_native['source']['base'] and native['source']['paths'].keys() == before_native['source']['paths'].keys(), 'Native source inventory changed')
    changed_native = [name for name, value in native['source']['paths'].items() if value != before_native['source']['paths'][name]]
    m.require(changed_native == ['hw/misc/p2d-devemu-import.c'], 'Unexpected native scope: ' + repr(changed_native))
    for name, expected in native['source']['paths'].items():
        m.require(m.sha(ROOT / 'qemu' / name) == expected, 'Stale canonical source: ' + name)
    for name, expected in native['runtime_source_hashes'].items():
        m.require(m.sha(m.NATIVE / name) == expected, 'Stale compiled source: ' + name)
    tested = m.tested_source_hashes()
    changed_java = []
    with zipfile.ZipFile(old_source) as old:
        for name in tested:
            data = (HERE / name).read_bytes()
            if name == 'AndroidManifest.xml':
                data = data.replace(b'android:versionCode="681"', b'android:versionCode="680"').replace(b'android:versionName="1.0.2-test10"', b'android:versionName="1.0.2-test9"')
            if data != old.read('android/' + name):
                changed_java.append(name)
        m.require(changed_java == ['src/com/samsixx/pocket2droid/RomSettingsActivity.java'], 'Unexpected frontend scope: ' + repr(changed_java))
        builder = (HERE / 'build.py').read_bytes().replace(b"VERSION = '1.0.2-test10'", b"VERSION = '1.0.2-test9'").replace(b'VERSION_CODE = 681', b'VERSION_CODE = 680')
        m.require(builder == old.read('android/build.py'), 'Unexpected build recipe change')
        readme = old.read('README.md')
        old_resources = {n.removeprefix('android/'): digest(old.read(n)) for n in old.namelist() if n.startswith('android/res/')}
    current_resources = {p.relative_to(HERE).as_posix(): m.sha(p) for p in (HERE / 'res').rglob('*') if p.is_file()}
    m.require(set(current_resources) - set(old_resources) == {'res/drawable/storage_card_warning.xml'}, 'Unexpected added resources')
    m.require(all(current_resources.get(n) == value for n, value in old_resources.items()), 'Existing resources changed')
    proof, polish = m.load(PROOF / 'RESULT.json'), m.load(UI / 'hint-icon-verification.json')
    m.require(proof['source_sha256'] == m.sha(ROOT / 'qemu/hw/misc/p2d-devemu-import.c') and proof['tests_sha256'] == m.sha(ROOT / 'tests/test_network_setup_files.py'), 'Hidden acceptance source changed')
    m.require(polish['source_sha256'] == m.sha(HERE / 'src/com/samsixx/pocket2droid/RomSettingsActivity.java') and polish['icon_sha256'] == m.sha(HERE / 'res/drawable/storage_card_warning.xml'), 'Accepted UI polish changed')
    for name, count in (('green.log', 11), ('native-suite.log', 182)):
        text = (PROOF / name).read_text()
        m.require(('Ran ' + str(count) + ' tests') in text and '\nOK\n' in text, 'Native acceptance missing: ' + name)
    guest = m.load(PROOF / 'guest/result.json')
    m.require(guest['automatic_query_output'] and guest['rom_unchanged'] and guest['marker_unchanged'] and not guest['real_card_has_helper'] and guest['exit_code'] == 0, 'Disposable guest acceptance failed')
    m.require(proof['bionic_sha256'] == native['binary_sha256'] == m.sha(BUILD / 'libp2dengine-bionic.so'), 'Accepted Bionic engine changed')
    libraries = {name: row['sha256'] for name, row in runtime['files'].items()}
    libraries['libp2dstorage.so'] = storage['binary_sha256']
    for name, expected in libraries.items():
        file = BUILD / ('storage-runtime' if name == 'libp2dstorage.so' else 'runtime') / name
        m.require(m.sha(file) == expected, 'Native payload differs')
        loads = [line for line in subprocess.check_output(['readelf', '-lW', str(file)], text=True).splitlines() if 'LOAD ' in line]
        m.require(loads and all(int(line.split()[-1], 16) >= 16384 for line in loads), 'ELF alignment failed')
    apk = Path(app['signed_apk'])
    m.require(app['version'] == VERSION and app['package'] == 'com.samsixx.pocket2droid' and not app['test_only'] and app['apk_sha256'] == m.sha(apk), 'APK identity differs')
    signature = m.validate_apk(apk, 'com.samsixx.pocket2droid', False, libraries, m.sha(BUILD / 'dex/classes.dex'))
    manifest = m.parse_manifest(apk)
    m.require(not manifest.get('instrumentation') and not manifest.get('provider'), 'Test fixtures packaged')
    with zipfile.ZipFile(old_apk) as old, zipfile.ZipFile(apk) as current:
        assets = lambda z: {n: digest(z.read(n)) for n in z.namelist() if n.startswith('assets/')}
        m.require(assets(old) == assets(current), 'Helper or assets changed')
        old_libs = {n: digest(old.read(n)) for n in old.namelist() if n.startswith('lib/')}
        new_libs = {n: digest(current.read(n)) for n in current.namelist() if n.startswith('lib/')}
        m.require(old_libs.keys() == new_libs.keys() and [n for n in old_libs if old_libs[n] != new_libs[n]] == ['lib/arm64-v8a/libp2dengine.so'], 'Unexpected native payload changes')
        dex = current.read('classes.dex')
        m.require(b'Tap to change the StorageCard location for this ROM.' in dex and b'storage_card_warning' in dex, 'UI polish missing from DEX')
        m.require(b'Lcom/samsixx/pocket2droid/StorageCardUiTest;' not in dex, 'Instrumentation compiled into app')
    vector = subprocess.check_output([str(m.SDK / 'aapt2'), 'dump', 'xmltree', str(apk), '--file', 'res/drawable/storage_card_warning.xml'], text=True)
    m.require('ffd32f2f' in vector.lower() and 'ffffffff' in vector.lower(), 'Red/white vector colors missing')
    stage = Path(tempfile.mkdtemp(prefix='.seal-hidden-storage-', dir=release.parent))
    try:
        delivered = stage / ('Pocket2Droid-v' + VERSION + '-Hidden-Helper-StorageCard.apk')
        shutil.copy2(apk, delivered)
        source = stage / ('Pocket2Droid-v' + VERSION + '.Source.zip')
        print('Signature, package, three requested changes and16KiB alignment verified; archiving source.', flush=True)
        inventory = snapshot(source, native, runtime, old_source)
        for name, expected in tested.items():
            m.require(inventory['android/' + name] == expected, 'Frontend snapshot differs')
        for name, expected in native['source']['paths'].items():
            m.require(inventory['qemu-canonical-changes/' + name] == expected, 'Canonical snapshot differs')
        for name, expected in native['runtime_source_hashes'].items():
            m.require(inventory['qemu-android-exact/' + name] == expected, 'Compiled snapshot differs')
        with zipfile.ZipFile(source) as archive:
            m.require(archive.read('README.md') == readme, 'README changed')
            m.require(digest(archive.read('android/res/drawable/storage_card_warning.xml')) == polish['icon_sha256'], 'Icon snapshot differs')
        for name in ('candidate-build.json', 'bionic-engine.json', 'runtime.json', 'bionic-tools.json', 'storage-runtime.json'):
            shutil.copy2(BUILD / name, stage / name)
        shutil.copy2(Path(__file__), stage / 'candidate-release-recipe.py')
        (stage / 'candidate-signature.txt').write_text(signature)
        (stage / 'warning-vector.txt').write_text(vector)
        evidence = stage / 'evidence'
        evidence.mkdir()
        for name in ('RESULT.json', 'source.diff', 'review.txt', 'red.log', 'green.log', 'native-suite.log', 'android-native.log', 'runtime.log', 'guest.log'):
            shutil.copy2(PROOF / name, evidence / name)
        shutil.copy2(PROOF / 'guest/result.json', evidence / 'disposable-guest-result.json')
        shutil.copy2(UI / 'hint-icon-verification.json', evidence / 'ui-polish-verification.json')
        record = dict(version=VERSION, version_code=CODE, package=app['package'], apk_sha256=m.sha(delivered), source_archive_sha256=m.sha(source), source_snapshot_files=len(inventory), original_signer=m.SIGNER,
                      signature_verified=True, apk_and_elf_alignment_16k=True, exact_native_and_dex_identity=True, changed_native_sources=changed_native, changed_product_java_files=changed_java,
                      hidden_virtual_2577=True, diagnostic_autorun_guest_verified=True, storage_card_hint_in_dex=True, red_warning_vector_verified=True, helper_assets_unchanged=True,
                      overlay_tests=11, native_tests=182, earlier_card_ui_checks_reused=36, ui_polish_runtime_test_rerun=False, phone_validation_pending=True,
                      readme_unchanged=True, phone_accessed=False, earlier_release_preserved=True, github_modified=False, build_seconds=app['seconds'])
        (stage / 'FINAL_VERIFICATION.json').write_text(json.dumps(record, indent=2) + '\n')
        (stage / 'INSTALL.txt').write_text(
            'Pocket2Droid1.0.2-test10/code681.\n'
            'Exit the current ROM normally, then install as an update. Do not uninstall or clear data.\n'
            'Check ROM settings: StorageCard path shows the tap-to-change hint.\n'
            'Tap it: the warning triangle should be red; Cancel preserves the current folder.\n'
            'With Internet On, start the ROM and check Storage Card in guest File Explorer.\n'
            'Virtual2577 should be hidden in the normal view, and Internet should still work.\n'
            'Show all files can reveal it. A real user2577 is left unchanged.\n'
            'Use http://google.com/ for a familiar browser check; modern HTTPS remains ROM-dependent.\n'
            'No reset/reimport or file moves needed. PC tests pass; phone validation is pending.\n')
        m.require(protected == {p.relative_to(prior).as_posix(): m.sha(p) for p in prior.rglob('*') if p.is_file()}, 'Test9 changed')
        (stage / 'SHA256SUMS.txt').write_text(''.join(m.sha(p) + '  ' + p.relative_to(stage).as_posix() + '\n' for p in sorted(stage.rglob('*')) if p.is_file()))
        m.publish_release(stage, release)
        print(json.dumps(dict(apk=str(release / delivered.name), **record), indent=2), flush=True)
    finally:
        if stage.exists():
            m.require(stage.parent.resolve() == release.parent.resolve() and stage.name.startswith('.seal-hidden-storage-'), 'Unsafe stage cleanup')
            shutil.rmtree(stage)


if __name__ == '__main__':
    main()
