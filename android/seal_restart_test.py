"""Seal the requested Restart menu update; preserve the prior WM5 test."""
from pathlib import Path
import hashlib,importlib.util,json,shutil,tempfile,zipfile

HERE=Path(__file__).resolve().parent
B=HERE/'build'
PROJECT=HERE.parents[2]
VERSION='1.0.2-test2'
CODE=673
spec=importlib.util.spec_from_file_location('wm5_release',HERE/'seal_wm5_test.py')
wm5=importlib.util.module_from_spec(spec);spec.loader.exec_module(wm5)
wm5.VERSION,wm5.CODE=VERSION,CODE
m=wm5.m;m.VERSION,m.VERSION_CODE=VERSION,CODE

def main():
    baseline=PROJECT/'apk/1.0.2-test'
    release=PROJECT/'apk/1.0.2-test2'
    m.require(not release.exists(),'Never overwrite a testing release')
    protected={p.relative_to(baseline).as_posix():m.sha(p) for p in baseline.rglob('*') if p.is_file()}
    old_apk=baseline/'Pocket2Droid-v1.0.2-test-WM5.apk'
    old_source=baseline/'Pocket2Droid-v1.0.2-test.Source.zip'
    m.require(m.sha(old_apk)=='9ae2f20e67271f58ee01121767a6bbd79df4988fcfdd7811c1bb82a4186ccc9f','Prior APK changed')
    m.require(m.sha(old_source)=='f250822c215bc7ff0591f251735b3357bf6a16b3cbcd7b0e438a500ac3beb7c2','Prior source changed')
    proof=B/'restart-tests'
    m.require('PASS 48 real Android frontend lifecycle checks' in (proof/'green.log').read_text(),'Restart lifecycle checks missing')
    m.require('Restart appears immediately above Exit' in (proof/'red.log').read_text(),'Missing red regression evidence')
    for name,digest in m.load(proof/'green-sources.json').items():
        m.require(m.sha(HERE/name)==digest,'Tested Java source differs: '+name)
    app=m.load(B/'candidate-build.json')
    native,runtime,storage=(m.load(B/n) for n in ('bionic-engine.json','runtime.json','storage-runtime.json'))
    for name in ('bionic-engine.json','runtime.json','storage-runtime.json'):
        m.require(m.load(B/name)==m.load(baseline/name),'Native/runtime inputs changed: '+name)
    for name,digest in native['source']['paths'].items():
        m.require(m.sha(HERE.parent/'qemu'/name)==digest,'Native source changed: '+name)
    libraries={n:r['sha256'] for n,r in runtime['files'].items()}
    libraries['libp2dstorage.so']=storage['binary_sha256']
    apk=Path(app['signed_apk'])
    m.require(app['version']==VERSION and app['package']=='com.samsixx.pocket2droid' and not app['test_only'] and app['apk_sha256']==m.sha(apk),'Wrong test update')
    signature=m.validate_apk(apk,'com.samsixx.pocket2droid',False,libraries,m.sha(B/'dex/classes.dex'))
    manifest=m.parse_manifest(apk)
    m.require(not manifest.get('instrumentation') and not manifest.get('provider'),'Test fixtures packaged')
    with zipfile.ZipFile(old_apk) as old,zipfile.ZipFile(apk) as new:
        fixed=lambda z:{n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith(('lib/','res/','assets/')) or n=='resources.arsc'}
        m.require(fixed(old)==fixed(new),'Native libraries/resources differ from verified WM5 candidate')
    with zipfile.ZipFile(old_source) as old:
        changed={p.name for p in (HERE/'src').rglob('*.java') if old.read('android/'+p.relative_to(HERE).as_posix())!=p.read_bytes()}
    m.require(changed=={'EmulatorActivity.java'},'Unexpected application behavior scope')
    stage=Path(tempfile.mkdtemp(prefix='.seal-restart-',dir=release.parent))
    try:
        delivered=stage/'Pocket2Droid-v1.0.2-test2-Restart.apk';shutil.copy2(apk,delivered)
        source=stage/'Pocket2Droid-v1.0.2-test2.Source.zip'
        print('Signature, package, version, unchanged native payload and alignment pass; sealing source.',flush=True)
        inventory=wm5.snapshot(source,native,runtime,old_source,
            'This test adds Restart above Exit. It closes/synchronizes the current session before reopening\n'
            'the same ROM screen. Save failure blocks restart. Engine/native behavior is unchanged.\n'
            '48 Android frontend checks pass; the Start handoff test blocks real native launch with SessionGuard.\n'
            'A phone restart/boot check remains pending.\n')
        for name,digest in m.tested_source_hashes().items():m.require(inventory['android/'+name]==digest,'Source snapshot differs: '+name)
        for name in ('candidate-build.json','bionic-engine.json','runtime.json','bionic-tools.json','storage-runtime.json'):
            shutil.copy2(B/name,stage/name)
        shutil.copy2(Path(__file__),stage/'candidate-release-recipe.py')
        (stage/'candidate-signature.txt').write_text(signature)
        evidence=stage/'evidence';evidence.mkdir()
        for name in ('red.log','green.log','green-sources.json'):shutil.copy2(proof/name,evidence/name)
        for p in (B/'release-restart-test').iterdir():
            if p.is_file():shutil.copy2(p,evidence/p.name)
        shutil.copy2(B/'runtime/libp2dengine.so.unstripped',stage/'libp2dengine.so.unstripped')
        record=dict(version=VERSION,version_code=CODE,package='com.samsixx.pocket2droid',
            apk_sha256=m.sha(delivered),source_archive_sha256=m.sha(source),source_snapshot_files=len(inventory),
            original_signer=m.SIGNER,signature_verified=True,apk_and_elf_alignment_16k=True,
            native_payload_identical_to='1.0.2-test',resources_unchanged=True,changed_java_files=sorted(changed),
            android_frontend_checks=48,save_failure_blocks_restart=True,same_rom_screen_handoff_checked=True,
            actual_new_guest_process_tested=False,review_blockers=0,prior_candidate_preserved=True,
            phone_modified=False,phone_validation_pending=True,github_modified=False)
        (stage/'FINAL_VERIFICATION.json').write_text(json.dumps(record,indent=2)+'\n')
        (stage/'INSTALL.txt').write_text('Pocket2Droid1.0.2-test2/code673:Restart menu update.\n'
            'Exit the current ROM normally,then install this APK as an update without uninstalling/clearing data.\n'
            'Inside Windows Mobile,press Android Back,then Restart immediately above Exit.\n'
            'The current session synchronizes and closes,then the same ROM reopens in the same screen.\n'
            'Confirm that it boots again and existing installed files/folders remain.\n'
            'Save failure blocks automatic reopening. No new ROM or save format is introduced.\n'
            'Native engine,WM5 support,resources and signer match the previous WM5 test.\n'
            '48 PC Android frontend checks pass;real phone Restart validation remains pending.\n')
        m.require(protected=={p.relative_to(baseline).as_posix():m.sha(p) for p in baseline.rglob('*') if p.is_file()},'Prior candidate changed')
        (stage/'SHA256SUMS.txt').write_text(''.join(m.sha(p)+'  '+p.relative_to(stage).as_posix()+'\n' for p in sorted(stage.rglob('*')) if p.is_file()))
        m.publish_release(stage,release)
        print(json.dumps(dict(apk=str(release/delivered.name),**record)),flush=True)
    finally:
        if stage.exists():
            m.require(stage.parent.resolve()==release.parent.resolve() and stage.name.startswith('.seal-restart-'),'Unsafe stage cleanup')
            shutil.rmtree(stage)

if __name__=='__main__':main()
