"""Bounded deterministic IIS export cost; explicitly not full guest/FPS timing."""
from pathlib import Path
import hashlib,json,statistics,struct,subprocess,tempfile,zipfile
from test_audio_scheduling import compile_model
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix='p2d-audio-cost-') as tmp:
    d=Path(tmp)
    with zipfile.ZipFile(ROOT.parents[1]/'apk/6.59/Pocket2Droid-V6.59-TCG-Source.zip') as z:
        old=d/'baseline-source.c';old.write_bytes(z.read('qemu-canonical-changes/hw/dma/p2d-iis-dma.c'))
    current=ROOT/'qemu/hw/dma/p2d-iis-dma.c'
    binaries={}
    for name,source in [('baseline',old),('candidate',current)]:
        binary=compile_model(source,d,name)
        generated=d/(name+'.c');code=generated.read_text()
        code='#include <time.h>\n'+code
        code=code.replace('if(scenario==0) {','if(scenario==16) {\n'
            'configure(&s,50000,true); struct timespec a,b;\n'
            'clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&a);\n'
            'drain(&s,250LL*1000000000,false);\n'
            'clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&b);\n'
            'fprintf(stderr,"%lld\\n",(long long)(b.tv_sec-a.tv_sec)*1000000000+b.tv_nsec-a.tv_nsec);snapshot(&s);\n'
            '} else if(scenario==0) {')
        generated.write_text(code)
        subprocess.run(['cc','-O2','-std=gnu11','-I'+str(ROOT/'qemu/include'),str(generated),str(ROOT/'qemu/hw/dma/p2d-audio.c'),'-o',str(binary)],check=True)
        binaries[name]=binary
    samples={k:[] for k in ('baseline','muted','enabled')};states={};packets=[]
    for _ in range(3):
        for label in samples:
            audio=d/'audio.bin';data=bytearray(67648);struct.pack_into('<5I',data,0,0x41443250,1,67648,64,65536);audio.write_bytes(data)
            command=[str(binaries['baseline' if label=='baseline' else 'candidate']),'16']
            if label=='enabled':command.append(str(audio))
            result=subprocess.run(command,capture_output=True,text=True,check=True,timeout=30)
            samples[label].append(int(result.stderr.strip()));states[label]=json.loads(result.stdout)
            if label=='enabled':packets.append(struct.unpack_from('<I',audio.read_bytes(),20)[0])
    assert states['baseline']==states['muted']==states['enabled'],states
    med={k:statistics.median(v) for k,v in samples.items()}
    report={'scope':'x86 Linux IIS-only model, 250 virtual seconds per run, not Android/full-guest FPS',
        'source_hashes':{'baseline':sha(old),'candidate':sha(current),'transport':sha(ROOT/'qemu/hw/dma/p2d-audio.c')},
        'cpu_ns':samples,'median_cpu_ms_per_guest_second':{k:v/250/1e6 for k,v in med.items()},
        'muted_vs_baseline_percent':100*(med['muted']/med['baseline']-1),
        'enabled_vs_muted_percent':100*(med['enabled']/med['muted']-1),
        'native_export_extra_cpu_ms_per_guest_second':(med['enabled']-med['muted'])/250/1e6,
        'batch_publications_per_run':packets,'guest_state_identical':True,'guest_state':states['enabled']}
    out=ROOT/'android/build/audio-tests/native-overhead.json';out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
