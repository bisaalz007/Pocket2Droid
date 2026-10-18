package com.samsixx.pocket2droid;

import android.app.*;
import android.content.*;
import android.os.*;
import android.provider.Settings;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.lang.reflect.*;
import java.util.*;
import java.util.concurrent.CopyOnWriteArrayList;

/** Real frontend windows on the owned PC emulator; no guest process or ROM data. */
public final class FrontendLifecycleTest extends Instrumentation {
    private final List<String> failures=new ArrayList<>();
    private int checks;
    private boolean granted;
    private static final class RestartProcess extends java.lang.Process {
        boolean live=true;
        public int exitValue(){if(live)throw new IllegalThreadStateException();return 0;}
        public int waitFor(){live=false;return 0;}
        public void destroy(){live=false;}
        public InputStream getInputStream(){return null;}
        public InputStream getErrorStream(){return null;}
        public OutputStream getOutputStream(){return null;}
    }
    private void restartFlow(EmulatorActivity session)throws Exception{
        try{EmulatorActivity.class.getDeclaredMethod("restart");}
        catch(NoSuchMethodException missing){check(false,"Restart implements save-before-reopen lifecycle");return;}
        Engine engine=(Engine)field(session,"engine");
        List<String> observations=new CopyOnWriteArrayList<>();
        File save=new File(session.getFilesDir(),"restart-owned-save.bin");
        RandomAccessFile handle=new RandomAccessFile(save,"rw");handle.setLength(1);handle.write(73);
        put(engine,"status",(Engine.Status)observations::add);put(engine,"storageHandle",handle);
        for(int attempt=0;attempt<2;attempt++){
            if(attempt==1)handle.setLength(StorageLayout.STORAGE_SIZE);
            put(engine,"process",new RestartProcess());
            main(()->{try{
                session.onBackPressed();PopupMenu popup=(PopupMenu)field(session,"popup");
                MenuItem restart=null;for(int i=0;i<popup.getMenu().size();i++)if(popup.getMenu().getItem(i).getTitle().equals("Restart"))restart=popup.getMenu().getItem(i);
                check(restart!=null&&restart.isEnabled(),"Live guest can select Restart");
                if(restart!=null)popup.getMenu().performIdentifierAction(restart.getItemId(),0);
                popup.dismiss();
            }catch(Exception e){throw new RuntimeException(e);}});
            for(int i=0;i<150&&(Boolean)field(session,"closing");i++)Thread.sleep(20);
            waitForIdleSync();check(!(Boolean)field(session,"closing"),"Restart completion restores menu availability");
            if(attempt==0){
                check(field(engine,"storageHandle")==handle,"Failed save keeps original storage handle");
                check(observations.stream().noneMatch(s->s.startsWith("Wait for")),"Failed save never attempts a fresh Start");
                check(!((RomBootState)field(session,"boot")).waiting(),"Failed save does not show a fresh boot");
                shell("input keyevent 4");waitForIdleSync();
            }else{
                int stopped=-1,start=-1;for(int i=0;i<observations.size();i++){String s=observations.get(i);if(s.startsWith("Stopped;"))stopped=i;if(s.startsWith("Wait for"))start=i;}
                // The test's SessionGuard owner intentionally blocks native Start.
                check(stopped>=0&&start>stopped,"Restart attempts Start only after successful storage close");
                check(field(session,"engine")==engine&&!session.isFinishing(),"Restart retains the same ROM screen and Engine");
                check(((RomBootState)field(session,"boot")).waiting(),"Restart waits for a fresh boot image");
            }
        }
        try(FileInputStream in=new FileInputStream(save)){check(in.read()==73,"Restart preserves owned save bytes");}
    }
    private static Object field(Object object,String name)throws Exception {
        Class<?> type=object.getClass();
        while(type!=null){try{Field f=type.getDeclaredField(name);f.setAccessible(true);return f.get(object);}
            catch(NoSuchFieldException missing){type=type.getSuperclass();}}
        throw new NoSuchFieldException(name);
    }
    private static void put(Object object,String name,Object value)throws Exception {
        Field f=object.getClass().getDeclaredField(name);f.setAccessible(true);f.set(object,value);
    }
    private static void invoke(Object object,String name)throws Exception {
        Method m=object.getClass().getDeclaredMethod(name);m.setAccessible(true);m.invoke(object);
    }
    private void check(boolean ok,String label){checks++;if(!ok)failures.add(label);}
    private void main(Runnable action){final Throwable[] failure={null};runOnMainSync(()->{try{action.run();}catch(Throwable e){failure[0]=e;}});waitForIdleSync();if(failure[0]!=null)throw new RuntimeException(failure[0]);}
    private void shell(String command)throws Exception {
        try(ParcelFileDescriptor p=getUiAutomation().executeShellCommand(command);
            InputStream in=new FileInputStream(p.getFileDescriptor())){byte[] b=new byte[1024];while(in.read(b)>=0){}}
    }
    private Activity launch(Class<?> type){return startActivitySync(new Intent(getTargetContext(),type).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));}
    private TextView label(View view,String value){
        if(view instanceof TextView&&value.equals(((TextView)view).getText().toString()))return (TextView)view;
        if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){TextView found=label(group.getChildAt(i),value);if(found!=null)return found;}}
        return null;
    }
    private void addMenu(MainActivity library)throws Exception {
        final PopupWindow[] popup={null};
        main(()->{try{((View)field(library,"addButton")).performClick();popup[0]=(PopupWindow)field(library,"addPopup");}
            catch(NoSuchFieldException missing){check(false,"Plus opens the two-option add popup");}
            catch(Exception failed){throw new RuntimeException(failed);}});
        if(popup[0]==null)return;
        Thread.sleep(120);waitForIdleSync();
        main(()->{View content=popup[0].getContentView();check(popup[0].isShowing(),"Add popup is displayed under the toolbar");
            check(label(content,"PPC Rom")!=null&&label(content,"File to StorageCard")!=null,"Popup offers both exact approved labels");
            check(content instanceof ViewGroup&&((ViewGroup)content).getChildCount()==3,"Popup contains two choices separated by one divider");
            TextView file=label(content,"File to StorageCard");android.text.Layout layout=file.getLayout();boolean fits=layout!=null&&layout.getHeight()<=file.getHeight();
            if(layout!=null)for(int line=0;line<layout.getLineCount();line++)fits&=layout.getLineWidth(line)<=file.getWidth()+1;
            check(fits,"StorageCard label fits the actual popup at the current font scale");});
        android.graphics.Bitmap screenshot=getUiAutomation().takeScreenshot();
        if(screenshot!=null){try(FileOutputStream image=new FileOutputStream(new File(library.getFilesDir(),"add-popup.png"))){screenshot.compress(android.graphics.Bitmap.CompressFormat.PNG,100,image);}screenshot.recycle();}
        main(()->{TextView file=label(popup[0].getContentView(),"File to StorageCard");if(file!=null)((View)file.getParent()).performClick();
            check(!popup[0].isShowing(),"Choosing an option dismisses the popup");
            try{check(!(Boolean)field(library,"picking"),"Active session blocks the file picker before starting a copy");}catch(Exception failed){throw new RuntimeException(failed);}});
        Thread.sleep(120);waitForIdleSync();shell("input keyevent 4");waitForIdleSync();
        main(()->{try{put(library,"picking",true);}catch(Exception failed){throw new RuntimeException(failed);}library.onActivityResult(11,Activity.RESULT_CANCELED,null);
            try{check(!(Boolean)field(library,"picking"),"Cancelled file selection clears picker state without a destination write");}catch(Exception failed){throw new RuntimeException(failed);}});
    }
    private void fixedStorageSettings()throws Exception {
        AppSettingsActivity settings=(AppSettingsActivity)launch(AppSettingsActivity.class);
        SharedPreferences preferences=settings.prefs();boolean hadDefault=preferences.contains("default_card");
        String original=preferences.getString("default_card",null);
        String legacy=new File(settings.getFilesDir(),"older-custom-card").getPath();
        try {
            main(()->{preferences.edit().putString("default_card",legacy).commit();
                try{invoke(settings,"render");}catch(Exception e){throw new RuntimeException(e);}
                View root=settings.getWindow().getDecorView();TextView title=label(root,"Default storagecard Folder");
                check(title!=null,"Default storagecard path remains visible");
                if(title!=null){ViewGroup row=(ViewGroup)title.getParent();
                    check(!row.isClickable()&&!row.isFocusable(),"Default storagecard row cannot open a picker");
                    File fixed=new File(StorageLayout.forContext(settings).root,"storagecard");
                    check(((TextView)row.getChildAt(1)).getText().toString().equals(fixed.getPath()),"Displayed default ignores a legacy custom preference");}
                check(label(root,"Used when adding a ROM. Existing ROMs keep their assigned storagecard folder.")==null,"Default-folder explanatory notice is removed");
                check(legacy.equals(preferences.getString("default_card",null)),"Legacy preference is retained without migrating files");
                if(granted){try{check(settings.repository().defaultCard.equals(new File(StorageLayout.forContext(settings).root,"storagecard")),"New ROM repository uses the fixed card despite a saved custom preference");}
                    catch(Exception e){throw new RuntimeException(e);}}
            });
            RomSettingsActivity rom=(RomSettingsActivity)launch(RomSettingsActivity.class);
            for(int i=0;i<40&&(Boolean)field(rom,"working");i++)Thread.sleep(50);
            waitForIdleSync();shell("input keyevent 4");Thread.sleep(150);waitForIdleSync();
            if(rom.isFinishing())throw new AssertionError("Synthetic ROM settings closed instead of dismissing its access/session error");
            main(()->{try{
                File card=new File(rom.getFilesDir(),"existing-custom-card");
                RomSettings old=RomSettings.defaults("Existing ROM",card);
                RomProfile profile=new RomProfile("never-read.BIN","pda_blue",new File(card,"rom"),new File(card,"save"),old,"NEW",null);
                put(rom,"profile",profile);invoke(rom,"render");View root=rom.getWindow().getDecorView();
                TextView title=label(root,"storagecard");check(title!=null,"Existing ROM card assignment remains visible");
                if(title!=null){ViewGroup row=(ViewGroup)title.getParent();
                    check(!row.isClickable()&&!row.isFocusable(),"Per-ROM storagecard row cannot open a picker");
                    check(((TextView)row.getChildAt(1)).getText().toString().equals(card.getPath()),"Existing custom assignment is displayed without silently redirecting it");}
                check(label(root,"Use a dedicated folder. The emulated OS can modify or delete files here; avoid personal folders.")==null,"Per-ROM folder warning is removed");
                check(((RomProfile)field(rom,"profile")).settings.card.equals(card),"Rendering locked settings preserves the existing card");rom.finish();
            }catch(Exception e){throw new RuntimeException(e);}});
        } finally {
            main(()->{SharedPreferences.Editor edit=preferences.edit();if(hadDefault)edit.putString("default_card",original);else edit.remove("default_card");edit.commit();settings.finish();});
        }
    }
    private void press(OnScreenControls controls,ControlsLayout.Key key,int action){
        ControlsLayout.Rect r=new ControlsLayout(controls.getWidth(),controls.getHeight()).rect(key);
        long now=SystemClock.uptimeMillis();
        MotionEvent event=MotionEvent.obtain(now,now,action,(r.left+r.right)/2,(r.top+r.bottom)/2,0);
        controls.dispatchTouchEvent(event);event.recycle();
    }
    private void multi(OnScreenControls controls,int action,ControlsLayout.Key... keys){
        MotionEvent.PointerProperties[] properties=new MotionEvent.PointerProperties[keys.length];
        MotionEvent.PointerCoords[] coordinates=new MotionEvent.PointerCoords[keys.length];
        ControlsLayout layout=new ControlsLayout(controls.getWidth(),controls.getHeight());
        for(int i=0;i<keys.length;i++){
            properties[i]=new MotionEvent.PointerProperties();properties[i].id=keys[i].ordinal();properties[i].toolType=MotionEvent.TOOL_TYPE_FINGER;
            coordinates[i]=new MotionEvent.PointerCoords();ControlsLayout.Rect r=layout.rect(keys[i]);
            coordinates[i].x=(r.left+r.right)/2;coordinates[i].y=(r.top+r.bottom)/2;coordinates[i].pressure=1;coordinates[i].size=1;
        }
        long now=SystemClock.uptimeMillis();MotionEvent event=MotionEvent.obtain(now,now,action,keys.length,properties,coordinates,0,0,1,1,0,0,InputDevice.SOURCE_TOUCHSCREEN,0);
        controls.dispatchTouchEvent(event);event.recycle();
    }
    private boolean held(OnScreenControls controls,ControlsLayout.Key key){
        try{return ((ControlsState)field(controls,"state")).held(key);}catch(Exception e){throw new RuntimeException(e);}
    }
    @Override public void onCreate(Bundle arguments){super.onCreate(arguments);granted="true".equals(arguments.getString("storage_granted"));start();}
    @Override public void onStart(){
        Bundle report=new Bundle();Object owner=new Object();
        try {
            // Prevent the library from scanning even when testing the granted return path.
            if(!SessionGuard.claim(owner,null))throw new AssertionError("Unexpected active test session");
            fixedStorageSettings();
            final int[] requests={0};
            addMonitor(new ActivityMonitor(){@Override public ActivityResult onStartActivity(Intent intent){
                if(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION.equals(intent.getAction())||Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION.equals(intent.getAction()))requests[0]++;
                return null;
            }});
            MainActivity library=(MainActivity)launch(MainActivity.class);
            Thread.sleep(450);waitForIdleSync();
            check(requests[0]==(granted?0:1),granted?"Granted storage access does not prompt at startup":"Missing access requests Android storage settings at startup");
            if(requests[0]>0){shell("input keyevent 4");Thread.sleep(300);waitForIdleSync();}
            check(requests[0]<=1,"Returning without permission does not immediately reopen settings");
            main(()->{library.onResume();library.onResume();});
            check(requests[0]<=1,"Repeated resume after refusal does not loop permission requests");
            ActivityMonitor recreated=addMonitor(MainActivity.class.getName(),null,false);
            main(library::recreate);
            MainActivity restored=(MainActivity)recreated.waitForActivityWithTimeout(3000);
            if(restored==null)throw new AssertionError("Library recreation not observed");
            waitForIdleSync();check(requests[0]<=1,"Recreation after refusal does not repeat the startup request");
            if(granted)addMenu(restored);
            main(restored::finish);removeMonitor(recreated);
            if(granted){report.putString("stream",(failures.isEmpty()?"PASS ":"FAIL ")+checks+" granted-storage Android lifecycle checks\n"+String.join("\n",failures)+"\n");report.putBoolean("passed",failures.isEmpty());return;}
            // Storage denial also prevents EmulatorActivity.onCreate from touching any ROM folder.
            EmulatorActivity session=(EmulatorActivity)launch(EmulatorActivity.class);
            for(int i=0;i<30&&(Boolean)field(session,"working");i++)Thread.sleep(50);
            waitForIdleSync();
            // LibraryUi's expected missing-access dialog is separate from session errors.
            shell("input keyevent 4");Thread.sleep(200);waitForIdleSync();
            if(session.isFinishing())throw new AssertionError("Synthetic session closed instead of dismissing its access error");
            main(()->{try {
                AlertDialog dialog=(AlertDialog)field(session,"errorDialog");if(dialog!=null)dialog.dismiss();
                File base=new File(session.getFilesDir(),"synthetic-controls");
                RomSettings settings=RomSettings.defaults("Synthetic frontend",base);
                RomProfile profile=new RomProfile("never-read.BIN","pda_blue",new File(base,"rom"),new File(base,"save"),settings,"new",null);
                session.prefs().edit().remove("controls_transparency").putBoolean("fps_enabled",false).commit();
                check(session.controlsTransparency()==50,"Fresh controls use 50% transparency");
                session.prefs().edit().putInt("controls_transparency",27).commit();
                check(session.controlsTransparency()==27,"Explicit transparency preference is preserved");
                put(session,"profile",profile);put(session,"engine",new Engine(session,s->{},new StorageLayout(null,base)));
                invoke(session,"build");
            }catch(Exception e){throw new RuntimeException(e);}});
            Thread.sleep(250);waitForIdleSync();
            OnScreenControls controls=(OnScreenControls)field(session,"keys");
            main(()->{press(controls,ControlsLayout.Key.UP,MotionEvent.ACTION_DOWN);check(held(controls,ControlsLayout.Key.UP),"Controls respond before opening menu");});
            for(int mode=0;mode<2;mode++){
                final int opening=mode;
                main(()->{try{
                    if(opening==0)((LinearLayout)field(session,"toolbar")).getChildAt(1).performClick();else session.onBackPressed();
                    Menu sessionMenu=((PopupMenu)field(session,"popup")).getMenu();
                    int restartAt=-1,exitAt=-1;
                    for(int item=0;item<sessionMenu.size();item++){
                        String title=sessionMenu.getItem(item).getTitle().toString();
                        if(title.equals("Restart"))restartAt=item;
                        if(title.equals("Exit"))exitAt=item;
                    }
                    check(restartAt>=0&&restartAt+1==exitAt,"Restart appears immediately above Exit: "+opening);
                    if(restartAt>=0)check(!sessionMenu.getItem(restartAt).isEnabled(),"Restart is disabled without a live guest: "+opening);
                    check(!held(controls,ControlsLayout.Key.UP),"Opening menu releases held key: "+opening);
                    press(controls,ControlsLayout.Key.UP,MotionEvent.ACTION_DOWN);
                    check(!held(controls,ControlsLayout.Key.UP),"Menu blocks guest controls: "+opening);
                }catch(Exception e){throw new RuntimeException(e);}});
                Thread.sleep(150);waitForIdleSync();
                main(()->{try{((PopupMenu)field(session,"popup")).dismiss();}catch(Exception e){throw new RuntimeException(e);}});
                Thread.sleep(250);waitForIdleSync();
                main(()->{press(controls,ControlsLayout.Key.UP,MotionEvent.ACTION_DOWN);
                    check(held(controls,ControlsLayout.Key.UP),"Controls recover after menu dismissal: "+opening);
                    press(controls,ControlsLayout.Key.UP,MotionEvent.ACTION_UP);
                    check(!held(controls,ControlsLayout.Key.UP),"Recovered key releases: "+opening);});
            }
            main(()->{session.onWindowFocusChanged(false);
                // Focus loss must release old keys, not leave a cached disabled flag.
                // This delivered event uses the real window's current focus state.
                check(session.hasWindowFocus(),"Synthetic window has focus before delivered-event recovery");
                press(controls,ControlsLayout.Key.UP,MotionEvent.ACTION_DOWN);
                check(held(controls,ControlsLayout.Key.UP),"Delivered touch recovers after input release without a second focus callback");
                controls.release();});
            main(()->{
                multi(controls,MotionEvent.ACTION_DOWN,ControlsLayout.Key.UP);
                multi(controls,MotionEvent.ACTION_POINTER_DOWN|(1<<8),ControlsLayout.Key.UP,ControlsLayout.Key.SELECT);
                multi(controls,MotionEvent.ACTION_POINTER_DOWN|(2<<8),ControlsLayout.Key.UP,ControlsLayout.Key.SELECT,ControlsLayout.Key.SOFT_RIGHT);
                check(held(controls,ControlsLayout.Key.UP)&&held(controls,ControlsLayout.Key.SELECT)&&held(controls,ControlsLayout.Key.SOFT_RIGHT),"Three real MotionEvent pointers remain held after menu recovery");
                multi(controls,MotionEvent.ACTION_POINTER_UP|(1<<8),ControlsLayout.Key.UP,ControlsLayout.Key.SELECT,ControlsLayout.Key.SOFT_RIGHT);
                check(held(controls,ControlsLayout.Key.UP)&&!held(controls,ControlsLayout.Key.SELECT)&&held(controls,ControlsLayout.Key.SOFT_RIGHT),"Releasing the middle pointer preserves the other two keys");
                multi(controls,MotionEvent.ACTION_POINTER_UP|(1<<8),ControlsLayout.Key.UP,ControlsLayout.Key.SOFT_RIGHT);
                multi(controls,MotionEvent.ACTION_UP,ControlsLayout.Key.UP);
                check(!held(controls,ControlsLayout.Key.UP)&&!held(controls,ControlsLayout.Key.SOFT_RIGHT),"Final pointer releases clear recovered multi-key holds");
            });
            main(()->{press(controls,ControlsLayout.Key.SELECT,MotionEvent.ACTION_DOWN);session.onPause();
                check(!held(controls,ControlsLayout.Key.SELECT),"Pause releases controls");
                press(controls,ControlsLayout.Key.SELECT,MotionEvent.ACTION_DOWN);
                check(!held(controls,ControlsLayout.Key.SELECT),"Paused controls cannot accept keys");session.onResume();});
            main(()->{press(controls,ControlsLayout.Key.SELECT,MotionEvent.ACTION_DOWN);
                check(held(controls,ControlsLayout.Key.SELECT),"Resume restores controls");controls.release();});
            restartFlow(session);
            main(session::finish);
            report.putString("stream",(failures.isEmpty()?"PASS ":"FAIL ")+checks+" real Android frontend lifecycle checks\n"+String.join("\n",failures)+"\n");
            report.putBoolean("passed",failures.isEmpty());
        }catch(Throwable failure){report.putString("stream","ERROR "+android.util.Log.getStackTraceString(failure));report.putBoolean("passed",false);}
        finally{SessionGuard.release(owner);finish(report.getBoolean("passed")?Activity.RESULT_OK:Activity.RESULT_CANCELED,report);}
    }
}
