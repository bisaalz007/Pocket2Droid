"""Compile production WM5 RAM publication and all frontend sources without an APK."""
from pathlib import Path
import os, shutil, subprocess, sys
HERE=Path(__file__).resolve().parents[1]
SRC=HERE/'src/com/samsixx/pocket2droid'
B=HERE/'build/wm5-ram-tests';B.mkdir(parents=True,exist_ok=True)
API=Path('/opt/pocket2droid-android-tools/android-36/android.jar')
JSON=HERE/'tests/dependencies/json-20240303.jar'
JDK=Path(shutil.which('javac')).resolve().parents[1]
subprocess.run(['cc','-std=c11','-O2','-shared','-fPIC','-Wall','-Wextra','-Werror',
    '-Dsyscall=p2d_test_syscall','-Dwrite=p2d_test_write','-Dfsync=p2d_test_fsync',
    '-I'+str(JDK/'include'),'-I'+str(JDK/'include/linux'),str(HERE/'native/storage_publish.c'),
    str(HERE/'tests/storage_faults.c'),'-o',str(B/'libp2dstorage.so')],check=True)
cp=str(JSON)+':'+str(API)
subprocess.run(['javac','--release','8','-cp',cp,'-d',str(B),
    *map(str,SRC.glob('*.java')),str(HERE/'tests/GuestRamTest.java')],check=True)
env=dict(os.environ)
if '--fallback' in sys.argv:env['P2D_TEST_STORAGE_UNSUPPORTED']='1'
subprocess.run(['java','-Djava.library.path='+str(B),'-cp',str(B)+':'+cp,
    'com.samsixx.pocket2droid.GuestRamTest'],env=env,check=True)
