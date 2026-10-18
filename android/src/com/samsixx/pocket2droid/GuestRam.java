package com.samsixx.pocket2droid;
import java.io.*;
import java.util.Arrays;

/** WM5 download images keep their object store in SDRAM across CPU resets. */
final class GuestRam {
    static final long SIZE=128L*1024*1024;
    private static final byte[] MAGIC={'B','0','0','0','F','F','\n'};
    static File prepare(File rom,File directory,File runtime)throws IOException{
        byte[] header=new byte[MAGIC.length];
        try(DataInputStream in=new DataInputStream(new FileInputStream(rom))){
            try{in.readFully(header);}catch(EOFException raw){return null;}
        }
        if(!Arrays.equals(header,MAGIC))return null;
        ProfileFiles.plain(directory);ProfileFiles.plain(runtime);
        if(!directory.isDirectory()||!runtime.isDirectory())throw new IOException("RAM storage folders unavailable");
        // Exact ROM identity prevents using another image's retained object store.
        File ram=new File(directory,"wm5-sdram-"+StorageLayout.digest(rom)+".bin");
        File checkpoint=new File(directory,ram.getName()+".ready");
        String ready="Pocket2Droid WM5 RAM 1\n"+ram.getName()+"\n"+SIZE+"\n";
        ProfileFiles.plain(ram);ProfileFiles.plain(checkpoint);
        if(checkpoint.exists()&&!ProfileFiles.read(checkpoint).equals(ready))throw new IOException("Invalid WM5 RAM checkpoint; existing files preserved");
        if(checkpoint.exists()&&!ram.exists())throw new IOException("Established WM5 RAM is missing; automatic reset blocked");
        if(ram.exists()){
            if(!ram.isFile()||ram.length()!=SIZE)throw new IOException("WM5 retained RAM has the wrong size; existing file preserved");
            ready(ram,checkpoint,ready,runtime);
            return ram;
        }
        File pending=File.createTempFile(ram.getName()+".",".pending",directory);
        try{
            try(RandomAccessFile f=new RandomAccessFile(pending,"rw")){
                f.setLength(SIZE);f.getFD().sync();
            }
            if(pending.length()!=SIZE)throw new IOException("Cannot prepare WM5 retained RAM");
            StoragePublish.publish(pending,ram,runtime);
            ready(ram,checkpoint,ready,runtime);
            return ram;
        }finally{StoragePublish.cleanupPending(pending,runtime);}
    }
    private static void ready(File ram,File checkpoint,String text,File runtime)throws IOException{
        // Retry file/directory durability even after a rename succeeded but sync
        // failed. Do not turn a retry into an implicit successful save reset.
        try(RandomAccessFile f=new RandomAccessFile(ram,"rw")){f.getFD().sync();}
        if(!StoragePublish.syncDirectory(ram.getParentFile()))throw new IOException("Cannot sync WM5 RAM publication; Start blocked");
        if(!checkpoint.exists()){
            File pending=File.createTempFile(checkpoint.getName()+".",".pending",checkpoint.getParentFile());
            try{
                ProfileFiles.write(pending,text);
                StoragePublish.publish(pending,checkpoint,runtime);
            }finally{StoragePublish.cleanupPending(pending,runtime);}
        }
        if(!ProfileFiles.read(checkpoint).equals(text)||!StoragePublish.syncDirectory(checkpoint.getParentFile()))throw new IOException("Cannot verify durable WM5 RAM checkpoint; Start blocked");
    }
}
