"""Generated resolver reports only; no network, installation or GPU."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from build_ai_wheel_lock import build, ROOTS, TORCH_HASHES


class AIWheelLockTests(unittest.TestCase):
    def fixture(self):
        installs = []
        for name, version in ROOTS.items():
            native = name in TORCH_HASHES or name == 'pillow'
            filename = name.replace('-', '_') + '-' + version + ('-cp313-cp313-win_amd64.whl' if native else '-py3-none-any.whl')
            host = 'download.pytorch.org' if name in TORCH_HASHES else 'files.pythonhosted.org'
            digest = TORCH_HASHES.get(name, 'a' * 64)
            installs.append({'metadata': {'name': name, 'version': version},
                'is_direct': name in TORCH_HASHES,
                'download_info': {'url': 'https://' + host + '/whl/' + filename,
                                  'archive_info': {'hashes': {'sha256': digest}}}})
        return {'version': '1', 'environment': {'sys_platform': 'win32', 'platform_machine': 'AMD64', 'python_full_version': '3.13.17'}, 'install': installs}

    def test_official_fixed_roots_generate_hash_required_draft(self):
        value, requirements = build(self.fixture())
        self.assertEqual(value['review_status'], 'draft')
        self.assertEqual(len(value['entries']), 5)
        self.assertEqual(requirements.count('--hash=sha256:'), 5)

    def test_local_pytorch_cache_keeps_pinned_official_origin(self):
        report = self.fixture()
        for item in report['install'][:2]:
            name = item['metadata']['name']
            filename = name + '-' + ROOTS[name] + '-cp313-cp313-win_amd64.whl'
            item['download_info']['url'] = 'file:///generated-cache/' + filename
        value, _ = build(report)
        self.assertTrue(all(entry['url'].startswith('https://') for entry in value['entries']))

    def test_changed_origin_hash_version_or_architecture_is_refused(self):
        original = self.fixture()
        for mutate in (
            lambda report: report['install'][0]['download_info'].update(url='https://untrusted.invalid/torch.whl'),
            lambda report: report['install'][0]['download_info']['archive_info']['hashes'].update(sha256='b' * 64),
            lambda report: report['install'][0]['metadata'].update(version='2.9.2'),
            lambda report: report['environment'].update(sys_platform='linux'),
            lambda report: report['install'][0]['download_info'].update(url='https://download.pytorch.org/whl/torch-2.9.1-cp312-cp312-win_amd64.whl'),
        ):
            report = copy.deepcopy(original)
            mutate(report)
            with self.subTest(report=report), self.assertRaises(ValueError):
                build(report)

    def test_missing_duplicate_or_source_distribution_is_refused(self):
        report = self.fixture()
        report['install'].pop()
        with self.assertRaises(ValueError): build(report)
        report = self.fixture()
        report['install'].append(copy.deepcopy(report['install'][0]))
        with self.assertRaises(ValueError): build(report)
        report = self.fixture()
        report['install'][-1]['download_info']['url'] = 'https://files.pythonhosted.org/package.tar.gz'
        with self.assertRaises(ValueError): build(report)


if __name__ == '__main__': unittest.main()
