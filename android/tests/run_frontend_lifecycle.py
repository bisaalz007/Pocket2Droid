"""Frontend-only APK/Instrumentation on the isolated PC emulator, never a phone."""
from pathlib import Path
import subprocess,sys,zipfile,json,hashlib

HERE=Path(__file__).resolve().parents[1]
PROJECT=HERE.parents[2]
API=Path('/opt/pocket2droid-android-tools/android-36/android.jar')
SDK=API.parent.parent/'android-16'
ADB=PROJECT/'tools/android-local/sdk/platform-tools/adb'
RESOLUTION='--resolution' in sys.argv
NETWORK='--network' in sys.argv
CARD='--storage-card' in sys.argv
TEST='StorageCardUiTest' if CARD else 'NetworkUiTest' if NETWORK else 'CustomResolutionUiTest' if RESOLUTION else 'FrontendLifecycleTest'
PACKAGE='com.samsixx.p2dcard' if CARD else 'com.samsixx.p2dnetwork' if NETWORK else 'com.samsixx.p2dresolution' if RESOLUTION else 'com.samsixx.p2dlifecycle'
if '--package' in sys.argv:
    PACKAGE=sys.argv[sys.argv.index('--package')+1]
    assert PACKAGE.startswith('com.samsixx.p2d') and PACKAGE!='com.samsixx.pocket2droid','Only disposable test packages are allowed'
OUT=HERE/'build'/('storage-card-ui' if CARD else 'networking/android-ui' if NETWORK else 'custom-resolution-ui' if RESOLUTION else 'frontend-lifecycle')
if '--out' in sys.argv:
    OUT=Path(sys.argv[sys.argv.index('--out')+1]).resolve()
    assert OUT.is_relative_to((HERE/'build').resolve()),'Evidence must remain under android/build'
GRANTED='--granted' in sys.argv or RESOLUTION or NETWORK or CARD
LABEL='granted' if GRANTED else ('red' if '--red' in sys.argv else 'green')
OUT.mkdir(parents=True,exist_ok=True)

def run(args):
    try:return subprocess.check_output(list(map(str,args)),stderr=subprocess.STDOUT,text=True)
    except subprocess.CalledProcessError as e:print(e.output,flush=True);raise
def adb(*args):return run([ADB,'-P','5041','-s','emulator-5580',*args])
assert adb('shell','getprop','ro.kernel.qemu').strip()=='1','Only the owned PC emulator is allowed'
assert adb('shell','getprop','sys.boot_completed').strip()=='1','Local Android boot incomplete'
manifest=OUT/'manifest.xml'
text=(HERE/'AndroidManifest.xml').read_text().replace('package="com.samsixx.pocket2droid"',f'package="{PACKAGE}"')
text=text.replace('<application ','<application android:debuggable="true" ',1)
if RESOLUTION:text=text.replace('</application>',f'<provider android:name="com.samsixx.pocket2droid.RomFrameFixtureProvider" android:authorities="{PACKAGE}.frames" android:exported="false" android:process=":frame_fixture" /></application>')
text=text.replace('</manifest>',f'<instrumentation android:name="com.samsixx.pocket2droid.{TEST}" android:targetPackage="{PACKAGE}" /></manifest>')
manifest.write_text(text)
classes=OUT/('classes-'+LABEL);classes.mkdir(exist_ok=True)
sources=sorted((HERE/'src').rglob('*.java'))+[HERE/('tests/'+TEST+'.java')]
if NETWORK:sources.append(HERE/'tests/EngineKeyTest.java')
if RESOLUTION:sources.append(HERE/'tests/RomFrameFixtureProvider.java')
run(['javac','--release','8','-encoding','UTF-8','-cp',API,'-d',classes,*sources])
jar=OUT/(LABEL+'.jar');run(['jar','cf',jar,'-C',classes,'.'])
dex=OUT/('dex-'+LABEL);dex.mkdir(exist_ok=True)
run(['java','-cp',SDK/'lib/d8.jar','com.android.tools.r8.D8','--min-api','24','--lib',API,'--output',dex,jar])
resources=OUT/'resources.zip';run([SDK/'aapt2','compile','--dir',HERE/'res','-o',resources])
apk=OUT/(LABEL+'-unsigned.apk');run([SDK/'aapt2','link','-I',API,'--manifest',manifest,'-o',apk,resources])
helper=None
if RESOLUTION or NETWORK or CARD:
    helper=OUT/'libp2dstorage-x86_64.so'
    clang='/opt/pocket2droid-android-tools/bionic/android-ndk-r30/toolchains/llvm/prebuilt/linux-x86_64/bin/x86_64-linux-android24-clang'
    run([clang,'-std=c11','-O2','-shared','-fPIC','-Wall','-Wextra','-Werror',HERE/'native/storage_publish.c','-o',helper])
with zipfile.ZipFile(apk,'a',zipfile.ZIP_DEFLATED) as z:
    z.write(dex/'classes.dex','classes.dex')
    if helper:z.write(helper,'lib/x86_64/libp2dstorage.so')
    if NETWORK:
        for name in ('autorun.exe','manifest.json'):
            z.write(HERE/'build/network-setup/production-helper'/name,'assets/network-setup/'+name)
key=OUT/'test-only.p12'
if not key.exists():run(['keytool','-genkeypair','-keystore',key,'-storetype','PKCS12','-storepass','frontend-test-only','-keypass','frontend-test-only','-alias','test','-keyalg','RSA','-dname','CN=Disposable PC frontend test','-validity','30'])
signed=OUT/(LABEL+'-test-only.apk');run(['java','-jar',SDK/'lib/apksigner.jar','sign','--ks',key,'--ks-pass','pass:frontend-test-only','--out',signed,apk])
owner=OUT/'owned-install.json'
existing=subprocess.run([str(ADB),'-P','5041','-s','emulator-5580','shell','pm','path',PACKAGE],capture_output=True,text=True).stdout.strip()
if existing:assert owner.exists() and json.loads(owner.read_text())['package']==PACKAGE,'Unexpected existing test package'
else:owner.write_text(json.dumps({'package':PACKAGE,'serial':'emulator-5580','initially_absent':True}))
print(adb('install','--no-incremental','-r',signed).strip(),flush=True)
adb('shell','appops','set',PACKAGE,'MANAGE_EXTERNAL_STORAGE','allow' if GRANTED else 'deny')
extra=['-e','http_port',sys.argv[sys.argv.index('--http-port')+1]] if NETWORK else []
result=adb('shell','am','instrument','-w','-e','storage_granted','true' if GRANTED else 'false',*extra,PACKAGE+'/com.samsixx.pocket2droid.'+TEST)
(OUT/(LABEL+'.log')).write_text(result)
(OUT/(LABEL+'-sources.json')).write_text(json.dumps({p.relative_to(HERE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},indent=2))
print(result,flush=True)
assert 'Process crashed' not in result and 'ERROR ' not in result,result
if '--red' not in sys.argv:assert 'PASS ' in result and 'ERROR ' not in result,result
