"""Bounded small-screen preview on the owned PC Android emulator only."""
import json,re,time
from library_pc_probe import adb,shell,capture,node,bounds,B,PKG

def main():
    assert shell('getprop ro.kernel.qemu').strip()=='1'
    original_size=shell('wm size');original_density=shell('wm density')
    try:
        shell('wm size 240x320');shell('wm density 160');time.sleep(.5)
        shell(f'am start -W -n {PKG}/com.samsixx.pocket2droid.MainActivity');time.sleep(.5)
        tree=capture('pc-library-small')
        controls=[bounds(node(tree,n)) for n in ('Add ROM','Search ROMs','App settings')]
        assert all(0<=a<c<=240 and c-a>=48 and d-b>=48 for a,b,c,d in controls)
        assert all(controls[i][2]<=controls[i+1][0] for i in range(2))
        n=node(tree,'App settings');a,b,c,d=bounds(n);shell(f'input tap {(a+c)//2} {(b+d)//2}');time.sleep(.3)
        settings=capture('pc-app-settings-small');node(settings,'Back')
        shell('input keyevent 4');time.sleep(.3)
        (B/'layout-result.json').write_text(json.dumps({'pc_only':True,'viewport':[240,320],'toolbar_targets_48dp':True,'nonoverlap':True,'phone_modified':False},indent=2)+'\n')
    finally:
        size=re.search(r'Override size: (\d+x\d+)',original_size)
        density=re.search(r'Override density: (\d+)',original_density)
        shell('wm size '+(size.group(1) if size else 'reset'))
        shell('wm density '+(density.group(1) if density else 'reset'))
        time.sleep(.4)
        shell(f'am start -W -n {PKG}/com.samsixx.pocket2droid.MainActivity')
        capture('pc-library-final')
    print('PASS small-screen toolbar geometry; PC size/density restored',flush=True)

if __name__=='__main__':main()
