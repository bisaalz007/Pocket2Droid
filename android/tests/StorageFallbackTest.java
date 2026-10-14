package com.samthedev.pocket2droid;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Real production layout/JNI on filesystems with an unsupported rename operation. */
public final class StorageFallbackTest {
    private static native void failAfter(long bytes);
    private static native void directoryFault(String path,int fault,int nth);
    private static int checks;
    private static void check(boolean ok,String why) { if(!ok) throw new AssertionError(why);checks++; }
    private interface Work { void run() throws Exception; }
    private static void refused(Work action,String why) throws Exception {
        try { action.run();throw new AssertionError(why); } catch(IOException expected) { checks++; }
    }
    private static StorageLayout layout(File base,String name) {
        File dir=new File(base,name);return new StorageLayout(new File(dir,"shared/pocket2droid"),new File(dir,"private/tcg-v1"));
    }
    private static File[] records(StorageLayout l) {
        return l.runtime.listFiles((d,n)->n.startsWith(".storage-publication-")&&n.endsWith(".incomplete"));
    }
    public static void main(String[] args) throws Exception {
        File base=Files.createTempDirectory("p2d-fallback-").toFile();
        StorageLayout layout=new StorageLayout(new File(base,"shared/pocket2droid"),new File(base,"private/tcg-v1"));
        try { layout.prepare(); }
        catch(IOException failure) { throw new AssertionError("Unsupported storage must create its first complete save safely",failure); }
        check(layout.storage.length()==32L*1024*1024,"Complete first save");
        check(records(layout).length==0,"Completed fallback retires its record");
        try(RandomAccessFile f=new RandomAccessFile(layout.storage,"rw")) { f.write(61);f.getFD().sync(); }
        layout.prepare();
        try(FileInputStream in=new FileInputStream(layout.storage)) { check(in.read()==61,"Normal restart retains changed save"); }

        StorageLayout interrupted=layout(base,"interrupted");failAfter(4);
        refused(interrupted::prepare,"Interrupted native copy must fail");failAfter(-1);
        check(interrupted.storage.length()==4,"Interrupted copy remains partial");
        check(records(interrupted).length==1,"Interruption retains durable record");
        File[] pending=interrupted.data.listFiles((d,n)->n.endsWith(".pending"));
        check(pending.length==1 && pending[0].length()==32L*1024*1024,"Prepared source remains complete");
        refused(interrupted::prepare,"Partial save must block next Start");
        try(RandomAccessFile f=new RandomAccessFile(interrupted.storage,"rw")) { f.setLength(32L*1024*1024);f.seek(f.length()-1);f.write(99);f.getFD().sync(); }
        refused(interrupted::prepare,"Full-size corrupt copy must also block Start");
        check(pending[0].exists(),"Failed recovery retains prepared source");
        try(RandomAccessFile f=new RandomAccessFile(interrupted.storage,"rw")) { f.seek(f.length()-1);f.write(0);f.getFD().sync(); }
        interrupted.prepare();
        check(records(interrupted).length==0,"Already complete interrupted publication recovers");
        check(new File(interrupted.runtime,"external-layout-v1.complete").isFile(),"Recovery finishes preparation");

        File source=File.createTempFile("winner.",".pending",layout.sdcard), target=new File(layout.sdcard,"winner");
        Files.write(source.toPath(),new byte[]{11,22,33});Files.write(target.toPath(),new byte[]{77});
        refused(()->StoragePublish.publish(source,target,layout.runtime),"Existing target must be preserved on fallback");
        check(Arrays.equals(Files.readAllBytes(target.toPath()),new byte[]{77}),"Existing target bytes unchanged");
        check(Arrays.equals(Files.readAllBytes(source.toPath()),new byte[]{11,22,33}),"Losing source retained");
        check(records(layout).length==0,"Refused existing target leaves no blocking record");

        File raceTarget=new File(layout.sdcard,"race");ExecutorService pool=Executors.newFixedThreadPool(8);
        CountDownLatch go=new CountDownLatch(1);AtomicInteger winners=new AtomicInteger();List<Future<?>> jobs=new ArrayList<>();
        for(int n=0;n<8;n++) {
            final byte value=(byte)n;File candidate=File.createTempFile("race.",".pending",layout.sdcard);
            Files.write(candidate.toPath(),new byte[]{value,value});
            jobs.add(pool.submit(()->{ try { go.await();StoragePublish.publish(candidate,raceTarget,layout.runtime);winners.incrementAndGet(); }
                catch(IOException exists) { } catch(InterruptedException stopped) { throw new AssertionError(stopped); } }));
        }
        go.countDown();for(Future<?> job:jobs) job.get();pool.shutdown();
        byte[] winner=Files.readAllBytes(raceTarget.toPath());
        check(winners.get()==1 && winner.length==2 && winner[0]==winner[1],"Concurrent writers publish one complete winner");
        check(records(layout).length==0,"Concurrent losing attempts retire their unused records");

        StorageLayout unsynced=layout(base,"unsynced");
        directoryFault(unsynced.data.getAbsolutePath(),1,0);
        refused(unsynced::prepare,"Unsupported shared directory fsync must block completion");
        check(unsynced.storage.length()==32L*1024*1024 && records(unsynced).length==1,
            "Unsynced publication retains complete destination and recovery record");
        File[] retained=unsynced.data.listFiles((d,n)->n.endsWith(".pending"));
        check(retained.length==1 && retained[0].length()==32L*1024*1024,"Unsynced publication retains prepared bytes");
        refused(unsynced::prepare,"Recovery must retain record while directory sync unsupported");
        check(records(unsynced).length==1 && retained[0].exists(),"Repeated sync failure retains recovery material");
        directoryFault("",0,0);unsynced.prepare();
        check(records(unsynced).length==0,"Recovery retires record only after directory sync succeeds");

        StorageLayout retirement=layout(base,"retirement");
        directoryFault(retirement.runtime.getAbsolutePath(),2,2);
        refused(retirement::prepare,"Journal-retirement fsync failure must report failure");
        directoryFault("",0,0);
        check(retirement.storage.length()==32L*1024*1024,"Retirement failure preserves durable complete destination");
        try(RandomAccessFile f=new RandomAccessFile(retirement.storage,"rw")) { f.write(88);f.getFD().sync(); }
        retirement.prepare();
        try(FileInputStream in=new FileInputStream(retirement.storage)) { check(in.read()==88,"Restart after retirement failure preserves existing destination"); }

        StorageLayout bad=layout(base,"torn");bad.prepare();
        Files.write(new File(bad.runtime,".storage-publication-torn.incomplete").toPath(),new byte[]{1});
        refused(bad::prepare,"Torn recovery record must fail closed even after migration");
        System.out.println("PASS StorageFallback "+checks+" actual Java/JNI assertions");
    }
}
