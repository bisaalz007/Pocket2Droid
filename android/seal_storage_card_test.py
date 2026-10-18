"""Seal the authorized per-ROM StorageCard test update without device writes."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
import zipfile

HERE=Path(__file__).resolve().parent
ROOT,BUILD=HERE.parent,HERE/'build'
PROJECT=ROOT.parents[1]
PROOF=BUILD/'storage-card-setting'
VERSION,CODE='1.0.2-test9',680
spec=importlib.util.spec_from_file_location('card_release_integrity',HERE/'finalize_release.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.VERSION,m.VERSION_CODE=VERSION,CODE
digest=lambda data:hashlib.sha256(data).hexdigest()


def snapshot(target,native,runtime,previous):
    raw=target.with_name('.current-source.zip')
    m.snapshot_sources(raw,{'native':native,'runtime':runtime})
    inventory={}
    with zipfile.ZipFile(raw) as current,zipfile.ZipFile(previous) as prior,zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=4) as final:
        for archive in (current,prior):
            for info in archive.infolist():
                name=info.filename
                if name=='SOURCE_SHA256.json' or name.endswith('-TEST-BUILD.txt') or name in inventory:continue
                data=archive.read(info);final.writestr(info,data);inventory[name]=digest(data)
        note=('Pocket2Droid '+VERSION+'/code680 per-ROM StorageCard folder selection.\n'
              'General StorageCard and File-to-StorageCard import location stay fixed.\n'
              'ROM settings opens Cancel/Continue warning, then validated folder picker.\n'
              'Warning omits the rejected scope sentence; no file move or reset.\n'
              '36 actual PC Android UI checks and repository133/settings98 in normal\n'
              'and fallback modes pass. Native/helper/resources equal signed test8.\n'
              'Build recipes retain documented WSL/cache/signing assumptions.\n'
              'No ROM, SDK, game, personal save, phone data or signing key bundled.\n'
              'Real phone selection/guest access confirmation remains pending.\n').encode()
        final.writestr('STORAGE-CARD-TEST-BUILD.txt',note);inventory['STORAGE-CARD-TEST-BUILD.txt']=digest(note)
        final.writestr('SOURCE_SHA256.json',json.dumps(inventory,indent=2)+'\n')
    raw.unlink()
    with zipfile.ZipFile(target) as archive:
        m.require(archive.testzip() is None and len(archive.namelist())==len(set(archive.namelist())),'Source CRC/duplicates failed')
        for name,expected in inventory.items():m.require(digest(archive.read(name))==expected,'Source differs: '+name)
    return inventory


def main():
    prior=PROJECT/'apk/1.0.2-test8';release=PROJECT/'apk'/VERSION
    m.require(not release.exists(),'Preserve existing release')
    old_apk=prior/'Pocket2Droid-v1.0.2-test8-Existing-ROM-Internet.apk'
    old_source=prior/'Pocket2Droid-v1.0.2-test8.Source.zip'
    m.require(m.sha(old_apk)=='343d1fd3c80320c8a81c7ee7a3f4859ba5e39464c368f3857f7cbbd2a3c470e9','Test8 APK changed')
    m.require(m.sha(old_source)=='fb53d59008024c251e37e0f62592377a17ce1e64d94509c3c06ca82a9b5843ab','Test8 source changed')
    protected={p.relative_to(prior).as_posix():m.sha(p) for p in prior.rglob('*') if p.is_file()}
    app,native,runtime,storage=(m.load(BUILD/name) for name in ('candidate-build.json','bionic-engine.json','runtime.json','storage-runtime.json'))
    for name,record in (('bionic-engine.json',native),('runtime.json',runtime),('storage-runtime.json',storage)):
        m.require(record==m.load(prior/name),'Native/runtime/storage changed: '+name)
    for name,expected in native['source']['paths'].items():m.require(m.sha(ROOT/'qemu'/name)==expected,'Stale canonical source')
    for name,expected in native['runtime_source_hashes'].items():m.require(m.sha(m.NATIVE/name)==expected,'Stale compiled source')
    tested=m.tested_source_hashes();changed=[]
    with zipfile.ZipFile(old_source) as old:
        for name in tested:
            data=(HERE/name).read_bytes()
            if name=='AndroidManifest.xml':data=data.replace(b'android:versionCode="680"',b'android:versionCode="679"').replace(b'android:versionName="1.0.2-test9"',b'android:versionName="1.0.2-test8"')
            if data!=old.read('android/'+name):changed.append(name)
        m.require(changed==['src/com/samsixx/pocket2droid/RomSettingsActivity.java'],'Unexpected frontend scope: '+repr(changed))
        builder=(HERE/'build.py').read_bytes().replace(b"VERSION = '1.0.2-test9'",b"VERSION = '1.0.2-test8'").replace(b'VERSION_CODE = 680',b'VERSION_CODE = 679')
        m.require(builder==old.read('android/build.py'),'Unexpected build recipe change')
        readme=old.read('README.md')
    proof=m.load(PROOF/'RESULT.json')
    m.require(proof['android_ui_checks']==36 and proof['review_actionable_findings']==0,'Acceptance/review missing')
    for name,expected in proof['source_hashes'].items():m.require(m.sha(HERE/name)==expected,'Accepted source changed: '+name)
    for name,expected in proof['logs'].items():m.require(m.sha(PROOF/name)==expected,'Acceptance evidence changed: '+name)
    for name,expected in m.load(PROOF/'red-ui/granted-sources.json').items():m.require(m.sha(HERE/name)==expected,'Android-tested source changed: '+name)
    m.require('The ROM StorageCard row must be clickable' in (PROOF/'red.log').read_text(),'Missing RED assertion')
    text=(PROOF/'green.log').read_text();m.require('PASS 36 real Android StorageCard checks' in text and 'ERROR ' not in text,'UI checks failed')
    for name in ('library.log','library-fallback.log'):
        text=(PROOF/name).read_text();m.require('PASS ROM repository 133' in text and 'PASS ROM settings/geometry 98' in text,'Filesystem/settings checks failed')
    libraries={name:row['sha256'] for name,row in runtime['files'].items()};libraries['libp2dstorage.so']=storage['binary_sha256']
    for name,expected in libraries.items():
        file=BUILD/('storage-runtime' if name=='libp2dstorage.so' else 'runtime')/name
        m.require(m.sha(file)==expected,'Native payload differs')
        loads=[line for line in subprocess.check_output(['readelf','-lW',str(file)],text=True).splitlines() if 'LOAD ' in line]
        m.require(loads and all(int(line.split()[-1],16)>=16384 for line in loads),'ELF alignment failed')
    apk=Path(app['signed_apk'])
    m.require(app['version']==VERSION and app['package']=='com.samsixx.pocket2droid' and not app['test_only'] and app['apk_sha256']==m.sha(apk),'APK identity differs')
    signature=m.validate_apk(apk,'com.samsixx.pocket2droid',False,libraries,m.sha(BUILD/'dex/classes.dex'))
    manifest=m.parse_manifest(apk);m.require(not manifest.get('instrumentation') and not manifest.get('provider'),'Test fixtures packaged')
    with zipfile.ZipFile(old_apk) as old,zipfile.ZipFile(apk) as current:
        fixed=lambda z:{name:digest(z.read(name)) for name in z.namelist() if name.startswith(('assets/','res/','lib/')) or name=='resources.arsc'}
        m.require(fixed(old)==fixed(current),'Native/helper/artwork changed from test8')
        m.require(b'Lcom/samsixx/pocket2droid/StorageCardUiTest;' not in current.read('classes.dex'),'Instrumentation compiled into app')
    stage=Path(tempfile.mkdtemp(prefix='.seal-storage-card-',dir=release.parent))
    try:
        delivered=stage/('Pocket2Droid-v'+VERSION+'-StorageCard.apk');shutil.copy2(apk,delivered)
        source=stage/('Pocket2Droid-v'+VERSION+'.Source.zip')
        print('Signature/package/version, payload and16KiB alignment verified; archiving source.',flush=True)
        inventory=snapshot(source,native,runtime,old_source)
        for name,expected in tested.items():m.require(inventory['android/'+name]==expected,'Frontend snapshot differs')
        for name,expected in native['source']['paths'].items():m.require(inventory['qemu-canonical-changes/'+name]==expected,'Native snapshot differs')
        for name,expected in native['runtime_source_hashes'].items():m.require(inventory['qemu-android-exact/'+name]==expected,'Compiled snapshot differs')
        with zipfile.ZipFile(source) as archive:m.require(archive.read('README.md')==readme,'README changed')
        for name in ('candidate-build.json','bionic-engine.json','runtime.json','bionic-tools.json','storage-runtime.json'):shutil.copy2(BUILD/name,stage/name)
        shutil.copy2(Path(__file__),stage/'candidate-release-recipe.py');(stage/'candidate-signature.txt').write_text(signature,encoding='utf-8')
        evidence=stage/'evidence';evidence.mkdir()
        for name in ('red.log','green.log','library.log','library-fallback.log','RESULT.json','scope.json','source.diff','review.txt','storage-card-warning.png','storage-card-selected.png'):shutil.copy2(PROOF/name,evidence/name)
        shutil.copy2(PROOF/'red-ui/granted-sources.json',evidence/'android-tested-sources.json')
        record=dict(version=VERSION,version_code=CODE,package='com.samsixx.pocket2droid',apk_sha256=m.sha(delivered),source_archive_sha256=m.sha(source),source_snapshot_files=len(inventory),original_signer=m.SIGNER,
                    signature_verified=True,apk_and_elf_alignment_16k=True,exact_native_and_dex_identity=True,native_helper_and_resources_identical_to_test8=True,
                    changed_product_java_files=changed,android_ui_checks=36,repository_checks=133,settings_checks=98,filesystem_modes=['normal','fallback'],
                    review_actionable_findings=0,general_storagecard_fixed=True,per_rom_card_selectable=True,warning_scope_sentence_removed=True,
                    readme_unchanged=True,phone_validation_pending=True,phone_accessed=False,earlier_release_preserved=True,github_modified=False,
                    build_seconds=app['seconds'])
        (stage/'FINAL_VERIFICATION.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
        (stage/'INSTALL.txt').write_text('Pocket2Droid1.0.2-test9/code680 StorageCard test.\n'
            'Exit the current ROM normally, then install this APK as an update.\n'
            'Do not uninstall, clear data or reimport ROMs. Existing saves remain.\n'
            'ROM settings > StorageCard folder now opens a Cancel/Continue warning.\n'
            'Cancel must preserve the current path. Continue opens the folder picker;\n'
            'use a dedicated test folder and choose Use this folder.\n'
            'Start the ROM and check that its Storage Card shows that folder, then\n'
            'exit/reopen and confirm the selection persists. Other ROMs and the\n'
            'general File to StorageCard destination should remain unchanged.\n'
            'Folder selection does not move old files.\n'
            '36 actual PC Android UI checks pass; phone validation is pending.\n',encoding='utf-8')
        m.require(protected=={p.relative_to(prior).as_posix():m.sha(p) for p in prior.rglob('*') if p.is_file()},'Test8 changed')
        (stage/'SHA256SUMS.txt').write_text(''.join(m.sha(p)+'  '+p.relative_to(stage).as_posix()+'\n' for p in sorted(stage.rglob('*')) if p.is_file()),encoding='utf-8')
        m.publish_release(stage,release);print(json.dumps(dict(apk=str(release/delivered.name),**record),indent=2),flush=True)
    finally:
        if stage.exists():
            m.require(stage.parent.resolve()==release.parent.resolve() and stage.name.startswith('.seal-storage-card-'),'Unsafe stage cleanup')
            shutil.rmtree(stage)


if __name__=='__main__':main()
