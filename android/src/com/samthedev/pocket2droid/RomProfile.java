package com.samthedev.pocket2droid;
import java.io.File;
final class RomProfile {
    final String filename,displayName,iconId,error,saveState;
    final File rom,storage;
    final RomSettings settings;
    RomProfile(String name,String icon,File rom,File storage,RomSettings settings,String state,String error){
        filename=name;iconId=icon;this.rom=rom;this.storage=storage;this.settings=settings;displayName=settings.displayName;saveState=state;this.error=error;
    }
}
