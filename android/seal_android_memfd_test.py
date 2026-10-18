"""Seal the reproduced Android helper-delivery correction; preserve test6."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
import zipfile

HERE=Path(__file__).resolve().parent
ROOT,BUILD=HERE.parent,HERE/'build'
PROJECT=ROOT.parents[1]
PROOF=BUILD/'network-setup/android-seal-fix'
VERSION,CODE='1.0.2-test7',678
spec=importlib.util.spec_from_file_location('seal_integrity',HERE/'finalize_release.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.VERSION,m.VERSION_CODE=VERSION,CODE
digest=lambda data:hashlib.sha256(data).hexdigest()

def main():
    prior=PROJECT/'apk/1.0.2-test6'
    release=PROJECT/'apk'/VERSION
    m.require(not release.exists(),'Never overwrite a release')
    old_apk=prior/'Pocket2Droid-v1.0.2-test6-WM65-Automatic-Internet.apk'
    old_source=prior/'Pocket2Droid-v1.0.2-test6.Source.zip'
    m.require(m.sha(old_apk)=='214e61f091ea931dcc87efcef425dd199ed6ef0d0b2f31742b571fae0019260f','Test6 APK changed')
    m.require(m.sha(old_source)=='715d01ec3af159c5b7710a5e257480e37062bcc17897f8359aeded32ce45306a','Test6 source changed')
    protected={p.relative_to(prior).as_posix():m.sha(p) for p in prior.rglob('*') if p.is_file()}
    app,native,runtime,storage=(m.load(BUILD/name) for name in ('candidate-build.json','bionic-engine.json','runtime.json','storage-runtime.json'))
    previous=m.load(prior/'bionic-engine.json')
    m.require(set(native['source']['paths'])==set(previous['source']['paths']),'Native inventory changed')
    changed=[name for name,value in native['source']['paths'].items() if value!=previous['source']['paths'][name]]
    m.require(changed==['hw/misc/p2d-net-setup-files.c'],'Unexpected production native changes: '+repr(changed))
    m.require(storage==m.load(prior/'storage-runtime.json'),'Storage helper changed')
    m.require(native['builder_sha256']==previous['builder_sha256']==m.sha(HERE/'build_bionic.py'),'Native builder changed')
    m.require(native['binary_sha256']==m.sha(BUILD/'libp2dengine-bionic.so'),'Native binary differs')
    for name,expected in native['source']['paths'].items():
        m.require(m.sha(ROOT/'qemu'/name)==expected,'Stale canonical source: '+name)
    for name,expected in native['runtime_source_hashes'].items():
        m.require(m.sha(m.NATIVE/name)==expected,'Stale compiled source: '+name)
    m.require(runtime['native_engine_record_sha256']==m.sha(BUILD/'bionic-engine.json'),'Runtime native identity differs')
    tested=m.tested_source_hashes()
    with zipfile.ZipFile(old_source) as baseline:
        for name in tested:
            data=(HERE/name).read_bytes()
            if name=='AndroidManifest.xml':
                data=data.replace(b'android:versionCode="678"',b'android:versionCode="677"').replace(b'android:versionName="1.0.2-test7"',b'android:versionName="1.0.2-test6"')
            m.require(data==baseline.read('android/'+name),'Unexpected frontend change: '+name)
        builder=(HERE/'build.py').read_bytes().replace(b"VERSION = '1.0.2-test7'",b"VERSION = '1.0.2-test6'").replace(b'VERSION_CODE = 678',b'VERSION_CODE = 677')
        m.require(builder==baseline.read('android/build.py'),'Unexpected APK recipe change')
    logs={name:m.sha(PROOF/name) for name in ('regression-red.log','native-final.log','phone-before/app-uid-probe.txt','phone-before/production-engine-probe-final.txt','phone-copy-guest.log','review.md')}
    m.require('Android chmod denial must not hide a sealable helper' in (PROOF/'regression-red.log').read_text(),'Missing RED regression')
    suite=(PROOF/'native-final.log').read_text()
    m.require('Ran 180 tests' in suite and suite.rstrip().endswith('OK'),'Native suite failed')
    phone=(PROOF/'phone-before/production-engine-probe-final.txt').read_text(encoding='utf-8-sig')
    m.require('fchmod-0400=-1 errno=13' in phone and 'get-seals=15' in phone and 'immutability_failures=0' in phone,'Android syscall evidence differs')
    m.require('PASS actual Android engine app-UID helper' in phone,'Actual Android helper delivery failed')
    initial=m.load(PROOF/'phone-copy-setup/result.json')
    reopen=m.load(PROOF/'phone-copy-reopen/result.json')
    for guest in (initial,reopen):
        m.require(guest['private_profile'] and guest['virtual_delivery'] and not guest['real_card_has_helper'],'Guest delivery differs')
        m.require(guest['exit_code']==0 and guest['rom_unchanged'] and guest['marker_unchanged'],'Guest preservation failed')
        m.require(guest['network_settings_taps']==0 and guest['settings_ui'] is False,'Unexpected guest input')
    m.require(reopen['positive_google_dns'] and reopen['public_http_200'],'Copied existing state did not browse')
    response=(PROOF/'phone-copy-reopen/query-response.bin').read_bytes();offset=response.index(b'<\x00')
    header,xml=response[:offset].decode('ascii'),response[offset:].decode('utf-16le')
    m.require('marker-version=0x00000001' in header and 'attempt-open=0x00000000' in header and 'P2D-Work-Internet' in xml,'Copied state setup did not persist')
    helper=m.load(BUILD/'network-setup/production-helper/manifest.json')
    m.require(initial['helper_sha256']==helper['executable_sha256'],'Guest-tested helper differs')
    libraries={name:row['sha256'] for name,row in runtime['files'].items()}
    libraries['libp2dstorage.so']=storage['binary_sha256']
    for name,expected in libraries.items():
        file=BUILD/('storage-runtime' if name=='libp2dstorage.so' else 'runtime')/name
        m.require(m.sha(file)==expected,'Native payload changed: '+name)
        loads=[line for line in subprocess.check_output(['readelf','-lW',str(file)],text=True).splitlines() if 'LOAD ' in line]
        m.require(loads and all(int(line.split()[-1],16)>=16384 for line in loads),'ELF alignment failed')
    apk=Path(app['signed_apk'])
    m.require(app['version']==VERSION and app['apk_sha256']==m.sha(apk),'APK build identity differs')
    signature=m.validate_apk(apk,'com.samsixx.pocket2droid',False,libraries,m.sha(BUILD/'dex/classes.dex'))
    manifest=m.parse_manifest(apk)
    m.require(not manifest.get('instrumentation') and not manifest.get('provider'),'Test fixtures packaged')
    with zipfile.ZipFile(old_apk) as old,zipfile.ZipFile(apk) as current:
        m.require(old.read('classes.dex')==current.read('classes.dex'),'Frontend dex changed')
        for name in old.namelist():
            if name.startswith(('res/','assets/')) or name=='resources.arsc':
                m.require(old.read(name)==current.read(name),'Artwork/helper/notice changed: '+name)
        m.require({name for name in old.namelist() if name.startswith('assets/')}=={name for name in current.namelist() if name.startswith('assets/')},'Unexpected assets')
        for name in libraries:
            if name!='libp2dengine.so':
                m.require(old.read('lib/arm64-v8a/'+name)==current.read('lib/arm64-v8a/'+name),'Unrelated native payload changed')
    stage=Path(tempfile.mkdtemp(prefix='.seal-android-memfd-',dir=release.parent))
    try:
        delivered=stage/('Pocket2Droid-v'+VERSION+'-Android-Internet-Fix.apk')
        shutil.copy2(apk,delivered)
        raw=stage/'.current-source.zip'
        m.snapshot_sources(raw,{'native':native,'runtime':runtime})
        source=stage/('Pocket2Droid-v'+VERSION+'.Source.zip');inventory={}
        with zipfile.ZipFile(raw) as current,zipfile.ZipFile(old_source) as old,zipfile.ZipFile(source,'w',zipfile.ZIP_DEFLATED,compresslevel=4) as out:
            for archive in (current,old):
                for info in archive.infolist():
                    name=info.filename
                    if name=='SOURCE_SHA256.json' or name.endswith('-TEST-BUILD.txt') or name in inventory:continue
                    data=archive.read(info);out.writestr(info,data);inventory[name]=digest(data)
            note=('Pocket2Droid '+VERSION+'/code678 Android helper-delivery correction.\n'
                  'Build android/build.py; canonical overlay qemu-canonical-changes/; exact\n'
                  'compiled Bionic source qemu-android-exact/. Existing WSL/NDK setup required.\n'
                  'Removes redundant host memfd chmod denied by Android app policy. All four\n'
                  'seals and VCEFS read-only protections retained.180 native tests pass.\n'
                  'Actual Android app-UID engine delivers helper through VCEFS with CPU paused.\n'
                  'Disposable copy of affected phone save applies/persists Work route and\n'
                  'renders Google HTTP on PC. Real phone browsing after update remains pending.\n'
                  'No ROM, SDK, user save, StorageCard contents or signing key included.\n').encode()
            out.writestr('ANDROID-MEMFD-TEST-BUILD.txt',note);inventory['ANDROID-MEMFD-TEST-BUILD.txt']=digest(note)
            out.writestr('SOURCE_SHA256.json',json.dumps(inventory,indent=2)+'\n')
        raw.unlink()
        with zipfile.ZipFile(source) as archive:
            m.require(archive.testzip() is None and len(archive.namelist())==len(set(archive.namelist())),'Source CRC/duplicates failed')
            for name,expected in inventory.items():m.require(digest(archive.read(name))==expected,'Source identity failed: '+name)
        for name,expected in native['source']['paths'].items():m.require(inventory['qemu-canonical-changes/'+name]==expected,'Native snapshot stale')
        for name,expected in native['runtime_source_hashes'].items():m.require(inventory['qemu-android-exact/'+name]==expected,'Compiled snapshot stale')
        for name,expected in tested.items():m.require(inventory['android/'+name]==expected,'Frontend snapshot stale')
        for name in ('candidate-build.json','bionic-engine.json','runtime.json','bionic-tools.json','storage-runtime.json'):shutil.copy2(BUILD/name,stage/name)
        shutil.copy2(Path(__file__),stage/'candidate-release-recipe.py')
        (stage/'candidate-signature.txt').write_text(signature,encoding='utf-8')
        evidence=stage/'evidence';evidence.mkdir()
        for name in logs:shutil.copy2(PROOF/name,evidence/Path(name).name)
        record=dict(version=VERSION,version_code=CODE,apk_sha256=m.sha(delivered),source_archive_sha256=m.sha(source),source_snapshot_files=len(inventory),original_signer=m.SIGNER,
                    signature_verified=True,apk_and_elf_alignment_16k=True,exact_native_and_dex_identity=True,native_tests=180,
                    changed_production_native_files=changed,android_app_uid_helper_delivery_passed=True,existing_phone_save_copy_pc_http_passed=True,
                    phone_browsing_confirmation_pending=True,user_app_not_installed=True,helper_sha256=helper['executable_sha256'],logs_sha256=logs,earlier_release_preserved=True)
        (stage/'FINAL_VERIFICATION.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
        (stage/'INSTALL.txt').write_text('Exit the ROM normally, then install this signed test7/code678 as an update.\nKeep app data and existing ROMs/saves; no reset or reimport.\nStart the affected ppc-phone-480x800 (480x800).bin with Internet On.\nLeave Work selected and try http://google.com/.\nActual phone helper delivery passed in an isolated native check; full phone browsing remains pending.\nExisting/adopted manual-only profiles retain their configuration.\n',encoding='utf-8')
        m.require(protected=={p.relative_to(prior).as_posix():m.sha(p) for p in prior.rglob('*') if p.is_file()},'Test6 changed')
        (stage/'SHA256SUMS.txt').write_text(''.join(m.sha(p)+'  '+p.relative_to(stage).as_posix()+'\n' for p in sorted(stage.rglob('*')) if p.is_file()),encoding='utf-8')
        m.publish_release(stage,release)
        print(json.dumps(dict(apk=str(release/delivered.name),**record),indent=2))
    finally:
        if stage.exists():
            m.require(stage.parent.resolve()==release.parent.resolve() and stage.name.startswith('.seal-android-memfd-'),'Unsafe stage cleanup')
            shutil.rmtree(stage)

if __name__=='__main__':main()
