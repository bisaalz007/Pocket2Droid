"""Seal the authorized samsixx package rename; preserve the original v1.0 release."""
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
PROJECT = HERE.parents[2]
PACKAGE = 'com.samsixx.pocket2droid'
spec = importlib.util.spec_from_file_location('integrity', HERE / 'finalize_release.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.VERSION, m.VERSION_CODE = '1.0', 669


def main():
    previous, release = PROJECT / 'apk/1.0', PROJECT / 'apk/1.0-samsixx'
    review = PROJECT / 'GITHUB_PREVIEW/Pocket2Droid'
    m.require(not release.exists(), 'Never overwrite an existing release')
    protected = {p.relative_to(previous).as_posix(): m.sha(p) for p in previous.rglob('*') if p.is_file()}
    for line in (previous / 'SHA256SUMS.txt').read_text().splitlines():
        digest, name = line.split('  ', 1)
        m.require(protected[name] == digest, 'Original release changed: ' + name)
    app, native, runtime, storage = (m.load(B / n) for n in ('candidate-build.json', 'bionic-engine.json', 'runtime.json', 'storage-runtime.json'))
    apk = Path(app['signed_apk'])
    m.require(apk.parent.resolve() == B.resolve() and app['package'] == PACKAGE and app['version'] == '1.0'
              and not app['test_only'] and m.sha(apk) == app['apk_sha256'], 'Wrong signed candidate')
    m.require(native == m.load(previous / 'bionic-engine.json'), 'Emulator engine changed')
    m.require(runtime == m.load(previous / 'runtime.json'), 'Emulator runtime changed')
    for name, digest in native['source']['paths'].items():
        m.require(m.sha(HERE.parent / 'qemu' / name) == digest, 'Canonical engine source changed: ' + name)
    for name, digest in native['runtime_source_hashes'].items():
        m.require(m.sha(m.NATIVE / name) == digest, 'Adapted engine source changed: ' + name)
    m.require(m.sha(HERE / 'build_storage.py') == storage['builder_sha256'], 'Storage builder changed')
    for name, digest in storage['sources'].items():
        m.require(m.sha(HERE / name) == digest, 'Storage record differs from source')
    java = sorted((HERE / 'src').rglob('*.java'))
    with zipfile.ZipFile(previous / 'Pocket2Droid-v1.0-Source.zip') as old:
        m.require(len(java) == 42, 'Unexpected frontend file count')
        for path in java:
            old_name = ('android/' + path.relative_to(HERE).as_posix()).replace('com/samsixx/', 'com/samthedev/')
            expected = old.read(old_name).replace(b'com.samthedev', b'com.samsixx')
            m.require(path.read_bytes() == expected, 'Frontend differs beyond package rename: ' + path.name)
        expected = old.read('android/native/storage_publish.c').replace(b'com_samthedev', b'com_samsixx')
        m.require((HERE / 'native/storage_publish.c').read_bytes() == expected, 'Storage behavior changed beyond JNI names')
    library = B / 'storage-runtime/libp2dstorage.so'
    m.require(m.sha(library) == storage['binary_sha256'], 'Storage binary differs from record')
    symbols = subprocess.check_output(['nm', '-D', '--defined-only', str(library)], text=True)
    exports = {line.split()[-1] for line in symbols.splitlines() if 'Java_' in line}
    m.require(exports == {'Java_com_samsixx_pocket2droid_StoragePublish_' + n
                         for n in ('publishNoReplace', 'copyNoReplace', 'syncDirectoryPath')}, 'JNI exports do not match renamed Java')
    libraries = {name: row['sha256'] for name, row in runtime['files'].items()}
    libraries['libp2dstorage.so'] = storage['binary_sha256']
    for name, digest in libraries.items():
        path = B / ('storage-runtime' if name == 'libp2dstorage.so' else 'runtime') / name
        m.require(m.sha(path) == digest, 'Runtime binary differs: ' + name)
        loads = [line for line in subprocess.check_output(['readelf', '-lW', str(path)], text=True).splitlines() if 'LOAD ' in line]
        m.require(loads and all(int(line.split()[-1], 16) >= 16384 for line in loads), 'ELF alignment failed: ' + name)
    signature = m.validate_apk(apk, PACKAGE, False, libraries, m.sha(B / 'dex/classes.dex'))
    manifest = m.parse_manifest(apk)
    m.require({a['name'] for a in manifest.get('activity', [])} == {PACKAGE + '.' + n for n in
              ('MainActivity', 'AppSettingsActivity', 'RomSettingsActivity', 'ButtonMappingActivity', 'EmulatorActivity')}, 'Unexpected activities')
    m.require(not manifest.get('instrumentation') and not manifest.get('provider'), 'Test components packaged')
    artwork = m.load(B / 'release-v1.0/artwork.json')
    m.require(artwork['apk_sha256'] == m.sha(apk) and artwork['png_visible_pixels_identical'] == 47
              and artwork['original_gif_verified'] and artwork['no_stale_resources'], 'Artwork evidence stale')
    with zipfile.ZipFile(apk) as z:
        for row in artwork['resources']:
            m.require(m.sha(HERE / row['resource']) == row['source_sha256']
                      and hashlib.sha256(z.read(row['apk_entry'])).hexdigest() == row['apk_sha256'], 'Artwork changed')
        dex = z.read('classes.dex')
        m.require(b'Lcom/samsixx/pocket2droid/MainActivity;' in dex and b'com/samthedev/' not in dex, 'Stale Java classes in APK')
        m.require({n for n in z.namelist() if n.startswith('assets/')} == {'assets/QEMU-COPYING.txt'}, 'Unexpected bundled data')
    markers = {'repository': ('PASS ROM repository 122', 'PASS ROM settings/geometry 71', '120 control geometry/input'),
               'repository-fallback': ('PASS ROM repository 122', 'PASS ROM settings/geometry 71', '120 control geometry/input'),
               'storage': ('PASS StorageLayout 51',), 'storage-fallback': ('PASS StorageFallback 28',),
               'mapping': ('GuestKey: 25', 'ButtonBindings: 24', 'InputNormalizer: 37', 'MappedInputState: 13', 'MappingCapture: 19'),
               'loading': ('Rom boot state: 15',), 'audio': ('PASS actual audio protocol', 'PASS actual pump', 'PASS session')}
    for name, required in markers.items():
        log = (B / 'package-rename' / (name + '.log')).read_text()
        m.require(all(marker in log for marker in required) and 'Traceback' not in log and 'FAIL ' not in log, 'Missing test evidence: ' + name)
    stage = Path(tempfile.mkdtemp(prefix='.seal-1.0-samsixx-', dir=release.parent))
    try:
        delivered = stage / 'Pocket2Droid-v1.0-com.samsixx-SIGNED.apk'
        shutil.copy2(apk, delivered)
        source = stage / 'Pocket2Droid-v1.0-com.samsixx-Source.zip'
        raw = stage / 'source-app.tmp.zip'
        inventory = m.snapshot_sources(raw, {'native': native, 'runtime': runtime})
        with zipfile.ZipFile(raw) as original, zipfile.ZipFile(source, 'w', zipfile.ZIP_DEFLATED, compresslevel=4) as z:
            for info in original.infolist():
                if info.filename != 'SOURCE_SHA256.json':
                    z.writestr(info, original.read(info))
            additions = [review / n for n in ('README.md', 'BUILDING.md', '.gitignore', '.gitattributes', 'LICENSE', 'THIRD_PARTY.md')]
            for folder in ('android/dependency-sources', 'android/dependency-licenses'):
                additions.extend(p for p in (review / folder).rglob('*') if p.is_file())
            for path in sorted(additions):
                name = path.relative_to(review).as_posix()
                if name in inventory:
                    m.require(inventory[name] == m.sha(path), 'Supplement conflicts with existing source: ' + name)
                else:
                    m.write_archive_file(z, path, name, inventory)
            z.writestr('SOURCE_SHA256.json', json.dumps(inventory, indent=2) + '\n')
        raw.unlink()
        with zipfile.ZipFile(source) as z:
            m.require(z.testzip() is None and len(z.namelist()) == len(set(z.namelist())), 'Invalid source archive')
            for name, digest in inventory.items():
                m.require(hashlib.sha256(z.read(name)).hexdigest() == digest, 'Source archive mismatch: ' + name)
            for name, digest in m.tested_source_hashes().items():
                m.require(inventory['android/' + name] == digest, 'Compiled source/archive mismatch: ' + name)
        for name in ('candidate-build.json', 'bionic-engine.json', 'runtime.json', 'bionic-tools.json', 'storage-runtime.json'):
            shutil.copy2(B / name, stage / name)
        shutil.copy2(Path(__file__), stage / 'candidate-release-recipe.py')
        (stage / 'candidate-signature.txt').write_text(signature)
        evidence = stage / 'evidence'
        evidence.mkdir()
        for path in (B / 'package-rename').glob('*.log'):
            shutil.copy2(path, evidence / path.name)
        shutil.copy2(B / 'release-v1.0/artwork.json', evidence / 'artwork.json')
        verification = dict(version='1.0', version_code=669, package=PACKAGE, app_name='Pocket2Droid',
                            apk_sha256=m.sha(delivered), source_archive_sha256=m.sha(source), source_snapshot_files=len(inventory),
                            original_signer=m.SIGNER, signature_verified=True, apk_and_elf_alignment_16k=True,
                            java_changes_package_only=42, storage_changes_jni_names_only=True, jni_exports_verified=3,
                            emulator_engine_and_runtime_unchanged=True, png_visible_pixel_identity=47, original_animated_gif=True,
                            dependency_sources_and_notices_included=True, baseline_preserved=True,
                            phone_modified=False, physical_phone_test_pending=True, github_modified=False,
                            build_portability_verified=False, complete_distribution_review=False)
        (stage / 'FINAL_VERIFICATION.json').write_text(json.dumps(verification, indent=2) + '\n')
        (stage / 'INSTALL.txt').write_text('Pocket2Droid 1.0, internal code669, ARM64 Android7+.\n'
            'Package com.samsixx.pocket2droid; original signing certificate.\n'
            'This is a separate app from the prior com.samthedev.pocket2droid package; no uninstall is required.\n'
            'Exit the prior app normally before starting this app: they use the same pocket2droid external folders.\n'
            'Grant storage access when requested. ROM/saves/StorageCard paths are unchanged; app-private settings do not migrate automatically.\n'
            'Do not clear data, reset the guest or run both packages together. No phone installation or phone validation performed.\n')
        m.require(protected == {p.relative_to(previous).as_posix(): m.sha(p) for p in previous.rglob('*') if p.is_file()}, 'Original v1.0 release changed')
        (stage / 'SHA256SUMS.txt').write_text(''.join(m.sha(p) + '  ' + p.relative_to(stage).as_posix() + '\n'
                                                   for p in sorted(stage.rglob('*')) if p.is_file()))
        m.publish_release(stage, release)
        print(json.dumps(dict(apk=str(release / delivered.name), **verification)), flush=True)
    finally:
        if stage.exists():
            m.require(stage.parent.resolve() == release.parent.resolve() and stage.name.startswith('.seal-1.0-samsixx-'), 'Unsafe staging cleanup')
            shutil.rmtree(stage)


if __name__ == '__main__':
    main()
