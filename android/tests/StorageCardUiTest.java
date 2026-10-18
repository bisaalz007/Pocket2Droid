package com.samsixx.pocket2droid;

import android.app.*;
import android.content.*;
import android.os.*;
import android.view.accessibility.AccessibilityNodeInfo;
import java.io.*;
import java.util.*;

/** Real dialog, folder selection and profile persistence on the owned PC VM. */
public final class StorageCardUiTest extends Instrumentation {
    private int checks;
    private LibraryUi activity;
    private void check(boolean ok,String why){if(!ok)throw new AssertionError(why);checks++;}
    private AccessibilityNodeInfo find(AccessibilityNodeInfo node,String text){
        if(node==null)return null;
        if(text.equalsIgnoreCase(String.valueOf(node.getText())))return node;
        for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo hit=find(node.getChild(i),text);if(hit!=null)return hit;}return null;
    }
    private AccessibilityNodeInfo root(){return getUiAutomation().getRootInActiveWindow();}
    private AccessibilityNodeInfo node(String text)throws Exception{
        for(int i=0;i<75;i++){AccessibilityNodeInfo hit=find(root(),text);if(hit!=null)return hit;Thread.sleep(40);}
        throw new AssertionError("Missing visible UI: "+text);
    }
    private boolean scroll(AccessibilityNodeInfo node){
        if(node==null)return false;
        if(node.isScrollable()&&node.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD))return true;
        for(int i=0;i<node.getChildCount();i++)if(scroll(node.getChild(i)))return true;return false;
    }
    private AccessibilityNodeInfo seek(String text)throws Exception{
        for(int i=0;i<12;i++){AccessibilityNodeInfo hit=find(root(),text);if(hit!=null&&hit.isVisibleToUser())return hit;scroll(root());Thread.sleep(70);}
        return node(text);
    }
    private void ready()throws Exception{
        for(int i=0;i<150;i++){boolean[] done={false};runOnMainSync(()->done[0]=!activity.working);if(done[0]){waitForIdleSync();return;}Thread.sleep(20);}
        throw new AssertionError("Settings task did not finish");
    }
    private void click(AccessibilityNodeInfo hit,String why)throws Exception{
        while(hit!=null&&!hit.isClickable())hit=hit.getParent();
        check(hit!=null&&hit.performAction(AccessibilityNodeInfo.ACTION_CLICK),why);waitForIdleSync();ready();
    }
    private void tap(String text)throws Exception{click(node(text),"Click real UI: "+text);}
    private void cardRow()throws Exception{
        AccessibilityNodeInfo hit=find(root(),"StorageCard folder");
        if(hit==null)hit=find(root(),"storagecard");
        if(hit==null||!hit.isVisibleToUser()){seek("STORAGE");hit=find(root(),"StorageCard folder");if(hit==null)hit=find(root(),"storagecard");}
        click(hit,"The ROM StorageCard row must be clickable");node("Change StorageCard folder?");
    }
    private AccessibilityNodeInfo editable(AccessibilityNodeInfo node){
        if(node==null)return null;if(node.isEditable())return node;
        for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo hit=editable(node.getChild(i));if(hit!=null)return hit;}return null;
    }
    private void choosePath(File folder)throws Exception{
        tap("Path…");node("Folder path");AccessibilityNodeInfo field=editable(root());
        Bundle args=new Bundle();args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,folder.getPath());
        check(field!=null&&field.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args),"Enter actual folder path");
        tap("Open");node(folder.getPath());tap("Use this folder");
    }
    private String read(File file)throws Exception{
        try(FileInputStream in=new FileInputStream(file);ByteArrayOutputStream out=new ByteArrayOutputStream()){
            byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1)out.write(b,0,n);return out.toString("UTF-8");
        }
    }
    private void write(File file,String value)throws Exception{try(FileOutputStream out=new FileOutputStream(file)){out.write(value.getBytes("UTF-8"));}}
    private void launch(String filename)throws Exception{
        activity=(RomSettingsActivity)startActivitySync(new Intent(getTargetContext(),RomSettingsActivity.class).putExtra("rom",filename).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        node("Guest resolution");ready();
    }
    private void close(){if(activity!=null)runOnMainSync(()->activity.finish());waitForIdleSync();activity=null;}
    private void screenshot(String name)throws Exception{
        android.graphics.Bitmap bitmap=getUiAutomation().takeScreenshot();check(bitmap!=null,"Capture actual StorageCard UI");
        try(FileOutputStream out=new FileOutputStream(new File(activity.getFilesDir(),name))){bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG,100,out);}bitmap.recycle();
    }
    @Override public void onCreate(Bundle args){super.onCreate(args);start();}
    @Override public void onStart(){Bundle result=new Bundle();try{
        StorageLayout paths=StorageLayout.forContext(getTargetContext());
        File general=new File(paths.root,"storagecard");RomRepository repository=new RomRepository(paths.root,paths.runtime,general);
        String id=UUID.randomUUID().toString();
        RomProfile first=repository.importRom(new ByteArrayInputStream(new byte[]{1}),"CARD_UI_"+id+".BIN");
        RomProfile second=repository.importRom(new ByteArrayInputStream(new byte[]{2}),"CARD_OTHER_"+id+".BIN");
        File meta=new File(first.storage.getParentFile(),"profile.json"),custom=new File(paths.root,"card-ui-"+id);
        check(custom.mkdir(),"Create dedicated owned card fixture");File keep=new File(custom,"keep.txt");write(keep,"existing card data");
        String before=read(meta);launch(first.filename);cardRow();
        AccessibilityNodeInfo warning=node("The emulated OS and its apps can modify or delete files in the selected folder.\n\nUse a dedicated folder. Do not select personal folders or folders containing important data.");
        check(!warning.getText().toString().contains("this ROM"),"Warning omits the rejected scope sentence");
        check(find(root(),"Use this folder")==null,"Warning appears before any folder picker");screenshot("storage-card-warning.png");
        tap("Cancel");check(read(meta).equals(before),"Warning Cancel leaves exact profile bytes unchanged");
        cardRow();tap("Continue");node("Use this folder");tap("Cancel");
        check(read(meta).equals(before),"Picker Cancel leaves exact profile bytes unchanged");
        cardRow();tap("Continue");node("Use this folder");choosePath(new File(paths.root,"data"));
        node("Use a dedicated folder outside ROM, data and runtime folders");tap("OK");
        check(read(meta).equals(before),"Managed data directory is refused without saving");
        cardRow();tap("Continue");node("Use this folder");choosePath(custom);
        RomProfile saved=repository.getProfile(first.filename);
        check(saved.settings.card.equals(custom.getCanonicalFile()),"Folder picker persists the selected ROM card");
        check(repository.getProfile(second.filename).settings.card.equals(general.getCanonicalFile()),"Changing one ROM leaves another ROM on the general card");
        check(read(keep).equals("existing card data")&&!first.storage.exists(),"Selection does not copy, delete or initialize guest files");
        org.json.JSONObject prior=new org.json.JSONObject(before),after=new org.json.JSONObject(read(meta));prior.remove("storageCard");after.remove("storageCard");
        check(prior.toString().equals(after.toString()),"Card change preserves all other profile settings, network identity and save state");
        Engine engine=new Engine(activity,s->{},new StorageLayout(paths.root,paths.runtime,saved));
        try{List<String> command=engine.processBuilder().command();check(command.get(command.indexOf("-machine")+1).contains(",shared-folder="+custom.getPath()+","),"Actual Engine launch options use the chosen card");}finally{engine.dispose();}
        close();launch(first.filename);seek("StorageCard folder");node(custom.getPath());screenshot("storage-card-selected.png");
        check(repository.getProfile(first.filename).settings.card.equals(custom.getCanonicalFile()),"Folder selection survives Activity close/reopen");close();
        RomProfile third=repository.importRom(new ByteArrayInputStream(new byte[]{3}),"CARD_NEW_"+id+".BIN");
        check(third.settings.card.equals(general.getCanonicalFile()),"New ROMs still inherit the fixed general folder");
        String name="card-import-"+id+".txt";File copied=repository.importCardFile(new ByteArrayInputStream(new byte[]{4}),name);
        check(copied.getParentFile().equals(general.getCanonicalFile())&&!new File(custom,name).exists(),"General File to StorageCard keeps its fixed destination");
        activity=(AppSettingsActivity)startActivitySync(new Intent(getTargetContext(),AppSettingsActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        AccessibilityNodeInfo defaultRow=seek("Default storagecard Folder").getParent();
        check(defaultRow!=null&&!defaultRow.isClickable(),"General StorageCard row remains informational and fixed");
        check(find(root(),general.getPath())!=null,"General settings still show the fixed path");
        result.putString("stream","PASS "+checks+" real Android StorageCard checks\n");result.putBoolean("passed",true);
    }catch(Throwable failure){result.putString("stream","ERROR "+android.util.Log.getStackTraceString(failure));result.putBoolean("passed",false);}
    finally{close();finish(result.getBoolean("passed")?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);}}
}
