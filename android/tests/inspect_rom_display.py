"""Read-only inventory of embedded display clues; no ROM/save writes."""
from pathlib import Path
import struct,json
P=Path(__file__).resolve().parents[4]/'PC windows mobile 6 Files/Roms and files'
paths=[P/'pocket pc/Deviceemulation/0409'/n for n in ('PPC_USA.BIN','PPC_USA_GSM_QVGA_VR.BIN','PPC_USA_GSM_VGA_VR.BIN','PPC_USA_GSM_VGA_SQUARE_VR.BIN')]
paths += [P/'pocket pc/DeviceemulationV650/0409/PPC_USA_GSM_WVGA_VR.BIN']
for p in paths:
    data=p.read_bytes();bitmaps=[];offset=0
    while True:
        offset=data.find(b'BM',offset)
        if offset<0:break
        if offset+54<=len(data):
            size,_,start,dib=struct.unpack_from('<I4sII',data,offset+2)
            w,h,planes,bpp=struct.unpack_from('<iiHH',data,offset+18)
            if dib in (40,108,124) and planes==1 and bpp in (1,4,8,16,24,32) and 100<=w<=1024 and 100<=abs(h)<=800 and 54<=start<=size and offset+size<=len(data):
                bitmaps.append(dict(offset=offset,width=w,height=h,bpp=bpp))
        offset+=2
    clues={}
    for word in ('DisplayWidth','DisplayHeight','ScreenWidth','ScreenHeight','LogicalPixelsX','LogicalPixelsY','HighDPI','480','QVGA','VGA','LCD'):
        found=data.find(word.encode('utf-16le'))
        if found>=0:clues[word]=found
    print(json.dumps(dict(rom=p.name,size=len(data),header=data[:80].hex(),bmp=bitmaps[:20],clues=clues)),flush=True)
