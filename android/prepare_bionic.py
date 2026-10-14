"""Private verified NDK and Android library sysroot; never installs on phone."""
from pathlib import Path
import hashlib
import json
import gzip
import subprocess
import urllib.request
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=Path('/opt/pocket2droid-android-tools/bionic')
ROOT.mkdir(exist_ok=True)
DOWNLOADS=ROOT/'downloads';DOWNLOADS.mkdir(exist_ok=True)
PREFIX=ROOT/'sysroot/data/data/com.termux/files/usr'
URL='https://dl.google.com/android/repository/android-ndk-r30-linux.zip'
EXPECTED='5107f898313790e449e87eee2183d9a20602dee9' # Official NDK downloads page.

def download(url,path,algorithm,expected):
    def digest():
        d=hashlib.new(algorithm)
        with path.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):d.update(chunk)
        return d.hexdigest()
    if not path.exists() or digest()!=expected:
        temporary=path.with_suffix(path.suffix+'.partial')
        with urllib.request.urlopen(url,timeout=40) as incoming,temporary.open('wb') as out:
            while chunk:=incoming.read(1024*1024):out.write(chunk)
        temporary.replace(path)
    assert digest()==expected,'Download checksum mismatch: '+path.name
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    archive=DOWNLOADS/'android-ndk-r30-linux.zip'
    sha=download(URL,archive,'sha1',EXPECTED)
    print('Official NDK archive verified',flush=True)
    ndk=ROOT/'android-ndk-r30'
    if not (ndk/'.p2d-extract-complete').exists():
        with zipfile.ZipFile(archive) as z:
            for item in z.infolist():
                target=(ROOT/item.filename).resolve()
                assert target.is_relative_to(ROOT.resolve()),'Archive path escape'
        subprocess.run(['unzip','-q',str(archive),'-d',str(ROOT)],check=True)
        (ndk/'.p2d-extract-complete').write_text(sha+'\n')
    repository='https://packages.termux.dev/apt/termux-main/'
    release=urllib.request.urlopen(repository+'dists/stable/Release',timeout=20).read().decode()
    sha_section=release.split('SHA256:\n',1)[1].split('SHA512:',1)[0]
    expected_index=next(line.split()[0] for line in sha_section.splitlines() if line.strip().endswith('main/binary-aarch64/Packages.gz'))
    raw=urllib.request.urlopen(repository+'dists/stable/main/binary-aarch64/Packages.gz',timeout=30).read()
    assert hashlib.sha256(raw).hexdigest()==expected_index,'Package index checksum mismatch'
    text=gzip.decompress(raw).decode()
    (DOWNLOADS/'Packages').write_text(text)
    packages={}
    for block in text.split('\n\n'):
        fields={}
        for line in block.splitlines():
            if line and not line.startswith(' ') and ': ' in line:
                k,v=line.split(': ',1);fields[k]=v
        if 'Package' in fields:packages[fields['Package']]=fields
    requested=['glib','libffi','libiconv','pcre2','libpixman','zlib','libandroid-shmem',
               'libandroid-posix-semaphore','libandroid-spawn']
    done={}
    while requested:
        name=requested.pop()
        if name in done:continue
        if name in ['libc','libdl','libm','libpthread']:continue
        p=packages[name]
        path=DOWNLOADS/Path(p['Filename']).name
        digest=download(repository+p['Filename'],path,'sha256',p['SHA256'])
        subprocess.run(['dpkg-deb','-x',str(path),str(ROOT/'sysroot')],check=True)
        done[name]={'version':p['Version'],'sha256':digest,'url':repository+p['Filename']}
        for dep in p.get('Depends','').split(','):
            dependency=dep.strip().split(' ')[0].split(':')[0]
            if dependency and dependency in packages and dependency not in done:requested.append(dependency)
        print('Android dependency',name,p['Version'],flush=True)
    report={'ndk_url':URL,'ndk_sha256':sha,'ndk_sha1':EXPECTED,
            'package_index_sha256':hashlib.sha256(raw).hexdigest(),'packages':done,'prefix':str(PREFIX)}
    (HERE/'build/bionic-tools.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Android-native toolchain ready',flush=True)

if __name__=='__main__':main()
