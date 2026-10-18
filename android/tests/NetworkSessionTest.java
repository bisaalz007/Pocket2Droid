package com.samsixx.pocket2droid;
import java.io.*;import java.net.*;import java.nio.charset.StandardCharsets;import java.nio.file.*;import java.util.*;
public final class NetworkSessionTest {
    static int checks;static void check(boolean b,String why){if(!b)throw new AssertionError(why);checks++;}
    static class Source implements NetworkSession.Source {
        List<InetAddress> dns=Collections.emptyList();Runnable callback;boolean fail;int registers,unregisters;
        public List<InetAddress> current(){return dns;}
        public void register(Runnable callback)throws Exception{this.callback=callback;registers++;if(fail)throw new IOException("registration failed");}
        public void unregister(){unregisters++;}
    }
    static String read(File f)throws IOException{return new String(Files.readAllBytes(f.toPath()),StandardCharsets.US_ASCII);}
    public static void main(String[] args)throws Exception {
        File root=Files.createTempDirectory("p2d-network-session-").toFile();
        try {
            Source source=new Source();List<Runnable> queue=new ArrayList<>();List<String> status=new ArrayList<>();
            NetworkSession first=new NetworkSession(source,root,queue::add,status::add);first.start();
            check(first.resolverFile().isFile()&&read(first.resolverFile()).isEmpty(),"No network starts with empty private DNS");
            source.dns=Arrays.asList(InetAddress.getByName("192.0.2.53"),InetAddress.getByName("2001:db8::53"));source.callback.run();queue.remove(0).run();
            String v=read(first.resolverFile());check(v.contains("nameserver 192.0.2.53\n")&&v.contains("2001:db8:"),"IPv4/IPv6 snapshot published");
            source.dns=Collections.emptyList();source.callback.run();queue.remove(0).run();check(read(first.resolverFile()).isEmpty(),"Network loss removes old DNS");
            source.callback.run();first.close();first.close();check(source.unregisters==1&&!first.resolverFile().exists(),"Close twice unregisters once");
            Source secondSource=new Source();secondSource.dns=Arrays.asList(InetAddress.getByName("192.0.2.54"));NetworkSession second=new NetworkSession(secondSource,root,Runnable::run,status::add);second.start();
            check(!first.resolverFile().equals(second.resolverFile()),"Each engine has a unique DNS path");queue.remove(0).run();source.callback.run();
            check(!first.resolverFile().exists()&&read(second.resolverFile()).equals("nameserver 192.0.2.54\n"),"Old queued and late callbacks cannot change new session");second.close();
            Source broken=new Source();broken.fail=true;NetworkSession failed=new NetworkSession(broken,root,Runnable::run,status::add);
            try{failed.start();throw new AssertionError("Partial registration accepted");}catch(IOException expected){checks++;}
            check(broken.unregisters==1&&!failed.resolverFile().exists(),"Failed startup cleans partial listener and DNS");failed.close();
            File f=new File(root,"atomic.conf");NetworkConfig.publishResolver(f,"old\n".getBytes(StandardCharsets.US_ASCII));NetworkConfig.publishResolver(f,"new\n".getBytes(StandardCharsets.US_ASCII));check(read(f).equals("new\n"),"Atomic same-length publication");
            try{NetworkConfig.publishResolver(f,new byte[4097]);throw new AssertionError("Oversized resolver accepted");}catch(IOException expected){checks++;}check(read(f).equals("new\n"),"Failed update preserves prior complete file");f.delete();
            check(NetworkConfig.resolverBytes(Arrays.asList(InetAddress.getByName("0.0.0.0"),InetAddress.getByName("224.0.0.1"))).length==0,"Unusable addresses are not DNS servers");
            check(root.list().length==0,"No session or temporary files leaked");
            System.out.println("Network session: "+checks+" checks passed (simulated connectivity source)");
        } finally {for(File f:root.listFiles())f.delete();root.delete();}
    }
}
