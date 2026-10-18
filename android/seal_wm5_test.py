"""Seal the authorized WM5 test using the current source and verified engine."""
from pathlib import Path
import hashlib, importlib.util, json, shutil, subprocess, tempfile, zipfile

HERE=Path(__file__).resolve().parent
B=HERE/'build'
PROJECT=HERE.parents[2]
PACKAGE='com.samsixx.pocket2droid'
VERSION='1.0.2-test'
CODE=672
spec=importlib.util.spec_from_file_location('release_integrity',HERE/'finalize_release.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.VERSION,m.VERSION_CODE=VERSION,CODE

def snapshot(target,native,runtime,baseline,extra_note=''):
    raw=target.with_name('.current-source.tmp.zip')
    m.snapshot_sources(raw,{'native':native,'runtime':runtime})
    inventory={}
    with zipfile.ZipFile(raw) as current,zipfile.ZipFile(baseline) as old,zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=4) as final:
        for archive in (current,old):
            for info in archive.infolist():
                name=info.filename
                if name in ('SOURCE_SHA256.json','WM5-TEST-BUILD.txt') or name in inventory:continue
                data=archive.read(info)
                final.writestr(info,data)
                inventory[name]=hashlib.sha256(data).hexdigest()
        note=('Pocket2Droid '+VERSION+' / code '+str(CODE)+' - WM5 testing source\n'
              'Current source overrides public1.0.1; unchanged dependency sources/notices retained.\n'
              'Build entry: android/build.py. Canonical native overlay: qemu-canonical-changes/.\n'
              'Exact Android native tree: qemu-android-exact/. Existing WSL/NDK build setup is required;\n'
              'an independent clean-machine build is not claimed. See existing BUILDING for environment limitations.\n'
              'Changes: validated B000FF RAM loading and WM5 retained SDRAM with safe file publication.\n'
              'Local boot/storage and Engine ART validation do not establish phone guest execution.\n'
              'No Microsoft SDK, ROM, user save or signing key is included.\n'+extra_note).encode()
        final.writestr('WM5-TEST-BUILD.txt',note)
        inventory['WM5-TEST-BUILD.txt']=hashlib.sha256(note).hexdigest()
        final.writestr('SOURCE_SHA256.json',json.dumps(inventory,indent=2)+'\n')
    raw.unlink()
    with zipfile.ZipFile(target) as archive:
        m.require(archive.testzip() is None,'Source ZIP CRC failure')
        for name,digest in inventory.items():m.require(hashlib.sha256(archive.read(name)).hexdigest()==digest,'Source archive mismatch: '+name)
    return inventory

