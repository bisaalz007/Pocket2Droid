package com.samsixx.pocket2droid;
import java.io.*;
import java.nio.charset.StandardCharsets;
import org.json.*;

/** Roll-forward metadata transaction. It can overwrite metadata only, never saves. */
final class ProfileFiles {
    static String name(String value)throws IOException {
        if(value==null||value.isEmpty()||value.startsWith(".")||value.length()>180||value.contains("/")||value.contains("\\")||value.indexOf('\0')>=0||value.indexOf('\n')>=0||value.indexOf('\r')>=0||!value.equals(value.trim()))throw new IOException("Invalid ROM filename");
        return value;
    }
    static void plain(File f)throws IOException {
        File expected=new File(f.getParentFile().getCanonicalFile(),f.getName());
        if(!expected.equals(f.getCanonicalFile()))throw new IOException("Redirected path refused: "+f.getName());
    }
    static void dir(File f)throws IOException{plain(f);if(!f.isDirectory()&&!f.mkdirs())throw new IOException("Cannot create folder: "+f);}
    static String read(File f)throws IOException {
        plain(f);if(!f.isFile()||f.length()>1024*1024)throw new IOException("Missing or invalid metadata: "+f.getName());
        try(InputStream in=new FileInputStream(f);ByteArrayOutputStream out=new ByteArrayOutputStream()){
            byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1){out.write(b,0,n);if(out.size()>1024*1024)throw new IOException("Metadata too large");}return new String(out.toByteArray(),StandardCharsets.UTF_8);
        }
    }
    static JSONObject object(File f)throws IOException{try{return new JSONObject(read(f));}catch(JSONException e){throw new IOException("Invalid metadata; existing data preserved",e);}}
    static void write(File f,String value)throws IOException {
        plain(f);dir(f.getParentFile());
        try(FileOutputStream out=new FileOutputStream(f)){out.write(value.getBytes(StandardCharsets.UTF_8));out.getFD().sync();}
        if(!read(f).equals(value)||!StoragePublish.syncDirectory(f.getParentFile()))throw new IOException("Cannot verify durable metadata");
    }
    static File journal(File runtime){return new File(runtime,"library-write.pending.json");}
    static void publishJournal(File target,String value,File runtime)throws IOException {
        try{new JSONObject(value);}catch(JSONException e){throw new IOException("Invalid journal; publication blocked",e);}
        plain(target);dir(runtime);File pending=File.createTempFile(target.getName()+".",".pending",runtime);
        try{write(pending,value);StoragePublish.publish(pending,target,runtime);if(!StoragePublish.syncDirectory(runtime))throw new IOException("Journal publication sync failed");}
        finally{StoragePublish.cleanupPending(pending,runtime);}
    }
    static File target(File root,String path)throws IOException {
        String[] parts=path.split("/",-1);
        if(!(parts.length==2&&parts[0].equals("data")&&(parts[1].equals("library.json")||parts[1].equals("library-order.json")))&&!(parts.length==3&&parts[0].equals("data")&&name(parts[1]).equals(parts[1])&&parts[2].equals("profile.json")))throw new IOException("Invalid metadata recovery target");
        File f=new File(root,path);plain(new File(root,"data"));plain(f.getParentFile());plain(f);return f;
    }
    static void commit(File root,File runtime,JSONObject... writes)throws IOException {
        recover(root,runtime);
        try {
            JSONArray list=new JSONArray();for(JSONObject item:writes){target(root,item.getString("path"));new JSONObject(item.getString("text"));list.put(item);}
            publishJournal(journal(runtime),new JSONObject().put("schema",1).put("writes",list).toString(),runtime);
            recover(root,runtime);
        }catch(JSONException e){throw new IOException("Invalid metadata transaction",e);}
    }
    static JSONObject update(String path,JSONObject object)throws IOException{try{return new JSONObject().put("path",path).put("text",object.toString());}catch(JSONException e){throw new IOException(e);}}
    static void recover(File root,File runtime)throws IOException {
        File j=journal(runtime);plain(j);if(!j.exists())return;
        try {
            JSONObject o=object(j);if(o.getInt("schema")!=1)throw new IOException("Unknown metadata transaction schema");
            JSONArray writes=o.getJSONArray("writes");if(writes.length()<1||writes.length()>2)throw new IOException("Invalid metadata transaction size");
            // Validate the entire record before changing any target.
            for(int i=0;i<writes.length();i++){JSONObject w=writes.getJSONObject(i);target(root,w.getString("path"));new JSONObject(w.getString("text"));}
            for(int i=0;i<writes.length();i++){JSONObject w=writes.getJSONObject(i);write(target(root,w.getString("path")),w.getString("text"));}
            if(!j.delete()||!StoragePublish.syncDirectory(runtime))throw new IOException("Metadata recovery incomplete");
        }catch(JSONException e){throw new IOException("Invalid metadata recovery record; files preserved",e);}
    }
}
