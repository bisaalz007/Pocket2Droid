package com.samsixx.pocket2droid;
import java.io.*;
import org.json.*;
public final class RomSettingsTest {
    static int checks;
    static void yes(boolean b,String why){if(!b)throw new AssertionError(why);checks++;}
    public static void main(String[] args)throws Exception {
        RomSettings s=RomSettings.defaults("ROM",new File("/tmp/card"));
        yes(s.scale==RomSettings.ScaleMode.FITTED&&s.resolution==RomSettings.GuestResolution.ROM_DEFAULT&&s.orientation==RomSettings.HostOrientation.PORTRAIT,"Safe display defaults");
        RomSettings round=RomSettings.parse(s.withOrientation(RomSettings.HostOrientation.LANDSCAPE).json());yes(round.orientation==RomSettings.HostOrientation.LANDSCAPE,"Settings JSON roundtrip");
        yes(RomSettings.parse(s.json().put("screenPosition","BOTTOM")).json().optString("screenPosition").equals("BOTTOM"),"Screen position survives profile JSON roundtrip");
        JSONObject legacy=s.json();legacy.remove("screenPosition");yes(RomSettings.parse(legacy).screenPosition==RomSettings.ScreenPosition.CENTER,"Existing profiles without a screen position remain centered");
        for(RomSettings.ScreenPosition position:RomSettings.ScreenPosition.values()){
            RomSettings placed=RomSettings.parse(s.withScreenPosition(position).json());
            yes(placed.screenPosition==position,"Every screen position persists");
            yes(placed.withDisplayName("Renamed").screenPosition==position&&placed.withScale(RomSettings.ScaleMode.PIXEL_PERFECT).screenPosition==position&&placed.withResolution(RomSettings.GuestResolution.WVGA).screenPosition==position&&placed.withOrientation(RomSettings.HostOrientation.LANDSCAPE).screenPosition==position&&placed.withCard(new File("/tmp/other-card")).screenPosition==position,"Changing another ROM setting preserves screen position");
        }
        for(Object invalid:new Object[]{"bogus",JSONObject.NULL,17}){
            try{RomSettings.parse(s.json().put("screenPosition",invalid));throw new AssertionError("Invalid screen position accepted");}catch(IOException expected){checks++;}
        }
        try{RomSettings.parse(s.json().put("scale","bogus"));throw new AssertionError("Invalid scale accepted");}catch(IOException expected){checks++;}
        yes(RomSettings.GuestResolution.WVGA.label.equals("WVGA (480×800)")&&RomSettings.GuestResolution.WVGA.supported(),"Board supports actual WVGA startup dimensions");
        yes(s.startupResolution("PPC_USA_GSM_VGA_SQUARE_VR.BIN")==RomSettings.GuestResolution.SQUARE_VGA,"SDK VGA Square default is 480x480");
        yes(s.startupResolution("ppc_usa_gsm_vga_square_vr (12).bin")==RomSettings.GuestResolution.SQUARE_VGA,"Collision suffix and lowercase retain SDK default");
        String[] annotated={"PPC_USA (240x320).BIN","PPC_USA_GSM_VR (240x320).BIN","PPC_USA_GSM_VGA_VR (480x640).BIN","PPC_USA_GSM_SQUARE_VR (240x240).BIN","PPC_USA_GSM_VGA_SQUARE_VR (480x480).BIN","PPC_USA_GSM_QVGA_VR (320x320).BIN"};
        RomSettings.GuestResolution[] wanted={RomSettings.GuestResolution.QVGA,RomSettings.GuestResolution.QVGA,RomSettings.GuestResolution.VGA,RomSettings.GuestResolution.SQUARE,RomSettings.GuestResolution.SQUARE_VGA,RomSettings.GuestResolution.SQUARE_QVGA};
        for(int i=0;i<annotated.length;i++){
            yes(s.startupResolution(annotated[i])==wanted[i],"Resolution annotation preserves SDK preset: "+annotated[i]);
            yes(s.startupResolution(annotated[i].toLowerCase(java.util.Locale.ROOT).replace(".bin"," (2).bin"))==wanted[i],"Annotated imports retain preset after collision rename: "+annotated[i]);
        }
        yes(s.startupResolution("PPC_USA_GSM_VGA_VR (480×640).BIN")==RomSettings.GuestResolution.VGA,"Multiplication-sign annotation retains SDK preset");
        yes(s.startupResolution("experiment (480x640).bin")==RomSettings.GuestResolution.QVGA,"Unfamiliar annotated names retain QVGA fallback");
        yes(s.startupResolution("experiment.bin")==RomSettings.GuestResolution.QVGA,"Unknown default is predictable QVGA");
        RomSettings explicit=RomSettings.parse(s.withResolution(RomSettings.GuestResolution.WVGA).json());
        yes(explicit.startupResolution("experiment.bin")==RomSettings.GuestResolution.WVGA,"Preset persists and overrides filename default");
        yes(explicit.startupResolution("PPC_USA_GSM_VGA_VR (480x640).BIN")==RomSettings.GuestResolution.WVGA,"Manual preset still overrides annotated filename");
        yes(RomSettings.GuestResolution.presets().length==9,"Dropdown offers nine actual resolution presets");
        for(RomSettings.GuestResolution preset:RomSettings.GuestResolution.presets())yes(preset!=RomSettings.GuestResolution.ROM_DEFAULT,"Legacy automatic value is not a dropdown option");
        java.nio.ByteBuffer frame=java.nio.ByteBuffer.allocate(FrameProtocol.SIZE).order(java.nio.ByteOrder.LITTLE_ENDIAN);
        frame.putInt(0,0x46443250);frame.putInt(4,1);frame.putInt(8,480);frame.putInt(12,800);frame.putInt(16,1);frame.putLong(24,1);
        yes(FrameProtocol.parse(frame).height==800,"Native WVGA height is accepted by actual Java protocol");
        DisplayTransform fitted=DisplayTransform.create(240,320,480,800,RomSettings.ScaleMode.FITTED,0,0);
        yes(fitted.scale==0.4f&&fitted.left==24f&&fitted.top==0,"Large ROM fitted into small viewport without changing guest dimensions");
        yes(fitted.touch(0,50)==null&&fitted.touch(120,160)[0]==240&&fitted.touch(120,160)[1]==400,"Letterbox rejection and transformed touch");
        DisplayTransform pixels=DisplayTransform.create(240,320,480,800,RomSettings.ScaleMode.PIXEL_PERFECT,0,0);
        yes(pixels.scale==1&&pixels.left==-120&&pixels.top==-240,"Pixel-perfect centers oversized image without shrinking");
        DisplayTransform panned=DisplayTransform.create(240,320,480,800,RomSettings.ScaleMode.PIXEL_PERFECT,999,999);
        yes(panned.left==0&&panned.top==0&&panned.touch(20,40)[0]==20,"Pan clamps to edge and touch uses actual viewport");
        yes(DisplayTransform.create(0,0,240,320,RomSettings.ScaleMode.FITTED,0,0).touch(1,1)==null,"Unavailable viewport refuses touch");
        RomSettings.ScreenPosition[] positions={RomSettings.ScreenPosition.TOP,RomSettings.ScreenPosition.CENTER,RomSettings.ScreenPosition.BOTTOM};
        float[] fittedTops={0,160,320},croppedTops={0,-240,-480};
        for(int i=0;i<positions.length;i++){
            DisplayTransform placed=DisplayTransform.create(240,640,240,320,RomSettings.ScaleMode.FITTED,positions[i],0,0);
            yes(placed.top==fittedTops[i]&&placed.scale==1&&placed.left==0,"Fitted image has the requested vertical alignment");
            int[] touch=placed.touch(120,fittedTops[i]+80);yes(touch[0]==120&&touch[1]==80,"Aligned touch targets the same guest point");
            yes(placed.touch(120,fittedTops[i]-1)==null&&placed.touch(120,fittedTops[i]+320)==null,"Bars above and below an aligned image refuse touch");
            DisplayTransform small=DisplayTransform.create(480,640,240,320,RomSettings.ScaleMode.PIXEL_PERFECT,positions[i],99,99);
            yes(small.left==120&&small.top==fittedTops[i]&&small.touch(119,fittedTops[i]+80)==null,"Small pixel-perfect image stays aligned and ignores pan");
            DisplayTransform cropped=DisplayTransform.create(240,320,480,800,RomSettings.ScaleMode.PIXEL_PERFECT,positions[i],0,0);
            yes(cropped.left==-120&&cropped.top==croppedTops[i]&&cropped.touch(120,40)[1]==40-croppedTops[i],"Oversized pixel-perfect alignment and touch agree");
            DisplayTransform start=DisplayTransform.create(240,320,480,800,RomSettings.ScaleMode.PIXEL_PERFECT,positions[i],999,999);
            DisplayTransform end=DisplayTransform.create(240,320,480,800,RomSettings.ScaleMode.PIXEL_PERFECT,positions[i],-999,-999);
            yes(start.left==0&&start.top==0&&end.left==-240&&end.top==-480,"Panning reaches both crop edges from every alignment");
            DisplayTransform landscape=DisplayTransform.create(640,240,320,240,RomSettings.ScaleMode.FITTED,positions[i],0,0);
            yes(landscape.top==0&&landscape.left==160&&landscape.touch(0,120)==null,"Full-height landscape images remain horizontally centered");
        }
        // A custom size must survive persistence and unrelated settings edits.
        RomSettings custom=RomSettings.parse(s.json().put("resolution","CUSTOM").put("customWidth",640).put("customHeight",360));
        yes(custom.json().getInt("customWidth")==640&&custom.json().getInt("customHeight")==360,"Custom dimensions survive profile JSON roundtrip");
        yes(custom.startupSize("PPC_USA_GSM_VGA_VR.BIN").width==640&&custom.startupSize("PPC_USA_GSM_VGA_VR.BIN").height==360,"Custom dimensions override filename-derived preset at launch");
        yes(custom.withResolution(RomSettings.GuestResolution.VGA).startupSize("x.bin").width==480&&custom.withResolution(RomSettings.GuestResolution.VGA).startupSize("x.bin").height==640,"Selecting a preset stops using the remembered custom dimensions");
        DisplayTransform customFit=DisplayTransform.create(400,400,640,360,RomSettings.ScaleMode.FITTED,0,0);
        yes(customFit.top==87.5f&&customFit.touch(200,200)[0]==320&&customFit.touch(200,200)[1]==180&&customFit.touch(200,87)==null,"Custom aspect ratio keeps display scaling and guest touch coordinates aligned");
        for(RomSettings edited:new RomSettings[]{custom.withDisplayName("Other"),custom.withScale(RomSettings.ScaleMode.PIXEL_PERFECT),custom.withOrientation(RomSettings.HostOrientation.LANDSCAPE),custom.withScreenPosition(RomSettings.ScreenPosition.BOTTOM),custom.withCard(new File("/tmp/new-card"))})
            yes(edited.json().getString("resolution").equals("CUSTOM")&&edited.json().getInt("customWidth")==640&&edited.json().getInt("customHeight")==360,"Unrelated settings retain custom dimensions");
        for(int[] size:new int[][]{{1,1},{1024,800},{641,479},{1280,960},{3840,2160},{Integer.MAX_VALUE,1}})
            yes(RomSettings.parse(s.json().put("resolution","CUSTOM").put("customWidth",size[0]).put("customHeight",size[1])).json().getInt("customWidth")==size[0],"Engine-supported custom size persists without rounding");
        for(Object[] size:new Object[][]{{0,320},{240,0},{-1,320},{2147483648L,320},{640.5,480},{"640",480},{JSONObject.NULL,480}}){
            try{RomSettings.parse(s.json().put("resolution","CUSTOM").put("customWidth",size[0]).put("customHeight",size[1]));throw new AssertionError("Invalid custom size accepted");}catch(IOException expected){checks++;}
        }
        try{RomSettings.parse(s.json().put("resolution","CUSTOM"));throw new AssertionError("Custom profile without dimensions accepted");}catch(IOException expected){checks++;}
        for(JSONObject partial:new JSONObject[]{s.json().put("customWidth",640),s.json().put("customHeight",480)}){
            try{RomSettings.parse(partial);throw new AssertionError("Incomplete custom dimensions accepted");}catch(IOException expected){checks++;}
        }
        try{s.withCustomResolution(0,320);throw new AssertionError("Invalid custom editor size accepted");}catch(IOException expected){checks++;}
        yes(RomSettings.parse(custom.withResolution(RomSettings.GuestResolution.VGA).json()).json().getInt("customWidth")==640,"Switching to a preset retains the last custom dimensions");
        System.out.println("PASS ROM settings/geometry "+checks+" assertions");
    }
}
