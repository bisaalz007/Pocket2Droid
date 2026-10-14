"""Seal a self-contained Android runtime with unique APK-compatible SONAMEs."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
OUT=HERE/'build'
PREFIX=Path('/opt/pocket2droid-android-tools/bionic/sysroot/data/data/com.termux/files/usr/lib')
SYSTEM={'libc.so','libm.so','libdl.so','liblog.so','libandroid.so'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def needed(p):return re.findall(r'Shared library: \[([^]]+)\]',subprocess.check_output(['readelf','-d',str(p)],text=True))

def main():
    engine=OUT/'libp2dengine-bionic.so'
    native=json.loads((OUT/'bionic-engine.json').read_text())
    assert sha(engine)==native['binary_sha256']
    todo=[engine];files={}
    while todo:
        p=todo.pop()
        if p.name in files:continue
        files[p.name]=p
        for name in needed(p):
            if name not in SYSTEM:todo.append(PREFIX/name)
    mapping={name:'libp2d_'+re.sub('[^a-zA-Z0-9_]','_',name[3:].split('.so')[0])+'.so' for name in files if name!=engine.name}
    mapping[engine.name]='libp2dengine.so'
    runtime=OUT/'runtime';runtime.mkdir(exist_ok=True)
    record={}
    for name,source in files.items():
        target=runtime/mapping[name];shutil.copyfile(source,target);target.chmod(0o755)
        command=['patchelf','--page-size','16384','--set-rpath','$ORIGIN']
        if name!=engine.name:command+=['--set-soname',mapping[name]]
        for dep in needed(source):
            if dep not in SYSTEM:command+=['--replace-needed',dep,mapping[dep]]
        subprocess.run(command+[str(target)],check=True)
        # Keep complete symbol information for later exact-PC profiling.
        symbols=runtime/(target.name+'.unstripped');shutil.copyfile(target,symbols)
        strip=Path('/opt/pocket2droid-android-tools/bionic/android-ndk-r30/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip')
        subprocess.run([str(strip),'--strip-debug',str(target)],check=True)
        for line in subprocess.check_output(['readelf','-lW',str(target)],text=True).splitlines():
            if 'LOAD ' in line:assert int(line.split()[-1],16)>=16384,'ELF load alignment invalid'
        assert set(needed(target)) <= SYSTEM | set(mapping.values()),'Runtime dependency closure broken'
        record[target.name]={'sha256':sha(target),'input_sha256':sha(source),'original_name':name,'symbols_sha256':sha(symbols)}
    report={'files':record,'native_engine_record_sha256':sha(OUT/'bionic-engine.json'),
            'packager_sha256':sha(Path(__file__)),'tools_record_sha256':sha(OUT/'bionic-tools.json')}
    (OUT/'runtime.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Sealed Android runtime:',', '.join(record),flush=True)

if __name__=='__main__':main()
