"""Seal authorized V6.66 from verified mapping/loading sources and signed contents."""
from pathlib import Path
import hashlib,importlib.util,json,shutil,subprocess,tempfile,zipfile
HERE=Path(__file__).resolve().parent;B=HERE/'build';P=HERE.parents[2];PACKAGE='com.samsixx.pocket2droid'
spec=importlib.util.spec_from_file_location('integrity',HERE/'finalize_release.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.VERSION,m.VERSION_CODE='6.66',666

def main():
    previous,release=P/'apk/6.65',P/'apk/6.66'
    m.require(not release.exists(),'Never overwrite an existing release')
    baseline={p.relative_to(previous).as_posix():m.sha(p) for p in previous.rglob('*') if p.is_file()}
    for line in (previous/'SHA256SUMS.txt').read_text().splitlines():
        digest,name=line.split('  ',1);m.require(baseline[name]==digest,'Protected V6.65 changed: '+name)
    app,native,runtime,storage=(m.load(B/n) for n in ('candidate-build.json','bionic-engine.json','runtime.json','storage-runtime.json'))
    apk=Path(app['signed_apk']);m.require(apk.parent.resolve()==B.resolve() and app['version']==m.VERSION and app['package']==PACKAGE and not app['test_only'] and m.sha(apk)==app['apk_sha256'],'Wrong signed candidate')
    old=m.load(previous/'bionic-engine.json')
    changed={n for n,d in native['source']['paths'].items() if old['source']['paths'].get(n)!=d}
    m.require(changed=={'hw/misc/p2d-devemu-services.c'} and set(native['source']['paths'])==set(old['source']['paths']),'Unexpected native changes')
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
    old_runtime=m.load(previous/'runtime.json');m.require(set(runtime['files'])==set(old_runtime['files']),'Runtime dependency set changed')
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
    proof=m.load(P/'GITHUB_PREVIEW/BUTTON_MAPPING_VERIFICATION.json')
    actual={p.relative_to(HERE).as_posix():m.sha(p) for p in (HERE/'src').rglob('*.java')}
    m.require(actual==proof['source_sha256'] and len(actual)==42,'Frontend source differs from verified source')
    for field in ('android_tested_source_sha256','loading_tested_source_sha256'):
        for name,digest in proof[field].items():m.require(m.sha(HERE/name)==digest,'Android test source changed: '+name)
    m.require(proof['native_source_sha256']==native['source']['paths']['hw/misc/p2d-devemu-services.c'] and proof['native_bionic_sha256']==native['binary_sha256'],'Mapping native proof stale')
    for text in (proof['android_mapping_log'],proof['ui_followup']['loading_android'],proof['ui_followup']['light_mapping'],proof['ui_followup']['dark_mapping'],*proof['legacy_android_lifecycle'].values()):m.require('PASS ' in text and 'FAIL ' not in text and 'ERROR ' not in text,'Frontend verification failed')
    artwork=m.load(B/'button-mapping/v666-artwork.json');m.require(artwork['apk_sha256']==app['apk_sha256'] and artwork['png_pixels_identical']==47 and artwork['original_gif_verified'] and artwork['no_stale_resources'],'Artwork proof stale')
    with zipfile.ZipFile(apk) as z:
        for row in artwork['resources']:
            m.require(m.sha(HERE/row['resource'])==row['source_sha256'] and hashlib.sha256(z.read(row['apk_entry'])).hexdigest()==row['apk_sha256'],'Artwork changed')
        m.require({n for n in z.namelist() if n.startswith('assets/')}=={'assets/QEMU-COPYING.txt'},'Unexpected bundled guest data')
    stage=Path(tempfile.mkdtemp(prefix='.seal-6.66-',dir=release.parent))
    try:
        delivered=stage/'Pocket2Droid-V6.66-Button-Mapping-TCG-SIGNED.apk';shutil.copy2(apk,delivered)
        source=stage/'Pocket2Droid-V6.66-Button-Mapping-TCG-Source.zip'
        print('Signature, identity, 16KiB alignment and complete artwork verified; archiving source.',flush=True)
        inventory=m.snapshot_sources(source,{'native':native,'runtime':runtime})
        tested=m.tested_source_hashes()
        with zipfile.ZipFile(source) as z:
            for name,digest in inventory.items():m.require(hashlib.sha256(z.read(name)).hexdigest()==digest,'Archive entry changed: '+name)
            for name,digest in tested.items():m.require(inventory['android/'+name]==digest,'Compiled source/archive differs')
            for row in artwork['resources']:m.require(inventory['android/'+row['resource']]==row['source_sha256'],'Artwork/source archive differs')
            for name,digest in native['source']['paths'].items():m.require(inventory['qemu-canonical-changes/'+name]==digest,'Canonical source/archive differs')
            for name,digest in native['runtime_source_hashes'].items():m.require(inventory['qemu-android-exact/'+name]==digest,'Adapted source/archive differs')
        for name in ('candidate-build.json','bionic-engine.json','runtime.json','bionic-tools.json','storage-runtime.json'):shutil.copy2(B/name,stage/name)
        shutil.copy2(Path(__file__),stage/'candidate-release-recipe.py');(stage/'candidate-signature.txt').write_text(signature)
        evidence=stage/'evidence';evidence.mkdir();shutil.copy2(P/'GITHUB_PREVIEW/BUTTON_MAPPING_VERIFICATION.json',evidence/'frontend-verification.json')
        for name in ('v666-build.log','v666-artwork.json','host-green.log','loading-host-green.log','keyboard-green.log'):shutil.copy2(B/'button-mapping'/name,evidence/name)
        (evidence/'tested-sources-v666.json').write_text(json.dumps(tested,indent=2)+'\n');(evidence/'application-badging.txt').write_text(badging)
        verification=dict(version=m.VERSION,version_code=m.VERSION_CODE,app_name='Pocket2Droid',package=PACKAGE,apk_sha256=m.sha(delivered),original_signer=m.SIGNER,signature_verified=True,apk_and_elf_alignment_16k=True,exact_dex_and_native_identity=True,source_archive_sha256=m.sha(source),source_snapshot_files=len(inventory),baseline_preserved=True,button_mapping=True,native_keyboard_cases=11,png_pixel_identity=47,original_animated_gif=True,phone_modified=False,physical_phone_test_pending=True,performance_gain_claimed=False,github_modified=False)
        (stage/'FINAL_VERIFICATION.json').write_text(json.dumps(verification,indent=2)+'\n')
        (stage/'INSTALL.txt').write_text('Pocket2Droid 6.66 (666), ARM64 Android 7.0+ (API24).\nInstall as an update to com.samsixx.pocket2droid after normal Exit; keep app data.\nDo not uninstall, clear data or reset the guest. The older com.samsixx.wm6android app is separate; close it before opening this app.\nIncludes startup storage request, default 50% controls transparency, menu/focus recovery, Tab/Space controls and global Button Mapping with sticks/triggers and multi-key ownership.\nMapping keypad follows system theme, scrolls above navigation and has top-right Reset.\nOriginal loading GIF fits any aspect ratio on black until the first visible ROM image is posted.\nQuick phone check: assign a keyboard/controller button, hold multiple keys, open/close the session menu, check startup animation and normally Exit to save.\nPhysical phone/controller behavior remains pending; local Android fixtures and signed-package integrity passed. No performance change is claimed.\nNo Windows Mobile ROMs, games, user saves or signing keys are bundled. V6.65 retained.\n')
        m.require(baseline=={p.relative_to(previous).as_posix():m.sha(p) for p in previous.rglob('*') if p.is_file()},'Protected V6.65 changed')
        (stage/'SHA256SUMS.txt').write_text(''.join(m.sha(p)+'  '+p.relative_to(stage).as_posix()+'\n' for p in sorted(stage.rglob('*')) if p.is_file()))
        m.publish_release(stage,release);print(json.dumps({'apk':str(release/delivered.name),'sha256':verification['apk_sha256'],'version':'6.66','source_files':len(inventory)}),flush=True)
    finally:
        if stage.exists():
            m.require(stage.parent.resolve()==release.parent.resolve() and stage.name.startswith('.seal-6.66-'),'Unsafe staging cleanup');shutil.rmtree(stage)
if __name__=='__main__':main()
