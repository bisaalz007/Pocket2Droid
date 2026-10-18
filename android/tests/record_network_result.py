"""Collect reproducible scope, preservation and validation evidence; no release."""
from pathlib import Path
import argparse, difflib, hashlib, importlib.util, json, subprocess, zipfile
EXP=Path(__file__).resolve().parents[2];OUT=EXP/'android/build/networking'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--final',action='store_true');args=parser.parse_args()
    baseline=json.loads((OUT/'baseline.json').read_text());preservation={name:sha(EXP.parents[1]/name)==digest for name,digest in baseline['artifacts'].items()};assert all(preservation.values())
    files=[p for p in (EXP/'android/src').rglob('*.java')]+[EXP/'android/AndroidManifest.xml']
    files+=list((EXP/'android').glob('*.py'))+list((EXP/'android/patches').glob('*'))
    spec=importlib.util.spec_from_file_location('scope_sync',EXP/'sync_source.py');sync=importlib.util.module_from_spec(spec);spec.loader.exec_module(sync)
    names=set(sync.git_names('diff','--name-only','-z',sync.BASE));names.update(sync.git_names('ls-files','--others','--exclude-standard','-z'))
    files += [EXP/'qemu'/n for n in names]
    files += [p for p in (EXP/'tests').glob('*') if p.suffix in ('.py','.c')]
    files += [p for p in (EXP/'android/tests').glob('*') if p.suffix in ('.py','.java')]
    inventory={str(p.relative_to(EXP)):sha(p) for p in files if p.is_file()}
    source_zip=EXP.parents[1]/'apk/1.0.2-test3/Pocket2Droid-v1.0.2-test3.Source.zip';scope=[];diff=''
    with zipfile.ZipFile(source_zip) as archive:
        entries=set(archive.namelist())
        for name,digest in sorted(inventory.items()):
            old=None;copy=OUT/'baseline'/name
            if copy.exists():old=copy.read_bytes()
            else:
                paths=[name] if not name.startswith('qemu/') else ['qemu-canonical-changes/'+name[5:],'qemu-android-exact/'+name[5:]]
                for path in paths:
                    if path in entries:old=archive.read(path);break
            oldhash=hashlib.sha256(old).hexdigest() if old is not None else None
            if oldhash==digest:continue
            scope.append({'path':name,'baseline_sha256':oldhash,'sha256':digest})
            if name.endswith(('.c','.h','.py','.java','.xml','.patch','.txt','Kconfig','.build','.mak')):
                diff+=''.join(difflib.unified_diff((old or b'').decode('utf8').splitlines(True),(EXP/name).read_text().splitlines(True),fromfile='test3/'+name,tofile='network/'+name))
    (OUT/'source-scope.diff').write_text(diff);(OUT/'source-scope.json').write_text(json.dumps(scope,indent=2)+'\n')
    guests={}
    for p in OUT.glob('wm*/result.json'):
        result=json.loads(p.read_text())
        from network_guest_probe import packets
        events=packets(p.parent/'packets.pcap') if (p.parent/'packets.pcap').exists() else []
        result['public_http']=any(e['kind']=='http' and e['ports'][0]==80 and e['text'].startswith('HTTP/') and ' 200 ' in e['text'].split('\r\n')[0] for e in events)
        p.write_text(json.dumps(result,indent=2)+'\n');guests[p.parent.name]=result
    logs={p.name:sha(p) for p in OUT.glob('*.log')}
    result={'feature':'optional Windows Mobile Internet access','release_apk_created':False,'phone_modified':False,'signed_test3_preserved':preservation,'source_hashes':inventory,'changed_sources':scope,'logs_sha256':logs,'guests':guests,'host_slirp':json.loads((OUT/'host/provenance.json').read_text()),'android_slirp':json.loads((OUT/'android/provenance.json').read_text()),'bionic_engine':json.loads((EXP/'android/build/bionic-engine.json').read_text()),'runtime':json.loads((EXP/'android/build/runtime.json').read_text()),'limitations':['ARM64 Android guest networking not yet tested on a phone','IPv4 guest DNS cannot use an IPv6-only upstream in this implementation','Private DNS/VPN/mobile-data compatibility unverified','Old guest browsers do not gain modern TLS support','WM5 test ROM gets DHCP/DNS/local HTTP but public HTTP did not complete within20seconds'],'review':'pending'}
    if args.final:
        wm6=guests['wm6-final-reopen'];wm5=guests['wm5-internet-final']
        for key in ['dhcp_ack','positive_public_dns','public_http','local_http','rom_unchanged','marker_unchanged']:assert wm6[key],key
        for key in ['dhcp_ack','positive_public_dns','local_http','rom_unchanged','marker_unchanged']:assert wm5[key],key
        assert wm6['exit_code']==wm5['exit_code']==0
        assert sha(Path(wm6['binary']))==wm6['binary_sha256']==wm5['binary_sha256']
        assert not guests['wm6-offline']['network_info'] and not guests['wm6-offline-baseline']['network_info']
        assert guests['wm6-offline']['exit_code']==guests['wm5-offline']['exit_code']==0
        native=result['bionic_engine'];assert sha(EXP/'android/build/libp2dengine-bionic.so')==native['binary_sha256']
        for name,digest in native['source']['paths'].items():assert sha(EXP/'qemu'/name)==digest,name
        for name,digest in native['runtime_source_hashes'].items():assert sha(Path(native['runtime_source_directory'])/name)==digest,name
        for platform in ['host','android']:
            pin=result[platform+'_slirp'];assert sha(OUT/platform/'lib/libslirp.a')==pin['library_sha256']
            assert sha(EXP/'android/build_slirp.py')==pin['builder_sha256']
        for name,entry in result['runtime']['files'].items():
            elf=EXP/'android/build/runtime'/name;assert sha(elf)==entry['sha256']
            for line in subprocess.check_output(['readelf','-lW',str(elf)],text=True).splitlines():
                if 'LOAD ' in line:assert int(line.split()[-1],16)>=16384
        tested=json.loads((OUT/'android-ui/granted-sources.json').read_text())
        for name,digest in tested.items():assert sha(EXP/'android'/name)==digest,'Android evidence stale: '+name
        assert 'Ran 164 tests' in (OUT/'native-final.log').read_text() and (OUT/'native-final.log').read_text().rstrip().endswith('OK')
        assert 'PASS 15 ' in (OUT/'network-ui-result.log').read_text()
        assert 'PASS 22 ' in (OUT/'restart-ui.log').read_text()
        assert 'PASS 60 ' in (OUT/'resolution-ui.log').read_text()
        result.update(status='local integration complete with documented limitations; no phone release',review='one fresh review; two Important findings reproduced RED then fixed GREEN; final164test native suite passed; no deferred minors',google_render='wm6-final-reopen/google-result.png',acceptance={'wm6':'DHCP,positive DNS,local/public HTTP and Google render,exit/reopen','wm5':'retained-set reopen,DHCP,positive DNS,local HTTP; public HTTP incomplete','offline':'WM6 baseline/candidate and WM5 boot; explicit no NIC/backend','android':'15actual UI/observer/app-UID socket checks and Engine ART ownership;125config+13simulated-source session checks','regressions':'129repository,98settings/geometry,120controls in both storage modes;29GuestRam;22Restart/lifecycle;60custom-resolution;18mapping ART','native':'164tests;9card,3resolver,clean host+Android build'} )
    (OUT/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
    (OUT/'review-package.md').write_text('# Networking whole-change review\n\nApproved spec: docs/superpowers/specs/2026-10-17-android-networking-design.md\nPlan: docs/superpowers/plans/2026-10-17-android-networking.md\nLedger: android/build/networking/progress.md (paths relative to EXPERIMENTS/qemu-devemu)\n\nRoot is not Git. source-scope.diff compares against preserved test3 files/source ZIP; source-scope.json binds hashes. This scope includes tests/build inputs. Existing unrelated QEMU modifications were preserved.\n\nSee RESULT.json and named log/guest directories for evidence. No release APK, phone writes or commits. PC Android tests use a separate test package. Guest acceptance was on disposable WM6/WM5 profiles. The initial reviewed-source-scope files are retained separately from the final corrected scope.\n')
    print('Scope:',len(scope),'changed files; signed rollback:',all(preservation.values()),'; guests:',list(guests))
if __name__=='__main__':main()
