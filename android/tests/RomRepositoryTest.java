package com.samsixx.pocket2droid;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import org.json.*;

public final class RomRepositoryTest {
    static int checks;
    interface Work { void run() throws Exception; }
    static void yes(boolean value,String why){if(!value)throw new AssertionError(why);checks++;}
    static void refused(Work w,String why)throws Exception{try{w.run();throw new AssertionError(why);}catch(IOException expected){checks++;}}
    static void write(File f,String s)throws Exception{f.getParentFile().mkdirs();Files.write(f.toPath(),s.getBytes("UTF-8"));}
    static void save(File f,int value)throws Exception{f.getParentFile().mkdirs();try(RandomAccessFile r=new RandomAccessFile(f,"rw")){r.setLength(StorageLayout.STORAGE_SIZE);r.write(value);r.getFD().sync();}}
    static int first(File f)throws Exception{try(FileInputStream in=new FileInputStream(f)){return in.read();}}
    static String text(File f)throws Exception{return new String(Files.readAllBytes(f.toPath()),"UTF-8");}
    static RomRepository repo(File base,File card)throws Exception{return new RomRepository(new File(base,"pocket2droid"),new File(base,"private"),card,new Random(4));}
    static File cardCopy(RomRepository repository,InputStream input,String name)throws Exception {
        try{return (File)RomRepository.class.getDeclaredMethod("importCardFile",InputStream.class,String.class).invoke(repository,input,name);}
        catch(NoSuchMethodException missing){throw new AssertionError("File to StorageCard copy is not implemented",missing);}
        catch(java.lang.reflect.InvocationTargetException failed){if(failed.getCause() instanceof IOException)throw (IOException)failed.getCause();throw failed;}
    }
    static void cardImports()throws Exception {
        File base=Files.createTempDirectory("p2d-card-import-").toFile(),custom=new File(base,"older-custom-default");custom.mkdir();
        RomRepository repository=repo(base,custom);File fixed=new File(base,"pocket2droid/storagecard");
        byte[] bytes={0,1,2,3,(byte)255};
        File file=cardCopy(repository,new ByteArrayInputStream(bytes),"Game.CAB");
        yes(file.equals(new File(fixed,"Game.CAB"))&&Arrays.equals(Files.readAllBytes(file.toPath()),bytes),"Any file is copied byte-for-byte to the fixed card, ignoring custom defaults");
        yes(custom.list().length==0&&!new File(base,"pocket2droid/Roms/Game.CAB").exists(),"Card import does not touch another folder or add a ROM");
        File duplicate=cardCopy(repository,new ByteArrayInputStream(new byte[]{9}),"Game.CAB");
        yes(duplicate.getName().equals("Game (1).CAB")&&Arrays.equals(Files.readAllBytes(file.toPath()),bytes),"First duplicate receives a suffix without replacing existing bytes");
        yes(cardCopy(repository,new ByteArrayInputStream(new byte[]{8}),"Game.CAB").getName().equals("Game (2).CAB"),"Further duplicate receives the next suffix");
        File folder=new File(fixed,"notes.txt");folder.mkdir();
        yes(cardCopy(repository,new ByteArrayInputStream(new byte[]{7}),"notes.txt").getName().equals("notes (1).txt")&&folder.isDirectory(),"A same-name directory is preserved");
        File empty=cardCopy(repository,new ByteArrayInputStream(new byte[0]),".nomedia");
        yes(empty.isFile()&&empty.length()==0,"Zero-byte files and valid leading-dot names are accepted");
        File shortFile;try{shortFile=cardCopy(repository,new ByteArrayInputStream(bytes),"x");}
        catch(Exception failure){throw new AssertionError("A one-character filename must copy normally",failure);}
        yes(shortFile.getName().equals("x")&&Arrays.equals(Files.readAllBytes(shortFile.toPath()),bytes),"One-character filename is retained without a temporary-prefix error");
        File binary=cardCopy(repository,new ByteArrayInputStream(bytes),"device.BIN");
        yes(binary.exists()&&!new File(base,"pocket2droid/data/device.BIN/profile.json").exists(),"BIN copied as a card file does not create a ROM profile");
        for(String invalid:new String[]{"../escape","/absolute","bad\\path",".","..","line\nbreak","",null})
            refused(()->cardCopy(repository,new ByteArrayInputStream(bytes),invalid),"Unsafe card filename cannot escape the selected destination");
        File source=new File(base,"original.exe");Files.write(source.toPath(),bytes);
        try(InputStream in=new FileInputStream(source)){cardCopy(repository,in,source.getName());}
        yes(Arrays.equals(Files.readAllBytes(source.toPath()),bytes),"Original selected file remains unchanged");
        InputStream failing=new InputStream(){int reads;public int read()throws IOException{throw new IOException("Interrupted provider");}public int read(byte[] buffer,int offset,int length)throws IOException{if(reads++>0)throw new IOException("Interrupted provider");buffer[offset]=1;return 1;}};
        refused(()->cardCopy(repository,failing,"partial.dat"),"An interrupted document stream fails safely");
        yes(!new File(fixed,"partial.dat").exists()&&Arrays.stream(fixed.list()).noneMatch(name->name.endsWith(".pending")),"Failed copy publishes no partial file and retires its owned temporary input");
        File race=new File(fixed,"race.dat");
        InputStream racing=new ByteArrayInputStream(bytes){boolean created;@Override public int read(byte[] buffer,int offset,int length){if(!created){created=true;try{Files.write(race.toPath(),new byte[]{77});}catch(IOException e){throw new RuntimeException(e);}}return super.read(buffer,offset,length);}};
        refused(()->cardCopy(repository,racing,race.getName()),"A destination created during streaming is never overwritten");
        yes(Arrays.equals(Files.readAllBytes(race.toPath()),new byte[]{77}),"Publication collision preserves the raced destination bytes");
        Object owner=new Object();yes(SessionGuard.claim(owner,"active.BIN"),"Card fixture acquires a running-session guard");
        try{refused(()->cardCopy(repository,new ByteArrayInputStream(bytes),"busy.dat"),"File copy is blocked while a ROM session owns storage");}
        finally{SessionGuard.release(owner);}
        yes(!new File(fixed,"busy.dat").exists(),"Blocked copy writes no destination");
        File outside=new File(base,"outside");outside.mkdir();File link=new File(fixed,"redirected.dat");Files.createSymbolicLink(link.toPath(),new File(outside,"untouched").toPath());
        refused(()->cardCopy(repository,new ByteArrayInputStream(bytes),link.getName()),"A redirected destination is refused without following the link");
        yes(!new File(outside,"untouched").exists(),"Redirected path cannot modify outside files");
        File redirectedBase=Files.createTempDirectory("p2d-card-redirect-").toFile(),redirectedRoot=new File(redirectedBase,"pocket2droid");redirectedRoot.mkdir();
        Files.createSymbolicLink(new File(redirectedRoot,"storagecard").toPath(),outside.toPath());
        refused(()->cardCopy(repo(redirectedBase,custom),new ByteArrayInputStream(bytes),"outside.dat"),"A redirected fixed storagecard folder is refused");
        yes(!new File(outside,"outside.dat").exists(),"Fixed-folder redirection never copies into unrelated data");
    }
    static List<String> names(RomRepository repository)throws Exception {
        List<String> result=new ArrayList<>();for(RomProfile profile:repository.scan())result.add(profile.filename);return result;
    }
    static void invalidDiscoveredOrder()throws Exception {
        File base=Files.createTempDirectory("p2d-order-invalid-discovery-").toFile(),root=new File(base,"pocket2droid"),card=new File(base,"card");card.mkdir();
        String longName=String.join("",Collections.nCopies(181,"x"))+".BIN";
        write(new File(root,"Roms/ Alpha.BIN"),"unsupported name");write(new File(root,"Roms/"+longName),"unsupported length");write(new File(root,"Roms/Old.BIN"),"old");
        RomRepository repository=repo(base,card);List<RomProfile> first=repository.scan();int invalid=0;
        for(RomProfile profile:first)if(profile.error!=null)invalid++;
        yes(first.size()==3&&invalid==2,"Unsupported discovered filenames retain individual invalid rows");
        List<String> again;try{again=names(repo(base,card));}
        catch(IOException failure){throw new AssertionError("Unsupported discovered names must not poison subsequent library scans",failure);}
        yes(again.size()==3&&again.contains("Old.BIN"),"Valid ROM remains available on repeated scans beside invalid filenames");
        repository.importRom(new ByteArrayInputStream(new byte[]{1}),"New.BIN");
        List<String> after=names(repo(base,card));
        yes(after.indexOf("New.BIN")>after.indexOf("Old.BIN"),"Valid import still appends after unsupported folder filenames are found");
        yes(text(new File(root,"Roms/ Alpha.BIN")).equals("unsupported name")&&text(new File(root,"Roms/"+longName)).equals("unsupported length"),"Unsupported discovered files are preserved unchanged");
    }
    static void interruptedFirstImportOrder()throws Exception {
        File base=Files.createTempDirectory("p2d-order-first-interruption-").toFile(),root=new File(base,"pocket2droid"),card=new File(base,"card");card.mkdir();
        write(new File(root,"Roms/Zeta.BIN"),"zeta");write(new File(root,"Roms/Middle.BIN"),"middle");
        RomRepository repository=repo(base,card);File order=new File(root,"data/library-order.json");
        InputStream checkpoint=new InputStream(){public int read()throws IOException{
            yes(order.isFile(),"Existing library baseline is durable before first-import input publication");
            throw new IOException("Stopped at pre-publication checkpoint");
        }};
        refused(()->repository.importRom(checkpoint,"Alpha.BIN"),"Interrupted first import leaves its prior durable baseline");
        // Simulate interruption after verified ROM/profile publication, before its
        // final order append. The saved pre-import baseline must lead on recovery.
        write(new File(root,"Roms/Alpha.BIN"),"published input");
        JSONObject profile=RomSettings.defaults("Alpha",card).json().put("schema",1).put("iconId","pda_blue").put("saveState","NEW");
        write(new File(root,"data/Alpha.BIN/profile.json"),profile.toString());
        yes(names(repo(base,card)).equals(Arrays.asList("Middle.BIN","Zeta.BIN","Alpha.BIN")),"Interrupted first import appends the published new profile after the old baseline");
    }
    static void libraryOrder()throws Exception {
        File base=Files.createTempDirectory("p2d-library-order-").toFile(),root=new File(base,"pocket2droid"),card=new File(base,"card");card.mkdir();
        write(new File(root,"Roms/Zeta.BIN"),"zeta");write(new File(root,"Roms/Middle.BIN"),"middle");
        RomRepository repository=repo(base,card);
        yes(names(repository).equals(Arrays.asList("Middle.BIN","Zeta.BIN")),"Existing library keeps its original alphabetical order on first adoption");
        RomProfile added=repository.importRom(new ByteArrayInputStream(new byte[]{7}),"Alpha.BIN");
        yes(names(repository).equals(Arrays.asList("Middle.BIN","Zeta.BIN","Alpha.BIN")),"Newly imported ROM appends below existing rows instead of sorting by filename");
        repository=repo(base,card);
        yes(names(repository).equals(Arrays.asList("Middle.BIN","Zeta.BIN","Alpha.BIN")),"Library addition order survives a repository restart");
        repository.saveSettings(added.filename,added.settings.withDisplayName("000 First label"));
        yes(names(repository).equals(Arrays.asList("Middle.BIN","Zeta.BIN","Alpha.BIN")),"Changing a ROM display name does not move its library row");
        RomProfile duplicate=repository.importRom(new ByteArrayInputStream(new byte[]{8}),"Alpha.BIN");
        yes(duplicate.filename.equals("Alpha (2).BIN")&&names(repository).equals(Arrays.asList("Middle.BIN","Zeta.BIN","Alpha.BIN","Alpha (2).BIN")),"Duplicate import is a new bottom row with its own filename");
        File discovered=new File(root,"Roms/000-discovered.BIN");write(discovered,"new file");discovered.setLastModified(1);
        yes(names(repository).equals(Arrays.asList("Middle.BIN","Zeta.BIN","Alpha.BIN","Alpha (2).BIN","000-discovered.BIN")),"ROM copied into the folder appends regardless of its name and old file timestamp");
        yes(new File(root,"Roms/Middle.BIN").delete(),"Fixture removes only its disposable ROM input");
        yes(names(repo(base,card)).equals(Arrays.asList("Middle.BIN","Zeta.BIN","Alpha.BIN","Alpha (2).BIN","000-discovered.BIN")),"Missing ROM keeps its retained profile row in the same place");
        repository.deleteRom("Alpha.BIN");
        repository.importRom(new ByteArrayInputStream(new byte[]{9}),"Alpha.BIN");
        yes(names(repo(base,card)).equals(Arrays.asList("Middle.BIN","Zeta.BIN","Alpha (2).BIN","000-discovered.BIN","Alpha.BIN")),"Deleting and reimporting the same filename creates a new bottom row");
        write(new File(root,"Roms/Case.BIN"),"upper");write(new File(root,"Roms/case.BIN"),"lower");
        List<String> caseOrder=names(repository);
        yes(caseOrder.size()==7&&caseOrder.subList(0,5).equals(Arrays.asList("Middle.BIN","Zeta.BIN","Alpha (2).BIN","000-discovered.BIN","Alpha.BIN"))&&caseOrder.contains("Case.BIN")&&caseOrder.contains("case.BIN"),"Case-only filenames remain separate appended rows");
        yes(names(repo(base,card)).equals(caseOrder),"Case-only additions keep the same order after restart");
        byte[] romBefore=Files.readAllBytes(added.rom.toPath());String profileBefore=text(new File(root,"data/Zeta.BIN/profile.json"));
        String malformed=new JSONObject().put("schema",1).put("roms",new JSONArray().put("../escape.BIN")).toString();
        File order=new File(root,"data/library-order.json");write(order,malformed);
        RomRepository invalid=repo(base,card);
        refused(()->invalid.scan(),"Invalid saved order is refused without rewriting metadata or following paths");
        refused(()->invalid.importRom(new ByteArrayInputStream(new byte[]{4}),"UnsafeOrder.BIN"),"Import does not publish a ROM while order metadata is invalid");
        yes(text(order).equals(malformed)&&Arrays.equals(Files.readAllBytes(added.rom.toPath()),romBefore)&&text(new File(root,"data/Zeta.BIN/profile.json")).equals(profileBefore)&&!new File(root,"Roms/UnsafeOrder.BIN").exists(),"Malformed order preserves existing ROM/profile bytes and publishes no input");

        // An upgrade may import before its first scan; old rows must still lead.
        File upgrade=Files.createTempDirectory("p2d-order-upgrade-").toFile(),upgradeRoot=new File(upgrade,"pocket2droid");
        write(new File(upgradeRoot,"Roms/Zeta.BIN"),"existing");write(new File(upgradeRoot,"Roms/Middle.BIN"),"existing");
        RomRepository fresh=repo(upgrade,card);fresh.importRom(new ByteArrayInputStream(new byte[]{1}),"Alpha.BIN");
        yes(names(fresh).equals(Arrays.asList("Middle.BIN","Zeta.BIN","Alpha.BIN")),"Import before first scan preserves existing rows ahead of the new ROM");
        JSONObject recovered=new JSONObject().put("schema",1).put("roms",new JSONArray().put("Zeta.BIN").put("Middle.BIN").put("Alpha.BIN"));
        write(new File(upgrade,"private/library-write.pending.json"),new JSONObject().put("schema",1).put("writes",new JSONArray().put(ProfileFiles.update("data/library-order.json",recovered))).toString());
        yes(names(repo(upgrade,card)).equals(Arrays.asList("Zeta.BIN","Middle.BIN","Alpha.BIN")),"Interrupted order metadata publication recovers the saved order");
    }
    public static void main(String[]args)throws Exception{
        invalidDiscoveredOrder();interruptedFirstImportOrder();
        libraryOrder();
        cardImports();
        File base=Files.createTempDirectory("p2d-library-").toFile(),root=new File(base,"pocket2droid"),card=new File(base,"card-A");card.mkdir();
        RomRepository r=repo(base,card);
        File iconBase=Files.createTempDirectory("p2d-six-icons-").toFile(),iconCard=new File(iconBase,"card");iconCard.mkdir();
        RomRepository sixIcons=new RomRepository(new File(iconBase,"pocket2droid"),new File(iconBase,"private"),iconCard,new Random(){@Override public int nextInt(int bound){return bound-1;}});
        RomProfile red=sixIcons.importRom(new ByteArrayInputStream(new byte[]{1}),"RED.BIN");
        yes(red.iconId.equals("pda_red"),"New red artwork can be assigned to an imported ROM");
        RomProfile orange=sixIcons.importRom(new ByteArrayInputStream(new byte[]{1}),"ORANGE.BIN");
        yes(orange.iconId.equals("pda_orange")&&!orange.iconId.equals(red.iconId),"Orange artwork can be assigned while excluding the last icon");
        RomRepository iconRestart=repo(iconBase,iconCard);
        yes(iconRestart.getProfile(red.filename).iconId.equals("pda_red")&&iconRestart.getProfile(orange.filename).iconId.equals("pda_orange"),"New artwork assignments survive repository restart without rerolling");
        yes(!iconRestart.importRom(new ByteArrayInputStream(new byte[]{1}),"NEXT.BIN").iconId.equals(orange.iconId),"Saved last-icon exclusion survives repository restart with six artwork choices");
        File defaultBase=Files.createTempDirectory("p2d-storagecard-").toFile();File defaultCard=new File(defaultBase,"pocket2droid/storagecard");
        RomRepository defaults=repo(defaultBase,defaultCard);RomProfile fresh=defaults.importRom(new ByteArrayInputStream(new byte[]{1}),"Fresh.BIN");
        yes(defaultCard.isDirectory()&&fresh.settings.card.equals(defaultCard),"New storagecard default is created and assigned");
        yes(fresh.settings.resolution==RomSettings.GuestResolution.QVGA,"Unknown new ROM selects concrete QVGA dropdown preset");
        yes(fresh.settings.internetEnabled&&NetworkConfig.validMac(fresh.settings.networkMac),"Import persists an online profile with a valid MAC");
        String freshMac=fresh.settings.networkMac;
        defaults.saveSettings(fresh.filename,fresh.settings.withInternetAccess(false));
        defaults.scan();
        yes(!repo(defaultBase,defaultCard).getProfile(fresh.filename).settings.internetEnabled&&repo(defaultBase,defaultCard).getProfile(fresh.filename).settings.networkMac.equals(freshMac),"Explicit Off survives discovery and repository restart without changing MAC");
        RomProfile square=defaults.importRom(new ByteArrayInputStream(new byte[]{1}),"PPC_USA_GSM_VGA_SQUARE_VR.BIN");
        yes(square.settings.resolution==RomSettings.GuestResolution.SQUARE_VGA,"Known new ROM selects Square VGA dropdown preset");
        RomProfile squareCopy=defaults.importRom(new ByteArrayInputStream(new byte[]{1}),"PPC_USA_GSM_VGA_SQUARE_VR.BIN");
        yes(squareCopy.settings.resolution==RomSettings.GuestResolution.SQUARE_VGA,"Import collision suffix preserves automatic preset selection");
        defaults.saveSettings(squareCopy.filename,squareCopy.settings.withResolution(RomSettings.GuestResolution.ROM_DEFAULT));
        yes(repo(defaultBase,defaultCard).getProfile(squareCopy.filename).settings.resolution==RomSettings.GuestResolution.SQUARE_VGA,"Older ROM-default profile resolves to its concrete preset without changing boot size");
        defaults.saveSettings(square.filename,square.settings.withResolution(RomSettings.GuestResolution.WVGA));
        defaults.scan();
        yes(repo(defaultBase,defaultCard).getProfile(square.filename).settings.resolution==RomSettings.GuestResolution.WVGA,"Rescan/restart preserves user's later manual resolution selection");
        defaults.saveSettings(square.filename,square.settings.withCustomResolution(640,360));defaults.scan();
        RomProfile customProfile=repo(defaultBase,defaultCard).getProfile(square.filename);
        yes(customProfile.settings.startupSize(square.filename).width==640&&customProfile.settings.startupSize(square.filename).height==360,"Custom resolution survives repository restart and discovery");
        yes(repo(defaultBase,defaultCard).getProfile(fresh.filename).settings.resolution==RomSettings.GuestResolution.QVGA,"Another ROM retains its independent resolution");
        defaults.prepareSave(square.filename,RomRepository.SaveChoice.NEW_INSTALLATION);
        StorageLayout staleSize=new StorageLayout(new File(defaultBase,"pocket2droid"),new File(defaultBase,"private"),defaults.verifyForLaunch(square.filename));
        defaults.saveSettings(square.filename,customProfile.settings.withCustomResolution(640,480));
        refused(staleSize::prepare,"Changing custom dimensions invalidates an already-selected launch profile");
        defaults.saveSettings(square.filename,defaults.getProfile(square.filename).settings.withInternetAccess(false));
        RomProfile beforeNetwork=defaults.verifyForLaunch(square.filename);
        StorageLayout staleNetwork=new StorageLayout(new File(defaultBase,"pocket2droid"),new File(defaultBase,"private"),beforeNetwork);
        defaults.saveSettings(square.filename,beforeNetwork.settings.withInternetAccess(true));
        refused(staleNetwork::prepare,"Changing Internet access invalidates an already-selected launch");
        RomProfile connected=repo(defaultBase,defaultCard).getProfile(square.filename);
        yes(connected.settings.internetEnabled&&NetworkConfig.validMac(connected.settings.networkMac),"Repository atomically retains enabled MAC");
        defaults.saveSettings(square.filename,connected.settings.withInternetAccess(false));
        RomProfile offlineAgain=repo(defaultBase,defaultCard).getProfile(square.filename);
        yes(!offlineAgain.settings.internetEnabled&&offlineAgain.settings.networkMac.equals(connected.settings.networkMac),"Repository Off retains network identity");
        StorageLayout staleMac=new StorageLayout(new File(defaultBase,"pocket2droid"),new File(defaultBase,"private"),offlineAgain);
        defaults.saveSettings(square.filename,RomSettings.parse(offlineAgain.settings.json().put("networkMac",NetworkConfig.newMac(new java.security.SecureRandom()))));
        refused(staleMac::prepare,"Changing MAC alone invalidates an already-selected launch");
        File discoveredRom=new File(defaultBase,"pocket2droid/Roms/ppc_usa_gsm_vga_vr.bin");write(discoveredRom,"disposable discovery fixture");
        defaults.scan();
        yes(repo(defaultBase,defaultCard).getProfile(discoveredRom.getName()).settings.resolution==RomSettings.GuestResolution.VGA,"Folder discovery selects and persists the matching dropdown preset");
        yes(repo(defaultBase,defaultCard).getProfile(discoveredRom.getName()).settings.internetEnabled,"A newly discovered ROM also persists the online default");
        for(String invalid:new String[]{"game.cab","OTHER.rom","image.bin.exe","unknown"}){
            refused(()->r.importRom(new ByteArrayInputStream(new byte[]{1}),invalid),"Only .bin ROM imports are accepted");
            yes(!new File(root,"Roms/"+invalid).exists(),"Rejected extension never publishes a file");
        }
        yes(r.importRom(new ByteArrayInputStream(new byte[]{1}),"Mixed.BiN").filename.equals("Mixed.BiN"),"BIN extension is case insensitive");
        RomProfile a=r.importRom(new ByteArrayInputStream(new byte[]{1,2,3}),"PPC_USA.BIN");
        yes(a.displayName.equals("PPC_USA"),"Display label preserves filename case/underscores without extension");
        yes(a.storage.equals(new File(root,"data/PPC_USA.BIN/ram-fmd.bin")),"Actual filename selects separate data");
        RomProfile b=r.importRom(new ByteArrayInputStream(new byte[]{1,2,3}),"PPC_USA.BIN");
        yes(b.filename.equals("PPC_USA (2).BIN")&&b.displayName.equals("PPC_USA"),"Collision gets filename suffix, original source label");
        yes(!a.iconId.equals(b.iconId),"Adjacent successful additions differ");
        yes(r.importRom(new ByteArrayInputStream(new byte[]{1}),"PPC_USA.BIN").filename.equals("PPC_USA (3).BIN"),"Further duplicate does not overwrite");
        refused(()->r.importRom(new ByteArrayInputStream(new byte[0]),"EMPTY.BIN"),"Empty import refused");
        refused(()->r.importRom(new ByteArrayInputStream(new byte[]{1}),"../unsafe.BIN"),"Path traversal refused");
        r.prepareSave(a.filename,RomRepository.SaveChoice.NEW_INSTALLATION);r.prepareSave(b.filename,RomRepository.SaveChoice.NEW_INSTALLATION);
        save(a.storage,11);save(b.storage,22);
        yes(first(r.verifyForLaunch(a.filename).storage)==11&&first(r.verifyForLaunch(b.filename).storage)==22&&first(r.verifyForLaunch(a.filename).storage)==11,"A->B->A isolates persistent bytes");
        write(a.rom,"different ROM contents");yes(first(r.verifyForLaunch(a.filename).storage)==11,"Same filename replacement keeps data without content gate");
        RomSettings changed=a.settings.withDisplayName("Shared label").withScale(RomSettings.ScaleMode.PIXEL_PERFECT);
        r.saveSettings(a.filename,changed);r.saveSettings(b.filename,b.settings.withDisplayName("Shared label"));
        RomProfile again=repo(base,card).verifyForLaunch(a.filename);
        yes(again.displayName.equals("Shared label")&&again.settings.scale==RomSettings.ScaleMode.PIXEL_PERFECT&&again.iconId.equals(a.iconId),"Settings/icon survive repository restart");
        yes(first(again.storage)==11&&a.rom.exists(),"Label edit never moves ROM/save");
        refused(()->r.saveSettings(a.filename,changed.withDisplayName("  ")),"Blank label cannot overwrite metadata");
        File newCard=new File(base,"card-B");newCard.mkdir();write(new File(card,"keep.txt"),"card preserved");
        RomRepository next=repo(base,newCard);
        RomProfile c=next.importRom(new ByteArrayInputStream(new byte[]{7}),"OTHER.BIN");
        yes(c.settings.card.equals(newCard.getCanonicalFile()),"New profile snapshots current card default");
        yes(next.verifyForLaunch(a.filename).settings.card.equals(card.getCanonicalFile()),"Changed default never reroutes existing profiles");
        next.saveSettings(a.filename,changed.withCard(newCard));
        yes(first(a.storage)==11&&new File(card,"keep.txt").exists(),"Changing card never moves old contents or internal save");
        refused(()->repo(base,new File(base,"missing-card")).importRom(new ByteArrayInputStream(new byte[]{1}),"FAIL.BIN"),"Inaccessible default blocks new import");
        yes(!new File(root,"Roms/FAIL.BIN").exists(),"Default failure publishes no ROM");
        refused(()->next.saveSettings(a.filename,changed.withCard(new File(root,"data"))),"Managed data cannot be a card");
        refused(()->next.saveSettings(a.filename,changed.withCard(base)),"Ancestor of managed files cannot be a card");
        yes(a.storage.delete(),"Fixture removes initialized save");
        refused(()->next.verifyForLaunch(a.filename),"Initialized missing save blocks launch");
        refused(()->next.prepareSave(a.filename,RomRepository.SaveChoice.NEW_INSTALLATION),"Initialized save never silently recreated");
        yes(!a.storage.exists(),"No reset after failure");save(a.storage,11);
        File legacy=new File(root,"data/ram-fmd.bin");save(legacy,77);
        next.prepareSave(c.filename,RomRepository.SaveChoice.USE_EXISTING_COPY);
        yes(first(c.storage)==77&&first(legacy)==77,"Explicit legacy migration copies and preserves original");
        yes(!next.getProfile(c.filename).settings.networkSetupEligible,"Copying existing guest data never schedules automatic changes to its connection settings");
        save(c.storage,33);next.prepareSave(c.filename,RomRepository.SaveChoice.USE_EXISTING_COPY);
        yes(first(c.storage)==33,"Ready copied save never compared against later-changed rollback");
        Files.move(c.rom.toPath(),new File(root,"Roms/RENAMED.BIN").toPath());
        Files.move(c.storage.getParentFile().toPath(),new File(root,"data/RENAMED.BIN").toPath());
        RomProfile renamed=next.verifyForLaunch("RENAMED.BIN");
        yes(first(renamed.storage)==33&&renamed.iconId.equals(c.iconId)&&renamed.displayName.equals(c.displayName),"Paired external rename retains profile/save/icon");
        Files.move(b.rom.toPath(),new File(root,"Roms/ALONE.BIN").toPath());next.scan();
        yes(b.storage.exists(),"ROM-only rename preserves old save");
        refused(()->next.verifyForLaunch("ALONE.BIN"),"New filename requires separate preparation");
        Object owner=new Object();yes(SessionGuard.claim(owner,a.filename),"Session acquired");
        refused(()->next.deleteRom(a.filename),"Active session prevents deletion");
        refused(()->next.importRom(new ByteArrayInputStream(new byte[]{1}),"BUSY.BIN"),"Active session prevents import");
        SessionGuard.release(owner);
        String aMeta=text(new File(a.storage.getParentFile(),"profile.json"));
        write(new File(a.storage.getParentFile(),"profile.json"),"broken JSON");
        refused(()->next.verifyForLaunch(a.filename),"Malformed metadata fails safely");
        yes(first(a.storage)==11,"Invalid metadata leaves save untouched");
        write(new File(a.storage.getParentFile(),"profile.json"),aMeta);
        JSONObject journal=new JSONObject().put("schema",1).put("writes",new JSONArray().put(new JSONObject().put("path","data/"+a.filename+"/profile.json").put("text",aMeta)));
        write(new File(base,"private/library-write.pending.json"),journal.toString());write(new File(a.storage.getParentFile(),"profile.json"),"partial write");
        yes(next.verifyForLaunch(a.filename).iconId.equals(a.iconId),"Interrupted metadata write rolls forward from private journal");
        File link=new File(root,"Roms/LINK.BIN");Files.createSymbolicLink(link.toPath(),a.rom.toPath());
        refused(()->next.verifyForLaunch("LINK.BIN"),"Redirected ROM refused");link.delete();
        String iconState=text(new File(root,"data/library.json"));
        next.deleteRom(a.filename);
        yes(!a.rom.exists()&&!a.storage.getParentFile().exists(),"Confirmed delete removes only selected ROM and internal data");
        yes(first(renamed.storage)==33&&first(legacy)==77&&new File(card,"keep.txt").exists(),"Deletion preserves other profile, legacy and cards");
        yes(text(new File(root,"data/library.json")).equals(iconState),"Deletion retains last icon state");
        next.deleteRom(b.filename);yes(!b.storage.getParentFile().exists(),"Missing ROM's retained profile can be deleted");
        write(new File(base,"private/library-delete.pending.json"),new JSONObject().put("schema",1).put("filename","RENAMED.BIN").toString());
        next.scan();yes(!renamed.rom.exists()&&!renamed.storage.getParentFile().exists(),"Interrupted confirmed deletion resumes without fresh save");
        yes(first(legacy)==77,"Legacy survives recovery");
        write(new File(root,"Roms/EXISTING.BIN"),"rom");
        File named=new File(root,"data/EXISTING.BIN/ram-fmd.bin");save(named,91);
        next.scan();yes(first(next.verifyForLaunch("EXISTING.BIN").storage)==91,"Existing filename-linked 32MiB save is reused without resetting");
        String longName=String.join("",Collections.nCopies(161,"x"))+".bin";
        RomProfile longRom=next.importRom(new ByteArrayInputStream(new byte[]{1}),longName);
        yes(longRom.displayName.length()==161&&next.scan().size()>1,"Long accepted filename cannot poison the library");
        File staged=new File(base,"private/library-delete.pending.json.partial");write(staged,"partial");
        yes(next.scan().size()>1&&named.exists(),"Unpublished deletion journal cannot delete or block profiles");staged.delete();
        File journalTarget=new File(base,"private/test-confirmed-delete.json");
        refused(()->ProfileFiles.publishJournal(journalTarget,"partial",new File(base,"private")),"Invalid journal cannot be published");
        yes(!journalTarget.exists(),"Journal is invisible before complete valid JSON publication");
        ProfileFiles.publishJournal(journalTarget,"{\"schema\":1}",new File(base,"private"));
        yes(ProfileFiles.object(journalTarget).getInt("schema")==1,"Confirmed journal publishes a complete verified record");journalTarget.delete();
        yes(newCard.delete(),"Disposable card is removed");next.deleteRom("EXISTING.BIN");
        yes(!named.exists()&&new File(card,"keep.txt").exists(),"Missing unrelated/default card never blocks safe deletion or alters card data");
        write(new File(root,"Roms/INVALID.BIN"),"rom");File invalid=new File(root,"data/INVALID.BIN/ram-fmd.bin");write(invalid,"bad");
        next.scan();refused(()->next.verifyForLaunch("INVALID.BIN"),"Invalid unprofiled save cannot be adopted");yes(text(invalid).equals("bad"),"Invalid unprofiled save is preserved");
        System.out.println("PASS ROM repository "+checks+" real filesystem assertions");
    }
}
