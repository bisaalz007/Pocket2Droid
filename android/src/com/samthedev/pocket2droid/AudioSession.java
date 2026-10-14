package com.samthedev.pocket2droid;
/** Control intent only; late callbacks cannot grant output to a new session. */
final class AudioSession {
    private long token;private boolean live,sound=true,foreground,allowed;
    synchronized long begin(){token++;live=true;allowed=false;return token;}
    synchronized void end(long id){if(id==token){live=false;allowed=false;}}
    synchronized boolean current(long id){return live&&id==token;}
    synchronized void allow(long id,boolean value){if(current(id))allowed=value;}
    synchronized void sound(boolean value){sound=value;}
    synchronized void foreground(boolean value){foreground=value;}
    synchronized boolean nativeEnabled(){return live&&sound&&foreground&&allowed;}
}
