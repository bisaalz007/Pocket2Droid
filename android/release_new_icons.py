"""Seal the authorized V6.64 artwork update; preserve the V6.63 runtime."""
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
m.VERSION, m.VERSION_CODE = '6.64', 664


def main():
    previous, release = P / 'apk/6.63', P / 'apk/6.64'
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
        m.require(record == m.load(previous / name), 'Unexpected runtime change: ' + name)
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
        m.require(loads and all(int(line.split()[-1], 16) >= 16384 for line in loads), 'ELF alignment invalid: ' + name)
    badging = subprocess.check_output([str(m.SDK / 'aapt2'), 'dump', 'badging', str(apk)], text=True)
    m.require("application-label:'Pocket2Droid'" in badging and "application: label='Pocket2Droid'" in badging,
              'App name must be Pocket2Droid without a version suffix')
    checks = {'v664-host.log': ('PASS ROM repository 71', 'PASS ROM settings/geometry 39'),
              'v664-fallback.log': ('PASS ROM repository 71', 'PASS ROM settings/geometry 39')}
    for name, markers in checks.items():
        text = (B / 'library-tests' / name).read_text()
        m.require(all(marker in text for marker in markers), 'Focused verification failed: ' + name)
    tested = m.tested_source_hashes()
    old = m.load(previous / 'evidence/tested-sources-v663.json')
    m.require(set(tested) == set(old), 'Unexpected source addition/removal')
    m.require({n for n in tested if tested[n] != old[n]} == {'AndroidManifest.xml'}, 'Unexpected code changes')
    artwork_proof = m.load(B / 'library-tests/v664-packaged-artwork.json')
    artwork = artwork_proof['artwork']
    m.require(artwork_proof['apk_sha256'] == app['apk_sha256'] and len(artwork) == 7,
              'Pixel proof must identify this APK and all seven supplied icons')
    expected = {'rom_icon_' + n + '.png' for n in ('blue', 'teal', 'amber', 'violet', 'orange', 'red')}
    expected.add('pocket2droid_icon.png')
    m.require({r['resource'] for r in artwork} == expected, 'Wrong artwork inventory')
    with zipfile.ZipFile(apk) as z, zipfile.ZipFile(previous / 'Pocket2Droid-V6.63-ROM-Library-TCG-SIGNED.apk') as old_apk:
        m.require(z.read('classes.dex') == old_apk.read('classes.dex'), 'Compiled Java changed from V6.63')
        m.require({n for n in z.namelist() if n.startswith('assets/')} == {'assets/QEMU-COPYING.txt'}, 'Unexpected ROM/game/save assets')
        for row in artwork:
            directory = 'drawable' if row['resource'] == 'pocket2droid_icon.png' else 'drawable-nodpi'
            source, resource = P / row['source'], HERE / 'res' / directory / row['resource']
            m.require(m.sha(source) == row['sha256'] == m.sha(resource), 'Supplied artwork changed')
            m.require(row['compiled_rgba_pixels_identical'] is True
                      and hashlib.sha256(z.read(row['apk_entry'])).hexdigest() == row['apk_resource_sha256'], 'APK artwork changed since pixel verification')
            if directory == 'drawable':
                m.require(z.read(row['apk_entry']) == old_apk.read(row['apk_entry']), 'Launcher icon changed')
            else:
                m.require(row['source'].startswith('assets/new/') and row['size'] == [192, 192], 'Wrong replacement ROM icon')
        m.require({n for n in z.namelist() if n.startswith('res/') and n.endswith('.png')}
                  == {r['apk_entry'] for r in artwork}, 'Unexpected or stale APK artwork')
    stage = Path(tempfile.mkdtemp(prefix='.seal-6.64-', dir=release.parent))
    try:
        delivered = stage / 'Pocket2Droid-V6.64-New-ROM-Icons-TCG-SIGNED.apk'
        shutil.copy2(apk, delivered)
        source = stage / 'Pocket2Droid-V6.64-New-ROM-Icons-TCG-Source.zip'
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
        for name in (*checks, 'v664-build.log', 'v664-packaged-artwork.json'):
            shutil.copy2(B / 'library-tests' / name, evidence / name)
        (evidence / 'tested-sources-v664.json').write_text(json.dumps(tested, indent=2) + '\n')
        (evidence / 'application-badging.txt').write_text(badging)
        verification = dict(version=m.VERSION, version_code=m.VERSION_CODE, app_name='Pocket2Droid',
            apk_sha256=m.sha(delivered), original_signer=m.SIGNER, signature_verified=True,
            apk_and_elf_alignment_16k=True, exact_dex_and_native_identity=True,
            native_engine_unchanged_from='6.63', java_code_unchanged_from='6.63', baseline_preserved=True,
            source_archive_sha256=m.sha(source), source_snapshot_files=len(inventory),
            six_replacement_rom_icons=True, supplied_app_icon_unchanged=True, compiled_artwork_pixels_identical=True,
            repository_assertions=71, settings_geometry_assertions=39, storage_fallback_tested=True,
            existing_icon_ids_preserved=True, physical_phone_test_pending=True,
            phone_modified=False, performance_gain_claimed=False)
        (stage / 'FINAL_VERIFICATION.json').write_text(json.dumps(verification, indent=2) + '\n')
        (stage / 'INSTALL.txt').write_text(
            'Install V6.64 as an update after normal EXIT. Keep existing app data; do not uninstall or clear data.\n'
            'App name: Pocket2Droid. Version metadata: 6.64 (664). Original package and signer retained.\n'
            'Six replacement icons from assets/new are included. Existing ROM icon IDs remain compatible, and new ROMs avoid repeating the last assigned icon.\n'
            'The supplied PD monogram launcher icon is unchanged.\n'
            'No ROM, CAB, game, or user save is bundled. Java code, native engine, audio and storage helper are identical to V6.63; no performance gain is claimed.\n'
            'ARM64 Android 7.0+ (API24) is required. Local profile/geometry and fallback checks pass; physical-phone UI/boot verification remains pending.\n')
        m.require(baseline == {str(p.relative_to(previous)): m.sha(p) for p in previous.rglob('*') if p.is_file()}, 'Baseline changed')
        m.require(m.sha(delivered) == app['apk_sha256'], 'Delivered APK changed')
        files = sorted(p for p in stage.rglob('*') if p.is_file())
        (stage / 'SHA256SUMS.txt').write_text(''.join(m.sha(p) + '  ' + str(p.relative_to(stage)) + '\n' for p in files))
        m.publish_release(stage, release)
        print(json.dumps(dict(apk=str(release / delivered.name), sha256=app['apk_sha256'],
              version=m.VERSION, app_name='Pocket2Droid', original_signer=True, baseline_preserved=True)), flush=True)
    finally:
        if stage.exists():
            m.require(stage.parent.resolve() == release.parent.resolve() and stage.name.startswith('.seal-6.64-'), 'Unsafe cleanup')
            shutil.rmtree(stage)


if __name__ == '__main__':
    main()
