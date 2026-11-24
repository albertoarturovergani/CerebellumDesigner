"""Exercise extraction and non-overwrite rules on Linux, without installing dependencies."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

WINDOWS = pathlib.Path(__file__).resolve().parents[1]
ARCHIVE = WINDOWS.parent / 'downloads/CerebellumDesigner_Ubuntu_20261123.tar.gz'
if not ARCHIVE.exists():
    ARCHIVE = WINDOWS / 'payload/CerebellumDesigner_Ubuntu_20261123.tar.gz'


class PayloadTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cd payload O'Neil ")
        self.root = pathlib.Path(self.temp.name)
        self.helper_dir = self.root / 'Windows launcher'
        self.helper_dir.mkdir()
        self.helper = self.helper_dir / 'wsl-helper.sh'
        shutil.copy2(WINDOWS / 'wsl-helper.sh', self.helper)
        (self.helper_dir / 'payload').mkdir()
        self.archive = self.helper_dir / 'payload' / ARCHIVE.name
        shutil.copy2(ARCHIVE, self.archive)
        self.target = self.root / 'Linux installation with spaces'

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self):
        return subprocess.run([
            'bash', '-c', 'source "$1"; cd_install_root="$2"; '
            'cd_source_marker="$2/.windows-source-sha256"; prepare_source',
            'payload-test', str(self.helper), str(self.target),
        ], text=True, capture_output=True)

    def test_extract_and_preserve_exports(self):
        first = self.prepare()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertTrue((self.target / 'DeformationAlgorithm/cereb_remorph/designer.py').is_file())
        result = self.target / 'DeformationAlgorithm/exports/scientific-result.txt'
        result.write_text('keep this result')
        second = self.prepare()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(result.read_text(), 'keep this result')

    def test_refuse_unrelated_folder(self):
        self.target.mkdir()
        result = self.target / 'important.txt'
        result.write_text('preserve')
        run = self.prepare()
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('Nothing overwritten', run.stderr)
        self.assertEqual(result.read_text(), 'preserve')

    def test_refuse_symlink(self):
        elsewhere = self.root / 'other-data'
        elsewhere.mkdir()
        self.target.symlink_to(elsewhere, target_is_directory=True)
        self.assertNotEqual(self.prepare().returncode, 0)
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_reject_corrupt_archive(self):
        self.archive.write_bytes(b'tampered')
        run = self.prepare()
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('checksum mismatch', run.stderr)
        self.assertFalse(self.target.exists())

    def test_reject_changed_source(self):
        self.assertEqual(self.prepare().returncode, 0)
        source = self.target / 'DeformationAlgorithm/cereb_remorph/designer.py'
        source.write_text('changed locally')
        self.assertNotEqual(self.prepare().returncode, 0)
        self.assertEqual(source.read_text(), 'changed locally')


if __name__ == '__main__':
    unittest.main(verbosity=2)
