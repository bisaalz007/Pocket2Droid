"""Inspect/reproduce only the owned frozen V6.53 disposable Android guest."""
from pathlib import Path
import argparse, importlib.util, json, re, struct, time, xml.etree.ElementTree as ET
from PIL import Image
HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('smoke',HERE/'phone_smoke.py')
sm=importlib.util.module_from_spec(spec);spec.loader.exec_module(sm)

def frame():
    raw=sm.adb('exec-out','run-as',sm.PACKAGE,'head','-c','64','files/tcg-v1/frames.bin',check=False).stdout
    if len(raw)!=64 or raw[:4]!=b'P2DF': return {'frame_header':raw.hex()}
    return {'width':struct.unpack_from('<I',raw,8)[0], 'height':struct.unpack_from('<I',raw,12)[0], 'sequence':struct.unpack_from('<Q',raw,24)[0]}

def liveness():
    report={'frame':frame()}
    pid=sm.adb('shell','pidof',sm.PACKAGE,check=False).stdout.decode().strip()
    lines=sm.adb('shell','ps','-A','-o','PID,PPID,ARGS').stdout.decode().splitlines()
    children=[line.split(None,2) for line in lines if len(line.split(None,2))==3 and line.split(None,2)[1]==pid and 'libp2dengine.so' in line]
    report['native_children']=[x[0] for x in children]
    for child,_,_ in children:
        raw=sm.adb('exec-out','run-as',sm.PACKAGE,'cat','/proc/'+child+'/stat',check=False).stdout.decode().strip()
        report['native_stat_'+child]=raw
    return report

def capture_guest(label):
    sm.owned(); sm.focused()
    assert re.fullmatch(r'[a-zA-Z0-9_-]+', label)
    f = frame(); size = 64 + f['width'] * f['height'] * 4
    raw = sm.adb('exec-out','run-as',sm.PACKAGE,'head','-c',str(size),'files/tcg-v1/frames.bin').stdout
    assert len(raw) == size
    Image.frombytes('RGBA',(f['width'],f['height']),raw[64:],'raw','BGRA').convert('RGB').save(sm.OUT/(label+'.png'))

def guest_tap(x,y,hold):
    sm.owned();sm.focused()
    sm.adb('shell','uiautomator','dump','/data/local/tmp/p2d-fs-layout.xml')
    try: raw=sm.adb('exec-out','cat','/data/local/tmp/p2d-fs-layout.xml').stdout
    finally: sm.adb('shell','rm','/data/local/tmp/p2d-fs-layout.xml')
    node=[n for n in ET.fromstring(raw).iter('node') if n.get('class')=='android.view.SurfaceView']
    assert len(node)==1,'Guest surface is not visible'
    l,t,r,b=map(int,re.findall(r'\d+',node[0].get('bounds')))
    f=frame();w,h=f['width'],f['height'];assert 0<=x<w and 0<=y<h
    scale=min((r-l)/w,(b-t)/h)
    px=round(l+((r-l)-w*scale)/2+x*scale);py=round(t+((b-t)-h*scale)/2+y*scale)
    if hold: sm.adb('shell','input','swipe',str(px),str(py),str(px),str(py),str(hold))
    else: sm.adb('shell','input','tap',str(px),str(py))
    return {'x':x,'y':y,'hold_ms':hold,'mapped':[px,py]}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['tap','capture','status']);p.add_argument('--x',type=int);p.add_argument('--y',type=int);p.add_argument('--hold',type=int,default=0);p.add_argument('--label',default='filesystem-check')
    a=p.parse_args();report={}
    if a.action=='tap': report.update(guest_tap(a.x,a.y,a.hold));time.sleep(.3)
    report.update(liveness())
    if a.action!='status':capture_guest(a.label)
    (sm.OUT/(a.label+'-liveness.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
