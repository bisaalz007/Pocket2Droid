"""Seal authorized public v1.0 with revised icons, persistent ROM order and exact source."""
from pathlib import Path
import hashlib,importlib.util,json,shutil,subprocess,tempfile,zipfile
HERE=Path(__file__).resolve().parent;B=HERE/'build';P=HERE.parents[2];PACKAGE='com.samthedev.pocket2droid'
spec=importlib.util.spec_from_file_location('integrity',HERE/'finalize_release.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.VERSION,m.VERSION_CODE='1.0',668

def main():
    previous,release=P/'apk/6.67',P/'apk/1.0'
    m.require(not release.exists(),'Never overwrite an existing release')
    baseline={p.relative_to(previous).as_posix():m.sha(p) for p in previous.rglob('*') if p.is_file()}
    for line in (previous/'SHA256SUMS.txt').read_text().splitlines():
        digest,name=line.split('  ',1);m.require(baseline[name]==digest,'Protected V6.67 changed: '+name)
    app,native,runtime,storage=(m.load(B/n) for n in ('candidate-build.json','bionic-engine.json','runtime.json','storage-runtime.json'))
    apk=Path(app['signed_apk']);m.require(apk.parent.resolve()==B.resolve() and app['version']==m.VERSION and app['package']==PACKAGE and not app['test_only'] and m.sha(apk)==app['apk_sha256'],'Wrong signed candidate')
    old=m.load(previous/'bionic-engine.json')
    m.require(native==old,'Native source/binary recipe changed from V6.67')
    for name,digest in native['source']['paths'].items():
        m.require(m.sha(HERE.parent/'qemu'/name)==digest,'Stale native source: '+name)
        m.require(m.sha(m.NATIVE/name)==native['runtime_source_hashes'].get(name,digest),'Compiled native source differs: '+name)
    for name,digest in native['runtime_source_hashes'].items():m.require(m.sha(m.NATIVE/name)==digest,'Stale adapted native source')
    m.require(native['builder_sha256']==m.sha(HERE/'build_bionic.py') and native['binary_sha256']==m.sha(B/'libp2dengine-bionic.so'),'Stale native build')
    m.require(runtime['native_engine_record_sha256']==m.sha(B/'bionic-engine.json') and runtime['packager_sha256']==m.sha(HERE/'package_runtime.py') and runtime['tools_record_sha256']==m.sha(B/'bionic-tools.json'),'Stale runtime packaging')
    m.require(storage==m.load(previous/'storage-runtime.json'),'Storage helper changed')
    m.require(storage['builder_sha256']==m.sha(HERE/'build_storage.py'),'Storage recipe changed')
    for name,digest in storage['sources'].items():m.require(m.sha(HERE/name)==digest,'Storage source changed')
    libraries={n:r['sha256'] for n,r in runtime['files'].items()};libraries['libp2dstorage.so']=storage['binary_sha256']
    old_runtime=m.load(previous/'runtime.json');m.require(runtime==old_runtime,'Native runtime changed from V6.67')
    for name,record in runtime['files'].items():
        if name!='libp2dengine.so':m.require(record==old_runtime['files'][name],'Dependency changed: '+name)
    for name,digest in libraries.items():
        path=B/('storage-runtime' if name=='libp2dstorage.so' else 'runtime')/name;m.require(m.sha(path)==digest,'Native binary differs')
        loads=[line for line in subprocess.check_output(['readelf','-lW',str(path)],text=True).splitlines() if 'LOAD ' in line]
        m.require(loads and all(int(line.split()[-1],16)>=16384 for line in loads),'ELF alignment failed: '+name)
    signature=m.validate_apk(apk,PACKAGE,False,libraries,m.sha(B/'dex/classes.dex'))
    badging=subprocess.check_output([str(m.SDK/'aapt2'),'dump','badging',str(apk)],text=True)
    m.require("application-label:'Pocket2Droid'" in badging and "application: label='Pocket2Droid'" in badging,'Wrong app label')
    manifest=m.parse_manifest(apk)
    m.require(not manifest.get('instrumentation') and not manifest.get('provider'),'Test fixture packaged')
    activities={a['name'] for a in manifest.get('activity',[])}
    m.require(activities=={PACKAGE+'.'+n for n in ('MainActivity','AppSettingsActivity','RomSettingsActivity','ButtonMappingActivity','EmulatorActivity')},'Unexpected activities')
    proof=m.load(P/'GITHUB_PREVIEW/ADD_POPUP_VERIFICATION.json')
    order=m.load(P/'GITHUB_PREVIEW/LIBRARY_ORDER_VERIFICATION.json')
    expected=dict(proof['production_source_hashes'])
    for row in order['source_files']:
        m.require(m.sha(HERE/row['path'].removeprefix('android/'))==row['after_sha256'],'Ordering source differs from tested source')
        if row['path'].startswith('android/src/'):expected[row['path']]=row['after_sha256']
    actual={'android/'+p.relative_to(HERE).as_posix():m.sha(p) for p in (HERE/'src').rglob('*.java')}
    m.require(actual==expected and len(actual)==42,'Unexpected frontend source change')
    for name,digest in proof['tested_android_source_hashes'].items():
        if 'android/'+name in expected:digest=expected['android/'+name]
        m.require(m.sha(HERE/name)==digest,'Unchanged Android UI fixture/source differs')
    for label,count in (('granted.log',22),('large-font.log',22),('denied.log',33)):
        log=proof['android_logs'][label];m.require('PASS '+str(count)+' ' in log and 'FAIL ' not in log and 'ERROR ' not in log,'Inherited unchanged-UI evidence failed')
    for mode in ('normal','fallback'):
        file=B/'library-order'/('green-'+mode+'.log')
        m.require(m.sha(file)==order['evidence_logs'][file.name],'Ordering test evidence changed')
        log=file.read_text();m.require('PASS ROM repository 122 ' in log and 'PASS ROM settings/geometry 71 ' in log and 'Traceback' not in log,'Ordering tests failed')
    m.require(order['normal_repository_assertions']==122 and order['fallback_repository_assertions']==122,'Missing ordering checks')
    icon_proof=m.load(P/'GITHUB_PREVIEW/ROM_ICON_COLOR_UPDATE_VERIFICATION.json')
    m.require(len(icon_proof['icons'])==6 and icon_proof['original_transparency_preserved'],'Supplied icons not verified')
    for row in icon_proof['icons']:
        original=P/'assets/icons 2'/('pocket2droid-'+row['color']+'@2x.png')
        m.require(m.sha(original)==m.sha(HERE/row['resource'].removeprefix('android/'))==row['after_sha256'],'Revised supplied icon changed')
    artwork=m.load(B/'release-v1.0/artwork.json');m.require(artwork['apk_sha256']==app['apk_sha256'] and artwork['png_visible_pixels_identical']==47 and artwork['original_gif_verified'] and artwork['no_stale_resources'],'Artwork proof stale')
    with zipfile.ZipFile(apk) as z:
        for row in artwork['resources']:
            m.require(m.sha(HERE/row['resource'])==row['source_sha256'] and hashlib.sha256(z.read(row['apk_entry'])).hexdigest()==row['apk_sha256'],'Artwork changed')
        m.require({n for n in z.namelist() if n.startswith('assets/')}=={'assets/QEMU-COPYING.txt'},'Unexpected bundled guest data')
    stage=Path(tempfile.mkdtemp(prefix='.seal-1.0-',dir=release.parent))
    try:
        delivered=stage/'Pocket2Droid-v1.0-SIGNED.apk';shutil.copy2(apk,delivered)
        source=stage/'Pocket2Droid-v1.0-Source.zip'
        print('Signature, identity, 16KiB alignment and complete artwork verified; archiving source.',flush=True)
        inventory=m.snapshot_sources(source,{'native':native,'runtime':runtime})
        tested=m.tested_source_hashes()
        with zipfile.ZipFile(source) as fixture_check:
            m.require(fixture_check.read('android/tests/fixtures/sdk-keypad.json')==(HERE/'tests/fixtures/sdk-keypad.json').read_bytes(),'Keypad fixture missing from exact source')
        with zipfile.ZipFile(source) as z:
            for name,digest in inventory.items():m.require(hashlib.sha256(z.read(name)).hexdigest()==digest,'Archive entry changed: '+name)
            for name,digest in tested.items():m.require(inventory['android/'+name]==digest,'Compiled source/archive differs')
            for row in artwork['resources']:m.require(inventory['android/'+row['resource']]==row['source_sha256'],'Artwork/source archive differs')
            for name,digest in native['source']['paths'].items():m.require(inventory['qemu-canonical-changes/'+name]==digest,'Canonical source/archive differs')
            for name,digest in native['runtime_source_hashes'].items():m.require(inventory['qemu-android-exact/'+name]==digest,'Adapted source/archive differs')
        for name in ('candidate-build.json','bionic-engine.json','runtime.json','bionic-tools.json','storage-runtime.json'):shutil.copy2(B/name,stage/name)
        shutil.copy2(Path(__file__),stage/'candidate-release-recipe.py');(stage/'candidate-signature.txt').write_text(signature)
        evidence=stage/'evidence';evidence.mkdir()
        for name in ('ADD_POPUP_VERIFICATION.json','FIXED_STORAGE_VERIFICATION.json','ROM_ICON_COLOR_UPDATE_VERIFICATION.json','LIBRARY_ORDER_VERIFICATION.json'):shutil.copy2(P/'GITHUB_PREVIEW'/name,evidence/name)
        for name in ('build.log','artwork.json'):shutil.copy2(B/'release-v1.0'/name,evidence/name)
        for mode in ('normal','fallback'):shutil.copy2(B/'library-order'/('green-'+mode+'.log'),evidence/('host-'+mode+'.log'))
        (evidence/'tested-sources-v1.0.json').write_text(json.dumps(tested,indent=2)+'\n');(evidence/'application-badging.txt').write_text(badging)
        verification=dict(version=m.VERSION,version_code=m.VERSION_CODE,app_name='Pocket2Droid',package=PACKAGE,apk_sha256=m.sha(delivered),original_signer=m.SIGNER,signature_verified=True,apk_and_elf_alignment_16k=True,exact_dex_and_native_identity=True,source_archive_sha256=m.sha(source),source_snapshot_files=len(inventory),baseline_preserved=True,fixed_storagecard=True,add_popup=True,any_file_to_storagecard=True,new_rom_icons=6,persistent_library_addition_order=True,button_mapping=True,native_unchanged_from_v667=True,png_visible_pixel_identity=47,original_animated_gif=True,phone_modified=False,physical_phone_test_pending=True,performance_gain_claimed=False,github_modified=False)
        (stage/'FINAL_VERIFICATION.json').write_text(json.dumps(verification,indent=2)+'\n')
        (stage/'INSTALL.txt').write_text('Pocket2Droid 1.0 (internal version668), ARM64 Android7.0+ (API24).\nInstall as an update to com.samthedev.pocket2droid after normal Exit; keep app data.\nDo not uninstall, clear data or reset the guest. The older com.samsixx.wm6android app is separate.\nIncludes fixed default storagecard and read-only global/per-ROM folder rows, new + popup with PPC Rom and File to StorageCard, safe duplicate suffixes and all six revised-colour ROM icons; newly added ROMs append at the bottom and order survives restart.\nRetains global Button Mapping,50% default controls transparency and original loading GIF fitted on black.\nQuick check: import a ROM and check it appears at the bottom after restarting; tap +, copy a file, verify it appears in pocket2droid/storagecard; an existing name receives a suffix. Exit an active ROM before importing.\nExisting custom ROM card assignments/files are preserved; no migration or data reset.\nSignature, package/version/name, DEX/native identity and16KiB alignment verified. V6.67 preserved. No phone install/performance claim.\nNo Windows Mobile ROMs, games, user saves or private signing keys are bundled.\n')
        m.require(baseline=={p.relative_to(previous).as_posix():m.sha(p) for p in previous.rglob('*') if p.is_file()},'Protected V6.67 changed')
        (stage/'SHA256SUMS.txt').write_text(''.join(m.sha(p)+'  '+p.relative_to(stage).as_posix()+'\n' for p in sorted(stage.rglob('*')) if p.is_file()))
        m.publish_release(stage,release);print(json.dumps({'apk':str(release/delivered.name),'sha256':verification['apk_sha256'],'version':'1.0','source_files':len(inventory)}),flush=True)
    finally:
        if stage.exists():
            m.require(stage.parent.resolve()==release.parent.resolve() and stage.name.startswith('.seal-1.0-'),'Unsafe staging cleanup');shutil.rmtree(stage)
if __name__=='__main__':main()
