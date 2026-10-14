"""Seal V6.62 against immutable V6.61 and current consolidated verification."""
from pathlib import Path
import hashlib,importlib.util,json,shutil,tempfile,zipfile,subprocess
HERE=Path(__file__).resolve().parent;B=HERE/'build';P=HERE.parents[2]
spec=importlib.util.spec_from_file_location('integrity',HERE/'finalize_release.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.VERSION,m.VERSION_CODE='6.62',662
def main():
 previous=P/'apk/6.61';release=P/'apk/6.62';m.require(not release.exists(),'Never overwrite an existing release')
 baseline={p.name:m.sha(p) for p in previous.iterdir() if p.is_file()}
 app,native,runtime,storage,smoke=(m.load(B/n) for n in ('candidate-build.json','bionic-engine.json','runtime.json','storage-runtime.json','smoke-build.json'))
 apk=Path(app['signed_apk']);m.require(app['version']=='6.62' and not app['test_only'] and m.sha(apk)==app['apk_sha256'],'Wrong or changed candidate')
 old=m.load(previous/'bionic-engine.json');changes={n for n,d in native['source']['paths'].items() if old['source']['paths'].get(n)!=d}
 m.require(changes=={'hw/arm/pocket2droid-devemu.c'} and set(native['source']['paths'])==set(old['source']['paths']),'Unexpected native change')
 m.require(storage==m.load(previous/'storage-runtime.json'),'Storage publication helper changed')
 oldruntime=m.load(previous/'runtime.json');m.require(set(runtime['files'])==set(oldruntime['files']),'Runtime closure changed')
 for name,record in runtime['files'].items():
  if name!='libp2dengine.so':m.require(record==oldruntime['files'][name],'Runtime dependency changed: '+name)
  m.require(m.sha(B/'runtime'/name)==record['sha256'],'Runtime identity changed')
  for line in subprocess.check_output(['readelf','-lW',str(B/'runtime'/name)],text=True).splitlines():
   if 'LOAD ' in line:m.require(int(line.split()[-1],16)>=16384,'ELF load alignment invalid: '+name)
 for name,digest in native['source']['paths'].items():m.require(m.sha(HERE.parent/'qemu'/name)==digest,'Canonical native source changed')
 for name,digest in native['runtime_source_hashes'].items():m.require(m.sha(m.NATIVE/name)==digest,'Compiled native source changed')
 m.require(native['builder_sha256']==m.sha(HERE/'build_bionic.py') and native['binary_sha256']==m.sha(B/'libp2dengine-bionic.so'),'Native compiler identity changed')
 libraries={name:r['sha256'] for name,r in runtime['files'].items()};libraries['libp2dstorage.so']=storage['binary_sha256']
 signature=m.validate_apk(apk,'com.samsixx.wm6android',False,libraries,m.sha(B/'dex/classes.dex'))
 m.validate_apk(Path(smoke['signed_apk']),'com.samsixx.p2dtest',True,libraries,m.sha(B/'dex/classes.dex'))
 ui=m.load(B/'library-tests/pc-ui-result.json');theme=m.load(B/'library-tests/theme-result.json');guest=m.load(B/'library-tests/display-guest-result.json')
 m.require(ui['rom_settings_fullscreen_exit_delete'] and not ui['phone_modified'],'Current PC UI integration missing')
 m.require(theme['live_activity_retained'] and theme['normal_exit'] and len(theme['checks'])==2 and not theme['phone_modified'],'System theme integration missing')
 m.require(len(guest['cases'])==3 and all(r['normal_exit'] and r['original_rom_unchanged'] for r in guest['cases']),'Whole guest display checks missing')
 m.require(guest['cases'][1]['dimensions']==[480,480] and guest['cases'][2]['dimensions']==[320,240],'Real guest dimensions not observed')
 checks={'ui-fixes-host.log':'PASS ROM settings/geometry 14','ui-fixes-fallback.log':'PASS ROM repository 61','ui-fixes-storage.log':'PASS StorageLayout 51','ui-fixes-storage-fallback.log':'PASS StorageFallback 28','ui-fixes-native.log':'OK','messages-green.log':'retry notification','ui-fixes-pc-final.log':'"rom_settings_fullscreen_exit_delete": true','ui-fixes-theme-final.log':'PASS system light/dark','ui-fixes-layout.log':'PASS small-screen','ui-fixes-landscape.log':'PASS landscape','EngineKeyTest-art.log':'PASS actual Engine ART','AudioPlayerArtTest-art.log':'PASS','InsetBackdropArtTest-art.log':'PASS actual Canvas'}
 for name,marker in checks.items():m.require(marker in (B/'library-tests'/name).read_text(),'Required check missing: '+name)
 tested=m.tested_source_hashes();m.require(tested==m.load(B/'library-tests/tested-sources-v662.json'),'Android sources changed since final testing')
 with zipfile.ZipFile(apk) as z:m.require({n for n in z.namelist() if n.startswith('assets/')}=={'assets/QEMU-COPYING.txt'},'Unexpected ROM/game/save assets')
 stage=Path(tempfile.mkdtemp(prefix='.seal-6.62-',dir=release.parent))
 try:
  delivered=stage/'Pocket2Droid-V6.62-UI-Fixes-TCG-SIGNED.apk';shutil.copy2(apk,delivered)
  source=stage/'Pocket2Droid-V6.62-UI-Fixes-TCG-Source.zip';inventory=m.snapshot_sources(source,{'native':native,'runtime':runtime})
  with zipfile.ZipFile(source) as z:
   m.require(z.testzip() is None,'Source archive CRC failure')
   for name,digest in tested.items():m.require(inventory['android/'+name]==digest,'Tested source/archive mismatch')
   for name,digest in inventory.items():m.require(hashlib.sha256(z.read(name)).hexdigest()==digest,'Archive identity mismatch')
  for name in ('candidate-build.json','bionic-engine.json','runtime.json','bionic-tools.json','storage-runtime.json'):shutil.copy2(B/name,stage/name)
  shutil.copy2(Path(__file__),stage/'candidate-release-recipe.py');(stage/'candidate-signature.txt').write_text(signature)
  evidence=stage/'evidence';evidence.mkdir()
  for name in list(checks)+['display-guest-result.json','pc-ui-result.json','theme-result.json','layout-result.json','landscape-result.json','tested-sources-v662.json','fixes-progress.md','ui-fixes-scope.diff','boot-display-red.log','boot-display-green.log','storagecard-red.log','messages-red.log','ui-fixes-audio.log']:shutil.copy2(B/'library-tests'/name,evidence/name)
  for name in ('pc-theme-yes-library.png','pc-theme-no-library.png','pc-theme-yes-popup.png','pc-theme-no-popup.png','pc-theme-yes-settings.png','pc-theme-no-settings.png','pc-library-small.png','pc-session-landscape.png','pc-fullscreen.png'):shutil.copy2(B/'library-tests'/name,evidence/name)
  for row in guest['cases']:
   p=Path(row['screenshot']).with_suffix('.png');shutil.copy2(p,evidence/p.name)
  verification=dict(version='6.62',signature=True,original_signer=m.SIGNER,alignment_16k=True,source_identity=True,native_changes=sorted(changes),baseline_preserved=True,phone_modified=False,physical_phone_ui_validation_pending=True,performance_gain_claimed=False,rom_default='Known SDK filenames/collision suffixes; unknown QVGA; explicit presets override',full_os_vga_square_480x480_observed=True)
  (stage/'FINAL_VERIFICATION.json').write_text(json.dumps(verification,indent=2)+'\n')
  (stage/'INSTALL.txt').write_text('Install V6.62 as an update after normal EXIT. Keep existing app data; do not uninstall or clear data.\nLong-press ROM opens Settings popup; tap starts it. Content/settings follow system light/dark; toolbar stays dark.\nNew profiles start fresh without a migration popup; existing per-ROM internal data and card paths are reused. Old unassigned saves remain untouched.\nNew ROMs default to pocket2droid/storagecard. Existing folders/assignments are not renamed or moved.\nROM default recognizes known SDK filenames (including import suffixes); unfamiliar filenames use240x320. Choose an explicit preset for renamed/custom ROMs.\nPPC_USA_GSM_VGA_SQUARE_VR.BIN starts at480x480; presets configure actual guest boot dimensions. Screen fit only controls host scaling.\nGuest/system inset borders are black; enabled FPS/keys remain in fullscreen. Back opens menu; Exit saves/stops.\nAudio/engine errors remain visible in dialogs; ordinary sound status strip removed.\nVerified on PC Android API30 and copied full OS on Linux. Physical phones and API24/25/35/36 UI runtime remain untested.\nNo bundled ROM/game/CAB/save; no CPU/JIT performance change. Baseline6.61 retained.\n')
  m.require(baseline=={p.name:m.sha(p) for p in previous.iterdir() if p.is_file()},'Baseline changed')
  files=sorted(p for p in stage.rglob('*') if p.is_file());(stage/'SHA256SUMS.txt').write_text(''.join(m.sha(p)+'  '+str(p.relative_to(stage))+'\n' for p in files))
  m.publish_release(stage,release);print(json.dumps(dict(apk=str(release/delivered.name),sha256=app['apk_sha256'],version='6.62',original_signer=True,baseline_preserved=True)),flush=True)
 finally:
  if stage.exists():m.require(stage.parent.resolve()==release.parent.resolve() and stage.name.startswith('.seal-6.62-'),'Unsafe cleanup');shutil.rmtree(stage)
if __name__=='__main__':main()
