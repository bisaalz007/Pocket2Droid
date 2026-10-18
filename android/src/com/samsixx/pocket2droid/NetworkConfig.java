package com.samsixx.pocket2droid;
import java.security.SecureRandom;
import java.util.*;
import java.io.*;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;

/** Pure launch/profile configuration shared by Android and host regressions. */
final class NetworkConfig {
    private NetworkConfig(){}
    static String newMac(SecureRandom random){
        byte[] bytes=new byte[6];random.nextBytes(bytes);bytes[0]=(byte)((bytes[0]&0xfc)|2);
        StringBuilder mac=new StringBuilder();for(byte b:bytes){if(mac.length()>0)mac.append(':');mac.append(String.format(Locale.ROOT,"%02x",b&255));}return mac.toString();
    }
    static boolean validMac(String mac){return mac!=null&&mac.matches("[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}")&&(Integer.parseInt(mac.substring(0,2),16)&3)==2;}
    static void appendArguments(List<String> args,boolean enabled,String mac){
        if(!enabled){Collections.addAll(args,"-nic","none");return;}
        if(!validMac(mac))throw new IllegalArgumentException("Invalid network MAC address");
        Collections.addAll(args,"-netdev","user,id=p2dnet,ipv6=off","-net","nic,model=ne2k_pcmcia,netdev=p2dnet,macaddr="+mac);
    }
    static byte[] resolverBytes(List<InetAddress> addresses){
        StringBuilder text=new StringBuilder();Set<String> seen=new HashSet<>();
        if(addresses!=null)for(InetAddress address:addresses){
            if(address==null||address.isAnyLocalAddress()||address.isMulticastAddress())continue;
            String host=address.getHostAddress();if(!seen.add(host))continue;
            String line="nameserver "+host+"\n";if(text.length()+line.length()>4096)break;text.append(line);
        }
        return text.toString().getBytes(StandardCharsets.US_ASCII);
    }
    static void publishResolver(File target,byte[] bytes)throws IOException {
        if(bytes.length>4096)throw new IOException("Resolver configuration exceeds 4 KiB");
        File parent=target.getParentFile();
        if(!parent.isDirectory()&&!parent.mkdirs()&&!parent.isDirectory())throw new IOException("Cannot create private resolver directory");
        File temporary=File.createTempFile(".dns-",".tmp",parent);
        try {
            try(FileOutputStream out=new FileOutputStream(temporary)){out.write(bytes);out.getFD().sync();}
            // Same-directory rename is atomic on Android/Linux; API24 compatible.
            if(!temporary.renameTo(target))throw new IOException("Cannot publish private resolver configuration");
        } finally {temporary.delete();}
    }
}
