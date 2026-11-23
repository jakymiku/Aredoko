"""Read File/Media tables through Windows Installer's READONLY database API.

Does not call MsiInstallProduct, MsiOpenPackage, actions, transforms, commit,
msiexec, or any executable in the selected package. No MSI stream extraction.
https://learn.microsoft.com/windows/win32/api/msiquery/nf-msiquery-msiopendatabasew
"""
from contextlib import contextmanager
import ctypes
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from storage_lease import plain_path

QUERIES={
    'files':('SELECT `File`, `FileName`, `FileSize`, `Version`, `Sequence` FROM `File`',
             ('id','name','bytes','version','sequence'),(False,False,True,False,True)),
    'media':('SELECT `DiskId`, `LastSequence`, `Cabinet` FROM `Media`',
             ('disk','last_sequence','cabinet'),(True,True,False)),
}


class ReadOnlyMSI:
    def __init__(self):
        if os.name!='nt':raise RuntimeError('MSI table inspection requires Windows')
        from prepare_portable import windows_directory
        self.api=ctypes.WinDLL(str(windows_directory()/'System32/msi.dll'))
        uint=ctypes.c_uint;handle=ctypes.POINTER(uint);wide=ctypes.c_wchar_p
        for name,args in (
            ('MsiOpenDatabaseW',[wide,wide,handle]),('MsiDatabaseOpenViewW',[uint,wide,handle]),
            ('MsiViewExecute',[uint,uint]),('MsiViewFetch',[uint,handle]),('MsiCloseHandle',[uint]),
            ('MsiRecordGetStringW',[uint,uint,wide,ctypes.POINTER(ctypes.c_ulong)])):
            method=getattr(self.api,name);method.argtypes=args;method.restype=uint
        self.api.MsiRecordGetInteger.argtypes=[uint,uint];self.api.MsiRecordGetInteger.restype=ctypes.c_int

    @staticmethod
    def checked(code):
        if code:raise RuntimeError('Read-only MSI table access failed: '+str(code))

    @contextmanager
    def owned(self,method,*arguments):
        value=ctypes.c_uint();code=method(*arguments,ctypes.byref(value))
        try:
            self.checked(code)
            if not value.value:raise RuntimeError('Missing read-only MSI handle')
            yield value.value
        finally:
            if value.value:self.api.MsiCloseHandle(value.value)

    def rows(self,database,key):
        query,fields,numeric=QUERIES[key];result=[]
        with self.owned(self.api.MsiDatabaseOpenViewW,database,query) as view:
            self.checked(self.api.MsiViewExecute(view,0))
            while True:
                record=ctypes.c_uint();code=self.api.MsiViewFetch(view,ctypes.byref(record))
                try:
                    if code==259:break  # ERROR_NO_MORE_ITEMS
                    self.checked(code)
                    if not record.value:raise RuntimeError('Missing MSI record')
                    if len(result)>=2048:raise ValueError('MSI row count exceeds review limit')
                    row={}
                    for column,(field,integer) in enumerate(zip(fields,numeric),1):
                        if integer:
                            value=self.api.MsiRecordGetInteger(record.value,column)
                            if value<0:raise ValueError('Invalid MSI inventory number')
                        else:
                            buffer=ctypes.create_unicode_buffer(4097);length=ctypes.c_ulong(4097)
                            self.checked(self.api.MsiRecordGetStringW(record.value,column,buffer,ctypes.byref(length)))
                            if length.value>4096:raise ValueError('MSI field exceeds review limit')
                            value=buffer.value
                        row[field]=value
                    result.append(row)
                finally:
                    if record.value:self.api.MsiCloseHandle(record.value)
        return result

    def inspect(self,path):
        path=plain_path(path);initial=path.stat()
        stamp=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if not 8<=initial.st_size<=64*1024*1024:raise ValueError('MSI size exceeds review limit')
        with path.open('rb') as stream:
            if stream.read(8)!=bytes.fromhex('d0cf11e0a1b11ae1'):raise ValueError('Expected an MSI compound database')
        # A null persist argument is MSIDBOPEN_READONLY (zero), never direct or
        # transact. Only the two constant SELECTs above can reach the engine.
        with self.owned(self.api.MsiOpenDatabaseW,str(path),None) as database:
            value={key:self.rows(database,key) for key in QUERIES}
        if stamp(initial)!=stamp(plain_path(path).stat()):raise RuntimeError('MSI changed during review')
        return {'format':'aredoko-msi-file-review-v1',**value,'read_only':True,'package_executed':False,'installed':False}
