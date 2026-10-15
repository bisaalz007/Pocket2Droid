package com.samsixx.pocket2droid;
import java.util.*;

/** Per-device reports coalesce into stable inputs. State survives focus gates. */
final class InputNormalizer {
 interface Sink {void input(int deviceId,String token,boolean down,boolean fresh);}
 private static final class Report {boolean down,blocked;long pressTime=Long.MIN_VALUE;String token;Report(String t){token=t;}}
 private static final class Axis {boolean armed,neutral;}
 private static final class Device {final Map<String,Report> reports=new LinkedHashMap<>();final Map<String,Axis> axes=new HashMap<>();}
 private final Map<Integer,Device> devices=new LinkedHashMap<>();private final Sink sink;private long gateTime=Long.MIN_VALUE;
 InputNormalizer(Sink sink){this.sink=sink;}
 private Device device(int id){Device d=devices.get(id);if(d==null){d=new Device();devices.put(id,d);}return d;}
 static String keyToken(int key){switch(key){case 19:return "dpad:up";case 20:return "dpad:down";case 21:return "dpad:left";case 22:return "dpad:right";case 104:return "trigger:left";case 105:return "trigger:right";default:return "key:"+key;}}
 private void report(int id,String channel,String token,boolean down,boolean fresh){Device d=device(id);Report r=d.reports.get(channel);if(r==null){r=new Report(token);d.reports.put(channel,r);}if(r.down==down)return;
  boolean before=held(d,token);r.down=down;r.blocked=false;boolean after=held(d,token);if(before!=after)sink.input(id,token,after,after&&fresh);
 }
 private boolean held(Device d,String token){for(Report r:d.reports.values())if(r.down&&r.token.equals(token))return true;return false;}
 void key(int id,int key,boolean down,int repeats){key(id,key,down,repeats,Long.MIN_VALUE);}
 void key(int id,int key,boolean down,int repeats,long pressTime){
  String channel="key:"+key,token=keyToken(key);Device d=device(id);Report old=d.reports.get(channel);
  if(old!=null&&pressTime!=Long.MIN_VALUE&&pressTime<old.pressTime)return;
  boolean newIdentity=old!=null&&old.pressTime!=Long.MIN_VALUE&&pressTime>old.pressTime;
  boolean fresh=down&&repeats==0&&(old==null||!old.down||newIdentity)&&pressTime>=gateTime;
  if(fresh){
   // A new physical press retires its previous aliases if their release went
   // to another window. Reports made since the gate still coalesce normally.
   boolean before=held(d,token);
   for(Report r:d.reports.values())if(r.token.equals(token)&&(newIdentity||r.blocked)){r.down=false;r.blocked=false;}
   if(before&&!held(d,token))sink.input(id,token,false,false);
  }
  report(id,channel,token,down,fresh);
  if(down)d.reports.get(channel).pressTime=pressTime;
 }
 void axis(int id,String channel,String control,float value,float min,float max,float flat){
  if(!Float.isFinite(value)||!Float.isFinite(min)||!Float.isFinite(max)||!Float.isFinite(flat)||max<=min)return;
  Device d=device(id);String axisId=channel+":"+control;Axis a=d.axes.get(axisId);if(a==null){a=new Axis();d.axes.put(axisId,a);}
  boolean trigger=control.startsWith("trigger:"),hat=control.startsWith("dpad:");
  float center=trigger?min:(min<0&&max>0?0:(min+max)/2);float delta=Math.max(min,Math.min(max,value))-center;
  float usable=delta>=0?max-center:center-min;float dead=Math.max(0,Math.min(flat,usable));
  float magnitude=usable>dead?Math.max(0,(Math.abs(delta)-dead)/(usable-dead)):0;
  a.neutral=hat?delta==0:magnitude<.35f;if(a.neutral)a.armed=true;
  if(trigger){transition(id,axisId,control,magnitude,a.armed,false);}
  else {
   String negative=hat?(control.endsWith("x")?"dpad:left":"dpad:up"):control+":-";
   String positive=hat?(control.endsWith("x")?"dpad:right":"dpad:down"):control+":+";
   // Release the old direction before pressing its opposite.
   if(delta>=0){transition(id,axisId+"-",negative,0,a.armed,hat);transition(id,axisId+"+",positive,magnitude,a.armed,hat);}
   else{transition(id,axisId+"+",positive,0,a.armed,hat);transition(id,axisId+"-",negative,magnitude,a.armed,hat);}
  }
 }
 private boolean heldChannel(Device d,String channel){Report r=d.reports.get(channel);return r!=null&&r.down;}
 private void transition(int id,String channel,String token,float magnitude,boolean fresh,boolean hat){boolean was=heldChannel(device(id),channel);boolean down=hat?magnitude>0:was?magnitude>=.35f:magnitude>=.65f;report(id,channel,token,down,fresh);}
 void beginCapture(){beginCapture(gateTime);}
 void beginCapture(long time){gateTime=Math.max(gateTime,time);for(Device d:devices.values()){for(Axis a:d.axes.values())a.armed=a.neutral;for(Report r:d.reports.values())if(r.down)r.blocked=true;}}
 void releaseDevice(int id){Device d=devices.remove(id);if(d==null)return;Set<String> released=new LinkedHashSet<>();for(Report r:d.reports.values())if(r.down)released.add(r.token);for(String t:released)sink.input(id,t,false,false);}
 void releaseAll(){for(int id:new ArrayList<>(devices.keySet()))releaseDevice(id);}
}
