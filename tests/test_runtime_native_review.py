"""Small generated PE headers/metadata; selected runtime code is never run."""
import hashlib,json,struct,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tools')]
from ai_runtime import FORMAT,MARKER
from collect_ai_runtime_notices import write_bundle
from inspect_runtime_native import inspect,record_key,pe_machine


def pe(code=0x8664):
    data=bytearray(134);data[:2]=b'MZ';struct.pack_into('<I',data,60,128);data[128:132]=b'PE\0\0';struct.pack_into('<H',data,132,code);return bytes(data)


class NativeReviewTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.base=Path(temporary.name)
        self.root=self.base/'runtime';site=self.root/'Lib/site-packages';metadata=site/'demo-1.0.dist-info';metadata.mkdir(parents=True)
        (metadata/'METADATA').write_text('Metadata-Version: 2.4\nName: demo\nVersion: 1.0\nLicense-File: LICENSE\n',encoding='utf-8')
        (metadata/'LICENSE').write_bytes(b'generated license');(self.root/'LICENSE.txt').write_bytes(b'generated interpreter notice')
        (metadata/'RECORD').write_text('demo\\core.pyd,,\ndemo.libs/native.dll,,\n../../../outside.exe,,\n',encoding='utf-8')
        payload={'python.exe':pe(),'Lib/site-packages/demo/core.pyd':pe(),'Lib/site-packages/demo.libs/native.dll':pe()}
        for name,data in payload.items():
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        self.entries=[{'path':path.relative_to(self.root).as_posix(),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
                      for path in self.root.rglob('*') if path.is_file()]
        self.manifest();self.notices=self.base/'notices';write_bundle(self.root,self.notices)
    def manifest(self):
        (self.root/MARKER).write_text(json.dumps({'format':FORMAT,'entries':self.entries}),encoding='utf-8')

    def test_native_owners_and_notice_references_are_mapped_without_execution(self):
        before={p:(p.stat().st_mtime_ns,p.read_bytes()) for p in self.root.rglob('*') if p.is_file()}
        with patch('subprocess.Popen',side_effect=AssertionError('No selected native code execution')):report=inspect(self.root,self.notices)
        self.assertEqual((report['native_count'],report['unmapped_count'],report['unknown_pe_count'],report['outside_record_references']),(3,1,0,1))
        self.assertFalse(report['redistribution_approved']);self.assertFalse(report['payload_hashes_verified']);self.assertFalse(report['extra_tree_verified'])
        self.assertTrue(all(row['pe_machine']=='amd64' for row in report['entries']))
        core=next(row for row in report['entries'] if row['path'].endswith('core.pyd'))
        self.assertEqual(core['distribution_record_owners'][0]['name'],'demo');self.assertTrue(core['distribution_record_owners'][0]['notice_files'])
        self.assertEqual(before,{p:(p.stat().st_mtime_ns,p.read_bytes()) for p in self.root.rglob('*') if p.is_file()})

    def test_record_normalization_never_resolves_or_opens_external_paths(self):
        self.assertEqual(record_key('demo\\core.pyd'),'lib/site-packages/demo/core.pyd')
        self.assertEqual(record_key('../../python.exe'),'python.exe')
        for value in ['../../../outside.dll','C:\\private.dll','//host/file.dll','demo/file:stream.dll']:
            with self.subTest(value=value),self.assertRaises(ValueError):record_key(value)

    def test_static_import_inventory_matches_are_candidates_not_loader_approval(self):
        from test_pe_imports import image
        for entry in self.entries:
            if Path(entry['path']).suffix in ('.exe','.pyd','.dll'):
                path=self.root/entry['path'];path.write_bytes(image(imports=('native.dll','KERNEL32.dll','MSVCP140_1.dll'),delayed=(),bits=32 if entry['path']=='python.exe' else 64))
                entry['bytes']=path.stat().st_size;entry['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        self.manifest();notices=self.base/'import-notices';write_bundle(self.root,notices)
        with patch('subprocess.Popen',side_effect=AssertionError('No native execution')):report=inspect(self.root,notices,imports=True)
        self.assertTrue(report['static_imports_inspected']);self.assertFalse(report['loader_resolution_verified'])
        self.assertFalse(report['dynamic_dependencies_inspected']);self.assertFalse(report['redistribution_approved'])
        edges=report['entries'][0]['static_imports']['edges']
        self.assertEqual(edges[0]['inventory_candidates'],['Lib/site-packages/demo.libs/native.dll'])
        self.assertEqual(edges[1]['inventory_candidates'],[])
        python=next(row for row in report['entries'] if row['path']=='python.exe')
        self.assertEqual(python['static_imports']['edges'][0]['same_machine_candidates'],[])
        self.assertEqual(len(report['unbundled_vc_imports']),3)
        self.assertLess(report['static_import_bytes_read'],32768)

    def test_malformed_imports_are_incomplete_not_a_successful_empty_graph(self):
        report=inspect(self.root,self.notices,imports=True)
        self.assertFalse(report['static_imports_inspected'])
        self.assertTrue(all(row['static_imports']['state']=='invalid' for row in report['entries']))

    def test_changed_native_size_is_rejected_before_review_output(self):
        (self.root/'python.exe').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'size changed'):inspect(self.root,self.notices)

    def test_duplicate_native_identity_is_rejected(self):
        self.entries.append({**next(e for e in self.entries if e['path']=='python.exe'),'path':'PYTHON.EXE'});self.manifest()
        with self.assertRaisesRegex(ValueError,'Invalid declared'):inspect(self.root,self.notices)

    def test_record_owner_metadata_must_match_sealed_hash(self):
        record=self.root/'Lib/site-packages/demo-1.0.dist-info/RECORD';record.write_text(record.read_text()+'\n')
        with self.assertRaisesRegex(ValueError,'metadata differs'):inspect(self.root,self.notices)

    def test_architecture_and_bad_headers_are_explicit(self):
        path=self.base/'header.dll'
        for code,name in [(0x8664,'amd64'),(0x14c,'x86'),(0xaa64,'arm64')]:
            path.write_bytes(pe(code));self.assertEqual(pe_machine(path),name)
        for data in [b'not PE',b'MZ'+b'\0'*62,pe()[:132]]:
            path.write_bytes(data);self.assertIsNone(pe_machine(path))

    def test_different_path_and_handle_clocks_are_kept_separate_but_changes_reject(self):
        path=self.root/'python.exe';info=path.stat()
        handle=types.SimpleNamespace(**{name:getattr(info,name) for name in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')})
        handle.st_ctime_ns+=100
        with patch('inspect_runtime_native.os.fstat',return_value=handle):self.assertEqual(pe_machine(path),'amd64')
        changed=types.SimpleNamespace(**{**vars(handle),'st_ctime_ns':handle.st_ctime_ns+1})
        with patch('inspect_runtime_native.os.fstat',side_effect=[handle,changed]):
            with self.assertRaisesRegex(RuntimeError,'source changed'):pe_machine(path)


if __name__=='__main__':unittest.main()
