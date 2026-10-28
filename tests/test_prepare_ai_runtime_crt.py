"""Generated x64 PE headers, fake license DOCX and sealed packs; no native loads."""
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tools'),str(ROOT/'tests')]
import test_ai_runtime as runtime_fixture
import prepare_ai_runtime_crt as tool
from collect_ai_runtime_notices import write_bundle
from ai_runtime import inspect_runtime,MARKER


def pe():
    data=bytearray(150);data[:2]=b'MZ';struct.pack_into('<I',data,60,128)
    data[128:132]=b'PE\0\0';struct.pack_into('<H',data,132,0x8664);return bytes(data)


class PrepareCRTTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.base=Path(temporary.name)
        self.source=runtime_fixture.fixture(self.base/'source')
        for name in ('vcruntime140.dll','vcruntime140_1.dll','Lib/site-packages/torch/lib/msvcp140.dll'):
            (self.source/name).write_bytes(b'generated old CRT')
        meta=self.source/'Lib/site-packages/demo-1.0.dist-info';meta.mkdir()
        (meta/'METADATA').write_text('Metadata-Version: 2.4\nName: demo\nVersion: 1.0\nLicense-File: LICENSE\n')
        (meta/'LICENSE').write_text('generated distribution license')
        stale=self.source/'THIRD_PARTY_LICENSES';stale.mkdir();(stale/'stale.txt').write_text('old incomplete notices')
        runtime_fixture.seal(self.source)
        self.notices=self.base/'notices';write_bundle(self.source,self.notices)
        self.crt=self.base/'extracted';self.crt.mkdir();self.inventory=self.base/'inventory.json';self.reference=self.base/'reference.json'
        self.license=self.base/'license.docx';payload=io.BytesIO()
        with zipfile.ZipFile(payload,'w') as archive:
            archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Generated license</w:t></w:r></w:p></w:body></w:document>')
        self.license.write_bytes(payload.getvalue());self.output=self.base/'new-pack'
        self.ref={'format':'aredoko-msvc-source-reference-v1','sha256':'c'*64,'file_version':'14.51.36247.0',
            'official_license_page':'https://visualstudio.microsoft.com/license-terms/test/',
            'license_document_sha256':hashlib.sha256(payload.getvalue()).hexdigest()}
        self.value={'format':'aredoko-msvc-static-source-inventory-v1','source_sha256':'c'*64,'entries':[]}
        for name in sorted(tool.CRT_NAMES):
            data=pe();path=self.crt/(name+'_amd64');path.write_bytes(data)
            self.value['entries'].append({'name':name,'path':path.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                'pe_machine':'amd64','metadata':{'file_version':self.ref['file_version'],'status':'Valid',
                    'signer_name':'Microsoft Windows Software Compatibility Publisher'}})
        self.save()

    def save(self):
        self.inventory.write_text(json.dumps(self.value));self.reference.write_text(json.dumps(self.ref))

    def prepare(self,**kwargs):
        return tool.prepare(self.source,self.output,crt=self.crt,inventory=self.inventory,reference=self.reference,
            notices=self.notices,license_document=self.license,**kwargs)

    def snapshot(self):
        return {p.relative_to(self.source).as_posix():(p.stat().st_mtime_ns,p.read_bytes()) for p in self.source.rglob('*') if p.is_file()}

    def test_complete_local_pack_preserves_source_and_wheel_copies_and_binds_notices(self):
        before=self.snapshot()
        with patch('subprocess.Popen',side_effect=AssertionError('No native execution')):result=self.prepare()
        self.assertTrue(result['prepared']);self.assertFalse(result['redistribution_approved']);self.assertFalse(result['clean_windows_verified'])
        self.assertEqual(len(result['replaced_root_files']),2);self.assertEqual(len(result['preserved_nested_crt']),1)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual((self.output/'Lib/site-packages/torch/lib/msvcp140.dll').read_bytes(),b'generated old CRT')
        for name in tool.CRT_NAMES:self.assertEqual((self.output/name).read_bytes(),pe())
        self.assertFalse((self.output/'THIRD_PARTY_LICENSES/stale.txt').exists())
        self.assertEqual(inspect_runtime(self.output,verify=True)['manifest_sha256'],result['manifest_sha256'])
        component=json.loads((self.output/tool.COMPONENT/'component.json').read_text())
        self.assertEqual({x['path'] for x in component['dlls']},tool.CRT_NAMES)
        for entry in component['notices']:
            self.assertEqual(hashlib.sha256((self.output/entry['path']).read_bytes()).hexdigest(),entry['sha256'])
        self.assertEqual((self.output/tool.COMPONENT/'runtime-license.docx').read_bytes(),self.license.read_bytes())
        self.assertEqual((self.output/tool.COMPONENT/'runtime-license.txt').read_text(),'Generated license')

    def test_check_is_read_only_and_does_not_create_output(self):
        before=self.snapshot();result=self.prepare(check=True)
        self.assertFalse(result['prepared']);self.assertFalse(self.output.exists());self.assertEqual(before,self.snapshot())

    def test_tampered_crt_and_license_fail_before_output_creation(self):
        path=self.crt/self.value['entries'][0]['path'];original=path.read_bytes();path.write_bytes(b'x'*len(original))
        with self.assertRaisesRegex(ValueError,'pinned inventory'):self.prepare()
        self.assertFalse(self.output.exists());path.write_bytes(original);self.license.write_bytes(b'wrong license')
        with self.assertRaisesRegex(ValueError,'license document'):self.prepare()
        self.assertFalse(self.output.exists())

    def test_incomplete_wrong_machine_version_signer_and_unsafe_name_are_rejected(self):
        original=json.loads(json.dumps(self.value))
        operations=[lambda v:v['entries'].pop(),lambda v:v['entries'][0].update(pe_machine='arm64'),
            lambda v:v['entries'][0]['metadata'].update(file_version='14.1.1.1'),
            lambda v:v['entries'][0]['metadata'].update(signer_name='Other publisher'),
            lambda v:v['entries'][0].update(path='../outside.dll'),lambda v:v['entries'][0].update(name='python.exe'),
            lambda v:v['entries'].__setitem__(0,v['entries'][1].copy()),lambda v:v.update(source_sha256='a'*64)]
        for operation in operations:
            self.value=json.loads(json.dumps(original));operation(self.value);self.save()
            with self.subTest(operation=operation),self.assertRaises(ValueError):self.prepare()
            self.assertFalse(self.output.exists())

    def test_extra_source_and_unbound_distribution_notices_are_rejected(self):
        extra=self.crt/'unexpected.dll';extra.write_bytes(pe())
        with self.assertRaisesRegex(ValueError,'Unlisted CRT'):self.prepare()
        extra.unlink();(self.source/'Lib/site-packages/demo-1.0.dist-info/LICENSE').write_text('changed notice')
        with self.assertRaisesRegex(ValueError,'Notice source changed'):self.prepare()
        self.assertFalse(self.output.exists())

    def test_output_overlap_or_existing_files_never_get_overwritten(self):
        original=self.output
        for destination in (self.source,self.source/'child',self.crt/'child',self.base):
            self.output=destination
            with self.subTest(destination=destination),self.assertRaises((ValueError,FileExistsError)):self.prepare()
        self.output=original;self.output.mkdir();sentinel=self.output/'keep.txt';sentinel.write_text('keep')
        with self.assertRaises(FileExistsError):self.prepare()
        self.assertEqual(sentinel.read_text(),'keep')

    def test_cancelled_copy_keeps_input_and_never_publishes_a_marker(self):
        before=self.snapshot();stop=[]
        with self.assertRaisesRegex(InterruptedError,'cancelled'):
            self.prepare(cancelled=lambda:bool(stop),progress=lambda value:stop.append(True))
        self.assertEqual(before,self.snapshot());self.assertTrue(self.output.exists());self.assertFalse((self.output/MARKER).exists())

    def test_corrupt_runtime_copy_retains_partial_evidence_without_a_valid_marker(self):
        path=self.source/'Lib/site-packages/torch/lib/generated.dll';path.write_bytes(b'bad source')
        with self.assertRaisesRegex(ValueError,'source (grew|changed)'):self.prepare()
        self.assertTrue(self.output.exists());self.assertFalse((self.output/MARKER).exists())

    def test_license_xml_entities_are_not_expanded(self):
        payload=io.BytesIO()
        with zipfile.ZipFile(payload,'w') as archive:archive.writestr('word/document.xml','<!DOCTYPE x [<!ENTITY e "unexpected">]><x>&e;</x>')
        with self.assertRaisesRegex(ValueError,'XML declaration'):tool.license_text(payload.getvalue())

    def test_failed_final_verification_removes_only_the_new_marker(self):
        original=tool.inspect_runtime;before=self.snapshot()
        def verify(root,**kwargs):
            if kwargs.get('verify'):raise ValueError('Generated final verification failure')
            return original(root,**kwargs)
        with patch.object(tool,'inspect_runtime',side_effect=verify),self.assertRaisesRegex(ValueError,'final verification'):
            self.prepare()
        self.assertFalse((self.output/MARKER).exists());self.assertTrue((self.output/'python.exe').is_file())
        self.assertEqual(before,self.snapshot())


if __name__=='__main__':unittest.main()
