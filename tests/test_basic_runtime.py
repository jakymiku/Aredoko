"""Generated-only verification boundaries; no network or runtime execution."""
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import prepare_basic_runtime as runtime


class BasicRuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.python = base / 'base'
        self.output = base / 'venv'
        (self.python / 'Lib/venv/scripts/nt').mkdir(parents=True)
        (self.output / 'Scripts').mkdir(parents=True)
        self.site = self.output / 'Lib/site-packages'
        self.site.mkdir(parents=True)
        for name in ('activate', 'activate.bat', 'activate.fish', 'Activate.ps1', 'deactivate.bat'):
            (self.output / 'Scripts' / name).write_text('generated shell fixture')
        for installed, original in (('python.exe', 'venvlauncher.exe'), ('pythonw.exe', 'venvwlauncher.exe')):
            (self.python / 'Lib/venv/scripts/nt' / original).write_bytes(b'generated PE fixture')
            (self.output / 'Scripts' / installed).write_bytes(b'generated PE fixture')
        self.configuration = (f'home = {self.python}\ninclude-system-site-packages = false\nversion = 3.13.17\n'
                              f'executable = {self.python / "python.exe"}\ncommand = generated fixture\n')
        (self.output / 'pyvenv.cfg').write_text(self.configuration)
        self.payload = io.BytesIO()
        with zipfile.ZipFile(self.payload, 'w') as archive:
            archive.writestr('PIL/__init__.py', b'generated Pillow fixture')
        (self.site / 'PIL').mkdir()
        (self.site / 'PIL/__init__.py').write_bytes(b'generated Pillow fixture')
        self.addCleanup(patch.stopall)
        patch.object(runtime.sys, 'base_prefix', str(self.python)).start()
        patch.object(runtime.sys, 'executable', str(self.python / 'python.exe')).start()

    def verify(self):
        with zipfile.ZipFile(self.payload) as archive:
            runtime.verify_environment(archive, self.output)

    def test_verified_bytes_and_base_are_accepted(self):
        self.verify()

    def test_changed_pillow_is_refused(self):
        (self.site / 'PIL/__init__.py').write_bytes(b'changed fixture')
        with self.assertRaisesRegex(ValueError, 'Pillow file changed'):
            self.verify()

    def test_extra_pth_and_script_are_refused(self):
        extra = self.site / 'injected.pth'
        extra.write_text('import generated_fixture')
        with self.assertRaisesRegex(ValueError, 'Unlisted'):
            self.verify()
        extra.unlink()
        (self.output / 'Scripts/injected.dll').write_bytes(b'generated fixture')
        with self.assertRaisesRegex(ValueError, 'Unlisted'):
            self.verify()

    def test_changed_launcher_is_refused(self):
        (self.output / 'Scripts/python.exe').write_bytes(b'changed fixture')
        with self.assertRaisesRegex(ValueError, 'launcher changed'):
            self.verify()

    def test_system_site_or_duplicate_configuration_is_refused(self):
        for text in (self.configuration.replace('= false', '= true'), self.configuration + 'home = other\n'):
            with self.subTest(text=text):
                (self.output / 'pyvenv.cfg').write_text(text)
                with self.assertRaises(ValueError):
                    self.verify()


if __name__ == '__main__':
    unittest.main()
