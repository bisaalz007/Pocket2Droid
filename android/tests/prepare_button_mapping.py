"""Own feature evidence and read-only pinned reference retrieval."""
from pathlib import Path
import hashlib, json, shutil, urllib.request
root=Path(__file__).resolve().parents[4]
src=root/'EXPERIMENTS/qemu-devemu'
out=src/'android/build/button-mapping'; out.mkdir(parents=True,exist_ok=True)
before=out/'before'
if not before.exists():
    before.mkdir()
    for name in ('android/src','android/res','android/AndroidManifest.xml','android/tests','qemu/hw/misc/p2d-devemu-services.c','tests/test_keyboard.py'):
        a=src/name;b=before/name;b.parent.mkdir(parents=True,exist_ok=True)
        if a.is_dir(): shutil.copytree(a,b)
        else: shutil.copy2(a,b)
    (out/'before-sha256.json').write_text(json.dumps({p.relative_to(before).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in before.rglob('*') if p.is_file()},indent=2))
rev='0f23982a1047b1b2d0dcebe7d9d82ac09a29b63f'
url=f'https://api.github.com/repos/gitntel/Microsoft-Device-Emulator/git/trees/{rev}?recursive=1'
data=json.load(urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Pocket2Droid-source-check'})))
(out/'reference-tree.json').write_text(json.dumps(data,indent=2))
for p in data['tree']:
    if any(s in p['path'].lower() for s in ('iowin','keyboard','board','s3c')):print(p['path'])
for name in ('boards/smdk2410/vktoscan.c','boards/scancodemapping.cpp','boards/smdk2410/devices.cpp'):
    url=f'https://raw.githubusercontent.com/gitntel/Microsoft-Device-Emulator/{rev}/{name}'
    content=urllib.request.urlopen(url).read()
    (out/Path(name).name).write_bytes(content)
    print(name,hashlib.sha256(content).hexdigest())
