"""Isolated PC Android UI/ART checks. Never targets a physical phone."""
from pathlib import Path
import json,subprocess,time,uuid,xml.etree.ElementTree as ET,shlex,re
HERE=Path(__file__).resolve().parents[1];PROJECT=HERE.parents[2];B=HERE/'build/library-tests'
ADB=PROJECT/'tools/android-local/sdk/platform-tools/adb'
PKG='com.samsixx.p2dtest';SERIAL='emulator-5580'
def adb(*args,**kw):return subprocess.check_output([str(ADB),'-P','5041','-s',SERIAL,*args],**kw)
def shell(command):return adb('shell',command,text=True)
def capture(label):
    for _ in range(3):
        shell('rm -f /sdcard/p2d-library-ui.xml');shell('uiautomator dump /sdcard/p2d-library-ui.xml')
        try:tree=ET.fromstring(adb('exec-out','cat','/sdcard/p2d-library-ui.xml'));break
        except (ET.ParseError,subprocess.CalledProcessError):time.sleep(.3)
    else:raise AssertionError('UI hierarchy unavailable')
    (B/(label+'.xml')).write_bytes(ET.tostring(tree));(B/(label+'.png')).write_bytes(adb('exec-out','screencap','-p'))
    return tree
def node(tree,text):
    matches=[n for n in tree.iter('node') if n.get('text','').casefold()==text.casefold() or n.get('content-desc','').casefold()==text.casefold()]
    assert matches,'UI item missing: '+text
    return matches[0]
def tap(tree,text,hold=False):
    n=node(tree,text);parts=n.get('bounds').replace('][',',').strip('[]').split(',');a,b,c,d=map(int,parts);x=(a+c)//2;y=(b+d)//2
    shell(f'input swipe {x} {y} {x} {y} 750' if hold else f'input tap {x} {y}');time.sleep(.4)
def bounds(n):return tuple(map(int,re.findall(r'\d+',n.get('bounds'))))
def snapshot():
    shell('rm -f /sdcard/p2d-library-ui.xml');shell('uiautomator dump /sdcard/p2d-library-ui.xml');return ET.fromstring(adb('exec-out','cat','/sdcard/p2d-library-ui.xml'))
def scroll_to(text):
    for _ in range(5):
        tree=snapshot()
        if any(n.get('text')==text for n in tree.iter('node')):return tree
        shell('input swipe 240 650 240 200 350');time.sleep(.2)
    raise AssertionError('Missing scroll item: '+text)
