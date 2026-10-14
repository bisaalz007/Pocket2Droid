"""Build a DEX CLI test of exact production Java/JNI; no test APK installation."""
from pathlib import Path
import subprocess,zipfile
HERE=Path(__file__).resolve().parents[1];SDK=Path('/opt/pocket2droid-android-tools')
build=HERE/'build/storage-art';build.mkdir(exist_ok=True)
classes=build/'classes';classes.mkdir(exist_ok=True)
sources=[HERE/'src/com/samthedev/pocket2droid'/n for n in ('StorageLayout.java','StoragePublish.java')]
subprocess.run(['javac','--release','8','-cp',str(SDK/'android-36/android.jar'),'-d',str(classes),*map(str,sources),str(HERE/'tests/StorageCompatibilityArtTest.java')],check=True)
subprocess.run(['jar','cf',str(build/'input.jar'),'-C',str(classes),'.'],check=True)
subprocess.run(['java','-cp',str(SDK/'android-16/lib/d8.jar'),'com.android.tools.r8.D8','--min-api','24','--lib',str(SDK/'android-36/android.jar'),'--output',str(build),str(build/'input.jar')],check=True)
with zipfile.ZipFile(build/'tests.jar','w') as z:z.write(build/'classes.dex','classes.dex')
print(build/'tests.jar')
