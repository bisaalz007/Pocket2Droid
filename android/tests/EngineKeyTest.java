package com.samsixx.pocket2droid;
import android.content.ContextWrapper;
import android.content.pm.ApplicationInfo;
import org.json.*;
import java.io.*;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import android.system.Os;
import java.util.*;
import java.util.concurrent.*;

/** Actual Engine worker/JSON commands on ART; fake process/control only. */
public final class EngineKeyTest {
    static void require(boolean b, String why) { if (!b) { System.err.println("FAIL Engine ART: " + why); throw new AssertionError(why); } }
    static void put(Object o, String n, Object v) throws Exception {
        Field f = Engine.class.getDeclaredField(n); f.setAccessible(true); f.set(o, v);
    }
    static Object get(Object o, String n) throws Exception {
        Field f = Engine.class.getDeclaredField(n); f.setAccessible(true); return f.get(o);
    }
    static class FakeProcess extends Process {
        boolean live = true;
        public int exitValue() { if (live) throw new IllegalThreadStateException(); return 0; }
        public int waitFor() { live = false; return 0; }
        public void destroy() { live = false; }
        public OutputStream getOutputStream() { return null; }
        public InputStream getInputStream() { return null; }
        public InputStream getErrorStream() { return null; }
    }
    static final class Control extends OutputStream {
        final PipedReader reader = new PipedReader();
        final PipedWriter reply;
        final List<Long> makes = new ArrayList<>(), breaks = new ArrayList<>();
        int ackDelay;
        Control() throws IOException { reply = new PipedWriter(reader); }
        public void write(int b) { throw new AssertionError("Expected complete command"); }
        public synchronized void write(byte[] b, int offset, int count) throws IOException {
            try {
                JSONObject call = new JSONObject(new String(b, offset, count, "UTF-8"));
                if (call.getString("execute").equals("input-send-event")) {
                    boolean down = call.getJSONObject("arguments").getJSONArray("events").getJSONObject(0).getJSONObject("data").getBoolean("down");
                    if (down && ackDelay > 0) Thread.sleep(ackDelay);
                    (down ? makes : breaks).add(System.nanoTime());
                }
                reply.write(new JSONObject().put("id", call.getInt("id")).put("return", new JSONObject()).toString() + "\n");
                reply.flush();
            } catch (Exception e) { throw new IOException(e); }
        }
        synchronized int breakCount() { return breaks.size(); }
    }
    static Engine create(File root, Control control) throws Exception {
        Engine e = new Engine(new ContextWrapper(null) {
            public File getFilesDir() { return root; }
            public ApplicationInfo getApplicationInfo() { ApplicationInfo a = new ApplicationInfo(); a.nativeLibraryDir = root.getPath(); return a; }
        }, text -> { }, new StorageLayout(new File(root,"pocket2droid"), new File(root,"private/tcg-v1")));
        require(e.storage.getParentFile().mkdirs(), "Fresh fixture directory");
        RandomAccessFile storage = new RandomAccessFile(e.storage, "rw"); storage.setLength(32L*1024*1024);
        put(e, "storageHandle", storage); put(e, "process", new FakeProcess());
        put(e, "output", control); put(e, "input", new BufferedReader(control.reader)); put(e, "desiredRunning", true);
        return e;
    }
    static Engine inactive(File root) {
        return new Engine(new ContextWrapper(null) {
            public ApplicationInfo getApplicationInfo() { ApplicationInfo a=new ApplicationInfo();a.nativeLibraryDir=root.getPath();return a; }
        }, text -> {}, new StorageLayout(new File(root,"pocket2droid"),new File(root,"private/tcg-v1")));
    }
    static void waitBreak(Control c) throws Exception {
        long deadline = System.nanoTime() + 2_000_000_000L;
        while (c.breakCount() == 0 && System.nanoTime() < deadline) Thread.sleep(2);
        require(c.breakCount() == 1, "One applied break");
    }
    static void close(Engine e) throws Exception {
        e.dispose(); ScheduledExecutorService w = (ScheduledExecutorService)get(e, "worker");
        require(w.awaitTermination(2, TimeUnit.SECONDS), "Worker cleanup");
    }
    public static void main(String[] args) throws Exception {
        File base = new File(args[0]); require(base.isDirectory(), "Owned test root");
        Engine launch=inactive(new File(base,"launch-arguments"));
        Method factory;
        try { factory=Engine.class.getDeclaredMethod("processBuilder"); }
        catch(NoSuchMethodException absent) { throw new AssertionError("Actual engine launch must expose its emitted machine options for verification",absent); }
        factory.setAccessible(true);
        File selectedRoot=new File(base,"selected/pocket2droid"),runtime=new File(base,"selected/private"),card=new File(base,"card, with spaces");
        require(card.mkdirs(),"Disposable custom card");
        RomSettings settings=RomSettings.defaults("OS B",card).withInternetAccess(false).withResolution(RomSettings.GuestResolution.SQUARE_VGA);
        File rom=new File(selectedRoot,"Roms/OS B.BIN"),backing=new File(selectedRoot,"data/OS B.BIN/ram-fmd.bin");
        RomProfile selected=new RomProfile("OS B.BIN",RomRepository.ICONS[0],rom,backing,settings,"READY",null);
        Engine selection=new Engine(new ContextWrapper(null){public ApplicationInfo getApplicationInfo(){ApplicationInfo a=new ApplicationInfo();a.nativeLibraryDir=base.getPath();return a;}},s->{},new StorageLayout(selectedRoot,runtime,selected));
        List<String> command=((ProcessBuilder)factory.invoke(selection)).command();
        require(command.get(command.indexOf("-bios")+1).equals(rom.getPath()),"Selected filename is passed as separate bios argument");
        require(command.get(command.indexOf("-machine")+1).contains("storage="+backing.getPath()),"Selected internal data is passed to the engine");
        require(command.get(command.indexOf("-machine")+1).contains("shared-folder="+card.getPath().replace(",",",,")),"Commas in selected card options are escaped");
        require(command.get(command.indexOf("-machine")+1).contains(",screen-width=480,screen-height=480"),"Persisted resolution reaches actual engine launch arguments");
        require(selection.cab==null,"Selected ROM has no game-specific CAB dependency");
        require(command.contains("-nic")&&command.get(command.indexOf("-nic")+1).equals("none")&&!command.contains("-netdev"),"Offline Engine has no backend");
        put(selection,"networkSetupFile",new File(base,"unused-setup.exe"));require(!selection.processBuilder().command().toString().contains("network-setup="),"Offline Engine never exposes prepared helper");
        RomProfile onlineProfile=new RomProfile(selected.filename,selected.iconId,rom,backing,settings.withInternetAccess(true),"READY",null);
        Engine onlineEngine=new Engine(new ContextWrapper(null){public ApplicationInfo getApplicationInfo(){ApplicationInfo a=new ApplicationInfo();a.nativeLibraryDir=base.getPath();return a;}},s->{},new StorageLayout(selectedRoot,runtime,onlineProfile));
        put(onlineEngine,"networkSetupFile",new File(base,"setup, private.exe"));
        List<String> onlineCommand=onlineEngine.processBuilder().command();
        require(onlineCommand.get(onlineCommand.indexOf("-machine")+1).contains(",network=on")&&onlineCommand.contains("user,id=p2dnet,ipv6=off")&&onlineCommand.toString().contains(onlineProfile.settings.networkMac),"Enabled Engine exposes optional card and user NAT with persisted MAC");require(onlineCommand.toString().contains("network-setup="+new File(base,"setup, private.exe").getPath().replace(",",",,")),"Eligible online profile passes exact escaped helper path");close(onlineEngine);
        JSONObject oldSettings=onlineProfile.settings.json();oldSettings.remove("networkSetupEligible");RomProfile oldProfile=new RomProfile(selected.filename,selected.iconId,rom,backing,RomSettings.parse(oldSettings),"READY",null);
        Engine oldEngine=new Engine(new ContextWrapper(null){public ApplicationInfo getApplicationInfo(){ApplicationInfo a=new ApplicationInfo();a.nativeLibraryDir=base.getPath();return a;}},s->{},new StorageLayout(selectedRoot,runtime,oldProfile));File legacyHelper=new File(base,"existing, profile.exe");put(oldEngine,"networkSetupFile",legacyHelper);require(oldEngine.processBuilder().command().toString().contains("network-setup="+legacyHelper.getPath().replace(",",",,")),"Existing Internet-On profile must deliver the guarded Work setup helper");close(oldEngine);
        RomProfile customProfile=new RomProfile(selected.filename,selected.iconId,rom,backing,settings.withCustomResolution(640,360),"READY",null);
        Engine customEngine=new Engine(new ContextWrapper(null){public ApplicationInfo getApplicationInfo(){ApplicationInfo a=new ApplicationInfo();a.nativeLibraryDir=base.getPath();return a;}},s->{},new StorageLayout(selectedRoot,runtime,customProfile));
        List<String> customCommand=((ProcessBuilder)factory.invoke(customEngine)).command();
        require(customCommand.get(customCommand.indexOf("-machine")+1).contains(",screen-width=640,screen-height=360"),"Custom width and height reach the actual native machine launch options");close(customEngine);
        require(selection.beginImport()&&Engine.activeProfileFilename().equals(selected.filename),"Guard retains selected filename");
        Engine challenger=inactive(new File(base,"challenger"));challenger.start();require(!challenger.starting,"Another ROM cannot steal a paused session");close(challenger);
        selection.endImport();CountDownLatch exited=new CountDownLatch(1);selection.close(ok->{require(ok&&!SessionGuard.busy(),"Exit callback follows ownership release");exited.countDown();});require(exited.await(2,TimeUnit.SECONDS),"Exit callback delivered");close(selection);
        List<String> arguments=((ProcessBuilder)factory.invoke(launch)).command();
        require(!arguments.contains("-object"),"Raw WM6 launch preserves anonymous RAM");
        int machineIndex=arguments.indexOf("-machine");require(machineIndex>=0,"Engine passes native machine options");
        Map<String,String> options=new HashMap<>();
        for(String option:arguments.get(machineIndex+1).split(",")) {
            int equal=option.indexOf('=');if(equal>=0)options.put(option.substring(0,equal),option.substring(equal+1));
        }
        File lock=new File(new File(base,"launch-arguments/private/tcg-v1"),"engine-storage.lock");
        require(lock.getPath().equals(options.get("storage-lock")),"Engine must request a stable private storage lock, not lock the public FUSE data file");
        require(new File(new File(base,"launch-arguments/private/tcg-v1"),"audio.bin").getPath().equals(options.get("audio-file")),
            "Engine audio transport must stay in private disposable runtime storage");
        require(launch.storage.getPath().equals(options.get("storage")) && launch.layout.sdcard.getPath().equals(options.get("shared-folder")),
            "Lock relocation keeps persistent data and guest Storage Card paths");
        require("240".equals(options.get("screen-width"))&&"320".equals(options.get("screen-height")),"Legacy callers preserve QVGA boot arguments");
        require(lock.getParentFile().mkdirs(),"Create only the task-owned private lock fixture");
        try(FileOutputStream out=new FileOutputStream(lock)) { out.write(37);out.getFD().sync(); }
        long inode=Os.stat(lock.getPath()).st_ino;
        close(launch);
        require(lock.isFile() && Os.stat(lock.getPath()).st_ino==inode,"Orderly cleanup retains the same lock inode");
        try(FileInputStream in=new FileInputStream(lock)) { require(in.read()==37,"Cleanup never truncates or replaces the stable private lock"); }
        Engine retained=create(new File(base,"wm5-retained"),new Control());
        File retainedFile=new File(retained.storage.getParentFile(),"wm5-sdram-fixture.bin");
        RandomAccessFile ram=new RandomAccessFile(retainedFile,"rw");ram.setLength(GuestRam.SIZE);ram.write(81);
        put(retained,"retainedRam",retainedFile);put(retained,"ramHandle",ram);
        List<String> ramCommand=((ProcessBuilder)factory.invoke(retained)).command();
        android.system.StructStat ramStat=Os.fstat(ram.getFD());
        require(ramCommand.get(ramCommand.indexOf("-machine")+1).contains(",ram-path="+retainedFile.getPath()),"WM5 uses its retained main RAM file");
        require(ramCommand.get(ramCommand.indexOf("-machine")+1).contains(",ram-identity="+Long.toHexString(ramStat.st_dev)+":"+Long.toHexString(ramStat.st_ino)),"Native RAM must match Android's actual open handle");
        require(!ramCommand.contains("-object"),"RAM backend cannot independently create a missing save");
        Method sync=Engine.class.getDeclaredMethod("syncStorage");sync.setAccessible(true);sync.invoke(retained);
        ram.setLength(1);
        try{sync.invoke(retained);throw new AssertionError("Invalid WM5 RAM must block successful save");}
        catch(java.lang.reflect.InvocationTargetException expected){require(expected.getCause() instanceof IOException,"RAM error reported as storage failure");}
        require(retained.busy(),"Failed RAM sync keeps ownership");
        ram.setLength(GuestRam.SIZE);close(retained);
        require(get(retained,"ramHandle")==null&&get(retained,"storageHandle")==null,"Normal close releases both synchronized storage handles");
        try(FileInputStream in=new FileInputStream(retainedFile)){require(in.read()==81,"Close preserves WM5 RAM bytes");}
        Engine retry=create(new File(base,"wm5-close-retry"),new Control());
        RandomAccessFile retryRam=new RandomAccessFile(new File(retry.storage.getParentFile(),"retained.bin"),"rw"){
            boolean fail=true;
            @Override public void close()throws IOException{if(fail){fail=false;throw new IOException("owned close failure");}super.close();}
        };
        retryRam.setLength(GuestRam.SIZE);put(retry,"ramHandle",retryRam);
        Method cleanup=Engine.class.getDeclaredMethod("cleanup");cleanup.setAccessible(true);
        final int[] unregistered={0};NetworkSession network=new NetworkSession(new NetworkSession.Source(){public List<java.net.InetAddress> current(){return Collections.emptyList();}public void register(Runnable changed){}public void unregister(){unregistered[0]++;}},new File(base,"owned-network"),Runnable::run,text->{});network.start();put(retry,"networkSession",network);
        require(!(Boolean)cleanup.invoke(retry)&&retry.busy(),"Partial close failure retains ownership and live handles");
        require(unregistered[0]==1&&!network.resolverFile().exists(),"Actual backend death closes DNS observer even if retained-storage close fails");
        require((Boolean)cleanup.invoke(retry)&&get(retry,"ramHandle")==null&&get(retry,"storageHandle")==null,"Retry closes both handles without reopening or resetting RAM");
        close(retry);
        Engine pending=create(new File(base,"network-pending"),new Control());
        final boolean[] pendingLive={true};put(pending,"process",new FakeProcess(){public int exitValue(){if(pendingLive[0])throw new IllegalThreadStateException();return 0;}public void destroy(){}});
        final int[] pendingClosed={0};NetworkSession pendingNetwork=new NetworkSession(new NetworkSession.Source(){public List<java.net.InetAddress> current(){return Collections.emptyList();}public void register(Runnable changed){}public void unregister(){pendingClosed[0]++;}},new File(base,"pending-dns"),Runnable::run,text->{});pendingNetwork.start();put(pending,"networkSession",pendingNetwork);
        require(!(Boolean)cleanup.invoke(pending)&&pendingClosed[0]==0&&pendingNetwork.resolverFile().exists(),"Shutdown pending retains network observer until actual process death");
        pendingLive[0]=false;require((Boolean)cleanup.invoke(pending)&&pendingClosed[0]==1,"Actual pending process death permits observer cleanup");close(pending);
        System.out.println("PASS Engine WM5 RAM: backend arguments, pause sync rejection, ownership and normal close");
        Control slow = new Control(); slow.ackDelay = 150;
        Engine e = create(new File(base, "slow"), slow);
        e.key("tab", true); e.key("tab", false); waitBreak(slow);
        require(slow.breaks.get(0) - slow.makes.get(0) >= 90_000_000L, "Hold starts after delayed down acknowledgement"); close(e);

        Control rapid = new Control(); e = create(new File(base, "rapid"), rapid);
        e.key("tab", true); e.key("tab", false); Thread.sleep(20);
        e.key("tab", true); e.key("tab", false); waitBreak(rapid);
        require(rapid.makes.size() == 1 && rapid.breaks.get(0)-rapid.makes.get(0) >= 90_000_000L, "Rapid taps coalesce without shortening hold"); close(e);

        Control paused = new Control(); e = create(new File(base, "paused"), paused);
        e.key("tab", true); e.key("tab", false); Thread.sleep(20);
        ScheduledExecutorService worker = (ScheduledExecutorService)get(e, "worker");
        CountDownLatch blocked = new CountDownLatch(1), release = new CountDownLatch(1);
        worker.execute(() -> { blocked.countDown(); try { release.await(); } catch (InterruptedException x) { Thread.currentThread().interrupt(); } });
        require(blocked.await(1, TimeUnit.SECONDS), "Worker blocked"); Thread.sleep(140);
        e.running(false); release.countDown(); waitBreak(paused);
        worker.submit(() -> {}).get(1, TimeUnit.SECONDS);
        require(((Map<?,?>)get(e,"held")).isEmpty(), "Pause clears ownership after actual break"); close(e);
        Engine first=inactive(new File(base,"ownership-first")),second=inactive(new File(base,"ownership-second"));
        require(first.beginImport(),"First import owns session");
        require(!first.beginImport() && !second.beginImport(),"Duplicate/recreated Activity import blocked");
        first.start();second.start();
        require(!first.starting && !second.starting,"Start cannot race active import across Activities");
        first.endImport();require(second.beginImport(),"Ownership transfers only after input completes");
        first.dispose();ScheduledExecutorService disposedWorker=(ScheduledExecutorService)get(first,"worker");
        require(disposedWorker.awaitTermination(2,TimeUnit.SECONDS),"Disposed inactive worker stopped");
        require(!first.beginImport(),"Disposed Activity cannot acquire new input ownership");
        require(!inactive(new File(base,"ownership-third")).beginImport(),"Closing other Activity cannot clear active owner");
        second.endImport();close(second);
        Engine restart=inactive(new File(base,"restart"));
        restart.close();ScheduledExecutorService restartWorker=(ScheduledExecutorService)get(restart,"worker");restartWorker.submit(()->{}).get(2,TimeUnit.SECONDS);
        CountDownLatch startHeld=new CountDownLatch(1),resumeStart=new CountDownLatch(1);
        restartWorker.execute(()->{startHeld.countDown();try{resumeStart.await();}catch(InterruptedException x){Thread.currentThread().interrupt();}});
        require(startHeld.await(1,TimeUnit.SECONDS),"Hold restart worker before launch");
        restart.start();AudioSession session=(AudioSession)get(restart,"audioSession");long token=session.begin();session.allow(token,true);
        boolean soundRestartReady=session.nativeEnabled();session.end(token);resumeStart.countDown();close(restart);
        require(soundRestartReady,"Start after Exit restores foreground sound intent without Home/resume");
        Engine delayed=create(new File(base,"delayed-consumer"),new Control());delayed.start();
        ScheduledExecutorService delayedWorker=(ScheduledExecutorService)get(delayed,"worker");delayedWorker.submit(()->{}).get(2,TimeUnit.SECONDS);
        AudioSession delayedSession=(AudioSession)get(delayed,"audioSession");long delayedToken=delayedSession.begin();put(delayed,"audioToken",delayedToken);
        Method callback=Engine.class.getDeclaredMethod("audioControl");callback.setAccessible(true);
        File sound=new File(base,"delayed-output.bin");try(RandomAccessFile f=new RandomAccessFile(sound,"rw")){f.setLength(AudioProtocol.SIZE);AudioProtocol.initialize(f.getChannel().map(java.nio.channels.FileChannel.MapMode.READ_WRITE,0,AudioProtocol.SIZE));}
        AudioPlayer consumer=new AudioPlayer(new ContextWrapper(null){public Object getSystemService(String name){return null;}},sound,text->{},(AudioPlayer.Control)callback.invoke(delayed));put(delayed,"audioPlayer",consumer);
        Field sinkField=AudioPlayer.class.getDeclaredField("sink");sinkField.setAccessible(true);Object sink=sinkField.get(consumer);
        CountDownLatch sinkHeld=new CountDownLatch(1),releaseSink=new CountDownLatch(1);
        Thread stuck=new Thread(()->{synchronized(sink){sinkHeld.countDown();try{releaseSink.await();}catch(InterruptedException x){Thread.currentThread().interrupt();}}});stuck.start();require(sinkHeld.await(1,TimeUnit.SECONDS),"Hold audio sink for delayed teardown");
        consumer.start(delayedToken);Thread.sleep(50);delayed.dispose();require(delayedWorker.awaitTermination(2,TimeUnit.SECONDS),"Storage cleanup finishes while audio teardown is pending");
        Engine next=inactive(new File(base,"after-delayed-consumer"));require(!next.beginImport(),"Live old consumer retains ownership and blocks reuse");
        releaseSink.countDown();stuck.join(1000);require(consumer.stop(1000),"Delayed audio consumer eventually finishes");
        long ownerDeadline=System.nanoTime()+1000000000L;boolean acquired=false;
        while(!acquired&&System.nanoTime()<ownerDeadline){acquired=next.beginImport();if(!acquired)Thread.sleep(2);}
        require(acquired,"Actual consumer completion releases disposed Engine ownership");next.endImport();close(next);
        System.out.println("PASS Engine sound lifecycle: Exit/Start foreground restored; delayed consumer retains then releases disposed ownership");
        System.out.println("PASS actual Engine ART: delayed ack, rapid re-press, due release before pause, import/start Activity ownership, private storage-lock argument/inode retained");
    }
}
