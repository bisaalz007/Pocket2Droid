package com.samsixx.pocket2droid;
import android.app.*;
import android.os.*;
import android.view.*;
import android.widget.*;
import java.io.*;

public final class RomSettingsActivity extends LibraryUi {
    private String filename;
    private RomProfile profile;
    private LinearLayout body;
    @Override public void onCreate(Bundle saved){super.onCreate(saved);filename=getIntent().getStringExtra("rom");LinearLayout root=column();root.addView(bar("ROM settings",()->launchRom(filename),"Start"));ScrollView scroll=new ScrollView(this);body=column();scroll.addView(body);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));status=text("",12,MUTED);status.setVisibility(View.GONE);root.addView(status);install(root);load();}
    private void load(){task(()->repository().getProfile(filename),p->{profile=p;render();});}
    private void save(RomSettings value){task(()->{repository().saveSettings(filename,value);return repository().getProfile(filename);},p->{profile=p;render();});}
    private void render(){body.removeAllViews();LinearLayout heading=new LinearLayout(this);heading.setPadding(dp(16),dp(20),dp(16),dp(16));heading.setGravity(Gravity.CENTER_VERTICAL);ImageView image=new ImageView(this);image.setImageBitmap(icon(profile.iconId));heading.addView(image,new LinearLayout.LayoutParams(dp(56),dp(56)));LinearLayout labels=column();labels.setPadding(dp(16),0,0,0);labels.addView(text(profile.displayName,20,TEXT));labels.addView(text(profile.filename,12,MUTED));heading.addView(labels);body.addView(heading);
        section(body,"GENERAL");row(body,"Display name",profile.displayName,()->{EditText edit=new EditText(this);edit.setSingleLine(true);edit.setText(profile.displayName);new AlertDialog.Builder(this).setTitle("Display name").setView(edit).setPositiveButton("Save",(d,w)->{try{save(profile.settings.withDisplayName(edit.getText().toString()));}catch(IOException e){error(e.getMessage());}}).setNegativeButton("Cancel",null).show();});row(body,"ROM file","Roms/"+profile.filename,null);
        section(body,"DISPLAY");row(body,"Guest resolution",profile.settings.resolution.label+"  ▾",this::resolutions);row(body,"Screen fit",profile.settings.scale==RomSettings.ScaleMode.FITTED?"Fitted  ▾":"Pixel perfect  ▾",()->new AlertDialog.Builder(this).setTitle("Screen fit").setItems(new String[]{"Fitted","Pixel perfect"},(d,i)->{try{save(profile.settings.withScale(RomSettings.ScaleMode.values()[i]));}catch(IOException e){error(e.getMessage());}}).show());
        note(body,"The preset is selected from the filename when adding a ROM; unfamiliar names start with QVGA. You can change it here. Screen fit only changes image scaling.");
        row(body,"Orientation",profile.settings.orientation==RomSettings.HostOrientation.PORTRAIT?"Portrait":"Landscape",()->new AlertDialog.Builder(this).setTitle("Orientation").setItems(new String[]{"Portrait","Landscape"},(d,i)->{try{save(profile.settings.withOrientation(RomSettings.HostOrientation.values()[i]));}catch(IOException e){error(e.getMessage());}}).show());
        row(body,"Screen Position",profile.settings.screenPosition.label+"  ▾",this::screenPositions);
        section(body,"STORAGE");row(body,"storagecard",profile.settings.card.getPath(),null);
        Button delete=action("Delete ROM",this::confirmDelete);delete.setTextColor(0xffff7979);LinearLayout.LayoutParams margin=new LinearLayout.LayoutParams(-1,dp(52));margin.setMargins(dp(16),dp(16),dp(16),dp(20));body.addView(delete,margin);
    }
    private void resolutions(){final RomSettings.GuestResolution[] modes=RomSettings.GuestResolution.presets();String[] labels=new String[modes.length];int selected=-1;for(int i=0;i<modes.length;i++){labels[i]=modes[i].label;if(modes[i]==profile.settings.resolution)selected=i;}
        new AlertDialog.Builder(this).setTitle("Guest resolution").setSingleChoiceItems(labels,selected,(d,i)->{d.dismiss();try{save(profile.settings.withResolution(modes[i]));}catch(IOException e){error(e.getMessage());}}).setNegativeButton("Close",null).show();
    }
    private void screenPositions(){final RomSettings.ScreenPosition[] positions=RomSettings.ScreenPosition.values();String[] labels=new String[positions.length];for(int i=0;i<positions.length;i++)labels[i]=positions[i].label;
        new AlertDialog.Builder(this).setTitle("Screen Position").setSingleChoiceItems(labels,profile.settings.screenPosition.ordinal(),(d,i)->{d.dismiss();try{save(profile.settings.withScreenPosition(positions[i]));}catch(IOException e){error(e.getMessage());}}).setNegativeButton("Close",null).show();
    }
    private void confirmDelete(){if(profile==null)return;final String selected=profile.filename;new AlertDialog.Builder(this).setTitle("Delete ROM?").setMessage(selected+"\n\nDeleting this ROM will also delete its internal storage, including installed apps, settings and saves. The storagecard folder and its files will not be affected.").setPositiveButton("Delete",(d,w)->{if(!selected.equals(filename))return;task(()->{repository().deleteRom(selected);return true;},value->finish());}).setNegativeButton("Cancel",null).show();}
}
