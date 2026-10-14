"""Prepare a private, checksum-checked Android compiler cache in WSL."""
from pathlib import Path
import concurrent.futures
import hashlib
import json
import shutil
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

PREFIX = Path('/opt/pocket2droid-android-tools')
PREFIX.mkdir(exist_ok=True)
if not shutil.which('javac'):
    with (PREFIX / 'jdk-install.log').open('w') as log:
        subprocess.run(['apt-get', '--yes', '--no-install-recommends', 'install',
                        'openjdk-17-jdk-headless'], stdout=log,
                       stderr=subprocess.STDOUT, check=True)
print('JDK:', subprocess.check_output(['javac', '-version'], stderr=subprocess.STDOUT,
                                     text=True).strip(), flush=True)
repository = PREFIX / 'repository.xml'
if not repository.exists():
    with urllib.request.urlopen('https://dl.google.com/android/repository/repository2-3.xml', timeout=60) as r:
        repository.write_bytes(r.read())
tree = ET.fromstring(repository.read_bytes())
items = []
for name in ['platforms;android-36', 'build-tools;36.0.0']:
    package = next(x for x in tree.iter() if x.tag.endswith('remotePackage') and x.get('path') == name)
    candidates = package.find('archives').findall('archive')
    archive = next(x for x in candidates if x.findtext('host-os') in (None, 'linux'))
    complete = archive.find('complete')
    checksum = complete.find('checksum')
    items.append({'package': name, 'url': complete.findtext('url'),
                  'size': int(complete.findtext('size')),
                  'algorithm': checksum.get('type', 'sha1'), 'checksum': checksum.text})

def materialize(item):
    target = PREFIX / item['url']
    if not target.exists():
        temporary = target.with_suffix('.download')
        print('Downloading', item['url'], flush=True)
        with urllib.request.urlopen('https://dl.google.com/android/repository/' + item['url'], timeout=60) as r, temporary.open('wb') as out:
            shutil.copyfileobj(r, out)
        temporary.replace(target)
    data = target.read_bytes()
    if len(data) != item['size'] or hashlib.new(item['algorithm'], data).hexdigest() != item['checksum']:
        raise ValueError('SDK checksum mismatch: ' + item['package'])
    item['sha256'] = hashlib.sha256(data).hexdigest()
    marker = PREFIX / (item['package'].replace(';', '-') + '.extracted')
    if not marker.exists():
        with zipfile.ZipFile(target) as z:
            for info in z.infolist():
                dest = PREFIX / info.filename
                if not dest.resolve().is_relative_to(PREFIX):
                    raise ValueError('SDK archive path escape')
                z.extract(info, PREFIX)
                if not info.is_dir():
                    mode = (info.external_attr >> 16) & 0o777
                    if mode:
                        dest.chmod(mode)
        marker.write_text(item['sha256'])
    return item

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    record = list(pool.map(materialize, items))
(PREFIX / 'tools.json').write_text(json.dumps(record, indent=2) + '\n')
print('Android platform/build tools verified:', [x.name for x in PREFIX.iterdir() if x.is_dir()], flush=True)
