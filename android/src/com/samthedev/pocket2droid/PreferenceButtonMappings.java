package com.samthedev.pocket2droid;
import android.content.*;
final class PreferenceButtonMappings implements ButtonMappingStore.Persistence {
 static final String KEY="button_mapping_v1";private static final Object LOCK=new Object();private final SharedPreferences prefs;
 PreferenceButtonMappings(Context context){prefs=context.getSharedPreferences("settings",Context.MODE_PRIVATE);}
 public String read(){synchronized(LOCK){Object value=prefs.getAll().get(KEY);return value instanceof String?(String)value:null;}}
 public boolean write(String value){synchronized(LOCK){String old=read();try{if(prefs.edit().putString(KEY,value).commit())return true;}catch(RuntimeException e){/* Restore the accepted in-memory snapshot too. */}
  SharedPreferences.Editor rollback=prefs.edit();if(old==null)rollback.remove(KEY);else rollback.putString(KEY,old);try{rollback.commit();}catch(RuntimeException e){/* UI will report failure. */}return false;
 }}
 static ButtonBindings load(Context context){return new ButtonMappingStore(new PreferenceButtonMappings(context)).current();}
}
