"""Bounded, read-only PE import/delay-import names; never loads selected code.

Layout reference: https://learn.microsoft.com/en-us/windows/win32/debug/pe-format
This is not Windows loader resolution, a full PE validator, or a license audit.
"""
import os
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from storage_lease import plain_path

MAX_READ=2*1024*1024
MAX_IMPORTS=512
MACHINES={0x8664:'amd64',0x14c:'x86',0xaa64:'arm64'}


def read_imports(path):
    path=plain_path(path)
    stamp=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
    initial=path.stat();used=0
    with path.open('rb') as stream:
        before=os.fstat(stream.fileno())
        def read(offset,count):
            nonlocal used
            if offset<0 or count<0 or offset+count>before.st_size:raise ValueError('PE data outside file')
            used+=count
            if used>MAX_READ:raise ValueError('PE read budget exceeded')
            stream.seek(offset);data=stream.read(count)
            if len(data)!=count:raise ValueError('Truncated PE data')
            return data
        try:
            dos=read(0,64)
            if dos[:2]!=b'MZ':raise ValueError('Missing DOS header')
            offset=struct.unpack_from('<I',dos,60)[0]
            if not 64<=offset<=1024*1024:raise ValueError('PE header offset exceeds limit')
            header=read(offset,24)
            if header[:4]!=b'PE\0\0':raise ValueError('Missing PE signature')
            machine,sections,_,_,_,optional_size,_=struct.unpack_from('<HHIIIHH',header,4)
            if not 1<=sections<=96:raise ValueError('PE section count exceeds limit')
            optional=read(offset+24,optional_size)
            if len(optional)<2:raise ValueError('Missing optional header')
            magic=struct.unpack_from('<H',optional)[0]
            if magic==0x10b:directory_offset=96;image_base_offset=28;image_base_type='<I'
            elif magic==0x20b:directory_offset=112;image_base_offset=24;image_base_type='<Q'
            else:raise ValueError('Unsupported optional header')
            if len(optional)<directory_offset:raise ValueError('Truncated optional header')
            directory_count=struct.unpack_from('<I',optional,directory_offset-4)[0]
            if directory_count>128 or directory_count>(len(optional)-directory_offset)//8:raise ValueError('Invalid PE directory count')
            image_base=struct.unpack_from(image_base_type,optional,image_base_offset)[0]
            headers_size=struct.unpack_from('<I',optional,60)[0]
            raw_sections=read(offset+24+optional_size,sections*40)
            spans=[]
            for number in range(sections):
                virtual_size,rva,raw_size,raw_offset=struct.unpack_from('<IIII',raw_sections,number*40+8)
                if raw_size and raw_offset+raw_size>before.st_size:raise ValueError('PE section outside file')
                spans.append((rva,max(virtual_size,raw_size),raw_offset,raw_size))
            def mapped(rva,count):
                locations=[]
                if rva>=0 and rva+count<=headers_size:locations.append((rva,headers_size-rva))
                for start,virtual_size,raw_offset,raw_size in spans:
                    if start<=rva and rva+count<=start+virtual_size:
                        delta=rva-start
                        if delta+count<=raw_size:locations.append((raw_offset+delta,raw_size-delta))
                if len(locations)!=1:raise ValueError('Unmapped or ambiguous PE RVA')
                return locations[0]
            def read_rva(rva,count):return read(mapped(rva,count)[0],count)
            def dll_name(rva):
                at,available=mapped(rva,1)
                raw=read(at,min(256,available));end=raw.find(b'\0')
                if end<1:raise ValueError('Invalid or unterminated DLL name')
                try:name=raw[:end].decode('ascii')
                except UnicodeError:raise ValueError('Non-ASCII DLL name') from None
                if name in ('.','..') or re.fullmatch(r'[-A-Za-z0-9_.+ ]{1,255}',name) is None:raise ValueError('DLL name is not a basename')
                return name
            def table(index,delayed=False):
                if directory_count<=index:return []
                rva,size=struct.unpack_from('<II',optional,directory_offset+index*8)
                if rva==size==0:return []
                width=32 if delayed else 20
                if not rva or size<width or size>MAX_READ:raise ValueError('Invalid import directory bounds')
                names=[]
                for number in range(min(size//width,MAX_IMPORTS+1)):
                    descriptor=read_rva(rva+number*width,width)
                    if descriptor==bytes(width):return names
                    if len(names)>=MAX_IMPORTS:raise ValueError('Import count exceeds limit')
                    if delayed:
                        flags,name_rva=struct.unpack_from('<II',descriptor)
                        if flags not in (0,1):raise ValueError('Unknown delay-import flags')
                        if flags==0:name_rva-=image_base
                    else:name_rva=struct.unpack_from('<I',descriptor,12)[0]
                    names.append(dll_name(name_rva))
                raise ValueError('Import directory has no terminator')
            result={'machine':MACHINES.get(machine,f'0x{machine:04x}'),'imports':table(1),'delay_imports':table(13,True)}
        finally:
            after=os.fstat(stream.fileno());current=plain_path(path).stat()
            # Keep path creation time and handle change time in their own domains.
            if (stamp(before)!=stamp(after) or stamp(initial)!=stamp(current) or
                    identity(initial)!=identity(before) or identity(after)!=identity(current)):
                raise RuntimeError('Native import source changed')
    result['bytes_read']=used
    return result
