package com.samthedev.pocket2droid;
import android.view.*;
import java.util.*;

/** Android extraction only. Capture and gameplay use the same pure normalizer. */
final class AndroidMappingInput {
 static final class Range {final float min,max,flat;Range(float min,float max,float flat){this.min=min;this.max=max;this.flat=flat;}}
 interface Ranges {Range get(MotionEvent event,int axis);}
 private final Ranges ranges;
 final InputNormalizer normalizer;
 AndroidMappingInput(InputNormalizer.Sink sink){this(sink,(e,a)->{InputDevice d=e.getDevice();InputDevice.MotionRange r=d==null?null:d.getMotionRange(a,e.getSource());return r==null?null:new Range(r.getMin(),r.getMax(),r.getFlat());});}
 AndroidMappingInput(InputNormalizer.Sink sink,Ranges ranges){normalizer=new InputNormalizer(sink);this.ranges=ranges;}
 void beginCapture(){normalizer.beginCapture(android.os.SystemClock.uptimeMillis());}
 boolean key(KeyEvent event){int action=event.getAction(),code=event.getKeyCode();if(ButtonBindings.reserved(code)||code<=0||(action!=KeyEvent.ACTION_DOWN&&action!=KeyEvent.ACTION_UP))return false;normalizer.key(event.getDeviceId(),code,action==KeyEvent.ACTION_DOWN,event.getRepeatCount(),event.getDownTime());return true;}
 boolean motion(MotionEvent e){if(!e.isFromSource(InputDevice.SOURCE_JOYSTICK)&&!e.isFromSource(InputDevice.SOURCE_GAMEPAD))return false;if(e.getActionMasked()!=MotionEvent.ACTION_MOVE)return false;
  boolean zr=ranges.get(e,MotionEvent.AXIS_Z)!=null&&ranges.get(e,MotionEvent.AXIS_RZ)!=null;
  for(int h=0;h<=e.getHistorySize();h++){
   axis(e,h,MotionEvent.AXIS_X,"stick:left:x");axis(e,h,MotionEvent.AXIS_Y,"stick:left:y");
   axis(e,h,zr?MotionEvent.AXIS_Z:MotionEvent.AXIS_RX,"stick:right:x");axis(e,h,zr?MotionEvent.AXIS_RZ:MotionEvent.AXIS_RY,"stick:right:y");
   axis(e,h,MotionEvent.AXIS_HAT_X,"dpad:x");axis(e,h,MotionEvent.AXIS_HAT_Y,"dpad:y");
   axis(e,h,MotionEvent.AXIS_LTRIGGER,"trigger:left");axis(e,h,MotionEvent.AXIS_BRAKE,"trigger:left");axis(e,h,MotionEvent.AXIS_RTRIGGER,"trigger:right");axis(e,h,MotionEvent.AXIS_GAS,"trigger:right");
  }return true;
 }
 private void axis(MotionEvent e,int h,int axis,String control){Range r=ranges.get(e,axis);if(r==null)return;float value=h==e.getHistorySize()?e.getAxisValue(axis):e.getHistoricalAxisValue(axis,h);normalizer.axis(e.getDeviceId(),"axis:"+axis,control,value,r.min,r.max,r.flat);}
 static String label(String token){
  if(token.startsWith("dpad:"))return "D-pad "+token.substring(5);
  if(token.startsWith("trigger:"))return (token.endsWith("left")?"Left":"Right")+" trigger";
  if(token.startsWith("stick:")){String[] p=token.split(":");return (p[1].equals("left")?"Left":"Right")+" stick "+(p[2].equals("x")?(p[3].equals("+")?"right":"left"):(p[3].equals("+")?"down":"up"));}
  try{int k=Integer.parseInt(token.substring(4));String name=KeyEvent.keyCodeToString(k).replace("KEYCODE_","");if(k>=96&&k<=110)return "Controller "+name.replace("BUTTON_","").replace('_',' ');return "Keyboard "+name.replace('_',' ');}catch(RuntimeException e){return token;}
 }
}
