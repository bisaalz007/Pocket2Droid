"""Seal test8 existing-ROM setup delivery; native/helper remain exact test7."""
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
PROOF=BUILD/'network-setup/existing-profiles'
VERSION,CODE='1.0.2-test8',679
spec=importlib.util.spec_from_file_location('existing_profile_integrity',HERE/'finalize_release.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.VERSION,m.VERSION_CODE=VERSION,CODE
digest=lambda data:hashlib.sha256(data).hexdigest()

def source_archive(target,native,runtime,previous):
    raw=target.with_name('.current-source.zip')
    m.snapshot_sources(raw,{'native':native,'runtime':runtime})
    inventory={}
    with zipfile.ZipFile(raw) as current,zipfile.ZipFile(previous) as prior,zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=4) as out:
        for archive in (current,prior):
            for info in archive.infolist():
                name=info.filename
                if name=='SOURCE_SHA256.json' or name.endswith('-TEST-BUILD.txt') or name in inventory:continue
                data=archive.read(info);out.writestr(info,data);inventory[name]=digest(data)
        note=('Pocket2Droid '+VERSION+'/code679 existing-ROM automatic Work setup correction.\n'
              'Build android/build.py; exact native source qemu-android-exact/ and\n'
              'canonical changes qemu-canonical-changes/. Existing WSL/NDK setup required.\n'
              'All Internet-On profiles receive the same guarded helper, including old\n'
              'missing/false eligibility metadata. Saved Off/MAC/storage are preserved.\n'
              'No guest reset or migration. Guest custom/Attempt1/Version1 guards retained.\n'
              'Android24 checks+Engine ART,host127/19/13,repository133/settings98,helper7\n'
              'pass. Native/helper bytes identical to signed test7; no new native suite\n'
              'or phone browsing claim. Full phone confirmation after update pending.\n'
              'No ROM, SDK, user save, StorageCard contents or signing key included.\n').encode()
        out.writestr('EXISTING-PROFILES-TEST-BUILD.txt',note);inventory['EXISTING-PROFILES-TEST-BUILD.txt']=digest(note)
        out.writestr('SOURCE_SHA256.json',json.dumps(inventory,indent=2)+'\n')
    raw.unlink()
    with zipfile.ZipFile(target) as archive:
        m.require(archive.testzip() is None and len(archive.namelist())==len(set(archive.namelist())),'Source CRC/duplicates failed')
        for name,expected in inventory.items():m.require(digest(archive.read(name))==expected,'Source differs: '+name)
    return inventory

