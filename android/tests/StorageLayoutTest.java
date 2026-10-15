package com.samsixx.pocket2droid;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Arrays;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Real temp files and the production no-replace syscall; no emulator or user data. */
public final class StorageLayoutTest {
    private static int checks;
    private static void require(boolean ok, String why) {
        if (!ok) throw new AssertionError(why);
        checks++;
    }
    private static void write(File f, String text) throws IOException {
        f.getParentFile().mkdirs();
        try (FileOutputStream out = new FileOutputStream(f)) { out.write(text.getBytes(StandardCharsets.UTF_8)); }
    }
    private static String text(File f) throws IOException {
        return new String(Files.readAllBytes(f.toPath()), StandardCharsets.UTF_8);
    }
    private static void guest(File f, int first) throws IOException {
        f.getParentFile().mkdirs();
        try (RandomAccessFile out = new RandomAccessFile(f, "rw")) {
            out.setLength(32L * 1024 * 1024); out.seek(0); out.write(first); out.getFD().sync();
        }
    }
    interface Work { void run() throws Exception; }
    private static void refused(Work action, String why) throws Exception {
        try { action.run(); throw new AssertionError(why); }
        catch (IOException expected) { checks++; }
    }
    private static StorageLayout layout(Path base, String name) {
        File f = base.resolve(name).toFile();
        return new StorageLayout(new File(f, "pocket2droid"), new File(f, "private/tcg-v1"));
    }
    public static void main(String[] args) throws Exception {
        Path base = args.length == 0 ? Files.createTempDirectory("p2d-storage-") : Paths.get(args[0]);
        Files.createDirectories(base);
        File general=base.resolve("isolation/shared").toFile(),appSpecific=base.resolve("isolation/test-app-external").toFile();
        File testRoot=StorageLayout.rootForPackage("com.samsixx.p2dtest",general,appSpecific);
        require(testRoot.equals(new File(general,".p2d-disposable-frontend/pocket2droid")),"Disposable package uses a reserved directory on the same general shared FUSE volume as production");
        require(StorageLayout.rootForPackage("com.samsixx.pocket2droid",general,appSpecific).equals(new File(general,"pocket2droid")),
            "Production package retains requested shared root");
        StorageLayout isolated=new StorageLayout(testRoot,base.resolve("isolation/test-private/tcg-v1").toFile());
        isolated.prepare();
        require(!new File(general,"pocket2droid").exists(),"Test preparation never creates files in production root");
        require(isolated.storage.isFile(),"Test still uses real app-owned external persistent file");
        require(StorageLayout.rootForPackage("com.samsixx.p2dtest",null,appSpecific)==null,"Unavailable general shared volume cannot fall back to app-specific pass-through storage");
        StorageLayout missing=new StorageLayout(null,base.resolve("unavailable/private/tcg-v1").toFile());
        refused(missing::prepare,"Unavailable external storage blocks instead of using private guest storage");
        require(!missing.runtime.exists(),"Unavailable preparation writes no runtime or guest files");
        StorageLayout a = layout(base, "migrate");
        write(new File(a.runtime, "PPC_USA.BIN"), "original ROM");
        write(new File(a.runtime, "RagingThunder.cab"), "original CAB");
        guest(new File(a.runtime, "ram-fmd.bin"), 17);
        write(new File(a.root.getParentFile(), "pocket2droidOld/keep.txt"), "user backup");
        a.prepare();
        require(a.rom.isFile(), "Migration publishes private ROM into external Roms");
        require(text(a.rom).equals("original ROM"), "Private ROM copied to Roms");
        require(text(a.cab).equals("original CAB"), "Private CAB copied to Storage Card");
        require(a.storage.length() == 32L * 1024 * 1024, "Save copied intact");
        require(new RandomAccessFile(a.storage, "r").read() == 17, "Save bytes preserved");
        require(new File(a.runtime, "ram-fmd.bin").isFile(), "Private rollback retained");
        require(text(new File(a.root.getParentFile(), "pocket2droidOld/keep.txt")).equals("user backup"), "Backup untouched");
        require(a.frames.getParentFile().equals(a.runtime) && a.control.getParentFile().equals(a.runtime)
                && a.temporary.getParentFile().equals(a.runtime), "Runtime paths remain private");
        guest(a.storage, 99); a.prepare();
        require(new RandomAccessFile(a.storage, "r").read() == 99, "Completed migration accepts later external save changes");

        StorageLayout b = layout(base, "conflict");
        guest(new File(b.runtime, "ram-fmd.bin"), 1); guest(b.storage, 2);
        refused(b::prepare, "Different existing external save must block automatic migration");
        require(new RandomAccessFile(b.storage, "r").read() == 2, "Conflicting external save is untouched");
        require(new RandomAccessFile(new File(b.runtime, "ram-fmd.bin"), "r").read() == 1, "Conflicting private save retained");

        StorageLayout c = layout(base, "preexisting");
        write(new File(c.runtime, "PPC_USA.BIN"), "private ROM"); write(c.rom, "user ROM");
        write(new File(c.sdcard, "user.txt"), "user file"); guest(c.storage, 7);
        c.prepare();
        require(text(c.rom).equals("user ROM") && text(new File(c.sdcard, "user.txt")).equals("user file"), "Preexisting files preserved");
        File published = new File(c.sdcard, "no-clobber"); File pending = new File(c.sdcard, "pending");
        write(published, "existing"); write(pending, "new");
        refused(() -> StoragePublish.publish(pending, published), "No-replace syscall must reject existing destination");
        require(text(published).equals("existing") && text(pending).equals("new"), "Failed publication preserves both files");

        StorageLayout d = layout(base, "partial");
        write(new File(d.runtime, "PPC_USA.BIN"), "ROM");
        guest(new File(d.runtime, "ram-fmd.bin"), 42); guest(d.storage, 42);
        write(d.rom, "ROM"); write(new File(d.data, "ram-fmd.bin.abandoned.pending"), "interrupted copy");
        d.prepare();
        require(new RandomAccessFile(d.storage, "r").read() == 42, "Crash after save publication safely completes migration");
        require(text(new File(d.data, "ram-fmd.bin.abandoned.pending")).equals("interrupted copy"), "Unowned partial files never reused/deleted");
        require(d.storage.delete(), "Remove test-only external save");
        refused(d::prepare, "Completed migration must not resurrect rollback after save removal");
        require(!d.storage.exists(), "Missing save remains absent, no reset");

        StorageLayout e = layout(base, "bad-size"); write(e.storage, "short");
        refused(e::prepare, "Malformed existing save must not be resized/reset");
        require(text(e.storage).equals("short"), "Malformed save bytes preserved");

        StorageLayout f = layout(base, "first-run"); f.prepare();
        require(f.storage.length() == 32L * 1024 * 1024, "First run creates persistent storage once");
        byte[] cab = new byte[36]; cab[0]='M';cab[1]='S';cab[2]='C';cab[3]='F';cab[8]=36;
        f.importCab(new ByteArrayInputStream(cab));
        require(Arrays.equals(cab, Files.readAllBytes(f.cab.toPath())), "Verified picker CAB goes to guest sdcard");
        f.importCab(new ByteArrayInputStream(cab));
        byte[] different = cab.clone(); different[35] = 1;
        refused(() -> f.importCab(new ByteArrayInputStream(different)), "Picker never replaces a different existing CAB");
        require(Arrays.equals(cab, Files.readAllBytes(f.cab.toPath())), "Existing CAB remains intact after conflict");
        byte[] alternateRom=new byte[100];alternateRom[0]=37;
        f.importRom(new ByteArrayInputStream(alternateRom));
        StorageLayout.verifyRom(f.rom);
        require(Arrays.equals(Files.readAllBytes(f.rom.toPath()),alternateRom),"Alternate ROM is imported without original hash or exact-size gate");
        refused(() -> f.importRom(new ByteArrayInputStream(new byte[]{91})),"Different imported ROM never overwrites existing ROM");
        require(f.rom.isFile(),"Existing alternate ROM remains intact");
        StorageLayout empty=layout(base,"empty-rom");empty.prepare();
        refused(()->empty.importRom(new ByteArrayInputStream(new byte[0])),"Empty ROM stays unpublished");
        require(!empty.rom.exists(),"Empty input cannot become selected ROM");
        write(empty.rom,"different experimental image");StorageLayout.verifyRom(empty.rom);
        require(text(empty.rom).equals("different experimental image"),"Manual renamed ROM accepted without hash gate");
        try(RandomAccessFile out=new RandomAccessFile(empty.rom,"rw")) { out.setLength(96L*1024*1024+1); }
        refused(()->StorageLayout.verifyRom(empty.rom),"Physical board flash capacity remains bounded");
        StorageLayout g = layout(base, "bad-cab"); g.prepare();
        refused(() -> g.importCab(new ByteArrayInputStream(new byte[36])), "Malformed CAB rejected");
        require(!g.cab.exists(), "Malformed CAB never reaches guest sdcard");

        StorageLayout h = layout(base, "symlink");
        File backup = new File(h.root.getParentFile(), "pocket2droidOld"); backup.mkdirs(); h.root.mkdirs();
        Files.createSymbolicLink(h.data.toPath(), backup.toPath());
        refused(h::prepare, "Data directory redirected into backup must be refused");
        require(!new File(backup, "ram-fmd.bin").exists(), "Symlink cannot modify renamed backup");

        StorageLayout i = layout(base, "interrupted-import"); i.prepare();
        refused(() -> i.importCab(new InputStream() {
            int count;
            public int read() throws IOException { if(count++==20) throw new IOException("Interrupted input");return 'M'; }
        }), "Interrupted import must not publish partial input");
        require(!i.cab.exists(), "Interrupted CAB remains unpublished");
        require(i.sdcard.list().length==0, "Interrupted import removes only its own temporary file");
        write(new File(i.runtime,"external-layout-v1.complete"), "torn migration checkpoint");
        refused(i::prepare, "Torn checkpoint must fail closed instead of remigrating/resetting");

        File raceDirectory = base.resolve("publish-race").toFile();raceDirectory.mkdirs();
        File raceTarget = new File(raceDirectory,"winner");
        ExecutorService pool=Executors.newFixedThreadPool(8);CountDownLatch go=new CountDownLatch(1);
        AtomicInteger winners=new AtomicInteger();Future<?>[] jobs=new Future[8];
        for(int n=0;n<8;n++) {
            final int value=n;File candidate=new File(raceDirectory,"candidate"+n);write(candidate,"writer"+n);
            jobs[n]=pool.submit(() -> {
                try { go.await();StoragePublish.publish(candidate,raceTarget);winners.incrementAndGet(); }
                catch(IOException alreadyExists) { }
                catch(InterruptedException stopped) { throw new AssertionError(stopped); }
            });
        }
        go.countDown();for(Future<?> job:jobs)job.get();pool.shutdown();
        require(winners.get()==1,"Concurrent publication has exactly one winner, no replacement");
        String winner=text(raceTarget);require(winner.startsWith("writer") && winner.length()==7,"Winner bytes are complete");
        int losers=0;for(File candidate:raceDirectory.listFiles())if(candidate.getName().startsWith("candidate"))losers++;
        require(losers==7,"Losing concurrently published files remain intact");
        System.out.println("PASS StorageLayout " + checks + " real filesystem assertions");
    }
}
