package com.samsixx.pocket2droid;
import java.io.*;
import java.nio.file.*;
import java.util.Arrays;

/** Production publication and files; no guest or user storage. */
public final class GuestRamTest {
    private static native void directoryFault(String path,int fault,int nth);
    private static native void failAfter(long bytes);
    static int checks;
    static void check(boolean value,String why){if(!value)throw new AssertionError(why);checks++;}
    interface Action{void run()throws Exception;}
    static void refused(Action action)throws Exception{try{action.run();throw new AssertionError("Expected preserved-file rejection");}catch(IOException expected){checks++;}}
    static void write(File f,byte[] b)throws Exception{try(FileOutputStream out=new FileOutputStream(f)){out.write(b);}}
    public static void main(String[] args)throws Exception{
        File root=Files.createTempDirectory("p2d-wm5-ram-").toFile(),data=new File(root,"shared/pocket2droid/data"),runtime=new File(root,"private");
        check(data.mkdirs()&&runtime.mkdir(),"Owned folders");
        File rom=new File(root,"original.bin");byte[] raw={1,2,3,4};write(rom,raw);
        check(GuestRam.prepare(rom,data,runtime)==null,"Raw WM6 leaves RAM anonymous");
        check(data.list().length==0,"Raw launch creates no new save file");
        byte[] original="B000FF\nSDK record fixture".getBytes("US-ASCII");write(rom,original);
        File ram=GuestRam.prepare(rom,data,runtime);
        check(ram.length()==128L*1024*1024,"WM5 gets 128 MiB retained RAM");
        check(ram.getName().contains(StorageLayout.digest(rom)),"Retained RAM belongs to exact ROM bytes");
        try(RandomAccessFile f=new RandomAccessFile(ram,"rw")){f.seek(0x12345);f.write(77);f.getFD().sync();}
        check(GuestRam.prepare(rom,data,runtime).equals(ram),"Existing compatible RAM reused");
        try(RandomAccessFile f=new RandomAccessFile(ram,"r")){f.seek(0x12345);check(f.read()==77,"Existing contents never cleared");}
        File moved=new File(data,"owned-save-backup");check(ram.renameTo(moved),"Move only owned save fixture");
        refused(()->GuestRam.prepare(rom,data,runtime));check(!ram.exists(),"Missing established RAM is never recreated");
        check(moved.renameTo(ram),"Restore only owned save fixture");
        File checkpoint=new File(data,ram.getName()+".ready");check(checkpoint.isFile(),"Durable initialization checkpoint");
        check(checkpoint.delete(),"Simulate interrupted initial checkpoint publication");
        check(GuestRam.prepare(rom,data,runtime).equals(ram)&&checkpoint.isFile(),"Complete checkpoint after interrupted initialization");
        try(RandomAccessFile f=new RandomAccessFile(ram,"r")){f.seek(0x12345);check(f.read()==77,"Initialization recovery preserves RAM bytes");}
        byte[] ready=Files.readAllBytes(checkpoint.toPath());write(checkpoint,new byte[]{1});
        refused(()->GuestRam.prepare(rom,data,runtime));write(checkpoint,ready);
        directoryFault(data.getAbsolutePath(),1,0);
        refused(()->GuestRam.prepare(rom,data,runtime));refused(()->GuestRam.prepare(rom,data,runtime));
        directoryFault("",0,0);check(GuestRam.prepare(rom,data,runtime).equals(ram),"Retry rechecks directory durability");
        byte[] changed=original.clone();changed[changed.length-1]^=1;write(rom,changed);
        File other=GuestRam.prepare(rom,data,runtime);
        check(!other.equals(ram)&&ram.exists(),"Different ROM cannot reuse or delete old RAM");
        byte[] unsynced=original.clone();unsynced[unsynced.length-2]^=2;write(rom,unsynced);
        directoryFault(data.getAbsolutePath(),1,0);
        refused(()->GuestRam.prepare(rom,data,runtime));refused(()->GuestRam.prepare(rom,data,runtime));
        directoryFault("",0,0);StoragePublish.recover(runtime,root);
        check(GuestRam.prepare(rom,data,runtime).length()==GuestRam.SIZE,"Interrupted initial publication recovers without reset");
        write(rom,original);
        try(RandomAccessFile f=new RandomAccessFile(ram,"rw")){f.setLength(17);}
        refused(()->GuestRam.prepare(rom,data,runtime));check(ram.length()==17,"Wrong-sized existing file preserved");
        File target=new File(root,"personal-file");write(target,new byte[]{9,8,7});
        check(ram.delete(),"Remove only owned corrupt fixture");Files.createSymbolicLink(ram.toPath(),target.toPath());
        refused(()->GuestRam.prepare(rom,data,runtime));check(Arrays.equals(Files.readAllBytes(target.toPath()),new byte[]{9,8,7}),"Symlink target unchanged");
        check(Arrays.equals(Files.readAllBytes(rom.toPath()),original),"ROM preserved");
        if(System.getenv("P2D_TEST_STORAGE_UNSUPPORTED")!=null){
            write(rom,"B000FF\ninterrupted copy".getBytes("US-ASCII"));
            failAfter(4);refused(()->GuestRam.prepare(rom,data,runtime));failAfter(-1);
            refused(()->GuestRam.prepare(rom,data,runtime));
            check(runtime.listFiles((d,n)->n.endsWith(".incomplete")).length==1,"Interrupted copy retains recovery material");
        }
        System.out.println("PASS GuestRam: "+checks+" checks; exact-ROM retention, raw isolation, corrupt-file and redirected-path preservation");
    }
}
