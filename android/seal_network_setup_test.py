"""Seal test5 automatic-network-setup APK from current source acceptance."""
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
VERSION, CODE = '1.0.2-test5', 676
spec = importlib.util.spec_from_file_location('setup_integrity', HERE / 'finalize_release.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.VERSION, m.VERSION_CODE = VERSION, CODE
PROOF = BUILD / 'network-setup'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def snapshot(target, native, runtime, previous):
    raw = target.with_name('.current-setup-source.zip')
    m.snapshot_sources(raw, {'native': native, 'runtime': runtime})
    inventory = {}
    skip = {'SOURCE_SHA256.json', 'NETWORK-TEST-BUILD.txt', 'WM5-TEST-BUILD.txt', 'NETWORK-SETUP-TEST-BUILD.txt'}
    with zipfile.ZipFile(raw) as current, zipfile.ZipFile(previous) as prior, zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=4) as final:
        for archive in (current, prior):
            for info in archive.infolist():
                name = info.filename
                if name in skip or name in inventory:
                    continue
                data = archive.read(info)
                final.writestr(info, data)
                inventory[name] = digest(data)
        query = ROOT / 'prototypes/network-setup/query_guest.c'
        m.write_archive_file(final, query, 'prototypes/network-setup/query_guest.c', inventory)
        note = (
            'Pocket2Droid ' + VERSION + ' / code' + str(CODE) + ' automatic Internet setup test\n'
            'Build entry: android/build.py; canonical overlay: qemu-canonical-changes/.\n'
            'Exact Bionic source: qemu-android-exact/. Existing WSL/NDK environment required.\n'
            'New profiles default Internet On. Recognized stock WM5/WM6 configuration gets\n'
            'a once-only direct Work-to-Internet route through the ARMv4 helper. Durable\n'
            'Attempt1 is separate from verified Version1 success; failures remain manual.\n'
            'Legacy/adopted saves preserve settings. Real StorageCard2577 wins; helper is\n'
            'virtual/read-only.179 native tests and Android frontend/ownership checks pass.\n'
            'WM6 Google HTTP and WM5 local HTTP passed on PC. Actual phone networking,\n'
            'modern TLS and WM5 public page rendering remain unverified.\n'
            'Source/dependency provenance, libslirp4.9.5 source/COPYRIGHT/patch included.\n'
            'No Microsoft SDK, ROM, game, save or signing key included.\n'
        ).encode('utf-8')
        final.writestr('NETWORK-SETUP-TEST-BUILD.txt', note)
        inventory['NETWORK-SETUP-TEST-BUILD.txt'] = digest(note)
        final.writestr('SOURCE_SHA256.json', json.dumps(inventory, indent=2) + '\n')
    raw.unlink()
    with zipfile.ZipFile(target) as z:
        m.require(z.testzip() is None, 'Source CRC failure')
        m.require(len(z.namelist()) == len(set(z.namelist())), 'Duplicate source entry')
        for name, expected in inventory.items():
            m.require(digest(z.read(name)) == expected, 'Source identity differs: ' + name)
    return inventory


