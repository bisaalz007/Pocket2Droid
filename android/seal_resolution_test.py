"""Seal the authorized custom-resolution test without replacing prior releases."""
from pathlib import Path
import hashlib,importlib.util,json,shutil,stat,subprocess,tempfile,zipfile

HERE=Path(__file__).resolve().parent
B=HERE/'build'
PROJECT=HERE.parents[2]
VERSION,CODE='1.0.2-test3',674
spec=importlib.util.spec_from_file_location('wm5_snapshot',HERE/'seal_wm5_test.py')
wm5=importlib.util.module_from_spec(spec);spec.loader.exec_module(wm5)
wm5.VERSION,wm5.CODE=VERSION,CODE
m=wm5.m;m.VERSION,m.VERSION_CODE=VERSION,CODE

def main():
    prior=PROJECT/'apk/1.0.2-test2';release=PROJECT/'apk'/VERSION
    m.require(not release.exists(),'Never overwrite a test release')
    old_apk=prior/'Pocket2Droid-v1.0.2-test2-Restart.apk'
    old_source=prior/'Pocket2Droid-v1.0.2-test2.Source.zip'
    protected={p.relative_to(prior).as_posix():m.sha(p) for p in prior.rglob('*') if p.is_file()}
    m.require(m.sha(old_apk)=='246d09a085f2a2832901fc041c8ff8e9795fe48f5108a9a4bb2497f678af3450','Prior APK changed')
    m.require(m.sha(old_source)=='141e974755d7d22ffbf4fdcde4104658664f05be46e7613e7ab6ec170d0b8726','Prior source changed')
    proof=B/'custom-resolution';result=m.load(proof/'RESULT.json')
    for name,digest in result['source_sha256'].items():m.require(m.sha(HERE/name)==digest,'Tested source changed: '+name)
    for name,digest in result['native_source_sha256'].items():m.require(m.sha(HERE.parent/'qemu'/name)==digest,'Tested native source changed: '+name)
    m.require(result['native_tests']==151 and result['real_android_ui_checks']==60 and result['app_resolution_cap'] is None,'Missing custom-resolution verification')
    m.require('PASS 60 real Android custom resolution checks' in (proof/'ui/granted.log').read_text(),'Actual UI/display checks missing')
    m.require('Ran 151 tests' in (proof/'uncapped-native-tests.log').read_text() and (proof/'uncapped-native-tests.log').read_text().rstrip().endswith('OK'),'Native suite failed')
    m.require('PASS actual Engine ART' in (proof/'engine-art.log').read_text(),'Actual Engine checks missing')
    app,native,runtime,storage=(m.load(B/n) for n in ('candidate-build.json','bionic-engine.json','runtime.json','storage-runtime.json'))
    old_native=m.load(prior/'bionic-engine.json');old_runtime=m.load(prior/'runtime.json')
    changed={n for n,h in native['source']['paths'].items() if old_native['source']['paths'].get(n)!=h}
    m.require(changed==set(result['production_native_changed']),'Native scope differs from reviewed integration')
    m.require(set(native['source']['paths'])==set(old_native['source']['paths']) and native['source']['base']==old_native['source']['base'],'Native inventory/base changed')
    m.require(m.sha(B/'libp2dengine-bionic.so')==native['binary_sha256'],'Native output differs')
    for name,digest in native['source']['paths'].items():
        m.require(m.sha(HERE.parent/'qemu'/name)==digest,'Canonical source changed: '+name)
        m.require(m.sha(m.NATIVE/name)==native['runtime_source_hashes'].get(name,digest),'Compiled source changed: '+name)
    m.require(runtime['native_engine_record_sha256']==m.sha(B/'bionic-engine.json'),'Stale runtime metadata')
    m.require(set(runtime['files'])==set(old_runtime['files']),'Runtime dependency inventory changed')
    for name,row in runtime['files'].items():
        if name!='libp2dengine.so':m.require(row==old_runtime['files'][name],'Dependency changed: '+name)
    m.require(storage==m.load(prior/'storage-runtime.json'),'Storage publication helper changed')
    libraries={n:r['sha256'] for n,r in runtime['files'].items()};libraries['libp2dstorage.so']=storage['binary_sha256']
    for name,digest in libraries.items():
        path=B/('storage-runtime' if name=='libp2dstorage.so' else 'runtime')/name
        m.require(m.sha(path)==digest,'Native payload identity differs')
        loads=[s for s in subprocess.check_output(['readelf','-lW',str(path)],text=True).splitlines() if 'LOAD ' in s]
        m.require(loads and all(int(s.split()[-1],16)>=16384 for s in loads),'ELF alignment failed: '+name)
    apk=Path(app['signed_apk'])
    m.require(app['version']==VERSION and app['package']=='com.samsixx.pocket2droid' and not app['test_only'] and app['apk_sha256']==m.sha(apk),'Candidate identity differs')
    signature=m.validate_apk(apk,'com.samsixx.pocket2droid',False,libraries,m.sha(B/'dex/classes.dex'))
    manifest=m.parse_manifest(apk);m.require(not manifest.get('instrumentation') and not manifest.get('provider'),'Test fixtures packaged')
    with zipfile.ZipFile(old_apk) as old,zipfile.ZipFile(apk) as new:
        art=lambda z:{n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith(('res/','assets/')) or n=='resources.arsc'}
        m.require(art(old)==art(new),'Resources/artwork changed')
    with zipfile.ZipFile(old_source) as old:
        java_changed={p.name for p in (HERE/'src').rglob('*.java') if old.read('android/'+p.relative_to(HERE).as_posix())!=p.read_bytes()}
    m.require(java_changed==set(result['production_java_changed']),'Unexpected Java scope')
    stage=Path(tempfile.mkdtemp(prefix='.seal-resolution-',dir=release.parent))
    try:
        delivered=stage/('Pocket2Droid-v'+VERSION+'-Custom-Resolution.apk');shutil.copy2(apk,delivered)
        source=stage/('Pocket2Droid-v'+VERSION+'.Source.zip')
        print('Original signer, identity, libraries and alignment verified; sealing exact source.',flush=True)
        inventory=wm5.snapshot(source,native,runtime,old_source,
            'This test retains WM5/Restart and adds per-ROM Custom resolution width/height.\n'
            'No fixed app-defined width/height cap; addressable memory and guest hardware still apply.\n'
            'Frame transport grows under lock; reset never shrinks it; a shared Java gate protects session handoff.\n'
            '151 native tests and60 real Android UI/display checks pass. Individual-ROM custom-size boot\n'
            'and Android ARM64 guest rendering remain pending. Version1.0.2-test3/code674.\n')
        with zipfile.ZipFile(source) as z:
            m.require(len(z.namelist())==len(set(z.namelist())),'Duplicate source archive entries')
            links=sum(stat.S_ISLNK(i.external_attr>>16) for i in z.infolist())
        for name,digest in m.tested_source_hashes().items():m.require(inventory['android/'+name]==digest,'Source snapshot differs: '+name)
        for name,digest in native['source']['paths'].items():m.require(inventory['qemu-canonical-changes/'+name]==digest,'Native snapshot differs')
        for name in ('candidate-build.json','bionic-engine.json','runtime.json','bionic-tools.json','storage-runtime.json'):shutil.copy2(B/name,stage/name)
        shutil.copy2(Path(__file__),stage/'candidate-release-recipe.py');(stage/'candidate-signature.txt').write_text(signature)
        evidence=stage/'evidence';evidence.mkdir()
        for name in ('RESULT.json','production.diff','uncapped-native-tests.log','uncapped-green-host.log','uncapped-fallback-host.log','uncapped-java-frame.log','uncapped-green-frame.log','frame-reset.log','engine-art.log','handoff-red.log','native-host-build.log','native-android-build.log','custom-remembered.png'):
            shutil.copy2(proof/name,evidence/name)
        for name in ('granted.log','granted-sources.json'):shutil.copy2(proof/'ui'/name,evidence/name)
        shutil.copy2(B/'runtime/libp2dengine.so.unstripped',stage/'libp2dengine.so.unstripped')
        record=dict(version=VERSION,version_code=CODE,package='com.samsixx.pocket2droid',apk_sha256=m.sha(delivered),source_archive_sha256=m.sha(source),source_snapshot_files=len(inventory),source_symlinks=links,original_signer=m.SIGNER,signature_verified=True,apk_and_elf_alignment_16k=True,exact_dex_and_native_identity=True,resources_unchanged=True,native_storage_helper_unchanged=True,java_changed_files=sorted(java_changed),native_changed_paths=sorted(changed),native_tests=151,android_ui_display_checks=60,engine_art_passed=True,app_resolution_cap=None,phone_modified=False,phone_validation_pending=True,github_modified=False,baseline_preserved=True)
        (stage/'FINAL_VERIFICATION.json').write_text(json.dumps(record,indent=2)+'\n')
        (stage/'INSTALL.txt').write_text('Pocket2Droid1.0.2-test3/code674:Custom resolution+Restart+WM5,ARM64 Android7.0+.\n'
            'Exit the current ROM normally,then install as an update. Do not uninstall or clear app data.\n'
            'Open ROM settings > Guest resolution > Custom…,enter width/height,Save,then Start.\n'
            'Choose a ROM-supported size first,e.g.640x480 for a compatible Pocket PC ROM.\n'
            'Success:the OS reaches its desktop at the chosen guest size and touch aligns correctly.\n'
            'Use Back > Restart once;the same ROM should reboot with its stored files intact.\n'
            'Cancel or invalid input must retain the previous settings. Presets remain available.\n'
            'No app-defined fixed resolution cap;ROM/driver/hardware and actual memory still constrain working sizes.\n'
            'If a size does not boot,Exit normally and choose the prior working preset;do not reset/delete saves.\n'
            'Keep all WM5 retained RAM,.ready and ram-fmd.bin files together.\n'
            'PC native/Android frontend checks pass;real phone custom-resolution boot/rendering is pending.\n')
        m.require(protected=={p.relative_to(prior).as_posix():m.sha(p) for p in prior.rglob('*') if p.is_file()},'Prior release modified')
        (stage/'SHA256SUMS.txt').write_text(''.join(m.sha(p)+'  '+p.relative_to(stage).as_posix()+'\n' for p in sorted(stage.rglob('*')) if p.is_file()))
        m.publish_release(stage,release);print(json.dumps(dict(apk=str(release/delivered.name),**record)),flush=True)
    finally:
        if stage.exists():
            m.require(stage.parent.resolve()==release.parent.resolve() and stage.name.startswith('.seal-resolution-'),'Unsafe stage cleanup');shutil.rmtree(stage)

if __name__=='__main__':main()