def main():
    prior=PROJECT/'apk/1.0.2-test7';release=PROJECT/'apk'/VERSION
    m.require(not release.exists(),'Never overwrite a release')
    old_apk=prior/'Pocket2Droid-v1.0.2-test7-Android-Internet-Fix.apk'
    old_source=prior/'Pocket2Droid-v1.0.2-test7.Source.zip'
    m.require(m.sha(old_apk)=='a08ff0a63cff90098741e21c5b9cb22d29997eaef5f79c5395db9046c4433995','Test7 APK changed')
    m.require(m.sha(old_source)=='8dc82a8901b7ff38325969d086bff31cff109e8810061f0d8f2f06d760efe9f1','Test7 source changed')
    protected={p.relative_to(prior).as_posix():m.sha(p) for p in prior.rglob('*') if p.is_file()}
    app,native,runtime,storage=(m.load(BUILD/name) for name in ('candidate-build.json','bionic-engine.json','runtime.json','storage-runtime.json'))
    for name,record in (('bionic-engine.json',native),('runtime.json',runtime),('storage-runtime.json',storage)):
        m.require(record==m.load(prior/name),'Native/runtime/storage changed: '+name)
    for name,expected in native['source']['paths'].items():m.require(m.sha(ROOT/'qemu'/name)==expected,'Stale canonical source')
    for name,expected in native['runtime_source_hashes'].items():m.require(m.sha(m.NATIVE/name)==expected,'Stale compiled source')
    changed=[];tested=m.tested_source_hashes()
    with zipfile.ZipFile(old_source) as old:
        for name in tested:
            data=(HERE/name).read_bytes()
            if name=='AndroidManifest.xml':data=data.replace(b'android:versionCode="679"',b'android:versionCode="678"').replace(b'android:versionName="1.0.2-test8"',b'android:versionName="1.0.2-test7"')
            if data!=old.read('android/'+name):changed.append(name)
        m.require(set(changed)=={'src/com/samsixx/pocket2droid/'+name+'.java' for name in ('Engine','NetworkSetup','RomSettingsActivity')},'Unexpected frontend changes: '+repr(changed))
        builder=(HERE/'build.py').read_bytes().replace(b"VERSION = '1.0.2-test8'",b"VERSION = '1.0.2-test7'").replace(b'VERSION_CODE = 679',b'VERSION_CODE = 678')
        m.require(builder==old.read('android/build.py'),'Unexpected build recipe change')
    red=(PROOF/'actual-engine-red.log').read_text()
    m.require('Existing Internet-On profile must deliver the guarded Work setup helper' in red and 'ERROR ' in red,'Missing RED evidence')
    green=(PROOF/'engine-ui-final.log').read_text()
    m.require('PASS 24 Android network UI/observer/socket checks; Engine ART lifecycle checks passed.' in green and 'ERROR ' not in green,'Android regression failed')
    for name,expected in m.load(PROOF/'android-ui/granted-sources.json').items():m.require(m.sha(HERE/name)==expected,'Android test source changed: '+name)
    for name,markers in (
        ('java-green.log',('Network config: 127 checks passed','Network setup publication/profile: 19 checks passed','Network session: 13 checks passed')),
        ('library-green.log',('PASS ROM repository 133','PASS ROM settings/geometry 98')),
        ('helper-guards.log',('Ran 7 tests','OK'))):
        text=(PROOF/name).read_text();m.require(all(marker in text for marker in markers),'Required acceptance failed: '+name)
    libraries={name:row['sha256'] for name,row in runtime['files'].items()};libraries['libp2dstorage.so']=storage['binary_sha256']
    for name,expected in libraries.items():
        file=BUILD/('storage-runtime' if name=='libp2dstorage.so' else 'runtime')/name
        m.require(m.sha(file)==expected,'Native payload differs')
        loads=[line for line in subprocess.check_output(['readelf','-lW',str(file)],text=True).splitlines() if 'LOAD ' in line]
        m.require(loads and all(int(line.split()[-1],16)>=16384 for line in loads),'ELF alignment failed')
    apk=Path(app['signed_apk']);m.require(app['version']==VERSION and app['apk_sha256']==m.sha(apk),'APK build identity differs')
    signature=m.validate_apk(apk,'com.samsixx.pocket2droid',False,libraries,m.sha(BUILD/'dex/classes.dex'))
    manifest=m.parse_manifest(apk);m.require(not manifest.get('instrumentation') and not manifest.get('provider'),'Test fixtures packaged')
    with zipfile.ZipFile(old_apk) as old,zipfile.ZipFile(apk) as current:
        m.require({name for name in old.namelist() if name.startswith('assets/')}=={name for name in current.namelist() if name.startswith('assets/')},'Unexpected assets')
        for name in old.namelist():
            if name.startswith(('assets/','res/','lib/')) or name=='resources.arsc':m.require(old.read(name)==current.read(name),'Unexpected payload change: '+name)
        helper_sha=digest(current.read('assets/network-setup/autorun.exe'))
    logs=('actual-engine-red.log','engine-ui-final.log','java-green.log','library-green.log','helper-guards.log','review.md')
    log_hashes={name:m.sha(PROOF/name) for name in logs}
    stage=Path(tempfile.mkdtemp(prefix='.seal-existing-network-',dir=release.parent))
    try:
        delivered=stage/('Pocket2Droid-v'+VERSION+'-Existing-ROM-Internet.apk');shutil.copy2(apk,delivered)
        source=stage/('Pocket2Droid-v'+VERSION+'.Source.zip');inventory=source_archive(source,native,runtime,old_source)
        for name,expected in tested.items():m.require(inventory['android/'+name]==expected,'Frontend snapshot differs')
        for name,expected in native['source']['paths'].items():m.require(inventory['qemu-canonical-changes/'+name]==expected,'Native snapshot differs')
        for name,expected in native['runtime_source_hashes'].items():m.require(inventory['qemu-android-exact/'+name]==expected,'Compiled snapshot differs')
        for name in ('candidate-build.json','bionic-engine.json','runtime.json','bionic-tools.json','storage-runtime.json'):shutil.copy2(BUILD/name,stage/name)
        shutil.copy2(Path(__file__),stage/'candidate-release-recipe.py');(stage/'candidate-signature.txt').write_text(signature,encoding='utf-8')
        evidence=stage/'evidence';evidence.mkdir()
        for name in logs:shutil.copy2(PROOF/name,evidence/name)
        shutil.copy2(PROOF/'android-ui/granted-sources.json',evidence/'android-tested-sources.json')
        shutil.copy2(prior/'FINAL_VERIFICATION.json',evidence/'native-baseline-test7.json')
        record=dict(version=VERSION,version_code=CODE,apk_sha256=m.sha(delivered),source_archive_sha256=m.sha(source),source_snapshot_files=len(inventory),original_signer=m.SIGNER,
                    signature_verified=True,apk_and_elf_alignment_16k=True,exact_native_and_dex_identity=True,native_and_guest_helper_unchanged_from_test7=True,
                    changed_product_java_files=changed,android_network_checks=24,engine_art_lifecycle_passed=True,host_network_checks=[127,19,13],repository_checks=133,settings_checks=98,guest_helper_checks=7,
                    helper_sha256=helper_sha,phone_browsing_confirmation_pending=True,user_phone_not_accessed=True,earlier_release_preserved=True,logs_sha256=log_hashes)
        (stage/'FINAL_VERIFICATION.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
        (stage/'INSTALL.txt').write_text('Exit the ROM normally, then install signed test8/code679 as an update.\nExisting ROMs with Internet access On now receive the same guarded Work setup\nhelper as new ROMs, including old missing/false eligibility metadata.\nKeep Work selected and try http://google.com/. No reset or reimport.\nSaved Off, MAC, storage and custom/prior-attempt guest configuration remain\nprotected; unsupported or previously failed setups can still need manual setup.\nActual phone browsing after this update remains pending.\n',encoding='utf-8')
        m.require(protected=={p.relative_to(prior).as_posix():m.sha(p) for p in prior.rglob('*') if p.is_file()},'Test7 changed')
        (stage/'SHA256SUMS.txt').write_text(''.join(m.sha(p)+'  '+p.relative_to(stage).as_posix()+'\n' for p in sorted(stage.rglob('*')) if p.is_file()),encoding='utf-8')
        m.publish_release(stage,release);print(json.dumps(dict(apk=str(release/delivered.name),**record),indent=2))
    finally:
        if stage.exists():
            m.require(stage.parent.resolve()==release.parent.resolve() and stage.name.startswith('.seal-existing-network-'),'Unsafe stage cleanup')
            shutil.rmtree(stage)

if __name__=='__main__':main()
