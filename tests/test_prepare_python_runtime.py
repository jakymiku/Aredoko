"""Generated layout fixtures only; no fake binary is executed by these tests."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from prepare_python_runtime import prepare


class PreparePythonRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aredoko-runtime-prepare-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / 'base CPython'
        self.site = self.root / 'venv/Lib/site-packages'
        self.output = self.root / 'prepared runtime 日本語'
        self.files = {
            'python.exe': b'fixture, never executed', 'pythonw.exe': b'fixture, never executed',
            'python3.dll': b'fixture', 'python311.dll': b'fixture', 'vcruntime140.dll': b'fixture',
            'LICENSE.txt': b'CPython license fixture', 'Lib/encodings/__init__.py': b'# fixture',
            'Lib/sqlite3/__init__.py': b'# fixture', 'Lib/__pycache__/skip.pyc': b'cache',
            'Lib/site-packages/unrelated.txt': b'never copied', 'DLLs/_sqlite3.pyd': b'fixture',
            'models/never.bin': b'never copied',
        }
        for name, data in self.files.items():
            path = self.base / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        for name, data in {
            'PIL/__init__.py': b'# fixture', 'pillow-1.dist-info/WHEEL': b'Tag: cp311-cp311-win_amd64\n',
            'pillow-1.dist-info/licenses/LICENSE': b'Pillow license fixture',
            'unrelated/__init__.py': b'# not selected by default',
            'unrelated/sourceless.pyc': b'bytecode-only dependency fixture',
        }.items():
            path = self.site / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def snapshot(self):
        return {str(p.relative_to(self.root)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                for source in (self.base, self.site) for p in source.rglob('*') if p.is_file()}

    def test_check_is_read_only_and_never_creates_output_parent(self):
        before = self.snapshot()
        target = self.root / 'absent parent/new runtime'
        result = prepare(self.base, self.site, target, check=True)
        self.assertTrue(result['pass'])
        self.assertFalse(result['prepared'])
        self.assertFalse(target.parent.exists())
        self.assertEqual(self.snapshot(), before)

    def test_prepares_isolated_layout_preserves_licenses_and_sources(self):
        before = self.snapshot()
        result = prepare(self.base, self.site, self.output)
        self.assertTrue(result['prepared'])
        self.assertFalse(result['runtime_imports_verified'])
        self.assertEqual(self.snapshot(), before)
        with zipfile.ZipFile(self.output / 'python311.zip') as archive:
            self.assertIn('encodings/__init__.py', archive.namelist())
            self.assertIn('sqlite3/__init__.py', archive.namelist())
            self.assertFalse(any('site-packages' in n or '__pycache__' in n for n in archive.namelist()))
        self.assertTrue((self.output / 'DLLs/_sqlite3.pyd').is_file())
        self.assertTrue((self.output / 'Lib/site-packages/pillow-1.dist-info/licenses/LICENSE').is_file())
        self.assertFalse((self.output / 'models').exists())
        self.assertFalse((self.output / 'Lib/site-packages/unrelated').exists())
        self.assertIn('DLLs\n', (self.output / 'python311._pth').read_text())

    def test_existing_directory_and_nested_destination_are_preserved(self):
        self.output.mkdir()
        marker = self.output / 'keep'
        marker.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):
            prepare(self.base, self.site, self.output)
        self.assertEqual(marker.read_bytes(), b'keep')
        with self.assertRaises(ValueError):
            prepare(self.base, self.site, self.base / 'new runtime')
        self.assertFalse((self.base / 'new runtime').exists())

    def test_venv_or_wrong_pillow_abi_is_rejected_before_writes(self):
        config = self.base / 'pyvenv.cfg'
        config.write_text('fixture')
        with self.assertRaisesRegex(ValueError, 'base CPython'):
            prepare(self.base, self.site, self.output)
        config.unlink()
        (self.site / 'pillow-1.dist-info/WHEEL').write_text('Tag: cp314-cp314-win_amd64\n')
        with self.assertRaisesRegex(ValueError, 'ABI'):
            prepare(self.base, self.site, self.output)
        self.assertFalse(self.output.exists())

    def test_ai_mode_requires_all_packages_and_rejects_editable_paths(self):
        with self.assertRaises(ValueError):
            prepare(self.base, self.site, self.output, include_ai=True)
        self.assertFalse(self.output.exists())
        for name in ('torch', 'transformers', 'sentence_transformers', 'numpy', 'onnxruntime'):
            package = self.site / name
            package.mkdir()
            (package / '__init__.py').write_text('# fixture')
        editable = self.site / '__editable__local.pth'
        editable.write_text('C:/not-a-runtime')
        with self.assertRaisesRegex(ValueError, 'Editable'):
            prepare(self.base, self.site, self.output, include_ai=True)
        self.assertFalse(self.output.exists())
        editable.unlink()
        prepare(self.base, self.site, self.output, include_ai=True)
        self.assertTrue((self.output / 'Lib/site-packages/torch/__init__.py').exists())
        self.assertTrue((self.output / 'Lib/site-packages/unrelated/sourceless.pyc').exists())


if __name__ == '__main__':
    unittest.main()
