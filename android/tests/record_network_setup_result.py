"""Bind automatic-network-setup source, test and preservation evidence. No release."""
from pathlib import Path
import argparse
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import zipfile

EXP = Path(__file__).resolve().parents[2]
ROOT = EXP.parents[1]
OUT = EXP / 'android/build/network-setup'
ARTIFACTS = {
    'apk/1.0.2-test3/Pocket2Droid-v1.0.2-test3.Source.zip': 'bdf86f3f027c3a1ac269a5d515a7b2f3a687db8f0e3043e483982754cd8b59fc',
    'apk/1.0.2-test4/Pocket2Droid-v1.0.2-test4-Internet.apk': 'cc3008afc15012f71f6a64527acb82b331a2be37cc6bbeab5e473f0a3674525e',
    'apk/1.0.2-test4/Pocket2Droid-v1.0.2-test4.Source.zip': '452da6664a054f0ac0cbd280e8147780a16cb082a7947e668547adf44d1d8e0e',
}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def query(path):
    data = (path / 'query-response.bin').read_bytes()
    offset = data.index(b'<\x00')
    return data[:offset].decode('ascii'), data[offset:].decode('utf-16le')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--final', action='store_true')
    args = parser.parse_args()
    # Frozen release records are authoritative; never rewrite their artifacts.
    old = load(EXP / 'android/build/networking/baseline.json')['artifacts']
    preserve = {}
    for name, digest in old.items():
        preserve[name] = sha(ROOT / name) == digest
    for name, digest in ARTIFACTS.items():
        if digest:
            preserve[name] = sha(ROOT / name) == digest
    assert all(preserve.values()), preserve
    baseline = {}
    for name in ('native.json', 'android.json'):
        baseline.update({k.replace('\\', '/'): v for k, v in load(OUT / 'baseline' / name).items()})
    paths = {EXP / name for name in baseline}
    paths.update((EXP / 'guest/network-setup').glob('*'))
    paths.update((EXP / 'tests/fixtures/network-setup').glob('*.xml'))
    paths.update(p for p in (EXP / 'tests').glob('*') if p.suffix in ('.py', '.c'))
    paths.update(p for p in (EXP / 'android/tests').glob('*') if p.suffix in ('.py', '.java'))
    paths.update((EXP / 'prototypes/network-setup').glob('*.c'))
    paths.update(EXP / name for name in (
        'android/AndroidManifest.xml',
        'qemu/hw/misc/p2d-net-setup-files.c',
        'qemu/include/hw/arm/p2d-net-setup-files.h',
        'android/src/com/samsixx/pocket2droid/NetworkSetup.java',
    ))
    inventory = {p.relative_to(EXP).as_posix(): sha(p) for p in paths if p.is_file()}
    changed, diff = [], []
    with zipfile.ZipFile(ROOT / 'apk/1.0.2-test4/Pocket2Droid-v1.0.2-test4.Source.zip') as z:
        entries = set(z.namelist())
        for name, digest in sorted(inventory.items()):
            copy = OUT / 'baseline' / name
            old_bytes = copy.read_bytes() if copy.is_file() else None
            if old_bytes is None:
                candidate = 'qemu-canonical-changes/' + name[5:] if name.startswith('qemu/') else name
                if candidate in entries:
                    old_bytes = z.read(candidate)
            old_hash = hashlib.sha256(old_bytes).hexdigest() if old_bytes is not None else None
            if old_hash == digest:
                continue
            changed.append({'path': name, 'baseline_sha256': old_hash, 'sha256': digest})
            if (EXP / name).suffix in ('.c', '.h', '.py', '.java', '.xml', '.build'):
                diff.extend(difflib.unified_diff(
                    (old_bytes or b'').decode('utf-8').splitlines(True),
                    (EXP / name).read_text(encoding='utf-8').splitlines(True),
                    fromfile='before/' + name, tofile='automatic-setup/' + name))
    (OUT / 'source-scope.diff').write_text(''.join(diff), encoding='utf-8')
    write(OUT / 'source-scope.json', changed)
    helper = load(OUT / 'production-helper/manifest.json')
    assert sha(OUT / 'production-helper/autorun.exe') == helper['executable_sha256']
    assert sha(EXP / 'guest/network-setup/build.py') == helper['builder_sha256']
    for name, digest in helper['sources'].items():
        assert sha(Path(name)) == digest, name
    for name, digest in helper['tools'].items():
        assert sha(Path(shutil.which(name))) == digest, name
    native = load(EXP / 'android/build/bionic-engine.json')
    assert sha(EXP / 'android/build/libp2dengine-bionic.so') == native['binary_sha256']
    for name, digest in native['source']['paths'].items():
        assert sha(EXP / 'qemu' / name) == digest, name
    for name, digest in native['runtime_source_hashes'].items():
        assert sha(Path(native['runtime_source_directory']) / name) == digest, name
    runtime = load(EXP / 'android/build/runtime.json')
    for name, entry in runtime['files'].items():
        elf = EXP / 'android/build/runtime' / name
        assert sha(elf) == entry['sha256'], name
        for line in subprocess.check_output(['readelf', '-lW', str(elf)], text=True).splitlines():
            if 'LOAD ' in line:
                assert int(line.split()[-1], 16) >= 16384, name
    guests = {}
    for p in sorted(OUT.glob('*/result.json')):
        if (p.parent / 'private-fmd.bin').is_file():
            result = load(p)
            result['record_sha256'] = sha(p)
            packet_record = p.parent / 'packet-summary.json'
            events = load(packet_record) if packet_record.exists() else []
            result['dhcp_ack'] = any(e['kind'] == 'dhcp' and e['type'] == [5] for e in events)
            if (p.parent / 'query-response.bin').exists():
                header, xml = query(p.parent)
                result['success_marker_1'] = 'marker-version=0x00000001' in header
                result['attempt_guard_present'] = 'attempt-open=0x00000000' in header
                result['work_internet_route_present'] = 'P2D-Work-Internet' in xml
            result['evidence_sha256'] = {f.name: sha(f) for f in p.parent.iterdir()
                                        if f.is_file() and f.suffix in ('.ppm', '.png', '.pcap', '.json')}
            guests[p.parent.name] = result
    result = {
        'feature': 'new-ROM Internet On and once-only stock Work-to-Internet setup',
        'status': 'local implementation, final acceptance/review pending',
        'release_apk_created': False, 'phone_modified': False,
        'signed_artifacts_preserved': preserve,
        'source_hashes': inventory, 'changed_sources': changed,
        'helper': helper, 'bionic_engine': native, 'runtime': runtime,
        'logs_sha256': {p.name: sha(p) for p in OUT.glob('*.log') if not p.name.startswith('record-')},
        'guests': guests,
        'limitations': [
            'Actual ARM64 phone guest networking/provisioning not tested by this change',
            'Only exact recognized stock SDK configuration is automatically changed',
            'Existing/copy/orphan profiles retain manual setup and all saved network choices',
            'A real StorageCard 2577 subtree or unavailable sealing disables helper delivery',
            'A failed guarded setup attempt requires manual setup rather than automatic retry',
            'IPv6-only upstream DNS, Private DNS/VPN and modern TLS remain unsupported or unverified',
            'WM5 preserved Work route and resolved Google, but public page rendering was incomplete at capture',
        ],
    }
    if args.final:
        for family in ('wm6', 'wm5'):
            initial = guests[family + '-guard-initial']
            reopen = guests[family + '-guard-reopen']
            assert initial['helper_sha256'] == helper['executable_sha256']
            assert initial['virtual_delivery'] and not initial['real_card_has_helper']
            assert reopen['success_marker_1'] and reopen['work_internet_route_present']
            assert reopen['attempt_guard_present']
            for record in (initial, reopen):
                assert record['exit_code'] == 0 and record['rom_unchanged'] and record['marker_unchanged']
                assert record['network_settings_taps'] == 0
            assert reopen['positive_google_dns']
            assert initial['dhcp_ack'] and reopen['dhcp_ack']
            local = guests[family + '-local-reopen']
            assert local['local_http_200'] and local['success_marker_1'] and local['work_internet_route_present']
        assert guests['wm6-guard-reopen']['public_http_200']
        user = guests['user-change-verify']
        assert user['success_marker_1'] and not user['work_internet_route_present']
        native_log = (OUT / 'native-post-review.log').read_text(encoding='utf-8')
        assert int(re.search(r'Ran (\d+) tests', native_log).group(1)) >= 179
        assert native_log.rstrip().endswith('OK')
        assert 'Ran 7 tests' in (OUT / 'helper-final.log').read_text(encoding='utf-8')
        assert 'PASS 17 ' in (OUT / 'android-ui-post-review.log').read_text(encoding='utf-8')
        assert 'PASS 22 ' in (OUT / 'restart-final.log').read_text(encoding='utf-8')
        assert 'PASS GuestRam: 29 ' in (OUT / 'retained-ram-final.log').read_text(encoding='utf-8')
        assert (OUT / 'final-review.md').is_file()
        result['review_sha256'] = sha(OUT / 'final-review.md')
        result['review_disposition'] = {
            'critical': 0, 'important': 1, 'deferred_minors': [],
            'fixed': 'durable pre-apply attempt guard; commit-failure then user-removal/relaunch RED to GREEN',
            'fix_verification': 'helper-final.log and native-post-review.log; no second review',
        }
        with zipfile.ZipFile(ROOT / 'apk/1.0.2-test4/Pocket2Droid-v1.0.2-test4.Source.zip') as frozen:
            assert (EXP / 'android/AndroidManifest.xml').read_bytes() == frozen.read('android/AndroidManifest.xml')
        tested = load(EXP / 'android/build/networking/android-ui/granted-sources.json')
        for name, digest in tested.items():
            assert sha(EXP / 'android' / name) == digest, 'Android evidence stale: ' + name
        with zipfile.ZipFile(EXP / 'android/build/networking/android-ui/granted-test-only.apk') as apk:
            assert hashlib.sha256(apk.read('assets/network-setup/autorun.exe')).hexdigest() == helper['executable_sha256']
        for name in ('task3-library-final.log', 'task3-library-fallback-final.log'):
            text = (OUT / name).read_text(encoding='utf-8')
            assert '133 real filesystem assertions' in text and '98 assertions' in text and '120 control' in text
        result.update(status='local source integration complete; see final-review.md and progress.md for review disposition',
                      acceptance='WM6/WM5 auto-setup + retained-state reopen; WM6 Google HTTP; user-change preservation; native/Java/owned-PC Android checks')
    write(OUT / 'RESULT.json', result)
    print(f'Bound {len(inventory)} source files, {len(changed)} changes and {len(guests)} private guest results; signed artifacts preserved')


if __name__ == '__main__':
    main()
