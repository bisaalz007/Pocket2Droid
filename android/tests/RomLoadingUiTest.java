package com.samsixx.pocket2droid;
import android.app.*;import android.content.*;import android.graphics.*;import android.graphics.drawable.*;import android.os.*;import android.view.*;
import java.io.*;import java.util.*;
public final class RomLoadingUiTest extends Instrumentation {
 int checks;List<String> failures=new ArrayList<>();void check(boolean v,String label){checks++;if(!v)failures.add(label);}
 void main(Runnable r){runOnMainSync(r);waitForIdleSync();}
 void until(java.util.function.BooleanSupplier predicate)throws Exception{long end=SystemClock.uptimeMillis()+3000;while(!predicate.getAsBoolean()&&SystemClock.uptimeMillis()<end)Thread.sleep(20);if(!predicate.getAsBoolean())throw new AssertionError("Frame timeout");}
 Bitmap snapshot(RomLoadingView v){Bitmap b=Bitmap.createBitmap(v.getWidth(),v.getHeight(),Bitmap.Config.ARGB_8888);main(()->v.draw(new Canvas(b)));return b;}
 int[] pixels(Bitmap b){int[] p=new int[b.getWidth()*b.getHeight()];b.getPixels(p,0,b.getWidth(),0,0,b.getWidth(),b.getHeight());return p;}
 Rect brightBounds(Bitmap b){Rect r=new Rect(b.getWidth(),b.getHeight(),0,0);int[] p=pixels(b);for(int y=0;y<b.getHeight();y++)for(int x=0;x<b.getWidth();x++)if((p[y*b.getWidth()+x]&0x00ffffff)>0x00808080){r.left=Math.min(r.left,x);r.top=Math.min(r.top,y);r.right=Math.max(r.right,x+1);r.bottom=Math.max(r.bottom,y+1);}return r;}
 void aspects(RomLoadingView v,boolean legacy){
  int l=v.getLeft(),t=v.getTop(),r=v.getRight(),b=v.getBottom();main(()->{v.active(false);v.layout(0,0,963,1633);});Bitmap source=snapshot(v);Rect pattern=brightBounds(source);check(!pattern.isEmpty(),"Decoded GIF has visible artwork");
  for(int[] size:new int[][]{{360,800},{800,360},{800,800},{1200,800}}){int w=size[0],h=size[1];main(()->v.layout(0,0,w,h));Bitmap rendered=snapshot(v);Rect actual=brightBounds(rendered);float scale=Math.min(w/963f,h/1633f),x=(w-963*scale)/2,y=(h-1633*scale)/2;check(Math.abs(actual.left-(x+pattern.left*scale))<3&&Math.abs(actual.right-(x+pattern.right*scale))<3&&Math.abs(actual.top-(y+pattern.top*scale))<3&&Math.abs(actual.bottom-(y+pattern.bottom*scale))<3,"Rendered artwork fits without distortion: "+w+"x"+h+", legacy="+legacy);check(rendered.getPixel(0,0)==Color.BLACK&&rendered.getPixel(w-1,h-1)==Color.BLACK,"Loading backdrop stays black at "+w+"x"+h);rendered.recycle();}
  source.recycle();main(()->{v.layout(l,t,r,b);v.active(true);});
 }
 void run(boolean legacy)throws Exception {
  RomLoadingHarnessActivity a=(RomLoadingHarnessActivity)startActivitySync(new Intent(getTargetContext(),RomLoadingHarnessActivity.class).putExtra("legacy",legacy).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));until(()->a.loader.getWidth()>0&&a.surface.frameObserved);waitForIdleSync();
  check(a.failure==null,"No synthetic frame errors");check(!a.surface.pictureObserved&&a.loader.getVisibility()==View.VISIBLE,"Black published frame retains loader");check(a.loader.animating(),"GIF starts when visible: legacy="+legacy);
  if(!legacy)check(a.loader.getDrawable() instanceof AnimatedImageDrawable,"Native animated GIF decoder");
  Bitmap first=snapshot(a.loader);Thread.sleep(450);Bitmap next=snapshot(a.loader);check(!Arrays.equals(pixels(first),pixels(next)),"GIF actually changes frames: legacy="+legacy);
  main(()->a.loader.active(false));check(!a.loader.animating(),"Inactive loader stops scheduling");Bitmap paused=snapshot(a.loader);Thread.sleep(400);Bitmap pausedAgain=snapshot(a.loader);check(Arrays.equals(pixels(paused),pixels(pausedAgain)),"Paused GIF stays still");main(()->a.loader.active(true));
  if(!legacy){RectF bounds=new RectF(0,0,a.loader.getDrawable().getIntrinsicWidth(),a.loader.getDrawable().getIntrinsicHeight());a.loader.getImageMatrix().mapRect(bounds);check(Math.abs(bounds.centerX()-a.loader.getWidth()/2f)<2&&Math.abs(bounds.centerY()-a.loader.getHeight()/2f)<2&&bounds.width()<=a.loader.getWidth()+2&&bounds.height()<=a.loader.getHeight()+2,"Reference aspect ratio fits centered without cropping");try(FileOutputStream f=new FileOutputStream(new File(a.getFilesDir(),"rom-loading.png"))){first.compress(Bitmap.CompressFormat.PNG,100,f);}}
  aspects(a.loader,legacy);
  main(()->a.frame(0x000000ff));Thread.sleep(120);check(a.loader.getVisibility()==View.VISIBLE,"Transparent colored pixels do not end loading");
  main(()->a.frame(0xffffffff));until(()->a.loader.getVisibility()==View.GONE);check(a.surface.pictureObserved&&!a.loader.animating(),"First visible posted ROM image stops and hides GIF");
  main(()->a.frame(0xff000000));Thread.sleep(100);check(a.loader.getVisibility()==View.GONE,"Later black game frame cannot restart GIF");
  main(a::restart);Thread.sleep(120);main(()->a.received(1));check(a.loader.getVisibility()==View.VISIBLE&&a.boot.waiting(),"Restart waits for new generation; stale callback ignored");main(()->a.frame(0xffffffff));try{until(()->a.loader.getVisibility()==View.GONE);}catch(AssertionError e){throw new AssertionError("Restart timeout legacy="+legacy+", failure="+a.failure+", picture="+a.surface.pictureObserved+", current="+a.engine.generation,e);}check(!a.boot.waiting(),"Restart image completes loader");main(a::finish);
 }
 @Override public void onCreate(Bundle b){super.onCreate(b);start();}
 @Override public void onStart(){Bundle result=new Bundle();try{run(false);run(true);result.putBoolean("passed",failures.isEmpty());result.putString("stream",(failures.isEmpty()?"PASS ":"FAIL ")+checks+" Android ROM loading checks\n"+String.join("\n",failures)+"\n");}catch(Throwable t){result.putString("stream","ERROR "+android.util.Log.getStackTraceString(t));}finally{finish(result.getBoolean("passed")?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);}}
}
