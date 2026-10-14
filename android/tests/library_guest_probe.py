"""A->B->A whole-OS launches on disposable filename-linked copies only."""
from pathlib import Path
import fcntl,hashlib,json,os,shutil,struct,subprocess,sys,tempfile,time,uuid
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parent;PROJECT=HERE.parents[2];B=HERE/'build/library-tests'
sys.path.insert(0,str(ROOT));from run_probe import QMP
sys.path.insert(0,str(ROOT/'prototypes/tcg-transition'));from guest import template
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    a=PROJECT/'PC windows mobile 6 Files/Roms and files/pocket pc/Deviceemulation/0409/PPC_USA.BIN'
    b=PROJECT/'PC windows mobile 6 Files/Roms and files/pocket pc/Deviceemulation/0409/PPC_USA_GSM_QVGA_VR.BIN'
    source=ROOT/'results/runs/20261010T120116Z-55e43657366b/private/ram-fmd.bin'
    originals={str(p):sha(p) for p in (a,b,source)}
    owned=Path(tempfile.mkdtemp(prefix='guest-',dir=B));roms=owned/'Roms';data=owned/'data';card=owned/'storage';runtime=owned/'runtime'
    for folder in (roms,data,card,runtime):folder.mkdir()
    saves=[]
    for name,rom in [('OS_A.BIN',a),('OS_B.BIN',b)]:
        shutil.copyfile(rom,roms/name);folder=data/name;folder.mkdir();save=folder/'ram-fmd.bin';saves.append(save)
        if name=='OS_A.BIN':shutil.copyfile(source,save)
        else:
            with save.open('wb') as f:f.truncate(32*1024*1024)
    steps=[];indices,expected=template('today',(5,64,210,142))
    for number,name in enumerate(('OS_A.BIN','OS_B.BIN','OS_A.BIN')):
        other=saves[1 if name=='OS_A.BIN' else 0];untouched=sha(other);save=data/name/'ram-fmd.bin'
        sock=Path('/tmp')/('p2d-library-'+uuid.uuid4().hex+'.sock');frames=runtime/'frames.bin'
        with frames.open('wb') as f:f.truncate(64+1024*800*4)
        command=[str(HERE/'build/qemu-host'),'-M',f'p2d-devemu,storage={save},storage-lock={runtime}/engine-storage.lock,shared-folder={card},frame-file={frames}', '-bios',str(roms/name),'-accel','tcg,thread=single','-display','none','-serial','none','-monitor','none','-S','-qmp',f'unix:{sock},server=on,wait=off']
        q=p=None;start=time.monotonic();today=False;published=False;dimensions=None
        with (owned/f'{number}-{name}.log').open('wb') as log:
            try:
                p=subprocess.Popen(command,stdout=log,stderr=log);q=QMP(sock,p);q.request('cont')
                while time.monotonic()-start<25:
                    if frames.exists():
                        with frames.open('rb') as f:
                            fcntl.lockf(f.fileno(),fcntl.LOCK_SH);raw=f.read();fcntl.lockf(f.fileno(),fcntl.LOCK_UN)
                        if raw[:4]==b'P2DF':
                            dimensions=struct.unpack_from('<II',raw,8);sequence=struct.unpack_from('<Q',raw,24)[0]
                            published=sequence>=3
                            if dimensions==(240,320):today=sum(raw[64+i*4:67+i*4]!=v for i,v in zip(indices,expected))<=len(indices)*.01
                            if today:break
                    time.sleep(.25)
                assert published,'Guest never published real boot frames'
                q.request('screendump',{'filename':str(owned/f'{number}-{name}.ppm'),'format':'ppm'})
                q.request('stop')
                with save.open('r+b') as f:os.fsync(f.fileno())
                q.request('quit');p.wait(timeout=5);assert p.returncode==0
                assert sha(other)==untouched,'Other ROM data was modified'
                if name=='OS_A.BIN':assert today,'Prepared baseline ROM did not boot to Today'
                steps.append(dict(filename=name,today=today,boot_frames=published,dimensions=dimensions,seconds=time.monotonic()-start,other_save_unchanged=True,normal_exit=True))
                print(json.dumps(steps[-1]),flush=True)
            finally:
                if q:q.close()
                if p and p.poll() is None:p.terminate();p.wait(timeout=5)
                sock.unlink(missing_ok=True)
    assert all(sha(Path(path))==digest for path,digest in originals.items())
    (B/'guest-result.json').write_text(json.dumps(dict(scope='Copied whole OS on x86/WSL; not Android performance',owned_root=str(owned),originals_unchanged=True,steps=steps),indent=2)+'\n')
if __name__=='__main__':main()
