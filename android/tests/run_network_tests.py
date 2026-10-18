"""Production settings/config/session logic on host JVM; no APK/device data."""
from pathlib import Path
import subprocess
HERE=Path(__file__).resolve().parents[1];SRC=HERE/'src/com/samsixx/pocket2droid';OUT=HERE/'build/networking/java-tests';OUT.mkdir(parents=True,exist_ok=True)
api=Path('/opt/pocket2droid-android-tools/android-36/android.jar');json=HERE/'tests/dependencies/json-20240303.jar'
sources=[SRC/(n+'.java') for n in ['RomSettings','NetworkConfig']]
tests=[HERE/'tests/NetworkConfigTest.java']
if (HERE/'tests/NetworkSetupTest.java').exists():
    sources.append(SRC/'NetworkSetup.java');tests.append(HERE/'tests/NetworkSetupTest.java')
if (HERE/'tests/NetworkSessionTest.java').exists():
    sources.append(SRC/'NetworkSession.java');tests.append(HERE/'tests/NetworkSessionTest.java')
cp=str(json)+':'+str(api)
subprocess.run(['javac','--release','8','-encoding','UTF-8','-cp',cp,'-d',str(OUT),*map(str,sources+tests)],check=True)
for test in tests:subprocess.run(['java','-cp',str(OUT)+':'+cp,'com.samsixx.pocket2droid.'+test.stem],check=True)
