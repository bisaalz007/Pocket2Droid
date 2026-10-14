"""Check the requested new-engine-only APK contract against actual signed contents."""
from pathlib import Path
import argparse, importlib.util, zipfile
HERE = Path(__file__).resolve().parents[1]
PROJECT = HERE.parents[2]
def check(path):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None, 'APK CRC mismatch'
        assert 'lib/arm64-v8a/libwm6android.so' not in z.namelist(), 'Old engine is still packaged'
        assert 'lib/arm64-v8a/libp2dengine.so' in z.namelist(), 'TCG engine missing'
        assert 'lib/arm64-v8a/libp2dstorage.so' in z.namelist(), 'Atomic storage publication helper missing'
        data = z.read('AndroidManifest.xml')
    spec = importlib.util.spec_from_file_location('manifest', PROJECT/'SOURCE/review-v640/Pocket2Droid-V6.40-Clean-Source/verify_signed_apk.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    elements=module.parse_manifest(data)
    assert not any(name=='activity' and attrs.get('name')=='android.app.NativeActivity' for name,attrs in elements), 'Old-engine activity still available'
    manifest=next(attrs for name,attrs in elements if name=='manifest')
    assert manifest['package']=='com.samsixx.wm6android' and manifest['versionCode']==657 and manifest['versionName']=='6.57'
    print('PASS original package, distinct V6.57, new engine only, storage helper present')
if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('apk',type=Path);check(p.parse_args().apk)
