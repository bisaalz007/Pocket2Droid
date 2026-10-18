"""Build an isolated target-36 app-UID memfd test; never installs or opens user data."""
from pathlib import Path
import hashlib
import json
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'build/network-setup/android-seal-fix/probe'
TOOLS = Path('/opt/pocket2droid-android-tools')
SDK = TOOLS / 'android-16'
API = TOOLS / 'android-36/android.jar'
NDK = TOOLS / 'bionic/android-ndk-r30/toolchains/llvm/prebuilt/linux-x86_64/bin'
OUT.mkdir(parents=True, exist_ok=True)
manifest = OUT / 'AndroidManifest.xml'
manifest.write_text('''<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.samsixx.p2dsealprobe" android:versionCode="1" android:versionName="1">
<uses-sdk android:minSdkVersion="24" android:targetSdkVersion="36"/>
<application android:debuggable="true" android:extractNativeLibs="true" android:label="P2D isolated seal check"/>
<instrumentation android:name="com.samsixx.p2dsealprobe.SealProbe" android:targetPackage="com.samsixx.p2dsealprobe"/>
</manifest>''', encoding='utf-8')
source = HERE / 'SealProbe.java'
classes = OUT / 'classes'
dex = OUT / 'dex'
classes.mkdir(exist_ok=True)
dex.mkdir(exist_ok=True)
subprocess.run([str(NDK/'aarch64-linux-android24-clang'), '-Wall', '-Wextra', '-Werror',
                '-shared', '-fPIC', '-O2', '-Wl,-z,max-page-size=16384',
                str(HERE/'network_setup_seal_probe.c'), '-o', str(OUT/'libsealprobe.so')], check=True)
subprocess.run(['javac', '--release', '8', '-cp', str(API), '-d', str(classes), str(source)], check=True)
subprocess.run(['jar', 'cf', str(OUT/'classes.jar'), '-C', str(classes), '.'], check=True)
subprocess.run(['java', '-cp', str(SDK/'lib/d8.jar'), 'com.android.tools.r8.D8',
                '--min-api', '24', '--lib', str(API), '--output', str(dex), str(OUT/'classes.jar')], check=True)
resources = OUT / 'resources.apk'
subprocess.run([str(SDK/'aapt2'), 'link', '-I', str(API), '--manifest', str(manifest), '-o', str(resources)], check=True)
unsigned = OUT / 'unsigned.apk'
with zipfile.ZipFile(unsigned, 'w', zipfile.ZIP_STORED) as result, zipfile.ZipFile(resources) as base:
    for name in base.namelist(): result.writestr(name, base.read(name))
    result.writestr('classes.dex', (dex/'classes.dex').read_bytes())
    result.writestr('lib/arm64-v8a/libsealprobe.so', (OUT/'libsealprobe.so').read_bytes())
    runtime=HERE.parent/'build/runtime'
    record=json.loads((HERE.parent/'build/runtime.json').read_text())
    for name,row in record['files'].items():
        data=(runtime/name).read_bytes()
        assert hashlib.sha256(data).hexdigest()==row['sha256']
        result.writestr('lib/arm64-v8a/'+name,data)
    result.writestr('assets/autorun.exe',(HERE.parent/'build/network-setup/production-helper/autorun.exe').read_bytes())
    result.writestr('assets/idle.bin',bytes.fromhex('feffffea'))
key = OUT / 'probe.jks'
if not key.exists():
    subprocess.run(['keytool','-genkeypair','-keystore',str(key),'-storepass','android',
                    '-keypass','android','-alias','probe','-dname','CN=P2D isolated probe',
                    '-keyalg','RSA','-validity','3650'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
aligned = OUT / 'aligned.apk'
subprocess.run([str(SDK/'zipalign'),'-f','-P','16','4',str(unsigned),str(aligned)],check=True)
subprocess.run([str(SDK/'apksigner'),'sign','--ks',str(key),'--ks-pass','pass:android',
                '--out',str(OUT/'seal-probe.apk'),str(aligned)],check=True)
print(OUT/'seal-probe.apk')
