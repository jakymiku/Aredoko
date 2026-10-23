"""Generated sealed-pack catalogs only; no network or selected code execution."""
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'tools'),str(Path(__file__).resolve().parent)]
from test_ai_runtime import fixture,seal
from build_ai_runtime_catalog import build_catalog,write_new
from ai_acquisition import Catalog

class RuntimeCatalogTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.base=Path(temp.name);self.pack=fixture(self.base/'pack')
        self.options={'key':'generated-runtime','revision':'c'*40,'base_url':'https://example.org/immutable/'+'c'*40,'license':'Multiple; see NOTICE','license_url':'https://example.org/NOTICE','allowed_hosts':['example.org']}
    def test_complete_catalog_includes_marker_and_preserves_source(self):
        before={str(p.relative_to(self.pack)):(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in self.pack.rglob('*') if p.is_file()}
        with patch('subprocess.Popen',side_effect=AssertionError('Selected code must not execute')):
            raw,catalog=build_catalog(self.pack,**self.options)
        value=json.loads(raw);self.assertEqual(catalog.kind,'runtime');self.assertEqual(len(value['entries']),len(before))
        for entry in value['entries']:
            self.assertEqual(entry['sha256'],before[str(Path(entry['path']))][0]);self.assertTrue(entry['url'].startswith(self.options['base_url']+'/'))
        self.assertEqual(next(e for e in value['entries'] if e['path']=='aredoko-ai-runtime.json')['role'],'inventory')
        self.assertEqual(before,{str(p.relative_to(self.pack)):(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in self.pack.rglob('*') if p.is_file()})
    def test_corrupt_or_unlisted_pack_never_produces_catalog(self):
        (self.pack/'extra.py').write_bytes(b'extra')
        with self.assertRaises(ValueError):build_catalog(self.pack,**self.options)
        (self.pack/'extra.py').unlink();bulk=self.pack/'Lib/site-packages/torch/lib/generated.dll';bulk.write_bytes(b'bad')
        with self.assertRaises(ValueError):build_catalog(self.pack,**self.options)
    def test_url_encoding_and_source_host_contract(self):
        (self.pack/'NOTICE third-party.txt').write_text('fixture');seal(self.pack)
        raw,_=build_catalog(self.pack,**self.options)
        self.assertTrue(next(e for e in json.loads(raw)['entries'] if e['path']=='NOTICE third-party.txt')['url'].endswith('NOTICE%20third-party.txt'))
        for base in ('http://example.org/runtime','https://user:secret@example.org/runtime','https://example.org/path?token=secret'):
            with self.subTest(base=base),self.assertRaises(ValueError):build_catalog(self.pack,**{**self.options,'base_url':base})
        with self.assertRaises(ValueError):build_catalog(self.pack,**{**self.options,'allowed_hosts':['other.example.org']})
    def test_output_never_overwrites_existing_or_changes_pack(self):
        raw,_=build_catalog(self.pack,**self.options);output=self.base/'catalog.json';write_new(raw,output,self.pack)
        self.assertEqual(output.read_bytes(),raw)
        with self.assertRaises(FileExistsError):write_new(b'changed',output,self.pack)
        self.assertEqual(output.read_bytes(),raw)
        with self.assertRaises(ValueError):write_new(raw,self.pack/'catalog.json',self.pack)
    def test_cancel_produces_no_catalog(self):
        with self.assertRaises(RuntimeError):build_catalog(self.pack,**self.options,cancelled=lambda:True)

if __name__=='__main__':unittest.main()
