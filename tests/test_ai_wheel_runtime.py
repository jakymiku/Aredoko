"""Official-artifact boundary fixtures; no real AI code, model or network."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from ai_wheel_runtime import installed_path, verify_wheels, build_environment


class AIWheelRuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.artifacts = self.base / 'artifacts';self.artifacts.mkdir()
        self.root = self.base / 'runtime';self.root.mkdir()
        self.wheel = self.artifacts / 'generated-1-py3-none-any.whl'
        with zipfile.ZipFile(self.wheel, 'w') as archive:
            archive.writestr('generated/__init__.py', b'generated fixture; never executed')
            archive.writestr('generated.data/data/share/doc.txt', b'generated upstream document')
        self.lock = {'entries': [{'name': 'generated', 'filename': self.wheel.name,
                                  'sha256': hashlib.sha256(self.wheel.read_bytes()).hexdigest()}]}
        self.target = self.root / 'Lib/site-packages/generated/__init__.py'
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b'generated fixture; never executed')
        (self.root / 'share').mkdir()
        (self.root / 'share/doc.txt').write_bytes(b'generated upstream document')

    def test_installed_bytes_are_compared_to_verified_wheel(self):
        progress = []
        checked = verify_wheels(self.root, self.artifacts, self.lock, progress=progress.append)
        self.assertGreater(checked, 0)
        self.assertEqual(progress[-1]['bytes_done'], checked)
        self.assertEqual(progress[-1]['bytes_total'], checked)
        self.assertEqual(progress[-1]['files_done'], progress[-1]['files_total'])
        self.target.write_bytes(b'changed fixture')
        with self.assertRaises(ValueError):verify_wheels(self.root, self.artifacts, self.lock)

    def test_replaced_artifact_or_extra_pth_is_refused(self):
        extra = self.root / 'Lib/site-packages/injected.pth'
        extra.write_text('generated fixture')
        with self.assertRaisesRegex(ValueError, 'Unlisted'):
            verify_wheels(self.root, self.artifacts, self.lock)
        extra.unlink()
        cache = self.target.parent / '__pycache__'
        cache.mkdir()
        (cache / 'generated.cpython-313.pyc').write_bytes(b'unverified bytecode fixture')
        with self.assertRaisesRegex(ValueError, 'Unlisted'):
            verify_wheels(self.root, self.artifacts, self.lock)
        (cache / 'generated.cpython-313.pyc').unlink()
        cache.rmdir()
        self.wheel.write_bytes(b'changed wheel')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            verify_wheels(self.root, self.artifacts, self.lock)

    def test_paths_and_unsupported_relocation_are_refused(self):
        self.assertEqual(installed_path('generated.data/purelib/generated/code.py'), 'Lib/site-packages/generated/code.py')
        self.assertEqual(installed_path('generated.data/data/share/doc.txt'), 'share/doc.txt')
        for name in ('../escape.py', '/absolute.py', 'generated.data/unknown/external.py', 'C:/escape.py'):
            with self.subTest(name=name), self.assertRaises(ValueError):installed_path(name)

    def test_bad_artifact_cannot_start_interpreter_or_create_environment(self):
        executable = self.base / 'base-python/python.exe'
        executable.parent.mkdir();executable.write_bytes(b'not executed')
        output = self.base / 'new environment'
        self.wheel.write_bytes(b'changed wheel')
        with patch('ai_wheel_runtime.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):build_environment(executable, self.artifacts, output, self.lock)
        run.assert_not_called()
        self.assertFalse(output.exists())

    def test_base_and_artifacts_cannot_be_used_as_environment_storage(self):
        executable = self.base / 'base-python/python.exe'
        executable.parent.mkdir();executable.write_bytes(b'not executed')
        for output in (executable.parent / 'nested', self.artifacts / 'nested', self.root):
            with self.subTest(output=output), patch('ai_wheel_runtime.subprocess.run') as run:
                with self.assertRaises((ValueError, FileExistsError)):
                    build_environment(executable, self.artifacts, output, self.lock)
                run.assert_not_called()

    def test_cancellation_before_construction_leaves_no_environment(self):
        executable = self.base / 'base-python/python.exe'
        executable.parent.mkdir();executable.write_bytes(b'not executed')
        output = self.base / 'cancelled environment'
        with patch('ai_wheel_runtime.subprocess.run') as run:
            with self.assertRaises(InterruptedError):
                build_environment(executable, self.artifacts, output, self.lock, cancelled=lambda: True)
        run.assert_not_called();self.assertFalse(output.exists())


if __name__ == '__main__':unittest.main()
