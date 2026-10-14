"""Mirror verified source into the local review preview, never commit/upload."""
from pathlib import Path
import json,hashlib,shutil
android=Path(__file__).resolve().parents[1];src=android.parent;root=android.parents[2];out=android/'build/button-mapping';preview=root/'GITHUB_PREVIEW/Pocket2Droid'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
scope=json.loads((out/'scope.json').read_text());copied=[]
for name in scope:
    if name.endswith('prepare_button_mapping.py'):continue
    targets=[name]
    if name.startswith('qemu/'):
        targets=[name.replace('qemu/','qemu-android-exact/',1),name.replace('qemu/','qemu-canonical-changes/',1)]
    for target in targets:
        source=src/name;destination=preview/target
        assert destination.resolve().is_relative_to(preview.resolve())
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination);assert sha(source)==sha(destination);copied.append(target)
deltaPath=preview/'PREVIEW_CHANGES.json';delta=json.loads(deltaPath.read_text())
known={entry['after'] for entry in delta['changes']+delta['added_files']}
for target in copied:
    if target not in known:delta['added_files'].append({'after':target,'after_sha256':sha(preview/target)});known.add(target)
for entry in delta['changes']+delta['added_files']:entry['after_sha256']=sha(preview/entry['after'])
feature='Global Button Mapping with illustrated 25-key keypad, automatic saving, keyboard/controller buttons, D-pad, sticks/triggers and independent ownership'
if feature not in delta['unreleased_features']:delta['unreleased_features'].append(feature)
followup='Inset-safe Button Mapping with toolbar Reset and system-theme keypad; original native ROM loading GIF fits any aspect ratio on black until the first visible posted guest image'
if followup not in delta['unreleased_features']:delta['unreleased_features'].append(followup)
delta['button_mapping_verification']='../BUTTON_MAPPING_VERIFICATION.json'
delta['note']='Review preview includes unreleased frontend/input features after sealed V6.65. Original SOURCE_SHA256 baseline is retained; sealed release is unchanged. No GitHub action.'
deltaPath.write_text(json.dumps(delta,indent=2)+'\n')
record=json.loads((out/'verification.json').read_text());record['assets']=json.loads((out/'assets.json').read_text())
tested=json.loads((out/'android/sources.json').read_text())
for name,want in tested.items():assert sha(android/name)==want,name
record['android_tested_source_sha256']=tested
record['android_mapping_log']=(out/'android/green-all.log').read_text()
assert 'PASS ' in record['android_mapping_log'] and 'FAIL ' not in record['android_mapping_log']
loading_tested=json.loads((out/'android/loading-sources.json').read_text())
for name,want in loading_tested.items():assert sha(android/name)==want,name
record['loading_tested_source_sha256']=loading_tested
record['ui_followup']={'loading_asset':json.loads((out/'loading-asset.json').read_text()),
 'loading_host':(out/'loading-host-green.log').read_text(),
 'loading_android':(out/'android/green-loading.log').read_text(),
 'light_mapping':(out/'layout-update/theme-light-green.log').read_text(),
 'dark_mapping':(out/'layout-update/theme-dark-green.log').read_text(),
 'red_evidence':['layout-update/red.log','layout-update/theme-red.log','layout-update/loading-red.log','layout-update/animation-red.log'],
 'aspect_ratios':'Rendered pixel bounds checked at portrait, landscape, square and tablet proportions through both native decoders; black corners verified.',
 'limits':'Owned Android API30 fixtures; no full OS boot, physical phone or real-controller confirmation.'}
assert all('PASS ' in record['ui_followup'][key] and 'FAIL ' not in record['ui_followup'][key] for key in ('loading_android','light_mapping','dark_mapping'))
record['final_review']={'verdict':'Two Important findings fixed in one pass; no Critical findings. No second review.',
 'resolved':['Recover missed key-up using press identity and gate time, preserving held-repeat rejection and alias coalescing.','Retain actual observed axis neutral state when arming capture.'],
 'red_android':(out/'review-android-red.log').read_text(),'red_axis':(out/'review-normalizer-red.log').read_text(),
 'green_host':(out/'review-host-green.log').read_text(),
 'save_failure':'Android failed-commit/cache-rollback test passes alongside mapping and runtime checks.'}
record['legacy_android_lifecycle']={'denied':(out/'lifecycle-denied/green.log').read_text(),'granted':(out/'lifecycle-denied/granted.log').read_text()}
assert all('PASS ' in log for log in record['legacy_android_lifecycle'].values())
for label in ('green','granted'):
    for name,want in json.loads((out/f'lifecycle-denied/{label}-sources.json').read_text()).items():assert sha(android/name)==want,name
record['existing_library_checks']=(out/'library.log').read_text()
record['preview_sha256']={p:sha(preview/p) for p in copied}
sealed={'Pocket2Droid-V6.65-On-Screen-Controls-TCG-SIGNED.apk':'46437016168727445852a949cba847361a5edafd1b63dde5b7a881c85e99f4fe','Pocket2Droid-V6.65-On-Screen-Controls-TCG-Source.zip':'4aa74e6b12f709ada148a1ad1150246ab306ef5bfe6c2d0f6861760299711d14'}
for name,want in sealed.items():assert sha(root/'apk/6.65'/name)==want,name
record['sealed_v665_unchanged']=sealed
(root/'GITHUB_PREVIEW/BUTTON_MAPPING_VERIFICATION.json').write_text(json.dumps(record,indent=2)+'\n')
summaryPath=root/'GITHUB_PREVIEW/VERIFICATION.json';summary=json.loads(summaryPath.read_text());summary['unreleased_features']=delta['unreleased_features'];summary['button_mapping_verification']='BUTTON_MAPPING_VERIFICATION.json';summary['preview_note']=delta['note'];summaryPath.write_text(json.dumps(summary,indent=2)+'\n')
for entry in delta['changes']+delta['added_files']:assert sha(preview/entry['after'])==entry['after_sha256']
print(f'{len(copied)} exact source/resource/test files mirrored; all preview delta hashes pass; sealed V6.65 APK/source unchanged')
