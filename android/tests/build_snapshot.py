"""Build a same-signer read-only instrumentation utility, not a Pocket2Droid release."""
from pathlib import Path
import hashlib, re, subprocess, zipfile
HERE = Path(__file__).resolve().parent
ANDROID = HERE.parent
PROJECT = ANDROID.parents[2]
TOOLS = Path('/opt/pocket2droid-android-tools')
SDK = TOOLS/'android-16'; API = TOOLS/'android-36/android.jar'
ROOT = ANDROID/'build/snapshot-tool'
ROOT.mkdir(exist_ok=True)
classes = ROOT/'classes'; classes.mkdir(exist_ok=True)
manifest = ROOT/'AndroidManifest.xml'
manifest.write_text('''<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.samsixx.p2dforensics" android:versionCode="1" android:versionName="1">
<uses-sdk android:minSdkVersion="24" android:targetSdkVersion="36"/>
<application android:label="P2D temporary snapshot utility" android:allowBackup="false"/>
<instrumentation android:name="com.samsixx.p2dforensics.Snapshot" android:targetPackage="com.samthedev.pocket2droid"/>
</manifest>''')
def run(args): subprocess.run(list(map(str,args)), check=True)
run(['javac','--release','8','-cp',API,'-d',classes,HERE/'Snapshot.java'])
jar=ROOT/'classes.jar'; run(['jar','cf',jar,'-C',classes,'.'])
dex=ROOT/'dex'; dex.mkdir(exist_ok=True)
run(['java','-cp',SDK/'lib/d8.jar','com.android.tools.r8.D8','--min-api','24','--lib',API,'--output',dex,jar])
unsigned=ROOT/'unsigned.apk'
run([SDK/'aapt2','link','-I',API,'--manifest',manifest,'-o',unsigned])
with zipfile.ZipFile(unsigned,'a') as z: z.write(dex/'classes.dex','classes.dex')
aligned=ROOT/'aligned.apk'; run([SDK/'zipalign','-f','4',unsigned,aligned])
key=PROJECT/'Key/wm6-v2-development.p12'
match=re.search(r'(?im)\bpassword\s*[:=]\s*([^\r\n]+)',(key.parent/'README.txt').read_text())
assert match
secret=TOOLS/'.p2d-signing-password'; secret.touch(mode=0o600,exist_ok=False)
signed=ROOT/'p2d-snapshot-signed.apk'
try:
    secret.write_text(match.group(1).strip().strip('`"\'')+'\n')
    run(['java','-jar',SDK/'lib/apksigner.jar','sign','--ks',key,'--ks-type','PKCS12','--ks-pass','file:'+str(secret),'--out',signed,aligned])
finally: secret.unlink()
verify=subprocess.check_output(['java','-jar',str(SDK/'lib/apksigner.jar'),'verify','--print-certs',str(signed)],text=True)
assert '85d6f87a557def48710b8e295ed58513888a99852843a90106b3b7f18e39681b' in verify
print('SNAPSHOT_TOOL '+hashlib.sha256(signed.read_bytes()).hexdigest())
