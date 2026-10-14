"""Read-only reference/real ARM driver proof. No guest boot or user storage."""
from pathlib import Path
import contextlib, importlib.util, io, json, re, struct, sys, hashlib
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC
android=Path(__file__).resolve().parents[1];out=android/'build/button-mapping';audit=android/'build/key-audit'
text=(out/'vktoscan.c').read_text()
table=[int(x,16) for x in re.findall(r'0x[0-9a-f]+',text.split('VKtoSCTable[256] = {')[1].split('};')[0])]
assert len(table)==256
fn=dict((int(a,16),int(b,16)) for a,b in re.findall(r'\{ (0x\w+), (0x\w+) \}',text.split('g_rgvkMapFn[21]')[1].split('};')[0]))
digits={str(n):table[0x30+n] for n in range(10)}
sequences={k:{'make':[v],'break':[v|0x80],'guest_vk':0x30+int(k)} for k,v in digits.items()}
for name,vk in [('f8',0x77),('f9',0x78)]:
    scan=table[fn[vk]]
    sequences[name]={'make':[0x63,scan,0xe3],'break':[0x63,scan|0x80,0xe3],'guest_vk':vk}
assert sequences==json.loads((android/'tests/fixtures/sdk-keypad.json').read_text())['sequences'],'Frozen protocol differs from pinned reference'
regs=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]
def call(uc,pc,args):
    for r,v in zip(regs,args):uc.reg_write(r,v)
    uc.reg_write(UC_ARM_REG_SP,0x701e000);uc.reg_write(UC_ARM_REG_LR,0x7000000)
    uc.emu_start(pc,0x7000000,count=10000)
    assert uc.reg_read(UC_ARM_REG_PC)==0x7000000
    return uc.reg_read(UC_ARM_REG_R0)
drivers=[]
for folder in ('classic-rom','professional-rom-pass2'):
    path=audit/folder/'fs/Windows/kbdmouse.dll'
    argv=sys.argv[:];sys.argv=['inspect_game.py',str(path)]
    spec=importlib.util.spec_from_file_location('keypad_pe',audit/'inspect_game.py');pe=importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()):spec.loader.exec_module(pe)
    sys.argv=argv
    uc=Uc(UC_ARCH_ARM,UC_MODE_ARM);pages=set()
    for a,z,p in [(s,z,p) for _,s,z,p,_ in pe.sections]+pe.aliases:
        for page in range(a&~4095,(a+z+4095)&~4095,4096):
            if page not in pages:uc.mem_map(page,4096);pages.add(page)
        uc.mem_write(a,pe.data[p:p+z])
    uc.mem_map(0x7000000,0x20000)
    config=pe.word(pe.exports['Matrix']+0x3c)
    size,flags,ranges,count,callback=struct.unpack('<5I',pe.data[pe.offset(config):pe.offset(config)+20]);assert(size,flags,count)==(20,8,1)
    mapper=pe.instructions[pe.exports['KeybdDriverMapVirtualKey']+0x88].operands[0].imm
    checked=[]
    for key,seq in sequences.items():
        for phase in ('make','break'):
            events=[]
            for scan in seq[phase]:
                # Fn is a PDD modifier. This extracted layout's raw scan table
                # does not admit 0x63; prove the original emulator bytes from
                # source, and the layout Fn callback from its VK separately.
                if scan&0x7f==0x63: vk=0xc1
                else:
                    found=call(uc,mapper,[scan&0x7f,ranges,count,0x7001000]);assert found==1,(folder,key,phase,hex(scan),found)
                    vk=struct.unpack('<I',uc.mem_read(0x7001000,4))[0]
                uc.mem_write(0x7002000,struct.pack('<3I',vk,scan&0x7f,0 if scan&0x80 else 0x80))
                produced=call(uc,callback,[0x7002000,1,0x7003000,1])
                if produced:events.append(struct.unpack('<3I',uc.mem_read(0x7003000,12)))
            assert len(events)==1 and events[0][0]==seq['guest_vk'] and bool(events[0][2]&0x80)==(phase=='make'),(key,phase,events)
            checked.append({'key':key,'phase':phase,'events':events})
        # Fn state is proven released by a subsequent plain 8 (not F8).
        assert call(uc,mapper,[digits['8'],ranges,count,0x7001000])==1
        uc.mem_write(0x7002000,struct.pack('<3I',0x38,digits['8'],0x80))
        assert call(uc,callback,[0x7002000,1,0x7003000,1])==1
        assert struct.unpack('<I',uc.mem_read(0x7003000,4))[0]==0x38
    drivers.append({'folder':folder,'sha256':hashlib.sha256(pe.data).hexdigest(),'checks':checked})
result={'revision':'0f23982a1047b1b2d0dcebe7d9d82ac09a29b63f','reference_sha256':hashlib.sha256((out/'vktoscan.c').read_bytes()).hexdigest(),'sequences':sequences,'drivers':drivers,'limit':'Digits execute raw scan translation. Fn bytes verified against original emulator source; extracted layout callback is tested with its VK_FN (0xc1), not PDD preprocessing. No full guest boot or Smartphone game behavior claim.'}
(out/'sdk-keypad.json').write_text(json.dumps(result,indent=2))
print('PASS: 48 digit / Fn callback make-break checks in two ARM drivers; Fn released; original emulator sequences verified (PDD preprocessing untested)')
