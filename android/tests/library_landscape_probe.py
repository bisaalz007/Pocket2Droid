"""Landscape session preview using an existing owned idle-ROM fixture."""
import json,time,struct
from library_pc_probe import shell,capture,node,tap,bounds,B,PKG,scroll_to

def main():
    assert shell('getprop ro.kernel.qemu').strip()=='1'
    shell(f'am start -W -n {PKG}/com.samthedev.pocket2droid.MainActivity');time.sleep(.3)
    tree=capture('pc-landscape-library')
    if any(n.get('content-desc')=='Emulated display' for n in tree.iter('node')):
        shell('input keyevent 4');tap(capture('pc-landscape-initial-exit'),'Exit');time.sleep(.5)
        tree=capture('pc-landscape-library')
    fixture=next(n.get('text') for n in tree.iter('node') if n.get('text','').startswith('UI_TEST_') and not n.get('text','').endswith('.BIN'))
    tap(tree,fixture,True);tap(capture('pc-landscape-popup'),'Settings');settings=scroll_to('Orientation');tap(settings,'Orientation');tap(capture('pc-orientation-options'),'Landscape')
    time.sleep(.3);tap(capture('pc-landscape-settings'),'Start');time.sleep(.7)
    shell('input keyevent 4');menu=capture('pc-landscape-menu')
    full=node(menu,'Fullscreen')
    # Android exposes a checked menu row through its child checkbox.
    parent=next(n for n in menu.iter('node') if n.get('resource-id')=='android:id/content' and full in list(n.iter('node')))
    checked=any(n.get('checked')=='true' for n in parent.iter('node'))
    if checked:tap(menu,'Fullscreen')
    else:shell('input keyevent 4')
    session=capture('pc-session-landscape');w,h=struct.unpack('>II',(B/'pc-session-landscape.png').read_bytes()[16:24])
    assert w>h,'Selected landscape orientation was not applied'
    assert bounds(node(session,'Emulated display'))[3]<=bounds(node(session,'TAB'))[1]
    shell('input keyevent 4');tap(capture('pc-landscape-exit-menu'),'Exit');time.sleep(.5)
    node(capture('pc-library-final'),'Add ROM')
    (B/'landscape-result.json').write_text(json.dumps({'pc_only':True,'landscape':[w,h],'normal_keys_do_not_cover_viewport':True,'normal_exit':True,'phone_modified':False},indent=2)+'\n')
    print('PASS landscape session layout and normal Exit',flush=True)

if __name__=='__main__':main()
