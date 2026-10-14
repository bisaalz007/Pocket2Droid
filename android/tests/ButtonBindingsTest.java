package com.samthedev.pocket2droid;
public class ButtonBindingsTest {
 static int checks;static void ok(boolean v){checks++;if(!v)throw new AssertionError("binding "+checks);}
 public static void main(String[]args){
  ButtonBindings b=ButtonBindings.defaults();ok(b.resolve("key:61")==GuestKey.TAB);ok(b.resolve("key:96")==null);ok(b.resolve("dpad:up")==GuestKey.UP);
  b=b.assign(GuestKey.TAB,"key:96").bindings;ButtonBindings.Change c=b.assign(GuestKey.SPACE,"key:96");b=c.bindings;
  ok(c.displacedTarget==GuestKey.TAB);ok(b.customInput(GuestKey.TAB)==null);ok(b.resolve("key:96")==GuestKey.SPACE);
  c=b.assign(GuestKey.SPACE,"key:61");b=c.bindings;ok(c.replacedInput.equals("key:96"));ok(b.resolve("key:96")==null);ok(b.resolve("key:61")==GuestKey.SPACE);
  ok(b.clear(GuestKey.SPACE).resolve("key:61")==GuestKey.TAB);ok(ButtonBindings.parse(b.serialize()).resolve("key:61")==GuestKey.SPACE);
  ok(ButtonBindings.parse("bad").resolve("key:61")==GuestKey.TAB);ok(ButtonBindings.parse("{\"version\":2,\"bindings\":{\"TAB\":\"key:96\"}}").customInput(GuestKey.TAB)==null);
  b=ButtonBindings.parse("{\"version\":1,\"bindings\":{\"TAB\":\"key:96\",\"SPACE\":\"key:96\",\"BAD\":\"key:1\",\"HOME\":\"key:3\",\"STAR\":19}}");
  ok(b.resolve("key:96")==GuestKey.TAB);ok(b.customInput(GuestKey.HOME)==null);ok(b.customInput(GuestKey.STAR)==null);
  class Disk implements ButtonMappingStore.Persistence {String data;boolean fail;public String read(){return data;}public boolean write(String s){if(fail)return false;data=s;return true;}}
  Disk d=new Disk();ButtonMappingStore store=new ButtonMappingStore(d);ButtonBindings old=store.current();d.fail=true;ok(!store.save(old.assign(GuestKey.TAB,"key:96").bindings));ok(store.current()==old);d.fail=false;ok(store.save(old.assign(GuestKey.TAB,"key:96").bindings));ok(new ButtonMappingStore(d).current().resolve("key:96")==GuestKey.TAB);
  ok(store.save(ButtonBindings.defaults()));ok(new ButtonMappingStore(d).current().resolve("key:96")==null);
  ButtonMappingStore broken=new ButtonMappingStore(new ButtonMappingStore.Persistence(){public String read(){throw new RuntimeException();}public boolean write(String v){throw new RuntimeException();}});ok(broken.current().resolve("key:61")==GuestKey.TAB);ok(!broken.save(b));
  System.out.println("ButtonBindings: "+checks+" assertions pass");
 }
}
