"""Seal the authorized Internet test APK; retain test3 and exact source/notices."""
from pathlib import Path
import hashlib, importlib.util, json, shutil, stat, subprocess, tempfile, zipfile
HERE=Path(__file__).resolve().parent;B=HERE/'build';PROJECT=HERE.parents[2]
VERSION,CODE='1.0.2-test4',675
spec=importlib.util.spec_from_file_location('network_integrity',HERE/'finalize_release.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.VERSION,m.VERSION_CODE=VERSION,CODE

def snapshot(target,native,runtime,previous):
    raw=target.with_name('.current-network-source.zip');m.snapshot_sources(raw,{'native':native,'runtime':runtime})
    inventory={}
    with zipfile.ZipFile(raw) as current,zipfile.ZipFile(previous) as old,zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=4) as final:
        for archive in (current,old):
            for info in archive.infolist():
                name=info.filename
                if name in ('SOURCE_SHA256.json','WM5-TEST-BUILD.txt','NETWORK-TEST-BUILD.txt') or name in inventory:continue
                data=archive.read(info);final.writestr(info,data);inventory[name]=hashlib.sha256(data).hexdigest()
        note=('Pocket2Droid '+VERSION+' / code675 - private Internet test\n'
              'Build entry: android/build.py; canonical overlay: qemu-canonical-changes/.\n'
              'Exact Bionic source: qemu-android-exact/. Source/dependency provenance and upstream\n'
              'libslirp4.9.5 source/COPYRIGHT/patch accompany this archive. Existing WSL/NDK setup\n'
              'is required; a clean-machine application build is not claimed.\n'
              'Optional per-ROM Internet access, NE2000 PC Card and user-mode NAT/private DNS.\n'
              '164 native tests and Android frontend/ownership checks pass. WM6 DHCP/DNS/HTTP\n'
              'and Google render on PC; ARM64 Android guest networking still needs phone testing.\n'
              'WM5 local HTTP works; its public page did not complete in the bounded test.\n'
              'Retains WM5 retained-RAM, Restart and uncapped custom resolution features.\n'
              'No Microsoft SDK, ROM, save or signing key included.\n').encode()
        final.writestr('NETWORK-TEST-BUILD.txt',note);inventory['NETWORK-TEST-BUILD.txt']=hashlib.sha256(note).hexdigest()
        final.writestr('SOURCE_SHA256.json',json.dumps(inventory,indent=2)+'\n')
    raw.unlink()
    with zipfile.ZipFile(target) as z:
        m.require(z.testzip() is None,'Source CRC failure')
        m.require(len(z.namelist())==len(set(z.namelist())),'Duplicate source entries')
        for name,digest in inventory.items():m.require(hashlib.sha256(z.read(name)).hexdigest()==digest,'Source identity differs: '+name)
    return inventory

