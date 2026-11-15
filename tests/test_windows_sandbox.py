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
import sandbox_trial as trial


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

    def test_managed_download_enables_only_guest_networking_for_matching_release(self):
        with self.assertRaisesRegex(ValueError, 'managed Python release'):
            tool.prepare(self.release, self.kit, self.output, managed_python_download=True)
        self.assertFalse(self.output.parent.exists())

        self.manifest.update(managed_python=tool.MANAGED_PYTHON, python_bundled=False)
        target = tool.prepare(self.release, self.kit, self.output, managed_python_download=True)
        config = ET.parse(target).getroot()
        self.assertEqual(config.findtext('Networking'), 'Enable')
        for option in ('vGPU', 'ClipboardRedirection', 'AudioInput', 'VideoInput', 'PrinterRedirection'):
            self.assertEqual(config.findtext(option), 'Disable')
        self.assertEqual(config.findtext('LogonCommand/Command'), r'explorer.exe C:\Aredoko')
        self.assertEqual([row.findtext('ReadOnly') for row in config.findall('MappedFolders/MappedFolder')],
                         ['true', 'true', 'false'])
        readme = (self.output / 'README.txt').read_text(encoding='utf-8-sig')
        self.assertIn('CPythonとPillow', readme)
        self.assertIn('生成素材3件', readme)

    def test_safe_sandbox_runner_refuses_when_existing_sandbox_active(self):
        wsb = self.root / 'data/ai-ui/trial/Trial.wsb'
        wsb.parent.mkdir(parents=True)
        wsb.write_text('<Configuration />', encoding='utf-8')
        evidence = wsb.parent / 'evidence'
        evidence.mkdir()
        prior_result = evidence / 'result.json'
        prior_failure = evidence / 'failure.json'
        prior_result.write_text('{"pass": true}', encoding='utf-8')
        prior_failure.write_text('{"error": "old"}', encoding='utf-8')
        killed = []
        launched = []
        with self.assertRaises(trial.ExistingSandboxError):
            trial.run_wsb_trial(
                wsb,
                evidence,
                list_processes=lambda: [{'pid': 4242, 'name': 'WindowsSandbox.exe', 'parent_pid': 1, 'cmdline': r'C:\other\User.wsb'}],
                popen=lambda *a, **kw: launched.append(a),
                stop_pids=lambda pids: killed.extend(pids),
            )
        self.assertEqual(launched, [])
        self.assertEqual(killed, [])
        self.assertTrue(prior_result.exists())
        self.assertTrue(prior_failure.exists())
        self.assertFalse((evidence / 'runs').exists())

    def test_safe_sandbox_runner_aborts_when_process_probe_fails(self):
        from types import SimpleNamespace

        with patch('sandbox_trial.subprocess.run', return_value=SimpleNamespace(returncode=1, stdout='', stderr='CIM denied')):
            with self.assertRaises(trial.SandboxProbeError):
                trial.list_sandbox_processes()
        with patch('sandbox_trial.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='', stderr='')):
            with self.assertRaises(trial.SandboxProbeError):
                trial.list_sandbox_processes()

        wsb = self.root / 'data/ai-ui/trial/Trial.wsb'
        wsb.parent.mkdir(parents=True)
        wsb.write_text('<Configuration />', encoding='utf-8')
        evidence = wsb.parent / 'evidence'
        evidence.mkdir()
        prior_result = evidence / 'result.json'
        prior_result.write_text('{"pass": true}', encoding='utf-8')
        launched = []
        with self.assertRaises(trial.SandboxProbeError):
            trial.run_wsb_trial(
                wsb,
                evidence,
                list_processes=lambda: (_ for _ in ()).throw(trial.SandboxProbeError('CIM denied')),
                popen=lambda *a, **kw: launched.append(a),
            )
        self.assertEqual(launched, [])
        self.assertTrue(prior_result.exists())
        self.assertFalse((evidence / 'runs').exists())

    def test_safe_sandbox_runner_isolates_per_run_evidence_and_wsb(self):
        wsb = self.root / 'data/ai-ui/trial/Trial.wsb'
        wsb.parent.mkdir(parents=True)
        evidence = wsb.parent / 'evidence'
        evidence.mkdir()
        prior_failure = evidence / 'failure.json'
        prior_failure.write_text('{"prior": 1}', encoding='utf-8')
        wsb.write_text(
            '<Configuration><MappedFolders>'
            '<MappedFolder><HostFolder>C:\\old\\evidence</HostFolder>'
            '<SandboxFolder>C:\\AredokoEvidence</SandboxFolder><ReadOnly>false</ReadOnly></MappedFolder>'
            '</MappedFolders></Configuration>',
            encoding='utf-8',
        )

        launched = []
        killed = []
        probe_calls = {'n': 0}

        class FakeProc:
            pid = 9001

            def wait(self, timeout=None):
                return 0

            def poll(self):
                return 0

        def fake_popen(cmd, **kw):
            launch_wsb = Path(cmd[1])
            launched.append(launch_wsb)
            (launch_wsb.parent / 'result.json').write_text('{"pass": true}', encoding='utf-8')
            return FakeProc()

        def fake_list():
            probe_calls['n'] += 1
            if probe_calls['n'] == 1:
                return []
            if probe_calls['n'] == 2:
                return [
                    {'pid': 9001, 'name': 'WindowsSandbox.exe', 'parent_pid': 1, 'cmdline': f'"WindowsSandbox.exe" "{launched[0]}"'},
                    {'pid': 7777, 'name': 'WindowsSandbox.exe', 'parent_pid': 1, 'cmdline': r'"WindowsSandbox.exe" "C:\Other\User.wsb"'},
                ]
            return [{'pid': 7777, 'name': 'WindowsSandbox.exe', 'parent_pid': 1, 'cmdline': r'"WindowsSandbox.exe" "C:\Other\User.wsb"'}]

        passed, report = trial.run_wsb_trial(
            wsb,
            evidence,
            settle_seconds=0,
            list_processes=fake_list,
            popen=fake_popen,
            stop_pids=lambda pids: killed.extend(pids),
        )
        self.assertTrue(passed)
        self.assertTrue(prior_failure.exists())
        run_dir = Path(report['evidence_dir'])
        self.assertEqual(run_dir.parent, evidence / 'runs')
        self.assertEqual(launched, [run_dir / 'Trial.wsb'])
        rewritten = ET.parse(launched[0]).getroot()
        self.assertEqual(rewritten.findtext('MappedFolders/MappedFolder/HostFolder'), str(run_dir))
        self.assertEqual(killed, [9001])

    def test_select_owned_sandbox_pids_ignores_unrelated_instances(self):
        wsb = (self.root / 'data/ai-ui/trial/Trial.wsb').resolve()
        processes = [
            {'pid': 100, 'name': 'WindowsSandbox.exe', 'parent_pid': 1, 'cmdline': f'"C:\\Windows\\System32\\WindowsSandbox.exe" "{wsb}"'},
            {'pid': 101, 'name': 'WindowsSandboxClient.exe', 'parent_pid': 100, 'cmdline': 'WindowsSandboxClient.exe'},
            {'pid': 102, 'name': 'WindowsSandboxServer.exe', 'parent_pid': 101, 'cmdline': ''},
            {'pid': 200, 'name': 'WindowsSandbox.exe', 'parent_pid': 1, 'cmdline': r'"C:\Windows\System32\WindowsSandbox.exe" "C:\Other\User.wsb"'},
            {'pid': 201, 'name': 'WindowsSandboxClient.exe', 'parent_pid': 200, 'cmdline': 'WindowsSandboxClient.exe'},
        ]
        owned = trial.select_owned_sandbox_pids(processes, 100, wsb)
        self.assertEqual(owned, [100, 101, 102])
        self.assertEqual(trial.select_owned_sandbox_pids(processes, 100, wsb, pre_existing_pids={100}), [])


if __name__ == '__main__':
    unittest.main()