def main():
    previous=PROJECT/'apk/1.0.1'
    release=PROJECT/'apk/1.0.2-test'
    m.require(not release.exists(),'Never overwrite an existing candidate')
    protected={p.relative_to(previous).as_posix():m.sha(p) for p in previous.rglob('*') if p.is_file()}
    old_apk=previous/'Pocket2Droid-v1.0.1.apk'
    old_source=previous/'Pocket2Droid-v1.0.1.Source.zip'
    m.require(m.sha(old_apk)=='d71451309d94efae0c38e67d1bbf597a01de12211bb5f91cf5c635d48024993d','Public APK changed')
    m.require(m.sha(old_source)=='ae7a7d09079a5293ec4aaa68c4f14884e64e4fe20f298816f7dcc1707454cae5','Public source changed')
    app,native,runtime,storage=(m.load(B/n) for n in ('candidate-build.json','bionic-engine.json','runtime.json','storage-runtime.json'))
    proof_root=HERE.parent/'build/wm5'
    proof=m.load(proof_root/'RESULT.json')
    m.require(proof['android_engine_sha256']==native['binary_sha256']==m.sha(B/'libp2dengine-bionic.so'),'Native engine differs from locally verified WM5 engine')
    for name,digest in {**proof['source_sha256'],**proof['test_source_sha256']}.items():
        m.require(m.sha(HERE.parent/name)==digest,'Tested source changed: '+name)
    m.require(proof['tests']['native']==149 and proof['tests']['ram_java_jni_normal']==29 and proof['tests']['ram_java_jni_forced_fallback']==32,'Incomplete WM5 checks')
    m.require('Ran 149 tests' in (proof_root/'final-149-tests.log').read_text() and (proof_root/'final-149-tests.log').read_text().rstrip().endswith('OK'),'Native tests failed')
    m.require('PASS Engine WM5 RAM:' in (proof_root/'engine-art.log').read_text(),'Actual Engine ART test missing')
    old=m.load(previous/'bionic-engine.json')
    changed={n for n,h in native['source']['paths'].items() if old['source']['paths'].get(n)!=h}
    m.require(changed=={'hw/arm/pocket2droid-devemu.c'} and set(native['source']['paths'])==set(old['source']['paths']),'Unexpected native scope')
    m.require(native['source']['base']==old['source']['base'],'Native base changed')
    for name in ('builder_sha256','platform','termux_patch_sha256','support_sources','runtime_source_hashes'):
        m.require(native[name]==old[name],'Native recipe/support changed: '+name)
    for name,digest in native['source']['paths'].items():
        m.require(m.sha(HERE.parent/'qemu'/name)==digest,'Canonical native source differs')
        m.require(m.sha(m.NATIVE/name)==native['runtime_source_hashes'].get(name,digest),'Compiled native source differs')
    m.require(runtime['native_engine_record_sha256']==m.sha(B/'bionic-engine.json'),'Stale runtime record')
    m.require(runtime['packager_sha256']==m.sha(HERE/'package_runtime.py') and runtime['tools_record_sha256']==m.sha(B/'bionic-tools.json'),'Runtime recipe changed')
    old_runtime=m.load(previous/'runtime.json')
    m.require(set(runtime['files'])==set(old_runtime['files']),'Dependency inventory changed')
    for name,row in runtime['files'].items():
        if name!='libp2dengine.so':m.require(row==old_runtime['files'][name],'Dependency changed: '+name)
    m.require(storage==m.load(previous/'storage-runtime.json'),'Native storage publication helper changed')
    libraries={n:r['sha256'] for n,r in runtime['files'].items()}
    libraries['libp2dstorage.so']=storage['binary_sha256']
    for name,digest in libraries.items():
        path=B/('storage-runtime' if name=='libp2dstorage.so' else 'runtime')/name
        m.require(m.sha(path)==digest,'Library differs: '+name)
        loads=[line for line in subprocess.check_output(['readelf','-lW',str(path)],text=True).splitlines() if 'LOAD ' in line]
        m.require(loads and all(int(line.split()[-1],16)>=16384 for line in loads),'ELF alignment failed: '+name)
    apk=Path(app['signed_apk'])
    m.require(app['version']==VERSION and app['package']==PACKAGE and not app['test_only'] and app['apk_sha256']==m.sha(apk),'Wrong candidate identity')
    signature=m.validate_apk(apk,PACKAGE,False,libraries,m.sha(B/'dex/classes.dex'))
    with zipfile.ZipFile(old_apk) as old_zip,zipfile.ZipFile(apk) as new_zip:
        art=lambda z:{n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith(('res/','assets/')) or n=='resources.arsc'}
        m.require(art(old_zip)==art(new_zip),'Resources or artwork changed')
    with zipfile.ZipFile(old_source) as z:
        java_changed={p.name for p in (HERE/'src').rglob('*.java') if 'android/'+p.relative_to(HERE).as_posix() not in z.namelist() or z.read('android/'+p.relative_to(HERE).as_posix())!=p.read_bytes()}
    m.require(java_changed=={'Engine.java','GuestRam.java'},'Unexpected Java behavior scope')
    manifest=m.parse_manifest(apk)
    m.require(not manifest.get('instrumentation') and not manifest.get('provider'),'Test fixtures packaged')
    stage=Path(tempfile.mkdtemp(prefix='.seal-wm5-',dir=release.parent))
    try:
        delivered=stage/'Pocket2Droid-v1.0.2-test-WM5.apk'
        shutil.copy2(apk,delivered)
        source=stage/'Pocket2Droid-v1.0.2-test.Source.zip'
        print('APK signature, package, native identity and alignment pass; archiving source.',flush=True)
        inventory=snapshot(source,native,runtime,old_source)
        for name,digest in m.tested_source_hashes().items():m.require(inventory['android/'+name]==digest,'Frontend snapshot differs: '+name)
        for name,digest in native['source']['paths'].items():m.require(inventory['qemu-canonical-changes/'+name]==digest,'Native snapshot differs')
        for name in ('candidate-build.json','bionic-engine.json','runtime.json','bionic-tools.json','storage-runtime.json'):
            shutil.copy2(B/name,stage/name)
        shutil.copy2(Path(__file__),stage/'candidate-release-recipe.py')
        (stage/'candidate-signature.txt').write_text(signature)
        evidence=stage/'evidence';evidence.mkdir()
        for name in ('RESULT.json','RESULT.txt','production-source.diff','final-149-tests.log','final-ram-java.log','engine-art.log','checked-ram-native.log'):
            shutil.copy2(proof_root/name,evidence/name)
        shutil.copy2(proof_root/'matrix-e0e96cc58b54/contact.png',evidence/'host-boot-matrix.png')
        for name in ('checked-created.png','checked-reopened.png'):
            shutil.copy2(proof_root/'persistence-filebacked'/name,evidence/name)
        shutil.copy2(B/'bionic-native.log',evidence/'android-native-build.log')
        for p in (B/'release-wm5-test').iterdir():
            if p.is_file():shutil.copy2(p,evidence/p.name)
        shutil.copy2(B/'runtime/libp2dengine.so.unstripped',stage/'libp2dengine.so.unstripped')
        verification=dict(version=VERSION,version_code=CODE,package=PACKAGE,private_test_candidate=True,
            apk_sha256=m.sha(delivered),source_archive_sha256=m.sha(source),source_snapshot_files=len(inventory),
            original_signer=m.SIGNER,signature_verified=True,apk_and_elf_alignment_16k=True,
            exact_dex_and_native_identity=True,resources_unchanged=True,native_storage_helper_unchanged=True,
            native_changed_paths=sorted(changed),java_changed_files=sorted(java_changed),
            native_tests_passed=149,java_jni_checks_normal=29,java_jni_checks_fallback=32,engine_art_passed=True,
            host_wm5_boot_variants=4,host_wm6_control_boot=True,host_wm5_file_reopen=True,
            baseline_preserved=True,phone_modified=False,android_wm5_validation_pending=True,github_modified=False,
            performance_gain_claimed=False)
        (stage/'FINAL_VERIFICATION.json').write_text(json.dumps(verification,indent=2)+'\n')
        (stage/'INSTALL.txt').write_text('Pocket2Droid 1.0.2-test / code672, ARM64 Android7.0+.\n'
            'Exit the current ROM normally, then install this APK as an update. Do not uninstall or clear data.\n'
            'Import the WM5 QVGA PPC_USA.bin under a distinct filename, e.g. WM5_PPC_USA_QVGA.bin,\n'
            'so it does not replace an existing WM6 ROM. Choose240x320 guest resolution.\n'
            'Success: reach Today, create a folder in My Documents, use normal Exit, then reopen and find it.\n'
            'WM5 adds a128MiB retained RAM file in that ROM data folder, alongside its existing32MiB save.\n'
            'Keep both files and the .ready checkpoint. The shared StorageCard path remains unchanged.\n'
            'Report boot success and whether the folder survives. WM6 may be checked afterward normally.\n'
            'Local PC guest/ART checks passed; WM5 guest runtime on Android is not yet validated.\n'
            'Public1.0.1 and its source remain unchanged. No phone installation was performed by this build.\n')
        m.require(protected=={p.relative_to(previous).as_posix():m.sha(p) for p in previous.rglob('*') if p.is_file()},'Public release artifacts changed')
        (stage/'SHA256SUMS.txt').write_text(''.join(m.sha(p)+'  '+p.relative_to(stage).as_posix()+'\n' for p in sorted(stage.rglob('*')) if p.is_file()))
        m.publish_release(stage,release)
        print(json.dumps(dict(apk=str(release/delivered.name),**verification)),flush=True)
    finally:
        if stage.exists():
            m.require(stage.parent.resolve()==release.parent.resolve() and stage.name.startswith('.seal-wm5-'),'Unsafe stage cleanup')
            shutil.rmtree(stage)

if __name__=='__main__':main()
