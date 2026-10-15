"""Seal the authorized clock-fix test APK, preserving public v1.0 artifacts."""
from pathlib import Path
import hashlib, importlib.util, json, shutil, subprocess, tempfile, zipfile

HERE=Path(__file__).resolve().parent
B=HERE/'build'
PROJECT=HERE.parents[2]
PACKAGE='com.samsixx.pocket2droid'
VERSION='1.0.1-test'
CODE=670
spec=importlib.util.spec_from_file_location('release_integrity',HERE/'finalize_release.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.VERSION,m.VERSION_CODE=VERSION,CODE

def main():
    previous=PROJECT/'apk/1.0-samsixx'
    release=PROJECT/'apk/1.0.1-test'
    m.require(not release.exists(),'Never overwrite an existing release')
    protected={p.relative_to(previous).as_posix():m.sha(p) for p in previous.rglob('*') if p.is_file()}
    baseline_apk=previous/'Pocket2Droid-v1.0.apk'
    m.require(m.sha(baseline_apk)=='01d97050d5e3ec1d482d22b848398bb749cd84fe9003e1339f22322c9bc793e0','Public APK identity differs')
    m.require(m.sha(previous/'Pocket2Droid-v1.0 Source.zip')=='969d266d1b7f719308fce7bac32f0a36b2183cb567930b0414e8b91842b36b32','Public source identity differs')
    app,native,runtime,storage=(m.load(B/n) for n in ('candidate-build.json','bionic-engine.json','runtime.json','storage-runtime.json'))
    old=m.load(previous/'bionic-engine.json')
    changed={n for n,h in native['source']['paths'].items() if h!=old['source']['paths'].get(n)}
    m.require(changed=={'hw/misc/p2d-devemu-services.c'} and set(native['source']['paths'])==set(old['source']['paths']),'Unexpected native scope')
    for name in ('base',): m.require(native['source'][name]==old['source'][name],'Native base changed')
    for name in ('builder_sha256','platform','termux_patch_sha256','support_sources','runtime_source_hashes'):
        m.require(native[name]==old[name],'Native recipe/support changed: '+name)
    m.require(native['binary_sha256']==m.sha(B/'libp2dengine-bionic.so'),'Native binary record differs')
    for name,digest in native['source']['paths'].items():
        m.require(m.sha(HERE.parent/'qemu'/name)==digest,'Canonical native source differs: '+name)
        m.require(m.sha(m.NATIVE/name)==native['runtime_source_hashes'].get(name,digest),'Compiled source differs: '+name)
    for name,digest in native['runtime_source_hashes'].items(): m.require(m.sha(m.NATIVE/name)==digest,'Android adaptation differs')
    m.require(runtime['native_engine_record_sha256']==m.sha(B/'bionic-engine.json'),'Stale runtime record')
    m.require(runtime['packager_sha256']==m.sha(HERE/'package_runtime.py') and runtime['tools_record_sha256']==m.sha(B/'bionic-tools.json'),'Runtime recipes changed')
    old_runtime=m.load(previous/'runtime.json')
    m.require(set(runtime['files'])==set(old_runtime['files']),'Dependency inventory changed')
    for name,row in runtime['files'].items():
        if name!='libp2dengine.so': m.require(row==old_runtime['files'][name],'Dependency changed: '+name)
    m.require(storage==m.load(previous/'storage-runtime.json'),'Storage helper changed')
    m.require(storage['builder_sha256']==m.sha(HERE/'build_storage.py'),'Storage recipe changed')
    for name,digest in storage['sources'].items(): m.require(m.sha(HERE/name)==digest,'Storage source changed')
    libraries={n:r['sha256'] for n,r in runtime['files'].items()}
    libraries['libp2dstorage.so']=storage['binary_sha256']
    for name,digest in libraries.items():
        path=B/('storage-runtime' if name=='libp2dstorage.so' else 'runtime')/name
        m.require(m.sha(path)==digest,'Packaged library differs: '+name)
        loads=[line for line in subprocess.check_output(['readelf','-lW',str(path)],text=True).splitlines() if 'LOAD ' in line]
        m.require(loads and all(int(line.split()[-1],16)>=16384 for line in loads),'ELF alignment failed: '+name)
    apk=Path(app['signed_apk'])
    m.require(apk.parent.resolve()==B.resolve() and app['version']==VERSION and app['package']==PACKAGE
              and not app['test_only'] and app['apk_sha256']==m.sha(apk),'Wrong signed APK candidate')
    signature=m.validate_apk(apk,PACKAGE,False,libraries,m.sha(B/'dex/classes.dex'))
    manifest=m.parse_manifest(apk)
    m.require(not manifest.get('instrumentation') and not manifest.get('provider'),'Test fixture components packaged')
    with zipfile.ZipFile(baseline_apk) as baseline, zipfile.ZipFile(apk) as candidate:
        m.require(baseline.read('classes.dex')==candidate.read('classes.dex'),'Frontend behavior changed')
        art=lambda z:{n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith('res/') or n=='resources.arsc' or n.startswith('assets/')}
        m.require(art(baseline)==art(candidate),'Resources, artwork or loading GIF changed')
    with zipfile.ZipFile(previous/'Pocket2Droid-v1.0 Source.zip') as z:
        for path in (HERE/'src').rglob('*.java'):
            m.require(z.read('android/'+path.relative_to(HERE).as_posix())==path.read_bytes(),'Java source changed: '+path.name)
    proof_root=HERE.parent/'build/game-inspection/big-range-hunting-2'
    proof=m.load(proof_root/'RESULT.json')
    m.require(proof['source_sha256']==native['source']['paths']['hw/misc/p2d-devemu-services.c'],'Tested native source differs')
    m.require(sum(x['tests'] for x in proof['checks'])==19 and all(x['exit_code']==0 for x in proof['checks']),'Clock/device tests did not pass')
    for check in proof['checks']:
        path=Path(check['command'][1]); m.require(m.sha(path)==check['test_sha256'],'Clock/device test changed since validation')
    stage=Path(tempfile.mkdtemp(prefix='.seal-clock-test-',dir=release.parent))
    try:
        delivered=stage/'Pocket2Droid-v1.0.1-test-Clock-Fix.apk'
        shutil.copy2(apk,delivered)
        source=stage/'Pocket2Droid-v1.0.1-test-Source.zip'
        print('Signature, package, version, native identity and 16KiB alignment pass; archiving exact source.',flush=True)
        inventory=m.snapshot_sources(source,{'native':native,'runtime':runtime})
        with zipfile.ZipFile(source) as z:
            for name,digest in inventory.items(): m.require(hashlib.sha256(z.read(name)).hexdigest()==digest,'Archive mismatch: '+name)
            for name,digest in m.tested_source_hashes().items(): m.require(inventory['android/'+name]==digest,'Frontend archive mismatch')
            for name,digest in native['source']['paths'].items(): m.require(inventory['qemu-canonical-changes/'+name]==digest,'Native archive mismatch')
            m.require(z.read('tests/test_rtc_clock.py')==(HERE.parent/'tests/test_rtc_clock.py').read_bytes(),'RTC regression missing from source')
        for name in ('candidate-build.json','bionic-engine.json','runtime.json','bionic-tools.json','storage-runtime.json'):
            shutil.copy2(B/name,stage/name)
        shutil.copy2(Path(__file__),stage/'candidate-release-recipe.py')
        (stage/'candidate-signature.txt').write_text(signature)
        evidence=stage/'evidence'; evidence.mkdir()
        for name in ('RESULT.json','test_rtc_clock.py.log','test_devices.py.log','clock-code-comparison.json'):
            shutil.copy2(proof_root/name,evidence/name)
        shutil.copy2(proof_root/'run-20261015T114623Z-62037313/main-menu.png',evidence/'host-game-main-menu.png')
        for path in (B/'release-clock-test').iterdir():
            if path.is_file(): shutil.copy2(path,evidence/path.name)
        shutil.copy2(B/'bionic-native.log',evidence/'android-native-build.log')
        shutil.copy2(B/'runtime/libp2dengine.so.unstripped',stage/'libp2dengine.so.unstripped')
        verification=dict(version=VERSION,version_code=CODE,package=PACKAGE,app_name='Pocket2Droid',private_test_candidate=True,
            apk_sha256=m.sha(delivered),source_archive_sha256=m.sha(source),source_snapshot_files=len(inventory),
            original_signer=m.SIGNER,signature_verified=True,apk_and_elf_alignment_16k=True,exact_dex_and_native_identity=True,
            frontend_resources_and_storage_unchanged=True,native_changed_paths=sorted(changed),host_tests_passed=19,
            host_game_reached_main_menu=True,baseline_preserved=True,phone_modified=False,android_validation_pending=True,
            github_modified=False,performance_gain_claimed=False)
        (stage/'FINAL_VERIFICATION.json').write_text(json.dumps(verification,indent=2)+'\n')
        (stage/'INSTALL.txt').write_text('Pocket2Droid 1.0.1-test (670), ARM64 Android7.0+.\n'
            'Install as an update to com.samsixx.pocket2droid, using the original signing certificate.\n'
            'Exit the running ROM/app normally before installing. Keep app data; no uninstall or guest reset.\n'
            'Test: launch Big Range Hunting 2 on the same ROM. Success means passing Gameloft logo and reaching the menu.\n'
            'Then exit/pause normally to retain guest state. Report whether it passes the logo.\n'
            'This candidate corrects the frozen emulated calendar clock. No gameplay speed claim.\n'
            'Public v1.0 preserved. No phone installation or Android runtime test performed by this build.\n')
        m.require(protected=={p.relative_to(previous).as_posix():m.sha(p) for p in previous.rglob('*') if p.is_file()},'Public v1.0 artifacts changed')
        (stage/'SHA256SUMS.txt').write_text(''.join(m.sha(p)+'  '+p.relative_to(stage).as_posix()+'\n' for p in sorted(stage.rglob('*')) if p.is_file()))
        m.publish_release(stage,release)
        print(json.dumps(dict(apk=str(release/delivered.name),**verification)),flush=True)
    finally:
        if stage.exists():
            m.require(stage.parent.resolve()==release.parent.resolve() and stage.name.startswith('.seal-clock-test-'),'Unsafe staging cleanup')
            shutil.rmtree(stage)

if __name__=='__main__': main()
