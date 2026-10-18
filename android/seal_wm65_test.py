"""Seal the reproduced WM6.5 stock-schema correction; preserve earlier tests."""
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
PROJECT, PROOF = ROOT.parents[1], BUILD / 'network-setup'
VERSION, CODE = '1.0.2-test6', 677
spec = importlib.util.spec_from_file_location('setup_seal', HERE / 'seal_network_setup_test.py')
seal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seal)
seal.VERSION, seal.CODE = VERSION, CODE
m = seal.m
m.VERSION, m.VERSION_CODE = VERSION, CODE


def digest(data):
    return hashlib.sha256(data).hexdigest()


def guest(name, markers=False):
    folder = PROOF / name
    record = m.load(folder / 'result.json')
    m.require(record['private_profile'] and record['virtual_delivery'] and not record['real_card_has_helper'], 'Guest delivery differs: ' + name)
    m.require(record['exit_code'] == 0 and record['rom_unchanged'] and record['marker_unchanged'], 'Guest preservation failed: ' + name)
    m.require(record['network_settings_taps'] == 0 and record['settings_ui'] is False, 'Guest settings were modified by test input')
    m.require(m.sha(Path(record['rom'])) == record['rom_sha256'], 'Original ROM changed')
    if markers:
        data = (folder / 'query-response.bin').read_bytes()
        offset = data.index(b'<\x00')
        header, xml = data[:offset].decode('ascii'), data[offset:].decode('utf-16le')
        m.require('marker-version=0x00000001' in header and 'attempt-open=0x00000000' in header, 'Guest setup did not persist')
        m.require('P2D-Work-Internet' in xml, 'Guest route did not persist')
    record['evidence_sha256'] = {p.name: m.sha(p) for p in folder.iterdir() if p.is_file() and p.suffix in ('.json', '.bin', '.png', '.ppm', '.pcap') and p.name != 'private-fmd.bin'}
    return record


