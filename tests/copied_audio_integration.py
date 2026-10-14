"""Reuse verified copied-guest navigation; inspect real Windows/game PCM locally."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'prototypes/tcg-transition/guest.py'
code=SOURCE.read_text()
def replace(old,new):
    global code
    assert code.count(old)==1,(old[:90],code.count(old))
    code=code.replace(old,new)
replace("ap=argparse.ArgumentParser();ap.add_argument('label',choices=['baseline','candidate']);a=ap.parse_args()",
        "ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();a.label='audio'")
replace("binary=HERE/'results'/('qemu-system-arm-'+a.label)","binary=Path('/opt/pocket2droid-tcg-build/host/qemu-system-arm')")
replace("manifest=json.loads((HERE/'results'/(a.label+'-build.json')).read_text())",
        "manifest={'binary_sha256':sha(binary),'instrumentation':'none'}")
replace("sock=Path('/tmp')/('p2d-transition-'+uuid.uuid4().hex+'.sock')", """audio=run/'audio.bin'
    empty=bytearray(67648);struct.pack_into('<5I',empty,0,0x41443250,1,67648,64,65536);audio.write_bytes(empty)
    sock=Path('/tmp')/('p2d-audio-'+uuid.uuid4().hex+'.sock')""")
replace("shared-folder={card},frame-file={frame}'", "shared-folder={card},frame-file={frame},audio-file={audio}'")
replace("            q.request('cont')", """            q.request('qom-set',{'path':'/machine/p2d-media','property':'output-enabled','value':True})
            q.request('cont')""")
replace("wait_for('game_files',(5,31,200,96))", "wait_for('game_files',(5,31,100,96))")
replace("            capture('race-after')", """            capture('race-after')
            q.request('stop')
            data=audio.read_bytes();wp,rp=struct.unpack_from('<2I',data,20)
            packets=[];nonzero=0
            for counter in range((wp-rp)&0xffffffff):
                slot=64+((rp+counter)&63)*32
                epoch,rate,frames,start=struct.unpack_from('<4I',data,slot)
                assert 1<=frames<=2048 and 8000<=rate<=192000
                pcm=bytes(data[2112+((start+i)&65535)] for i in range(frames*4))
                nonzero+=sum(v[0]!=0 for v in struct.iter_unpack('<h',pcm))
                packets.append({'rate':rate,'frames':frames,'epoch':epoch})
            record['audio']={'packets':packets,'nonzero_samples':nonzero,'status':q.request('qom-get',{'path':'/machine/p2d-media','property':'output-status'})}
            assert packets and nonzero,'No actual game PCM observed'
            q.request('qom-set',{'path':'/machine/p2d-media','property':'output-enabled','value':False})
            assert struct.unpack_from('<2I',audio.read_bytes(),20)[0]==struct.unpack_from('<2I',audio.read_bytes(),20)[1]
            q.request('cont')""")
replace("        (HERE/'results'/('guest-'+a.label+'.json')).write_text(json.dumps(dict(run=str(run),**record),indent=2)+'\\n')",
        "        a.output.parent.mkdir(parents=True,exist_ok=True)\n        record['canonical_source_hashes']=json.loads(Path('/opt/pocket2droid-tcg-build/source.sync.json').read_text())['paths']\n        a.output.write_text(json.dumps(dict(run=str(run),**record),indent=2)+'\\n')")
exec(compile(code,str(SOURCE),'exec'),{'__name__':'__main__','__file__':str(SOURCE)})
