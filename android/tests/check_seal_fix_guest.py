"""Boot disposable copies of the read-only phone save; never touch phone/card data."""
from pathlib import Path
import hashlib
import json
import shutil
from network_setup_probe import run_case

EXP=Path(__file__).resolve().parents[2]
PROJECT=EXP.parents[1]
OUT=EXP/'android/build/network-setup/android-seal-fix'
phone=OUT/'phone-before'
rom=PROJECT/'PC windows mobile 6 Files/Roms and files/pocket pc/DeviceemulationV610/0409/ppc-phone-480x800 (480x800).bin'
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(rom)=='7334f87ba0025506d5bf4900c81a6bbe56d26ad041e111a0f58de240a1fbef9b'
assert sha(phone/'ram-fmd.bin')=='74d487a99980aba79c1fcd8db7e3a72259d7990447d8bbb4ce216503f42295ce'
seed=OUT/'private-phone-copy'
seed.mkdir()
shutil.copy2(phone/'ram-fmd.bin',seed/'private-fmd.bin')
(seed/'result.json').write_text(json.dumps(dict(private_profile=True,rom_sha256=sha(rom),
    source='read-only phone save copied while no native engine PID existed',
    source_sha256=sha(phone/'ram-fmd.bin')))+'\n',encoding='utf-8')
binary=Path('/opt/pocket2droid-network-integration/host/qemu-system-arm')
initial=run_case(binary,rom,EXP/'android/build/network-setup/production-helper/autorun.exe',
                 OUT/'phone-copy-setup','policy-initial',seed,True,False,(480,800),False,55)
assert initial['exit_code']==0 and initial['rom_unchanged'] and initial['marker_unchanged']
reopen=run_case(binary,rom,EXP/'android/build/network-setup/guard-inspect-helper/autorun.exe',
                OUT/'phone-copy-reopen','inspect-reopen',OUT/'phone-copy-setup',True,False,(480,800),False)
assert reopen['exit_code']==0 and reopen['rom_unchanged'] and reopen['marker_unchanged']
response=(OUT/'phone-copy-reopen/query-response.bin').read_bytes()
offset=response.index(b'<\x00')
header,xml=response[:offset].decode('ascii'),response[offset:].decode('utf-16le')
assert 'marker-version=0x00000001' in header and 'attempt-open=0x00000000' in header
assert 'P2D-Work-Internet' in xml
assert reopen['positive_google_dns'] and reopen['public_http_200']
assert sha(phone/'ram-fmd.bin')=='74d487a99980aba79c1fcd8db7e3a72259d7990447d8bbb4ce216503f42295ce'
print(json.dumps(dict(phone_copy_setup=initial,phone_copy_reopen=reopen),indent=2))
