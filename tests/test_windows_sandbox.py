"""Generated-only manual Sandbox configuration and paired-release contracts."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import prepare_windows_sandbox as tool


class WindowsSandboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aredoko-sandbox-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo & generated'
        self.release = self.root / 'dist/basic & fixture/Aredoko'
        self.release.mkdir(parents=True)
        self.kit = self.root / 'dist/kit & fixture'
        self.kit.mkdir()
        self.output = self.root / 'data/ai-ui/new & session'
        self.manifest = {'frontend_activation': 'portable', 'ai_runtime_bundled': False, 'models_bundled': False}
        (self.release / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')
        self.archive = self.release.parent / 'Aredoko-windows-x64.zip'
        self.archive.write_bytes(b'generated archive fixture')
        self.candidate = {'manifest_sha256': tool.digest(self.release / 'manifest.json'), 'zip_sha256': tool.digest(self.archive)}
        self.write_candidate()
        self.repo_patch = patch.object(tool, 'REPO', self.root)
        self.repo_patch.start()
        self.addCleanup(self.repo_patch.stop)
        self.verifier_patch = patch.object(tool, 'verify_release', return_value=self.manifest)
        self.verifier = self.verifier_patch.start()
        self.addCleanup(self.verifier_patch.stop)

    def write_candidate(self):
        (self.kit / 'candidate.json').write_text(json.dumps(self.candidate), encoding='utf-8')

    def test_exact_mappings_disabled_sharing_and_xml_escaping(self):
        target = tool.prepare(self.release, self.kit, self.output)
        self.verifier.assert_called_once_with(self.release)
        xml = target.read_text(encoding='utf-8')
        self.assertIn('&amp;', xml)
        config = ET.fromstring(xml)
        for option in ('vGPU', 'Networking', 'ClipboardRedirection', 'AudioInput', 'VideoInput', 'PrinterRedirection'):
            self.assertEqual(config.findtext(option), 'Disable')
        mappings = [{node.tag: node.text for node in row} for row in config.findall('MappedFolders/MappedFolder')]
        self.assertEqual(mappings, [
            {'HostFolder': str(self.release), 'SandboxFolder': r'C:\Aredoko', 'ReadOnly': 'true'},
            {'HostFolder': str(self.kit), 'SandboxFolder': r'C:\AredokoValidation', 'ReadOnly': 'true'},
            {'HostFolder': str(self.output / 'evidence'), 'SandboxFolder': r'C:\AredokoEvidence', 'ReadOnly': 'false'}])
        self.assertEqual(config.findtext('LogonCommand/Command'), r'explorer.exe C:\Aredoko')
        self.assertEqual({path.name for path in self.output.iterdir()}, {'Aredoko.wsb', 'README.txt', 'evidence'})
        self.assertEqual(list((self.output / 'evidence').iterdir()), [])
        readme = (self.output / 'README.txt').read_text(encoding='utf-8-sig')
        for text in ('3010', 'Aredoko.exe', 'result-template.json', '閉じる前', '合格を意味しません'):
            self.assertIn(text, readme)

    def test_pair_mismatch_rejected_before_output_or_parent_creation(self):
        for field in ('manifest_sha256', 'zip_sha256'):
            original = self.candidate[field]
            with self.subTest(field=field):
                self.candidate[field] = '0' * 64
                self.write_candidate()
                with self.assertRaisesRegex(ValueError, 'does not match'):
                    tool.prepare(self.release, self.kit, self.output)
                self.assertFalse(self.output.parent.exists())
            self.candidate[field] = original

    def test_optional_archive_digest_absent_keeps_legacy_pair_usable(self):
        self.candidate.pop('zip_sha256')
        self.write_candidate()
        self.archive.unlink()
        self.assertTrue(tool.prepare(self.release, self.kit, self.output).is_file())

    def test_existing_output_preserved(self):
        self.output.mkdir(parents=True)
        sentinel = self.output / 'keep.txt'
        sentinel.write_bytes(b'keep existing evidence')
        with self.assertRaises(FileExistsError):
            tool.prepare(self.release, self.kit, self.output)
        self.verifier.assert_not_called()
        self.assertEqual(sentinel.read_bytes(), b'keep existing evidence')
        self.assertEqual(list(self.output.iterdir()), [sentinel])

    def test_input_overlap_rejected_before_verification_or_writes(self):
        inputs = self.root / 'data/ai-ui/inputs'
        release = inputs / 'release'
        kit = inputs / 'kit'
        release.mkdir(parents=True)
        kit.mkdir()
        for output in (release / 'new', kit / 'new', inputs):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, 'overlap'):
                tool.prepare(release, kit, output)
        self.verifier.assert_not_called()
        self.assertEqual(list(release.iterdir()), [])
        self.assertEqual(list(kit.iterdir()), [])

    def test_output_outside_ignored_root_rejected(self):
        outside = self.root / 'outside/new'
        with self.assertRaisesRegex(ValueError, 'data/ai-ui'):
            tool.prepare(self.release, self.kit, outside)
        self.verifier.assert_not_called()
        self.assertFalse(outside.parent.exists())

    def test_non_basic_release_rejected_before_output(self):
        self.manifest['ai_runtime_bundled'] = True
        with self.assertRaisesRegex(ValueError, 'basic release'):
            tool.prepare(self.release, self.kit, self.output)
        self.assertFalse(self.output.parent.exists())


if __name__ == '__main__':
    unittest.main()
