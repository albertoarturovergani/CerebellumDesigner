"""Build on Windows, not through WSL or cross compilation."""
from pathlib import Path
import hashlib
import json
import platform
import importlib.metadata
import shutil
import subprocess
import sys
import zipfile
from prepare_resources import prepare
ROOT = Path(__file__).resolve().parent

def main():
    if sys.platform != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise SystemExit('Build requires native Windows x64 and Python 3.12')
    prepare()
    source = ROOT / 'DeformationAlgorithm'
    for cache in source.rglob('__pycache__'):
        shutil.rmtree(cache)
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed',
           '--name', 'CerebellumDesigner', '--distpath', str(ROOT/'dist'), '--workpath', str(ROOT/'build'),
           '--specpath', str(ROOT), '--paths', str(source), '--paths', str(ROOT),
           '--hidden-import', 'native_checks', '--collect-all', 'reportlab',
           '--exclude-module', 'bsb', '--exclude-module', 'mpi4py', '--exclude-module', 'nest',
           '--add-data', f'{source};DeformationAlgorithm',
           '--add-data', f'{source/"cereb_remorph"};cereb_remorph',
           '--add-data', f'{ROOT/"resources"};resources', str(ROOT/'desktop.py')]
    subprocess.run(cmd, check=True)
    folder = ROOT/'dist/CerebellumDesigner'
    shutil.copy2(ROOT/'README_IT.txt', folder/'LEGGIMI.txt')
    shutil.copy2(ROOT/'THIRD_PARTY.txt', folder/'THIRD_PARTY.txt')
    notices=folder/'_internal/third_party_licenses'
    notices.mkdir(parents=True,exist_ok=True)
    for dist in importlib.metadata.distributions():
        name=dist.metadata['Name']
        for item in dist.files or []:
            if any(token in item.name.lower() for token in ('license','copying','notice')):
                original=dist.locate_file(item)
                if original.is_file():
                    target=notices/name/Path(str(item))
                    if '..' in target.parts:continue
                    target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(original,target)
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.is_file():shutil.copy2(python_license,notices/'Python-LICENSE.txt')
    manifest = {'format':'CerebellumDesigner native Windows x64', 'editor_version':'0.0.1',
                'ubuntu_required':False, 'python_install_required':False,
                'files':{p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(folder.rglob('*')) if p.is_file()}}
    (folder/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(folder/'CerebellumDesigner.exe')

if __name__ == '__main__':
    main()
