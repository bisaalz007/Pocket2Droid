package com.samthedev.pocket2droid;
import java.util.*;
/** First-owner make, last-owner break; bindings are pinned on physical down. */
final class MappedInputState {
 interface Listener {void key(GuestKey key,boolean down);}
 private ButtonBindings bindings;private final Listener listener;
 private final Map<Integer,Map<String,GuestKey>> hardware=new HashMap<>();
 private final Set<GuestKey> touch=EnumSet.noneOf(GuestKey.class);
 private final EnumMap<GuestKey,Integer> counts=new EnumMap<>(GuestKey.class);
 MappedInputState(ButtonBindings b,Listener l){bindings=b;listener=l;}
 private void own(GuestKey k,boolean down){if(k==null)return;int old=counts.containsKey(k)?counts.get(k):0,next=old+(down?1:-1);if(next<=0)counts.remove(k);else counts.put(k,next);if(old==0&&next>0)listener.key(k,true);else if(old>0&&next<=0)listener.key(k,false);}
 void input(int id,String token,boolean down){Map<String,GuestKey> owners=hardware.get(id);if(down){if(owners!=null&&owners.containsKey(token))return;GuestKey k=bindings.resolve(token);if(k==null)return;if(owners==null){owners=new HashMap<>();hardware.put(id,owners);}owners.put(token,k);own(k,true);}else if(owners!=null){own(owners.remove(token),false);if(owners.isEmpty())hardware.remove(id);}}
 void touch(GuestKey k,boolean down){if(k==null)return;if(down?touch.add(k):touch.remove(k))own(k,down);}
 void bindings(ButtonBindings value){releaseHardware();bindings=value;}
 void releaseDevice(int id){Map<String,GuestKey> owners=hardware.remove(id);if(owners!=null)for(GuestKey k:owners.values())own(k,false);}
 void releaseHardware(){for(int id:new ArrayList<>(hardware.keySet()))releaseDevice(id);}
 void releaseAll(){releaseHardware();for(GuestKey k:new ArrayList<>(touch))touch(k,false);}
}
