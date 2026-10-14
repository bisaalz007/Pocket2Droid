package com.samthedev.pocket2droid;
import java.util.Locale;

/** Quiet ordinary status; keep actionable failures visible without a status bar. */
final class SessionMessages {
    private String active;
    static boolean error(String value){
        if(value==null)return false;
        String s=value.toLowerCase(Locale.ROOT);
        return s.contains("error")||s.contains("unavailable")||s.contains("blocked")||
            s.contains("engine exited")||s.startsWith("wait for")||
            s.startsWith("sound disabled:")||s.startsWith("sound: unsupported");
    }
    boolean begin(String value){if(value.equals(active))return false;active=value;return true;}
    void dismiss(){active=null;}
}
