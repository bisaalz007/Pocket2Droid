"""Boot presentation gate only; no engine, ROM, device or save access."""
from pathlib import Path
import subprocess
android=Path(__file__).resolve().parents[1];out=android/'build/button-mapping/rom-loading/host';out.mkdir(parents=True,exist_ok=True)
subprocess.run(['javac','--release','8','-d',str(out),str(android/'src/com/samsixx/pocket2droid/RomBootState.java'),str(android/'tests/RomBootStateTest.java')],check=True)
subprocess.run(['java','-cp',str(out),'com.samsixx.pocket2droid.RomBootStateTest'],check=True)
