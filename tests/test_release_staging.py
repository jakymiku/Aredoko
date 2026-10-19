"""Generated-only release staging and real Windows native argv regressions."""
import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'app'))
import package_release as release
from production import ProductionCatalog
from storage_lease import StoragePathError


class ReleaseStagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aredoko-stage-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / 'source with spaces'
        self.binary = self.repo / 'src/Aredoko.WinUI/bin/x64/Release/net10.0-windows10.0.26100.0/win-x64'
        self.binary.mkdir(parents=True)
        for name in release.PAYLOAD:
            (self.binary / name).write_bytes(('fixture:' + name).encode())
        (self.binary / 'symbols.pdb').write_bytes(b'not distributed')
        (self.binary / 'AppX').mkdir()
        (self.binary / 'AppX/old.exe').write_bytes(b'stale development layout')
        (self.repo / 'app').mkdir()
        for source in (ROOT / 'app').iterdir():
            if source.is_file() and source.suffix in ('.py', '.json'):
                shutil.copy2(source, self.repo / 'app' / source.name)
        for name in ('THIRD_PARTY_NOTICES.md', 'docs/user-guide.md',
                     'tools/start-aredoko.ps1', 'tools/native-arguments.ps1', 'tools/backup_library.py'):
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        for source in (ROOT / 'docs').glob('*.md'):
            shutil.copy2(source, self.repo / 'docs' / source.name)
        profile = self.repo / 'config/ai-profiles/fixture.json'
        profile.parent.mkdir(parents=True)
        profile.write_text('{"fixture":true}', encoding='utf-8')
        # A release must never discover or ship these files.
        for name in ('data/catalog.sqlite', 'models/private.bin', '.venv-ai/private.py'):
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'private fixture')
        self.output = self.base / 'release with spaces'
        self.addCleanup(patch.stopall)
        patch.object(release, 'REPO', self.repo).start()

    def test_existing_directory_untouched_and_build_never_started(self):
        self.output.mkdir()
        sentinel = self.output / 'keep.txt'
        sentinel.write_bytes(b'keep me')
        before = sentinel.stat().st_mtime_ns
        with patch.object(release.subprocess, 'run') as build:
            with self.assertRaises(FileExistsError):
                release.package(self.output)
        build.assert_not_called()
        self.assertEqual(sentinel.read_bytes(), b'keep me')
        self.assertEqual(sentinel.stat().st_mtime_ns, before)

    def test_existing_empty_directory_and_file_refused(self):
        self.output.mkdir()
        with self.assertRaises(FileExistsError):
            release.package(self.output, skip_build=True)
        existing_file = self.base / 'keep.bin'
        existing_file.write_bytes(b'keep')
        with self.assertRaises((FileExistsError, StoragePathError)):
            release.package(existing_file, skip_build=True)
        self.assertEqual(existing_file.read_bytes(), b'keep')

    def test_check_never_creates_parents_or_builds(self):
        target = self.base / 'missing parent' / 'new stage'
        with patch.object(release.subprocess, 'run') as build:
            result = release.package(target, dry_run=True)
        build.assert_not_called()
        self.assertTrue(result['pass'])
        self.assertFalse(target.parent.exists())

    def test_check_detects_missing_build_without_writing(self):
        (self.binary / release.PAYLOAD[0]).unlink()
        with self.assertRaises(StoragePathError):
            release.package(self.output, skip_build=True, dry_run=True)
        self.assertFalse(self.output.exists())

    def test_manifest_profiles_tools_and_no_private_data(self):
        result = release.package(self.output, skip_build=True)
        self.assertEqual(result['readiness'], 'staging-only')
        self.assertFalse(result['python_bundled'])
        self.assertFalse(result['ai_runtime_bundled'])
        self.assertFalse(result['clean_machine_activation_verified'])
        entries = {row['path']: row for row in result['entries']}
        self.assertIn('backend/config/ai-profiles/fixture.json', entries)
        self.assertIn('native-arguments.ps1', entries)
        self.assertIn('tools/backup_library.py', entries)
        for name in ('user-guide.md', 'model-profiles.md', 'wd-tagger.md', 'backup-recovery.md'):
            self.assertIn('docs/' + name, entries)
        self.assertNotIn('bin/symbols.pdb', entries)
        self.assertFalse(any(p.startswith('bin/AppX/') for p in entries))
        self.assertFalse(any('private' in p or p.endswith('.sqlite') for p in entries))
        self.assertEqual(result['files_count'], len(entries))
        self.assertEqual(result['total_bytes'], sum(e['bytes'] for e in entries.values()))
        for name, entry in entries.items():
            data = (self.output / name).read_bytes()
            self.assertEqual(entry['bytes'], len(data))
            self.assertEqual(entry['sha256'], hashlib.sha256(data).hexdigest())
        checksums = (self.output / 'sha256sums.txt').read_text(encoding='utf-8')
        self.assertEqual(len(checksums.splitlines()), len(entries))
        self.assertEqual(json.loads((self.output / 'manifest.json').read_text(encoding='utf-8')), result)

    def test_failed_copy_does_not_publish_completion_marker(self):
        with patch.object(release, 'copy_payload', side_effect=OSError('fixture copy failure')):
            with self.assertRaises(OSError):
                release.package(self.output, skip_build=True)
        self.assertTrue(self.output.is_dir())
        self.assertFalse((self.output / 'manifest.json').exists())
        self.assertTrue((self.binary / release.PAYLOAD[0]).is_file())
        with self.assertRaises(FileExistsError):
            release.package(self.output, skip_build=True)

    def test_reparse_ancestor_is_refused_before_mutation(self):
        original = release.plain_path
        def refuse(path, **kwargs):
            if Path(path) == self.base:
                raise StoragePathError('Linked storage paths are not supported')
            return original(path, **kwargs)
        with patch.object(release, 'plain_path', side_effect=refuse):
            with self.assertRaises(StoragePathError):
                release.package(self.output, skip_build=True)
        self.assertFalse(self.output.exists())

    def test_actual_packaged_backup_cli_roundtrip(self):
        release.package(self.output, skip_build=True)
        catalog_path = self.base / 'generated catalog.sqlite'
        catalog = ProductionCatalog(catalog_path)
        catalog.close()
        script = self.output / 'tools/backup_library.py'
        bundle, restored = self.base / 'bundle', self.base / 'restored'
        for args in (['--help'], ['backup', '--catalog', str(catalog_path), '--output', str(bundle)],
                     ['restore', '--bundle', str(bundle), '--output', str(restored)]):
            result = subprocess.run([sys.executable, str(script), *args], cwd=self.output,
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        import sqlite3
        with closing(sqlite3.connect(restored / 'catalog.sqlite')) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')


@unittest.skipUnless(os.name == 'nt', 'Windows PowerShell native process regression')
class NativeArgumentTests(unittest.TestCase):
    def test_real_powershell_start_process_preserves_arguments(self):
        with tempfile.TemporaryDirectory(prefix='aredoko-argv-') as folder:
            base = Path(folder)
            recorder = base / '記録 with spaces.py'
            recorder.write_text('import json,sys\nfrom pathlib import Path\n'
                'Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:],ensure_ascii=False),encoding="utf-8")\n', encoding='utf-8')
            expected = ['', 'ordinary', '空白 を含む', "single'quote", '$value`&literal', 'C:\\',
                        'C:\\folder with spaces\\', '\\', '--viewer-settings']
            values = base / 'values.json'
            values.write_text(json.dumps(expected, ensure_ascii=False), encoding='utf-8')
            output = base / 'captured.json'
            wrapper = base / 'wrapper.ps1'
            wrapper.write_text('''param($Helper,$Python,$Recorder,$Output,$Values)
$ErrorActionPreference='Stop'
. $Helper
$items = Get-Content -LiteralPath $Values -Raw -Encoding UTF8 | ConvertFrom-Json
$line = Join-AredokoNativeArguments -Values (@($Recorder,$Output) + $items)
$child = Start-Process -FilePath $Python -ArgumentList $line -WindowStyle Hidden -PassThru -Wait
if ($child.ExitCode -ne 0) { throw 'Recorder failed' }
''', encoding='utf-8-sig')
            result = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                '-File', str(wrapper), str(ROOT / 'tools/native-arguments.ps1'), sys.executable,
                str(recorder), str(output), str(values)], capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(output.read_text(encoding='utf-8')), expected)

    def test_invalid_argument_rejected_before_process_launch(self):
        helper = str(ROOT / 'tools/native-arguments.ps1').replace("'", "''")
        command = ". '" + helper + "'; $ErrorActionPreference='Stop'; " + '''
foreach ($bad in @('has"quote', ('line'+[char]10+'break'), ('zero'+[char]0))) {
  $refused=$false
  try { Join-AredokoNativeArguments -Values @('safe',$bad) | Out-Null } catch { $refused=$true }
  if (-not $refused) { throw 'Invalid argument was accepted' }
}
'''
        result = subprocess.run(['powershell', '-NoProfile', '-Command', command],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
