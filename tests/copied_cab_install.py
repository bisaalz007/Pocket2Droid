"""Bounded full Windows Mobile CAB installation on an owned disposable copy.

The host-only fault shim forces Android10's missing NOREPLACE operation. No
phone data is accessed. UI control checks the exact recorded process owner.
"""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile,time,uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from run_probe import PROJECT,EXPERIMENT,QMP,create_run_dir,validate_inputs
FIXTURE=ROOT/'benchmarks/game-import/results/native-runs/20261007T213708Z-638c3f4415d3/ram-fmd-final.bin'
FIXTURE_HASH='8865961036fcb3f9033d2a1d7ff6f7731ed1f6521ce7cbe13d80d601f5a8eebd'
CAB=PROJECT/'DOCUMENTATION/PHONE_EVIDENCE/v644/game-files/rt_filao_efigs_retail_ppc.cab'
BINARY=Path('/opt/pocket2droid-tcg-build/host/qemu-system-arm')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
class Owner:
    def __init__(self,pid):self.pid=pid
    def poll(self):return None if Path(f'/proc/{self.pid}').exists() else 1
def launch(seconds):
    assert 20<=seconds<=600
    run=create_run_dir(EXPERIMENT/'results/runs');inputs=validate_inputs(PROJECT,run)
    assert sha(FIXTURE)==FIXTURE_HASH
    private=run/'private';private.mkdir();card=run/'sdcard';card.mkdir()
    shutil.copyfile(FIXTURE,private/'ram-fmd.bin');shutil.copyfile(CAB,card/'RagingThunder.cab')
    assert sha(private/'ram-fmd.bin')==FIXTURE_HASH and sha(card/'RagingThunder.cab')==sha(CAB)
    sock=Path('/tmp')/('p2d-cab-'+uuid.uuid4().hex+'.sock')
    cmd=[str(BINARY),'-M',f'p2d-devemu,storage={private}/ram-fmd.bin,storage-lock={private}/engine-storage.lock,shared-folder={card}',
         '-bios',inputs['rom_path'],'-accel','tcg,thread=single','-display','none','-serial','none','-monitor','none','-S',
         '-qmp',f'unix:{sock},server=on,wait=off','-d','unimp','-D',str(run/'mmio.log')]
    record={**inputs,'command':cmd,'qmp_path':str(sock),'engine_sha256':sha(BINARY),
            'original_storage':str(FIXTURE),'original_storage_sha256':FIXTURE_HASH,'original_cab_sha256':sha(CAB),
            'missing_noreplace_forced':True,'phone_data_accessed':False}
    process=None
    with tempfile.TemporaryDirectory(prefix='p2d-cab-fault-') as fault:
        lib=Path(fault)/'faults.so'
        subprocess.run(['cc','-shared','-fPIC',str(Path(__file__).with_name('move_faults.c')),'-ldl','-o',str(lib)],check=True)
        try:
            with (run/'engine.log').open('xb') as log:
                process=subprocess.Popen(cmd,stdout=log,stderr=log,env=dict(os.environ,
                    LD_PRELOAD=str(lib),P2D_TEST_MOVE_RENAME_FAIL='1'))
                record['pid']=process.pid
                q=QMP(sock,process);q.request('cont');q.close()
                (run/'session.json').write_text(json.dumps(record,indent=2)+'\n')
                print(json.dumps({'run':str(run),'pid':process.pid}),flush=True)
                try:process.wait(timeout=seconds)
                except subprocess.TimeoutExpired:
                    q=QMP(sock,process);q.request('quit');q.close();process.wait(timeout=8)
                record['normal_exit']=process.returncode==0
        finally:
            if process and process.poll() is None:process.terminate();process.wait(timeout=5)
            sock.unlink(missing_ok=True)
            record['original_inputs_unchanged']=(sha(FIXTURE)==FIXTURE_HASH and sha(CAB)==record['original_cab_sha256']
                and validate_inputs(PROJECT,run)['rom_sha256']==inputs['rom_sha256'])
            record['installed_files']={str(p.relative_to(card)):dict(bytes=p.stat().st_size,sha256=sha(p))
                for p in card.rglob('*') if p.is_file()}
            record['pending_records']=[p.name for p in private.glob('.guest-move-*.pending')]
            (run/'session-final.json').write_text(json.dumps(record,indent=2)+'\n')
            print(json.dumps({'normal_exit':record.get('normal_exit'),'original_inputs_unchanged':record['original_inputs_unchanged'],
                              'installed_file_count':len(record['installed_files']),'pending_records':record['pending_records']}),flush=True)
def control(a):
    run=a.run.resolve(strict=True);assert run.is_relative_to(EXPERIMENT/'results/runs')
    record=json.loads((run/'session.json').read_text());pid=record['pid']
    assert Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')[:-1]==[x.encode() for x in record['command']]
    q=QMP(Path(record['qmp_path']),Owner(pid))
    try:
        if a.action=='quit':q.request('quit');return
        if a.action=='tap':
            assert 0<=a.x<240 and 0<=a.y<320
            q.request('input-send-event',{'events':[
                {'type':'abs','data':{'axis':'x','value':round(a.x*32767/239)}},
                {'type':'abs','data':{'axis':'y','value':round(a.y*32767/319)}},
                {'type':'btn','data':{'button':'left','down':True}}]})
            time.sleep(.15)
            q.request('input-send-event',{'events':[{'type':'btn','data':{'button':'left','down':False}}]})
        if a.action=='key':
            assert a.key in ['up','down','left','right','tab','ret','esc','spc']
            for down in [True,False]:
                q.request('input-send-event',{'events':[{'type':'key','data':{'key':{'type':'qcode','data':a.key},'down':down}}]})
                time.sleep(.1)
        time.sleep(a.wait)
        ppm=run/(a.label+'.ppm');assert not ppm.exists()
        q.request('stop')
        try:q.request('screendump',{'filename':str(ppm),'format':'ppm'})
        finally:q.request('cont')
        with (run/'actions.jsonl').open('a') as f:f.write(json.dumps(vars(a),default=str)+'\n')
        print(str(ppm),flush=True)
    finally:q.close()
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['launch','capture','tap','key','quit'])
    p.add_argument('--run',type=Path);p.add_argument('--duration',type=int,default=600)
    p.add_argument('--label',default='capture');p.add_argument('--wait',type=float,default=.5)
    p.add_argument('--x',type=int);p.add_argument('--y',type=int);p.add_argument('--key')
    a=p.parse_args();assert 0<=a.wait<=30 and '/' not in a.label and '\\' not in a.label
    if a.action=='launch':launch(a.duration)
    else:assert a.run;control(a)
