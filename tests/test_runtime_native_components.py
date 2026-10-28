"""Generated CRT components; metadata audit must not execute selected files."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tools')]
from ai_runtime import FORMAT,MARKER
from collect_ai_runtime_notices import write_bundle
from inspect_runtime_native import inspect
from msvc_component_contract import COMPONENT,CRT_NAMES


def entry(path,key):
    data=path.read_bytes();return {'path':key,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}


class NativeComponentTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.base=Path(temporary.name)
        self.root=self.base/'runtime';meta=self.root/'Lib/site-packages/demo-1.0.dist-info';meta.mkdir(parents=True)
        (meta/'METADATA').write_text('Metadata-Version: 2.4\nName: demo\nVersion: 1.0\nLicense-File: LICENSE\n')
        (meta/'LICENSE').write_text('Generated distribution terms');(self.root/'LICENSE.txt').write_text('Generated interpreter terms')
        data=bytearray(150);data[:2]=b'MZ';struct.pack_into('<I',data,60,128)
        data[128:132]=b'PE\0\0';struct.pack_into('<H',data,132,0x8664)
        for name in ('python.exe',*CRT_NAMES):(self.root/name).write_bytes(data)
        self.directory=self.root/COMPONENT;self.directory.mkdir(parents=True)
        for name in ('runtime-license.docx','runtime-license.txt','NOTICE.txt'):(self.directory/name).write_bytes(b'Generated original terms '+name.encode())
        self.component={'format':'aredoko-msvc-component-v1','source_sha256':'a'*64,'version':'14.51.36247.0',
            'license_document_sha256':hashlib.sha256((self.directory/'runtime-license.docx').read_bytes()).hexdigest(),
            'license_url':'https://visualstudio.microsoft.com/license-terms/test/','redistribution_approved':False,
            'dlls':[entry(self.root/name,name) for name in sorted(CRT_NAMES)],
            'notices':[entry(path,COMPONENT+'/'+path.name) for path in sorted(self.directory.iterdir())]}
        self.save();self.notices=self.base/'notices';write_bundle(self.root,self.notices)

    def save(self):
        (self.directory/'component.json').write_text(json.dumps(self.component))
        entries=[entry(path,path.relative_to(self.root).as_posix()) for path in sorted(self.root.rglob('*')) if path.is_file() and path.name!=MARKER]
        (self.root/MARKER).write_text(json.dumps({'format':FORMAT,'entries':entries}))

    def test_bound_crt_and_notices_are_mapped_without_approving_loading_or_rights(self):
        before={path:path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        with patch('subprocess.Popen',side_effect=AssertionError('No selected code execution')):result=inspect(self.root,self.notices)
        self.assertEqual(result['native_count'],13);self.assertEqual(result['unmapped_count'],1)
        self.assertEqual(result['unmapped_distribution_record_count'],13)
        self.assertEqual(len(result['native_components']),1);component=result['native_components'][0]
        self.assertEqual(set(component['dll_files']),CRT_NAMES);self.assertTrue(component['payload_hashes_verified'])
        self.assertFalse(component['redistribution_approved']);self.assertFalse(result['redistribution_approved'])
        self.assertFalse(result['loader_resolution_verified']);self.assertFalse(result['payload_hashes_verified'])
        self.assertEqual(sum(row['native_component_owner'] is not None for row in result['entries']),12)
        self.assertEqual(before,{path:path.read_bytes() for path in self.root.rglob('*') if path.is_file()})

    def test_changed_metadata_payload_and_notice_are_rejected_even_at_equal_size(self):
        for path in (self.directory/'component.json',self.root/'msvcp140_1.dll',self.directory/'NOTICE.txt'):
            before=path.read_bytes();path.write_bytes(b'x'*len(before))
            with self.subTest(path=path),self.assertRaises(ValueError):inspect(self.root,self.notices)
            path.write_bytes(before)

    def test_forged_component_scope_or_approval_is_not_accepted_by_resealing(self):
        original=json.loads(json.dumps(self.component))
        operations=[lambda v:v['dlls'].pop(),lambda v:v['notices'].pop(),
            lambda v:v['dlls'][0].update(path='../private.dll'),lambda v:v['dlls'][0].update(path='python.exe'),
            lambda v:v['dlls'][0].update(sha256='0'*64),lambda v:v['dlls'].__setitem__(0,v['dlls'][1].copy()),
            lambda v:v.update(redistribution_approved=True),lambda v:v.update(version='preview'),
            lambda v:v.update(license_url='https://untrusted.example/terms'),lambda v:v.update(license_document_sha256='b'*64)]
        for operation in operations:
            self.component=json.loads(json.dumps(original));operation(self.component);self.save()
            with self.subTest(operation=operation),self.assertRaises(ValueError):inspect(self.root,self.notices)

    def test_x86_crt_cannot_be_declared_as_a_valid_x64_component(self):
        path=self.root/'msvcp140.dll';data=bytearray(path.read_bytes());struct.pack_into('<H',data,132,0x14c);path.write_bytes(data)
        self.component['dlls']=[entry(self.root/name,name) for name in sorted(CRT_NAMES)];self.save()
        with self.assertRaisesRegex(ValueError,'amd64'):inspect(self.root,self.notices)

    def test_missing_component_marker_is_not_silently_treated_as_no_component(self):
        (self.directory/'component.json').unlink()
        with self.assertRaises(ValueError):inspect(self.root,self.notices)


if __name__=='__main__':unittest.main()
