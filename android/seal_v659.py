"""Seal V6.59 recoverable guest SD-card file moves, retaining V6.58."""
from pathlib import Path
import hashlib, importlib.util, json, shutil, subprocess, tempfile, zipfile

HERE=Path(__file__).resolve().parent
BUILD=HERE/'build'
PROJECT=HERE.parents[2]
ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('release_tools',HERE/'finalize_release.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.VERSION,m.VERSION_CODE='6.59',659
sha,load,require=m.sha,m.load,m.require

def log(path):
    data=path.read_bytes()
    return data.decode('utf-16' if data[:2] in (b'\xff\xfe',b'\xfe\xff') else 'utf-8-sig')

def main():
    previous=PROJECT/'apk/6.58';release=PROJECT/'apk/6.59'
    require(not release.exists(),'Preserve existing V6.59; never overwrite')
    baseline={p.name:sha(p) for p in previous.iterdir() if p.is_file()}
    require(baseline['Pocket2Droid-V6.58-TCG-SIGNED.apk']==
            '7d095d8cf41635c68247229800247d5e7a2cbe79453f1078e3079d656a9b5672','Baseline APK changed')
    app,native,runtime,storage=(load(BUILD/n) for n in
        ('candidate-build.json','bionic-engine.json','runtime.json','storage-runtime.json'))
    require(app['version']=='6.59' and app['test_only'] is False
            and app['previous_engine_packaged'] is False,'Wrong candidate')
    apk=Path(app['signed_apk'])
    require(apk.resolve().parent==BUILD.resolve() and sha(apk)==app['apk_sha256'],'Candidate APK changed')
    old_native,old_runtime=load(previous/'bionic-engine.json'),load(previous/'runtime.json')
    native_changes={n for n,d in native['source']['paths'].items() if old_native['source']['paths'].get(n)!=d}
    allowed_native={'hw/arm/pocket2droid-devemu.c','hw/misc/p2d-devemu-services.c',
                    'hw/misc/p2d-devemu-import.c','include/hw/arm/p2d-import.h','hw/misc/p2d-folder-move.h'}
    require(native['source']['base']==old_native['source']['base'] and native_changes==allowed_native
            and set(old_native['source']['paths'])<=set(native['source']['paths']),
            'Unexpected native change; CPU/MMU/JIT/audio/display paths must be unchanged')
    for field in ('builder_sha256','termux_patch_sha256','support_sources'):
        require(native[field]==old_native[field],'Native recipe/support changed: '+field)
    for name,record in runtime['files'].items():
        if name!='libp2dengine.so':require(record==old_runtime['files'][name],'Dependency changed: '+name)
    require(set(runtime['files'])==set(old_runtime['files']),'Runtime dependency set changed')
    require(storage==load(previous/'storage-runtime.json'),'Android save publication helper changed')
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
    engine_symbols=subprocess.check_output(['nm','-D',str(BUILD/'runtime/libp2dengine.so')],text=True)
    require('p2d_test_' not in engine_symbols and b'P2D_TEST_MOVE_' not in (BUILD/'runtime/libp2dengine.so').read_bytes(),
            'Host move fault injection must be absent from the production engine')
    for name in libraries:
        lib=helper if name==helper.name else BUILD/'runtime'/name
        for line in subprocess.check_output(['readelf','-lW',str(lib)],text=True).splitlines():
            if 'LOAD ' in line: require(int(line.split()[-1],16)>=16384,'ELF alignment failed: '+name)
    require(app['engine_sha256']==libraries['libp2dengine.so'] and
            app['storage_helper_sha256']==libraries[helper.name],'Build record differs')
    source_hashes=m.tested_source_hashes()
    with zipfile.ZipFile(previous/'Pocket2Droid-V6.58-TCG-Source.zip') as z:
        changed=[n for n in source_hashes if m.local(n).read_bytes()!=z.read('android/'+n)]
    allowed={'AndroidManifest.xml','src/com/samsixx/wm6android/MainActivity.java'}
    require(set(changed)==allowed,'Unexpected Android behavior change: '+str(changed))
    test_logs={'move-compat-host.log':BUILD/'move-compat-host.log',
               'guest-movefile-fixed.json':PROJECT/'DOCUMENTATION/PHONE_EVIDENCE/v658-a133/guest-movefile-fixed.json',
               'copied-cab-install.json':BUILD/'v659-cab-integration.json',
               'v659-build-final.log':BUILD/'v659-build-final.log'}
    require('Ran 36 tests' in log(test_logs['move-compat-host.log']) and '\nOK' in log(test_logs['move-compat-host.log']),
            '36 focused host tests did not pass')
    android=load(test_logs['guest-movefile-fixed.json'])
    require(android['engine_sha256']==libraries['libp2dengine.so'] and
            android['status']=='PASS_ACTUAL_ANDROID_GUEST_FILE_MOVE_WITHOUT_REPLACEMENT' and
            android['complete_target_bytes_verified']==76800,'Actual Android native bridge test is stale or failed')
    cab=load(test_logs['copied-cab-install.json'])
    require(cab['installer_success_observed'] and cab['normal_exit'] and cab['original_inputs_unchanged']
            and not cab['pending_records'] and cab['missing_noreplace_forced'] and cab['phone_data_accessed'] is False
            and cab['engine_sha256']==sha(Path('/opt/pocket2droid-tcg-build/host/qemu-system-arm'))
            and cab['canonical_source_hashes']==native['source']['paths'],'Copied full Windows Mobile installer failed or source stale')
    require(cab['installed_files']['Program Files/RagingThunder/ragingthunder.exe']['bytes']==149504 and
            cab['installed_files']['Program Files/RagingThunder/data_highend_eng.vfs']['bytes']==724619,
            'Full game payload missing from Storage Card')
    signature=m.validate_apk(apk,'com.samsixx.wm6android',False,libraries,sha(BUILD/'dex/classes.dex'))
    with zipfile.ZipFile(apk) as z:
        require({n for n in z.namelist() if n.startswith('assets/')}=={'assets/QEMU-COPYING.txt'},
                'ROM/save or unexpected APK assets present')
    stage=Path(tempfile.mkdtemp(prefix='.seal-6.59-',dir=release.parent))
    try:
        delivered=stage/'Pocket2Droid-V6.59-TCG-SIGNED.apk';shutil.copy2(apk,delivered)
        shutil.copy2(Path(__file__),stage/'candidate-release-recipe.py')
        for name in ('candidate-build.json','bionic-engine.json','runtime.json','bionic-tools.json','storage-runtime.json'):
            shutil.copy2(BUILD/name,stage/name)
        (stage/'candidate-signature.txt').write_text(signature)
        evidence={'version':'6.59','source_hashes':source_hashes,'changed_android_files_vs_v658':sorted(changed),
                  'changed_native_files_vs_v658':sorted(native_changes),'dependency_and_storage_helper_binaries_identical_to_v658':True,
                  'rom_selection':'Readable nonempty pocket2droid/Roms/PPC_USA.BIN, up to 96MiB; no identity hash or exact size',
                  'storage':'Original atomic guest moves retained; unsupported regular-file moves use exclusive copy, durable inode claim, content/metadata verification and directory sync; interruptions preserve recovery material and block access',
                  'tests':{'host_shared_folder_tests':16,'host_guest_move_and_fault_tests':20,
                           'actual_android_move_bytes':76800,'device':'8c000c756641873211d','copied_full_cab_installer_success':True},
                  'review':{'important_findings_remaining':0,'fixed_findings':['Target provenance and inode aliases','Final target/source pathname rechecks','Writable handle metadata failure','Absent-source directory sync','Recovery permissions and timestamps']},
                  'test_artifacts':{n:sha(p) for n,p in test_logs.items()},
                  'validation_scope':'36 focused host tests, actual Android10 native temporary-file move, full copied Windows Mobile CAB installation; production app boot/save and real-device installer pending',
                  'host_concurrency_limit':'Path identity checked before deletion; ordinary stat/unlink does not lock out arbitrary concurrent host mutation',
                  'performance_gain_claimed':False,'s25_and_doov_v659_validation_pending':True,'baseline_artifacts':baseline}
        (stage/'RELEASE_EVIDENCE.json').write_text(json.dumps(evidence,indent=2)+'\n')
        evidence_dir=stage/'evidence';evidence_dir.mkdir()
        for name,path in test_logs.items(): (evidence_dir/name).write_text(log(path))
        sources=stage/'Pocket2Droid-V6.59-TCG-Source.zip'
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
        symbols=stage/'Pocket2Droid-V6.59-TCG-Symbols.zip'
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
                   phone_validation_pending=True,performance_gain_claimed=False,baseline_version='6.58')
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
            require(stage.resolve().parent==release.parent.resolve() and stage.name.startswith('.seal-6.59-'),'Unsafe cleanup path')
            shutil.rmtree(stage)

if __name__=='__main__':main()