def main():
    prior=PROJECT/'apk/1.0.2-test3';release=PROJECT/'apk'/VERSION
    m.require(not release.exists(),'Never overwrite an existing test artifact')
    protected={p.relative_to(prior).as_posix():m.sha(p) for p in prior.rglob('*') if p.is_file()}
    old_apk=prior/'Pocket2Droid-v1.0.2-test3-Custom-Resolution.apk';old_source=prior/'Pocket2Droid-v1.0.2-test3.Source.zip'
    m.require(m.sha(old_apk)=='d3b17771e8751f1df62f0c2baf1aa125d49855cf865a73403d55e88a7f37d801','Protected APK changed')
    m.require(m.sha(old_source)=='bdf86f3f027c3a1ac269a5d515a7b2f3a687db8f0e3043e483982754cd8b59fc','Protected source changed')
    proof=B/'networking';result=m.load(proof/'RESULT.json')
    m.require(result['status'].startswith('local integration complete'),'Feature acceptance incomplete')
    for name,digest in result['source_hashes'].items():
        if name.startswith(('android/src/','qemu/')):m.require(m.sha(HERE.parent/name)==digest,'Feature source changed: '+name)
    for name,marker in [('native-final.log','Ran 164 tests'),('network-ui-result.log','PASS 15 '),('restart-ui.log','PASS 22 '),('resolution-ui.log','PASS 60 '),('java-final.log','Network session: 13 checks passed')]:
        m.require(marker in (proof/name).read_text(),'Required evidence missing: '+name)
    m.require((proof/'native-final.log').read_text().rstrip().endswith('OK'),'Native suite did not pass')
    wm6=result['guests']['wm6-final-reopen']
    m.require(all(wm6[k] for k in ('dhcp_ack','positive_public_dns','public_http','local_http','rom_unchanged')) and wm6['exit_code']==0,'WM6 acceptance failed')
    app,native,runtime,storage=(m.load(B/n) for n in ('candidate-build.json','bionic-engine.json','runtime.json','storage-runtime.json'))
    m.require(native==result['bionic_engine'] and runtime==result['runtime'],'Native acceptance identity differs')
    m.require(storage==m.load(prior/'storage-runtime.json'),'Storage helper changed')
    for name,digest in native['source']['paths'].items():
        m.require(m.sha(HERE.parent/'qemu'/name)==digest,'Canonical native source differs')
        m.require(m.sha(m.NATIVE/name)==native['runtime_source_hashes'].get(name,digest),'Compiled native source differs')
    libraries={name:row['sha256'] for name,row in runtime['files'].items()};libraries['libp2dstorage.so']=storage['binary_sha256']
    for name,digest in libraries.items():
        path=B/('storage-runtime' if name=='libp2dstorage.so' else 'runtime')/name;m.require(m.sha(path)==digest,'Payload differs: '+name)
        loads=[s for s in subprocess.check_output(['readelf','-lW',str(path)],text=True).splitlines() if 'LOAD ' in s]
        m.require(loads and all(int(s.split()[-1],16)>=16384 for s in loads),'ELF alignment failed')
    m.require(set(runtime['files'])==set(m.load(prior/'runtime.json')['files']),'Unexpected dynamic dependency change')
    apk=Path(app['signed_apk']);m.require(app['version']==VERSION and app['package']=='com.samsixx.pocket2droid' and not app['test_only'] and m.sha(apk)==app['apk_sha256'],'Wrong candidate identity')
    signature=m.validate_apk(apk,'com.samsixx.pocket2droid',False,libraries,m.sha(B/'dex/classes.dex'))
    manifest=m.parse_manifest(apk);m.require(not manifest.get('instrumentation') and not manifest.get('provider'),'Test fixtures packaged')
    permissions={row['name'] for row in manifest['uses-permission']}
    m.require({'android.permission.INTERNET','android.permission.ACCESS_NETWORK_STATE'}<=permissions,'Network permissions missing')
    with zipfile.ZipFile(old_source) as old:
        before=old.read('android/AndroidManifest.xml').decode().replace('\r\n','\n').replace('android:versionCode="674"','android:versionCode="675"').replace('android:versionName="1.0.2-test3"','android:versionName="1.0.2-test4"')
        # Feature acceptance adds only the two normal network permissions.
        after=(HERE/'AndroidManifest.xml').read_text()
        expected=before.replace('    <uses-sdk android:minSdkVersion="24" android:targetSdkVersion="36" />','    <uses-sdk android:minSdkVersion="24" android:targetSdkVersion="36" />\n    <uses-permission android:name="android.permission.INTERNET" />\n    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />')
        m.require(after==expected,'Unexpected manifest scope')
    with zipfile.ZipFile(old_apk) as old,zipfile.ZipFile(apk) as z:
        art=lambda a:{n:hashlib.sha256(a.read(n)).hexdigest() for n in a.namelist() if n.startswith('res/') or n=='resources.arsc'}
        m.require(art(old)==art(z),'Artwork/resources changed')
        m.require({n for n in z.namelist() if n.startswith('assets/')}=={'assets/QEMU-COPYING.txt','assets/LIBSLIRP-COPYRIGHT.txt','assets/LIBSLIRP-NOTICE.txt'},'Unexpected assets')
        m.require(z.read('assets/LIBSLIRP-COPYRIGHT.txt')==(proof/'android/source/COPYRIGHT').read_bytes(),'Static library notices differ')
    stage=Path(tempfile.mkdtemp(prefix='.seal-network-',dir=release.parent))
    try:
        delivered=stage/('Pocket2Droid-v'+VERSION+'-Internet.apk');shutil.copy2(apk,delivered)
        print('Test APK signature, payload and16KiB alignment verified; sealing source.',flush=True)
        source=stage/('Pocket2Droid-v'+VERSION+'.Source.zip');inventory=snapshot(source,native,runtime,old_source)
        for name,digest in m.tested_source_hashes().items():m.require(inventory['android/'+name]==digest,'Frontend source archive mismatch')
        for name,digest in native['source']['paths'].items():m.require(inventory['qemu-canonical-changes/'+name]==digest,'Native source archive mismatch')
        for name in ('candidate-build.json','bionic-engine.json','runtime.json','bionic-tools.json','storage-runtime.json'):shutil.copy2(B/name,stage/name)
        shutil.copy2(Path(__file__),stage/'candidate-release-recipe.py');(stage/'candidate-signature.txt').write_text(signature)
        evidence=stage/'evidence';evidence.mkdir()
        for name in ('RESULT.json','progress.md','source-scope.diff','source-scope.json','native-final.log','java-final.log','network-ui-result.log','restart-ui.log','resolution-ui.log','guest-ram.log','runtime-final.log','review-clean-build-green.log','review-socket-reset-green.log'):shutil.copy2(proof/name,evidence/name)
        for name in ('google-result.png','local-result.png','public-result.png'):shutil.copy2(proof/'wm6-final-reopen'/name,evidence/name)
        shutil.copy2(B/'runtime/libp2dengine.so.unstripped',stage/'libp2dengine.so.unstripped')
        record=dict(version=VERSION,version_code=CODE,package=app['package'],private_test_candidate=True,apk_sha256=m.sha(delivered),source_archive_sha256=m.sha(source),source_snapshot_files=len(inventory),original_signer=m.SIGNER,signature_verified=True,apk_and_elf_alignment_16k=True,exact_dex_and_native_identity=True,native_tests=164,network_default='Off per ROM; next start',phone_validation_pending=True,phone_modified=False,baseline_preserved=True,wm5_public_http_incomplete=True,ipv6_only_dns_unsupported=True)
        (stage/'FINAL_VERIFICATION.json').write_text(json.dumps(record,indent=2)+'\n')
        (stage/'INSTALL.txt').write_text('Pocket2Droid1.0.2-test4/code675 Internet test;ARM64 Android7.0+.\n'
            'Exit the current ROM normally,then install this APK as an update. Keep app data.\n'
            'ROM settings > Internet access > On,then Start. It is Off by default.\n'
            'Inside Windows Mobile:Settings > Connections > Network Cards > The Internet.\n'
            'Try http://google.com/ or http://example.com/ in Internet Explorer.\n'
            'Success:page loads,then normal pause/Exit andRestart retain files. No modernHTTPS promise.\n'
            'Phone Wi-Fi/mobile/loss/recovery still needs testing. WM5 public HTTP incomplete in PC check.\n'
            'If networking prevents boot,Exit normally andturn Internet access Off;keep saves.\n'
            'Preserves WM5 retained RAM,Restart andcustom resolutions. No ROM/game/save included.\n')
        m.require(protected=={p.relative_to(prior).as_posix():m.sha(p) for p in prior.rglob('*') if p.is_file()},'Protected test3 modified')
        (stage/'SHA256SUMS.txt').write_text(''.join(m.sha(p)+'  '+p.relative_to(stage).as_posix()+'\n' for p in sorted(stage.rglob('*')) if p.is_file()))
        m.publish_release(stage,release);print(json.dumps(dict(apk=str(release/delivered.name),**record)),flush=True)
    finally:
        if stage.exists():
            m.require(stage.parent.resolve()==release.parent.resolve() and stage.name.startswith('.seal-network-'),'Unsafe stage cleanup');shutil.rmtree(stage)
if __name__=='__main__':main()
