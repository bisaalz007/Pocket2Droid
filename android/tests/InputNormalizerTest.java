package com.samthedev.pocket2droid;
import java.util.*;
public class InputNormalizerTest {
 static int checks;static void eq(Object a,Object b){checks++;if(!a.equals(b))throw new AssertionError(checks+": "+a+" != "+b);}
 public static void main(String[]args){
  List<String> events=new ArrayList<>();InputNormalizer n=new InputNormalizer((d,t,p,f)->events.add(d+":"+t+":"+p+":"+f));
  n.axis(8,"x","stick:left:x",.50f,-1,1,0);n.beginCapture();n.axis(8,"x","stick:left:x",.65f,-1,1,0);eq(events.toString(),"[8:stick:left:x:+:true:false]");
  n.axis(8,"x","stick:left:x",0,-1,1,0);n.axis(8,"x","stick:left:x",.65f,-1,1,0);eq(events.get(2),"8:stick:left:x:+:true:true");n.releaseDevice(8);events.clear();
  n.key(9,96,true,0,100);n.beginCapture(150);n.key(9,96,true,1,100);eq(events.size(),1);n.key(9,96,true,0,200);eq(events.toString(),"[9:key:96:true:true, 9:key:96:false:false, 9:key:96:true:true]");n.key(9,96,false,0,100);n.key(9,96,true,0,200);eq(events.size(),3);n.key(9,96,false,0,200);eq(events.size(),4);n.releaseDevice(9);events.clear();
  n.axis(10,"trigger","trigger:left",0,0,1,0);n.key(10,104,true,0,300);n.axis(10,"trigger","trigger:left",1,0,1,0);n.beginCapture(350);n.key(10,104,true,1,300);eq(events.size(),1);n.key(10,104,true,0,400);eq(events.toString(),"[10:trigger:left:true:true, 10:trigger:left:false:false, 10:trigger:left:true:true]");n.axis(10,"trigger","trigger:left",1,0,1,0);eq(events.size(),3);n.key(10,104,false,0,400);eq(events.size(),3);n.axis(10,"trigger","trigger:left",0,0,1,0);eq(events.size(),4);n.releaseDevice(10);events.clear();
  n.axis(11,"hat","dpad:x",0,-1,1,0);n.axis(11,"hat","dpad:x",1,-1,1,0);n.beginCapture(450);n.key(11,22,true,0,430);eq(events.size(),1);n.key(11,22,true,0,500);eq(events.size(),3);n.releaseDevice(11);events.clear();
  n=new InputNormalizer((d,t,p,f)->events.add(d+":"+t+":"+p+":"+f));
  n.axis(1,"x","stick:left:x",0,-1,1,0);n.beginCapture();n.axis(1,"x","stick:left:x",.64f,-1,1,0);eq(events.size(),0);
  n.axis(1,"x","stick:left:x",.65f,-1,1,0);eq(events.toString(),"[1:stick:left:x:+:true:true]");n.axis(1,"x","stick:left:x",.36f,-1,1,0);eq(events.size(),1);n.axis(1,"x","stick:left:x",.34f,-1,1,0);eq(events.size(),2);
  events.clear();n.beginCapture();n.axis(2,"z","stick:right:x",1,-1,1,0);eq(events.get(0),"2:stick:right:x:+:true:false");n.axis(2,"z","stick:right:x",0,-1,1,0);n.axis(2,"z","stick:right:x",1,-1,1,0);eq(events.get(2),"2:stick:right:x:+:true:true");n.beginCapture();n.axis(2,"z","stick:right:x",1,-1,1,0);eq(events.size(),3);
  n.axis(2,"z","stick:right:x",-1,-1,1,0);eq(events.get(3),"2:stick:right:x:+:false:false");eq(events.get(4),"2:stick:right:x:-:true:false");
  events.clear();n.key(1,96,true,3);eq(events.get(0),"1:key:96:true:false");n.beginCapture();n.key(1,96,true,4);eq(events.size(),1);n.key(1,96,false,0);n.key(1,96,true,0);eq(events.get(2),"1:key:96:true:true");
  events.clear();n.axis(3,"hatx","dpad:x",0,-1,1,0);n.key(3,22,true,0);n.axis(3,"hatx","dpad:x",1,-1,1,0);eq(events.size(),1);n.key(3,22,false,0);eq(events.size(),1);n.axis(3,"hatx","dpad:x",0,-1,1,0);eq(events.size(),2);
  events.clear();n.axis(4,"ltrigger","trigger:left",0,0,1,0);n.key(4,104,true,0);n.axis(4,"ltrigger","trigger:left",1,0,1,0);n.axis(4,"brake","trigger:left",1,0,1,0);eq(events.size(),1);n.key(4,104,false,0);n.axis(4,"ltrigger","trigger:left",0,0,1,0);eq(events.size(),1);n.axis(4,"brake","trigger:left",0,0,1,0);eq(events.size(),2);
  events.clear();n.axis(5,"rx","stick:right:x",100,0,200,20);n.axis(5,"rx","stick:right:x",170,0,200,20);eq(events.size(),0);n.axis(5,"rx","stick:right:x",172,0,200,20);eq(events.size(),1);n.axis(5,"rx","stick:right:x",147,0,200,20);eq(events.size(),2);
  events.clear();n.key(6,61,true,0);n.key(7,61,true,0);n.releaseDevice(6);eq(events.size(),3);eq(events.get(2),"6:key:61:false:false");n.releaseAll();eq(events.get(events.size()-1),"7:key:61:false:false");
  System.out.println("InputNormalizer: "+checks+" assertions pass");
 }
}
