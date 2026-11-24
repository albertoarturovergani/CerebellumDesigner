"""Extract only pinned model sources from the already published, verified kit."""
from pathlib import Path, PurePosixPath
import hashlib
import tarfile
ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT.parent / 'downloads/CerebellumDesigner_Ubuntu_20261123.tar.gz'
EXPECTED = 'd98bff221871c5e18678ebaf5dfdacc866c06ee444f076a7476968d791704b17'

def prepare():
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == EXPECTED, 'Source archive checksum mismatch'
    dest = ROOT / 'resources/src/cerebellar-models'
    prefix = 'CerebellumDesigner_Ubuntu/src/cerebellar-models/'
    count = 0
    with tarfile.open(ARCHIVE) as archive:
        for item in archive:
            if not item.name.startswith(prefix) or not item.isfile():
                continue
            relative = PurePosixPath(item.name[len(prefix):])
            if '..' in relative.parts or relative.is_absolute():
                raise ValueError('Invalid archive member')
            if any(part in ('.git', '__pycache__') for part in relative.parts):
                continue
            target = dest.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(item).read())
            count += 1
    assert (dest / 'LICENSE').is_file()
    assert (dest / 'morphologies/morphologies.yaml').is_file()
    print(f'Prepared {count} pinned model files')
    return dest

if __name__ == '__main__':
    prepare()
