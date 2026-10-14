package com.samthedev.pocket2droid;
public class RomBootStateTest {
 static int checks;static void check(boolean v){checks++;if(!v)throw new AssertionError("check "+checks);}
 public static void main(String[]args){
  check(!RomBootState.hasPicture(new int[]{0,0xff000000,0x0000ff00}));
  check(RomBootState.hasPicture(new int[]{0xff000000,0xffffffff}));
  check(RomBootState.hasPicture(new int[]{0xff000001}));
  RomBootState b=new RomBootState();b.starting(0);check(b.waiting());check(!b.picture(0,0));check(!b.picture(1,2));check(b.waiting());check(b.picture(1,1));check(!b.waiting());check(!b.picture(1,1));
  b.starting(1);check(!b.picture(1,1));check(b.waiting());check(b.picture(2,2));b.starting(2);b.failed();check(!b.waiting());check(!b.picture(3,3));
  System.out.println("Rom boot state: "+checks+" assertions pass");
 }
}
