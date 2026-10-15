package com.samsixx.pocket2droid;
import java.io.*;
import java.util.Arrays;

/** Actual Android Java/JNI with freshly owned shared/private directories only. */
public final class StorageCompatibilityArtTest {
    private static int checks;
    private static void check(boolean b,String why) { if(!b) throw new AssertionError(why);checks++; }
    private static byte[] read(File f) throws Exception {
        try(FileInputStream in=new FileInputStream(f);ByteArrayOutputStream out=new ByteArrayOutputStream()) {
            byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1)out.write(b,0,n);return out.toByteArray();
        }
    }
    private static void clean(File f,File root) throws Exception {
        check(f.getCanonicalPath().equals(root.getCanonicalPath()) || f.getCanonicalPath().startsWith(root.getCanonicalPath()+File.separator),"Cleanup stays in owned test root");
        if(f.isDirectory()) { File[] children=f.listFiles();check(children!=null,"Owned directory readable");for(File c:children)clean(c,root); }
        check(f.delete(),"Remove owned test file");
    }
    public static void main(String[] args) throws Exception {
        File privateRoot=new File(args[0]),sharedRoot=new File(args[1]);
        check(privateRoot.getPath().startsWith("/data/local/tmp/.p2d-art-storage-") && sharedRoot.getPath().startsWith("/sdcard/.p2d-art-storage-"),"Disposable roots only");
        check(privateRoot.mkdir()&&sharedRoot.mkdir(),"Existing directories refused");
        StorageLayout layout=new StorageLayout(new File(sharedRoot,"pocket2droid"),new File(privateRoot,"tcg-v1"));
        layout.prepare();check(layout.storage.length()==32L*1024*1024,"First-run save created on actual shared filesystem");
        check(StoragePublish.syncDirectory(layout.data),"Shared directory fsync confirmed on this device");
        System.out.println("Actual shared-storage directory fsync supported=true");
        try(RandomAccessFile f=new RandomAccessFile(layout.storage,"rw")) { f.write(73);f.getFD().sync(); }
        layout.prepare();try(FileInputStream in=new FileInputStream(layout.storage)) {check(in.read()==73,"Changed save retained on restart");}
        byte[] rom={18,42,61,99};layout.importRom(new ByteArrayInputStream(rom));StorageLayout.verifyRom(layout.rom);
        check(Arrays.equals(read(layout.rom),rom),"Alternative ROM imported without original hash/size gate");
        boolean refused=false;try {layout.importRom(new ByteArrayInputStream(new byte[]{2}));}catch(IOException expected){refused=true;}
        check(refused&&Arrays.equals(read(layout.rom),rom),"Existing ROM preserved during conflicting import");
        File target=new File(layout.sdcard,"publish"),pending=File.createTempFile("publish.",".pending",layout.sdcard);
        try(FileOutputStream out=new FileOutputStream(pending)) {out.write(new byte[]{11,22});out.getFD().sync();}
        StoragePublish.publish(pending,target,layout.runtime);StoragePublish.cleanupPending(pending,layout.runtime);
        check(Arrays.equals(read(target),new byte[]{11,22}),"Production JNI fallback publishes complete bytes");
        pending=File.createTempFile("publish.",".pending",layout.sdcard);
        try(FileOutputStream out=new FileOutputStream(pending)) {out.write(77);out.getFD().sync();}
        refused=false;try{StoragePublish.publish(pending,target,layout.runtime);}catch(IOException expected){refused=true;}
        check(refused&&Arrays.equals(read(target),new byte[]{11,22})&&read(pending)[0]==77,"JNI cannot replace existing destination");
        int behaviorChecks=checks;clean(sharedRoot,sharedRoot);clean(privateRoot,privateRoot);
        System.out.println("PASS actual Android storage compatibility "+behaviorChecks+" behavior assertions; owned files cleaned; no emulator/user-data access");
    }
}
