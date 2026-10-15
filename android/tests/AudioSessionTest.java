package com.samsixx.pocket2droid;
public final class AudioSessionTest {
    static void check(boolean b){if(!b)throw new AssertionError("Session gating");}
    public static void main(String[] args){
        AudioSession g=new AudioSession();g.foreground(true);long old=g.begin();g.allow(old,true);check(g.nativeEnabled());
        g.foreground(false);check(!g.nativeEnabled());g.allow(old,true);check(!g.nativeEnabled());
        g.foreground(true);g.sound(false);check(!g.nativeEnabled());g.sound(true);check(g.nativeEnabled());
        g.end(old);long next=g.begin();g.allow(old,true);check(!g.nativeEnabled());g.allow(next,true);check(g.nativeEnabled());
        g.end(old);check(g.nativeEnabled());g.end(next);check(!g.nativeEnabled());
        System.out.println("PASS session mute/pause/current-token gating and stale callback exclusion");
    }
}
