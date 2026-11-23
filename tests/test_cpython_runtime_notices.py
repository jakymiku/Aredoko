"""Generated CPython native inventory and checked-in text notices; no code loading."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tools'),str(ROOT/'tests')]
import test_ai_runtime as fixture_tools
import prepare_cpython_runtime_notices as tool
from ai_runtime import MARKER,inspect_runtime
from collect_ai_runtime_notices import write_bundle
from inspect_runtime_native import inspect
from cpython_component_contract import COMPONENT,NATIVE_NAMES,notice_bindings,validate_component,validate_sources


class CPythonNoticeTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.base=Path(temporary.name)
        self.source=fixture_tools.fixture(self.base/'source');self.output=self.base/'new-pack'
        pe=bytearray(512);pe[:2]=b'MZ';struct.pack_into('<I',pe,60,128);pe[128:132]=b'PE\0\0';struct.pack_into('<H',pe,132,0x8664)
        for name in NATIVE_NAMES:(self.source/name).write_bytes(pe)
        meta=self.source/'Lib/site-packages/demo-1.0.dist-info';meta.mkdir()
        (meta/'METADATA').write_text('Metadata-Version: 2.4\nName: demo\nVersion: 1.0\nLicense-File: LICENSE\n')
        (meta/'LICENSE').write_text('Generated demo notice');self.source_manifest=fixture_tools.seal(self.source)
        self.python_notices=self.base/'python-notices';write_bundle(self.source,self.python_notices)
        self.notices=self.base/'notice-sources';shutil.copytree(ROOT/'config/runtime-notices/cpython311-20261029',self.notices)
        self.reference=self.base/'reference.json';rows=[]
        versions={'DLLs/libcrypto-3.dll':'3.0.13','DLLs/libssl-3.dll':'3.0.13','DLLs/libffi-8.dll':None,
            'DLLs/sqlite3.dll':'3.45.1.0','DLLs/tcl86t.dll':'8.6.12','DLLs/tk86t.dll':'8.6.12'}
        for e in self.source_manifest['entries']:
            if e['path'] in NATIVE_NAMES:rows.append({**e,'file_version':versions.get(e['path'],'3.11.9'),'product_version':versions.get(e['path'],'3.11.9')})
        self.ref={'format':'aredoko-cpython-native-reference-v1','runtime_manifest_sha256':hashlib.sha256((self.source/MARKER).read_bytes()).hexdigest(),
            'redistribution_approved':False,'source_executed':False,'version_resources_are_supplier_proof':False,'registry_enabled':False,'entries':rows}
        self.save_ref()
    def save_ref(self):self.reference.write_text(json.dumps(self.ref))
    def prepare(self,**kwargs):return tool.prepare(self.source,self.output,notices=self.notices,reference=self.reference,**kwargs)
    def snapshot(self):return {p.relative_to(self.source).as_posix():(p.stat().st_mtime_ns,p.read_bytes()) for p in self.source.rglob('*') if p.is_file()}
    def test_new_pack_retains_all_source_bytes_and_binds_38_native_files_without_approval(self):
        before=self.snapshot()
        with patch('subprocess.Popen',side_effect=AssertionError('Selected code must not execute')):report=self.prepare();review=inspect(self.output,self.python_notices)
        self.assertTrue(report['prepared']);self.assertFalse(report['redistribution_approved']);self.assertFalse(report['notice_coverage_reviewed'])
        self.assertEqual(before,self.snapshot());self.assertTrue(all((self.output/name).read_bytes()==data for name,(_,data) in before.items() if name!=MARKER))
        component=json.loads((self.output/COMPONENT/'component.json').read_text())
        self.assertEqual({e['path'] for e in component['natives']},NATIVE_NAMES);self.assertEqual(component['file_notice_bindings'],notice_bindings())
        self.assertEqual(len(review['native_components']),1);self.assertEqual(len(review['native_components'][0]['native_files']),38)
        self.assertEqual(review['unmapped_count'],1);self.assertEqual(review['components_pending_notice_review'],1)
        self.assertFalse(review['native_components'][0]['supplier_binary_hashes_verified']);self.assertFalse(review['redistribution_approved'])
        self.assertTrue(review['native_components'][0]['payload_hashes_verified']);self.assertEqual(inspect_runtime(self.output,verify=True)['manifest_sha256'],report['manifest_sha256'])
    def test_preflight_is_read_only_and_existing_output_or_overlap_is_preserved(self):
        before=self.snapshot();self.assertFalse(self.prepare(check=True)['prepared']);self.assertFalse(self.output.exists());self.assertEqual(before,self.snapshot())
        with self.assertRaises(ValueError):tool.prepare(self.source,self.source/'nested',notices=self.notices,reference=self.reference)
        self.output.mkdir();(self.output/'sentinel').write_text('Keep me')
        with self.assertRaises(FileExistsError):self.prepare()
        self.assertEqual((self.output/'sentinel').read_text(),'Keep me');self.assertEqual(before,self.snapshot())
    def test_changed_notice_and_extra_notice_are_rejected_before_creating_output(self):
        p=self.notices/'openssl-LICENSE.txt';original=p.read_bytes();p.write_bytes(b'x'*len(original))
        with self.assertRaisesRegex(ValueError,'Notice source changed'):self.prepare()
        self.assertFalse(self.output.exists());p.write_bytes(original);(self.notices/'extra.txt').write_text('unknown')
        with self.assertRaisesRegex(ValueError,'Unlisted'):self.prepare()
        self.assertFalse(self.output.exists())
    def test_stale_reference_wrong_version_and_approval_claim_rejected(self):
        original=json.loads(json.dumps(self.ref))
        operations=[lambda v:v.update(runtime_manifest_sha256='0'*64),lambda v:v.update(redistribution_approved=True),
            lambda v:v.update(version_resources_are_supplier_proof=True),lambda v:v['entries'].pop(),
            lambda v:v['entries'][0].update(file_version='3.14.0'),lambda v:v['entries'][0].update(path='../python.exe')]
        for operation in operations:
            self.ref=json.loads(json.dumps(original));operation(self.ref);self.save_ref()
            with self.subTest(operation=operation),self.assertRaises(ValueError):self.prepare()
            self.assertFalse(self.output.exists())
    def test_changed_native_is_never_published_with_a_final_marker(self):
        path=self.source/'DLLs/_bz2.pyd';data=bytearray(path.read_bytes());data[-1]=1;path.write_bytes(data)
        with self.assertRaisesRegex(ValueError,'Runtime source changed'):self.prepare()
        self.assertFalse((self.output/MARKER).exists());self.assertTrue(path.exists())
    def test_cancel_during_copy_and_final_validation_retains_source_without_publishing(self):
        before=self.snapshot()
        def progress(value):
            if value['stage']=='copying_runtime':self.cancel=True
        self.cancel=False
        with self.assertRaises(InterruptedError):self.prepare(cancelled=lambda:self.cancel,progress=progress)
        self.assertFalse((self.output/MARKER).exists());self.assertEqual(before,self.snapshot())
        self.output=self.base/'final-validation-cancel';self.cancel=False
        def late(value):
            if value['stage']=='checking_runtime':self.cancel=True
        with self.assertRaises((RuntimeError,InterruptedError)):self.prepare(cancelled=lambda:self.cancel,progress=late)
        self.assertFalse((self.output/MARKER).exists());self.assertEqual(before,self.snapshot())
    def test_audit_rejects_resealed_forged_coverage_and_missing_notice_marker(self):
        self.prepare();path=self.output/COMPONENT/'component.json';original=path.read_bytes()
        value=json.loads(original);value['notice_coverage_reviewed']=True;path.write_text(json.dumps(value));fixture_tools.seal(self.output)
        with self.assertRaisesRegex(ValueError,'approval claim'):inspect(self.output,self.python_notices)
        path.write_bytes(original);fixture_tools.seal(self.output);path.unlink()
        with self.assertRaises(ValueError):inspect(self.output,self.python_notices)
    def test_resealed_notice_or_reference_edits_do_not_change_existing_component_binding(self):
        self.prepare()
        for name in ('openssl-LICENSE.txt','reference.json','python-installed-LICENSE.txt'):
            p=self.output/COMPONENT/name;original=p.read_bytes();p.write_bytes(b'x'*len(original));fixture_tools.seal(self.output)
            with self.subTest(name=name),self.assertRaises(ValueError):inspect(self.output,self.python_notices)
            p.write_bytes(original)
        fixture_tools.seal(self.output)
    def test_source_urls_and_per_file_notice_omissions_are_rejected(self):
        value=json.loads((self.notices/'sources.json').read_text());original=json.loads(json.dumps(value))
        operations=[lambda v:v['entries'][0].update(source_url='https://untrusted.example/license'),lambda v:v['entries'][0].update(extraction='changed'),
            lambda v:v['entries'][0].update(source_sha256='0'*64),lambda v:v['entries'].pop(),lambda v:v.update(redistribution_approved=True)]
        for operation in operations:
            value=json.loads(json.dumps(original));operation(value)
            with self.subTest(operation=operation),self.assertRaises(ValueError):validate_sources(value)
        self.prepare();component=json.loads((self.output/COMPONENT/'component.json').read_text());declared={e['path'].casefold():e for e in json.loads((self.output/MARKER).read_text())['entries']}
        component['file_notice_bindings']['DLLs/_ssl.pyd'].remove(COMPONENT+'/openssl-LICENSE.txt')
        with self.assertRaisesRegex(ValueError,'per-file'):validate_component(component,declared)


if __name__=='__main__':unittest.main()
