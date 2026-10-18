"""Owned networking integration cache and source/evidence snapshot (no release)."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, os, shutil, subprocess, time
EXP=Path(__file__).resolve().parents[1]
OUT=EXP/'android/build/networking'
ROOT=Path('/opt/pocket2droid-network-integration')
SOURCE=ROOT/'source'
BUILD=ROOT/'host'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    a=argparse.ArgumentParser();a.add_argument('--snapshot',action='store_true');a.add_argument('--build',action='store_true');args=a.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    if args.snapshot:
        baseline=json.loads((EXP/'android/build/bionic-engine.json').read_text())['source']
        assert all(sha(EXP/'qemu'/n)==h for n,h in baseline['paths'].items())
        files={str(p.relative_to(EXP)):sha(p) for p in (EXP/'android/src').rglob('*') if p.is_file()}
        files.update({'qemu/'+n:h for n,h in baseline['paths'].items()})
        files['android/AndroidManifest.xml']=sha(EXP/'android/AndroidManifest.xml')
        artifacts={str(p.relative_to(EXP.parents[1])):sha(p) for p in (EXP.parents[1]/'apk/1.0.2-test3').glob('*') if p.is_file()}
        record={'source':baseline,'files':files,'artifacts':artifacts}
        dest=OUT/'baseline.json';assert not dest.exists();dest.write_text(json.dumps(record,indent=2)+'\n')
        backup=OUT/'baseline';backup.mkdir()
        for n in files:
            p=backup/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(EXP/n,p)
        print('Baseline preserved',len(files),len(artifacts));return
    baseline=json.loads((OUT/'baseline.json').read_text())
    ROOT.mkdir(exist_ok=True)
    if not SOURCE.exists(): subprocess.run(['git','clone','--local','--no-hardlinks','/opt/pocket2droid-tcg-build/source',str(SOURCE)],check=True)
    spec=importlib.util.spec_from_file_location('network_sync',EXP/'sync_source.py')
    sync=importlib.util.module_from_spec(spec);spec.loader.exec_module(sync)
    names=set(sync.git_names('diff','--name-only','-z',sync.BASE))
    names.update(sync.git_names('ls-files','--others','--exclude-standard','-z'))
    for name in names:
        src=EXP/'qemu'/name
        if src.is_file():
            dest=SOURCE/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
    if args.build:
        BUILD.mkdir(exist_ok=True)
        slirp=OUT/'host/lib/pkgconfig'
        deps=Path('/opt/pocket2droid-network-probe/deps/usr/lib/x86_64-linux-gnu')
        env=dict(os.environ,PKG_CONFIG_PATH=str(slirp if slirp.exists() else deps/'pkgconfig'))
        identity=sha(OUT/'host/provenance.json') if (OUT/'host/provenance.json').exists() else 'spike-4.7'
        stamp=BUILD/'network-dependency.sha256'
        if not (BUILD/'build.ninja').exists() or not stamp.exists() or stamp.read_text()!=identity:
            cmd=[str(SOURCE/'configure'),'--target-list=arm-softmmu','--with-devices-arm=p2d','--without-default-features','--without-default-devices','--enable-tcg','--enable-pixman','--enable-hmp','--enable-slirp','--disable-werror','--disable-docs','--disable-tools','--python=/opt/pocket2droid-tcg-build/host/pyvenv/bin/python3','--extra-ldflags=-Wl,-rpath,'+str(deps)]
            with (OUT/'host-configure.log').open('w') as log: subprocess.run(cmd,cwd=BUILD,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
            stamp.write_text(identity)
        start=time.monotonic()
        with (OUT/'host-build.log').open('w') as log: subprocess.run(['ninja','-j12','qemu-system-arm'],cwd=BUILD,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        print(json.dumps({'binary':str(BUILD/'qemu-system-arm'),'sha256':sha(BUILD/'qemu-system-arm'),'seconds':time.monotonic()-start}))
if __name__=='__main__':main()
