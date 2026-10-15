"""Build only an owned PC frontend test package; never launch a guest or phone."""
from pathlib import Path
import argparse, subprocess, zipfile, json, hashlib
android=Path(__file__).resolve().parents[1];root=android.parents[2];out=android/'build/button-mapping/android';out.mkdir(parents=True,exist_ok=True)
api=Path('/opt/pocket2droid-android-tools/android-36/android.jar');sdk=api.parent.parent/'android-16';adbpath=root/'tools/android-local/sdk/platform-tools/adb';package='com.samsixx.p2dmapping'
p=argparse.ArgumentParser();p.add_argument('--red',action='store_true');p.add_argument('--suite',choices=['all','ui','runtime','loading'],default='all');args=p.parse_args()
def run(a):return subprocess.check_output(list(map(str,a)),stderr=subprocess.STDOUT,text=True)
def adb(*a):return run([adbpath,'-P','5041','-s','emulator-5580',*a])
assert adb('shell','getprop','ro.kernel.qemu').strip()=='1'
assert adb('shell','getprop','sys.boot_completed').strip()=='1'
manifest=out/'manifest.xml';text=(android/'AndroidManifest.xml').read_text().replace('package="com.samsixx.pocket2droid"',f'package="{package}"').replace('<application ','<application android:debuggable="true" ',1)
instrument='RomLoadingUiTest' if args.suite=='loading' else 'ButtonMappingUiTest'
if args.suite=='loading':text=text.replace('</application>',f'<activity android:name="com.samsixx.pocket2droid.RomLoadingHarnessActivity" android:exported="false" /><provider android:name="com.samsixx.pocket2droid.RomFrameFixtureProvider" android:authorities="{package}.frames" android:exported="false" android:process=":framefixture" /></application>')
manifest.write_text(text.replace('</manifest>',f'<instrumentation android:name="com.samsixx.pocket2droid.{instrument}" android:targetPackage="{package}" /></manifest>'))
classes=out/'classes';classes.mkdir(exist_ok=True);sources=sorted((android/'src').rglob('*.java'))+[android/'tests/ButtonMappingUiTest.java',android/'tests/ButtonMappingRuntimeTest.java']
if args.suite=='loading':sources.extend([android/'tests/RomLoadingUiTest.java',android/'tests/RomLoadingHarnessActivity.java',android/'tests/RomFrameFixtureProvider.java'])
try:run(['javac','--release','8','-encoding','UTF-8','-cp',api,'-d',classes,*sources])
except subprocess.CalledProcessError as e:print(e.output);raise
jar=out/'tests.jar';run(['jar','cf',jar,'-C',classes,'.']);dex=out/'dex';dex.mkdir(exist_ok=True)
run(['java','-cp',sdk/'lib/d8.jar','com.android.tools.r8.D8','--min-api','24','--lib',api,'--output',dex,jar]);res=out/'resources.zip';run([sdk/'aapt2','compile','--dir',android/'res','-o',res]);apk=out/'unsigned-test.apk';run([sdk/'aapt2','link','-I',api,'--manifest',manifest,'-o',apk,res])
with zipfile.ZipFile(apk,'a',zipfile.ZIP_DEFLATED) as z:z.write(dex/'classes.dex','classes.dex')
key=out/'test-only.p12'
if not key.exists():run(['keytool','-genkeypair','-keystore',key,'-storetype','PKCS12','-storepass','mapping-test-only','-keypass','mapping-test-only','-alias','test','-keyalg','RSA','-dname','CN=Disposable PC mapping test','-validity','30'])
signed=out/'signed-test-only.apk';run(['java','-jar',sdk/'lib/apksigner.jar','sign','--ks',key,'--ks-pass','pass:mapping-test-only','--out',signed,apk])
owner=out/'owned-install.json';probe=subprocess.run([str(adbpath),'-P','5041','-s','emulator-5580','shell','pm','path',package],capture_output=True,text=True);assert probe.returncode in (0,1),probe.stderr;existing=probe.stdout.strip()
if existing:assert owner.exists() and json.loads(owner.read_text())['package']==package
else:owner.write_text(json.dumps({'package':package,'serial':'emulator-5580','initially_absent':True}))
print(adb('install','-r',signed).strip(),flush=True);adb('shell','appops','set',package,'MANAGE_EXTERNAL_STORAGE','deny')
result=adb('shell','am','instrument','-w','-e','suite',args.suite,package+'/com.samsixx.pocket2droid.'+instrument);label=('red' if args.red else 'green')+'-'+args.suite;(out/(label+'.log')).write_text(result);print(result,flush=True)
(out/('loading-sources.json' if args.suite=='loading' else 'sources.json')).write_text(json.dumps({p.relative_to(android).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},indent=2))
shot='rom-loading.png' if args.suite=='loading' else 'mapping-screen.png'
try:adb('pull',f'/data/data/{package}/files/{shot}',out/shot)
except subprocess.CalledProcessError:
    with (out/shot).open('wb') as f:subprocess.run([str(adbpath),'-P','5041','-s','emulator-5580','exec-out','run-as',package,'cat',f'files/{shot}'],stdout=f,check=True)
if not args.red:assert 'PASS ' in result and 'ERROR ' not in result and 'FAIL ' not in result,result
