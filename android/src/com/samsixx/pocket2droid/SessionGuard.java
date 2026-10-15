package com.samsixx.pocket2droid;

/** One owner across session startup, audio shutdown, and library filesystem work. */
final class SessionGuard {
    private static Object owner;
    private static String filename;
    static synchronized boolean claim(Object candidate,String name) {
        if(owner!=null&&owner!=candidate)return false;
        owner=candidate;filename=name;return true;
    }
    static synchronized void release(Object candidate){if(owner==candidate){owner=null;filename=null;}}
    static synchronized boolean busy(){return owner!=null;}
    static synchronized String filename(){return filename;}
}
