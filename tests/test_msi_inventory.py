"""Stub Windows database calls; never install a generated or real MSI."""
import ctypes
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from read_msi_inventory import ReadOnlyMSI,QUERIES


class StubAPI:
    def __init__(self):self.closed=[];self.queries=[];self.calls=[];self.remaining=0
    def MsiOpenDatabaseW(self,path,mode,output):
        self.calls.append(('open',path,mode));output._obj.value=1;return 0
    def MsiDatabaseOpenViewW(self,db,query,output):
        self.queries.append(query);output._obj.value=2;self.remaining=1;return 0
    def MsiViewExecute(self,view,record):self.calls.append(('select',view,record));return 0
    def MsiViewFetch(self,view,output):
        if not self.remaining:return 259
        self.remaining-=1;output._obj.value=3;return 0
    def MsiCloseHandle(self,value):self.closed.append(value);return 0
    def MsiRecordGetInteger(self,record,column):return 1
    def MsiRecordGetStringW(self,record,column,buffer,length):buffer.value='generated';length._obj.value=9;return 0


class MSIInventoryTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.path=Path(temporary.name)/'generated.msi';self.path.write_bytes(bytes.fromhex('d0cf11e0a1b11ae1')+b'generated, not valid MSI')
        self.api=StubAPI();self.reader=ReadOnlyMSI.__new__(ReadOnlyMSI);self.reader.api=self.api

    def test_only_readonly_database_and_fixed_select_queries_are_allowed(self):
        before=self.path.read_bytes();value=self.reader.inspect(self.path)
        self.assertEqual(self.api.calls[0],('open',str(self.path),None))
        self.assertEqual(self.api.queries,[QUERIES[key][0] for key in ('files','media')])
        self.assertEqual(self.api.closed,[3,2,3,2,1]);self.assertTrue(value['read_only'])
        self.assertFalse(value['package_executed']);self.assertFalse(value['installed'])
        self.assertEqual(self.path.read_bytes(),before)

    def test_query_or_field_failure_closes_all_acquired_handles(self):
        for target in ('MsiViewExecute','MsiRecordGetStringW'):
            with self.subTest(target=target):
                self.api.closed=[]
                with patch.object(self.api,target,return_value=1603),self.assertRaises(RuntimeError):self.reader.inspect(self.path)
                self.assertEqual(self.api.closed[-2:],[2,1])
                if target=='MsiRecordGetStringW':self.assertIn(3,self.api.closed)

    def test_bounded_rows_and_fields_reject_malformed_data(self):
        with patch.object(self.api,'MsiRecordGetInteger',return_value=-2147483648),self.assertRaises(ValueError):self.reader.inspect(self.path)
        self.assertEqual(self.api.closed[-3:],[3,2,1])
        with self.assertRaises(KeyError):self.reader.rows(1,'arbitrary SQL')

    def test_bad_magic_or_change_never_produces_a_receipt(self):
        self.path.write_bytes(b'not a database')
        with self.assertRaises(ValueError):self.reader.inspect(self.path)
        self.assertEqual(self.api.calls,[])


if __name__=='__main__':unittest.main()
