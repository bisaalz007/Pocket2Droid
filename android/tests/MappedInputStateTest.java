package com.samsixx.pocket2droid;
import java.util.*;
public class MappedInputStateTest {
 static int checks;static void eq(Object a,Object b){checks++;if(!a.equals(b))throw new AssertionError(checks+": "+a+" != "+b);}
 public static void main(String[]args){List<String>e=new ArrayList<>();MappedInputState s=new MappedInputState(ButtonBindings.defaults(),(k,d)->e.add(k+":"+d));
  s.input(1,"key:61",true);s.input(2,"key:61",true);s.touch(GuestKey.TAB,true);s.input(1,"key:61",true);eq(e.size(),1);s.releaseDevice(1);eq(e.size(),1);s.input(2,"key:61",false);eq(e.size(),1);s.touch(GuestKey.TAB,false);eq(e.toString(),"[TAB:true, TAB:false]");
  e.clear();for(String t:new String[]{"key:61","key:62","key:66","dpad:left"})s.input(1,t,true);eq(e.size(),4);s.input(2,"key:61",true);s.releaseDevice(1);eq(e.size(),7);s.releaseDevice(2);eq(e.size(),8);
  e.clear();s.touch(GuestKey.TAB,true);s.input(1,"key:61",true);s.bindings(ButtonBindings.defaults().assign(GuestKey.SPACE,"key:61").bindings);eq(e.size(),1);s.input(1,"key:61",false);eq(e.size(),1);s.touch(GuestKey.TAB,false);eq(e.get(1),"TAB:false");s.input(1,"key:61",true);eq(e.get(2),"SPACE:true");s.releaseAll();eq(e.get(3),"SPACE:false");s.input(1,"key:96",true);s.input(1,"key:96",false);eq(e.size(),4);
  System.out.println("MappedInputState: "+checks+" assertions pass");
 }
}