def main():
    prior = PROJECT / 'apk/1.0.2-test4'
    release = PROJECT / 'apk' / VERSION
    m.require(not release.exists(), 'Never overwrite an existing release')
    protected = {p.relative_to(prior).as_posix(): m.sha(p) for p in prior.rglob('*') if p.is_file()}
    old_apk = prior / 'Pocket2Droid-v1.0.2-test4-Internet.apk'
    old_source = prior / 'Pocket2Droid-v1.0.2-test4.Source.zip'
    m.require(m.sha(old_apk) == 'cc3008afc15012f71f6a64527acb82b331a2be37cc6bbeab5e473f0a3674525e', 'Protected test4 APK changed')
    m.require(m.sha(old_source) == '452da6664a054f0ac0cbd280e8147780a16cb082a7947e668547adf44d1d8e0e', 'Protected test4 source changed')
    proof = m.load(PROOF / 'RESULT.json')
    m.require(proof['status'].startswith('local source integration complete'), 'Feature acceptance incomplete')
    for name, expected in proof['source_hashes'].items():
        data = (ROOT / name).read_bytes()
        if name == 'android/build.py':
            data = data.replace(b"VERSION = '1.0.2-test5'", b"VERSION = '1.0.2-test4'").replace(b'VERSION_CODE = 676', b'VERSION_CODE = 675')
        elif name == 'android/AndroidManifest.xml':
            data = data.replace(b'android:versionCode="676"', b'android:versionCode="675"').replace(b'android:versionName="1.0.2-test5"', b'android:versionName="1.0.2-test4"')
        m.require(digest(data) == expected, 'Source differs beyond release metadata: ' + name)
    for name, expected in proof['logs_sha256'].items():
        m.require(m.sha(PROOF / name) == expected, 'Accepted test evidence changed: ' + name)
    m.require(m.sha(PROOF / 'final-review.md') == proof['review_sha256'], 'Review identity changed')
    m.require(proof['review_disposition']['important'] == 1 and not proof['review_disposition']['deferred_minors'], 'Review disposition differs')
    for name, expected in (('native-post-review.log', 'Ran 179 tests'), ('android-ui-post-review.log', 'PASS 17 '), ('helper-final.log', 'Ran 7 tests')):
        m.require(expected in (PROOF / name).read_text(encoding='utf-8'), 'Required check missing: ' + name)
    m.require((PROOF / 'native-post-review.log').read_text(encoding='utf-8').rstrip().endswith('OK'), 'Native suite failed')
    for family in ('wm5', 'wm6'):
        initial, reopen = (proof['guests'][family + suffix] for suffix in ('-guard-initial', '-guard-reopen'))
        m.require(initial['helper_sha256'] == proof['helper']['executable_sha256'], 'Guest used a different helper')
        m.require(all(reopen[k] for k in ('attempt_guard_present', 'success_marker_1', 'work_internet_route_present', 'positive_google_dns', 'rom_unchanged')), 'Guest reopen failed')
    app, native, runtime, storage = (m.load(BUILD / n) for n in ('candidate-build.json', 'bionic-engine.json', 'runtime.json', 'storage-runtime.json'))
    m.require(native == proof['bionic_engine'] and runtime == proof['runtime'], 'Native acceptance identity differs')
    m.require(storage == m.load(prior / 'storage-runtime.json'), 'Storage helper changed')
    for name, expected in native['source']['paths'].items():
        m.require(m.sha(ROOT / 'qemu' / name) == expected, 'Native source changed: ' + name)
    for name, expected in native['runtime_source_hashes'].items():
        m.require(m.sha(m.NATIVE / name) == expected, 'Compiled native source changed: ' + name)
    libraries = {name: row['sha256'] for name, row in runtime['files'].items()}
    libraries['libp2dstorage.so'] = storage['binary_sha256']
    for name, expected in libraries.items():
        path = BUILD / ('storage-runtime' if name == 'libp2dstorage.so' else 'runtime') / name
        m.require(m.sha(path) == expected, 'Payload differs: ' + name)
        loads = [line for line in subprocess.check_output(['readelf', '-lW', str(path)], text=True).splitlines() if 'LOAD ' in line]
        m.require(loads and all(int(line.split()[-1], 16) >= 16384 for line in loads), 'ELF alignment failed')
    apk = Path(app['signed_apk'])
    m.require(app['version'] == VERSION and app['package'] == 'com.samsixx.pocket2droid' and not app['test_only'] and m.sha(apk) == app['apk_sha256'], 'Wrong candidate identity')
    signature = m.validate_apk(apk, app['package'], False, libraries, m.sha(BUILD / 'dex/classes.dex'))
    manifest = m.parse_manifest(apk)
    m.require(not manifest.get('instrumentation') and not manifest.get('provider'), 'Test fixtures packaged')
    permissions = {row['name'] for row in manifest['uses-permission']}
    m.require({'android.permission.INTERNET', 'android.permission.ACCESS_NETWORK_STATE'} <= permissions, 'Network permissions missing')
    with zipfile.ZipFile(old_apk) as old, zipfile.ZipFile(apk) as z:
        art = lambda a: {n: digest(a.read(n)) for n in a.namelist() if n.startswith('res/') or n == 'resources.arsc'}
        m.require(art(old) == art(z), 'Artwork/resources changed')
        expected_assets = {'assets/QEMU-COPYING.txt', 'assets/LIBSLIRP-COPYRIGHT.txt', 'assets/LIBSLIRP-NOTICE.txt', 'assets/network-setup/autorun.exe', 'assets/network-setup/manifest.json'}
        m.require({n for n in z.namelist() if n.startswith('assets/')} == expected_assets, 'Unexpected APK assets')
        m.require(digest(z.read('assets/network-setup/autorun.exe')) == proof['helper']['executable_sha256'], 'Packaged helper differs from guest-tested helper')
        m.require(json.loads(z.read('assets/network-setup/manifest.json')) == proof['helper'], 'Helper provenance differs')
        m.require(z.read('assets/LIBSLIRP-COPYRIGHT.txt') == (BUILD / 'networking/android/source/COPYRIGHT').read_bytes(), 'Dependency notice changed')
    stage = Path(tempfile.mkdtemp(prefix='.seal-network-setup-', dir=release.parent))
    try:
        delivered = stage / ('Pocket2Droid-v' + VERSION + '-Automatic-Internet.apk')
        shutil.copy2(apk, delivered)
        source = stage / ('Pocket2Droid-v' + VERSION + '.Source.zip')
        inventory = snapshot(source, native, runtime, old_source)
        for name, expected in m.tested_source_hashes().items():
            m.require(inventory['android/' + name] == expected, 'Archived frontend differs: ' + name)
        for name, expected in native['source']['paths'].items():
            m.require(inventory['qemu-canonical-changes/' + name] == expected, 'Archived native source differs: ' + name)
        for name, expected in native['runtime_source_hashes'].items():
            m.require(inventory['qemu-android-exact/' + name] == expected, 'Archived compiled source differs: ' + name)
        m.require(inventory['android/build/network-setup/production-helper/autorun.exe'] == proof['helper']['executable_sha256'], 'Archived helper differs')
        for name in ('candidate-build.json', 'bionic-engine.json', 'runtime.json', 'bionic-tools.json', 'storage-runtime.json'):
            shutil.copy2(BUILD / name, stage / name)
        shutil.copy2(Path(__file__), stage / 'candidate-release-recipe.py')
        (stage / 'candidate-signature.txt').write_text(signature, encoding='utf-8')
        shutil.copy2(BUILD / 'runtime/libp2dengine.so.unstripped', stage / 'libp2dengine.so.unstripped')
        evidence = stage / 'evidence'
        evidence.mkdir()
        for name in ('RESULT.json', 'progress.md', 'source-scope.diff', 'source-scope.json', 'final-review.md', 'native-post-review.log', 'helper-final.log', 'java-post-review.log', 'android-ui-post-review.log', 'review-guard-red.log', 'review-guard-green.log'):
            shutil.copy2(PROOF / name, evidence / name)
        record = dict(version=VERSION, version_code=CODE, package=app['package'], private_test_candidate=True,
                      apk_sha256=m.sha(delivered), source_archive_sha256=m.sha(source), source_snapshot_files=len(inventory),
                      original_signer=m.SIGNER, signature_verified=True, apk_and_elf_alignment_16k=True,
                      exact_dex_and_native_identity=True, guest_helper_sha256=proof['helper']['executable_sha256'],
                      native_tests=179, network_default='On for new profiles; existing settings preserved',
                      phone_validation_pending=True, phone_modified=False, test4_preserved=True,
                      wm5_public_http_unconfirmed=True, ipv6_only_dns_unsupported=True)
        (stage / 'FINAL_VERIFICATION.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        (stage / 'INSTALL.txt').write_text(
            'Pocket2Droid ' + VERSION + '/code' + str(CODE) + ' automatic Internet test. ARM64 Android7+.\n'
            'Exit the current ROM normally, then install this APK as an update. Keep app data.\n'
            'New profiles default Internet On. For automatic Work setup use a newly added\n'
            'compatible stock ROM with fresh guest storage. Keep existing saves intact.\n'
            'Existing/adopted profiles keep all choices and manual setup; enable Internet\n'
            'and select The Internet inside WM Network Cards if they still need it.\n'
            'For the new-profile test leave Work selected and try http://google.com/ on WM6.\n'
            'Exit/reopen normally and verify browsing plus your files; test Restart normally.\n'
            'No modern HTTPS guarantee. WM5 public browsing is unconfirmed; local HTTP passed.\n'
            'Unknown/custom ROM configuration, real card2577 conflicts or unsupported sealing\n'
            'use manual setup. A failed guarded attempt is not automatically retried.\n'
            'If networking prevents boot, Exit normally and turn Internet access Off.\n', encoding='utf-8')
        m.require(protected == {p.relative_to(prior).as_posix(): m.sha(p) for p in prior.rglob('*') if p.is_file()}, 'Protected test4 artifacts changed')
        for name, ok in proof['signed_artifacts_preserved'].items():
            m.require(ok, 'Prior artifact preservation had failed: ' + name)
        (stage / 'SHA256SUMS.txt').write_text(''.join(m.sha(p) + '  ' + p.relative_to(stage).as_posix() + '\n' for p in sorted(stage.rglob('*')) if p.is_file()), encoding='utf-8')
        m.publish_release(stage, release)
        print(json.dumps(dict(apk=str(release / delivered.name), **record), indent=2), flush=True)
    finally:
        if stage.exists():
            m.require(stage.parent.resolve() == release.parent.resolve() and stage.name.startswith('.seal-network-setup-'), 'Unsafe stage cleanup')
            shutil.rmtree(stage)


if __name__ == '__main__':
    main()
