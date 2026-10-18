from pathlib import Path
import fcntl,mmap,struct,subprocess,tempfile,time
here=Path(__file__).resolve().parents[1];out=here/'build/custom-resolution'
subprocess.run(['javac','--release','8','-d',str(out),str(here/'src/com/samsixx/pocket2droid/FrameProtocol.java'),str(here/'tests/FrameResetTest.java')],check=True)
with tempfile.TemporaryDirectory(prefix='p2d-frame-reset-') as tmp:
    file=Path(tmp)/'frame.bin';size=64+1280*960*4
    with file.open('w+b') as f:
        f.truncate(size);f.write(b'P2DF'+bytes(60));f.seek(size-4);f.write(struct.pack('<I',0xff123456));f.flush()
        with mmap.mmap(f.fileno(),size,access=mmap.ACCESS_READ) as view:
            fcntl.lockf(f,fcntl.LOCK_SH)
            p=subprocess.Popen(['java','-cp',str(out),'com.samsixx.pocket2droid.FrameResetTest',str(file)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            try:
                assert p.stdout.readline().strip()=='INITIALIZING'
                time.sleep(.15)
                assert p.poll() is None,'Initializer ignored the active reader lock'
                assert file.stat().st_size==size and view[:4]==b'P2DF'
                assert struct.unpack_from('<I',view,size-4)[0]==0xff123456
                fcntl.lockf(f,fcntl.LOCK_UN)
                result=p.communicate(timeout=5)[0]
                assert p.returncode==0 and 'PASS locked monotonic' in result,result
                assert file.stat().st_size==size and view[:64]==bytes(64)
                assert struct.unpack_from('<I',view,size-4)[0]==0xff123456
            finally:
                if p.poll() is None:p.kill();p.wait()
print('PASS actual frame initialization waits for reader, preserves mapped size/pixels, resets header after unlock')
