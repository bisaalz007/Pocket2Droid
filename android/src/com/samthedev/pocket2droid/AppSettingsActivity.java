package com.samthedev.pocket2droid;
import android.os.*;
import android.view.View;
import android.widget.*;
import java.io.*;
public final class AppSettingsActivity extends LibraryUi {
    private LinearLayout body;
    @Override public void onCreate(Bundle saved){super.onCreate(saved);LinearLayout root=column();root.addView(bar("App settings",null,null));ScrollView scroll=new ScrollView(this);body=column();scroll.addView(body);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));status=text("",12,MUTED);status.setVisibility(View.GONE);root.addView(status);install(root);render();}
    @Override protected void onResume(){super.onResume();if(body!=null)render();}
    private void render(){body.removeAllViews();section(body,"AUDIO");switchRow(body,"Sound","Enable sound","sound_enabled",true);section(body,"DISPLAY");switchRow(body,"Display FPS counter","Show display presentations per second","fps_enabled",true);switchRow(body,"Enable fullscreen","Hide system bars and toolbar","fullscreen_enabled",false);section(body,"CONTROLS");switchRow(body,"Enable on-screen controls","Show touch controls","keys_enabled",true);transparencyRow();row(body,"Button Mapping","Assign keyboard and controller inputs",()->startActivity(new android.content.Intent(this,ButtonMappingActivity.class)));switchRow(body,"Vibration feedback","Vibrate briefly when an on-screen key is pressed","controls_vibration",true);section(body,"STORAGE");row(body,"Storage access",StorageAccess.granted(this)?"Allowed":"Tap to allow",()->access());StorageLayout paths=StorageLayout.forContext(this);row(body,"Default Rom folder","pocket2droid/Roms",null);String card=paths.root==null?"pocket2droid/storagecard":new File(paths.root,"storagecard").getPath();row(body,"Default storagecard Folder",card,null);row(body,"Default Data Folder","pocket2droid/data",null);}
    private void transparencyRow(){int value=controlsTransparency();LinearLayout box=row(body,"Controls transparency",value+"% · 0% solid, 100% invisible",null);TextView detail=(TextView)box.getChildAt(1);SeekBar slider=new SeekBar(this);slider.setMax(100);slider.setProgress(value);slider.setContentDescription("Controls transparency");box.addView(slider,new LinearLayout.LayoutParams(-1,dp(48)));
        slider.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){
            public void onProgressChanged(SeekBar bar,int progress,boolean fromUser){detail.setText(progress+"% · 0% solid, 100% invisible");if(fromUser)prefs().edit().putInt("controls_transparency",progress).apply();}
            public void onStartTrackingTouch(SeekBar bar){}
            public void onStopTrackingTouch(SeekBar bar){}
        });
    }
    @Override public void onRequestPermissionsResult(int request,String[] p,int[] r){super.onRequestPermissionsResult(request,p,r);render();}
}
