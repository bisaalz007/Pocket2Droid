"""Focused host Java logic suites and API compilation; no APK or guest boot."""
from pathlib import Path
import argparse, hashlib, subprocess
a=argparse.ArgumentParser()
for name in ('catalog','bindings','normalizer','ownership','capture'):a.add_argument('--'+name,action='store_true')
args=a.parse_args();android=Path(__file__).resolve().parents[1];src=android/'src/com/samthedev/pocket2droid';out=android/'build/button-mapping/host';out.mkdir(parents=True,exist_ok=True)
dep=android/'tests/dependencies/json-20240303.jar'
assert hashlib.sha256(dep.read_bytes()).hexdigest()=='3cf6cd6892e32e2b4c1c39e0f52f5248a2f5b37646fdfbb79a66b46b618414ed'
suites={'catalog':(['GuestKey'],'GuestKeyTest'),'bindings':(['GuestKey','ButtonBindings','ButtonMappingStore'],'ButtonBindingsTest'),'normalizer':(['InputNormalizer'],'InputNormalizerTest'),'ownership':(['GuestKey','ButtonBindings','MappedInputState'],'MappedInputStateTest')}
suites['capture']=(['GuestKey','ButtonBindings','ButtonMappingStore','MappingCapture'],'MappingCaptureTest')
selected=[v for k,v in suites.items() if getattr(args,k)] or list(suites.values())
names=set(n for sources,t in selected for n in sources)
cp=str(dep)+':/opt/pocket2droid-android-tools/android-36/android.jar'
subprocess.run(['javac','--release','8','-encoding','UTF-8','-cp',cp,'-d',str(out),*[str(src/(n+'.java')) for n in sorted(names)],*[str(android/'tests'/(t+'.java')) for _,t in selected]],check=True)
for _,t in selected:subprocess.run(['java','-cp',str(out)+':'+cp,'com.samthedev.pocket2droid.'+t],check=True)
