"""Generated model packs/loopback only; no real weights, runtime or GPU execution."""
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import os
import sys
import tempfile
import threading
import unittest
sys.path[:0] = [str(Path(__file__).resolve().parents[1] / name) for name in ('app', 'tools')]
from ai_acquisition import Catalog, acquire
from ai_model_pack import inspect_model, model_validator
from ai_profiles import DEFAULT_PROFILE
from ai_runtime import model_state
from ai_runtime_preferences import AIRuntimePreferences
from build_ai_model_catalog import build_catalog, write_new
from tagger_profile import WDProfile

REPO = Path(__file__).resolve().parents[1]

class ModelCatalogTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name); self.source = self.base / 'explicit model'; self.source.mkdir()
        self.profile = replace(DEFAULT_PROFILE, directory='generated model/nested', revision='a' * 40)
        for name, content in {'aredoko-revision.txt': self.profile.revision.encode(), 'config.json': b'{}',
            'model.safetensors': b'generated weights', 'tokenizer.json': b'{}', 'LICENSE.txt': b'generated license fixture'}.items():
            (self.source / name).write_bytes(content)
        self.options = dict(key='generated-model', base_url='https://publisher.example/pinned/' + self.profile.revision,
                            license='fixture-only', license_url='https://publisher.example/NOTICE', allowed_hosts=['publisher.example'])
    def build(self):
        return build_catalog(self.source, self.profile, **self.options)
    def version(self, raw):
        return Catalog.parse(json.dumps(raw).encode())
    def source_state(self):
        return {p.relative_to(self.source).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.source.rglob('*') if p.is_file()}

    def test_draft_keeps_exact_layout_source_and_url_encoding_without_execution(self):
        before = self.source_state()
        with patch('subprocess.Popen', side_effect=AssertionError('No selected code execution')):
            raw, catalog = self.build()
        self.assertEqual(self.source_state(), before)
        self.assertEqual(catalog.kind, 'model'); self.assertEqual(catalog.revision, self.profile.revision)
        self.assertEqual({entry.path for entry in catalog.entries}, {self.profile.directory + '/' + name for name in before})
        self.assertTrue(all(entry.url.startswith(self.options['base_url'] + '/') for entry in catalog.entries))
        for entry in catalog.entries:
            name = entry.path[len(self.profile.directory) + 1:]
            self.assertEqual(entry.sha256, hashlib.sha256(before[name][0]).hexdigest())
        self.assertEqual(json.loads(raw)['format'], 'aredoko-acquisition-v1')
        output = self.base / 'draft.json'; write_new(raw, output, self.source)
        with self.assertRaises(FileExistsError): write_new(b'replace', output, self.source)
        self.assertEqual(output.read_bytes(), raw)
        with self.assertRaises(ValueError): write_new(raw, self.source / 'catalog.json', self.source)

    def test_sharded_model_and_missing_or_unsafe_shard(self):
        (self.source / 'model.safetensors').unlink()
        (self.source / 'weights').mkdir(); (self.source / 'weights/part.safetensors').write_bytes(b'shard')
        index = self.source / 'model.safetensors.index.json'
        index.write_text(json.dumps({'weight_map': {'x': 'weights/part.safetensors'}}))
        self.build()
        for name in ('weights/missing.safetensors', '../escape.safetensors', 'CON'):
            index.write_text(json.dumps({'weight_map': {'x': name}}))
            with self.subTest(name=name), self.assertRaises((ValueError, OSError)): self.build()

    def test_wrong_revision_duplicate_metadata_and_missing_tokenizer_fail(self):
        marker = self.source / 'aredoko-revision.txt'; marker.write_text('b' * 40)
        with self.assertRaisesRegex(ValueError, 'revision'): self.build()
        marker.write_text(self.profile.revision)
        config = self.source / 'config.json'; config.write_text('{"x":1,"x":2}')
        with self.assertRaisesRegex(ValueError, 'Duplicate'): self.build()
        config.write_text('{}'); (self.source / 'tokenizer.json').unlink()
        with self.assertRaisesRegex(ValueError, 'tokenizer'): self.build()

    def test_license_payload_profile_boundary_and_catalog_revision_required(self):
        raw, _ = self.build(); value = json.loads(raw)
        for mutation in ('kind', 'revision', 'prefix', 'license', 'role'):
            item = json.loads(raw)
            if mutation == 'kind': item['kind'] = 'runtime'
            elif mutation == 'revision': item['revision'] = 'b' * 40
            elif mutation == 'prefix': item['entries'][0]['path'] = 'another-model/config.json'
            elif mutation == 'license': item['entries'] = [e for e in item['entries'] if e['role'] != 'license']
            else:
                for e in item['entries']:
                    if e['path'].endswith('/config.json'): e['role'] = 'weights'
            catalog = self.version(item)
            if mutation == 'role':
                target = self.base / mutation / self.profile.directory; target.mkdir(parents=True)
                import shutil
                shutil.copytree(self.source, target, dirs_exist_ok=True)
                with self.assertRaisesRegex(ValueError, 'role'): model_validator(self.profile, catalog)(self.base / mutation, lambda: False)
            else:
                with self.subTest(mutation=mutation), self.assertRaises(ValueError): model_validator(self.profile, catalog)
        (self.source / 'LICENSE.txt').unlink()
        with self.assertRaisesRegex(ValueError, 'license'): self.build()

    def test_changed_earlier_file_is_detected_after_hashing(self):
        from build_ai_model_catalog import digest as original
        altered = False
        def changing(path, **kwargs):
            nonlocal altered
            result = original(path, **kwargs)
            if not altered:
                altered = True; path.write_bytes(path.read_bytes() + b'changed')
            return result
        with patch('build_ai_model_catalog.digest', side_effect=changing):
            with self.assertRaisesRegex(ValueError, 'changed'): self.build()

    def test_summary_exposes_only_profile_bound_model_identity(self):
        from ai_download_jobs import AIDownloadJobs
        from model_locations import ModelTarget
        from unittest.mock import Mock
        _, catalog = self.build()
        validator = model_validator(self.profile, catalog)
        jobs = AIDownloadJobs(self.base / 'downloads', specifications=((catalog, validator),))
        self.addCleanup(jobs.close)
        row = jobs.catalogs()['catalogs'][0]
        self.assertEqual(row['model_target'], ModelTarget.for_profile('embedding', self.profile).to_dict())
        self.assertEqual(len(row['definition_sha256']), 64)
        changed = replace(self.profile, query_prompt_name=None, query_prefix='another:')
        other = model_validator(changed, catalog)
        self.assertEqual(other.target, validator.target)
        self.assertNotEqual(other.definition_sha256, validator.definition_sha256)
        arbitrary = Mock(model_target=validator.target, definition_sha256=validator.definition_sha256)
        legacy = AIDownloadJobs(self.base / 'legacy', specifications=((catalog, arbitrary),))
        self.addCleanup(legacy.close)
        self.assertNotIn('model_target', legacy.catalogs()['catalogs'][0])
        mismatched = replace(catalog, fingerprint='0' * 64)
        with self.assertRaisesRegex(ValueError, 'binding mismatch'):
            AIDownloadJobs(self.base / 'bad', specifications=((mismatched, validator),))

    def test_source_hardlinks_and_cancellation_are_rejected(self):
        os.link(self.source / 'config.json', self.base / 'alias.json')
        with self.assertRaisesRegex(ValueError, 'Hardlinked'): self.build()
        (self.base / 'alias.json').unlink()
        with self.assertRaises(InterruptedError): build_catalog(self.source, self.profile, cancelled=lambda: True, **self.options)

    def test_untrusted_host_or_plain_http_and_escaping_profile_are_rejected(self):
        for changed in ({'base_url': 'http://publisher.example/model'}, {'base_url': 'https://other.example/model'}, {'base_url': 'https://publisher.example/model?q=1'}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                build_catalog(self.source, self.profile, **(self.options | changed))
        bad = replace(self.profile, directory='CON')
        with self.assertRaises(ValueError): build_catalog(self.source, bad, **self.options)

    def test_wd_profile_binds_hashes_provenance_and_roles(self):
        import shutil
        shutil.rmtree(self.source); self.source.mkdir()
        value = json.loads((REPO / 'config/tagger-profiles/wd-swinv2-v3.json').read_text())
        value['model_directory'] = 'models/generated-wd'
        for name, content in {'model.onnx': b'generated onnx', 'selected_tags.csv': b'tag,category\nfixture,0'}.items():
            (self.source / name).write_bytes(content)
            value['artifacts'][name] = {'size': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
        profile = WDProfile.from_dict(value)
        (self.source / 'aredoko-source.json').write_text(json.dumps(profile.identity()))
        (self.source / 'NOTICE').write_bytes(b'fixture notice')
        raw, catalog = build_catalog(self.source, profile, **self.options)
        target = self.base / 'installed/generated-wd'; shutil.copytree(self.source, target)
        model_validator(profile, catalog)(target.parent, lambda: False)
        self.assertEqual(profile.verify(self.base, hashes=True, models_root=target.parent), target)
        value = json.loads(raw); next(e for e in value['entries'] if e['role'] == 'weights')['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'fixed profile'): model_validator(profile, self.version(value))
        (self.source / 'model.onnx').write_bytes(b'x' * len(b'generated onnx'))
        with self.assertRaisesRegex(ValueError, 'fixed profile'): build_catalog(self.source, profile, **self.options)
        (self.source / 'aredoko-source.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'provenance'): inspect_model(self.source, profile)

    def test_generated_acquisition_then_explicit_models_selection(self):
        raw, _ = self.build(); value = json.loads(raw); owner = self; requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                name = self.path.removeprefix('/artifact/')
                requests.append(name); payload = (owner.source / name).read_bytes()
                self.send_response(200); self.send_header('Content-Length', str(len(payload))); self.end_headers(); self.wfile.write(payload)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(3)))
        value['allowed_hosts'] = ['127.0.0.1']
        for entry in value['entries']:
            entry['url'] = f'http://127.0.0.1:{server.server_port}/artifact/' + entry['path'][len(self.profile.directory) + 1:]
        catalog = Catalog.parse(json.dumps(value).encode(), test_loopback=True)
        original = self.source_state(); preferences = self.base / 'launch-settings.json'
        preferences.write_text('{"ui_theme":"dark","database":"' + (self.base / 'catalog.sqlite').as_posix() + '"}')
        with patch('subprocess.Popen', side_effect=AssertionError('No selected runtime execution')):
            result = acquire(catalog, self.base / 'versions', validate=model_validator(self.profile, catalog), publish=lambda action: action())
            self.assertFalse(preferences.read_text().find('models_root') >= 0)
            service = AIRuntimePreferences(preferences, self.base, self.profile)
            service.select(models_root=result['root'], consent=True)
            state = service.snapshot()
        self.assertTrue(state['model']['ready']); self.assertFalse(state['inference_verified'])
        self.assertTrue(state['restart_required']); self.assertEqual(json.loads(preferences.read_text())['ui_theme'], 'dark')
        self.assertTrue(model_state(self.profile, self.base, result['root'])['ready'])
        self.assertEqual(self.source_state(), original); self.assertEqual(len(requests), len(catalog.entries))
        corrupt = Path(result['root']) / self.profile.directory / 'model.safetensors'; corrupt.write_bytes(b'x' * corrupt.stat().st_size)
        with self.assertRaisesRegex(ValueError, 'checksum'):
            acquire(catalog, self.base / 'versions', validate=model_validator(self.profile, catalog), publish=lambda action: action())
        self.assertEqual(len(requests), len(catalog.entries))

if __name__ == '__main__':
    unittest.main()
