"""Copied full-OS display checks; original ROMs/data are never opened writable."""
from pathlib import Path
import hashlib,json,subprocess,sys,tempfile,time,uuid,struct,fcntl
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parent;PROJECT=HERE.parents[2];B=HERE/'build/library-tests'
sys.path.insert(0,str(ROOT));from run_probe import QMP
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 owned=Path(tempfile.mkdtemp(prefix='display-guest-',dir=B));results=[]
 folder=PROJECT/'PC windows mobile 6 Files/Roms and files/pocket pc/Deviceemulation/0409'
 cases=[('square-baseline','PPC_USA_GSM_VGA_SQUARE_VR.BIN',240,320),
        ('square-correct','PPC_USA_GSM_VGA_SQUARE_VR.BIN',480,480),
        ('qvga-landscape','PPC_USA.BIN',320,240)]
 for label,name,width,height in cases:
  rom=folder/name;original=sha(rom);save=owned/(label+'.save')
  with save.open('wb') as f:f.truncate(32*1024*1024)
  frames=owned/(label+'.frames')
  with frames.open('wb') as f:f.truncate(64+1024*800*4)
  sock=Path('/tmp')/('p2d-display-'+uuid.uuid4().hex);q=p=None
  with (owned/(label+'.log')).open('wb') as log:
   try:
    p=subprocess.Popen([str(HERE/'build/qemu-host'),'-M',f'p2d-devemu,storage={save},screen-width={width},screen-height={height},frame-file={frames}',
      '-bios',str(rom),'-accel','tcg,thread=single','-display','none','-monitor','none','-serial','none','-S','-qmp',f'unix:{sock},server=on,wait=off'],stdout=log,stderr=log)
    q=QMP(sock,p);q.request('cont');time.sleep(18)
    q.request('stop');q.request('screendump',{'filename':str(owned/(label+'.ppm')),'format':'ppm'})
    with frames.open('rb') as f:
     fcntl.lockf(f.fileno(),fcntl.LOCK_SH);header=f.read(64);fcntl.lockf(f.fileno(),fcntl.LOCK_UN)
    dimensions=struct.unpack_from('<II',header,8);assert dimensions==(width,height),(label,dimensions)
    q.request('quit');p.wait(timeout=5);assert p.returncode==0
    assert sha(rom)==original
    record=dict(case=label,dimensions=dimensions,normal_exit=True,original_rom_unchanged=True,rom_sha256=original,screenshot=str(owned/(label+'.ppm')))
    results.append(record);print(json.dumps(record),flush=True)
   finally:
    if q:q.close()
    if p and p.poll() is None:p.terminate();p.wait(timeout=5)
    sock.unlink(missing_ok=True)
 (B/'display-guest-result.json').write_text(json.dumps(dict(scope='Copied full OS on Linux; not phone FPS',owned_root=str(owned),cases=results),indent=2)+'\n')
if __name__=='__main__':main()
