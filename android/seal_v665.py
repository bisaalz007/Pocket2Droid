"""Seal authorized V6.65 controls/settings release with the requested new app ID."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
import zipfile

HERE=Path(__file__).resolve().parent
B=HERE/'build'
P=HERE.parents[2]
spec=importlib.util.spec_from_file_location('release_integrity',HERE/'finalize_release.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.VERSION,m.VERSION_CODE='6.65',665
PACKAGE='com.samsixx.pocket2droid'

def main():
    previous,release=P/'apk/6.64',P/'apk/6.65'
    m.require(not release.exists(),'Preserve existing releases; never overwrite')
    baseline={str(p.relative_to(previous)):m.sha(p) for p in previous.rglob('*') if p.is_file()}
    for line in (previous/'SHA256SUMS.txt').read_text().splitlines():
        digest,name=line.split('  ',1)
        m.require(baseline[name]==digest,'Protected V6.64 changed: '+name)
    app,native,runtime,storage=(m.load(B/n) for n in
        ('candidate-build.json','bionic-engine.json','runtime.json','storage-runtime.json'))
    apk=Path(app['signed_apk'])
    m.require(apk.resolve().parent==B.resolve() and app['version']==m.VERSION
              and app['package']==PACKAGE and app['test_only'] is False
              and m.sha(apk)==app['apk_sha256'],'Wrong or changed signed candidate')
    old_native=m.load(previous/'bionic-engine.json')
    changed={n for n,d in native['source']['paths'].items() if old_native['source']['paths'].get(n)!=d}
    m.require(changed=={'hw/misc/p2d-devemu-services.c'} and
              set(native['source']['paths'])==set(old_native['source']['paths']),
              'Only the native keyboard mapping may differ from V6.64')
    for name,digest in native['source']['paths'].items():
        m.require(m.sha(HERE.parent/'qemu'/name)==digest,'Stale native source: '+name)
        m.require(m.sha(m.NATIVE/name)==native['runtime_source_hashes'].get(name,digest),'Compiled source differs: '+name)
    for name,digest in native['runtime_source_hashes'].items():
        m.require(m.sha(m.NATIVE/name)==digest,'Android source adaptation differs: '+name)
    m.require(native['builder_sha256']==m.sha(HERE/'build_bionic.py') and
              native['binary_sha256']==m.sha(B/'libp2dengine-bionic.so'),'Stale native build')
    m.require(runtime['native_engine_record_sha256']==m.sha(B/'bionic-engine.json') and
              runtime['packager_sha256']==m.sha(HERE/'package_runtime.py') and
              runtime['tools_record_sha256']==m.sha(B/'bionic-tools.json'),'Stale native packaging')
    libraries={name:record['sha256'] for name,record in runtime['files'].items()}
    libraries['libp2dstorage.so']=storage['binary_sha256']
    helper=B/'storage-runtime/libp2dstorage.so'
    m.require(storage['builder_sha256']==m.sha(HERE/'build_storage.py') and
              storage['binary_sha256']==m.sha(helper),'Stale JNI helper')
    for name,digest in storage['sources'].items():m.require(m.sha(HERE/name)==digest,'Stale JNI source')
    exports=subprocess.check_output(['nm','-D',str(helper)],text=True)
    for name in ('StoragePublish_publishNoReplace','StoragePublish_copyNoReplace','StoragePublish_syncDirectoryPath'):
        m.require('Java_com_samsixx_pocket2droid_'+name in exports,'Missing renamed JNI export: '+name)
    m.require('Java_com_samsixx_' not in exports and 'p2d_test_' not in exports,'Old/test JNI implementation packaged')
    signature=m.validate_apk(apk,PACKAGE,False,libraries,m.sha(B/'dex/classes.dex'))
    for name,digest in libraries.items():
        path=helper if name==helper.name else B/'runtime'/name
        m.require(m.sha(path)==digest,'Runtime binary differs: '+name)
        loads=[line for line in subprocess.check_output(['readelf','-lW',str(path)],text=True).splitlines() if 'LOAD ' in line]
        m.require(loads and all(int(line.split()[-1],16)>=16384 for line in loads),'ELF alignment failed: '+name)
    old_runtime=m.load(previous/'runtime.json')
    m.require(set(runtime['files'])==set(old_runtime['files']),'Unexpected runtime dependency change')
    for name,record in runtime['files'].items():
        if name!='libp2dengine.so':m.require(record==old_runtime['files'][name],'Audio/dependency library changed: '+name)
    badging=subprocess.check_output([str(m.SDK/'aapt2'),'dump','badging',str(apk)],text=True)
    m.require("application-label:'Pocket2Droid'" in badging and
              "application: label='Pocket2Droid'" in badging,'App label includes wrong name/version')
    manifest=m.parse_manifest(apk)
    launcher=[a for a in manifest.get('activity',[]) if a.get('name')==PACKAGE+'.MainActivity']
    m.require(len(launcher)==1 and not manifest.get('activity-alias'),'Wrong launcher identity')
    tested=m.tested_source_hashes()
    frontend=m.load(B/'icon-controls/frontend-verification.json')
    for name,digest in frontend['source_sha256'].items():m.require(m.sha(HERE/name)==digest,'Frontend verification stale: '+name)
    m.require(frontend['java_sources']==30 and frontend['java_dex_resources_pass'],'Missing frontend build verification')
    checks={'v665-host.log':('PASS ROM repository 71','PASS ROM settings/geometry 71','115 control geometry/input assertions passed'),
            'v665-fallback.log':('PASS ROM repository 71','PASS ROM settings/geometry 71','115 control geometry/input assertions passed'),
            'v665-keyboard.log':('Ran 7 tests','OK')}
    for name,markers in checks.items():
        text=(B/'icon-controls'/name).read_text()
        m.require(all(marker in text for marker in markers),'Focused check failed: '+name)
    pixels=m.load(B/'icon-controls/v665-packaged-artwork.json')
    m.require(pixels['apk_sha256']==app['apk_sha256'] and len(pixels['artwork'])==21
              and all(row['rgba_pixels_identical'] for row in pixels['artwork']),'Packaged artwork proof missing/stale')
    with zipfile.ZipFile(apk) as z:
        m.require({n for n in z.namelist() if n.startswith('assets/')}=={'assets/QEMU-COPYING.txt'},'ROM/game/save data inside APK')
        m.require({n for n in z.namelist() if n.startswith('res/') and n.endswith('.png')}==
                  {row['apk_entry'] for row in pixels['artwork']},'Missing/extra APK artwork')
        for row in pixels['artwork']:
            m.require(m.sha(P/row['source'])==row['source_sha256'],'Supplied art changed: '+row['source'])
            m.require(m.sha(HERE/row['resource_path'])==row['resource_sha256'],'Resource source changed')
            m.require(hashlib.sha256(z.read(row['apk_entry'])).hexdigest()==row['apk_resource_sha256'],'Compiled artwork changed')
    stage=Path(tempfile.mkdtemp(prefix='.seal-6.65-',dir=release.parent))
    try:
        delivered=stage/'Pocket2Droid-V6.65-On-Screen-Controls-TCG-SIGNED.apk'
        shutil.copy2(apk,delivered)
        source=stage/'Pocket2Droid-V6.65-On-Screen-Controls-TCG-Source.zip'
        print('Signature, identity, 16KiB alignment and artwork verified; archiving exact source.',flush=True)
        inventory=m.snapshot_sources(source,{'native':native,'runtime':runtime})
        with zipfile.ZipFile(source) as z:
            for name,digest in inventory.items():m.require(hashlib.sha256(z.read(name)).hexdigest()==digest,'Source archive entry differs: '+name)
            for name,digest in tested.items():m.require(inventory['android/'+name]==digest,'Verified source/archive mismatch: '+name)
            for name,digest in native['source']['paths'].items():m.require(inventory['qemu-canonical-changes/'+name]==digest,'Native source archive mismatch')
            for name,digest in native['runtime_source_hashes'].items():m.require(inventory['qemu-android-exact/'+name]==digest,'Android adaptation archive mismatch')
            for row in pixels['artwork']:m.require(inventory['android/'+row['resource_path']]==row['resource_sha256'],'Artwork archive differs')
        for name in ('candidate-build.json','bionic-engine.json','runtime.json','bionic-tools.json','storage-runtime.json'):
            shutil.copy2(B/name,stage/name)
        shutil.copy2(Path(__file__),stage/'candidate-release-recipe.py')
        (stage/'candidate-signature.txt').write_text(signature)
        evidence=stage/'evidence';evidence.mkdir()
        for name in (*checks,'v665-build.log','v665-storage.log','v665-runtime.log','v665-packaged-artwork.json','verification.json','scope.diff'):
            shutil.copy2(B/'icon-controls'/name,evidence/name)
        (evidence/'tested-sources-v665.json').write_text(json.dumps(tested,indent=2)+'\n')
        (evidence/'application-badging.txt').write_text(badging)
        verification=dict(version=m.VERSION,version_code=m.VERSION_CODE,app_name='Pocket2Droid',package=PACKAGE,
            apk_sha256=m.sha(delivered),original_signer=m.SIGNER,signature_verified=True,
            apk_and_elf_alignment_16k=True,exact_dex_and_native_identity=True,renamed_jni_exports_verified=True,
            source_archive_sha256=m.sha(source),source_snapshot_files=len(inventory),baseline_preserved=True,
            supplied_control_pngs=14,compiled_artwork_rgba_identical=True,control_assertions=115,keyboard_qmp_tests=7,
            repository_assertions=71,settings_geometry_assertions=71,storage_fallback_tested=True,
            multi_pointer_controls=True,vibration_feedback=True,controls_transparency=True,per_rom_screen_position=True,
            physical_phone_test_pending=True,phone_modified=False,performance_gain_claimed=False,
            app_id_change_user_authorized=True,installs_separately_from_old_package=True)
        (stage/'FINAL_VERIFICATION.json').write_text(json.dumps(verification,indent=2)+'\n')
        (stage/'INSTALL.txt').write_text(
            'Pocket2Droid V6.65 (665), ARM64 Android 7.0+ (API24). App label remains Pocket2Droid.\n'
            'Requested app ID: com.samsixx.pocket2droid. This installs separately from com.samsixx.wm6android.\n'
            'Normally Exit the older app before opening this build: both can use the shared pocket2droid folder.\n'
            'Do not uninstall, clear data or reset either guest. Allow storage access when Android asks.\n'
            'All ROMs use supplied soft keys/Back/Call/End/Home/D-pad/smaller Select and held overlays.\n'
            'Controls stay on a black bottom panel, including fullscreen. Multiple fingers can hold independent keys.\n'
            'App settings: Controls transparency, then Vibration feedback (default on; respects Android haptic settings).\n'
            'ROM Display settings: Screen Position below Orientation: Top/Center/Bottom. Only the guest moves.\n'
            'Brief phone check: hold a direction + Select, release Select while retaining direction; check soft keys and cancellation.\n'
            'Check transparency, vibration, screen positions and landscape/fullscreen; normally Exit to save afterwards.\n'
            'Local compilation/input/settings/storage regressions and signature/identity/artwork/alignment checks pass.\n'
            'Phone UI/boot, vibration and TalkBack remain untested for this APK. No performance gain is claimed.\n'
            'No Windows Mobile ROM, CAB/game, saves or signing keys are bundled. V6.64 artifacts are preserved.\n')
        m.require(baseline=={str(p.relative_to(previous)):m.sha(p) for p in previous.rglob('*') if p.is_file()},'V6.64 changed while sealing')
        m.require(m.sha(delivered)==app['apk_sha256'],'Delivered APK changed')
        files=sorted(p for p in stage.rglob('*') if p.is_file())
        (stage/'SHA256SUMS.txt').write_text(''.join(m.sha(p)+'  '+str(p.relative_to(stage))+'\n' for p in files))
        m.publish_release(stage,release)
        print(json.dumps(dict(apk=str(release/delivered.name),sha256=app['apk_sha256'],version=m.VERSION,
                              package=PACKAGE,source_snapshot_files=len(inventory),baseline_preserved=True)),flush=True)
    finally:
        if stage.exists():
            m.require(stage.parent.resolve()==release.parent.resolve() and stage.name.startswith('.seal-6.65-'),'Unsafe staging cleanup')
            shutil.rmtree(stage)

if __name__=='__main__':main()
