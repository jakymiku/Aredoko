"""Read bounded WiX Burn v2 container spans; never execute or extract the EXE.

Format reference (not a code dependency):
https://github.com/wixtoolset/wix3/blob/develop/src/burn/engine/section.cpp
Only complete Cabinet containers with non-overlapping ranges are accepted.
"""
import os
from pathlib import Path
import struct
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from storage_lease import plain_path

MAX_BYTES=96*1024*1024


def containers(path):
    path=plain_path(path);initial=path.stat()
    stamp=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
    if not 64<=initial.st_size<=MAX_BYTES:raise ValueError('Bundle size exceeds review limit')
    with path.open('rb') as stream:
        before=os.fstat(stream.fileno())
        def read(at,count):
            if at<0 or count<0 or at+count>before.st_size:raise ValueError('Bundle structure outside source')
            stream.seek(at);raw=stream.read(count)
            if len(raw)!=count:raise ValueError('Truncated bundle structure')
            return raw
        dos=read(0,64)
        if dos[:2]!=b'MZ':raise ValueError('Missing bundle DOS header')
        pe=struct.unpack_from('<I',dos,60)[0]
        if not 64<=pe<=1024*1024:raise ValueError('Bundle PE offset exceeds limit')
        header=read(pe,24)
        if header[:4]!=b'PE\0\0':raise ValueError('Missing bundle PE header')
        count=struct.unpack_from('<H',header,6)[0];optional_size=struct.unpack_from('<H',header,20)[0]
        if not 1<=count<=96 or optional_size>4096:raise ValueError('Bundle PE table exceeds limit')
        optional=read(pe+24,optional_size)
        magic=struct.unpack_from('<H',optional)[0] if len(optional)>=2 else None
        directory_at=96 if magic==0x10b else 112 if magic==0x20b else None
        if directory_at is None or len(optional)<directory_at+40:raise ValueError('Missing bundle security directory')
        if struct.unpack_from('<I',optional,directory_at-4)[0]<5:raise ValueError('Missing bundle directory count')
        signature_at,signature_size=struct.unpack_from('<II',optional,directory_at+32)
        table=read(pe+24+optional_size,count*40);burn=[];section_end=pe+24+optional_size+count*40
        for i in range(count):
            row=table[i*40:(i+1)*40];size,at=struct.unpack_from('<II',row,16)
            if size and (at<section_end or at+size>before.st_size):raise ValueError('Invalid bundle section span')
            section_end=max(section_end,at+size)
            if row[:8]==b'.wixburn':burn.append((at,size))
        if len(burn)!=1:raise ValueError('Expected one Burn section')
        at,size=burn[0]
        if not 52<=size<=4096:raise ValueError('Invalid Burn section size')
        raw=read(at,size)
        magic,version=struct.unpack_from('<II',raw)
        stub,_,original_at,original_size,kind,count=struct.unpack_from('<6I',raw,24)
        if magic!=0x00f14300 or version!=2 or kind!=1 or not 1<=count<=116 or 48+count*4>size:
            raise ValueError('Unsupported Burn container format')
        sizes=struct.unpack_from('<'+str(count)+'I',raw,48)
        if stub<section_end or any(not 36<=length<=MAX_BYTES for length in sizes):raise ValueError('Invalid Burn container bounds')
        if bool(original_at)!=bool(original_size) or bool(signature_at)!=bool(signature_size):raise ValueError('Incomplete bundle signature span')
        engine_end=original_at+original_size if original_at else signature_at+signature_size if signature_at else stub+sizes[0]
        ux_end=stub+sizes[0]
        if not ux_end<=engine_end<=before.st_size:raise ValueError('Invalid Burn engine boundary')
        if original_at and (original_at<ux_end or original_at+original_size>before.st_size):raise ValueError('Invalid original signature span')
        if signature_at and (signature_at<ux_end or signature_at+signature_size>before.st_size):raise ValueError('Invalid final signature span')
        result=[];next_at=engine_end
        for index,length in enumerate(sizes):
            location=stub if index==0 else next_at
            if location+length>before.st_size:raise ValueError('Attached bundle container is incomplete')
            # A new outer Authenticode signature must not overlap any container.
            if signature_at and location<signature_at+signature_size and signature_at<location+length:
                raise ValueError('Bundle signature overlaps a container')
            cab=read(location,36)
            if cab[:4]!=b'MSCF' or struct.unpack_from('<I',cab,8)[0]!=length:raise ValueError('Burn container is not an exact Cabinet')
            result.append({'index':index,'offset':location,'bytes':length})
            if index:next_at+=length
        after=os.fstat(stream.fileno())
    current=plain_path(path).stat()
    if stamp(initial)!=stamp(current) or stamp(before)!=stamp(after) or identity(initial)!=identity(before):raise RuntimeError('Bundle changed during review')
    return result
