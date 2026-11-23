"""Publisher-side generated split transport and v4 catalog bindings."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tools'),str(ROOT/'tests')]
import test_ai_runtime as fixture
from prepare_ai_runtime_archive import prepare_archive
from split_ai_runtime_archive import split_archive,verify_parts
from build_ai_runtime_catalog import build_parts_catalog,write_new


class SplitCatalogTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.base=Path(temporary.name)
        self.pack=fixture.fixture(self.base/'source');self.archive=self.base/'runtime.zip'
        prepare_archive(self.pack,self.archive);self.output=self.base/'parts'
        self.size=self.archive.stat().st_size//2+1
        self.options={'key':'generated-split-runtime','revision':'c'*40,'base_url':'https://example.org/fixed/'+'c'*40,
            'license':'Generated multiple','license_url':'https://example.org/NOTICE','allowed_hosts':['example.org']}

    def split(self,**kwargs):return split_archive(self.archive,self.output,part_bytes=self.size,**kwargs)

    def test_split_catalog_preserves_source_and_binds_ordered_files_without_registration(self):
        before=(self.archive.read_bytes(),self.archive.stat().st_mtime_ns)
        with patch('subprocess.Popen',side_effect=AssertionError('No source code execution')):
            value=self.split();bound,spec=verify_parts(self.output);raw,catalog=build_parts_catalog(self.output,**self.options)
        self.assertEqual(value,bound);self.assertEqual(len(spec.parts),2)
        self.assertEqual(b''.join((self.output/name).read_bytes() for name in spec.parts),before[0])
        self.assertEqual((self.archive.read_bytes(),self.archive.stat().st_mtime_ns),before)
        self.assertEqual(json.loads(raw)['format'],'aredoko-acquisition-v4');self.assertEqual(catalog.runtime_archive,spec)
        self.assertEqual([e.path for e in catalog.entries],list(spec.parts));self.assertEqual(sum(e.size for e in catalog.entries),len(before[0]))
        self.assertEqual(hashlib.sha256(before[0]).hexdigest(),value['archive_sha256'])
        output=self.base/'catalog.json';write_new(raw,output,self.output)
        with self.assertRaises(FileExistsError):write_new(raw,output,self.output)
        with self.assertRaises(ValueError):write_new(raw,self.output/'catalog.json',self.output)

    def test_cancel_keeps_source_and_never_publishes_parts_receipt(self):
        stopped=threading.Event();before=self.archive.read_bytes()
        with self.assertRaises(InterruptedError):self.split(cancelled=stopped.is_set,progress=lambda value:stopped.set())
        self.assertEqual(self.archive.read_bytes(),before);self.assertFalse((self.output/'parts.json').exists())

    def test_invalid_size_existing_output_and_invalid_url_are_refused(self):
        for size in (True,0,2*1024**3,self.archive.stat().st_size):
            with self.subTest(size=size),self.assertRaises(ValueError):split_archive(self.archive,self.output,part_bytes=size)
            self.assertFalse(self.output.exists())
        self.split()
        with self.assertRaises(FileExistsError):self.split()
        for url in ('http://example.org/path','https://user:password@example.org/path','https://example.org/path?token=x'):
            with self.subTest(url=url),self.assertRaises(ValueError):build_parts_catalog(self.output,**{**self.options,'base_url':url})

    def test_changed_part_or_extra_file_never_produces_a_catalog(self):
        self.split();descriptor=json.loads((self.output/'parts.json').read_text());path=self.output/descriptor['entries'][0]['path']
        before=path.read_bytes();path.write_bytes(b'x'*len(before))
        with self.assertRaisesRegex(ValueError,'checksum'):build_parts_catalog(self.output,**self.options)
        path.write_bytes(before);(self.output/'unknown.txt').write_text('keep this file')
        with self.assertRaisesRegex(ValueError,'directory changed'):build_parts_catalog(self.output,**self.options)
        self.assertEqual((self.output/'unknown.txt').read_text(),'keep this file')


if __name__=='__main__':unittest.main()
