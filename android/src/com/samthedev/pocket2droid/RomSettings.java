package com.samthedev.pocket2droid;
import java.io.*;
import org.json.*;

final class RomSettings {
    enum ScaleMode { FITTED, PIXEL_PERFECT }
    enum HostOrientation { PORTRAIT, LANDSCAPE }
    enum ScreenPosition {
        TOP("Top",0f),CENTER("Center",0.5f),BOTTOM("Bottom",1f);
        final String label;final float anchor;
        ScreenPosition(String label,float anchor){this.label=label;this.anchor=anchor;}
    }
    enum GuestResolution {
        // Retained only to read profiles written before concrete preset defaults.
        ROM_DEFAULT("ROM default",0,0),SMARTPHONE("Smartphone (176×220)",176,220),
        SQUARE("Square (240×240)",240,240),QVGA("QVGA (240×320)",240,320),
        QVGA_LANDSCAPE("QVGA landscape (320×240)",320,240),SQUARE_QVGA("Square QVGA (320×320)",320,320),
        WQVGA("WQVGA (240×400)",240,400),SQUARE_VGA("Square VGA (480×480)",480,480),
        VGA("VGA (480×640)",480,640),WVGA("WVGA (480×800)",480,800);
        final String label;final int width,height;
        GuestResolution(String label,int w,int h){this.label=label;width=w;height=h;}
        boolean supported(){return true;}
        static GuestResolution[] presets(){GuestResolution[] all=values();return java.util.Arrays.copyOfRange(all,1,all.length);}
    }
    final String displayName;
    final GuestResolution resolution;
    final ScaleMode scale;
    final HostOrientation orientation;
    final ScreenPosition screenPosition;
    final File card;
    RomSettings(String name,GuestResolution resolution,ScaleMode scale,HostOrientation orientation,File card)throws IOException {
        this(name,resolution,scale,orientation,ScreenPosition.CENTER,card);
    }
    RomSettings(String name,GuestResolution resolution,ScaleMode scale,HostOrientation orientation,ScreenPosition screenPosition,File card)throws IOException {
        if(name==null||name.trim().isEmpty()||name.length()>180||name.indexOf('\0')>=0)throw new IOException("Enter a nonempty display name (up to 180 characters)");
        if(resolution==null||scale==null||orientation==null||screenPosition==null||card==null||!card.isAbsolute())throw new IOException("Invalid ROM settings");
        displayName=name.trim();this.resolution=resolution;this.scale=scale;this.orientation=orientation;this.screenPosition=screenPosition;this.card=card;
    }
    static RomSettings defaults(String name,File card)throws IOException{return new RomSettings(name,GuestResolution.ROM_DEFAULT,ScaleMode.FITTED,HostOrientation.PORTRAIT,card);}
    RomSettings withDisplayName(String name)throws IOException{return new RomSettings(name,resolution,scale,orientation,screenPosition,card);}
    RomSettings withScale(ScaleMode value)throws IOException{return new RomSettings(displayName,resolution,value,orientation,screenPosition,card);}
    RomSettings withResolution(GuestResolution value)throws IOException{return new RomSettings(displayName,value,scale,orientation,screenPosition,card);}
    GuestResolution startupResolution(String filename){
        if(resolution!=GuestResolution.ROM_DEFAULT)return resolution;
        // SDK metadata supplies sizes outside the raw BIN. Recognize those names
        // with optional resolution annotations and import collision suffixes.
        // Unfamiliar filenames still default to QVGA.
        String name=filename.toUpperCase(java.util.Locale.ROOT)
            .replaceFirst(" \\([0-9]+\\)(?=\\.BIN$)","")
            .replaceFirst(" \\([0-9]+[X×][0-9]+\\)(?=\\.BIN$)","");
        switch(name){
            case "PPC_USA_GSM_SQUARE_VR.BIN":return GuestResolution.SQUARE;
            case "PPC_USA_GSM_QVGA_VR.BIN":case "PPC_USA_GSM_320X320_VR.BIN":return GuestResolution.SQUARE_QVGA;
            case "PPC_USA_GSM_VGA_SQUARE_VR.BIN":return GuestResolution.SQUARE_VGA;
            case "PPC_USA_GSM_VGA_VR.BIN":return GuestResolution.VGA;
            case "PPC_USA_GSM_WQVGA_VR.BIN":case "PPC-PHONE-240X400.BIN":return GuestResolution.WQVGA;
            case "PPC_USA_GSM_WVGA_VR.BIN":case "PPC-PHONE-480X800.BIN":return GuestResolution.WVGA;
            case "SP_USA_GSM_QVGA_LS_VR.BIN":return GuestResolution.QVGA_LANDSCAPE;
            case "SP_USA_GSM_VR.BIN":return GuestResolution.SMARTPHONE;
            default:return GuestResolution.QVGA;
        }
    }
    RomSettings withOrientation(HostOrientation value)throws IOException{return new RomSettings(displayName,resolution,scale,value,screenPosition,card);}
    RomSettings withScreenPosition(ScreenPosition value)throws IOException{return new RomSettings(displayName,resolution,scale,orientation,value,card);}
    RomSettings withCard(File value)throws IOException{return new RomSettings(displayName,resolution,scale,orientation,screenPosition,value);}
    JSONObject json()throws JSONException{return new JSONObject().put("displayName",displayName).put("resolution",resolution.name()).put("scale",scale.name()).put("orientation",orientation.name()).put("screenPosition",screenPosition.name()).put("storageCard",card.getPath());}
    static RomSettings parse(JSONObject o)throws IOException {
        try{return new RomSettings(o.getString("displayName"),GuestResolution.valueOf(o.getString("resolution")),ScaleMode.valueOf(o.getString("scale")),HostOrientation.valueOf(o.getString("orientation")),o.has("screenPosition")?ScreenPosition.valueOf(o.getString("screenPosition")):ScreenPosition.CENTER,new File(o.getString("storageCard")));}
        catch(JSONException|IllegalArgumentException e){throw new IOException("Invalid profile settings; retained data preserved",e);}
    }
}
