package com.samthedev.pocket2droid;
import java.util.*;
import org.json.*;

/** Immutable custom assignments; default routes are overridden by input. */
final class ButtonBindings {
 private final EnumMap<GuestKey,String> custom;
 private ButtonBindings(EnumMap<GuestKey,String> map){custom=new EnumMap<>(map);}
 static ButtonBindings defaults(){return new ButtonBindings(new EnumMap<>(GuestKey.class));}
 static boolean validToken(String s){
  if(s==null)return false;
  if(s.matches("dpad:(up|down|left|right)|stick:(left|right):(x|y):[+-]|trigger:(left|right)"))return true;
  if(!s.matches("key:[1-9][0-9]{0,3}"))return false;
  try{int k=Integer.parseInt(s.substring(4));return k<=1023&&!reserved(k)&&!(k>=19&&k<=22)&&k!=104&&k!=105;}catch(NumberFormatException e){return false;}
 }
 static boolean reserved(int k){return k==3||k==4||k==26||k==24||k==25||k==27||k==79||k==82||k==164||k==187||k==223||k==224;}
 String customInput(GuestKey key){return custom.get(key);}
 GuestKey resolve(String token){for(Map.Entry<GuestKey,String> e:custom.entrySet())if(e.getValue().equals(token))return e.getKey();return defaultTarget(token);}
 static GuestKey defaultTarget(String t){
  if(t==null)return null;
  switch(t){case "dpad:up":return GuestKey.UP;case "dpad:down":return GuestKey.DOWN;case "dpad:left":return GuestKey.LEFT;case "dpad:right":return GuestKey.RIGHT;}
  if(!t.startsWith("key:"))return null;int k;try{k=Integer.parseInt(t.substring(4));}catch(NumberFormatException e){return null;}
  if(k>=7&&k<=16)return GuestKey.fromQcode(Integer.toString(k-7));
  if(k>=144&&k<=153)return GuestKey.fromQcode(Integer.toString(k-144));
  switch(k){case 23:case 66:case 160:return GuestKey.ENTER;case 61:return GuestKey.TAB;case 62:return GuestKey.SPACE;
   case 111:return GuestKey.BACK;case 67:return GuestKey.BACKSPACE;case 131:return GuestKey.SOFT_LEFT;case 132:return GuestKey.SOFT_RIGHT;
   case 5:case 133:return GuestKey.CALL;case 6:case 134:return GuestKey.END_CALL;case 117:return GuestKey.HOME;
   case 17:case 138:case 155:return GuestKey.STAR;case 18:case 139:return GuestKey.HASH;default:return null;}
 }
 static final class Change {
  final ButtonBindings bindings;final GuestKey displacedTarget;final String replacedInput;
  Change(ButtonBindings b,GuestKey d,String r){bindings=b;displacedTarget=d;replacedInput=r;}
 }
 Change assign(GuestKey target,String token){
  if(target==null||!target.visible||!validToken(token))throw new IllegalArgumentException("Invalid assignment");
  EnumMap<GuestKey,String> m=new EnumMap<>(custom);GuestKey displaced=null;String previous=m.remove(target);
  for(GuestKey k:GuestKey.values())if(token.equals(m.get(k))){m.remove(k);displaced=k;break;}
  m.put(target,token);return new Change(new ButtonBindings(m),displaced,previous);
 }
 ButtonBindings clear(GuestKey key){EnumMap<GuestKey,String> m=new EnumMap<>(custom);m.remove(key);return new ButtonBindings(m);}
 String serialize(){try{JSONObject entries=new JSONObject();for(GuestKey k:GuestKey.values())if(custom.containsKey(k))entries.put(k.name(),custom.get(k));return new JSONObject().put("version",1).put("bindings",entries).toString();}catch(JSONException e){throw new IllegalStateException(e);}}
 static ButtonBindings parse(String text){
  ButtonBindings b=defaults();if(text==null)return b;
  try{JSONObject j=new JSONObject(text);if(!(j.opt("version") instanceof Number)||j.getInt("version")!=1)return b;JSONObject entries=j.optJSONObject("bindings");if(entries==null)return b;
   Set<String> used=new HashSet<>();for(GuestKey k:GuestKey.values()){Object token=entries.opt(k.name());if(k.visible&&token instanceof String&&validToken((String)token)&&used.add((String)token))b=b.assign(k,(String)token).bindings;}
  }catch(JSONException|IllegalArgumentException e){return defaults();}return b;
 }
}
