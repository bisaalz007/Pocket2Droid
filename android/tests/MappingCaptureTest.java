package com.samsixx.pocket2droid;
import java.util.*;
public class MappingCaptureTest {
 static int checks;static void ok(boolean v){checks++;if(!v)throw new AssertionError("capture "+checks);}
 public static void main(String[]args){
  class Disk implements ButtonMappingStore.Persistence {String value;boolean fail;public String read(){return value;}public boolean write(String s){if(fail)return false;value=s;return true;}}
  Disk d=new Disk();ButtonMappingStore store=new ButtonMappingStore(d);List<String>log=new ArrayList<>();MappingCapture c=new MappingCapture(store,t->t.equals("key:96")?"Controller A":t,new MappingCapture.Listener(){public void selected(GuestKey k,boolean l){}public void message(String m){log.add(m);}});
  c.select(GuestKey.TAB);ok(log.get(0).equals("Press any key to assign Tab"));c.input(1,"key:96",true,false);ok(c.listening());c.input(1,"key:96",false,true);ok(c.listening());c.input(1,"key:96",true,true);ok(!c.listening());ok(log.get(1).equals("Tab mapped as Controller A"));ok(store.current().resolve("key:96")==GuestKey.TAB);
  c.select(GuestKey.SPACE);c.input(1,"key:96",true,true);ok(log.get(log.size()-1).contains("Tab assignment cleared"));ok(store.current().customInput(GuestKey.TAB)==null);
  d.fail=true;c.select(GuestKey.TAB);c.input(1,"key:61",true,true);ok(c.listening());ok(!log.get(log.size()-1).contains("mapped as"));ok(store.current().customInput(GuestKey.TAB)==null);ok(!c.clearSelected());d.fail=false;c.select(GuestKey.SPACE);ok(c.clearSelected());ok(store.current().resolve("key:96")==null);
  c.select(GuestKey.TAB);c.select(GuestKey.HOME);ok(c.selected()==GuestKey.HOME);c.cancel();ok(!c.listening());c.input(1,"key:96",true,true);ok(store.current().resolve("key:96")==null);ok(c.reset());ok(c.selected()==null);
  System.out.println("MappingCapture: "+checks+" assertions pass");
 }
}
