"""Seal the authorized V6.63 frontend release without changing the V6.62 engine."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
B = HERE / 'build'
P = HERE.parents[2]
spec = importlib.util.spec_from_file_location('integrity', HERE / 'finalize_release.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.VERSION, m.VERSION_CODE = '6.63', 663


def main():
    previous, release = P / 'apk/6.62', P / 'apk/6.63'
    m.require(not release.exists(), 'Never overwrite an existing release')
    baseline = {str(p.relative_to(previous)): m.sha(p) for p in previous.rglob('*') if p.is_file()}
    for line in (previous / 'SHA256SUMS.txt').read_text().splitlines():
        digest, name = line.split('  ', 1)
        m.require(baseline[name] == digest, 'Protected baseline changed: ' + name)
    app, native, runtime, storage = (m.load(B / n) for n in
        ('candidate-build.json', 'bionic-engine.json', 'runtime.json', 'storage-runtime.json'))
    apk = Path(app['signed_apk'])
    m.require(app['version'] == m.VERSION and app['test_only'] is False
              and m.sha(apk) == app['apk_sha256'], 'Wrong or changed candidate')
    for name, record in (('bionic-engine.json', native), ('runtime.json', runtime), ('storage-runtime.json', storage)):
        m.require(record == m.load(previous / name), 'Native/runtime changes are outside this release: ' + name)
    for name, digest in native['source']['paths'].items():
        m.require(m.sha(HERE.parent / 'qemu' / name) == digest, 'Canonical native source changed: ' + name)
    for name, digest in native['runtime_source_hashes'].items():
        m.require(m.sha(m.NATIVE / name) == digest, 'Compiled native source changed: ' + name)
    m.require(native['builder_sha256'] == m.sha(HERE / 'build_bionic.py')
              and native['binary_sha256'] == m.sha(B / 'libp2dengine-bionic.so'), 'Native build identity changed')
    libraries = {name: record['sha256'] for name, record in runtime['files'].items()}
    libraries['libp2dstorage.so'] = storage['binary_sha256']
    signature = m.validate_apk(apk, 'com.samsixx.wm6android', False, libraries, m.sha(B / 'dex/classes.dex'))
    for name in libraries:
        path = B / ('storage-runtime' if name == 'libp2dstorage.so' else 'runtime') / name
        m.require(m.sha(path) == libraries[name], 'Runtime binary changed: ' + name)
        loads = [line for line in subprocess.check_output(['readelf', '-lW', str(path)], text=True).splitlines() if 'LOAD ' in line]
        m.require(loads and all(int(line.split()[-1], 16) >= 16384 for line in loads), 'ELF load alignment invalid: ' + name)
    badging = subprocess.check_output([str(m.SDK / 'aapt2'), 'dump', 'badging', str(apk)], text=True)
    m.require("application-label:'Pocket2Droid'" in badging and "application: label='Pocket2Droid'" in badging,
              'App name must be Pocket2Droid without a version suffix')
    checks = {'v663-host.log': ('PASS ROM repository 71', 'PASS ROM settings/geometry 39'),
              'v663-fallback.log': ('PASS ROM repository 71', 'PASS ROM settings/geometry 39')}
    for name, markers in checks.items():
        text = (B / 'library-tests' / name).read_text()
        m.require(all(marker in text for marker in markers), 'Focused verification failed: ' + name)
    tested = m.tested_source_hashes()
    with zipfile.ZipFile(previous / 'Pocket2Droid-V6.62-UI-Fixes-TCG-Source.zip') as z:
        old = m.load(previous / 'evidence/tested-sources-v662.json')
        m.require(set(tested) == set(old), 'Unexpected Android source file addition/removal')
        changes = {name for name, digest in tested.items() if digest != old[name]}
        m.require(changes == {'AndroidManifest.xml', 'src/com/samsixx/wm6android/RomRepository.java',
                             'src/com/samsixx/wm6android/RomSettings.java', 'src/com/samsixx/wm6android/RomSettingsActivity.java'},
                  'Unexpected frontend source changes: ' + str(changes))
    artwork = m.load(B / 'library-tests/user-artwork-verification.json')
    m.require(len(artwork) == 7, 'Expected six ROM icons and one app icon')
    with zipfile.ZipFile(apk) as z, zipfile.ZipFile(B / 'library-tests/user-artwork-resources.apk') as reference:
        m.require({n for n in z.namelist() if n.startswith('assets/')} == {'assets/QEMU-COPYING.txt'}, 'Unexpected ROM/game/save assets')
        expected_pngs = set()
        for row in artwork:
            source = P / row['source'].replace('\\', '/')
            directory = 'drawable' if row['resource'] == 'pocket2droid_icon.png' else 'drawable-nodpi'
            resource = HERE / 'res' / directory / row['resource']
            compiled_directory = 'drawable' if directory == 'drawable' else 'drawable-nodpi-v4'
            entry = 'res/' + compiled_directory + '/' + row['resource']
            expected_pngs.add(entry)
            m.require(m.sha(source) == row['sha256'] == m.sha(resource), 'Supplied artwork changed: ' + row['resource'])
            m.require(row['compiled_pixels_identical'] and z.read(entry) == reference.read(entry), 'APK artwork differs from pixel-verified resource: ' + entry)
            row['apk_entry'] = entry
            row['apk_resource_sha256'] = hashlib.sha256(z.read(entry)).hexdigest()
        m.require({n for n in z.namelist() if n.startswith('res/') and n.endswith('.png')} == expected_pngs, 'Unexpected or stale APK artwork')
    stage = Path(tempfile.mkdtemp(prefix='.seal-6.63-', dir=release.parent))
    try:
        delivered = stage / 'Pocket2Droid-V6.63-ROM-Library-TCG-SIGNED.apk'
        shutil.copy2(apk, delivered)
        source = stage / 'Pocket2Droid-V6.63-ROM-Library-TCG-Source.zip'
        print('APK verified; archiving exact source and release evidence.', flush=True)
        inventory = m.snapshot_sources(source, {'native': native, 'runtime': runtime})
        with zipfile.ZipFile(source) as z:
            for name, digest in inventory.items():
                m.require(hashlib.sha256(z.read(name)).hexdigest() == digest, 'Archive identity mismatch: ' + name)
            for name, digest in tested.items():
                m.require(inventory['android/' + name] == digest, 'Verified source/archive mismatch: ' + name)
            m.require(inventory['android/build.py'] == m.sha(HERE / 'build.py'), 'Build recipe archive mismatch')
            for row in artwork:
                directory = 'drawable' if row['resource'] == 'pocket2droid_icon.png' else 'drawable-nodpi'
                m.require(inventory['android/res/' + directory + '/' + row['resource']] == row['sha256'], 'Artwork archive mismatch')
        for name in ('candidate-build.json', 'bionic-engine.json', 'runtime.json', 'bionic-tools.json', 'storage-runtime.json'):
            shutil.copy2(B / name, stage / name)
        shutil.copy2(Path(__file__), stage / 'candidate-release-recipe.py')
        (stage / 'candidate-signature.txt').write_text(signature)
        evidence = stage / 'evidence'
        evidence.mkdir()
        for name in (*checks, 'v663-build.log', 'user-icons-red.log', 'filename-resolution-suffix-red.log'):
            shutil.copy2(B / 'library-tests' / name, evidence / name)
        (evidence / 'tested-sources-v663.json').write_text(json.dumps(tested, indent=2) + '\n')
        (evidence / 'packaged-artwork.json').write_text(json.dumps(artwork, indent=2) + '\n')
        (evidence / 'application-badging.txt').write_text(badging)
        verification = dict(version=m.VERSION, version_code=m.VERSION_CODE, app_name='Pocket2Droid',
            apk_sha256=m.sha(delivered), original_signer=m.SIGNER, signature_verified=True,
            apk_and_elf_alignment_16k=True, exact_dex_and_native_identity=True,
            native_engine_unchanged_from='6.62', baseline_preserved=True,
            source_archive_sha256=m.sha(source), source_snapshot_files=len(inventory),
            six_supplied_rom_icons=True, supplied_app_icon=True, compiled_artwork_pixels_identical=True,
            repository_assertions=71, settings_geometry_assertions=39, storage_fallback_tested=True,
            concrete_resolution_presets=True, rom_default_hidden=True, physical_phone_test_pending=True,
            phone_modified=False, performance_gain_claimed=False)
        (stage / 'FINAL_VERIFICATION.json').write_text(json.dumps(verification, indent=2) + '\n')
        (stage / 'INSTALL.txt').write_text(
            'Install V6.63 as an update after normal EXIT. Keep existing app data; do not uninstall or clear data.\n'
            'App name: Pocket2Droid. Version metadata: 6.63 (663). Original package and signer retained.\n'
            'Your PD monogram is the launcher icon. Six supplied ROM icons are assigned to new ROMs without repeating the last assignment. Existing icon IDs remain compatible.\n'
            'New/discovered ROMs select a concrete resolution preset from known SDK filenames. Resolution annotations and import collision suffixes are accepted. Unknown names use QVGA 240x320; select another preset if needed.\n'
            'ROM default is removed from the dropdown. Old automatic profiles resolve to a concrete preset; existing explicit resolution settings are preserved.\n'
            'No ROM, CAB, game, or user save is bundled. Native engine, audio and storage helper are identical to V6.62; no performance gain is claimed.\n'
            'ARM64 Android 7.0+ (API24) is required. Current changes passed local profile/geometry and fallback checks; physical-phone UI/boot verification of this APK remains pending.\n')
        m.require(baseline == {str(p.relative_to(previous)): m.sha(p) for p in previous.rglob('*') if p.is_file()}, 'Baseline changed')
        m.require(m.sha(delivered) == app['apk_sha256'], 'Delivered APK changed')
        files = sorted(p for p in stage.rglob('*') if p.is_file())
        (stage / 'SHA256SUMS.txt').write_text(''.join(m.sha(p) + '  ' + str(p.relative_to(stage)) + '\n' for p in files))
        m.publish_release(stage, release)
        print(json.dumps(dict(apk=str(release / delivered.name), sha256=app['apk_sha256'],
              version=m.VERSION, app_name='Pocket2Droid', original_signer=True, baseline_preserved=True)), flush=True)
    finally:
        if stage.exists():
            m.require(stage.parent.resolve() == release.parent.resolve() and stage.name.startswith('.seal-6.63-'), 'Unsafe cleanup')
            shutil.rmtree(stage)


if __name__ == '__main__':
    main()
