package com.samthedev.pocket2droid;
import java.util.*;
public class GuestKeyTest {
 public static void main(String[] args){
  if(GuestKey.mappingTargets().size()!=25)throw new AssertionError("25 targets");
  Set<String>s=new HashSet<>();for(GuestKey k:GuestKey.values()){if(!s.add(k.qcode)||GuestKey.fromQcode(k.qcode)!=k)throw new AssertionError(k);}
  if(GuestKey.mappingTargets().contains(GuestKey.BACKSPACE))throw new AssertionError("Hidden Backspace");
  if(GuestKey.fromQcode("not-a-key")!=null)throw new AssertionError();
  System.out.println("GuestKey: 25 targets, unique transport and hidden Backspace pass");
 }
}
