package com.samthedev.pocket2droid;
import android.app.*;
import android.content.*;
import android.os.*;
import android.graphics.*;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.lang.reflect.*;
import java.util.*;

public final class ButtonMappingUiTest extends Instrumentation {
 final List<String> failures=new ArrayList<>();int checks;String suite;
 static Object field(Object o,String n)throws Exception {Class<?> c=o.getClass();while(c!=null){try{Field f=c.getDeclaredField(n);f.setAccessible(true);return f.get(o);}catch(NoSuchFieldException e){c=c.getSuperclass();}}throw new NoSuchFieldException(n);}
 static void put(Object o,String n,Object v)throws Exception {Field f=o.getClass().getDeclaredField(n);f.setAccessible(true);f.set(o,v);}
 static void invoke(Object o,String n)throws Exception {Method m=o.getClass().getDeclaredMethod(n);m.setAccessible(true);m.invoke(o);}
 void check(boolean v,String n){checks++;if(!v){failures.add(n);android.util.Log.e("MappingTest",n);}}
 void main(Runnable r){Throwable[] e={null};runOnMainSync(()->{try{r.run();}catch(Throwable t){e[0]=t;}});waitForIdleSync();if(e[0]!=null)throw new RuntimeException(e[0]);}
 Activity launch(Class<?> c){return startActivitySync(new Intent(getTargetContext(),c).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));}
 void shell(String s)throws Exception {try(ParcelFileDescriptor p=getUiAutomation().executeShellCommand(s);InputStream in=new FileInputStream(p.getFileDescriptor())){byte[] b=new byte[1024];while(in.read(b)>=0){}}}
 static final Map<String,Long> pressTimes=new HashMap<>();
 static void key(Activity a,int device,int code,boolean down,int repeat){String k=device+":"+code;long now=SystemClock.uptimeMillis();if(down&&repeat==0)pressTimes.put(k,now);key(a,device,code,down,repeat,pressTimes.getOrDefault(k,now));}
 static void key(Activity a,int device,int code,boolean down,int repeat,long downTime){a.dispatchKeyEvent(new KeyEvent(downTime,SystemClock.uptimeMillis(),down?KeyEvent.ACTION_DOWN:KeyEvent.ACTION_UP,code,repeat,0,device,0,0,code>=96&&code<=110?InputDevice.SOURCE_GAMEPAD:InputDevice.SOURCE_KEYBOARD));}
 static AndroidMappingInput.Ranges ranges(){return (e,axis)->{if(axis==MotionEvent.AXIS_X||axis==MotionEvent.AXIS_Y||axis==MotionEvent.AXIS_RX||axis==MotionEvent.AXIS_RY||axis==MotionEvent.AXIS_HAT_X||axis==MotionEvent.AXIS_HAT_Y)return new AndroidMappingInput.Range(-1,1,0);if(axis==MotionEvent.AXIS_LTRIGGER||axis==MotionEvent.AXIS_BRAKE)return new AndroidMappingInput.Range(0,1,0);return null;};}
 static MotionEvent event(int device,float x,float trigger){MotionEvent.PointerProperties p=new MotionEvent.PointerProperties();p.id=0;p.toolType=MotionEvent.TOOL_TYPE_UNKNOWN;MotionEvent.PointerCoords c=new MotionEvent.PointerCoords();c.setAxisValue(MotionEvent.AXIS_X,x);c.setAxisValue(MotionEvent.AXIS_LTRIGGER,trigger);c.setAxisValue(MotionEvent.AXIS_BRAKE,trigger);long now=SystemClock.uptimeMillis();return MotionEvent.obtain(now,now,MotionEvent.ACTION_MOVE,1,new MotionEvent.PointerProperties[]{p},new MotionEvent.PointerCoords[]{c},0,0,1,1,device,0,InputDevice.SOURCE_JOYSTICK,0);}
 static void motion(Activity a,int device,float x,float trigger){MotionEvent e=event(device,x,trigger);a.onGenericMotionEvent(e);e.recycle();}
 static void tap(View v){v.performClick();}
 static void gesture(View v){long now=SystemClock.uptimeMillis();for(int action:new int[]{MotionEvent.ACTION_DOWN,MotionEvent.ACTION_UP}){MotionEvent e=MotionEvent.obtain(now,now,action,v.getWidth()/2f,v.getHeight()/2f,0);v.dispatchTouchEvent(e);e.recycle();}}
 static void touch(OnScreenControls v,ControlsLayout.Key k,boolean down){ControlsLayout.Rect r=new ControlsLayout(v.getWidth(),v.getHeight()).rect(k);long now=SystemClock.uptimeMillis();MotionEvent e=MotionEvent.obtain(now,now,down?MotionEvent.ACTION_DOWN:MotionEvent.ACTION_UP,(r.left+r.right)/2,(r.top+r.bottom)/2,0);v.dispatchTouchEvent(e);e.recycle();}
 static void texts(View v,List<String> result){if(v instanceof TextView)result.add(((TextView)v).getText().toString());if(v instanceof android.view.ViewGroup){ViewGroup g=(ViewGroup)v;for(int i=0;i<g.getChildCount();i++)texts(g.getChildAt(i),result);}}
 static PreferenceButtonMappings failedPreferences(Context base,String accepted){
  Map<String,Object> cache=new HashMap<>();cache.put(PreferenceButtonMappings.KEY,accepted);
  SharedPreferences prefs=(SharedPreferences)Proxy.newProxyInstance(SharedPreferences.class.getClassLoader(),new Class<?>[]{SharedPreferences.class},(p,m,args)->{
   if(m.getName().equals("getAll"))return new HashMap<>(cache);
   if(!m.getName().equals("edit"))throw new UnsupportedOperationException(m.getName());
   Map<String,Object> edits=new HashMap<>();Set<String> removed=new HashSet<>();
   return Proxy.newProxyInstance(SharedPreferences.Editor.class.getClassLoader(),new Class<?>[]{SharedPreferences.Editor.class},(e,method,a)->{
    if(method.getName().equals("putString")){edits.put((String)a[0],a[1]);return e;}
    if(method.getName().equals("remove")){removed.add((String)a[0]);return e;}
    if(method.getName().equals("commit")){for(String k:removed)cache.remove(k);cache.putAll(edits);return false;} // Android can update memory even when disk commit fails.
    throw new UnsupportedOperationException(method.getName());
   });
  });
  return new PreferenceButtonMappings(new ContextWrapper(base){@Override public SharedPreferences getSharedPreferences(String name,int mode){return prefs;}});
 }
 @Override public void onCreate(Bundle b){super.onCreate(b);suite=b.getString("suite","all");start();}
 private void uiChecks()throws Exception {
  AppSettingsActivity settings=(AppSettingsActivity)launch(AppSettingsActivity.class);waitForIdleSync();List<String> labels=new ArrayList<>();main(()->texts(settings.getWindow().getDecorView(),labels));check(labels.indexOf("Controls transparency")<labels.indexOf("Button Mapping")&&labels.indexOf("Button Mapping")<labels.indexOf("Vibration feedback"),"Settings order");main(settings::finish);
  getTargetContext().getSharedPreferences("settings",Context.MODE_PRIVATE).edit().remove(PreferenceButtonMappings.KEY).putInt("controls_transparency",100).commit();
  ButtonMappingActivity a=(ButtonMappingActivity)launch(ButtonMappingActivity.class);for(int i=0;i<60&&!a.hasWindowFocus();i++)Thread.sleep(50);waitForIdleSync();if(!a.hasWindowFocus())throw new AssertionError("Mapping window never focused");ButtonMappingView pad=(ButtonMappingView)field(a,"keypad");MappingCapture capture=(MappingCapture)field(a,"capture");TextView log=(TextView)field(a,"log");
  LinearLayout root=(LinearLayout)pad.getParent().getParent().getParent();ScrollView scroll=(ScrollView)pad.getParent().getParent();LinearLayout toolbar=(LinearLayout)root.getChildAt(0);
  WindowInsets originalInsets=root.getRootWindowInsets();
  main(()->{List<String> visible=new ArrayList<>();texts(root,visible);check(!visible.contains("Clear assignment")&&!visible.contains("Reset defaults"),"Standalone clear/reset actions removed");check(toolbar.getChildCount()==3&&toolbar.getChildAt(2) instanceof Button&&((Button)toolbar.getChildAt(2)).getText().toString().equals("Reset"),"Reset is in the top-right toolbar");
   root.dispatchApplyWindowInsets(new WindowInsets.Builder().setSystemWindowInsets(Insets.of(0,a.dp(24),0,a.dp(96))).build());
  });waitForIdleSync();
  main(()->{int safe=root.getHeight()-root.getPaddingTop()-root.getPaddingBottom();TextView current;try{current=(TextView)field(a,"current");}catch(Exception e){throw new RuntimeException(e);}check(scroll.getHeight()<=Math.max(0,safe-toolbar.getHeight()-current.getHeight()-a.dp(96)),"Keypad height excludes navigation and status insets");check(log.getHeight()>=a.dp(96),"Log space retained when navigation inset grows");scroll.setSmoothScrollingEnabled(false);scroll.fullScroll(View.FOCUS_DOWN);});waitForIdleSync();
  main(()->{Rect visible=new Rect();View hash=pad.target(GuestKey.HASH);int[] location=new int[2];root.getLocationOnScreen(location);check(hash.getGlobalVisibleRect(visible)&&visible.height()==hash.getHeight()&&visible.bottom<=location[1]+root.getHeight()-root.getPaddingBottom(),"Bottom keypad row fully scrolls above navigation bar: "+visible+" height="+hash.getHeight()+" scroll="+scroll.getScrollY());scroll.fullScroll(View.FOCUS_UP);root.dispatchApplyWindowInsets(originalInsets);root.requestApplyInsets();});waitForIdleSync();
  main(()->gesture(pad.target(GuestKey.TAB)));waitForIdleSync();check(capture.listening()&&capture.selected()==GuestKey.TAB,"Actual target touch gesture");
  main(()->{check(pad.getChildCount()==25,"25 accessible child targets");for(GuestKey k:GuestKey.mappingTargets()){View v=pad.target(k);check(v.getContentDescription().toString().startsWith(k.label)&&v.isClickable()&&v.getWidth()>=a.dp(48)&&v.getHeight()>=a.dp(48),"Accessible 48dp "+k);}
   check(pad.getAlpha()==1&&pad.getVisibility()==View.VISIBLE,"Mapping visible at 100% gameplay transparency");check(((android.graphics.drawable.ColorDrawable)pad.getBackground()).getColor()==a.BACKGROUND,"Keypad background matches system theme");tap(pad.target(GuestKey.TAB));check(log.getText().toString().endsWith("Press any key to assign Tab"),"Prompt text");key(a,1,96,true,1);check(capture.listening(),"Repeat rejected");key(a,1,96,false,0);key(a,1,96,true,0);check(log.getText().toString().endsWith("Tab mapped as Controller A"),"Confirmation text");check(PreferenceButtonMappings.load(a).resolve("key:96")==GuestKey.TAB,"Automatic persistent assignment");key(a,1,96,false,0);
   try{put(a,"input",new AndroidMappingInput((d,t,p,f)->capture.input(d,t,p,f),ranges()));}catch(Exception e){throw new RuntimeException(e);}
   motion(a,5,0,0);tap(pad.target(GuestKey.SPACE));motion(a,5,.64f,0);check(capture.listening(),"Axis threshold");motion(a,5,1,0);check(!capture.listening()&&PreferenceButtonMappings.load(a).resolve("stick:left:x:+")==GuestKey.SPACE,"Motion capture saves");
   tap(pad.target(GuestKey.HOME));motion(a,5,1,0);check(capture.listening(),"Held axis rejected");motion(a,5,0,0);motion(a,5,0,1);check(PreferenceButtonMappings.load(a).resolve("trigger:left")==GuestKey.HOME,"Trigger alias capture");
   motion(a,9,.50f,0);tap(pad.target(GuestKey.BACK));motion(a,9,.65f,0);check(capture.listening(),"Part-held axis must reach neutral before capture");motion(a,9,0,0);motion(a,9,.65f,0);check(!capture.listening()&&PreferenceButtonMappings.load(a).resolve("stick:left:x:+")==GuestKey.BACK,"Neutral then activation captures");
   long oldPress=SystemClock.uptimeMillis()-20;key(a,10,97,true,0,oldPress);a.onWindowFocusChanged(false);a.onWindowFocusChanged(true);tap(pad.target(GuestKey.BACK));key(a,10,97,true,1,oldPress);check(capture.listening(),"Focus return rejects held key repeat");key(a,10,97,true,0,SystemClock.uptimeMillis()+1);check(!capture.listening()&&PreferenceButtonMappings.load(a).resolve("key:97")==GuestKey.BACK,"New press captures after release delivered elsewhere");key(a,10,97,false,0,SystemClock.uptimeMillis()+1);
   try{ButtonMappingStore s=(ButtonMappingStore)field(a,"store");ButtonMappingStore.Persistence real=(ButtonMappingStore.Persistence)field(s,"persistence");ButtonBindings accepted=s.current();PreferenceButtonMappings failed=failedPreferences(a,accepted.serialize());put(s,"persistence",failed);tap(pad.target(GuestKey.CALL));key(a,11,108,true,0);key(a,11,108,false,0);check(capture.listening()&&log.getText().toString().endsWith("Could not save assignment. Previous mappings kept; try again."),"Failed commit cannot confirm assignment");check(s.current()==accepted,"Failed commit keeps accepted map");check(new ButtonMappingStore(failed).current().serialize().equals(accepted.serialize()),"Failed commit rolls back preference cache for next activity");put(s,"persistence",real);capture.cancel();}catch(Exception e){throw new RuntimeException(e);}
   tap(pad.target(GuestKey.TAB));a.onBackPressed();check(!capture.listening()&&!a.isFinishing(),"Back cancels first");tap(pad.target(GuestKey.HASH));a.onWindowFocusChanged(false);check(!capture.listening(),"Focus cancels");tap(pad.target(GuestKey.STAR));a.onPause();check(!capture.listening(),"Pause cancels");callActivityOnResume(a);
   android.view.ViewParent parent=pad.getParent().getParent();check(parent instanceof ScrollView&&((View)parent).getHeight()<pad.getHeight(),"Small-screen keypad scrolls while log stays above");
  });
  try(FileOutputStream f=new FileOutputStream(new File(a.getFilesDir(),"mapping-screen.png"))){getUiAutomation().takeScreenshot().compress(Bitmap.CompressFormat.PNG,100,f);}
  ActivityMonitor monitor=addMonitor(ButtonMappingActivity.class.getName(),null,false);main(a::recreate);ButtonMappingActivity restored=(ButtonMappingActivity)monitor.waitForActivityWithTimeout(3000);if(restored==null)throw new AssertionError("No recreation");waitForIdleSync();check(!((MappingCapture)field(restored,"capture")).listening(),"Recreation disarms");check(PreferenceButtonMappings.load(restored).resolve("key:96")==GuestKey.TAB,"Recreation retains saved assignments");removeMonitor(monitor);
  LinearLayout restoredRoot=(LinearLayout)((ButtonMappingView)field(restored,"keypad")).getParent().getParent().getParent();LinearLayout restoredBar=(LinearLayout)restoredRoot.getChildAt(0);
  if(restoredBar.getChildCount()==3){
   main(()->tap(restoredBar.getChildAt(2)));Thread.sleep(100);AlertDialog dialog=(AlertDialog)field(restored,"resetDialog");
   main(()->{check(PreferenceButtonMappings.load(restored).resolve("key:96")==GuestKey.TAB,"Reset waits for confirmation");dialog.getButton(AlertDialog.BUTTON_NEGATIVE).performClick();});Thread.sleep(100);
   main(()->check(PreferenceButtonMappings.load(restored).resolve("key:96")==GuestKey.TAB,"Reset cancel preserves mappings"));
   main(()->tap(restoredBar.getChildAt(2)));Thread.sleep(100);AlertDialog confirmed=(AlertDialog)field(restored,"resetDialog");
   main(()->confirmed.getButton(AlertDialog.BUTTON_POSITIVE).performClick());
   main(()->{check(PreferenceButtonMappings.load(restored).resolve("key:96")==null&&PreferenceButtonMappings.load(restored).resolve("stick:left:x:+")==null,"Toolbar Reset persists defaults");restored.finish();});
  }else main(restored::finish);
 }
 @Override public void onStart(){Bundle b=new Bundle();try{if(!suite.equals("runtime"))uiChecks();if(!suite.equals("ui"))ButtonMappingRuntimeTest.run(this);b.putString("stream",(failures.isEmpty()?"PASS ":"FAIL ")+checks+" Android mapping checks\n"+String.join("\n",failures)+"\n");b.putBoolean("passed",failures.isEmpty());}catch(Throwable e){b.putString("stream","ERROR "+android.util.Log.getStackTraceString(e));}finally{finish(b.getBoolean("passed")?Activity.RESULT_OK:Activity.RESULT_CANCELED,b);}}
}
