"""Operate only this task's disposable package; never touch legacy app data."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
ADB = PROJECT / 'tools/platform-tools/adb.exe'
SERIAL = 'R5CY52NFFNN'
PACKAGE = 'com.samsixx.p2dtest'
OUT = HERE / 'build/phone-smoke'
OWNER = OUT / 'owned-install.json'

def adb(*args, check=True, **kwargs):
    p = subprocess.run([str(ADB),'-s',SERIAL,*args],capture_output=True,timeout=40,**kwargs)
    if check and p.returncode: raise RuntimeError(p.stderr.decode(errors='replace')+p.stdout.decode(errors='replace'))
    return p

def owned():
    data = json.loads(OWNER.read_text())
    assert data['serial'] == SERIAL and data['package'] == PACKAGE and data['initially_absent']
    info = adb('shell','dumpsys','package',PACKAGE).stdout.decode(errors='replace')
    assert 'versionCode='+str(data.get('version_code',653)) in info
    return data

def focused():
    lines=adb('shell','dumpsys','activity','activities').stdout.decode(errors='replace').splitlines()
    assert any(PACKAGE in line for line in lines if 'ResumedActivity:' in line or 'topResumedActivity=' in line), 'Disposable app is not foreground'

def capture(label):
    owned(); focused()
    adb('shell','uiautomator','dump','/data/local/tmp/p2d-frontend-smoke.xml')
    raw = adb('exec-out','cat','/data/local/tmp/p2d-frontend-smoke.xml').stdout
    (OUT/(label+'.xml')).write_bytes(raw)
    (OUT/(label+'.png')).write_bytes(adb('exec-out','screencap','-p').stdout)
    for node in ET.fromstring(raw).iter('node'):
        text=node.get('text','')
        if text: print(text,node.get('bounds'))
    adb('shell','rm','/data/local/tmp/p2d-frontend-smoke.xml')

def tap(text):
    owned();focused()
    adb('shell','uiautomator','dump','/data/local/tmp/p2d-frontend-smoke.xml')
    raw=adb('exec-out','cat','/data/local/tmp/p2d-frontend-smoke.xml').stdout
    nodes=[n for n in ET.fromstring(raw).iter('node') if n.get('text')==text]
    assert len(nodes)==1,(text,len(nodes))
    x,y,xx,yy=map(int,re.findall(r'\d+',nodes[0].get('bounds')))
    adb('shell','input','tap',str((x+xx)//2),str((y+yy)//2))
    adb('shell','rm','/data/local/tmp/p2d-frontend-smoke.xml')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',choices=['prepare','launch','capture','tap','log','remove'])
    ap.add_argument('value',nargs='?',default='screen')
    args=ap.parse_args();OUT.mkdir(exist_ok=True)
    if args.action=='prepare':
        assert not adb('shell','pidof','com.samsixx.wm6android',check=False).stdout.strip(), 'Original app still active'
        assert not adb('shell','pidof','com.samthedev.pocket2droid',check=False).stdout.strip(), 'New app still active'
        present = bool(adb('shell','pm','path',PACKAGE,check=False).stdout.strip())
        if present: owned()
        apk=HERE/'build/Pocket2Droid-V6.53-TCG-SMOKE-SIGNED.apk'
        record=json.loads((HERE/'build/smoke-build.json').read_text())
        assert record['test_only'] and record['package']==PACKAGE and hashlib.sha256(apk.read_bytes()).hexdigest()==record['apk_sha256']
        if present:
            assert owned()['installed_apk_sha256'] == record['apk_sha256'], 'Owned test package differs; explicit update needed'
        else:
            print(adb('install',str(apk)).stdout.decode().strip())
            OWNER.write_text(json.dumps({'serial':SERIAL,'package':PACKAGE,'initially_absent':True,'installed_apk_sha256':record['apk_sha256']},indent=2))
        adb('shell','run-as',PACKAGE,'mkdir','-p','files/tcg-v1')
        inputs=[('ROM',PROJECT/'PC windows mobile 6 Files/Roms and files/pocket pc/Deviceemulation/0409/PPC_USA.BIN','PPC_USA.BIN',
                 'b6ca519070e84da0bf6886fb3bde606ce098a0cfaffff436b8faf46a9a580bf7'),
                ('CAB',PROJECT/'DOCUMENTATION/PHONE_EVIDENCE/v644/game-files/rt_filao_efigs_retail_ppc.cab','RagingThunder.cab',
                 '2061b29422de832c65306f6c789ed4eca861f3a28056a3cf98374d98adeafd00')]
        for kind,source,target,digest in inputs:
            assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
            staging='/data/local/tmp/p2d-frontend-input-'+uuid.uuid4().hex[:12]
            adb('shell','mkdir',staging)
            try:
                adb('shell','chmod','755',staging)
                adb('push',str(source),staging+'/input')
                adb('shell','chmod','644',staging+'/input')
                adb('shell','run-as',PACKAGE,'cp',staging+'/input','files/tcg-v1/'+target)
            finally:
                adb('shell','rm','-f',staging+'/input')
                adb('shell','rmdir',staging)
            actual=adb('shell','run-as',PACKAGE,'sha256sum','files/tcg-v1/'+target).stdout.decode().split()[0]
            assert actual==digest,actual
            print(kind,'copied and verified')
    elif args.action=='launch':
        owned();print(adb('shell','am','start','-n',PACKAGE+'/com.samthedev.pocket2droid.MainActivity').stdout.decode())
    elif args.action=='capture': capture(args.value)
    elif args.action=='tap': tap(args.value)
    elif args.action=='log':
        owned();r=adb('exec-out','run-as',PACKAGE,'cat','files/tcg-v1/engine.log',check=False)
        (OUT/'engine.log').write_bytes(r.stdout);print(r.stdout.decode(errors='replace')[-6000:])
    else:
        owned()
        print(adb('uninstall',PACKAGE).stdout.decode().strip())
        assert not adb('shell','pm','path',PACKAGE,check=False).stdout.strip()
        OWNER.rename(OUT/'removed-install.json')

if __name__=='__main__':main()
