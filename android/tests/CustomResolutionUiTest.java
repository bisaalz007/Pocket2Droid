package com.samsixx.pocket2droid;

import android.app.*;
import android.content.*;
import android.os.*;
import android.view.accessibility.AccessibilityNodeInfo;
import java.io.*;
import java.util.*;

/** Actual Android dialogs and profile writes on the isolated PC emulator. */
public final class CustomResolutionUiTest extends Instrumentation {
    private int checks;
    private RomSettingsActivity activity;
    private void check(boolean ok,String why){if(!ok)throw new AssertionError(why);checks++;}
    private AccessibilityNodeInfo find(AccessibilityNodeInfo node,String text){
        if(node==null)return null;
        boolean field=text.equals("Width (px)")||text.equals("Height (px)");
        if((!field||node.isEditable())&&(text.equalsIgnoreCase(String.valueOf(node.getText()))||text.equals(String.valueOf(node.getContentDescription()))))return node;
        for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo hit=find(node.getChild(i),text);if(hit!=null)return hit;}return null;
    }
    private AccessibilityNodeInfo node(String text)throws Exception{
        for(int i=0;i<60;i++){AccessibilityNodeInfo hit=find(getUiAutomation().getRootInActiveWindow(),text);if(hit!=null)return hit;Thread.sleep(40);}
        throw new AssertionError("Missing visible UI: "+text);
    }
    private void tap(String text)throws Exception{
        AccessibilityNodeInfo hit=node(text);while(hit!=null&&!hit.isClickable())hit=hit.getParent();
        check(hit!=null&&hit.performAction(AccessibilityNodeInfo.ACTION_CLICK),"Click real UI: "+text);waitForIdleSync();Thread.sleep(100);
    }
    private void enter(String label,String value)throws Exception{
        Bundle args=new Bundle();args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);
        check(node(label).performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args),"Edit real numeric field: "+label);waitForIdleSync();
    }
    private boolean scroll(AccessibilityNodeInfo root){
        if(root==null)return false;if(root.isScrollable()&&root.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD))return true;
        for(int i=0;i<root.getChildCount();i++)if(scroll(root.getChild(i)))return true;return false;
    }
    private void openCustom()throws Exception{
        tap("Guest resolution");
        for(int i=0;i<8&&find(getUiAutomation().getRootInActiveWindow(),"Custom…")==null;i++){scroll(getUiAutomation().getRootInActiveWindow());Thread.sleep(100);}
        tap("Custom…");node("Custom resolution");
    }
    private void screenshot(String name)throws Exception{
        android.graphics.Bitmap bitmap=getUiAutomation().takeScreenshot();check(bitmap!=null,"Capture actual custom UI");
        try(FileOutputStream out=new FileOutputStream(new File(activity.getFilesDir(),name))){bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG,100,out);}bitmap.recycle();
    }
    private void launch(String filename)throws Exception{
        activity=(RomSettingsActivity)startActivitySync(new Intent(getTargetContext(),RomSettingsActivity.class).putExtra("rom",filename).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));node("Guest resolution");
    }
    private void until(java.util.function.BooleanSupplier predicate)throws Exception{
        for(int i=0;i<200&&!predicate.getAsBoolean();i++)Thread.sleep(20);
        check(predicate.getAsBoolean(),"Frame is actually drawn after transport resize");
    }
    private void frame(String fixture,int w,int h,int sequence){
        Bundle values=new Bundle();values.putString("fixture",fixture);values.putInt("width",w);values.putInt("height",h);values.putLong("sequence",sequence);values.putInt("color",0xff123456);
        activity.getContentResolver().call(android.net.Uri.parse("content://"+activity.getPackageName()+".frames"),"frame",null,values);
    }
    private void frameGrowth()throws Exception{
        String fixture="custom-frame-growth-"+UUID.randomUUID();File base=new File(activity.getFilesDir(),fixture);check(base.mkdir(),"Create owned frame fixture");
        List<String> errors=new java.util.concurrent.CopyOnWriteArrayList<>();Engine engine=new Engine(activity,errors::add,new StorageLayout(null,base));
        GuestSurface[] screen={null};
        try{
            frame(fixture,240,320,1);engine.generation=1;engine.frameReady=true;
            runOnMainSync(()->{screen[0]=new GuestSurface(activity,engine,errors::add);screen[0].resumed=true;activity.setContentView(screen[0]);});
            until(()->screen[0].frameObserved);
            frame(fixture,1280,960,2);until(()->screen[0].guestWidth==1280&&screen[0].guestHeight==960);
            check(engine.generation==1&&errors.isEmpty(),"Larger frame remaps during the same session without display error");
            frame(fixture,960,1280,3);until(()->screen[0].guestWidth==960&&screen[0].guestHeight==1280);
            check(errors.isEmpty(),"Portrait frame above old height cap is consumed correctly");
            long before=engine.frames.length();engine.prepareFrames();
            check(engine.frames.length()==before,"Smaller-session initialization never truncates an active large-frame mapping");
            frame(fixture,320,240,4);until(()->screen[0].guestWidth==320&&screen[0].guestHeight==240);
            check(errors.isEmpty(),"Display keeps running after synchronized smaller-session initialization");
            Engine successor=new Engine(activity,errors::add,new StorageLayout(null,base));
            java.util.concurrent.CountDownLatch locked=new java.util.concurrent.CountDownLatch(1),release=new java.util.concurrent.CountDownLatch(1),done=new java.util.concurrent.CountDownLatch(1);
            java.util.concurrent.atomic.AtomicReference<Throwable> failure=new java.util.concurrent.atomic.AtomicReference<>();
            Thread reader=new Thread(()->{synchronized(engine.frameAccess){try(RandomAccessFile f=new RandomAccessFile(engine.frames,"r");java.nio.channels.FileLock lock=f.getChannel().lock(0,Long.MAX_VALUE,true)){locked.countDown();release.await();}catch(Throwable e){failure.set(e);locked.countDown();}}});
            Thread initializer=new Thread(()->{try{successor.prepareFrames();}catch(Throwable e){failure.set(e);}finally{done.countDown();}});
            try{
                reader.start();check(locked.await(2,java.util.concurrent.TimeUnit.SECONDS),"Previous Engine reader owns the shared frame lock");initializer.start();
                boolean early=done.await(150,java.util.concurrent.TimeUnit.MILLISECONDS);release.countDown();reader.join(2000);initializer.join(2000);
                check(!early&&failure.get()==null&&done.getCount()==0,"Next Engine waits for the previous Engine reader without overlapping-lock failure");
            }finally{release.countDown();successor.dispose();}
        }finally{if(screen[0]!=null){screen[0].destroyed=true;screen[0].resumed=false;}engine.dispose();}
    }
    @Override public void onCreate(Bundle args){super.onCreate(args);start();}
    @Override public void onStart(){Bundle result=new Bundle();try{
        StorageLayout paths=StorageLayout.forContext(getTargetContext());
        RomRepository repository=new RomRepository(paths.root,paths.runtime,new File(paths.root,"storagecard"));
        String filename="CUSTOM_UI_"+UUID.randomUUID().toString()+".BIN";
        RomProfile fixture=repository.importRom(new ByteArrayInputStream(new byte[]{1}),filename);
        launch(filename);openCustom();
        check(node("Width (px)").getText().toString().equals("240")&&node("Height (px)").getText().toString().equals("320"),"First edit starts from the current preset");
        enter("Width (px)","640");enter("Height (px)","360");tap("Cancel");
        check(repository.getProfile(filename).settings.resolution==RomSettings.GuestResolution.QVGA,"Cancel preserves the stored preset");
        openCustom();
        for(String invalid:new String[]{"","0","2147483648","9999999999999"}){
            enter("Width (px)",invalid);tap("Save");node("Custom resolution");
            check(repository.getProfile(filename).settings.resolution==RomSettings.GuestResolution.QVGA,"Invalid width keeps editor open without saving");
        }
        enter("Width (px)","640");enter("Height (px)","0");tap("Save");node("Custom resolution");
        check(repository.getProfile(filename).settings.resolution==RomSettings.GuestResolution.QVGA,"Invalid height does not save");
        enter("Height (px)","360");screenshot("custom-editor.png");tap("Save");node("Custom (640×360)  ▾");
        RomProfile saved=repository.getProfile(filename);
        check(saved.settings.startupSize(filename).width==640&&saved.settings.startupSize(filename).height==360,"Save writes actual custom dimensions to this ROM profile");
        check(saved.storage.equals(fixture.storage)&&saved.settings.card.equals(fixture.settings.card),"Resolution edits retain internal storage and StorageCard assignments");
        Engine engine=new Engine(activity,s->{},new StorageLayout(paths.root,paths.runtime,saved));
        try{List<String> command=engine.processBuilder().command();check(command.get(command.indexOf("-machine")+1).contains(",screen-width=640,screen-height=360"),"Persisted custom size reaches actual Engine launch options");}finally{engine.dispose();}
        runOnMainSync(()->activity.finish());waitForIdleSync();launch(filename);openCustom();
        check(node("Width (px)").getText().toString().equals("640")&&node("Height (px)").getText().toString().equals("360"),"Custom fields survive Activity close and reopen");tap("Cancel");
        tap("Guest resolution");tap("VGA (480×640)");node("VGA (480×640)  ▾");
        check(repository.getProfile(filename).settings.startupSize(filename).height==640,"Selecting a preset restores its guest dimensions");openCustom();
        check(node("Width (px)").getText().toString().equals("640")&&node("Height (px)").getText().toString().equals("360"),"Returning from a preset remembers the last custom size");
        screenshot("custom-remembered.png");tap("Cancel");
        openCustom();enter("Width (px)","1280");enter("Height (px)","960");tap("Save");node("Custom (1280×960)  ▾");
        check(repository.getProfile(filename).settings.startupSize(filename).width==1280,"Custom editor accepts resolutions above the old cap");
        frameGrowth();
        result.putString("stream","PASS "+checks+" real Android custom resolution checks\n");result.putBoolean("passed",true);
    }catch(Throwable failure){result.putString("stream","ERROR "+android.util.Log.getStackTraceString(failure));result.putBoolean("passed",false);}
    finally{if(activity!=null)runOnMainSync(()->activity.finish());finish(result.getBoolean("passed")?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);}}
}
