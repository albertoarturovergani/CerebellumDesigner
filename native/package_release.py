from pathlib import Path
import hashlib
import shutil
import zipfile
ROOT=Path(__file__).resolve().parent
folder=ROOT/'dist/CerebellumDesigner'
validation=ROOT/'test-output/frozen space é/validation.json'
assert validation.is_file()
shutil.copy2(validation, ROOT/'dist/validation_windows.json')
output=ROOT/'dist/CerebellumDesigner_Windows_x64.zip'
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(folder.rglob('*')):
        if p.is_file():z.write(p,arcname=(Path('CerebellumDesigner')/p.relative_to(folder)).as_posix())
checksum=hashlib.sha256(output.read_bytes()).hexdigest()
(ROOT/'dist/SHA256SUMS.txt').write_text(checksum+'  '+output.name+'\n',encoding='utf-8')
print(output.name,output.stat().st_size,checksum)
