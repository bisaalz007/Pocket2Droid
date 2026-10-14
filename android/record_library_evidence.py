"""Record final tested frontend identity and explicit manual boot observation."""
from pathlib import Path
import hashlib,importlib.util,json
HERE=Path(__file__).resolve().parent;B=HERE/'build/library-tests'
spec=importlib.util.spec_from_file_location('integrity',HERE/'finalize_release.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def main():
    ui=json.loads((B/'pc-ui-result.json').read_text())
    assert ui.get('rom_settings_fullscreen_exit_delete') is True
    image=B/'guest-6no8ulup/1-OS_B.BIN.png'
    assert image.is_file()
    observation={
        'second_rom_today_visually_confirmed':True,
        'automated_template_match':False,
        'image':str(image),'image_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
        'observation':'Manual screenshot inspection confirms the phone-ROM Today screen: Start, owner info, no messages/tasks/appointments and Live Search. Its theme differs from ROM A, so the A-specific template does not match.',
        'timing_claimed':False,
        'scope':'Copied complete OS on x86/WSL; not Android gameplay or boot performance.'
    }
    (B/'guest-visual-verification.json').write_text(json.dumps(observation,indent=2)+'\n')
    (B/'tested-sources.json').write_text(json.dumps(m.tested_source_hashes(),indent=2)+'\n')
    print('Recorded final frontend identity and second-ROM visual boot observation',flush=True)

if __name__=='__main__':main()
