package com.samsixx.p2dsealprobe;

import android.app.Instrumentation;
import android.net.LocalSocket;
import android.net.LocalSocketAddress;
import android.os.Bundle;
import java.io.*;
import java.nio.*;
import java.nio.file.Files;
import java.util.Arrays;
import java.util.concurrent.TimeUnit;

/** App-private fixtures only; actual production engine, CPU paused throughout. */
public final class SealProbe extends Instrumentation {
    static { System.loadLibrary("sealprobe"); }
    private static native String run();
    public void onCreate(Bundle args) { super.onCreate(args); start(); }
    private static void require(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
    private static String hex(byte[] data) {
        StringBuilder out=new StringBuilder();
        for(byte value:data)out.append(String.format(java.util.Locale.ROOT,"%02x",value&255));
        return out.toString();
    }
    private static String command(BufferedReader in, OutputStream out, String text)throws Exception {
        out.write((text+"\n").getBytes("US-ASCII"));out.flush();
        String line;
        do {line=in.readLine();require(line!=null,"Engine closed the test socket");}
        while(line.startsWith("IRQ "));
        require(line.startsWith("OK"),"QTest command failed: "+line);
        return line.length()>3?line.substring(3).trim():"";
    }
    private File asset(String name,File directory)throws Exception {
        File file=new File(directory,name);
        try(InputStream in=getTargetContext().getAssets().open(name);
            FileOutputStream out=new FileOutputStream(file)) {
            byte[] buffer=new byte[4096];int count;
            while((count=in.read(buffer))!=-1)out.write(buffer,0,count);
        }
        return file;
    }
    private String delivery()throws Exception {
        File root=new File(getTargetContext().getFilesDir(),"delivery-"+System.nanoTime());
        require(root.mkdir(),"Create independent test directory");
        File card=new File(root,"card");require(card.mkdir(),"Create empty private card");
        File helper=asset("autorun.exe",root), idle=asset("idle.bin",root);
        File log=new File(root,"engine.log"),socket=new File(root,"qtest.sock");
        String libraries=getTargetContext().getApplicationInfo().nativeLibraryDir;
        ProcessBuilder builder=new ProcessBuilder(new File(libraries,"libp2dengine.so").getPath(),
            "-M","p2d-devemu,network=on,shared-folder="+card+",network-setup="+helper,
            "-bios",idle.getPath(),"-accel","tcg,thread=single","-S",
            "-display","none","-monitor","none","-serial","none","-nic","none",
            "-qtest","unix:"+socket+",server=on,wait=off","-qtest-log","/dev/null");
        builder.environment().put("LD_LIBRARY_PATH",libraries);
        builder.environment().put("TMPDIR",root.getPath());
        builder.redirectErrorStream(true);builder.redirectOutput(log);
        Process engine=builder.start();
        try(LocalSocket client=new LocalSocket()) {
            boolean connected=false;
            for(int attempt=0;attempt<100;attempt++) {
                try {client.connect(new LocalSocketAddress(socket.getPath(),LocalSocketAddress.Namespace.FILESYSTEM));connected=true;break;}
                catch(IOException pending) {Thread.sleep(30);}
            }
            require(connected,"Native test socket unavailable: "+new String(Files.readAllBytes(log.toPath()),"UTF-8"));
            client.setSoTimeout(3000);
            BufferedReader in=new BufferedReader(new InputStreamReader(client.getInputStream(),"US-ASCII"));
            OutputStream out=client.getOutputStream();
            byte[] raw=new byte[1068];ByteBuffer pb=ByteBuffer.wrap(raw).order(ByteOrder.LITTLE_ENDIAN);
            pb.putShort(0,(short)1068);pb.putInt(4,-1);pb.putShort(8,(short)-1);pb.put(32,(byte)1);
            byte[] name="\\2577\\autorun.exe".getBytes("UTF-16LE");
            pb.putShort(34,(short)name.length);System.arraycopy(name,0,raw,36,name.length);
            command(in,out,"write 0x30008000 1068 0x"+hex(raw));
            command(in,out,"writel 0x500f4000 0x30008000");
            command(in,out,"writel 0x500f4004 0x11");
            require(Long.decode(command(in,out,"readl 0x500f400c"))==0,"Helper metadata not visible");
            require((Long.decode(command(in,out,"readw 0x3000801c"))&1)==1,"Guest helper must be read-only");
            command(in,out,"writel 0x500f4004 6");
            require(Long.decode(command(in,out,"readl 0x500f400c"))==0,"Helper open failed");
            int handle=Long.decode(command(in,out,"readw 0x3000800a")).intValue();
            pb.putShort(10,(short)handle);pb.putInt(16,64);pb.putInt(20,0);pb.putInt(24,0x30010ff0);
            command(in,out,"write 0x30008000 1068 0x"+hex(raw));
            command(in,out,"writel 0x500f4004 7");
            require(Long.decode(command(in,out,"readl 0x500f400c"))==0,"Helper read failed");
            require(command(in,out,"read 0x30010ff0 64").equalsIgnoreCase("0x"+hex(Arrays.copyOf(Files.readAllBytes(helper.toPath()),64))),"Helper bytes differ");
            command(in,out,"writel 0x500f4004 0xe");
            require(Long.decode(command(in,out,"readl 0x500f400c"))==5,"Guest helper deletion must fail");
            require(!new File(card,"2577").exists(),"Virtual helper must not create real card files");
            return "PASS actual Android engine app-UID helper metadata/read-only/open/read/deny-delete; private card untouched; CPU paused.\n";
        } finally {
            engine.destroy();require(engine.waitFor(5,TimeUnit.SECONDS),"Owned native test process did not exit");
        }
    }
    public void onStart() {
        Bundle result=new Bundle();
        try {String kernel=run();require(kernel.contains("immutability_failures=0"),kernel);
            result.putString("stream",kernel+delivery());finish(-1,result);}
        catch(Throwable error) {result.putString("stream",android.util.Log.getStackTraceString(error));finish(0,result);}
    }
}
