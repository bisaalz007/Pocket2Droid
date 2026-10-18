package com.samsixx.pocket2droid;
import java.io.*;import java.util.*;import java.security.SecureRandom;import org.json.*;
public final class NetworkConfigTest {
    static int checks;static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);checks++;}
    public static void main(String[] args)throws Exception {
        RomSettings original=RomSettings.defaults("ROM",new File("/tmp/card"));
        check(original.internetEnabled&&NetworkConfig.validMac(original.networkMac),"A new profile is ready for an online launch with its own valid MAC");
        JSONObject legacy=original.json();legacy.remove("internetEnabled");legacy.remove("networkMac");legacy.remove("networkSetupEligible");check(!RomSettings.parse(legacy).internetEnabled&&!RomSettings.parse(legacy).networkSetupEligible,"Missing fields preserve legacy Off/manual behavior");
        RomSettings on=original.withInternetAccess(true),other=RomSettings.defaults("Other ROM",new File("/tmp/card"));
        RomSettings savedOff=original.withInternetAccess(false);
        check(!RomSettings.parse(savedOff.json()).internetEnabled,"Saved Off remains Off after loading with new defaults");
        check(RomSettings.parse(original.json()).internetEnabled,"Saved On remains On");
        check(!on.networkMac.equals(other.networkMac),"Independent profiles get different MACs");
        check(on.networkMac.equals(on.withInternetAccess(false).withInternetAccess(true).networkMac),"Off/On keeps MAC identity");
        check(RomSettings.parse(on.json()).networkMac.equals(on.networkMac),"Profile JSON retains MAC");
        for(RomSettings edited:new RomSettings[]{on.withDisplayName("New"),on.withScale(RomSettings.ScaleMode.PIXEL_PERFECT),on.withResolution(RomSettings.GuestResolution.VGA),on.withCustomResolution(240,500),on.withOrientation(RomSettings.HostOrientation.LANDSCAPE),on.withScreenPosition(RomSettings.ScreenPosition.TOP),on.withCard(new File("/tmp/other"))})check(edited.internetEnabled&&edited.networkSetupEligible&&edited.networkMac.equals(on.networkMac),"Other settings preserve networking and eligibility");
        for(Object v:new Object[]{"true",1,JSONObject.NULL}){
            try{RomSettings.parse(original.json().put("internetEnabled",v));throw new AssertionError("Invalid enabled type accepted");}catch(IOException expected){checks++;}
        }
        for(Object v:new Object[]{"",17,JSONObject.NULL,"ff:12:34:56:78:90","00:12:34:56:78:90","02:12:34:56:78:90,netdev=evil"}){
            try{RomSettings.parse(on.json().put("networkMac",v));throw new AssertionError("Invalid MAC accepted");}catch(IOException expected){checks++;}
        }
        JSONObject missing=on.json();missing.remove("networkMac");try{RomSettings.parse(missing);throw new AssertionError("Enabled profile without MAC accepted");}catch(IOException expected){checks++;}
        for(int i=0;i<100;i++){String mac=NetworkConfig.newMac(new SecureRandom());check(mac.matches("[0-9a-f]{2}(:[0-9a-f]{2}){5}")&&(Integer.parseInt(mac.substring(0,2),16)&3)==2,"MAC local/unicast");}
        List<String> off=new ArrayList<>();NetworkConfig.appendArguments(off,false,null);check(off.equals(Arrays.asList("-nic","none")),"Offline has no backend");
        List<String> online=new ArrayList<>();NetworkConfig.appendArguments(online,true,on.networkMac);check(online.equals(Arrays.asList("-netdev","user,id=p2dnet,ipv6=off","-net","nic,model=ne2k_pcmcia,netdev=p2dnet,macaddr="+on.networkMac)),"Enabled launch has only user-mode backend");
        try{NetworkConfig.appendArguments(new ArrayList<>(),true,"bad,hostfwd=tcp::1-:2");throw new AssertionError("Unsafe MAC accepted");}catch(IllegalArgumentException expected){checks++;}
        System.out.println("Network config: "+checks+" checks passed");
    }
}
