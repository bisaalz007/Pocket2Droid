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
        section(body,"DISPLAY");row(body,"Guest resolution",profile.settings.resolutionLabel()+"  ▾",this::resolutions);row(body,"Screen fit",profile.settings.scale==RomSettings.ScaleMode.FITTED?"Fitted  ▾":"Pixel perfect  ▾",()->new AlertDialog.Builder(this).setTitle("Screen fit").setItems(new String[]{"Fitted","Pixel perfect"},(d,i)->{try{save(profile.settings.withScale(RomSettings.ScaleMode.values()[i]));}catch(IOException e){error(e.getMessage());}}).show());
        note(body,"The preset is selected from the filename when adding a ROM; unfamiliar names start with QVGA. You can change it here. Screen fit only changes image scaling.");
        row(body,"Orientation",profile.settings.orientation==RomSettings.HostOrientation.PORTRAIT?"Portrait":"Landscape",()->new AlertDialog.Builder(this).setTitle("Orientation").setItems(new String[]{"Portrait","Landscape"},(d,i)->{try{save(profile.settings.withOrientation(RomSettings.HostOrientation.values()[i]));}catch(IOException e){error(e.getMessage());}}).show());
        row(body,"Screen Position",profile.settings.screenPosition.label+"  ▾",this::screenPositions);
        section(body,"STORAGE");LinearLayout card=row(body,"StorageCard folder",profile.settings.card.getPath(),this::storageCard);
        TextView cardHint=text("Tap to change the StorageCard location for this ROM.",12,MUTED);cardHint.setPadding(0,dp(8),0,0);card.addView(cardHint);
        section(body,"NETWORK");row(body,"Internet access",profile.settings.internetEnabled?"On  ▾":"Off  ▾",()->new AlertDialog.Builder(this).setTitle("Internet access").setSingleChoiceItems(new String[]{"Off","On"},profile.settings.internetEnabled?1:0,(d,i)->{d.dismiss();try{save(profile.settings.withInternetAccess(i==1));}catch(IOException e){error(e.getMessage());}}).setNegativeButton("Close",null).show());
        note(body,"New ROMs start with Internet access On. Supported new and existing ROMs can use the Work network automatically when On. Custom guest network settings are preserved. If automatic setup does not work, select The Internet in Windows Mobile's Network Cards settings. Older browsers may not support modern HTTPS sites.");
        Button delete=action("Delete ROM",this::confirmDelete);delete.setTextColor(0xffff7979);LinearLayout.LayoutParams margin=new LinearLayout.LayoutParams(-1,dp(52));margin.setMargins(dp(16),dp(16),dp(16),dp(20));body.addView(delete,margin);
    }
    private void storageCard(){
        if(profile==null)return;
        new AlertDialog.Builder(this).setTitle("Change StorageCard folder?").setIcon(getResources().getIdentifier("storage_card_warning","drawable",getPackageName()))
            .setMessage("The emulated OS and its apps can modify or delete files in the selected folder.\n\nUse a dedicated folder. Do not select personal folders or folders containing important data.")
            .setNegativeButton("Cancel",null).setPositiveButton("Continue",(d,w)->folder(profile.settings.card,file->{
                try{save(profile.settings.withCard(file));}catch(IOException failure){error(failure.getMessage());}
            })).show();
    }
    private void resolutions(){final RomSettings.GuestResolution[] modes=RomSettings.GuestResolution.presets();String[] labels=new String[modes.length+1];int selected=profile.settings.resolution==RomSettings.GuestResolution.CUSTOM?modes.length:-1;for(int i=0;i<modes.length;i++){labels[i]=modes[i].label;if(modes[i]==profile.settings.resolution)selected=i;}labels[modes.length]="Custom…";
        new AlertDialog.Builder(this).setTitle("Guest resolution").setSingleChoiceItems(labels,selected,(d,i)->{d.dismiss();if(i==modes.length){customResolution();return;}try{save(profile.settings.withResolution(modes[i]));}catch(IOException e){error(e.getMessage());}}).setNegativeButton("Close",null).show();
    }
    private void customResolution(){
        LinearLayout form=column();form.setPadding(dp(24),dp(12),dp(24),0);
        LinearLayout sizes=new LinearLayout(this);sizes.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout widthBox=column(),heightBox=column();
        TextView widthLabel=text("Width (px)",14,MUTED),heightLabel=text("Height (px)",14,MUTED);
        EditText width=new EditText(this),height=new EditText(this);
        width.setId(View.generateViewId());height.setId(View.generateViewId());widthLabel.setLabelFor(width.getId());heightLabel.setLabelFor(height.getId());
        for(EditText edit:new EditText[]{width,height}){edit.setSingleLine(true);edit.setInputType(android.text.InputType.TYPE_CLASS_NUMBER);edit.setSelectAllOnFocus(true);edit.setTextSize(20);}
        width.setContentDescription("Width (px)");height.setContentDescription("Height (px)");
        RomSettings.GuestSize current=profile.settings.startupSize(profile.filename);
        boolean custom=profile.settings.customWidth>0;
        width.setText(Integer.toString(custom?profile.settings.customWidth:current.width));height.setText(Integer.toString(custom?profile.settings.customHeight:current.height));
        widthBox.addView(widthLabel);widthBox.addView(width);heightBox.addView(heightLabel);heightBox.addView(height);
        sizes.addView(widthBox,new LinearLayout.LayoutParams(0,-2,1));TextView times=text("×",20,TEXT);times.setPadding(dp(12),dp(16),dp(12),0);sizes.addView(times);sizes.addView(heightBox,new LinearLayout.LayoutParams(0,-2,1));form.addView(sizes);
        TextView helper=text("Applies the next time you start this ROM.\nSome ROMs may not support every resolution.",14,MUTED);helper.setPadding(0,dp(16),0,dp(8));form.addView(helper);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("Custom resolution").setView(form).setPositiveButton("Save",null).setNegativeButton("Cancel",null).create();
        dialog.setOnShowListener(d->dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{
            Integer w=customDimension(width),h=customDimension(height);if(w==null||h==null)return;
            try{save(profile.settings.withCustomResolution(w,h));dialog.dismiss();}catch(IOException e){error(e.getMessage());}
        }));dialog.show();
    }
    private Integer customDimension(EditText edit){
        try{String value=edit.getText().toString().trim();if(!value.matches("[0-9]+"))throw new NumberFormatException();int n=Integer.parseInt(value);if(n<1)throw new NumberFormatException();edit.setError(null);return n;}
        catch(NumberFormatException e){edit.setError("Enter a positive whole number");edit.requestFocus();return null;}
    }
    private void screenPositions(){final RomSettings.ScreenPosition[] positions=RomSettings.ScreenPosition.values();String[] labels=new String[positions.length];for(int i=0;i<positions.length;i++)labels[i]=positions[i].label;
        new AlertDialog.Builder(this).setTitle("Screen Position").setSingleChoiceItems(labels,profile.settings.screenPosition.ordinal(),(d,i)->{d.dismiss();try{save(profile.settings.withScreenPosition(positions[i]));}catch(IOException e){error(e.getMessage());}}).setNegativeButton("Close",null).show();
    }
    private void confirmDelete(){if(profile==null)return;final String selected=profile.filename;new AlertDialog.Builder(this).setTitle("Delete ROM?").setMessage(selected+"\n\nDeleting this ROM will also delete its internal storage, including installed apps, settings and saves. The storagecard folder and its files will not be affected.").setPositiveButton("Delete",(d,w)->{if(!selected.equals(filename))return;task(()->{repository().deleteRom(selected);return true;},value->finish());}).setNegativeButton("Cancel",null).show();}
}
