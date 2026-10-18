"""Automatic-launch gate on a disposable stock WM6 profile, no UI replay."""
from pathlib import Path
import argparse
import hashlib
import http.server
import json
import shutil
import subprocess
import sys
import time
import threading
import uuid

EXP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(EXP))
from run_probe import QMP
sys.path.insert(0, str(EXP/'prototypes/networking'))
from run_guest import capture, tap
from network_guest_probe import packets


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_case(binary, rom, helper, out, scenario, clone=None, virtual=False, local_http=False, screen_size=(240,320), settings_ui=True, initial_wait=None):
    allowed = (EXP/'android/build/network-setup').resolve()
    out = out.resolve()
    assert out.is_relative_to(allowed) and not out.exists()
    assert scenario in ('query-autorun', 'work-route-probe', 'remove-route-probe', 'policy-initial', 'inspect-reopen'), 'Unknown probe scenario'
    out.mkdir(parents=True)
    helper=helper.resolve()
    rom=rom.resolve();wm5=rom.open('rb').read(7)==b'B000FF\n'
    share = out/'private-card'
    share.mkdir()
    if not virtual:
        (share/'2577').mkdir()
        shutil.copy2(helper, share/'2577/autorun.exe')
    server = None
    thread = None
    if local_http:
        assert scenario == 'inspect-reopen'
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body=b'<html><body><h1>Pocket2Droid automatic Work setup works</h1></body></html>'
                self.send_response(200);self.send_header('Content-Length',str(len(body)))
                self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(body)
                (out/'http-request.txt').write_text(self.path,encoding='utf-8')
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    if scenario == 'inspect-reopen':
        url='http://10.0.2.2:'+str(server.server_port)+'/' if server else 'http://google.com/'
        (share/'browser.flag').write_bytes(url.encode('utf-16le'))
    if scenario in ('work-route-probe','remove-route-probe'):
        xml = '<wap-provisioningdoc><characteristic type="CM_ProxyEntries"><characteristic type="P2D-Work-Internet"><parm name="SrcId" value="{A1182988-0D73-439E-87AD-2A5B369F808B}"/><parm name="DestId" value="{436EF144-B4FB-4863-A041-8F905A62C572}"/><parm name="Proxy" value=""/><parm name="Type" value="0"/><parm name="Enable" value="1"/></characteristic></characteristic></wap-provisioningdoc>'
        if scenario == 'remove-route-probe':
            xml='<wap-provisioningdoc><characteristic type="CM_ProxyEntries"><nocharacteristic type="P2D-Work-Internet"/></characteristic></wap-provisioningdoc>'
        (share/'apply.xml').write_bytes(xml.encode('utf-16le'))
    marker = share/'preserve.txt'
    marker.write_text('private-'+uuid.uuid4().hex)
    storage = out/'private-fmd.bin'
    with storage.open('xb') as f:
        f.truncate(33554432)
    if clone:
        prior=json.loads((clone/'result.json').read_text())
        assert prior['rom_sha256']==sha(rom) and prior['private_profile']
        shutil.copy2(clone/'private-fmd.bin',storage)
    retained=out/('wm5-sdram-'+sha(rom)+'.bin');ready=Path(str(retained)+'.ready')
    if wm5:
        if clone:
            shutil.copy2(clone/retained.name,retained);shutil.copy2(clone/ready.name,ready)
        else:
            with retained.open('xb') as f:f.truncate(128*1024*1024)
            ready.write_text('Pocket2Droid WM5 RAM 1\n'+retained.name+'\n'+str(128*1024*1024)+'\n')
    sock = Path('/tmp')/('p2d-setup-'+uuid.uuid4().hex+'.sock')
    option = lambda p: str(p).replace(',', ',,')
    machine='p2d-devemu,network=on,storage='+option(storage)+',shared-folder='+option(share)
    width,height=screen_size
    assert width>0 and height>0
    machine+=',screen-width='+str(width)+',screen-height='+str(height)
    if wm5:
        stat=retained.stat();machine+=',ram-path='+option(retained)+',ram-identity='+format(stat.st_dev,'x')+':'+format(stat.st_ino,'x')
    if virtual:machine+=',network-setup='+option(helper)
    cmd = [str(binary), '-M', machine,
           '-bios', str(rom), '-display', 'none', '-serial', 'none', '-monitor', 'none',
           '-qmp', 'unix:'+str(sock)+',server=on,wait=off', '-netdev', 'user,id=p2dnet,ipv6=off',
           '-net', 'nic,model=ne2k_pcmcia,netdev=p2dnet,macaddr=02:12:34:56:78:90']
    cmd += ['-object', 'filter-dump,id=setupdump,netdev=p2dnet,file='+option(out/'packets.pcap')]
    result = {'scenario': scenario, 'rom': str(rom), 'rom_sha256': sha(rom),
              'helper_sha256': sha(helper), 'binary_sha256': sha(binary), 'command': cmd,
              'private_profile': True, 'wm5':wm5,'network_settings_taps': 0,
              'screen_size':[width,height],'settings_ui':settings_ui,
              'initial_wait':initial_wait,
              'marker_sha256': sha(marker)}
    q = None
    with (out/'engine.log').open('w') as log:
        process = subprocess.Popen(cmd, stdout=log, stderr=log)
    try:
        q = QMP(sock, process)
        if scenario == 'policy-initial':
            time.sleep(initial_wait if initial_wait is not None else (55 if wm5 else 25))
        else:
            deadline = time.monotonic()+65
            while time.monotonic() < deadline:
                if (share/'p2d-network-query.txt').exists():
                    time.sleep(12 if scenario in ('work-route-probe','remove-route-probe','inspect-reopen') else 2)
                    break
                if process.poll() is not None:
                    raise RuntimeError('Guest exited before query')
                time.sleep(1)
        capture(q, out, 'autorun-desktop')
        if settings_ui and scenario in ('work-route-probe','policy-initial','inspect-reopen'):
            for x,y in [(28,12),(43,190),(130,285),(36,112)]:
                tap(q,x,y)
            capture(q,out,'work-selection')
        result['automatic_query_output'] = (share/'p2d-network-query.txt').exists()
        if result['automatic_query_output']:
            shutil.copy2(share/'p2d-network-query.txt', out/'query-response.bin')
        result['network_info'] = q.request('human-monitor-command', {'command-line': 'info network'})
    finally:
        if process.poll() is None:
            if q:
                q.request('quit')
            else:
                process.terminate()
            process.wait(timeout=10)
        if q:
            q.close()
        if server:
            server.shutdown();server.server_close();thread.join()
        sock.unlink(missing_ok=True)
        result.update(exit_code=process.returncode, rom_unchanged=sha(rom)==result['rom_sha256'],
                      marker_unchanged=sha(marker)==result['marker_sha256'])
        result.update(virtual_delivery=virtual,real_card_has_helper=(share/'2577').exists())
        events = packets(out/'packets.pcap') if (out/'packets.pcap').exists() else []
        (out/'packet-summary.json').write_text(json.dumps(events,indent=2)+'\n')
        result['positive_google_dns'] = any(e['kind']=='dns' and 'google' in e['name'] and e['response'] and e['rcode']==0 and e['answers']>0 for e in events)
        result['public_http_200'] = any(e['kind']=='http' and e['ports'][0]==80 and e['text'].startswith('HTTP/') and ' 200 ' in e['text'].split('\r\n')[0] for e in events)
        result['local_http_200'] = bool(server) and (out/'http-request.txt').exists() and any(e['kind']=='http' and e['text'].startswith('HTTP/') and ' 200 ' in e['text'].split('\r\n')[0] for e in events)
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--binary', type=Path, default=Path('/opt/pocket2droid-network-integration/host/qemu-system-arm'))
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--helper', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--scenario', default='query-autorun')
    p.add_argument('--clone',type=Path)
    p.add_argument('--virtual',action='store_true')
    p.add_argument('--local-http',action='store_true')
    p.add_argument('--size',default='240x320')
    p.add_argument('--no-settings-ui',action='store_true')
    p.add_argument('--initial-wait',type=float)
    a = p.parse_args()
    size=tuple(map(int,a.size.lower().split('x')))
    assert len(size)==2
    assert a.initial_wait is None or 0<a.initial_wait<=120
    print(json.dumps(run_case(a.binary, a.rom, a.helper, a.out, a.scenario,a.clone,a.virtual,a.local_http,size,not a.no_settings_ui,a.initial_wait), indent=2))
