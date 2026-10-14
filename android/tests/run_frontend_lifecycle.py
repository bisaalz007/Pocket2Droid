"""Frontend-only APK/Instrumentation on the isolated PC emulator, never a phone."""
from pathlib import Path
import subprocess,sys,zipfile,json,hashlib

HERE=Path(__file__).resolve().parents[1]
PROJECT=HERE.parents[2]
API=Path('/opt/pocket2droid-android-tools/android-36/android.jar')
SDK=API.parent.parent/'android-16'
ADB=PROJECT/'tools/android-local/sdk/platform-tools/adb'
PACKAGE='com.samthedev.p2dlifecycle'
OUT=HERE/'build/frontend-lifecycle'
if '--out' in sys.argv:
    OUT=Path(sys.argv[sys.argv.index('--out')+1]).resolve()
    assert OUT.is_relative_to((HERE/'build').resolve()),'Evidence must remain under android/build'
GRANTED='--granted' in sys.argv
LABEL='granted' if GRANTED else ('red' if '--red' in sys.argv else 'green')
OUT.mkdir(parents=True,exist_ok=True)

def run(args):return subprocess.check_output(list(map(str,args)),stderr=subprocess.STDOUT,text=True)
def adb(*args):return run([ADB,'-P','5041','-s','emulator-5580',*args])
assert adb('shell','getprop','ro.kernel.qemu').strip()=='1','Only the owned PC emulator is allowed'
assert adb('shell','getprop','sys.boot_completed').strip()=='1','Local Android boot incomplete'
manifest=OUT/'manifest.xml'
text=(HERE/'AndroidManifest.xml').read_text().replace('package="com.samthedev.pocket2droid"',f'package="{PACKAGE}"')
text=text.replace('<application ','<application android:debuggable="true" ',1)
text=text.replace('</manifest>',f'<instrumentation android:name="com.samthedev.pocket2droid.FrontendLifecycleTest" android:targetPackage="{PACKAGE}" /></manifest>')
manifest.write_text(text)
classes=OUT/('classes-'+LABEL);classes.mkdir(exist_ok=True)
sources=sorted((HERE/'src').rglob('*.java'))+[HERE/'tests/FrontendLifecycleTest.java']
run(['javac','--release','8','-encoding','UTF-8','-cp',API,'-d',classes,*sources])
jar=OUT/(LABEL+'.jar');run(['jar','cf',jar,'-C',classes,'.'])
dex=OUT/('dex-'+LABEL);dex.mkdir(exist_ok=True)
run(['java','-cp',SDK/'lib/d8.jar','com.android.tools.r8.D8','--min-api','24','--lib',API,'--output',dex,jar])
resources=OUT/'resources.zip';run([SDK/'aapt2','compile','--dir',HERE/'res','-o',resources])
apk=OUT/(LABEL+'-unsigned.apk');run([SDK/'aapt2','link','-I',API,'--manifest',manifest,'-o',apk,resources])
with zipfile.ZipFile(apk,'a',zipfile.ZIP_DEFLATED) as z:z.write(dex/'classes.dex','classes.dex')
key=OUT/'test-only.p12'
if not key.exists():run(['keytool','-genkeypair','-keystore',key,'-storetype','PKCS12','-storepass','frontend-test-only','-keypass','frontend-test-only','-alias','test','-keyalg','RSA','-dname','CN=Disposable PC frontend test','-validity','30'])
signed=OUT/(LABEL+'-test-only.apk');run(['java','-jar',SDK/'lib/apksigner.jar','sign','--ks',key,'--ks-pass','pass:frontend-test-only','--out',signed,apk])
owner=OUT/'owned-install.json'
existing=subprocess.run([str(ADB),'-P','5041','-s','emulator-5580','shell','pm','path',PACKAGE],capture_output=True,text=True).stdout.strip()
if existing:assert owner.exists() and json.loads(owner.read_text())['package']==PACKAGE,'Unexpected existing test package'
else:owner.write_text(json.dumps({'package':PACKAGE,'serial':'emulator-5580','initially_absent':True}))
print(adb('install','-r',signed).strip(),flush=True)
adb('shell','appops','set',PACKAGE,'MANAGE_EXTERNAL_STORAGE','allow' if GRANTED else 'deny')
result=adb('shell','am','instrument','-w','-e','storage_granted','true' if GRANTED else 'false',PACKAGE+'/com.samthedev.pocket2droid.FrontendLifecycleTest')
(OUT/(LABEL+'.log')).write_text(result)
(OUT/(LABEL+'-sources.json')).write_text(json.dumps({p.relative_to(HERE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},indent=2))
print(result,flush=True)
assert 'Process crashed' not in result and 'ERROR ' not in result,result
if '--red' not in sys.argv:assert 'PASS ' in result and 'ERROR ' not in result,result
