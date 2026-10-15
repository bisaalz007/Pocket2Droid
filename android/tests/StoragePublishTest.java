package com.samsixx.pocket2droid;
import java.io.*;

/** Root runs this only in a newly created task-owned Android directory. */
public final class StoragePublishTest {
    static void require(boolean b, String why) { if (!b) throw new AssertionError(why); }
    static void write(File f, int value) throws IOException {
        try(FileOutputStream out=new FileOutputStream(f)) { out.write(value);out.getFD().sync(); }
    }
    static int read(File f) throws IOException { try(FileInputStream in=new FileInputStream(f)) { return in.read(); } }
    public static void main(String[] args) throws Exception {
        File root=new File(args[0]);
        require(root.mkdir(), "Test root must be fresh; existing directories are refused");
        File pending=new File(root,"pending"),destination=new File(root,"published");
        write(pending,19);StoragePublish.publish(pending,destination);
        require(!pending.exists() && read(destination)==19,"Atomic publication on this filesystem");
        write(pending,23);
        boolean refused=false;try { StoragePublish.publish(pending,destination); } catch(IOException expected) { refused=true; }
        require(refused && read(pending)==23 && read(destination)==19,"Existing target cannot be replaced");
        boolean directorySync=StoragePublish.syncDirectory(root);
        System.out.println("PASS Android no-replace publication; directory fsync supported="+directorySync+"; root="+root);
        // Only the two exact files created above; never recursive cleanup.
        require(pending.delete() && destination.delete() && root.delete(),"Clean up owned test files");
    }
}
