"""Cached native Android/Bionic QEMU build, separate from proven Linux engines."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=Path('/opt/pocket2droid-android-tools/bionic')
SOURCE=Path('/opt/pocket2droid-network-integration/bionic-source')
BUILD=Path('/opt/pocket2droid-network-integration/bionic-build')
TOOLS=ROOT/'android-ndk-r30/toolchains/llvm/prebuilt/linux-x86_64/bin'
PREFIX=ROOT/'sysroot/data/data/com.termux/files/usr'
CC=TOOLS/'aarch64-linux-android24-clang'
OUT=HERE/'build'

def main():
    slirp=OUT/'networking/android'
    assert (slirp/'provenance.json').exists(), 'Run build_slirp.py --platform android first'
    if not (SOURCE/'.git').exists():
        subprocess.run(['git','clone','--local','--no-hardlinks','/opt/pocket2droid-tcg-build/source',str(SOURCE)],check=True)
    spec=importlib.util.spec_from_file_location('p2d_bionic_sync',HERE.parent/'sync_source.py')
    sync=importlib.util.module_from_spec(spec);spec.loader.exec_module(sync)
    backup=SOURCE/'system/vl.c.orig'
    if backup.exists():
        assert backup.read_bytes()==(HERE.parent/'qemu/system/vl.c').read_bytes(), 'Unexpected patch backup contents'
        backup.unlink()
    sync.CACHE=SOURCE;sync.main()
    # Android heap tags are incompatible with QEMU's host-pointer bookkeeping.
    # Reuse upstream Termux's published initialization workaround only.
    patch=OUT/'termux-reference/0016-Add-workaround-for-tagged-pointers-on-Android-12.patch'
    raw=patch.read_text().replace('#ifdef __TERMUX__','#ifdef __ANDROID__')
    p=subprocess.run(['patch','-p1','--batch','--forward','--no-backup-if-mismatch'],input=raw,text=True,cwd=SOURCE,capture_output=True)
    (OUT/'bionic-patch.log').write_text(p.stdout+p.stderr);p.check_returncode()
    vl=SOURCE/'system/vl.c'
    vl.write_text(vl.read_text().replace('#include <stdbool.h>', '#include <stdbool.h>\n#include <android/api-level.h>'))
    meson=SOURCE/'meson.build'
    text=meson.read_text()
    assert 'if not have_shm_open\n' in text
    meson.write_text(text.replace('if not have_shm_open\n',"if not have_shm_open and not cc.has_header('android/api-level.h')\n",1))
    # Android has no librt/POSIX shm namespace. A QEMU fallback uses its
    # caller-selected private TMPDIR, with normal exclusive creation semantics.
    posix=SOURCE/'util/oslib-posix.c'
    text=posix.read_text()
    marker='#define MAX_MEM_PREALLOC_THREAD_COUNT'
    assert marker in text
    support_code='''#ifdef __ANDROID__
static char *p2d_shm_path(const char *name)
{
    while (*name == '/') name++;
    if (!*name || strchr(name, '/')) { errno = EINVAL; return NULL; }
    return g_build_filename(g_get_tmp_dir(), name, NULL);
}
static int shm_open(const char *name, int flags, mode_t mode)
{
    char *path = p2d_shm_path(name);
    if (!path) return -1;
    int fd = open(path, flags | O_CLOEXEC | O_NOFOLLOW, mode);
    g_free(path); return fd;
}
static int shm_unlink(const char *name)
{
    char *path = p2d_shm_path(name);
    if (!path) return -1;
    int result = unlink(path); g_free(path); return result;
}
#endif

'''
    posix.write_text(text.replace(marker,support_code+marker,1))
    # Bionic setjmp workaround shipped by the established Android QEMU port.
    support=SOURCE.parent/'setjmp';support.mkdir(exist_ok=True);(support/'private').mkdir(exist_ok=True)
    for original in (OUT/'termux-reference/setjmp-aarch64').iterdir():
        name=original.name.replace('private-','private/')
        target=support/name;shutil.copyfile(original,target)
    subprocess.run([str(CC),'-I'+str(support),'-c',str(support/'setjmp.S'),'-o',str(support/'setjmp.o')],check=True)
    subprocess.run([str(TOOLS/'llvm-ar'),'rcs',str(support/'libandroid-setjmp.a'),str(support/'setjmp.o')],check=True)
    BUILD.mkdir(exist_ok=True)
    pc=SOURCE.parent/'bionic-pkgconfig';pc.mkdir(exist_ok=True)
    for entry in (PREFIX/'lib/pkgconfig').glob('*.pc'):
        (pc/entry.name).write_text(entry.read_text().replace('prefix=/data/data/com.termux/files/usr','prefix='+str(PREFIX)))
    shutil.copy2(slirp/'lib/pkgconfig/slirp.pc',pc/'slirp.pc')
    env=dict(os.environ,PATH=str(TOOLS)+':'+os.environ['PATH'],PKG_CONFIG='/usr/bin/pkg-config',
             PKG_CONFIG_LIBDIR=str(pc),PKG_CONFIG_SYSROOT_DIR='')
    config=[str(SOURCE/'configure'),'--target-list=arm-softmmu','--with-devices-arm=p2d',
            '--cc='+str(CC),'--cxx='+str(TOOLS/'aarch64-linux-android24-clang++'),
            '--host-cc=gcc','--cross-prefix='+str(TOOLS/'llvm-'),'--cpu=aarch64','--disable-werror',
            '--without-default-features','--without-default-devices','--enable-tcg','--enable-pixman','--enable-slirp',
            '--disable-tools','--disable-docs','--disable-user','--disable-plugins','--disable-modules',
            '--extra-cflags=-I'+str(PREFIX/'include'),
            '--extra-ldflags=-L'+str(PREFIX/'lib')+' -L'+str(support)+' -landroid-setjmp -landroid-shmem -llog -Wl,-z,max-page-size=16384 -Wl,-rpath,$ORIGIN']
    identity=hashlib.sha256(json.dumps(config).encode()).hexdigest()
    stamp=BUILD/'p2d-config.sha256'
    if not stamp.exists() or stamp.read_text().strip()!=identity:
        with (OUT/'bionic-configure.log').open('w') as log:
            subprocess.run(config,cwd=BUILD,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        stamp.write_text(identity+'\n')
    with (OUT/'bionic-native.log').open('w') as log:
        subprocess.run(['ninja','-j12','qemu-system-arm'],cwd=BUILD,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    target=OUT/'libp2dengine-bionic.so';shutil.copy2(BUILD/'qemu-system-arm',target)
    record={'binary_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'slirp':json.loads((slirp/'provenance.json').read_text()),
            'runtime_source_directory':str(SOURCE),
            'source':json.loads(SOURCE.with_name(SOURCE.name+'.sync.json').read_text()),
            'platform':'Android/Bionic API24 executable','termux_patch_sha256':hashlib.sha256(raw.encode()).hexdigest(),
            'builder_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'support_sources':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (OUT/'termux-reference/setjmp-aarch64').iterdir()},
            'runtime_source_hashes':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in ['system/vl.c','meson.build','util/oslib-posix.c']}}
    (OUT/'bionic-engine.json').write_text(json.dumps(record,indent=2)+'\n')
    print('Android/Bionic engine built',target,flush=True)

if __name__=='__main__':main()
