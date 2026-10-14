package com.samthedev.pocket2droid;
final class ButtonMappingStore {
 interface Persistence {String read();boolean write(String value);}
 private final Persistence persistence;private ButtonBindings accepted;
 ButtonMappingStore(Persistence p){persistence=p;try{accepted=ButtonBindings.parse(p.read());}catch(RuntimeException e){accepted=ButtonBindings.defaults();}}
 ButtonBindings current(){return accepted;}
 boolean save(ButtonBindings value){try{if(value==null||!persistence.write(value.serialize()))return false;accepted=value;return true;}catch(RuntimeException e){return false;}}
}