def main():
    prior = PROJECT / 'apk/1.0.2-test5'
    release = PROJECT / 'apk' / VERSION
    m.require(not release.exists(), 'Never overwrite a test release')
    protected = {p.relative_to(prior).as_posix(): m.sha(p) for p in prior.rglob('*') if p.is_file()}
    old_apk = prior / 'Pocket2Droid-v1.0.2-test5-Automatic-Internet.apk'
    old_source = prior / 'Pocket2Droid-v1.0.2-test5.Source.zip'
    m.require(m.sha(old_apk) == '51190615c1a61114baa9b2c298bc55631ca5d75e86f69580ae1886494354ace4', 'Test5 APK changed')
    m.require(m.sha(old_source) == '1fe9a007866ee16845778fa786b54b28bdd09c14732aa02da33075d57d94cd4d', 'Test5 source changed')
    app, native, runtime, storage = (m.load(BUILD / n) for n in ('candidate-build.json', 'bionic-engine.json', 'runtime.json', 'storage-runtime.json'))
    m.require(native == m.load(prior / 'bionic-engine.json') and runtime == m.load(prior / 'runtime.json') and storage == m.load(prior / 'storage-runtime.json'), 'Native/runtime/storage changed beyond helper correction')
    tested = m.tested_source_hashes()
    with zipfile.ZipFile(old_source) as old:
        for name in tested:
            data = (HERE / name).read_bytes()
            if name == 'AndroidManifest.xml':
                data = data.replace(b'android:versionCode="677"', b'android:versionCode="676"').replace(b'android:versionName="1.0.2-test6"', b'android:versionName="1.0.2-test5"')
            m.require(data == old.read('android/' + name), 'Unexpected Android frontend change: ' + name)
        build = (HERE / 'build.py').read_bytes().replace(b"VERSION = '1.0.2-test6'", b"VERSION = '1.0.2-test5'").replace(b'VERSION_CODE = 677', b'VERSION_CODE = 676')
        m.require(build == old.read('android/build.py'), 'Unexpected APK builder change')
        for name in ('net_setup.c', 'net_setup.h', 'build.py', 'stock_wm6.h'):
            m.require((ROOT / 'guest/network-setup' / name).read_bytes() == old.read('guest/network-setup/' + name), 'Unexpected helper adapter change: ' + name)
    helper = m.load(BUILD / 'network-setup/production-helper/manifest.json')
    m.require(helper == m.load(PROOF / 'wm65-helper/manifest.json'), 'Packaged helper differs from guest-tested helper')
    for name, expected in helper['sources'].items():
        m.require(m.sha(Path(name)) == expected, 'Helper source changed: ' + name)
    m.require(m.sha(ROOT / 'guest/network-setup/build.py') == helper['builder_sha256'], 'Helper recipe changed')
    for name, marker in (('wm65-policy-red.log', 'WM6.5 stock ReadOnly metadata applies'), ('wm65-policy-green.log', 'Ran 7 tests'), ('wm65-native-all.log', 'Ran 179 tests')):
        m.require(marker in (PROOF / name).read_text(encoding='utf-8'), 'Required evidence absent: ' + name)
    m.require((PROOF / 'wm65-policy-green.log').read_text(encoding='utf-8').rstrip().endswith('OK'), 'Helper suite failed')
    m.require((PROOF / 'wm65-native-all.log').read_text(encoding='utf-8').rstrip().endswith('OK'), 'Native suite failed')
    initial = guest('wm65-fixed-full-initial')
    reopen = guest('wm65-fixed-full-reopen', True)
    local = guest('wm65-fixed-full-local', True)
    classic_initial = guest('wm65-fix-classic-initial')
    classic = guest('wm65-fix-classic-reopen', True)
    m.require(initial['helper_sha256'] == classic_initial['helper_sha256'] == helper['executable_sha256'], 'Different helper in full OS checks')
    m.require(reopen['positive_google_dns'] and reopen['public_http_200'] and local['local_http_200'], 'WM6.5 browsing acceptance failed')
    m.require(classic['positive_google_dns'] and classic['public_http_200'], 'Earlier Classic ROM regressed')
    fix = dict(cause='WM6.5 stock ReadOnly0 metadata was rejected by the older exact fingerprint',
               change='one additional exact stock schema with paired exact readback; unknown/custom/ReadOnly1 preserved',
               helper=helper, native_unchanged=True, android_frontend_unchanged=True, native_tests=179,
               source_hashes={str(p.relative_to(ROOT)): m.sha(p) for p in list((ROOT / 'guest/network-setup').glob('*')) + list((ROOT / 'tests/fixtures/network-setup').glob('*.xml')) if p.is_file()},
               guests=dict(wm65_initial=initial, wm65_reopen=reopen, wm65_local=local, classic_reopen=classic),
               logs_sha256={name: m.sha(PROOF / name) for name in ('wm65-policy-red.log', 'wm65-policy-green.log', 'wm65-native-all.log')},
               phone_modified=False, phone_confirmation_pending=True)
    (PROOF / 'wm65-fix-result.json').write_text(json.dumps(fix, indent=2) + '\n', encoding='utf-8')
    libraries = {name: row['sha256'] for name, row in runtime['files'].items()}
    libraries['libp2dstorage.so'] = storage['binary_sha256']
    for name, expected in libraries.items():
        path = BUILD / ('storage-runtime' if name == 'libp2dstorage.so' else 'runtime') / name
        m.require(m.sha(path) == expected, 'Native payload changed: ' + name)
        loads = [line for line in subprocess.check_output(['readelf', '-lW', str(path)], text=True).splitlines() if 'LOAD ' in line]
        m.require(loads and all(int(line.split()[-1], 16) >= 16384 for line in loads), 'ELF alignment failed')
    apk = Path(app['signed_apk'])
    m.require(app['version'] == VERSION and app['package'] == 'com.samsixx.pocket2droid' and not app['test_only'] and m.sha(apk) == app['apk_sha256'], 'Wrong APK identity')
    signature = m.validate_apk(apk, app['package'], False, libraries, m.sha(BUILD / 'dex/classes.dex'))
    manifest = m.parse_manifest(apk)
    m.require(not manifest.get('instrumentation') and not manifest.get('provider'), 'Test fixtures packaged')
    with zipfile.ZipFile(old_apk) as old, zipfile.ZipFile(apk) as z:
        m.require(old.read('classes.dex') == z.read('classes.dex'), 'Frontend dex changed beyond helper fix')
        art = lambda a: {n: digest(a.read(n)) for n in a.namelist() if n.startswith('res/') or n == 'resources.arsc'}
        m.require(art(old) == art(z), 'Artwork changed')
        assets = {'assets/QEMU-COPYING.txt', 'assets/LIBSLIRP-COPYRIGHT.txt', 'assets/LIBSLIRP-NOTICE.txt', 'assets/network-setup/autorun.exe', 'assets/network-setup/manifest.json'}
        m.require({n for n in z.namelist() if n.startswith('assets/')} == assets, 'Unexpected assets')
        m.require(digest(z.read('assets/network-setup/autorun.exe')) == helper['executable_sha256'] and json.loads(z.read('assets/network-setup/manifest.json')) == helper, 'Packaged helper differs')
    stage = Path(tempfile.mkdtemp(prefix='.seal-wm65-', dir=release.parent))
    try:
        delivered = stage / ('Pocket2Droid-v' + VERSION + '-WM65-Automatic-Internet.apk')
        shutil.copy2(apk, delivered)
        source = stage / ('Pocket2Droid-v' + VERSION + '.Source.zip')
        # The common snapshot adds current files before the older source fallback.
        # Use the pre-helper fallback to avoid inheriting its diagnostic duplicate.
        fallback = PROJECT / 'apk/1.0.2-test4/Pocket2Droid-v1.0.2-test4.Source.zip'
        m.require(m.sha(fallback) == '452da6664a054f0ac0cbd280e8147780a16cb082a7947e668547adf44d1d8e0e', 'Fallback source changed')
        inventory = seal.snapshot(source, native, runtime, fallback)
        for name, expected in tested.items():
            m.require(inventory['android/' + name] == expected, 'Archived frontend differs: ' + name)
        for name, expected in native['source']['paths'].items():
            m.require(inventory['qemu-canonical-changes/' + name] == expected, 'Archived native differs: ' + name)
        for name, expected in native['runtime_source_hashes'].items():
            m.require(inventory['qemu-android-exact/' + name] == expected, 'Archived compiled source differs: ' + name)
        for name, expected in fix['source_hashes'].items():
            m.require(inventory[name] == expected, 'Archived helper/fixture differs: ' + name)
        for name in ('candidate-build.json', 'bionic-engine.json', 'runtime.json', 'bionic-tools.json', 'storage-runtime.json'):
            shutil.copy2(BUILD / name, stage / name)
        shutil.copy2(Path(__file__), stage / 'candidate-release-recipe.py')
        (stage / 'candidate-signature.txt').write_text(signature, encoding='utf-8')
        evidence = stage / 'evidence'
        evidence.mkdir()
        for name in ('wm65-fix-result.json', 'wm65-policy-red.log', 'wm65-policy-green.log', 'wm65-native-all.log'):
            shutil.copy2(PROOF / name, evidence / name)
        shutil.copy2(PROOF / 'wm65-fixed-full-reopen/autorun-desktop.png', evidence / 'wm65-google.png')
        record = dict(version=VERSION, version_code=CODE, apk_sha256=m.sha(delivered), source_archive_sha256=m.sha(source),
                      source_snapshot_files=len(inventory), original_signer=m.SIGNER, signature_verified=True,
                      apk_and_elf_alignment_16k=True, exact_native_and_dex_identity=True,
                      helper_sha256=helper['executable_sha256'], wm65_work_automatic_pc_passed=True,
                      phone_confirmation_pending=True, phone_modified=False, earlier_test_preserved=True)
        (stage / 'FINAL_VERIFICATION.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        (stage / 'INSTALL.txt').write_text(
            'Pocket2Droid ' + VERSION + '/code' + str(CODE) + ' WM6.5 automatic Internet correction.\n'
            'Exit the ROM normally, then install as an update. Keep app data and saves.\n'
            'Fixes the stock WM6.5 ReadOnly metadata format, including PPC_USA_GSM_WVGA_VR.\n'
            'Automatic setup can keep Work selected. Tested Google HTTP and local HTTP\n'
            'on fresh480x800 PC guest and normal reopen; actual phone confirmation pending.\n'
            'Internet On for new profiles. Existing/manual/attempted/custom profiles retain\n'
            'their settings; no reset/reimport is required to keep using existing data.\n'
            'Try http://google.com/. Modern HTTPS is not added.\n', encoding='utf-8')
        m.require(protected == {p.relative_to(prior).as_posix(): m.sha(p) for p in prior.rglob('*') if p.is_file()}, 'Test5 artifacts changed')
        (stage / 'SHA256SUMS.txt').write_text(''.join(m.sha(p) + '  ' + p.relative_to(stage).as_posix() + '\n' for p in sorted(stage.rglob('*')) if p.is_file()), encoding='utf-8')
        m.publish_release(stage, release)
        print(json.dumps(dict(apk=str(release / delivered.name), **record), indent=2), flush=True)
    finally:
        if stage.exists():
            m.require(stage.parent.resolve() == release.parent.resolve() and stage.name.startswith('.seal-wm65-'), 'Unsafe stage cleanup')
            shutil.rmtree(stage)


if __name__ == '__main__':
    main()
