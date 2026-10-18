"""Disposable full-OS acceptance; owns only its fresh profile/process/socket/server.

Default CLI runs a bounded check. --serve keeps the disposable guest available
for exact QMP inspection; control subcommands take its explicit owner.json path.
Never points QEMU at the user's save or StorageCard directory.
"""
from pathlib import Path
import argparse, hashlib, http.server, json, os, shutil, socket, struct, subprocess, sys, threading, time, uuid
EXP=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(EXP));from run_probe import QMP
sys.path.insert(0,str(EXP/'prototypes/networking'));from run_guest import tap,capture
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def option(p):return str(p).replace(',',',,')
def packets(path):
    data=path.read_bytes();endian='<' if data[:4]==bytes.fromhex('d4c3b2a1') else '>';p=24;events=[]
    while p+16<=len(data):
        _,_,n,_=struct.unpack_from(endian+'IIII',data,p);p+=16;f=data[p:p+n];p+=n
        if len(f)<34 or f[12:14]!=b'\x08\x00':continue
        ip=f[14:14+int.from_bytes(f[16:18],'big')];h=(ip[0]&15)*4
        if len(ip)<h+8:continue
        a,b=struct.unpack_from('!HH',ip,h)
        if ip[9]==17:
            length=int.from_bytes(ip[h+4:h+6],'big');payload=ip[h+8:h+length]
            if {a,b}=={67,68} and len(payload)>=240:
                at=240;opts={}
                while at<len(payload):
                    code=payload[at];at+=1
                    if code==255:break
                    if not code:continue
                    if at>=len(payload):break
                    size=payload[at];at+=1;opts[code]=list(payload[at:at+size]);at+=size
                events.append({'kind':'dhcp','type':opts.get(53),'address':socket.inet_ntoa(payload[16:20])})
            if (a==53 or b==53) and len(payload)>=12:
                flags=int.from_bytes(payload[2:4],'big');at=12;labels=[]
                while at<len(payload) and 0<payload[at]<64:
                    size=payload[at];at+=1;labels.append(payload[at:at+size].decode('ascii','replace'));at+=size
                events.append({'kind':'dns','name':'.'.join(labels),'response':bool(flags&0x8000),'rcode':flags&15,'answers':int.from_bytes(payload[6:8],'big')})
        if ip[9]==6 and len(ip)>=h+20:
            payload=ip[h+(ip[h+12]>>4)*4:]
            if payload:events.append({'kind':'http','ports':[a,b],'text':payload[:500].decode('ascii','replace')})
    return events