def main():
    assert shell('getprop ro.kernel.qemu').strip()=='1','Only the owned PC emulator is allowed'
    smoke=json.loads((HERE/'build/smoke-build.json').read_text());assert smoke['test_only'] and smoke['version']=='6.62'
    adb('install','-r',smoke['signed_apk']);shell(f'appops set {PKG} MANAGE_EXTERNAL_STORAGE allow')
    native=Path('/opt/pocket2droid-android-tools/bionic/android-ndk-r30/toolchains/llvm/prebuilt/linux-x86_64/bin/x86_64-linux-android24-clang')
    helper=B/'libp2dstorage-x86_64.so'
    subprocess.run([str(native),'-std=c11','-O2','-shared','-fPIC','-Wall','-Wextra','-Werror',str(HERE/'native/storage_publish.c'),'-o',str(helper)],check=True)
    owned='/data/local/tmp/p2d-ui-'+uuid.uuid4().hex;shell('mkdir '+owned)
    adb('push',str(HERE/'build/audio-tests/audio-art.jar'),owned+'/tests.jar');adb('push',str(helper),owned+'/libp2dstorage.so')
    for test in ('EngineKeyTest','AudioPlayerArtTest','InsetBackdropArtTest'):
        dest=owned+'/'+test;shell('mkdir '+dest)
        out=shell('CLASSPATH='+owned+'/tests.jar app_process -Djava.library.path='+owned+' /system/bin com.samsixx.pocket2droid.'+test+' '+dest)
        (B/(test+'-art.log')).write_text(out);assert 'PASS' in out,out
    shell(f'am start -W -n {PKG}/com.samsixx.pocket2droid.MainActivity');time.sleep(1)
    initial=capture('pc-library');node(initial,'Add ROM');node(initial,'App settings')
    tap(initial,'App settings');settings=capture('pc-app-settings');node(settings,'Sound');node(settings,'Enable fullscreen');node(settings,'Enable on-screen keys')
    for title,value in [('Display FPS counter',True),('Enable fullscreen',False),('Enable on-screen keys',True)]:
        current=snapshot();toggle=next(n for n in current.iter('node') if n.get('content-desc')==title and n.get('checkable')=='true')
        if (toggle.get('checked')=='true')!=value:
            x0,y0,x1,y1=bounds(toggle);shell(f'input tap {(x0+x1)//2} {(y0+y1)//2}');time.sleep(.2)
    shell('input keyevent 4');time.sleep(.4);library=capture('pc-library-return')
    tap(library,'Add ROM');picker=capture('pc-import-picker');shell('input keyevent 4');time.sleep(.5);cancel=capture('pc-import-cancel');node(cancel,'Add ROM')
    name='UI_TEST_'+uuid.uuid4().hex[:6]+'.BIN';label=name[:-4];root='/sdcard/.p2d-disposable-frontend/pocket2droid'
    shell('mkdir -p '+root+'/Roms '+root+'/data/'+name);local=B/'idle-ui.bin';local.write_bytes(bytes.fromhex('feffffea'));adb('push',str(local),root+'/Roms/'+name)
    shell('truncate -s 33554432 '+root+'/data/'+name+'/ram-fmd.bin')
    shell(f'am force-stop {PKG}');shell(f'am start -W -n {PKG}/com.samsixx.pocket2droid.MainActivity');time.sleep(.5)
    listing=capture('pc-library-with-rom');node(listing,label);tap(listing,label,True);options=capture('pc-rom-popup');node(options,'Settings');tap(options,'Settings');rom_settings=capture('pc-rom-settings');node(rom_settings,'Start');node(rom_settings,'Display name')
    tap(rom_settings,'Guest resolution');resolutions=capture('pc-resolution-options');assert not any(n.get('text')=='ROM default' for n in resolutions.iter('node'));node(resolutions,'QVGA (240×320)');tap(resolutions,'Square VGA (480×480)');time.sleep(.3)
    selected=snapshot();assert any(n.get('text','').startswith('Square VGA (480×480)') for n in selected.iter('node'))
    rom_settings=capture('pc-rom-settings-return');tap(rom_settings,'Start');time.sleep(1);session=capture('pc-session')
    node(session,'TAB');surface=node(session,'Emulated display')
    assert bounds(surface)[3]<=bounds(node(session,'TAB'))[1],'Normal keys cover guest viewport'
    shell('input keyevent 4');menu=capture('pc-session-menu');node(menu,'Exit');assert not any('CAB' in n.get('text','') for n in menu.iter('node'))
    tap(menu,'Fullscreen');full=capture('pc-fullscreen');node(full,'TAB');assert any(n.get('text','').startswith('Display FPS') for n in full.iter('node'))
    width,height=map(int,re.findall(r'(?:Override|Physical) size: (\d+)x(\d+)',shell('wm size'))[-1])
    # UIAutomator clips accessibility bounds to API30's stale appBounds after
    # immersive navigation hides. Use the Activity's actual layout hierarchy.
    layout=shell('dumpsys activity top');(B/'fullscreen-activity.txt').write_text(layout)
    actual=re.findall(r'com\.samsixx\.wm6android\.GuestSurface\{[^\n]* (\d+),(\d+)-(\d+),(\d+)\}',layout)
    assert actual and tuple(map(int,actual[-1]))==(0,0,width,height),'Hidden system bars still reserve fullscreen space'
    shell('input keyevent 4');menu=snapshot();tap(menu,'On-screen keys');no_keys=capture('pc-fullscreen-no-keys');assert not any(n.get('text')=='TAB' for n in no_keys.iter('node'))
    shell('input keyevent 4');menu=snapshot();tap(menu,'Display FPS counter');no_overlays=capture('pc-fullscreen-no-overlays');assert not any('Display FPS' in n.get('text','') for n in no_overlays.iter('node'))
    shell('input keyevent 4');menu=snapshot();tap(menu,'On-screen keys');keys_only=capture('pc-fullscreen-keys-only');node(keys_only,'TAB')
    shell('input keyevent 3');time.sleep(.2);shell(f'am start -W -n {PKG}/com.samsixx.pocket2droid.MainActivity');time.sleep(.3);active=capture('pc-paused-library');resume=next((n for n in active.iter('node') if n.get('text')=='Resume active ROM'),None)
    if resume:tap(active,'Resume active ROM')
    elif not any(n.get('content-desc')=='Emulated display' for n in active.iter('node')):tap(active,label)
    time.sleep(.4);shell('input keyevent 4');menu=snapshot();tap(menu,'Exit');time.sleep(.5);after=capture('pc-after-exit');node(after,'Add ROM')
    tap(after,label,True);tap(snapshot(),'Settings');settings=scroll_to('Delete ROM');tap(settings,'Delete ROM');confirm=capture('pc-delete-confirmation');node(confirm,'Delete ROM?');tap(confirm,'Cancel');time.sleep(.2)
    settings=scroll_to('Delete ROM');tap(settings,'Delete ROM');tap(snapshot(),'Delete');time.sleep(.5);deleted=capture('pc-deleted-library');assert not any(n.get('text')==label for n in deleted.iter('node'))
    report={'pc_emulator':SERIAL,'phone_modified':False,'art_tests':True,'library_settings_import_cancel':True,'rom_settings_fullscreen_exit_delete':True,'native_execution_on_pc_android_claimed':False,'owned_art_root':owned}
    (B/'pc-ui-result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
if __name__=='__main__':main()
