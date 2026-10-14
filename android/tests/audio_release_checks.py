"""Current V6.60 evidence and isolated S25 smoke setup; never real guest data."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, shlex, subprocess, uuid
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parent;PROJECT=ROOT.parents[1]
REQUIRED=('native_correctness','copied_guest_pcm','engine_art','audio_art','audible_system','audible_game',
          'focus_pause_resume','normal_save_reopen','private_data_only','overhead_reviewed')
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def validate_record(record,expected):
    for key in ('version','apk_sha256','native_sha256','source_hashes'):
        if record.get(key)!=expected[key]:raise ValueError('Stale sound evidence: '+key)
    for key in REQUIRED:
        if record.get('checks',{}).get(key) is not True:raise ValueError('Sound check missing: '+key)
def main():
    p=argparse.ArgumentParser();p.add_argument('--device',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--prepare',action='store_true');a=p.parse_args()
    adb=PROJECT/'tools/platform-tools/adb.exe';package='com.samsixx.p2dtest'
    def call(*args,binary=False):
        r=subprocess.run([str(adb),'-s',a.device,*map(str,args)],capture_output=True,timeout=60)
        if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace')+r.stdout.decode(errors='replace'))
        return r.stdout if binary else r.stdout.decode(errors='replace')
    def shell(*args):return call('shell',shlex.join(map(str,args)))
    build=json.loads((HERE/'build/smoke-build.json').read_text());native=json.loads((HERE/'build/bionic-engine.json').read_text())
    assert build['version']=='6.60' and build['test_only'] and build['package']==package
    info=shell('dumpsys','package',package);assert 'versionCode=660' in info and 'DEBUGGABLE' in info
    source_hashes={str(x.relative_to(HERE)):sha(x) for x in [HERE/'AndroidManifest.xml',*sorted((HERE/'src').rglob('*.java')),*[p for p in (HERE/'native').rglob('*') if p.suffix in ('.c','.h')]]}
    record={'version':'6.60','apk_sha256':build['apk_sha256'],'native_sha256':native['binary_sha256'],
            'source_hashes':source_hashes,'device':a.device,'model':shell('getprop','ro.product.model').strip(),
            'checks':{key:False for key in REQUIRED},'original_user_data_accessed':False}
    if a.prepare:
        public='/sdcard/.p2d-disposable-frontend/pocket2droid'
        assert not shell('sh','-c','test -e '+shlex.quote(public)+' && echo present || true').strip(),'Preserve existing disposable folder; inspect before reuse'
        master=PROJECT/'DOCUMENTATION/PHONE_EVIDENCE/v656-doov/copy-405494e22c';manifest=json.loads((master/'COPY.json').read_text())
        shell('mkdir','-p',public+'/Roms',public+'/data',public+'/sdcard/Program Files/RagingThunder')
        rom=PROJECT/'PC windows mobile 6 Files/Roms and files/pocket pc/Deviceemulation/0409/PPC_USA.BIN'
        call('push',rom,public+'/Roms/PPC_USA.BIN')
        originals={'ROM':sha(rom)}
        for name,identity in manifest['files'].items():
            assert Path(name).name==name and name in ('ram-fmd.bin','ragingthunder.exe','data_highend_eng.vfs','setup.dll')
            src=master/name;assert sha(src)==identity['sha256'];originals[name]=sha(src)
            target=public+('/data/ram-fmd.bin' if name=='ram-fmd.bin' else '/sdcard/Program Files/RagingThunder/'+name)
            call('push',src,target);assert shell('sha256sum',target).split()[0]==identity['sha256']
        assert shell('sha256sum',public+'/Roms/PPC_USA.BIN').split()[0]==originals['ROM']
        record['copied_input_hashes']=originals;record['test_public_root']=public;record['checks']['private_data_only']=True
        shell('appops','set',package,'MANAGE_EXTERNAL_STORAGE','allow')
        shell('am','start','-n',package+'/com.samthedev.pocket2droid.MainActivity')
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'state':'disposable_sound_app_ready','device':a.device,'model':record['model'],'output':str(a.output)}))
if __name__=='__main__':main()
