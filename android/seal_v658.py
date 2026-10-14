"""Seal V6.58 storage compatibility and filename-selected ROM release."""
from pathlib import Path
import hashlib, importlib.util, json, shutil, subprocess, tempfile, zipfile

HERE=Path(__file__).resolve().parent
BUILD=HERE/'build'
PROJECT=HERE.parents[2]
ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('release_tools',HERE/'finalize_release.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.VERSION,m.VERSION_CODE='6.58',658
sha,load,require=m.sha,m.load,m.require

def log(path):
    data=path.read_bytes()
    return data.decode('utf-16' if data[:2] in (b'\xff\xfe',b'\xfe\xff') else 'utf-8-sig')

def main():
    previous=PROJECT/'apk/6.57';release=PROJECT/'apk/6.58'
    require(not release.exists(),'Preserve existing V6.58; never overwrite')
    baseline={p.name:sha(p) for p in previous.iterdir() if p.is_file()}
    require(baseline['Pocket2Droid-V6.57-TCG-SIGNED.apk']==
            'a9473924c712297a178ef9dbc8428e3e97e157d005952f4ef1d702fcc3997681','Baseline APK changed')
    app,native,runtime,storage=(load(BUILD/n) for n in
        ('candidate-build.json','bionic-engine.json','runtime.json','storage-runtime.json'))
    require(app['version']=='6.58' and app['test_only'] is False
            and app['previous_engine_packaged'] is False,'Wrong candidate')
    apk=Path(app['signed_apk'])
    require(apk.resolve().parent==BUILD.resolve() and sha(apk)==app['apk_sha256'],'Candidate APK changed')
    require(native==load(previous/'bionic-engine.json') and runtime==load(previous/'runtime.json'),
            'QEMU engine/runtime must remain byte-identical to V6.57')
    require(native['binary_sha256']==sha(BUILD/'libp2dengine-bionic.so'),'Compiler output changed')
    require(native['builder_sha256']==sha(HERE/'build_bionic.py'),'Compiler recipe changed')
    for name,digest in native['source']['paths'].items():
        require(sha(m.local(name,ROOT/'qemu'))==digest,'Canonical native source changed: '+name)
        expected=native['runtime_source_hashes'].get(name,digest)
        require(sha(m.local(name,m.NATIVE))==expected,'Compiled source cache changed: '+name)
    for name,digest in native['runtime_source_hashes'].items():
        require(sha(m.local(name,m.NATIVE))==digest,'Android source changed: '+name)
    for name,digest in native['support_sources'].items():
        require(sha(m.local(name,BUILD/'termux-reference/setjmp-aarch64'))==digest,'Setjmp input changed')
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
    helper=m.local(storage['binary_path'])
    require(helper==(BUILD/'storage-runtime/libp2dstorage.so').resolve(),'Wrong helper path')
    require(sha(helper)==storage['binary_sha256'] and sha(HERE/'build_storage.py')==storage['builder_sha256'],
            'Storage helper build changed')
    for name,digest in storage['sources'].items():
        require(sha(m.local(name))==digest,'Storage source changed: '+name)
    libraries[helper.name]=storage['binary_sha256']
    symbols_text=subprocess.check_output(['nm','-D',str(helper)],text=True)
    require('p2d_test_' not in symbols_text and 'StorageFallbackTest' not in symbols_text,
            'Host fault injection must not be present in Android helper')
    for name in libraries:
        lib=helper if name==helper.name else BUILD/'runtime'/name
        for line in subprocess.check_output(['readelf','-lW',str(lib)],text=True).splitlines():
            if 'LOAD ' in line: require(int(line.split()[-1],16)>=16384,'ELF alignment failed: '+name)
    require(app['engine_sha256']==libraries['libp2dengine.so'] and
            app['storage_helper_sha256']==libraries[helper.name],'Build record differs')
    source_hashes=m.tested_source_hashes()
    with zipfile.ZipFile(previous/'Pocket2Droid-V6.57-TCG-Source.zip') as z:
        changed=[n for n in source_hashes if m.local(n).read_bytes()!=z.read('android/'+n)]
    allowed={'AndroidManifest.xml','native/storage_publish.c'}|{
        'src/com/samsixx/wm6android/'+n for n in
        ('StoragePublish.java','StorageLayout.java','Engine.java','MainActivity.java')}
    require(set(changed)==allowed,'Unexpected Android behavior change: '+str(changed))
    test_logs={
        'storage-layout-final.log':BUILD/'storage-layout-final.log',
        'storage-fallback-final.log':BUILD/'storage-fallback-final.log',
        'android10-storage-final.log':BUILD/'storage-art/android10.log',
        'v658-build-final.log':BUILD/'v658-build-final.log'}
    require('PASS StorageLayout 51 real filesystem assertions' in log(test_logs['storage-layout-final.log']),
            'Layout regression suite did not pass')
    require('PASS StorageFallback 28 actual Java/JNI assertions' in log(test_logs['storage-fallback-final.log']),
            'Fallback and durability fault suite did not pass')
    require('PASS actual Android storage compatibility 9 behavior assertions' in log(test_logs['android10-storage-final.log'])
            and 'directory fsync supported=true' in log(test_logs['android10-storage-final.log']),
            'Current-device actual ART/storage test did not pass')
    signature=m.validate_apk(apk,'com.samsixx.wm6android',False,libraries,sha(BUILD/'dex/classes.dex'))
    with zipfile.ZipFile(apk) as z:
        require({n for n in z.namelist() if n.startswith('assets/')}=={'assets/QEMU-COPYING.txt'},
                'ROM/save or unexpected APK assets present')
    stage=Path(tempfile.mkdtemp(prefix='.seal-6.58-',dir=release.parent))
    try:
        delivered=stage/'Pocket2Droid-V6.58-TCG-SIGNED.apk';shutil.copy2(apk,delivered)
        shutil.copy2(Path(__file__),stage/'candidate-release-recipe.py')
        for name in ('candidate-build.json','bionic-engine.json','runtime.json','bionic-tools.json','storage-runtime.json'):
            shutil.copy2(BUILD/name,stage/name)
        (stage/'candidate-signature.txt').write_text(signature)
        evidence={'version':'6.58','source_hashes':source_hashes,'changed_production_files_vs_v657':sorted(changed),
                  'engine_and_dependency_binaries_identical_to_v657':True,
                  'rom_selection':'Readable nonempty pocket2droid/Roms/PPC_USA.BIN, up to 96MiB; no identity hash or exact size',
                  'storage':'Original atomic no-replace path retained; unsupported operation uses journaled exclusive copy; incomplete/undurable publication fails closed',
                  'tests':{'host_layout_assertions':51,'host_fallback_and_fault_assertions':28,
                           'actual_android10_assertions':9,'device':'8c000c756641873211d','shared_directory_fsync':True},
                  'review':{'important_findings_remaining':0,'fixed_finding':'Require parent directory sync before journal retirement; fault regressions pass'},
                  'test_artifacts':{n:sha(p) for n,p in test_logs.items()},
                  'validation_scope':'Focused host and actual Android10 temporary-file tests; production app boot/save pending installation',
                  'performance_gain_claimed':False,'s25_and_doov_v658_validation_pending':True,'baseline_artifacts':baseline}
        (stage/'RELEASE_EVIDENCE.json').write_text(json.dumps(evidence,indent=2)+'\n')
        evidence_dir=stage/'evidence';evidence_dir.mkdir()
        for name,path in test_logs.items(): (evidence_dir/name).write_text(log(path))
        sources=stage/'Pocket2Droid-V6.58-TCG-Source.zip'
        print('Archiving exact source and verifying identities...',flush=True)
        inventory=m.snapshot_sources(sources,dict(native=native,runtime=runtime))
        with zipfile.ZipFile(sources) as z:
            for name,digest in inventory.items():
                require(hashlib.sha256(z.read(name)).hexdigest()==digest,'Source archive identity mismatch: '+name)
        for name,digest in source_hashes.items():
            require(inventory['android/'+name]==digest,'Android snapshot mismatch: '+name)
        for name,digest in native['source']['paths'].items():
            require(inventory['qemu-canonical-changes/'+name]==digest,'Canonical snapshot mismatch')
        for name,digest in native['runtime_source_hashes'].items():
            require(inventory['qemu-android-exact/'+name]==digest,'Android engine snapshot mismatch')
        symbols=stage/'Pocket2Droid-V6.58-TCG-Symbols.zip'
        with zipfile.ZipFile(symbols,'w',zipfile.ZIP_DEFLATED,compresslevel=4) as z:
            for name in runtime['files']: z.write(BUILD/'runtime'/(name+'.unstripped'),name+'.unstripped')
            z.write(helper,helper.name+'.unstripped')
        with zipfile.ZipFile(symbols) as z:
            require(z.testzip() is None,'Symbols CRC failed')
            for name,record in runtime['files'].items():
                require(hashlib.sha256(z.read(name+'.unstripped')).hexdigest()==record['symbols_sha256'],'Symbol identity failed')
        require(sha(delivered)==app['apk_sha256'],'Delivered APK changed')
        require(baseline=={p.name:sha(p) for p in previous.iterdir() if p.is_file()},'Baseline artifacts changed')
        scope=dict(app,delivered_apk=delivered.name,source_archive_sha256=sha(sources),
                   symbols_archive_sha256=sha(symbols),source_snapshot_files=len(inventory),
                   phone_validation_pending=True,performance_gain_claimed=False,baseline_version='6.57')
        (stage/'RELEASE_SCOPE.json').write_text(json.dumps(scope,indent=2)+'\n')
        (stage/'FINAL_VERIFICATION.json').write_text(json.dumps({'signature':True,'native_identity':True,
            'source_identity':True,'alignment_16k':True,'baseline_preserved':True,'host_faults_absent_from_android_binary':True,
            'phone_validation_pending':True},indent=2)+'\n')
        sums=[p for p in sorted(stage.rglob('*')) if p.is_file()]
        (stage/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+str(p.relative_to(stage))+'\n' for p in sums))
        m.publish_release(stage,release)
        print(json.dumps(scope,indent=2),flush=True)
    finally:
        if stage.exists():
            require(stage.resolve().parent==release.parent.resolve() and stage.name.startswith('.seal-6.58-'),'Unsafe cleanup path')
            shutil.rmtree(stage)

if __name__=='__main__':main()
