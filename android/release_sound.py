"""Seal current V6.60 sound evidence; preserve V6.59 and original identity."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,shutil,subprocess,tempfile,zipfile
HERE=Path(__file__).resolve().parent;BUILD=HERE/'build';ROOT=HERE.parent;PROJECT=ROOT.parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
m=module('release_integrity',HERE/'finalize_release.py');m.VERSION,m.VERSION_CODE='6.60',660
checks=module('sound_evidence',HERE/'tests/audio_release_checks.py')
sha,load,require=m.sha,m.load,m.require
def log(p):
    data=p.read_bytes();return data.decode('utf-16' if data[:2] in (b'\xff\xfe',b'\xfe\xff') else 'utf-8-sig')
def main():
    p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,required=True);a=p.parse_args()
    previous=PROJECT/'apk/6.59';release=PROJECT/'apk/6.60'
    require(not release.exists(),'Preserve existing V6.60; never overwrite')
    baseline={p.name:sha(p) for p in previous.iterdir() if p.is_file()}
    require(baseline['Pocket2Droid-V6.59-TCG-SIGNED.apk']=='1d3ef5f74261eb372f0ea812164e39b23e60b630dc48a616f3c238cf29ba3415','Baseline APK changed')
    app,native,runtime,storage,smoke=(load(BUILD/n) for n in ('candidate-build.json','bionic-engine.json','runtime.json','storage-runtime.json','smoke-build.json'))
    require(app['version']=='6.60' and app['test_only'] is False and app['previous_engine_packaged'] is False,'Wrong production candidate')
    require(smoke['version']=='6.60' and smoke['test_only'] and smoke['package']=='com.samsixx.p2dtest','Wrong disposable candidate')
    apk=Path(app['signed_apk']);smoke_apk=Path(smoke['signed_apk'])
    for path,record in [(apk,app),(smoke_apk,smoke)]:
        require(path.resolve().parent==BUILD.resolve() and sha(path)==record['apk_sha256'],'Candidate APK changed')
    old_native,old_runtime=load(previous/'bionic-engine.json'),load(previous/'runtime.json')
    native_changes={n for n,d in native['source']['paths'].items() if old_native['source']['paths'].get(n)!=d}
    allowed_native={'hw/arm/pocket2droid-devemu.c','hw/dma/p2d-iis-dma.c','hw/dma/p2d-audio.c','include/hw/arm/p2d-audio.h','hw/dma/meson.build'}
    require(native['source']['base']==old_native['source']['base'] and native_changes==allowed_native and set(old_native['source']['paths'])<=set(native['source']['paths']),'Unexpected CPU/MMU/JIT/IRQ/storage/display source change')
    for field in ('builder_sha256','termux_patch_sha256','support_sources'):
        require(native[field]==old_native[field],'Native recipe/support changed: '+field)
    require(set(runtime['files'])==set(old_runtime['files']),'Runtime dependency set changed')
    for name,record in runtime['files'].items():
        if name!='libp2dengine.so':require(record==old_runtime['files'][name],'Dependency changed: '+name)
    require(storage==load(previous/'storage-runtime.json'),'Save publication helper changed')
    require(native['binary_sha256']==sha(BUILD/'libp2dengine-bionic.so'),'Compiler output changed')
    require(native['builder_sha256']==sha(HERE/'build_bionic.py'),'Compiler recipe changed')
    for name,digest in native['source']['paths'].items():
        require(sha(m.local(name,ROOT/'qemu'))==digest,'Canonical native source changed: '+name)
        require(sha(m.local(name,m.NATIVE))==native['runtime_source_hashes'].get(name,digest),'Compiled source cache changed: '+name)
    for name,digest in native['runtime_source_hashes'].items():require(sha(m.local(name,m.NATIVE))==digest,'Android engine source changed: '+name)
    for name,digest in native['support_sources'].items():require(sha(m.local(name,BUILD/'termux-reference/setjmp-aarch64'))==digest,'Setjmp input changed')
    patch=(BUILD/'termux-reference/0016-Add-workaround-for-tagged-pointers-on-Android-12.patch').read_text().replace('#ifdef __TERMUX__','#ifdef __ANDROID__')
    require(hashlib.sha256(patch.encode()).hexdigest()==native['termux_patch_sha256'],'Heap tag patch changed')
    require(runtime['native_engine_record_sha256']==sha(BUILD/'bionic-engine.json'),'Stale engine record')
    require(runtime['packager_sha256']==sha(HERE/'package_runtime.py'),'Runtime packager changed')
    require(runtime['tools_record_sha256']==sha(BUILD/'bionic-tools.json'),'Dependency input changed')
    libraries={}
    for name,record in runtime['files'].items():
        require(sha(BUILD/'runtime'/name)==record['sha256'],'Runtime library changed: '+name)
        require(sha(BUILD/'runtime'/(name+'.unstripped'))==record['symbols_sha256'],'Symbols changed')
        libraries[name]=record['sha256']
    helper=m.local(storage['binary_path']);require(helper==(BUILD/'storage-runtime/libp2dstorage.so').resolve(),'Wrong storage helper path')
    require(sha(helper)==storage['binary_sha256'] and sha(HERE/'build_storage.py')==storage['builder_sha256'],'Storage helper build changed')
    for name,digest in storage['sources'].items():require(sha(m.local(name))==digest,'Storage source changed')
    libraries[helper.name]=storage['binary_sha256']
    for name in libraries:
        lib=helper if name==helper.name else BUILD/'runtime'/name
        symbols=subprocess.check_output(['nm','-D',str(lib)],text=True)
        require('p2d_test_' not in symbols and 'StorageFallbackTest' not in symbols,'Test fault injection present in Android library')
        if name=='libp2dengine.so':require(b'P2D_TEST_MOVE_' not in lib.read_bytes(),'Move test fault injection present')
        for line in subprocess.check_output(['readelf','-lW',str(lib)],text=True).splitlines():
            if 'LOAD ' in line:require(int(line.split()[-1],16)>=16384,'ELF alignment failed: '+name)
    for record in (app,smoke):require(record['engine_sha256']==libraries['libp2dengine.so'] and record['storage_helper_sha256']==libraries[helper.name],'Build/runtime identities differ')
    sources=m.tested_source_hashes()
    with zipfile.ZipFile(previous/'Pocket2Droid-V6.59-TCG-Source.zip') as z:
        changed=[n for n in sources if 'android/'+n not in z.namelist() or m.local(n).read_bytes()!=z.read('android/'+n)]
    prefix='src/com/samsixx/wm6android/'
    allowed={'AndroidManifest.xml',*[prefix+n+'.java' for n in ('MainActivity','Engine','StorageLayout','AudioProtocol','AudioPump','PcmResampler','AudioPlayer','AudioSession')]}
    require(set(changed)==allowed,'Unexpected Android behavior change: '+str(changed))
    evidence=load(a.evidence)
    checks.validate_record(evidence,{'version':'6.60','apk_sha256':smoke['apk_sha256'],'native_sha256':native['binary_sha256'],'source_hashes':sources})
    require(evidence.get('installed_apk_sha256')==smoke['apk_sha256'] and evidence.get('original_user_data_accessed') is False,'Phone candidate identity/data preservation not confirmed')
    artifacts=evidence.get('artifacts',{});required={'native-tests','copied-guest','engine-art','audio-art','phone-session','native-overhead','phone-overhead','review'}
    require(required<=set(artifacts),'Current evidence artifacts missing')
    paths={}
    for name,record in artifacts.items():
        require(Path(name).name==name,'Invalid artifact name');path=m.local(record['path']);require(path.suffix in ('.txt','.log','.json'),'Exclude guest binaries/images from release evidence')
        require(sha(path)==record['sha256'],'Evidence artifact changed: '+name);paths[name]=path
    require(re.search(r'Ran [1-9][0-9]* tests',log(paths['native-tests'])) and '\nOK' in log(paths['native-tests']),'Native suite did not pass')
    require('PASS actual Engine ART' in log(paths['engine-art']) and 'PASS Engine sound lifecycle' in log(paths['engine-art']),'Current Engine sound lifecycle ART did not pass')
    require('transient=true pauseResponsive=true completion=1' in log(paths['audio-art']) and 'Focus callback during request preserved: true' in log(paths['audio-art']) and 'PASS actual Android sound' in log(paths['audio-art']),'Current audio lifecycle ART did not pass')
    copied=load(paths['copied-guest'])
    require(copied['original_inputs_unchanged'] and copied['normal_exit'] and not copied.get('error') and copied['canonical_source_hashes']==native['source']['paths'],'Copied guest integration failed or stale')
    require(copied['binary_sha256']==sha(Path('/opt/pocket2droid-tcg-build/host/qemu-system-arm')),'Copied host engine changed')
    require(copied['audio']['nonzero_samples']>0 and len(copied['audio']['packets'])>0,'No real guest audio observed')
    signature=m.validate_apk(apk,'com.samsixx.wm6android',False,libraries,sha(BUILD/'dex/classes.dex'))
    m.validate_apk(smoke_apk,'com.samsixx.p2dtest',True,libraries,sha(BUILD/'dex/classes.dex'))
    with zipfile.ZipFile(apk) as z:require({n for n in z.namelist() if n.startswith('assets/')}=={'assets/QEMU-COPYING.txt'},'ROM/save or unexpected APK assets present')
    stage=Path(tempfile.mkdtemp(prefix='.seal-6.60-',dir=release.parent))
    try:
        delivered=stage/'Pocket2Droid-V6.60-Sound-TCG-SIGNED.apk';shutil.copy2(apk,delivered)
        shutil.copy2(Path(__file__),stage/'candidate-release-recipe.py')
        for name in ('candidate-build.json','bionic-engine.json','runtime.json','bionic-tools.json','storage-runtime.json'):shutil.copy2(BUILD/name,stage/name)
        (stage/'candidate-signature.txt').write_text(signature)
        evidence_dir=stage/'evidence';evidence_dir.mkdir()
        for name,path in paths.items():(evidence_dir/(name+path.suffix)).write_text(log(path))
        (stage/'ANDROID_INTEGRATION.json').write_text(json.dumps(evidence,indent=2)+'\n')
        source_zip=stage/'Pocket2Droid-V6.60-Sound-TCG-Source.zip';inventory=m.snapshot_sources(source_zip,dict(native=native,runtime=runtime))
        with zipfile.ZipFile(source_zip) as z:
            for name,digest in inventory.items():require(hashlib.sha256(z.read(name)).hexdigest()==digest,'Source archive identity mismatch')
        for name,digest in sources.items():require(inventory['android/'+name]==digest,'Android snapshot mismatch')
        for name,digest in native['source']['paths'].items():require(inventory['qemu-canonical-changes/'+name]==digest,'Canonical native snapshot mismatch')
        for name,digest in native['runtime_source_hashes'].items():require(inventory['qemu-android-exact/'+name]==digest,'Compiled native snapshot mismatch')
        symbol_zip=stage/'Pocket2Droid-V6.60-Sound-TCG-Symbols.zip'
        with zipfile.ZipFile(symbol_zip,'w',zipfile.ZIP_DEFLATED,compresslevel=4) as z:
            for name in runtime['files']:z.write(BUILD/'runtime'/(name+'.unstripped'),name+'.unstripped')
            z.write(helper,helper.name+'.unstripped')
        with zipfile.ZipFile(symbol_zip) as z:
            require(z.testzip() is None,'Symbols CRC failed')
            for name,record in runtime['files'].items():require(hashlib.sha256(z.read(name+'.unstripped')).hexdigest()==record['symbols_sha256'],'Symbol identity failed')
        require(sha(delivered)==app['apk_sha256'],'Delivered APK changed')
        require(baseline=={p.name:sha(p) for p in previous.iterdir() if p.is_file()},'Baseline artifacts changed')
        scope=dict(app,delivered_apk=delivered.name,source_archive_sha256=sha(source_zip),symbols_archive_sha256=sha(symbol_zip),baseline_version='6.59',performance_gain_claimed=False,doov_sound_validation_pending=True)
        (stage/'RELEASE_SCOPE.json').write_text(json.dumps(scope,indent=2)+'\n')
        (stage/'RELEASE_EVIDENCE.json').write_text(json.dumps({'version':'6.60','changed_native_files_vs_v659':sorted(native_changes),'changed_android_files_vs_v659':sorted(changed),'baseline_artifacts':baseline,'dependencies_and_save_helper_unchanged':True,'native_and_android_sources_verified':True,'observations':evidence.get('observations',{}),'validation_scope':'Copied full WM boot/game PCM/save; real S25 ART and disposable foreground game/mute/pause/restart. API24/25 and DOOV runtime remain untested.'},indent=2)+'\n')
        (stage/'FINAL_VERIFICATION.json').write_text(json.dumps({'signature':True,'native_identity':True,'source_identity':True,'alignment_16k':True,'baseline_preserved':True,'original_signer':m.SIGNER},indent=2)+'\n')
        (stage/'INSTALL.txt').write_text('V6.60 Sound. Install as an update after normal EXIT; do not uninstall or clear data.\nSound is enabled by default. Use Sound switch to mute and Android media volume keys.\nTCG, ROM selection and public ROM/save/Storage Card paths are retained.\nS25 game/system sound verified; occasional static reported. DOOV/API24 runtime sound not yet verified.\nNo CPU/JIT performance gain claimed. V6.59 is retained for rollback planning; do not downgrade over saves without backup.\n')
        sums=[p for p in sorted(stage.rglob('*')) if p.is_file()];(stage/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+str(p.relative_to(stage))+'\n' for p in sums))
        m.publish_release(stage,release);print(json.dumps(scope,indent=2),flush=True)
    finally:
        if stage.exists():
            require(stage.resolve().parent==release.parent.resolve() and stage.name.startswith('.seal-6.60-'),'Unsafe cleanup path');shutil.rmtree(stage)
if __name__=='__main__':main()
