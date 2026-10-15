"""Focused actual Java/JNI storage suite, with host-only filesystem fault injection."""
from pathlib import Path
import argparse, os, shutil, subprocess
HERE=Path(__file__).resolve().parents[1]
JDK=Path(shutil.which('javac')).resolve().parents[1]
ANDROID=Path('/opt/pocket2droid-android-tools/android-36/android.jar')
p=argparse.ArgumentParser(description=__doc__); p.add_argument('--fallback',action='store_true'); a=p.parse_args()
build=HERE/'build/storage-tests'; build.mkdir(parents=True,exist_ok=True)
subprocess.run(['cc','-std=c11','-O2','-fPIC','-shared','-Wall','-Wextra','-Werror',
    '-Dsyscall=p2d_test_syscall','-Dwrite=p2d_test_write','-Dfsync=p2d_test_fsync','-I'+str(JDK/'include'),'-I'+str(JDK/'include/linux'),
    str(HERE/'native/storage_publish.c'),str(HERE/'tests/storage_faults.c'),'-o',str(build/'libp2dstorage.so')],check=True)
sources=[HERE/'src/com/samsixx/pocket2droid'/n for n in ('StorageLayout.java','StoragePublish.java','RomProfile.java','RomSettings.java','RomRepository.java','ProfileFiles.java','SessionGuard.java')]
tests=[HERE/'tests'/n for n in ('StorageLayoutTest.java','StorageFallbackTest.java')]
subprocess.run(['javac','--release','8','-cp',str(ANDROID),'-d',str(build),*map(str,sources+tests)],check=True)
env=dict(os.environ)
if a.fallback: env['P2D_TEST_STORAGE_UNSUPPORTED']='1'
test='StorageFallbackTest' if a.fallback else 'StorageLayoutTest'
subprocess.run(['java','-Djava.library.path='+str(build),'-cp',str(build)+':'+str(ANDROID),
    'com.samsixx.pocket2droid.'+test],env=env,check=True)
