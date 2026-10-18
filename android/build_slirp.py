"""Pinned private static libslirp, host and Android/Bionic API24."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, subprocess, tarfile, urllib.request
HERE=Path(__file__).resolve().parent
OUT=HERE/'build/networking'
ROOT=Path('/opt/pocket2droid-network-integration/deps')
VERSION='4.9.5'
DIGEST='f43e68b60b580647574ec4a0e2b6c600a56281e6c39f79426510832dc810f483'
URL='https://gitlab.freedesktop.org/slirp/libslirp/-/archive/v4.9.5/libslirp-v4.9.5.tar.gz'
MESON='/opt/pocket2droid-tcg-build/host/pyvenv/bin/meson'
TOOLS=Path('/opt/pocket2droid-android-tools/bionic/android-ndk-r30/toolchains/llvm/prebuilt/linux-x86_64/bin')
PREFIX=Path('/opt/pocket2droid-android-tools/bionic/sysroot/data/data/com.termux/files/usr')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--platform',choices=['host','android'],required=True);p.add_argument('--unpatched',action='store_true',help='test-only RED control');a=p.parse_args()
    ROOT.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    archive=ROOT/'libslirp-4.9.5.tar.gz'
    if not archive.exists():urllib.request.urlretrieve(URL,archive)
    assert sha(archive)==DIGEST,'libslirp archive identity mismatch'
    suffix=a.platform+('-unpatched' if a.unpatched else '')
    source=ROOT/('source-'+suffix);build=ROOT/('build-'+suffix);dest=OUT/suffix
    if not source.exists():
        source.mkdir();subprocess.run(['tar','-xzf',str(archive),'--strip-components=1','-C',str(source)],check=True)
    patch=HERE/'patches/libslirp-android-resolver.patch'
    if not a.unpatched:
        with tarfile.open(archive) as verified:
            pristine=verified.extractfile('libslirp-v4.9.5/src/slirp.c').read()
        (source/'src/slirp.c').write_bytes(pristine)
        subprocess.run(['patch','--batch','-p1','-i',str(patch)],cwd=source,check=True)
    env=dict(os.environ);args=[MESON,'setup',str(build),str(source),'--prefix='+str(dest),'--libdir=lib','--default-library=static','--buildtype=release','-Db_lto=false','-Dtests=false']
    # Older releases have no tests option; tests are upstream build_by_default false.
    args.remove('-Dtests=false')
    if a.platform=='android':
        cross=ROOT/'slirp-android.ini'
        cross.write_text("[binaries]\nc = '"+str(TOOLS/'aarch64-linux-android24-clang')+"'\nar = '"+str(TOOLS/'llvm-ar')+"'\nstrip = '"+str(TOOLS/'llvm-strip')+"'\npkg-config = '/usr/bin/pkg-config'\n[host_machine]\nsystem = 'android'\ncpu_family = 'aarch64'\ncpu = 'aarch64'\nendian = 'little'\n[properties]\nneeds_exe_wrapper = true\n[built-in options]\nc_args = ['-I"+str(PREFIX/'include')+"']\n")
        args+=['--cross-file',str(cross)]
        env.update(PKG_CONFIG_LIBDIR=str(PREFIX/'lib/pkgconfig'),PKG_CONFIG_SYSROOT_DIR=str(PREFIX.parents[4]))
    if (build/'build.ninja').exists():args.insert(2,'--reconfigure')
    with (OUT/('slirp-'+suffix+'-build.log')).open('w') as log:
        subprocess.run(args,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        subprocess.run(['ninja','-C',str(build),'-j8','install'],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    notices=dest/'source';notices.mkdir(exist_ok=True)
    shutil.copy2(archive,notices/archive.name)
    for name in ['COPYRIGHT','src/slirp.c']:
        target=notices/Path(name).name;shutil.copy2(source/name,target)
    if not a.unpatched:shutil.copy2(patch,notices/patch.name)
    record={'version':VERSION,'url':URL,'archive_sha256':DIGEST,'platform':a.platform,'patched':not a.unpatched,'patch_sha256':sha(patch) if not a.unpatched else None,'library_sha256':sha(dest/'lib/libslirp.a'),'builder_sha256':sha(Path(__file__)),'source_sha256':{str(f.relative_to(source)):sha(f) for f in source.rglob('*') if f.is_file()},'compiler':str(TOOLS/'aarch64-linux-android24-clang') if a.platform=='android' else shutil.which('cc')}
    (dest/'provenance.json').write_text(json.dumps(record,indent=2)+'\n');print('Built',suffix,record['library_sha256'])
if __name__=='__main__':main()
