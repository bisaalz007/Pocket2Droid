"""Seal the approved V6.61 UI candidate; retain baseline and source identity."""
from pathlib import Path
import hashlib,importlib.util,json,shutil,tempfile,zipfile
HERE=Path(__file__).resolve().parent;B=HERE/'build';P=HERE.parents[2]
spec=importlib.util.spec_from_file_location('release_integrity',HERE/'finalize_release.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.VERSION,m.VERSION_CODE='6.61',661
def main():
    previous=P/'apk/6.60';release=P/'apk/6.61';m.require(not release.exists(),'Never overwrite an existing release')
    baseline={p.name:m.sha(p) for p in previous.iterdir() if p.is_file()}
    app,native,runtime,storage,smoke=(m.load(B/name) for name in ('candidate-build.json','bionic-engine.json','runtime.json','storage-runtime.json','smoke-build.json'))
    apk=Path(app['signed_apk']);m.require(app['version']=='6.61' and not app['test_only'] and m.sha(apk)==app['apk_sha256'],'Wrong or changed UI candidate')
    old=m.load(previous/'bionic-engine.json');changes={n for n,d in native['source']['paths'].items() if old['source']['paths'].get(n)!=d}
    m.require(changes=={'hw/display/p2d-devemu-lcd.c','include/hw/arm/p2d-frame.h'} and set(native['source']['paths'])==set(old['source']['paths']),'Unexpected CPU/TCG/audio/storage native change')
    m.require(storage==m.load(previous/'storage-runtime.json'),'Save publication helper changed')
    old_runtime=m.load(previous/'runtime.json');m.require(set(runtime['files'])==set(old_runtime['files']),'Runtime closure changed')
    for name,r in runtime['files'].items():
        if name!='libp2dengine.so':m.require(r==old_runtime['files'][name],'Runtime dependency changed: '+name)
        m.require(m.sha(B/'runtime'/name)==r['sha256'],'Runtime identity changed')
    for name,digest in native['source']['paths'].items():m.require(m.sha(HERE.parent/'qemu'/name)==digest,'Native source identity changed')
    for name,digest in native['runtime_source_hashes'].items():m.require(m.sha(m.NATIVE/name)==digest,'Compiled source identity changed')
    m.require(native['builder_sha256']==m.sha(HERE/'build_bionic.py') and native['binary_sha256']==m.sha(B/'libp2dengine-bionic.so'),'Compiler record changed')
    libraries={name:r['sha256'] for name,r in runtime['files'].items()};libraries['libp2dstorage.so']=storage['binary_sha256']
    signature=m.validate_apk(apk,'com.samsixx.wm6android',False,libraries,m.sha(B/'dex/classes.dex'))
    m.validate_apk(Path(smoke['signed_apk']),'com.samsixx.p2dtest',True,libraries,m.sha(B/'dex/classes.dex'))
    ui=m.load(B/'library-tests/pc-ui-result.json');guest=m.load(B/'library-tests/guest-result.json')
    m.require(ui.get('rom_settings_fullscreen_exit_delete') is True and ui.get('phone_modified') is False,'Consolidated isolated UI checks missing')
    m.require(guest['originals_unchanged'] and len(guest['steps'])==3 and all(s['other_save_unchanged'] and s['normal_exit'] for s in guest['steps']),'Guest isolation checks missing')
    visual=m.load(B/'library-tests/guest-visual-verification.json')
    m.require(visual.get('second_rom_today_visually_confirmed') is True and visual.get('automated_template_match') is False,'Second-ROM boot observation missing')
    m.require(m.sha(Path(visual['image']))==visual['image_sha256'],'Second-ROM screenshot changed')
    layout=m.load(B/'library-tests/layout-result.json');landscape=m.load(B/'library-tests/landscape-result.json')
    m.require(layout.get('toolbar_targets_48dp') and layout.get('nonoverlap') and landscape.get('normal_exit'),'Viewport checks missing')
    logs={'review-green.log':'PASS ROM repository 60','storage-final.log':'PASS StorageFallback 28','audio-final.log':'PASS session','frame-final.log':'PASS frame protocol','lcd-final.log':'OK','EngineKeyTest-art.log':'PASS actual Engine ART','AudioPlayerArtTest-art.log':'PASS'}
    for name,marker in logs.items():m.require(marker in (B/'library-tests'/name).read_text(),'Required check failed: '+name)
    tested=m.tested_source_hashes();m.require(tested==m.load(B/'library-tests/tested-sources.json'),'Android sources changed since final verification')
    with zipfile.ZipFile(apk) as z:
        m.require({n for n in z.namelist() if n.startswith('assets/')}=={'assets/QEMU-COPYING.txt'},'Unexpected ROM/game/save assets')
        for color in ('blue','teal','amber','violet'):m.require(any('rom_icon_'+color in n for n in z.namelist()),'Missing ROM icon')
    stage=Path(tempfile.mkdtemp(prefix='.seal-6.61-',dir=release.parent))
    try:
        delivered=stage/'Pocket2Droid-V6.61-ROM-Library-TCG-SIGNED.apk';shutil.copy2(apk,delivered)
        source=stage/'Pocket2Droid-V6.61-ROM-Library-TCG-Source.zip';inventory=m.snapshot_sources(source,{'native':native,'runtime':runtime})
        with zipfile.ZipFile(source) as z:
            m.require(z.testzip() is None,'Source archive CRC failure')
            for name,digest in tested.items():m.require(inventory['android/'+name]==digest,'Tested source archive mismatch')
            for name,digest in inventory.items():m.require(hashlib.sha256(z.read(name)).hexdigest()==digest,'Archive identity mismatch')
        for name in ('candidate-build.json','bionic-engine.json','runtime.json','bionic-tools.json','storage-runtime.json'):shutil.copy2(B/name,stage/name)
        shutil.copy2(Path(__file__),stage/'candidate-release-recipe.py');(stage/'candidate-signature.txt').write_text(signature)
        evidence=stage/'evidence';evidence.mkdir()
        for name in list(logs)+['repository-final.log','pc-ui.log','layout-final.log','landscape-final.log','pc-ui-result.json','guest-result.json','guest-visual-verification.json','layout-result.json','landscape-result.json','tested-sources.json','progress.md']:shutil.copy2(B/'library-tests'/name,evidence/name)
        for name in ('pc-library-final.png','pc-library-small.png','pc-session-landscape.png','pc-fullscreen.png','pc-rom-settings.png','pc-app-settings.png'):shutil.copy2(B/'library-tests'/name,evidence/name)
        (stage/'FINAL_VERIFICATION.json').write_text(json.dumps(dict(version='6.61',signature=True,original_signer=m.SIGNER,alignment_16k=True,source_identity=True,native_changes=sorted(changes),baseline_preserved=True,performance_gain_claimed=False,physical_phone_ui_validation_pending=True),indent=2)+'\n')
        (stage/'INSTALL.txt').write_text('Install V6.61 as an update only after normal EXIT. Do not uninstall or clear app data.\n+ imports only .bin ROM files, never overwriting an existing filename; duplicates gain (2), (3), etc.\nEach filename uses data/<filename>/ram-fmd.bin and profile.json. Existing unassigned data requires an explicit preserved copy/new-installation choice.\nNew ROMs default to pocket2droid/storage. Existing per-ROM card assignments stay unchanged when the default changes.\nTap ROM to start; hold for settings. Back in emulator opens menu; Exit saves/stops. Fullscreen keeps enabled FPS/keys.\nGuest resolution uses ROM default; other preset overrides are disabled. Native output up to1024x800 is supported.\nNo bundled ROM/game, no CAB import/button/dependency. Existing Storage Card files remain accessible.\nPC UI/ART and copied A->B->A OS checks passed; S25/DOOV/new UI and API24/25/36 physical runtime still require validation.\nV6.60 retained. No new CPU/JIT performance gain claimed.\n')
        m.require(baseline=={p.name:m.sha(p) for p in previous.iterdir() if p.is_file()},'Baseline changed')
        sums=sorted(p for p in stage.rglob('*') if p.is_file());(stage/'SHA256SUMS.txt').write_text(''.join(m.sha(p)+'  '+str(p.relative_to(stage))+'\n' for p in sums))
        m.publish_release(stage,release);print(json.dumps(dict(apk=str(release/delivered.name),sha256=app['apk_sha256'],version='6.61',original_signer=True,baseline_preserved=True)),flush=True)
    finally:
        if stage.exists():m.require(stage.parent.resolve()==release.parent.resolve() and stage.name.startswith('.seal-6.61-'),'Unsafe temporary cleanup');shutil.rmtree(stage)
if __name__=='__main__':main()
