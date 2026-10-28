"""Generated EXE headers and stub metadata; no installers or trust-store changes."""
import hashlib
import json
from types import SimpleNamespace
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'tools')]
import inspect_msvc_redist as review


class MSVCRedistReviewTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.path=Path(temporary.name)/'generated redist.exe'
        header=bytearray(96);header[:2]=b'MZ';struct.pack_into('<I',header,60,64)
        header[64:68]=b'PE\0\0';struct.pack_into('<H',header,68,0x14c);self.path.write_bytes(header)
        self.info={'status':'Valid','signer_name':'Microsoft Corporation','signer_thumbprint':'A'*40,
            'product_name':'Microsoft Visual C++ v14 Redistributable (x64)','file_description':'Generated fixture',
            'file_version':'14.44.35112.0','product_version':'14.44.35112.0'}
        self.url='https://aka.ms/vc14/vc_redist.x64.exe'

    def test_receipt_records_hash_and_separates_installer_stub_from_payload(self):
        before=self.path.read_bytes()
        with patch.object(review,'metadata',return_value=self.info),patch.object(review.subprocess,'run') as run:
            result=review.inspect(self.path,self.url)
        self.assertEqual(result['sha256'],hashlib.sha256(before).hexdigest());self.assertEqual(result['bytes'],len(before))
        self.assertEqual(result['installer_pe_machine'],'x86');self.assertEqual(self.path.read_bytes(),before)
        self.assertFalse(result['payload_architecture_verified']);self.assertFalse(result['download_origin_verified'])
        self.assertFalse(result['redistribution_approved']);self.assertFalse(result['installer_executed']);run.assert_not_called()

    def test_invalid_signature_or_other_publisher_is_rejected(self):
        for change in ({'status':'UnknownError'},{'status':'HashMismatch'},{'signer_name':'Other Publisher'},{'signer_thumbprint':'bad'}):
            with self.subTest(change=change),patch.object(review,'metadata',return_value={**self.info,**change}),self.assertRaises(ValueError):review.inspect(self.path,self.url)

    def test_architecture_version_and_malformed_metadata_are_rejected(self):
        for change in ({'product_name':'Microsoft Visual C++ (x86)'},{'file_version':'15.0.1.0'},{'product_name':'Other Microsoft application (x64)'},{'file_version':None}):
            with self.subTest(change=change),patch.object(review,'metadata',return_value={**self.info,**change}),self.assertRaises(ValueError):review.inspect(self.path,self.url)

    def test_unsafe_or_non_microsoft_urls_never_read_metadata(self):
        for url in ('http://aka.ms/vc14/x.exe','https://aka.ms.evil.example/x.exe','https://user:pass@aka.ms/a','https://aka.ms/a#fragment','https://aka.ms/a b'):
            with self.subTest(url=url),patch.object(review,'metadata') as metadata,self.assertRaises(ValueError):review.inspect(self.path,url)
            metadata.assert_not_called()

    def test_source_change_during_inspection_is_rejected(self):
        def changed(path):path.write_bytes(path.read_bytes()+b'changed');return self.info
        with patch.object(review,'metadata',side_effect=changed),self.assertRaises(RuntimeError):review.inspect(self.path,self.url)

    def test_windows_metadata_uses_literal_environment_and_inbox_modules(self):
        fake_os=SimpleNamespace(name='nt',environ={'PSModulePath':'incompatible-parent-modules'})
        response=SimpleNamespace(returncode=0,stdout=json.dumps(self.info))
        with patch.object(review,'os',fake_os),patch('prepare_portable.windows_directory',return_value=self.path.parent),patch.object(review.subprocess,'CREATE_NO_WINDOW',0,create=True),patch.object(review.subprocess,'run',return_value=response) as run:
            self.assertEqual(review.metadata(self.path),self.info)
        arguments=run.call_args.args[0];options=run.call_args.kwargs
        self.assertNotIn(str(self.path),arguments);self.assertFalse(options['shell'])
        self.assertIn('-NoProfile',arguments);self.assertEqual(options['env']['AREDOKO_REVIEW_FILE'],str(self.path))
        self.assertNotEqual(options['env']['PSModulePath'],'incompatible-parent-modules')
        self.assertNotIn('ExecutionPolicy',str(arguments))

    def test_size_extension_and_non_pe_are_rejected_before_signature(self):
        for payload,suffix,limit in ((b'not PE','.exe',review.MAX_BYTES),(b'MZ','.dll',review.MAX_BYTES),(self.path.read_bytes(),'.exe',16)):
            with self.subTest(suffix=suffix,limit=limit):
                target=self.path.with_suffix(suffix);target.write_bytes(payload)
                with patch.object(review,'MAX_BYTES',limit),patch.object(review,'metadata') as metadata,self.assertRaises(ValueError):review.inspect(target,self.url)
                metadata.assert_not_called()


if __name__=='__main__':unittest.main()
