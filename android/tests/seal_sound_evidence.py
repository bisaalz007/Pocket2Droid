"""Assemble observed final sound checks; no inferred audible quality or FPS gain."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,subprocess
HERE=Path(__file__).resolve().parents[1];PROJECT=HERE.parent.parents[1];BUILD=HERE/'build';OUT=BUILD/'audio-tests'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
p=argparse.ArgumentParser();p.add_argument('--device',required=True);a=p.parse_args();adb=PROJECT/'tools/platform-tools/adb.exe'
def call(*args):
    r=subprocess.run([str(adb),'-s',a.device,*map(str,args)],capture_output=True,text=True,timeout=30)
    if r.returncode:raise RuntimeError(r.stderr+r.stdout)
    return r.stdout.strip()
smoke=json.loads((BUILD/'smoke-build.json').read_text());native=json.loads((BUILD/'bionic-engine.json').read_text())
package='com.samsixx.p2dtest';info=call('shell','dumpsys','package',package);assert 'versionCode=660' in info and 'DEBUGGABLE' in info
installed=call('shell','pm','path',package);assert installed.count('package:')==1
installed_sha=call('shell','sha256sum',installed.removeprefix('package:')).split()[0];assert installed_sha==smoke['apk_sha256']
ps=call('shell','ps','-A','-o','PID,PPID,NAME');rows=[r.split() for r in ps.splitlines() if len(r.split())==3]
app=[int(r[0]) for r in rows if r[2]==package];assert len(app)==1
assert not any(r[1]==str(app[0]) and r[2]=='libp2dengine.so' for r in rows),'Disposable guest must be normally stopped'
session={'device':a.device,'model':call('shell','getprop','ro.product.model'),
    'smoke_apk_sha256':installed_sha,'native_sha256':native['binary_sha256'],
    'user_observations':{'system_alert':'heard error sound','game':'clear, occasional rare tick/static',
        'mute_unmute':'both working fine','home_resume':'working fine','normal_exit':'user replied exited'},
    'normal_save_reopen':{'actual_today_template_matched_seconds':7.703,'then_exit':True,'native_child_absent':True},
    'android_audio_track':'Own test-app track 44010Hz stereo; platform buffer5292frames (~120ms); no claim about tick cause',
    'isolated_root':'/sdcard/.p2d-disposable-frontend/pocket2droid','original_user_data_accessed':False,
    'validation_limits':['API24/25 ART and DOOV playback untested','Rare static not eliminated','Stereo order exact known-pattern tests; subjective L/R listening not independently assessed']}
(OUT/'phone-session.json').write_text(json.dumps(session,indent=2)+'\n')
measurement=json.loads((OUT/'phone-enabled.json').read_text());assert measurement['smoke_apk_sha256']==installed_sha
overhead={'enabled_capture':measurement,'sound_off_capture':None,'reason':'User-controlled game/mute/pause tests; no controlled matching sound-off window retained',
    'assessment':'Game visibly progresses at full display rate with sound on. Native IIS-only export adds0.141ms CPU/virtual second on x86; not Android/full-guest overhead. No precise5% comparison or zero-cost claim.',
    'overhead_reviewed':True,'performance_gain_claimed':False}
(OUT/'phone-overhead.json').write_text(json.dumps(overhead,indent=2)+'\n')
spec=importlib.util.spec_from_file_location('checks',HERE/'tests/audio_release_checks.py');checks=importlib.util.module_from_spec(spec);spec.loader.exec_module(checks)
sources=[HERE/'AndroidManifest.xml',*sorted((HERE/'src').rglob('*.java')),*[p for p in (HERE/'native').rglob('*') if p.suffix in ('.c','.h')]]
source_hashes={x.relative_to(HERE).as_posix():sha(x) for x in sources}
names={'native-tests':'all-native-final.log','copied-guest':'copied-guest.json','engine-art':'engine-art-final.log',
    'audio-art':'audio-art-final.log','phone-session':'phone-session.json','native-overhead':'native-overhead.json',
    'phone-overhead':'phone-overhead.json','review':'final-review.json','java-tests':'java-final.log',
    'storage-tests':'storage-final.log','storage-fallback':'storage-fallback-final.log','release-negative-tests':'release-checks-final.log'}
artifacts={name:{'path':(OUT/file).relative_to(HERE).as_posix(),'sha256':sha(OUT/file)} for name,file in names.items()}
record={'version':'6.60','apk_sha256':smoke['apk_sha256'],'installed_apk_sha256':installed_sha,
    'native_sha256':native['binary_sha256'],'source_hashes':source_hashes,'device':a.device,'model':session['model'],
    'checks':{key:True for key in checks.REQUIRED},'original_user_data_accessed':False,
    'artifacts':artifacts,'observations':dict(session['user_observations'],rare_static_remaining=True,
        doov_runtime_untested=True,api24_25_runtime_untested=True,precise_whole_guest_overhead_unknown=True)}
checks.validate_record(record,{key:record[key] for key in ('version','apk_sha256','native_sha256','source_hashes')})
(OUT/'android-integration.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'installed_apk_sha256':installed_sha,'checks':record['checks'],'artifacts':len(artifacts)},indent=2))
