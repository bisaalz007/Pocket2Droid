package com.samsixx.pocket2droid;
import android.content.Context;
import java.io.*;
import java.security.*;
import java.util.*;
import org.json.*;

/** Verified content-addressed guest asset. Never writes to a guest/card path. */
final class NetworkSetup {
    private NetworkSetup(){}
    static File prepare(Context context,RomSettings settings)throws IOException {
        // Profile age is not a guest opt-out. The helper itself preserves
        // custom configurations and durable prior-attempt/success markers.
        if(settings==null||!settings.internetEnabled)return null;
        File directory=new File(context.getFilesDir().getCanonicalFile(),"network-setup");
        try(InputStream exe=context.getAssets().open("network-setup/autorun.exe");
            InputStream manifest=context.getAssets().open("network-setup/manifest.json")){
            return publish(exe,manifest,directory);
        }
    }
    static String appendMachineOption(String machine,File helper){return helper==null?machine:machine+",network-setup="+helper.getAbsolutePath().replace(",",",,");}
    private static byte[] read(InputStream input,int maximum)throws IOException {
        ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] buffer=new byte[4096];int n;
        while((n=input.read(buffer))!=-1){if(n==0)continue;if(n>maximum-out.size())throw new IOException("Network setup asset exceeds size limit");out.write(buffer,0,n);}return out.toByteArray();
    }
    private static String sha(byte[] data)throws IOException {
        try{StringBuilder text=new StringBuilder();for(byte b:MessageDigest.getInstance("SHA-256").digest(data))text.append(String.format(Locale.ROOT,"%02x",b&255));return text.toString();}
        catch(NoSuchAlgorithmException failure){throw new IOException(failure);}
    }
    private static int u16(byte[] b,int n){return (b[n]&255)|((b[n+1]&255)<<8);}
    private static long u32(byte[] b,int n){return ((long)u16(b,n)|((long)u16(b,n+2)<<16));}
    private static void executable(byte[] b)throws IOException {
        if(b.length<512||b[0]!='M'||b[1]!='Z')throw new IOException("Invalid network setup executable");
        long offset=u32(b,60);if(offset>b.length-96)throw new IOException("Invalid network setup header");int p=(int)offset;
        if(b[p]!='P'||b[p+1]!='E'||b[p+2]!=0||b[p+3]!=0||u16(b,p+4)!=0x1c0||u16(b,p+20)<72||u16(b,p+24)!=0x10b||u16(b,p+92)!=9||(u16(b,p+22)&2)==0||(u16(b,p+22)&0x2000)!=0)throw new IOException("Network setup must be an ARM Windows CE executable");
    }
    static synchronized File publish(InputStream source,InputStream metadata,File directory)throws IOException {
        byte[] exe=read(source,256*1024),manifest=read(metadata,65536);String expected;
        try{JSONObject record=new JSONObject(new String(manifest,"UTF-8"));expected=record.getString("executable_sha256");
            if(!expected.matches("[0-9a-f]{64}")||!record.getString("machine").equals("ARMv4")||record.getInt("subsystem")!=9||!record.getString("builder_sha256").matches("[0-9a-f]{64}")||record.getJSONObject("sources").length()==0||record.getJSONObject("tools").length()==0)throw new IOException("Invalid network setup provenance");
        }catch(JSONException failure){throw new IOException("Invalid network setup manifest",failure);}
        if(!expected.equals(sha(exe)))throw new IOException("Network setup asset hash mismatch");executable(exe);
        File parent=directory.getAbsoluteFile();if(!parent.equals(parent.getCanonicalFile()))throw new IOException("Network setup directory cannot be a link");
        if(!parent.isDirectory()&&!parent.mkdirs()&&!parent.isDirectory())throw new IOException("Cannot prepare private network setup directory");
        File target=new File(parent,expected+".exe");if(!target.equals(target.getCanonicalFile()))throw new IOException("Network setup cache cannot be a link");
        if(target.exists()){
            if(!target.isFile())throw new IOException("Invalid network setup cache entry");
            try(InputStream in=new FileInputStream(target)){if(expected.equals(sha(read(in,256*1024))))return target;}
        }
        File temporary=File.createTempFile(".setup-",".tmp",parent);
        try{try(FileOutputStream out=new FileOutputStream(temporary)){out.write(exe);out.getFD().sync();}
            if(!temporary.setReadOnly())throw new IOException("Cannot protect network setup asset");
            if(!temporary.renameTo(target))throw new IOException("Cannot publish private network setup asset");
        }finally{temporary.delete();}
        return target;
    }
}
