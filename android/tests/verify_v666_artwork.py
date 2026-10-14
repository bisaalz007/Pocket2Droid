"""Inspect the actual production APK's complete current artwork, including GIF."""
from pathlib import Path
import hashlib,io,json,zipfile
from PIL import Image
here=Path(__file__).resolve().parents[1];build=here/'build'
apk=build/'Pocket2Droid-V6.66-TCG-CANDIDATE-SIGNED.apk'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
rows=[]
with zipfile.ZipFile(apk) as z:
    expected=set()
    for source in sorted(p for p in (here/'res').rglob('*') if p.is_file()):
        names=[n for n in z.namelist() if n.startswith('res/') and n.endswith('/'+source.name)]
        assert len(names)==1,source.name
        name=names[0];expected.add(name);linked=z.read(name)
        row={'resource':source.relative_to(here).as_posix(),'source_sha256':sha(source),'apk_entry':name,'apk_sha256':hashlib.sha256(linked).hexdigest()}
        if source.suffix=='.png':
            original=Image.open(source).convert('RGBA');compiled=Image.open(io.BytesIO(linked)).convert('RGBA')
            assert original.size==compiled.size and original.tobytes()==compiled.tobytes(),name
            row['pixels_identical']=True
        else:
            assert source.name=='rom_loading.gif' and linked==source.read_bytes()
            image=Image.open(io.BytesIO(linked));assert image.n_frames==14 and image.info['loop']==0
            row.update(original_animated_bytes=True,frames=14,infinite_loop=True)
        rows.append(row)
    assert {n for n in z.namelist() if n.startswith('res/')}==expected,'Stale or unexpected APK resources'
    assert len(rows)==48 and sum(r.get('pixels_identical',False) for r in rows)==47
    assert {n for n in z.namelist() if n.startswith('assets/')}=={'assets/QEMU-COPYING.txt'}
record={'apk_sha256':sha(apk),'resources':rows,'png_pixels_identical':47,'original_gif_verified':True,'no_stale_resources':True}
(build/'button-mapping/v666-artwork.json').write_text(json.dumps(record,indent=2)+'\n')
print('Actual signed APK: 47 PNGs preserve source pixels; original 14-frame looping GIF included; no stale resources')
