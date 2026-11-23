"""Generated PE bytes only; no executable is loaded or run."""
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tools')]
from pe_imports import read_imports


def image(*,bits=64,imports=('native.dll',),delayed=('optional.dll',),legacy_delay=False):
    data=bytearray(0xc00);data[:2]=b'MZ';struct.pack_into('<I',data,60,0x80);data[0x80:0x84]=b'PE\0\0'
    optional_size=240 if bits==64 else 224
    struct.pack_into('<HHIIIHH',data,0x84,0x8664 if bits==64 else 0x14c,1,0,0,0,optional_size,0)
    optional=0x98;directory=optional+(112 if bits==64 else 96)
    struct.pack_into('<H',data,optional,0x20b if bits==64 else 0x10b)
    base=0x140000000 if bits==64 else 0x400000
    struct.pack_into('<Q' if bits==64 else '<I',data,optional+(24 if bits==64 else 28),base)
    struct.pack_into('<I',data,optional+60,0x400);struct.pack_into('<I',data,directory-4,16)
    section=optional+optional_size;data[section:section+8]=b'.rdata\0\0'
    struct.pack_into('<IIII',data,section+8,0x800,0x1000,0x800,0x400)
    name_offset=0x800
    for kind,names,descriptor_offset,rva,width,index in (
        ('imports',imports,0x400,0x1000,20,1),('delay',delayed,0x600,0x1200,32,13)):
        if not names:continue
        struct.pack_into('<II',data,directory+8*index,rva,(len(names)+1)*width)
        for number,name in enumerate(names):
            encoded=name.encode('ascii')+b'\0';data[name_offset:name_offset+len(encoded)]=encoded
            name_rva=name_offset-0x400+0x1000
            if kind=='imports':struct.pack_into('<I',data,descriptor_offset+number*width+12,name_rva)
            else:struct.pack_into('<II',data,descriptor_offset+number*width,0 if legacy_delay else 1,name_rva+(base if legacy_delay else 0))
            name_offset+=len(encoded)
    return data


class PEImportTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.path=Path(temporary.name)/'generated.dll'
    def parse(self,data):self.path.write_bytes(data);return read_imports(self.path)

    def test_pe32_and_pe32plus_normal_and_delay_names_without_execution(self):
        for bits,machine in ((32,'x86'),(64,'amd64')):
            with self.subTest(bits=bits),patch('subprocess.Popen',side_effect=AssertionError('No execution')):
                value=self.parse(image(bits=bits,imports=('native.dll','KERNEL32.dll'),delayed=('optional.dll',)))
                self.assertEqual(value['machine'],machine);self.assertEqual(value['imports'],['native.dll','KERNEL32.dll'])
                self.assertEqual(value['delay_imports'],['optional.dll']);self.assertLess(value['bytes_read'],8192)

    def test_legacy_delay_uses_va_instead_of_rva(self):
        self.assertEqual(self.parse(image(bits=32,legacy_delay=True))['delay_imports'],['optional.dll'])

    def test_no_imports_is_explicit_for_a_valid_image(self):
        value=self.parse(image(imports=(),delayed=()));self.assertEqual(value['imports'],[]);self.assertEqual(value['delay_imports'],[])

    def test_directory_count_and_truncated_headers_are_rejected(self):
        bad=image();struct.pack_into('<I',bad,0x98+108,17)
        for data in (bad,image()[:100],b'not PE',image()[:0x99]):
            with self.subTest(size=len(data)),self.assertRaises(ValueError):self.parse(data)

    def test_unmapped_and_virtual_only_name_rvas_are_not_read(self):
        for name_rva in (0x3000,0xffffffff):
            data=image();struct.pack_into('<I',data,0x400+12,name_rva)
            with self.subTest(rva=name_rva),self.assertRaisesRegex(ValueError,'RVA'):self.parse(data)
        data=image();section=0x98+240;struct.pack_into('<I',data,section+8,0x1000);struct.pack_into('<I',data,0x400+12,0x1900)
        with self.assertRaisesRegex(ValueError,'RVA'):self.parse(data)

    def test_path_names_and_missing_name_terminator_are_rejected(self):
        for name in ('../outside.dll','C:\\private.dll','network/name.dll'):
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'basename'):self.parse(image(imports=(name,)))
        data=image(delayed=());data[0x800:0x900]=b'A'*256
        with self.assertRaisesRegex(ValueError,'unterminated'):self.parse(data)

    def test_directory_requires_terminator_and_known_delay_flags(self):
        data=image();struct.pack_into('<I',data,0x98+112+8+4,20)
        with self.assertRaisesRegex(ValueError,'terminator'):self.parse(data)
        data=image();struct.pack_into('<I',data,0x600,2)
        with self.assertRaisesRegex(ValueError,'delay-import flags'):self.parse(data)

    def test_overlapping_rvas_are_not_silently_resolved(self):
        data=image();struct.pack_into('<H',data,0x86,2);section=0x98+240
        data[section+40:section+80]=data[section:section+40]
        with self.assertRaisesRegex(ValueError,'ambiguous'):self.parse(data)

    def test_file_and_handle_clock_domains_preserve_source_but_reject_changes(self):
        self.path.write_bytes(image());before=(self.path.read_bytes(),self.path.stat().st_mtime_ns);info=self.path.stat()
        handle=types.SimpleNamespace(**{name:getattr(info,name) for name in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')});handle.st_ctime_ns+=100
        with patch('pe_imports.os.fstat',return_value=handle):read_imports(self.path)
        self.assertEqual(before,(self.path.read_bytes(),self.path.stat().st_mtime_ns))
        changed=types.SimpleNamespace(**{**vars(handle),'st_ctime_ns':handle.st_ctime_ns+1})
        with patch('pe_imports.os.fstat',side_effect=[handle,changed]),self.assertRaisesRegex(RuntimeError,'source changed'):read_imports(self.path)


if __name__=='__main__':unittest.main()
