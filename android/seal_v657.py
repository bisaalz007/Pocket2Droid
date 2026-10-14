"""Seal the V6.57 audio-scheduler candidate; phone validation stays explicitly pending."""
from pathlib import Path
import hashlib, importlib.util, json, shutil, subprocess, tempfile, zipfile

HERE = Path(__file__).resolve().parent
BUILD = HERE / 'build'
PROJECT = HERE.parents[2]
ROOT = HERE.parent
spec = importlib.util.spec_from_file_location('release_tools', HERE / 'finalize_release.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.VERSION, m.VERSION_CODE = '6.57', 657
sha, load, require = m.sha, m.load, m.require

def main():
    previous = PROJECT / 'apk/6.56'
    release = PROJECT / 'apk/6.57'
    require(not release.exists(), 'Preserve existing V6.57; never overwrite')
    baseline_hashes = {p.name: sha(p) for p in previous.iterdir() if p.is_file()}
    require(baseline_hashes['Pocket2Droid-V6.56-TCG-SIGNED.apk'] ==
            '326055d8152189750892a0586cee18322d0bd39229afc6b86b799c712fe89bee', 'Baseline APK changed')
    app, native, runtime, storage = (load(BUILD / n) for n in
        ('candidate-build.json','bionic-engine.json','runtime.json','storage-runtime.json'))
    old_native, old_runtime, old_storage = (load(previous / n) for n in
        ('bionic-engine.json','runtime.json','storage-runtime.json'))
    require(app['version']=='6.57' and app['test_only'] is False, 'Wrong candidate')
    apk = Path(app['signed_apk'])
    require(apk.resolve().parent == BUILD.resolve() and sha(apk)==app['apk_sha256'], 'Candidate APK changed')
    require(native['binary_sha256']==sha(BUILD/'libp2dengine-bionic.so'), 'Compiler output changed')
    require(native['builder_sha256']==sha(HERE/'build_bionic.py'), 'Compiler recipe changed')
    require(native['source']['base']==old_native['source']['base'], 'CPU base changed')
    for key, base in (('source',ROOT/'qemu'),('runtime_source_hashes',m.NATIVE)):
        current = native[key]['paths'] if key=='source' else native[key]
        old = old_native[key]['paths'] if key=='source' else old_native[key]
        require(set(current)==(set(old)|{'include/qemu/timer.h','util/qemu-timer.c'} if key=='source' else set(old)), 'Native source inventory changed')
        require({n for n in current if current[n]!=old.get(n)}==({'hw/dma/p2d-iis-dma.c','hw/misc/p2d-devemu-services.c','include/qemu/timer.h','util/qemu-timer.c'} if key=='source' else set()), 'Unexpected native change')
        for name,digest in current.items():
            require(sha(m.local(name,base))==digest, 'Native source changed: '+name)
    for name,digest in native['source']['paths'].items():
        expected=native['runtime_source_hashes'].get(name,digest)
        require(sha(m.local(name,m.NATIVE))==expected, 'Compiled source cache differs: '+name)
    for key in ('termux_patch_sha256','support_sources','builder_sha256'):
        require(native[key]==old_native[key], 'Android compatibility input changed: '+key)
    patch=(BUILD/'termux-reference/0016-Add-workaround-for-tagged-pointers-on-Android-12.patch').read_text().replace('#ifdef __TERMUX__','#ifdef __ANDROID__')
    require(hashlib.sha256(patch.encode()).hexdigest()==native['termux_patch_sha256'], 'Heap tag patch changed')
    for name,digest in native['support_sources'].items():
        require(sha(m.local(name,BUILD/'termux-reference/setjmp-aarch64'))==digest, 'Setjmp source changed')
    require(runtime['native_engine_record_sha256']==sha(BUILD/'bionic-engine.json'), 'Runtime uses stale native record')
    require(runtime['packager_sha256']==sha(HERE/'package_runtime.py'), 'Runtime packager changed')
    require(runtime['tools_record_sha256']==sha(BUILD/'bionic-tools.json')==old_runtime['tools_record_sha256'], 'Dependency inputs changed')
    require(set(runtime['files'])==set(old_runtime['files']), 'Dependency inventory changed')
    libraries={}
    for name,record in runtime['files'].items():
        require(sha(BUILD/'runtime'/name)==record['sha256'], 'Runtime library changed')
        require(sha(BUILD/'runtime'/(name+'.unstripped'))==record['symbols_sha256'], 'Symbols changed')
        if name!='libp2dengine.so':
            require(record==old_runtime['files'][name], 'Non-engine library changed')
        for line in subprocess.check_output(['readelf','-lW',str(BUILD/'runtime'/name)],text=True).splitlines():
            if 'LOAD ' in line: require(int(line.split()[-1],16)>=16384,'ELF alignment failed')
        libraries[name]=record['sha256']
    require(runtime['files']['libp2dengine.so']['input_sha256']==native['binary_sha256'], 'Packaged engine has wrong input')
    require(storage==old_storage, 'Storage helper build changed')
    helper=m.local(storage['binary_path'])
    require(sha(helper)==storage['binary_sha256'], 'Storage helper changed')
    require(sha(HERE/'build_storage.py')==storage['builder_sha256'], 'Storage builder changed')
    for name,digest in storage['sources'].items():
        require(sha(m.local(name))==digest, 'Storage source changed')
    libraries[helper.name]=storage['binary_sha256']
    require(app['engine_sha256']==libraries['libp2dengine.so'] and app['storage_helper_sha256']==libraries[helper.name], 'Build record differs')
    source_hashes=m.tested_source_hashes()
    with zipfile.ZipFile(previous/'Pocket2Droid-V6.56-TCG-Source.zip') as z:
        for name,digest in source_hashes.items():
            current=m.local(name).read_bytes()
            if name=='AndroidManifest.xml':
                current=current.replace(b'6.57',b'6.56').replace(b'versionCode="657"',b'versionCode="656"')
            if name=='src/com/samsixx/wm6android/MainActivity.java':
                current=current.replace(b'Pocket2Droid 6.57.',b'Pocket2Droid 6.56.')
            require(current==z.read('android/'+name), 'Unexpected Android behavior change: '+name)
    verification=load(ROOT/'results/audio-scheduling/RESULT.json')
    verified_scope=load(ROOT/'results/audio-scheduling/SCOPE.json')
    require(verification['status']=='LOCAL_INTEGRATION_ACCEPTED_UNRELEASED', 'Scheduler result not accepted')
    require(verification['correctness']['host_checks']==96, 'Host suite incomplete')
    require(verified_scope['android_binary_sha256']==native['binary_sha256'], 'Android binary differs from accepted candidate')
    require(verified_scope['changed_native_files_vs_signed_v656']==[
        'hw/dma/p2d-iis-dma.c','hw/misc/p2d-devemu-services.c','include/qemu/timer.h','util/qemu-timer.c'], 'Unexpected tested scope')
    for name,digest in verified_scope['final_source_hashes'].items():
        require(native['source']['paths'][name]==digest, 'Compiled scheduler differs from tested source')
    tests=(ROOT/'results/audio-scheduling/final-host-tests.log').read_text()
    require('Ran 96 tests' in tests and tests.rstrip().endswith('OK'), 'Host suite did not pass')
    boot=load(Path(verification['boot']['run'])/'session-final.json')
    require(boot['normal_exit'] and boot['original_inputs_unchanged'] and boot['original_rom_unchanged'], 'Copied guest boot/save guard failed')
    require(boot['qemu_sha256']==verified_scope['host_binary_sha256'], 'Host boot used another candidate')
    signature=m.validate_apk(apk,'com.samsixx.wm6android',False,libraries,sha(BUILD/'dex/classes.dex'))
    with zipfile.ZipFile(apk) as z:
        require({n for n in z.namelist() if n.startswith('assets/')}=={'assets/QEMU-COPYING.txt'}, 'Unexpected APK assets')
    stage=Path(tempfile.mkdtemp(prefix='.seal-6.57-',dir=release.parent))
    try:
        delivered=stage/'Pocket2Droid-V6.57-TCG-SIGNED.apk'
        shutil.copy2(apk,delivered)
        shutil.copy2(Path(__file__),stage/'candidate-release-recipe.py')
        for name in ('candidate-build.json','bionic-engine.json','runtime.json','bionic-tools.json','storage-runtime.json'):
            shutil.copy2(BUILD/name,stage/name)
        (stage/'candidate-signature.txt').write_text(signature)
        evidence={'version':'6.57','source_hashes':source_hashes,'validation_scope':'Host-native candidate; Android boot/gameplay/save and S25 regression pending',
                  'host_verification':verification,'android_interfaces_match_v656_except_version':True,
                  'speaker_output_enabled':False,'s25_validation_pending':True,
                  'performance_gain_claimed':False,'baseline_artifacts':baseline_hashes}
        (stage/'RELEASE_EVIDENCE.json').write_text(json.dumps(evidence,indent=2)+'\n')
        evidence_dir=stage/'evidence';evidence_dir.mkdir()
        for name in ('RESULT.json','SCOPE.json','final-source.diff','final-host-tests.log','host-benchmark.json','android-native.log'):
            shutil.copy2(ROOT/'results/audio-scheduling'/name,evidence_dir/name)
        shutil.copy2(Path(verification['boot']['run'])/'session-final.json',evidence_dir/'copied-guest-boot.json')
        sources=stage/'Pocket2Droid-V6.57-TCG-Source.zip'
        inventory=m.snapshot_sources(sources,dict(native=native,runtime=runtime))
        with zipfile.ZipFile(sources) as z:
            require('tests/reference/v656-iis-dma.c' in z.namelist(),'Frozen media regression reference missing from snapshot')
            require(hashlib.sha256(z.read('tests/reference/v656-iis-dma.c')).hexdigest()=='dcdabe28838723a420972260c132e6f51922ba5d9e533cace3e2a69883fa7a36','Frozen reference changed')
            for name,digest in inventory.items():
                require(hashlib.sha256(z.read(name)).hexdigest()==digest,'Source archive identity mismatch')
        for name,digest in native['source']['paths'].items():
            require(inventory['qemu-canonical-changes/'+name]==digest,'Canonical archive mismatch')
        for name,digest in native['runtime_source_hashes'].items():
            require(inventory['qemu-android-exact/'+name]==digest,'Android native archive mismatch')
        symbols=stage/'Pocket2Droid-V6.57-TCG-Symbols.zip'
        with zipfile.ZipFile(symbols,'w',zipfile.ZIP_DEFLATED,compresslevel=4) as z:
            for name in runtime['files']:
                z.write(BUILD/'runtime'/(name+'.unstripped'),name+'.unstripped')
            z.write(helper,helper.name+'.unstripped')
        with zipfile.ZipFile(symbols) as z:
            require(z.testzip() is None,'Symbols CRC failed')
            for name,record in runtime['files'].items():
                require(hashlib.sha256(z.read(name+'.unstripped')).hexdigest()==record['symbols_sha256'],'Symbol identity failed')
        require(sha(delivered)==app['apk_sha256'],'Delivered APK changed')
        require(baseline_hashes=={p.name:sha(p) for p in previous.iterdir() if p.is_file()},'Baseline artifacts changed')
        scope=dict(app,delivered_apk=delivered.name,source_archive_sha256=sha(sources),
                   symbols_archive_sha256=sha(symbols),source_snapshot_files=len(inventory),
                   phone_validation_pending=True,exact_game_fps_known=False,baseline_version='6.56')
        (stage/'RELEASE_SCOPE.json').write_text(json.dumps(scope,indent=2)+'\n')
        (stage/'FINAL_VERIFICATION.json').write_text(json.dumps({'signature':True,'native_identity':True,'source_identity':True,'alignment_16k':True,'baseline_preserved':True,'phone_validation_pending':True},indent=2)+'\n')
        sums=[p for p in sorted(stage.rglob('*')) if p.is_file()]
        (stage/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+str(p.relative_to(stage))+'\n' for p in sums))
        m.publish_release(stage,release)
        print(json.dumps(scope,indent=2),flush=True)
    finally:
        if stage.exists():
            require(stage.resolve().parent==release.parent.resolve() and stage.name.startswith('.seal-6.57-'),'Unsafe cleanup path')
            shutil.rmtree(stage)

if __name__=='__main__': main()
