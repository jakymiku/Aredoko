"""Generated application-owned registry fixtures. No network or model execution."""
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import sys
import tempfile
import unittest
sys.path[:0] = [str(Path(__file__).resolve().parents[1] / name) for name in ('app', 'tools')]
from ai_acquisition_registry import Registration, TRUSTED_CATALOGS, load_trusted_specs
from ai_acquisition import Catalog
from ai_profiles import DEFAULT_PROFILE
from build_ai_model_catalog import build_catalog as model_catalog
from build_ai_runtime_catalog import build_catalog as runtime_catalog
from test_ai_runtime import fixture

class AcquisitionRegistryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); (self.root / 'config/acquisition').mkdir(parents=True)
        self.source = self.root / 'source'; self.source.mkdir()
        self.profile = replace(DEFAULT_PROFILE, directory='generated-model', revision='a' * 40)
        for name, payload in {'aredoko-revision.txt': self.profile.revision.encode(), 'config.json': b'{}',
            'model.safetensors': b'generated', 'tokenizer.json': b'{}', 'NOTICE': b'fixture license'}.items():
            (self.source / name).write_bytes(payload)
        self.options = dict(key='generated-model', base_url='https://example.org/pinned/' + self.profile.revision,
                            license='fixture only', license_url='https://example.org/NOTICE', allowed_hosts=['example.org'])
        raw, catalog = model_catalog(self.source, self.profile, **self.options)
        self.catalog_path = self.root / 'config/acquisition/model.json'; self.catalog_path.write_bytes(raw)
        self.profile_path = self.root / 'config/model.json'; self.profile_path.write_text(json.dumps(self.profile.to_dict()))
        self.entry = Registration('config/acquisition/model.json', catalog.fingerprint, 'config/model.json',
                                  hashlib.sha256(self.profile_path.read_bytes()).hexdigest(), 'embedding')

    def test_only_source_listed_catalog_is_loaded_without_network_or_execution(self):
        (self.root / 'config/acquisition/unregistered.json').write_text('not a catalog')
        with patch('subprocess.Popen', side_effect=AssertionError('No selected code execution')):
            specs = load_trusted_specs(self.root, (self.entry,))
        self.assertEqual(len(specs), 1); self.assertEqual(specs[0][0].fingerprint, self.entry.catalog_id)
        installed = self.root / 'installed' / self.profile.directory
        import shutil
        shutil.copytree(self.source, installed)
        self.assertIsNone(specs[0][1](installed.parent, lambda: False))

    def test_production_empty_registry_never_reads_arbitrary_config(self):
        self.assertEqual(TRUSTED_CATALOGS, ())
        with patch('ai_acquisition_registry._read', side_effect=AssertionError('No catalog discovery')):
            self.assertEqual(load_trusted_specs(self.root), ())

    def test_changed_catalog_and_changed_profile_are_rejected(self):
        original = self.catalog_path.read_bytes(); value = json.loads(original); value['license'] = 'changed'
        self.catalog_path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'catalog changed'): load_trusted_specs(self.root, (self.entry,))
        self.catalog_path.write_bytes(original); value = self.profile.to_dict(); value['label'] = 'changed'
        self.profile_path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'profile changed'): load_trusted_specs(self.root, (self.entry,))

    def test_model_cannot_use_runtime_validator_or_unpinned_profile(self):
        invalid = [replace(self.entry, profile_kind=None), replace(self.entry, profile_sha256='0' * 64),
                   replace(self.entry, profile_kind='downloaded-python'), replace(self.entry, profile_path='../source/config.json')]
        for entry in invalid:
            with self.subTest(entry=entry), self.assertRaises(ValueError): load_trusted_specs(self.root, (entry,))

    def test_unsafe_paths_duplicate_registrations_and_production_http_rejected(self):
        for entry in (replace(self.entry, catalog_path='../outside.json'), replace(self.entry, catalog_path=None),
                      replace(self.entry, catalog_path='config/acquisition/../model.json')):
            with self.subTest(entry=entry), self.assertRaises(ValueError): load_trusted_specs(self.root, (entry,))
        with self.assertRaisesRegex(ValueError, 'Duplicate'): load_trusted_specs(self.root, (self.entry, self.entry))
        value = json.loads(self.catalog_path.read_bytes()); value['entries'][0]['url'] = 'http://127.0.0.1/artifact'
        self.catalog_path.write_text(json.dumps(value))
        with self.assertRaises(ValueError): load_trusted_specs(self.root, (self.entry,))

    def test_runtime_registry_always_uses_existing_full_validator(self):
        pack = fixture(self.root / 'runtime')
        raw, catalog = runtime_catalog(pack, revision='b' * 40, **(self.options | {'key': 'generated-runtime'}))
        path = self.root / 'config/acquisition/runtime.json'; path.write_bytes(raw)
        entry = Registration('config/acquisition/runtime.json', catalog.fingerprint)
        specs = load_trusted_specs(self.root, (entry,)); specs[0][1](pack, lambda: False)
        (pack / 'unlisted.py').write_bytes(b'not executed')
        with self.assertRaisesRegex(ValueError, 'Unlisted'): specs[0][1](pack, lambda: False)
        with self.assertRaisesRegex(ValueError, 'runtime validator'): load_trusted_specs(self.root, (replace(entry, profile_kind='embedding'),))

if __name__ == '__main__':
    unittest.main()
