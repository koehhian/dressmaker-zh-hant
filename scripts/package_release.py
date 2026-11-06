"""Package the verified installer and public documentation. No game files needed."""
from pathlib import Path
import csv
import hashlib
import json
import re
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist/release'
config = json.loads((ROOT / 'release.json').read_text(encoding='utf-8'))
tag = config['tag']
if not re.fullmatch(r'v\d{4}\.\d{2}\.\d{2}(?:\.\d+)?', tag):
    raise SystemExit('Invalid release tag')
installer = ROOT / config['installer']
if hashlib.sha256(installer.read_bytes()).hexdigest() != config['installer_sha256']:
    raise SystemExit('Installer hash does not match the validated release manifest')
rows = list(csv.DictReader((ROOT / 'localization/zh-Hant/translations.csv').open(encoding='utf-8-sig')))
assert len(rows) == 5398 and len({(r['table'], r['id']) for r in rows}) == 5398
assert len({r['table'] for r in rows}) == 4
for name in ['README.md', 'docs/USER_GUIDE.md', 'docs/VALIDATION.md', 'RELEASE_NOTES.md']:
    assert config['tested_steam_build'] in (ROOT / name).read_text(encoding='utf-8'), name

OUT.mkdir(parents=True, exist_ok=True)
shutil.copy2(installer, OUT / 'DressmakerZHant.exe')
files = ['README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'RELEASE_NOTES.md',
         'docs/USER_GUIDE.md', 'docs/VALIDATION.md', 'docs/DEPENDENCIES.json',
         'docs/DEPENDENCY_LICENSES.txt', 'docs/screenshots/main-menu.png',
         'docs/screenshots/installer.png']
# Zip members have fixed timestamps, so identical inputs produce identical archives.
def add(z, name, data):
    info = zipfile.ZipInfo(name, date_time=(2026, 11, 6, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    z.writestr(info, data)

windows = OUT / f'dressmaker-zh-hant-{tag}-windows.zip'
with zipfile.ZipFile(windows, 'w') as z:
    add(z, 'DressmakerZHant.exe', installer.read_bytes())
    for name in files:
        add(z, name, (ROOT / name).read_bytes())
    add(z, 'SHA256SUMS.txt', (config['installer_sha256'] + '  DressmakerZHant.exe\n').encode())

source = OUT / f'dressmaker-zh-hant-{tag}-source.zip'
tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
with zipfile.ZipFile(source, 'w') as z:
    for name in sorted(n for n in tracked if n):
        if name.startswith('distribution/') or name.lower().endswith(('.exe', '.zip', '.pyc')):
            continue
        add(z, name, (ROOT / name).read_bytes())

assets = [OUT / 'DressmakerZHant.exe', windows, source]
(OUT / 'SHA256SUMS.txt').write_text(''.join(
    f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n'
    for path in assets), encoding='utf-8', newline='\n')
print('Validated 5398 unique strings, 4 tables, tested Steam build and installer hash.')
for path in assets + [OUT / 'SHA256SUMS.txt']:
    print(path.name, path.stat().st_size)
