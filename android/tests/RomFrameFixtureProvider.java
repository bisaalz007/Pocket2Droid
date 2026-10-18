package com.samsixx.pocket2droid;
import android.content.*;import android.database.Cursor;import android.net.Uri;import android.os.Bundle;
import java.io.*;import java.nio.*;import java.nio.channels.*;
/** Separate owned process, like QEMU: Java in-process locks have different semantics. */
public final class RomFrameFixtureProvider extends ContentProvider {
 public boolean onCreate(){return true;}
 public Bundle call(String method,String argument,Bundle extras){
  String fixture=extras.getString("fixture","rom-loading-frame-fixture");if(!fixture.matches("[A-Za-z0-9_-]+"))throw new IllegalArgumentException("Invalid fixture directory");
  File base=new File(getContext().getFilesDir(),fixture);base.mkdirs();
  try(RandomAccessFile f=new RandomAccessFile(new File(base,"frames.bin"),"rw")){
   int w=extras.getInt("width",2),h=extras.getInt("height",3),bytes=FrameProtocol.frameBytes(w,h);
   try(FileLock lock=f.getChannel().lock()){
    f.setLength(Math.max(f.length(),Math.max(FrameProtocol.SIZE,bytes)));
    ByteBuffer b=ByteBuffer.allocate(bytes).order(ByteOrder.LITTLE_ENDIAN);b.putInt(0,0x46443250);b.putInt(4,1);b.putInt(8,w);b.putInt(12,h);b.putInt(16,1);b.putLong(24,extras.getLong("sequence"));for(int i=0;i<w*h;i++)b.putInt(64+i*4,extras.getInt("color"));f.seek(0);f.write(b.array());
   }
  }catch(Exception e){throw new IllegalStateException(e);}return Bundle.EMPTY;
 }
 public Cursor query(Uri u,String[]p,String s,String[]a,String o){return null;}public String getType(Uri u){return null;}public Uri insert(Uri u,ContentValues v){throw new UnsupportedOperationException();}public int delete(Uri u,String s,String[]a){throw new UnsupportedOperationException();}public int update(Uri u,ContentValues v,String s,String[]a){throw new UnsupportedOperationException();}
}
