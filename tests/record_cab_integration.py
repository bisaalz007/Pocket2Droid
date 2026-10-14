"""Record a reviewed full-installer screenshot with exact source identities."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path)
    p.add_argument('--success-observed',action='store_true');a=p.parse_args()
    run=a.run.resolve(strict=True);assert run.is_relative_to(ROOT/'results/runs') and a.success_observed
    report=json.loads((run/'session-final.json').read_text())
    assert report['normal_exit'] and report['original_inputs_unchanged'] and not report['pending_records']
    native=json.loads((ROOT/'android/build/bionic-engine.json').read_text())
    for name,digest in native['source']['paths'].items():
        assert sha(ROOT/'qemu'/name)==digest
        assert sha(Path('/opt/pocket2droid-tcg-build/source')/name)==digest
    assert report['engine_sha256']==sha(Path('/opt/pocket2droid-tcg-build/host/qemu-system-arm'))
    report.update(installer_success_observed=True,destination='Storage Card',
                  canonical_source_hashes=native['source']['paths'],
                  screenshot=str(run/'installed.png'),screenshot_sha256=sha(run/'installed.png'),
                  completed_session_sha256=sha(run/'session-final.json'),
                  scope='Copied full Windows Mobile guest with missing NOREPLACE forced; not Android gameplay timing')
    (ROOT/'android/build/v659-cab-integration.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS full copied Windows Mobile Storage Card CAB installation, source identities and originals preserved')
