package com.samthedev.pocket2droid;
import android.app.*;
import android.os.*;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.lang.reflect.*;
import java.util.*;

/** Actual Activity event delivery with a recording router, never a guest engine. */
final class ButtonMappingRuntimeTest {
 static void run(ButtonMappingUiTest t)throws Exception {
  EmulatorActivity a=(EmulatorActivity)t.launch(EmulatorActivity.class);Thread.sleep(300);t.shell("input keyevent 4");Thread.sleep(200);t.waitForIdleSync();
  List<String> events=new ArrayList<>();
  t.main(()->{try{
   File base=new File(a.getFilesDir(),"mapping-runtime-synthetic");RomSettings settings=RomSettings.defaults("Synthetic mapping",base);
   ButtonMappingUiTest.put(a,"profile",new RomProfile("never-read.BIN","pda_blue",new File(base,"rom"),new File(base,"save"),settings,"new",null));
   Engine engine=new Engine(a,s->{},new StorageLayout(null,base));ButtonMappingUiTest.put(a,"engine",engine);ButtonMappingUiTest.invoke(a,"build");
   ((GuestSurface)ButtonMappingUiTest.field(a,"display")).destroyed=true;engine.frameReady=true;
   ButtonBindings b=ButtonBindings.defaults().assign(GuestKey.TAB,"key:96").bindings.assign(GuestKey.SPACE,"key:61").bindings.assign(GuestKey.ENTER,"stick:left:x:+").bindings.assign(GuestKey.HOME,"trigger:left").bindings;
   ButtonMappingUiTest.put(a,"mappedKeys",new MappedInputState(b,(k,d)->events.add(k+":"+d)));
   ButtonMappingUiTest.put(a,"inputBindings",b);
   Method method=a.getClass().getDeclaredMethod("normalizedInput",int.class,String.class,boolean.class,boolean.class);method.setAccessible(true);
   ButtonMappingUiTest.put(a,"mappingInput",new AndroidMappingInput((d,s,p,f)->{try{method.invoke(a,d,s,p,f);}catch(Exception e){throw new RuntimeException(e);}},ButtonMappingUiTest.ranges()));
  }catch(Exception e){throw new RuntimeException(e);}});for(int i=0;i<60&&!a.hasWindowFocus();i++)Thread.sleep(50);t.waitForIdleSync();
  t.main(()->{try{t.check((Boolean)ButtonMappingUiTest.field(a,"foreground")&&a.hasWindowFocus()&&((Engine)ButtonMappingUiTest.field(a,"engine")).frameReady,"Synthetic runtime ready, with no frame reader or guest process");}catch(Exception e){throw new RuntimeException(e);}});
  t.main(()->{ButtonMappingUiTest.key(a,1,96,true,0);t.check(events.toString().equals("[TAB:true]"),"Controller A custom route");ButtonMappingUiTest.key(a,2,96,true,0);
   try{OnScreenControls controls=(OnScreenControls)ButtonMappingUiTest.field(a,"keys");ButtonMappingUiTest.touch(controls,ControlsLayout.Key.TAB,true);a.onInputDeviceRemoved(1);ButtonMappingUiTest.key(a,2,96,false,0);t.check(events.size()==1,"Disconnect preserves controller and touch owners");ButtonMappingUiTest.touch(controls,ControlsLayout.Key.TAB,false);t.check(events.toString().equals("[TAB:true, TAB:false]"),"Last owner releases");}catch(Exception e){throw new RuntimeException(e);}
   events.clear();ButtonMappingUiTest.key(a,1,61,true,0);ButtonMappingUiTest.key(a,1,61,false,0);t.check(events.toString().equals("[SPACE:true, SPACE:false]"),"Custom suppresses default Tab");
   events.clear();ButtonMappingUiTest.key(a,1,8,true,0);ButtonMappingUiTest.key(a,1,8,false,0);t.check(events.toString().equals("[DIGIT_1:true, DIGIT_1:false]"),"Keyboard digit default");
   events.clear();ButtonMappingUiTest.motion(a,5,0,0);ButtonMappingUiTest.motion(a,5,1,0);ButtonMappingUiTest.motion(a,5,0,0);t.check(events.toString().equals("[ENTER:true, ENTER:false]"),"Actual axis MotionEvents route and release");
   events.clear();ButtonMappingUiTest.key(a,1,96,true,0);a.onBackPressed();t.check(events.toString().equals("[TAB:true, TAB:false]"),"Menu releases mapped input");
  });Thread.sleep(100);
  t.main(()->{try{((PopupMenu)ButtonMappingUiTest.field(a,"popup")).dismiss();}catch(Exception e){throw new RuntimeException(e);}});Thread.sleep(180);
  t.main(()->{ButtonMappingUiTest.key(a,1,96,true,1);t.check(events.size()==2,"Held repeat cannot replay after popup");ButtonMappingUiTest.key(a,1,96,true,0);t.check(events.size()==3,"Fresh input works after popup despite lost release");ButtonMappingUiTest.key(a,1,96,false,0);
   events.clear();ButtonMappingUiTest.motion(a,6,0,0);ButtonMappingUiTest.key(a,6,104,true,0);ButtonMappingUiTest.motion(a,6,0,1);t.check(events.toString().equals("[HOME:true]"),"Dual trigger reports coalesce");a.onBackPressed();t.check(events.toString().equals("[HOME:true, HOME:false]"),"Menu releases dual trigger");
  });Thread.sleep(100);t.main(()->{try{((PopupMenu)ButtonMappingUiTest.field(a,"popup")).dismiss();}catch(Exception e){throw new RuntimeException(e);}});Thread.sleep(180);
  t.main(()->{ButtonMappingUiTest.key(a,6,104,true,1);t.check(events.size()==2,"Held dual trigger cannot replay");ButtonMappingUiTest.key(a,6,104,true,0);t.check(events.size()==3,"New trigger press recovers stale key and analog aliases");ButtonMappingUiTest.motion(a,6,0,1);t.check(events.size()==3,"New analog alias cannot duplicate make");ButtonMappingUiTest.key(a,6,104,false,0);ButtonMappingUiTest.motion(a,6,0,0);t.check(events.size()==4,"Recovered dual trigger releases once");
   events.clear();ButtonMappingUiTest.key(a,1,96,true,0);a.onPause();t.check(events.toString().equals("[TAB:true, TAB:false]"),"Pause releases mapping");a.onResume();ButtonMappingUiTest.key(a,1,96,true,2);t.check(events.size()==2,"Resume rejects held repeat");ButtonMappingUiTest.key(a,1,96,false,0);a.finish();});
 }
}
