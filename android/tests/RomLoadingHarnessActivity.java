package com.samthedev.pocket2droid;
import android.app.*;import android.os.*;import android.graphics.Color;import android.view.*;import android.widget.*;
import java.io.*;import java.nio.*;import java.nio.channels.*;
/** Owned private frame fixture; Engine.start is never called. */
public final class RomLoadingHarnessActivity extends Activity {
 Engine engine;GuestSurface surface;RomLoadingView loader;RomBootState boot=new RomBootState();long sequence;String failure;
 @Override public void onCreate(Bundle state){super.onCreate(state);File base=new File(getFilesDir(),"rom-loading-frame-fixture");base.mkdirs();engine=new Engine(this,s->failure=s,new StorageLayout(null,base));boot.starting(0);engine.generation=1;
  FrameLayout root=new FrameLayout(this);root.setBackgroundColor(Color.BLACK);surface=new GuestSurface(this,engine,s->failure=s,this::received);surface.resumed=true;root.addView(surface,new FrameLayout.LayoutParams(-1,-1));loader=new RomLoadingView(this,getIntent().getBooleanExtra("legacy",false));root.addView(loader,new FrameLayout.LayoutParams(-1,-1));loader.active(true);setContentView(root);frame(0xff000000);engine.frameReady=true;
 }
 void received(long generation){runOnUiThread(()->{if(boot.picture(generation,engine.generation)){loader.active(false);loader.setVisibility(View.GONE);}});}
 void frame(int color){Bundle values=new Bundle();values.putLong("sequence",++sequence);values.putInt("color",color);getContentResolver().call(android.net.Uri.parse("content://"+getPackageName()+".frames"),"frame",null,values);}
 void restart(){boot.starting(engine.generation);frame(0xff000000);engine.generation++;loader.setVisibility(View.VISIBLE);loader.active(true);}
 @Override protected void onDestroy(){surface.destroyed=true;surface.resumed=false;loader.active(false);engine.dispose();super.onDestroy();}
}
