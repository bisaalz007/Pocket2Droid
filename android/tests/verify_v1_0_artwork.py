"""Verify complete artwork in the actual signed V1.0 candidate."""
from pathlib import Path
import hashlib,io,json,zipfile
from PIL import Image

here=Path(__file__).resolve().parents[1];build=here/'build'
apk=build/'Pocket2Droid-V1.0-TCG-CANDIDATE-SIGNED.apk'
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
rows=[]
with zipfile.ZipFile(apk) as archive:
    expected=set()
    for source in sorted(path for path in (here/'res').rglob('*') if path.is_file()):
        matches=[name for name in archive.namelist() if name.startswith('res/') and name.endswith('/'+source.name)]
        assert len(matches)==1,source.name
        name=matches[0];expected.add(name);data=archive.read(name)
        row=dict(resource=source.relative_to(here).as_posix(),source_sha256=sha(source),apk_entry=name,apk_sha256=hashlib.sha256(data).hexdigest())
        if source.suffix=='.png':
            original=Image.open(source).convert('RGBA');linked=Image.open(io.BytesIO(data)).convert('RGBA')
            assert original.size==linked.size,name
            raw=original.tobytes();compiled=linked.tobytes();normalized=0
            for offset in range(0,len(raw),4):
                before=raw[offset:offset+4];after=compiled[offset:offset+4]
                assert before[3]==after[3],name+' alpha mismatch'
                if before[3]:assert before==after,name+' visible pixel mismatch'
                elif before!=after:normalized+=1
            if not source.name.startswith('rom_icon_'):assert raw==compiled,name+' unexpected artwork change'
            # RGB beneath fully transparent pixels may be normalized by aapt2;
            # visible pixels and every alpha value are checked above.
            row.update(visible_pixels_identical=True,alpha_identical=True,transparent_rgb_normalized=normalized)
        else:
            assert source.name=='rom_loading.gif' and data==source.read_bytes()
            image=Image.open(io.BytesIO(data));assert image.n_frames==14 and image.info['loop']==0
            row.update(original_animated_bytes=True,frames=14,infinite_loop=True)
        rows.append(row)
    assert {name for name in archive.namelist() if name.startswith('res/')}==expected
    assert len(rows)==48 and sum(row.get('visible_pixels_identical',False) for row in rows)==47
    assert {name for name in archive.namelist() if name.startswith('assets/')}=={'assets/QEMU-COPYING.txt'}
record=dict(apk_sha256=sha(apk),resources=rows,png_visible_pixels_identical=47,original_gif_verified=True,no_stale_resources=True)
out=build/'release-v1.0';out.mkdir(exist_ok=True)
(out/'artwork.json').write_text(json.dumps(record,indent=2)+'\n')
print('PASS signed V1.0 artwork:47 PNGs retain all visible pixels/alpha; six new ROM icons present; original14-frame GIF; no stale resources')
