"""Compile/source identity and original-pixel verification, without packaging a release."""
from pathlib import Path
import argparse, hashlib, json, subprocess, zipfile, difflib, io
android=Path(__file__).resolve().parents[1];root=android.parents[2];src=android.parent;out=android/'build/button-mapping'
p=argparse.ArgumentParser();p.add_argument('--assets-only',action='store_true');args=p.parse_args()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if args.assets_only:
    from PIL import Image
    assets={}
    for path in (android/'res/drawable-nodpi').glob('mapping*.png'):
        name=path.stem
        if name=='mapping_call':original=root/'assets/buttons/Call.png'
        elif name=='mapping_end_call':original=root/'assets/buttons/End call.png'
        else:
            key=name.replace('mapping_key_','').replace('_pressed','')
            original=root/'assets/buttons/Numbers'/('key-'+key+('-pressed@2x.png' if name.endswith('_pressed') else '-normal@2x.png'))
        assert original.read_bytes()==path.read_bytes(),name
        with zipfile.ZipFile(out/'resource-check.ap_') as z:
            member=next(n for n in z.namelist() if n.endswith('/'+path.name))
            linked=Image.open(io.BytesIO(z.read(member))).convert('RGBA');source=Image.open(original).convert('RGBA')
            assert linked.size==source.size and linked.tobytes()==source.tobytes(),name
        assets[name]={'sha256':sha(original),'size':list(source.size),'linked_rgba_exact':True}
    assert len(assets)==26
    gif=android/'res/raw/rom_loading.gif';original=Path('D:/CHATGPT PROJECTS/DUDE THEFT RACING/.codex-remote-attachments/01a0d3c8-f9aa-7bb1-98ac-02f219bdd20f/a5f17b0c-1334-4354-a4f5-eca90820c556/1-1791917002670.gif')
    assert gif.read_bytes()==original.read_bytes()
    with zipfile.ZipFile(out/'resource-check.ap_') as z:assert z.read('res/raw/rom_loading.gif')==original.read_bytes()
    animation=Image.open(gif);durations=[]
    for frame in range(animation.n_frames):animation.seek(frame);durations.append(animation.info['duration'])
    (out/'loading-asset.json').write_text(json.dumps({'sha256':sha(gif),'size':list(animation.size),'frames':animation.n_frames,'loop':animation.info['loop'],'durations_ms':durations,'linked_bytes_exact':True},indent=2))
    (out/'assets.json').write_text(json.dumps(assets,indent=2));print('26 linked icons: exact original pixels; loading GIF: original animated bytes preserved');raise SystemExit()
api=Path('/opt/pocket2droid-android-tools/android-36/android.jar');sdk=api.parent.parent/'android-16'
def run(a,name):
    r=subprocess.run(list(map(str,a)),capture_output=True,text=True);(out/(name+'.log')).write_text(r.stdout+r.stderr);print(name,r.returncode,flush=True);r.check_returncode()
sources=sorted((android/'src').rglob('*.java'));classes=out/'production-classes';classes.mkdir(exist_ok=True)
run(['javac','--release','8','-encoding','UTF-8','-cp',api,'-d',classes,*sources],'production-java')
jar=out/'production.jar';run(['jar','cf',jar,'-C',classes,'.'],'production-jar');dex=out/'production-dex';dex.mkdir(exist_ok=True)
run(['java','-cp',sdk/'lib/d8.jar','com.android.tools.r8.D8','--min-api','24','--lib',api,'--output',dex,jar],'production-dex')
resources=out/'production-resources.zip';run([sdk/'aapt2','compile','--dir',android/'res','-o',resources],'production-resources');run([sdk/'aapt2','link','-I',api,'--manifest',android/'AndroidManifest.xml','-o',out/'resource-check.ap_',resources],'production-link')
run(['python3',android/'tests/run_button_mapping_tests.py'],'host-green');run(['python3',android/'tests/run_rom_boot_tests.py'],'loading-host-green');run(['python3',src/'tests/test_keyboard.py'],'keyboard-green')
before=out/'before';old=json.loads((out/'before-sha256.json').read_text());current={}
for name in ('android/src','android/res','android/AndroidManifest.xml','android/tests','qemu/hw/misc/p2d-devemu-services.c','tests/test_keyboard.py'):
    path=src/name
    for f in (path.rglob('*') if path.is_dir() else [path]):
        if f.is_file() and '__pycache__' not in str(f):current[f.relative_to(src).as_posix()]=sha(f)
changes={k:{'before':old.get(k),'after':v} for k,v in current.items() if old.get(k)!=v};diff=[]
for k in changes:
    if k.endswith(('.java','.py','.c','.xml','.json')):
        a=(before/k).read_text() if (before/k).exists() else ''
        diff.extend(difflib.unified_diff(a.splitlines(True),(src/k).read_text().splitlines(True),fromfile='before/'+k,tofile='after/'+k))
(out/'scope.diff').write_text(''.join(diff));(out/'scope.json').write_text(json.dumps(changes,indent=2))
result={'java_sources':len(sources),'source_sha256':{f.relative_to(android).as_posix():sha(f) for f in sources},'native_source_sha256':sha(src/'qemu/hw/misc/p2d-devemu-services.c'),'native_bionic_sha256':sha(android/'build/libp2dengine-bionic.so'),'java_dex_resource_link_pass':True,'host_logic_pass':True,'keyboard_qmp_cases':11,'release_apk_created':False,'phone_modified':False,'github_uploaded':False,'limitations':['Physical Bluetooth/USB controller reporting unverified.','SDK F8/F9 bytes and layout Fn callback verified separately; PDD preprocessing/full Smartphone key behavior unverified.']}
(out/'verification.json').write_text(json.dumps(result,indent=2));print('Source verification recorded; no release APK produced')
