package com.samsixx.pocket2droid;
import android.app.*;import android.content.*;import android.os.*;import android.view.accessibility.AccessibilityNodeInfo;
import java.io.*;import java.net.*;import java.util.*;import java.util.concurrent.*;

/** Actual frontend/Android observer plus app-UID sockets; guest QEMU tested separately. */
public final class NetworkUiTest extends Instrumentation {
    private int checks,port;private RomSettingsActivity activity;
    private void check(boolean ok,String why){if(!ok)throw new AssertionError(why);checks++;}
    private AccessibilityNodeInfo find(AccessibilityNodeInfo n,String text){if(n==null)return null;if(text.equals(String.valueOf(n.getText())))return n;for(int i=0;i<n.getChildCount();i++){AccessibilityNodeInfo r=find(n.getChild(i),text);if(r!=null)return r;}return null;}
    private AccessibilityNodeInfo node(String text)throws Exception{for(int i=0;i<60;i++){AccessibilityNodeInfo n=find(getUiAutomation().getRootInActiveWindow(),text);if(n!=null)return n;Thread.sleep(50);}throw new AssertionError("Missing UI "+text);}
    private boolean scroll(AccessibilityNodeInfo n){if(n==null)return false;if(n.isScrollable()&&n.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD))return true;for(int i=0;i<n.getChildCount();i++)if(scroll(n.getChild(i)))return true;return false;}
    private void tap(String text)throws Exception{AccessibilityNodeInfo n=node(text);while(n!=null&&!n.isClickable())n=n.getParent();check(n!=null&&n.performAction(AccessibilityNodeInfo.ACTION_CLICK),"Click "+text);waitForIdleSync();Thread.sleep(100);}
    private void internet()throws Exception{for(int i=0;i<5&&find(getUiAutomation().getRootInActiveWindow(),"Internet access")==null;i++){scroll(getUiAutomation().getRootInActiveWindow());Thread.sleep(100);}tap("Internet access");}
    private void launch(String filename)throws Exception{activity=(RomSettingsActivity)startActivitySync(new Intent(getTargetContext(),RomSettingsActivity.class).putExtra("rom",filename).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));node("Guest resolution");}
    private void waitProfile(RomRepository repo,String filename,boolean enabled)throws Exception{for(int i=0;i<100;i++){boolean[] idle={false};runOnMainSync(()->idle[0]=!activity.working);if(idle[0]&&repo.getProfile(filename).settings.internetEnabled==enabled)return;Thread.sleep(30);}throw new AssertionError("Settings write/UI completion timed out");}
    @Override public void onCreate(Bundle args){super.onCreate(args);port=Integer.parseInt(args.getString("http_port"));start();}
    @Override public void onStart(){Bundle result=new Bundle();try{
        check(android.os.Process.myUid()!=0&&android.os.Process.myUid()!=2000,"Tests run under unprivileged app UID");
        StorageLayout paths=StorageLayout.forContext(getTargetContext());RomRepository repo=new RomRepository(paths.root,paths.runtime,new File(paths.root,"storagecard"));String name="NETWORK_UI_"+UUID.randomUUID()+".BIN";
        RomProfile initial=repo.importRom(new ByteArrayInputStream(new byte[]{1}),name);check(initial.settings.internetEnabled&&NetworkConfig.validMac(initial.settings.networkMac),"New actual profile On with valid MAC");
        launch(name);internet();tap("On");waitProfile(repo,name,true);String mac=repo.getProfile(name).settings.networkMac;
        internet();tap("Off");waitProfile(repo,name,false);runOnMainSync(()->activity.finish());waitForIdleSync();launch(name);internet();tap("On");waitProfile(repo,name,true);check(repo.getProfile(name).settings.networkMac.equals(mac),"UI Off/On across Activity recreation preserves MAC");
        check(repo.getProfile(name).storage.equals(initial.storage)&&repo.getProfile(name).settings.card.equals(initial.settings.card),"Network edit preserves all storage paths");
        File setup=NetworkSetup.prepare(getTargetContext(),initial.settings);check(setup.isFile()&&setup.length()<=256*1024,"Actual Android publishes verified helper in private storage");check(!setup.getPath().startsWith(paths.root.getPath())&&!new File(initial.settings.card,"2577").exists(),"Actual helper publication never writes to ROM or StorageCard directories");
        for(int form=0;form<2;form++){
            org.json.JSONObject old=initial.settings.json();if(form==0)old.remove("networkSetupEligible");else old.put("networkSetupEligible",false);
            RomSettings legacy=RomSettings.parse(old);check(!legacy.networkSetupEligible,"Read historical profile eligibility without rewriting metadata");
            check(setup.equals(NetworkSetup.prepare(getTargetContext(),legacy)),"Existing Internet-On profile publishes exact same verified helper");
            check(NetworkSetup.prepare(null,legacy.withInternetAccess(false))==null,"Existing Internet-Off profile must never access helper assets or storage");
        }
        check(NetworkSetup.prepare(null,null)==null,"Profile-less launch never prepares a helper");
        android.graphics.Bitmap shot=getUiAutomation().takeScreenshot();if(shot!=null){try(FileOutputStream out=new FileOutputStream(new File(activity.getFilesDir(),"network-settings.png"))){shot.compress(android.graphics.Bitmap.CompressFormat.PNG,100,out);}shot.recycle();}
        File networkRoot=new File(getTargetContext().getFilesDir(),"observer-"+UUID.randomUUID());ExecutorService worker=Executors.newSingleThreadExecutor();NetworkSession session=new NetworkSession(getTargetContext(),networkRoot,worker,text->{});
        try{session.start();check(session.resolverFile().isFile(),"Actual ConnectivityManager observer creates private DNS file");worker.submit(()->{}).get(2,TimeUnit.SECONDS);check(session.resolverFile().length()<=4096,"Actual Android DNS is bounded");}finally{session.close();worker.shutdown();worker.awaitTermination(2,TimeUnit.SECONDS);}
        check(!session.resolverFile().exists(),"Actual observer close removes owned DNS");networkRoot.delete();
        try(Socket socket=new Socket()){socket.connect(new InetSocketAddress("10.0.2.2",port),3000);socket.setSoTimeout(3000);socket.getOutputStream().write("GET / HTTP/1.0\r\nHost: owned-test\r\n\r\n".getBytes("US-ASCII"));ByteArrayOutputStream bytes=new ByteArrayOutputStream();byte[] buffer=new byte[1024];int n;while((n=socket.getInputStream().read(buffer))!=-1)bytes.write(buffer,0,n);check(bytes.toString("US-ASCII").contains("p2d-owned-android-network-test"),"Actual app-UID network permission and TCP response");}
        File engineRoot=new File(getTargetContext().getFilesDir(),"engine-network-"+UUID.randomUUID());check(engineRoot.mkdir(),"Create owned ART fixtures");EngineKeyTest.main(new String[]{engineRoot.getPath()});
        result.putString("stream","PASS "+checks+" Android network UI/observer/socket checks; Engine ART lifecycle checks passed. Guest NAT is separate PC evidence.\n");result.putBoolean("passed",true);
    }catch(Throwable e){result.putString("stream","ERROR "+android.util.Log.getStackTraceString(e));result.putBoolean("passed",false);}finally{if(activity!=null)runOnMainSync(()->activity.finish());finish(result.getBoolean("passed")?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);}}
}