def main():
    p=argparse.ArgumentParser();p.add_argument('--rom',type=Path);p.add_argument('--mode',choices=['online','offline']);p.add_argument('--out',type=Path);p.add_argument('--binary',default='/opt/pocket2droid-network-integration/host/qemu-system-arm');p.add_argument('--serve',action='store_true');p.add_argument('--clone',type=Path);p.add_argument('--control',type=Path);p.add_argument('--action',nargs='+');a=p.parse_args()
    if a.control:
        info=json.loads(a.control.read_text());owner=type('Owner',(),{'poll':lambda self: None})();q=QMP(Path(info['socket']),owner)
        try:
            if a.action[0]=='tap':tap(q,int(a.action[1]),int(a.action[2]));capture(q,Path(info['out']),a.action[3])
            elif a.action[0]=='capture':capture(q,Path(info['out']),a.action[1])
            elif a.action[0]=='quit':q.request('quit')
            elif a.action[0]=='hmp':print(q.request('human-monitor-command',{'command-line':' '.join(a.action[1:])}))
        finally:q.close()
        return
    assert a.rom and a.mode and a.out
    rom=a.rom.resolve();out=a.out.resolve();allowed=(EXP/'android/build/networking').resolve()
    assert out.is_relative_to(allowed) and not out.exists(),'Output must be a fresh owned networking evidence directory'
    out.mkdir(parents=True);rom_hash=sha(rom);wm5=rom.open('rb').read(7)==b'B000FF\n'
    save=out/'private-fmd.bin';ram=out/('wm5-sdram-'+rom_hash+'.bin');ready=out/(ram.name+'.ready')
    if a.clone:
        prior=json.loads((a.clone/'result.json').read_text());assert prior['rom_sha256']==rom_hash
        for name in ['private-fmd.bin']+([ram.name,ready.name] if wm5 else []):shutil.copy2(a.clone/name,out/name)
    else:
        with save.open('xb') as f:f.truncate(33554432)
        if wm5:
            with ram.open('xb') as f:f.truncate(128*1024*1024)
            ready.write_text('Pocket2Droid WM5 RAM 1\n'+ram.name+'\n'+str(128*1024*1024)+'\n')
    share=out/'private-shared-folder';share.mkdir()
    if a.clone:shutil.copytree(a.clone/'private-shared-folder',share,dirs_exist_ok=True)
    marker=share/'p2d-save-marker.txt'
    if not marker.exists():marker.write_text('owned-profile-'+uuid.uuid4().hex)
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            data=b'<html><body><h1>Pocket2Droid networking works</h1><p>Private PC test page.</p><p><a href="http://example.com/">Test public DNS and HTTP</a></p></body></html>'
            self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            with (out/'http-requests.log').open('a') as f:f.write(self.path+'\n')
        def log_message(self,*args):pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    (share/'Network test.htm').write_text('<html><head><meta http-equiv="refresh" content="0;url=http://10.0.2.2:'+str(server.server_port)+'/"></head><body>Network test</body></html>')
    (share/'Google test.htm').write_text('<html><head><meta http-equiv="refresh" content="0;url=http://google.com/"></head><body><a href="http://google.com/">Google test</a></body></html>') if 'google' in out.name else None
    sock=Path('/tmp')/('p2d-net-accept-'+uuid.uuid4().hex+'.sock')
    machine='p2d-devemu,storage='+option(save)+',shared-folder='+option(share)
    if wm5:
        stat=ram.stat();machine+=',ram-path='+option(ram)+',ram-identity='+format(stat.st_dev,'x')+':'+format(stat.st_ino,'x')
    cmd=[a.binary,'-M',machine+(',network=on' if a.mode=='online' else ''),'-bios',str(rom),'-display','none','-serial','none','-monitor','none','-qmp',f'unix:{sock},server=on,wait=off']
    if a.mode=='online':cmd+=['-netdev','user,id=p2dnet,ipv6=off','-net','nic,model=ne2k_pcmcia,netdev=p2dnet,macaddr=02:12:34:56:78:90','-object',f'filter-dump,id=acceptdump,netdev=p2dnet,file={option(out/"packets.pcap")}']
    else:cmd+=['-nic','none']
    record={'rom':str(rom),'rom_sha256':rom_hash,'wm5':wm5,'out':str(out),'socket':str(sock),'mode':a.mode,'binary':a.binary,'binary_sha256':sha(Path(a.binary)),'command':cmd,'private_profile':True,'marker_sha256':sha(marker)}
    process=None;q=None
    try:
        with (out/'engine.log').open('w') as log:process=subprocess.Popen(cmd,stdout=log,stderr=log)
        record['pid']=process.pid;(out/'owner.json').write_text(json.dumps(record,indent=2)+'\n')
        q=QMP(sock,process);time.sleep(55 if wm5 else 25);capture(q,out,'desktop')
        record['network_info']=q.request('human-monitor-command',{'command-line':'info network'})
        print(json.dumps(record),flush=True)
        if a.serve:
            q.close();q=None;process.wait(timeout=480)
        elif a.mode=='online':
            # Configure before opening IE so its modal error cannot consume taps.
            # WM5 differences remain visible compatibility evidence.
            for x,y in [(28,12),(43,190),(130,285),(36,112),(222,84),(60,97),(227,12),(227,12)]:tap(q,x,y)
            capture(q,out,'configured-desktop')
            for x,y in [(28,12),(45,170),(186 if wm5 else 36,112),(43,308),(68,147),(66,58)]:tap(q,x,y)
            time.sleep(8);capture(q,out,'local-result');tap(q,75,168);time.sleep(20 if wm5 else 8);capture(q,out,'public-result')
    finally:
        if process and process.poll() is None:
            try:
                if q is None:q=QMP(sock,process)
                q.request('stop');q.request('quit');process.wait(timeout=10)
            except Exception:process.terminate();process.wait(timeout=10)
        if q:q.close()
        server.shutdown();server.server_close();thread.join();sock.unlink(missing_ok=True)
        record.update(exit_code=process.returncode if process else None,rom_unchanged=sha(rom)==rom_hash,storage_size=save.stat().st_size,marker_unchanged=sha(marker)==record['marker_sha256'])
        events=packets(out/'packets.pcap') if (out/'packets.pcap').exists() else []
        (out/'packet-summary.json').write_text(json.dumps(events,indent=2)+'\n')
        record.update(dhcp_ack=any(e['kind']=='dhcp' and e['type']==[5] for e in events),positive_public_dns=any(e['kind']=='dns' and e['name']=='example.com' and e['response'] and e['rcode']==0 and e['answers']>0 for e in events),public_http=any(e['kind']=='http' and e['ports'][0]==80 and e['text'].startswith('HTTP/') and ' 200 ' in e['text'].split('\r\n')[0] for e in events),local_http=(out/'http-requests.log').exists())
        record['file_hashes']={f.name:sha(f) for f in [save]+([ram,ready] if wm5 else [])}
        (out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print('Acceptance result '+str(out/'result.json'),flush=True)
        assert record['rom_unchanged'] and record['marker_unchanged'] and record['exit_code']==0
if __name__=='__main__':main()
