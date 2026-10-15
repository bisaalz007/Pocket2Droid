package com.samsixx.pocket2droid;
public final class SessionMessagesTest {
    public static void main(String[] args){
        for(String value:new String[]{"Sound disabled: Wrong audio buffer size","Sound disabled: invalid PCM","Sound disabled: incomplete stereo write","Sound: unsupported guest IIS format","Engine error: permission denied","Engine exited (code 1); see engine.log","Storage sync/close error: failed","Sound shutdown pending; restart blocked"})
            if(!SessionMessages.error(value))throw new AssertionError("Hidden actionable failure: "+value);
        for(String value:new String[]{"Sound enabled","Sound muted","Sound playing (44100 Hz)","Running TCG","Paused; storage flushed","Stopped"})
            if(SessionMessages.error(value))throw new AssertionError("Normal status shown as error: "+value);
        SessionMessages gate=new SessionMessages();
        if(!gate.begin("failed")||gate.begin("failed"))throw new AssertionError("Active duplicate not coalesced");
        gate.dismiss();if(!gate.begin("failed"))throw new AssertionError("Retry failure hidden after dismiss");
        System.out.println("PASS actionable audio/engine/storage failures, quiet normal status, retry notification");
    }
}
