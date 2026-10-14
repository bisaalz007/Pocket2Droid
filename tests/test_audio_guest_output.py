"""Export hook runs inside actual media_event; independent stereo expectations."""
import struct, subprocess, tempfile, unittest
from pathlib import Path
from test_audio_scheduling import ROOT
class GuestOutputTests(unittest.TestCase):
    def test_fifo_mute_phase_and_clock_transitions(self):
        text=(ROOT/'qemu/hw/dma/p2d-iis-dma.c').read_text()
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);h=(ROOT/'tests/audio-model-harness.c').read_text().replace('int main(', 'int scheduling_main(')
            model=text[text.index('typedef struct P2DMedia'):text.index('static const MemoryRegionOps')]
            model+=text[text.index('static void media_clock'):text.index('static void media_reset')]
            model+=text[text.index('static void media_reset'):text.index('static void media_realize')]
            soc=(ROOT/'qemu/hw/misc/p2d-devemu-services.c').read_text()
            model+=soc[soc.index('static void timer_before_update'):soc.index('static void p2d_timer_expired')]
            generated=d/'guest.c';generated.write_text('#include "hw/arm/p2d-audio.h"\n'+h.replace('/* MODEL */',model)+(ROOT/'tests/audio-guest-harness.c').read_text())
            binary=d/'guest';subprocess.run(['cc','-O2','-std=gnu11','-I'+str(ROOT/'qemu/include'),str(generated),str(ROOT/'qemu/hw/dma/p2d-audio.c'),'-o',str(binary)],check=True)
            path=d/'audio.bin';data=bytearray(67648);struct.pack_into('<5I',data,0,0x41443250,1,67648,64,65536);path.write_bytes(data)
            subprocess.run([str(binary),str(path)],check=True)
            data=path.read_bytes();wp,rp=struct.unpack_from('<2I',data,20);self.assertEqual(wp-rp,1)
            epoch,rate,frames,start=struct.unpack_from('<4I',data,64+(rp%64)*32)
            self.assertEqual((rate,frames),(44100,1));self.assertEqual(struct.unpack_from('<2h',data,2112+start%65536),(77,88))
            # Earlier published payload remains for independent ordering checks even after epoch flush.
            self.assertEqual(struct.unpack_from('<4h',data,2112),(32767,-32768,123,-456))
            self.assertEqual(struct.unpack_from('<2h',data,2120),(55,66))
if __name__=='__main__': unittest.main()
