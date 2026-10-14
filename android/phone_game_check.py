"""Runtime checks confined to this task's disposable frontend and guest fixture."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import time
import uuid
import xml.etree.ElementTree as ET
import phone_smoke as p

RUN = p.HERE.parent / 'benchmarks/game-import/results/native-runs/20261007T213708Z-638c3f4415d3'

def nodes():
    p.owned(); p.focused()
    remote = '/data/local/tmp/p2d-frontend-smoke.xml'
    p.adb('shell', 'uiautomator', 'dump', remote)
    try:
        raw = p.adb('exec-out', 'cat', remote).stdout
        return list(ET.fromstring(raw).iter('node'))
    finally:
        p.adb('shell', 'rm', remote)

def guest_tap(x, y):
    surface = [n for n in nodes() if n.get('class') == 'android.view.SurfaceView']
    assert len(surface) == 1
    l, t, r, b = map(int, re.findall(r'\d+', surface[0].get('bounds')))
    scale = min((r-l)/240, (b-t)/320)
    px = round(l + ((r-l)-240*scale)/2 + x*scale)
    py = round(t + ((b-t)-320*scale)/2 + y*scale)
    p.adb('shell', 'input', 'tap', str(px), str(py))

def fixture():
    p.owned(); p.focused()
    state = json.loads((RUN / 'session-final.json').read_text())
    assert state['boot_kind'] == 'cold_zero_ram_fresh_ram_fmd' and state['normal_exit']
    assert state['rom_sha256'] == 'b6ca519070e84da0bf6886fb3bde606ce098a0cfaffff436b8faf46a9a580bf7'
    assert any(n.get('text', '').startswith('Stopped; retained TCG') for n in nodes()), 'Exit first'
    processes = p.adb('shell', 'ps', '-A', '-o', 'PID,PPID,ARGS').stdout.decode(errors='replace')
    assert not any(p.PACKAGE in line and 'libp2dengine.so' in line for line in processes.splitlines()), 'Engine still owns storage'
    source = RUN / 'ram-fmd-final.bin'
    assert source.stat().st_size == 32*1024*1024
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    staging = '/data/local/tmp/p2d-frontend-game-' + uuid.uuid4().hex[:12]
    p.adb('shell', 'mkdir', staging)
    try:
        p.adb('shell', 'chmod', '755', staging)
        p.adb('push', str(source), staging + '/fmd')
        p.adb('shell', 'chmod', '644', staging + '/fmd')
        p.adb('shell', 'run-as', p.PACKAGE, 'cp', staging + '/fmd', 'files/tcg-v1/ram-fmd.bin')
        actual = p.adb('shell', 'run-as', p.PACKAGE, 'sha256sum', 'files/tcg-v1/ram-fmd.bin').stdout.decode().split()[0]
        assert actual == digest
    finally:
        p.adb('shell', 'rm', '-f', staging + '/fmd')
        p.adb('shell', 'rmdir', staging)
    (p.OUT / 'game-fixture.json').write_text(json.dumps({'source': str(source), 'sha256': digest, 'provenance': state,
        'target_package': p.PACKAGE, 'original_user_data_accessed': False}, indent=2))
    print('Verified fresh native-test game fixture:', digest)
    p.tap('START')

def counter_cost():
    p.owned(); p.focused()
    pid = p.adb('shell', 'pidof', p.PACKAGE).stdout.decode().strip()
    assert pid.isdigit()
    hz = int(p.adb('shell', 'getconf', 'CLK_TCK').stdout.decode())
    def ticks():
        raw = p.adb('exec-out', 'run-as', p.PACKAGE, 'cat', '/proc/'+pid+'/task/'+pid+'/stat').stdout.decode()
        fields = raw.rsplit(')', 1)[1].split()
        return int(fields[11]) + int(fields[12])
    results = []
    for enabled in [True, False]:
        switches = [n for n in nodes() if n.get('text') == 'FPS counter']
        assert len(switches) == 1
        checked = switches[0].get('checked') == 'true'
        if checked != enabled: p.tap('FPS counter')
        time.sleep(.6)
        p.adb('shell', 'dumpsys', 'gfxinfo', p.PACKAGE, 'reset')
        before = ticks(); began = time.monotonic(); time.sleep(8)
        after = ticks(); elapsed = time.monotonic()-began
        graphics = p.adb('shell', 'dumpsys', 'gfxinfo', p.PACKAGE, 'framestats').stdout
        label = 'counter-on' if enabled else 'counter-off'
        (p.OUT/(label+'-gfxinfo.txt')).write_bytes(graphics)
        p.capture(label)
        results.append({'counter_enabled': enabled, 'wall_seconds': elapsed, 'main_thread_ticks': after-before,
                        'main_thread_cpu_seconds': (after-before)/hz, 'clock_hz': hz})
    p.tap('FPS counter')
    report = {'windows': results, 'scope': 'UI main-thread cost on real ART; sequential same-running-game windows, not a matched gameplay speedup benchmark',
              'quantization_seconds': 1/hz, 'original_user_data_accessed': False}
    (p.OUT/'counter-ui-cost.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['fixture', 'guest-tap', 'counter-cost'])
    ap.add_argument('coordinates', nargs='*', type=int)
    args = ap.parse_args()
    if args.action == 'fixture': fixture()
    elif args.action == 'counter-cost': counter_cost()
    else:
        assert len(args.coordinates) == 2
        guest_tap(*args.coordinates)
