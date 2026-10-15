"""Bounded UI actions exclusively in the disposable V6.60 package."""
from pathlib import Path
import argparse,json,re,subprocess,sys,time,uuid,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parent;PROJECT=ROOT.parents[1]
sys.path.insert(0,str(ROOT/'prototypes/tcg-transition'));from guest import template
p=argparse.ArgumentParser();p.add_argument('--device',required=True);p.add_argument('action',choices=['inspect','start','navigate','sound','home','resume','exit']);a=p.parse_args()
package='com.samsixx.p2dtest';out=HERE/'build/audio-tests';adb=PROJECT/'tools/platform-tools/adb.exe'
def call(*args,binary=False):
    r=subprocess.run([str(adb),'-s',a.device,*map(str,args)],capture_output=True,timeout=20)
    if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace')+r.stdout.decode(errors='replace'))
    return r.stdout if binary else r.stdout.decode(errors='replace')
info=call('shell','dumpsys','package',package);assert 'versionCode=660' in info and 'DEBUGGABLE' in info
def foreground():
    text=call('shell','dumpsys','activity','activities');assert any(package in line for line in text.splitlines() if 'ResumedActivity' in line or 'topResumedActivity=' in line)
def nodes():
    foreground();remote='/data/local/tmp/p2d-sound-ui-'+uuid.uuid4().hex+'.xml'
    call('shell','uiautomator','dump',remote)
    try:return list(ET.fromstring(call('exec-out','cat',remote,binary=True)).iter('node'))
    finally:call('shell','rm',remote)
def click(text):
    ns=[n for n in nodes() if n.get('text','').lower()==text.lower()];assert len(ns)==1,[n.get('text') for n in nodes()]
    l,t,r,b=map(int,re.findall(r'\d+',ns[0].get('bounds')));call('shell','input','tap',(l+r)//2,(t+b)//2)
def tap(x,y):
    ns=[n for n in nodes() if 'SurfaceView' in n.get('class','')];assert len(ns)==1
    l,t,r,b=map(int,re.findall(r'\d+',ns[0].get('bounds')));s=min((r-l)/240,(b-t)/320)
    call('shell','input','tap',round(l+((r-l)-240*s)/2+x*s),round(t+((b-t)-320*s)/2+y*s))
def key(name):
    foreground();call('shell','input','keyevent',{'ret':66,'down':20,'tab':61}[name]);time.sleep(.15)
def wait(name,box,timeout=35,fg=False):
    indices,expected=template(name,box,fg);begin=time.monotonic()
    while time.monotonic()-begin<timeout:
        data=call('exec-out','run-as',package,'head','-c',307264,'files/tcg-v1/frames.bin',binary=True)
        if data[:4]==b'P2DF' and len(data)>=307264:
            different=sum(data[64+i*4:67+i*4]!=v for i,v in zip(indices,expected))
            if different<=len(indices)*.01:print(name,round(time.monotonic()-begin,3),flush=True);return
        time.sleep(.25)
    raise RuntimeError('Disposable guest did not reach '+name)
if a.action=='start':click('start')
elif a.action=='navigate':
    wait('today',(5,64,210,142));tap(35,12);wait('start',(3,30,135,166));tap(55,149);wait('programs',(5,31,200,70))
    key('ret');wait('program_files',(5,31,200,72));key('ret');wait('game_files',(5,31,100,96))
    key('down');key('ret');wait('language_english',(40,108,200,119));key('down');wait('language_english',(30,135,180,150))
    key('tab');wait('english_confirm',(25,136,210,185));time.sleep(.7);key('tab');wait('sound_on',(10,194,225,241))
    time.sleep(.7);key('tab');wait('game_mode',(10,111,225,178));time.sleep(.7);key('tab');wait('quick_race',(208,294,238,318),fg=True)
elif a.action=='sound':click('Sound')
elif a.action=='home':foreground();call('shell','input','keyevent',3)
elif a.action=='resume':call('shell','am','start','-n',package+'/com.samsixx.pocket2droid.MainActivity')
elif a.action=='exit':click('exit')
if a.action in ('inspect','start','navigate','sound','resume','exit'):
    ns=nodes();texts=[n.get('text') for n in ns if n.get('text')];print(json.dumps(texts))
    (out/(a.action+'-screen.png')).write_bytes(call('exec-out','screencap','-p',binary=True))
