package com.samsixx.pocket2droid;
import java.io.RandomAccessFile;

/** The parent owns a shared lock and checks that actual initialization waits. */
public final class FrameResetTest {
    public static void main(String[] args)throws Exception{
        try(RandomAccessFile file=new RandomAccessFile(args[0],"rw")){
            System.out.println("INITIALIZING");System.out.flush();
            FrameProtocol.initialize(file,240,320);
        }
        System.out.println("PASS locked monotonic frame initialization");
    }
}
