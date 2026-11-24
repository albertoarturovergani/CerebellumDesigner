"""Build the Windows launcher ZIP around the immutable verified Ubuntu source kit."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'windows'
DOWNLOADS = ROOT / 'downloads'
PAYLOAD = DOWNLOADS / 'CerebellumDesigner_Ubuntu_20261123.tar.gz'
EXPECTED = 'd98bff221871c5e18678ebaf5dfdacc866c06ee444f076a7476968d791704b17'
assert hashlib.sha256(PAYLOAD.read_bytes()).hexdigest() == EXPECTED
DEST = DOWNLOADS / 'CerebellumDesigner_Windows_WSL2_20261124.zip'
files = {}
for p in sorted(SOURCE.rglob('*')):
    if not p.is_file() or '__pycache__' in p.parts:
        continue
    relative = p.relative_to(SOURCE).as_posix()
    content = p.read_bytes()
    if p.suffix in ('.cmd', '.ps1', '.txt'):
        content = content.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
    elif p.suffix in ('.sh', '.py'):
        content = content.replace(b'\r\n', b'\n')
    files[relative] = content
files['payload/' + PAYLOAD.name] = PAYLOAD.read_bytes()
manifest = {
    'name': 'Cerebellum Designer for Windows with WSL2',
    'app_version': '0.0.1',
    'launcher_date': '2026-11-24',
    'source_archive_sha256': EXPECTED,
    'files': {name: hashlib.sha256(value).hexdigest() for name, value in files.items()},
    'validation_scope': 'Launcher contracts and Linux backend; full Windows/WSL2 installation not verified.',
}
files['windows_manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
with zipfile.ZipFile(DEST, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for name, content in files.items():
        info = zipfile.ZipInfo('CerebellumDesigner_Windows/' + name, (2026, 11, 24, 12, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, content)
with zipfile.ZipFile(DEST) as archive:
    assert archive.testzip() is None
    for name, expected in manifest['files'].items():
        assert hashlib.sha256(archive.read('CerebellumDesigner_Windows/' + name)).hexdigest() == expected
lines = []
for p in sorted(DOWNLOADS.iterdir()):
    if p.suffix == '.zip' or p.name.endswith('.tar.gz'):
        lines.append(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name)
(DOWNLOADS / 'SHA256SUMS').write_text('\n'.join(lines) + '\n')
print(json.dumps({'file': str(DEST), 'bytes': DEST.stat().st_size, 'sha256': hashlib.sha256(DEST.read_bytes()).hexdigest(), 'entries': len(files)}, indent=2))
