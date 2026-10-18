package com.samsixx.pocket2droid;
import java.io.*;import java.nio.file.*;import java.security.*;import java.util.*;import org.json.*;
public final class NetworkSetupTest {
    static int checks;
    static void check(boolean value,String why){if(!value)throw new AssertionError(why);checks++;}
    interface Work{void run()throws Exception;}
    static void refused(Work work,String why)throws Exception{try{work.run();throw new AssertionError(why);}catch(IOException expected){checks++;}}
    static String sha(byte[] bytes)throws Exception{StringBuilder s=new StringBuilder();for(byte b:MessageDigest.getInstance("SHA-256").digest(bytes))s.append(String.format(Locale.ROOT,"%02x",b&255));return s.toString();}
    static File publish(byte[] exe,String manifest,File dir)throws Exception{return NetworkSetup.publish(new ByteArrayInputStream(exe),new ByteArrayInputStream(manifest.getBytes("UTF-8")),dir);}
    public static void main(String[]args)throws Exception{
        File fixture=new File("android/build/network-setup/production-helper");byte[] exe=Files.readAllBytes(new File(fixture,"autorun.exe").toPath());String manifest=new String(Files.readAllBytes(new File(fixture,"manifest.json").toPath()),"UTF-8");
        File root=Files.createTempDirectory("p2d-setup-java-").toFile(),dir=new File(root,"app-private");
        File result=publish(exe,manifest,dir);check(result.getParentFile().equals(dir)&&result.getName().equals(sha(exe)+".exe"),"Only app-private hash-named helper published");check(Arrays.equals(Files.readAllBytes(result.toPath()),exe),"Published exact verified executable");
        long timestamp=result.lastModified();check(publish(exe,manifest,dir).equals(result)&&result.lastModified()==timestamp,"Verified cache reused without modifying live inode");
        Files.write(result.toPath(),new byte[]{1,2,3});try(FileInputStream old=new FileInputStream(result)){check(publish(exe,manifest,dir).equals(result),"Stale cached bytes replaced at same content address");check(old.read()==1&&Arrays.equals(Files.readAllBytes(result.toPath()),exe),"Atomic repair preserves already-open inode");}
        String bad=new JSONObject(manifest).put("executable_sha256",String.join("",Collections.nCopies(64,"0"))).toString();refused(()->publish(exe,bad,new File(root,"bad-hash")),"Hash mismatch rejected");
        byte[] invalid=exe.clone();invalid[0]=0;String malformed=new JSONObject(manifest).put("executable_sha256",sha(invalid)).toString();refused(()->publish(invalid,malformed,new File(root,"bad-pe")),"Invalid PE rejected even with matching metadata hash");
        refused(()->publish(new byte[256*1024+1],manifest,new File(root,"oversize")),"Executable input bounded");
        refused(()->publish(exe,new String(new char[65537]).replace('\0','x'),new File(root,"oversize-manifest")),"Manifest input bounded");
        File linked=new File(root,"symlink-cache");check(linked.mkdir(),"Create symlink fixture");File victim=new File(root,"outside.txt");Files.write(victim.toPath(),new byte[]{91});Files.createSymbolicLink(new File(linked,sha(exe)+".exe").toPath(),victim.toPath());refused(()->publish(exe,manifest,linked),"Symlink cache never followed or replaced");check(Files.readAllBytes(victim.toPath())[0]==91,"Outside file preserved");
        String machine=NetworkSetup.appendMachineOption("p2d-devemu,network=on",new File("/tmp/app,cache/setup.exe"));check(machine.equals("p2d-devemu,network=on,network-setup=/tmp/app,,cache/setup.exe"),"Machine path escaping preserves one option");check(NetworkSetup.appendMachineOption("p2d-devemu",null).equals("p2d-devemu"),"Unavailable helper leaves original launch intact");
        RomSettings fresh=RomSettings.defaults("ROM",new File("/tmp/card"));check(fresh.networkSetupEligible,"New ROM retains compatible eligibility metadata");JSONObject legacy=fresh.json();legacy.remove("networkSetupEligible");check(!RomSettings.parse(legacy).networkSetupEligible,"Legacy metadata still parses unchanged; guest helper now decides whether setup is safe");check(fresh.withInternetAccess(false).withInternetAccess(true).networkSetupEligible,"Off/On preserves compatibility metadata");
        check(NetworkSetup.prepare(null,RomSettings.parse(legacy).withInternetAccess(false))==null,"Saved Off never reads helper assets");check(NetworkSetup.prepare(null,null)==null,"No profile never reads helper assets");
        System.out.println("Network setup publication/profile: "+checks+" checks passed");
    }
}
