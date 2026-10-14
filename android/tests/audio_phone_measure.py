"""Short read-only own-process CPU/display observation in disposable app."""
from pathlib import Path
import argparse,hashlib,json,struct,subprocess,time
HERE=Path(__file__).resolve().parents[1];PROJECT=HERE.parent.parents[1]
p=argparse.ArgumentParser();p.add_argument('--device',required=True);p.add_argument('--label',required=True);p.add_argument('--seconds',type=int,default=12);a=p.parse_args()
assert 1<=a.seconds<=30 and a.label in ('enabled','muted')
adb=PROJECT/'tools/platform-tools/adb.exe';package='com.samsixx.p2dtest'
def call(*args,binary=False):
    r=subprocess.run([str(adb),'-s',a.device,*map(str,args)],capture_output=True,timeout=15)
    if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace'))
    return r.stdout if binary else r.stdout.decode(errors='replace')
pid=int(call('shell','pidof',package).strip());rows=call('shell','ps','-A','-o','PID,PPID,NAME').splitlines()
children=[int(row.split()[0]) for row in rows if len(row.split())==3 and row.split()[1]==str(pid) and row.split()[2]=='libp2dengine.so'];assert len(children)==1
hz=int(call('shell','getconf','CLK_TCK').strip());native=children[0]
def snapshot():
    wall=time.monotonic();cpu={}
    for name,number in [('frontend',pid),('native',native)]:
        fields=call('exec-out','run-as',package,'cat','/proc/'+str(number)+'/stat').rsplit(')',1)[1].split();cpu[name]=int(fields[11])+int(fields[12])
    f=call('exec-out','run-as',package,'head','-c','64','files/tcg-v1/frames.bin',binary=True)
    audio=call('exec-out','run-as',package,'head','-c','64','files/tcg-v1/audio.bin',binary=True)
    assert f[:4]==b'P2DF' and audio[:4]==b'P2DA'
    return {'wall':wall,'cpu_ticks':cpu,'frame_sequence':struct.unpack_from('<Q',f,24)[0],
        'packet_write':struct.unpack_from('<I',audio,20)[0],'epoch':struct.unpack_from('<I',audio,36)[0],'status':struct.unpack_from('<I',audio,44)[0]}
before=snapshot();time.sleep(a.seconds);after=snapshot();elapsed=after['wall']-before['wall']
report={'label':a.label,'device':a.device,'pids':{'frontend':pid,'native':native},'elapsed_s':elapsed,
    'before':before,'after':after,'cpu_seconds':{k:(after['cpu_ticks'][k]-before['cpu_ticks'][k])/hz for k in before['cpu_ticks']},
    'display_presentations_per_second':(after['frame_sequence']-before['frame_sequence'])/elapsed,
    'same_output_epoch':before['epoch']==after['epoch'],
    'scope':'Short unmatched read-only app window; display presentations are not measured guest game FPS; not a precise overhead percentage',
    'smoke_apk_sha256':json.loads((HERE/'build/smoke-build.json').read_text())['apk_sha256']}
out=HERE/'build/audio-tests';(out/('phone-'+a.label+'.json')).write_text(json.dumps(report,indent=2)+'\n')
(out/('flinger-'+a.label+'.txt')).write_text(call('shell','dumpsys','media.audio_flinger'))
print(json.dumps(report,indent=2))
