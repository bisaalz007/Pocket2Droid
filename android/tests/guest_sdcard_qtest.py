"""Exercise the release guest-file bridge on fresh Android shared files only."""
from pathlib import Path
import argparse,hashlib,json,os,socket,struct,subprocess,time,uuid

PROJECT=Path(__file__).resolve().parents[4]
ANDROID=PROJECT/'EXPERIMENTS/qemu-devemu/android'
ADB=PROJECT/'tools/platform-tools/adb.exe'
SERIAL='8c000c756641873211d'
EVIDENCE=PROJECT/'DOCUMENTATION/PHONE_EVIDENCE/v658-a133'

def adb(*args,check=True):
    return subprocess.run([str(ADB),'-s',SERIAL,*map(str,args)],check=check,
                          stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')

class Protocol:
    def __init__(self,port,qmp=False):
        self.sock=socket.create_connection(('127.0.0.1',port),3);self.sock.settimeout(5)
        self.stream=self.sock.makefile('rwb');self.qmp=qmp
        if qmp:
            greeting=self.stream.readline()
            if not greeting:self.close();raise EOFError('Temporary QEMU not ready')
            assert 'QMP' in json.loads(greeting)
            self.request('qmp_capabilities')
    def request(self,command,args=None):
        raw=json.dumps({'execute':command,**({'arguments':args} if args else {})}) if self.qmp else command
        self.stream.write((raw+'\n').encode());self.stream.flush()
        while True:
            result=self.stream.readline()
            if not result:raise EOFError('Temporary QEMU closed')
            if self.qmp:
                obj=json.loads(result)
                if 'event' in obj:continue
                if 'error' in obj:raise RuntimeError(obj)
                return obj['return']
            response=result.decode().strip()
            if response.startswith('IRQ '):continue
            assert response.startswith('OK'),response
            return response.split()[1:]
    def close(self):self.stream.close();self.sock.close()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--fixed',action='store_true');args=parser.parse_args()
    tag=uuid.uuid4().hex;stage='/data/local/tmp/.p2d-guest-qtest-'+tag
    shared='/sdcard/.p2d-guest-qtest-'+tag
    result={'device':SERIAL,'scope':'Release native bridge, idle 4-byte BIOS, QTest, fresh owned shared directory; no app/user-data access'}
    forward=[];qmp=qtest=None;launcher=None
    adb('shell','mkdir',stage,shared)
    try:
        runtime=json.loads((ANDROID/'build/runtime.json').read_text())
        if not args.fixed:assert runtime==json.loads((PROJECT/'apk/6.58/runtime.json').read_text()),'Release engine identity changed'
        for name,record in runtime['files'].items():
            library=ANDROID/'build/runtime'/name
            assert hashlib.sha256(library.read_bytes()).hexdigest()==record['sha256'],'Runtime bytes changed'
            adb('push',library,stage+'/'+name)
        result['engine_sha256']=runtime['files']['libp2dengine.so']['sha256']
        idle=ANDROID/'build/compat-probe/qtest-idle.bin';idle.write_bytes(bytes.fromhex('feffffea'))
        adb('push',idle,stage+'/idle.bin');adb('shell','chmod','755',stage+'/libp2dengine.so')
        adb('shell','truncate','-s','33554432',stage+'/ram-fmd.bin')
        remote_base=20000+int(tag[:4],16)%20000
        for remote in (remote_base,remote_base+1):
            port=int(adb('forward','tcp:0','tcp:'+str(remote)).stdout.strip());forward.append(port)
        command=('cd '+stage+' && exec env LD_LIBRARY_PATH='+stage+' timeout 40 ./libp2dengine.so '
                 '-machine p2d-devemu,shared-folder='+shared+',storage='+stage+'/ram-fmd.bin,storage-lock='+stage+'/engine-storage.lock -bios '+stage+'/idle.bin '
                 '-accel tcg -S -name p2d-qtest-'+tag+' -display none -serial none -monitor none -qtest-log /dev/null '
                 '-qtest tcp:127.0.0.1:'+str(remote_base)+',server=on,wait=off '
                 '-qmp tcp:127.0.0.1:'+str(remote_base+1)+',server=on,wait=off >'+stage+'/engine.log 2>&1')
        launcher=subprocess.Popen([str(ADB),'-s',SERIAL,'shell',command],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        for _ in range(60):
            try:
                qmp=Protocol(forward[1],True)
                assert qmp.request('query-name')['name']=='p2d-qtest-'+tag,'Foreign QMP endpoint'
                qtest=Protocol(forward[0]);break
            except (OSError,EOFError):
                if qmp is not None:qmp.close();qmp=None
                time.sleep(.1)
        if qtest is None:
            raise RuntimeError(adb('shell','cat',stage+'/engine.log').stdout)
        pb=bytearray(1068);struct.pack_into('<H',pb,0,1068)
        def execute(code,name=None,second=None):
            nonlocal pb
            for value,off,length in ((name,36,34),(second,550,548)):
                if value is None:continue
                raw=value.encode('utf-16le');assert len(raw)<=512
                pb[off:off+512]=bytes(512);pb[off:off+len(raw)]=raw
                struct.pack_into('<H',pb,length,len(raw))
            qtest.request('write 0x30008000 1068 0x'+pb.hex())
            qtest.request('writel 0x500f4000 0x30008000');qtest.request('writel 0x500f4004 0x%x'%code)
            code=int(qtest.request('readl 0x500f400c')[0],16)
            pb[:]=bytes.fromhex(qtest.request('read 0x30008000 1068')[0].removeprefix('0x'))
            return code
        result['create']=execute(5,'\\source');assert result['create']==0
        struct.pack_into('<H',pb,30,2);assert execute(6,'\\source')==0
        payload=bytes(range(256))*300
        for position in range(0,len(payload),65536):
            chunk=payload[position:position+65536]
            qtest.request('write 0x30010000 %d 0x%s'%(len(chunk),chunk.hex()))
            struct.pack_into('<III',pb,16,len(chunk),position,0x30010000);assert execute(8)==0
        assert execute(0xa)==0
        struct.pack_into('<H',pb,28,32)
        result['set_normal_attributes']=execute(0xe,'\\source');assert result['set_normal_attributes']==0
        result['move_to_absent_target']=execute(0xf,'\\source','\\target')
        result['source_retained']=adb('shell','test','-f',shared+'/source',check=False).returncode==0
        result['target_created']=adb('shell','test','-e',shared+'/target',check=False).returncode==0
        if args.fixed:
            assert result['move_to_absent_target']==0 and not result['source_retained'] and result['target_created'],result
            assert adb('shell','sha256sum',shared+'/target').stdout.split()[0]==hashlib.sha256(payload).hexdigest()
            result['complete_target_bytes_verified']=len(payload)
            result['status']='PASS_ACTUAL_ANDROID_GUEST_FILE_MOVE_WITHOUT_REPLACEMENT'
        else:
            assert result['move_to_absent_target']==31 and result['source_retained'] and not result['target_created'],result
            result['status']='REPRODUCED_RELEASE_V658_GUEST_MOVEFILE_ERROR31_ON_SHARED_STORAGE'
        qmp.request('quit');qmp.close();qmp=None;qtest.close();qtest=None
        assert launcher.wait(timeout=5)==0,'Temporary engine exit failed'
        print(json.dumps(result,indent=2),flush=True)
        EVIDENCE.mkdir(exist_ok=True)
        (EVIDENCE/('guest-movefile-fixed.json' if args.fixed else 'guest-movefile-reproduction.json')).write_text(json.dumps(result,indent=2)+'\n')
    finally:
        EVIDENCE.mkdir(exist_ok=True)
        (EVIDENCE/'guest-qtest-engine.log').write_text(adb('shell','cat',stage+'/engine.log',check=False).stdout)
        if qmp is not None:
            try:qmp.request('quit')
            finally:qmp.close()
        if qtest is not None:qtest.close()
        if launcher is not None and launcher.poll() is None:
            launcher.wait(timeout=45) # Device timeout is40s, independent of controller.
        for port in forward:adb('forward','--remove','tcp:'+str(port),check=False)
        # Exact known owned paths only. No recursive device deletion.
        for name in ('source','target'):adb('shell','rm','-f',shared+'/'+name,check=False)
        adb('shell','rmdir',shared,check=False)
        runtime=json.loads((ANDROID/'build/runtime.json').read_text())
        for name in (*runtime['files'],'idle.bin','engine.log','ram-fmd.bin','engine-storage.lock','.guest-move.lock'):adb('shell','rm','-f',stage+'/'+name,check=False)
        adb('shell','rmdir',stage,check=False)

if __name__=='__main__':main()
