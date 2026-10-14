"""System theme, popup, compact footer and live-session configuration checks."""
import json,re,time
from library_pc_probe import shell,capture,node,tap,bounds,B,PKG,scroll_to,snapshot
def main():
 assert shell('getprop ro.kernel.qemu').strip()=='1'
 shell(f'am start -W -n {PKG}/com.samthedev.pocket2droid.MainActivity');time.sleep(.4)
 current=snapshot()
 if any(n.get('content-desc')=='Emulated display' for n in current.iter('node')):
  shell('input keyevent 4');tap(snapshot(),'Exit');time.sleep(.5)
 original=shell('cmd uimode night').strip();checks=[]
 try:
  for mode in ('yes','no'):
   shell('cmd uimode night '+mode);time.sleep(.4)
   shell(f'am start -W -n {PKG}/com.samthedev.pocket2droid.MainActivity');time.sleep(.4)
   tree=capture('pc-theme-'+mode+'-library');assert not any(n.get('text')=='ROM library' for n in tree.iter('node'))
   hint=node(tree,'Tap to start · Hold for options');a,b,c,d=bounds(hint);assert d-b<=28,'Footer is not compact'
   fixture=next(n.get('text') for n in tree.iter('node') if n.get('text','').startswith('UI_TEST_') and not n.get('text','').endswith('.BIN'))
   tap(tree,fixture,True);popup=capture('pc-theme-'+mode+'-popup');tap(popup,'Settings')
   settings=capture('pc-theme-'+mode+'-settings');tap(settings,'Guest resolution');dialog=capture('pc-theme-'+mode+'-resolution');node(dialog,'VGA (480×640)');tap(dialog,'Close');shell('input keyevent 4')
   tap(snapshot(),'App settings');app=capture('pc-theme-'+mode+'-app-settings');node(app,'Enable sound');node(app,'Default storagecard Folder');shell('input keyevent 4')
   checks.append(dict(mode=mode,library=True,popup=True,settings=True,dialog=True,compact_footer=True))
  # Theme changes in a running guest must not recreate its Activity or lose input.
  tree=snapshot();fixture=next(n.get('text') for n in tree.iter('node') if n.get('text','').startswith('UI_TEST_') and not n.get('text','').endswith('.BIN'))
  tap(tree,fixture);time.sleep(1);before=shell('dumpsys activity top');ident=re.findall(r'context: com\.samsixx\.wm6android\.EmulatorActivity@([0-9a-f]+)',before)
  (B/'theme-activity-before.txt').write_text(before)
  shell('cmd uimode night yes');time.sleep(.5);after=shell('dumpsys activity top');(B/'theme-activity-after.txt').write_text(after)
  assert ident and re.findall(r'context: com\.samsixx\.wm6android\.EmulatorActivity@([0-9a-f]+)',after)==ident,'Theme change recreated the live session'
  session=capture('pc-theme-live-session');assert not any('Sound enabled' in n.get('text','') for n in session.iter('node'))
  shell('input keyevent 4');menu=capture('pc-theme-live-menu');tap(menu,'Exit');time.sleep(.5)
  (B/'theme-result.json').write_text(json.dumps(dict(checks=checks,live_activity_retained=True,normal_exit=True,phone_modified=False),indent=2)+'\n')
 finally:
  mode=next((m for m in ('auto','yes','no') if re.search(r'\b'+m+r'\b',original)), 'no');shell('cmd uimode night '+mode);time.sleep(.3)
 print('PASS system light/dark library/settings/dialog/popup; compact footer; live Activity retained; normal Exit',flush=True)
if __name__=='__main__':main()
