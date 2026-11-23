"""A seekable bounded ZIP view over 2–8 immutable transport parts, no join copy."""
import bisect
import io
import os
from pathlib import Path
import re
from ai_runtime import relative
from storage_lease import plain_path

MAX_PART_BYTES=2*1024**3-1
MAX_READ=32*1024**2


def part_names(value):
    if not isinstance(value,(list,tuple)) or not 2<=len(value)<=8:raise ValueError('Two to eight runtime ZIP parts required')
    base=None;names=[]
    for index,name in enumerate(value,1):
        name=relative(name);match=re.fullmatch(r'([^/]+\.zip)\.part([0-9]{3})',name)
        if match is None or len(name)>200 or int(match[2])!=index:raise ValueError('Ordered runtime ZIP part names required')
        if base is None:base=match[1]
        if match[1]!=base:raise ValueError('Runtime ZIP parts must share one base name')
        names.append(name)
    return tuple(names)


def _stamp(info):return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_nlink
def _identity(info):return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_nlink


class ZIPPartsReader(io.RawIOBase):
    def __init__(self,directory,names):
        super().__init__();self._streams=[];self._paths=[];self._path_stamps=[];self._handle_stamps=[]
        self._offsets=[0];self._position=0;directory=plain_path(directory,directory=True)
        try:
            for name in part_names(names):
                path=plain_path(directory/name);before=path.stat()
                if not 1<=before.st_size<=MAX_PART_BYTES:raise ValueError('Runtime ZIP part size exceeds limit')
                stream=path.open('rb');self._streams.append(stream);opened=os.fstat(stream.fileno())
                if _identity(before)!=_identity(opened):raise ValueError('Runtime ZIP part changed before opening')
                self._paths.append(path);self._path_stamps.append(_stamp(before));self._handle_stamps.append(_stamp(opened))
                self._offsets.append(self._offsets[-1]+before.st_size)
        except BaseException:self.close();raise

    def readable(self):return True
    def seekable(self):return True
    def tell(self):self._checkClosed();return self._position
    def seek(self,offset,whence=os.SEEK_SET):
        self._checkClosed()
        if type(offset) is not int or whence not in (os.SEEK_SET,os.SEEK_CUR,os.SEEK_END):raise ValueError('Invalid runtime ZIP seek')
        position=offset+(self._position if whence==os.SEEK_CUR else self._offsets[-1] if whence==os.SEEK_END else 0)
        if position<0:raise OSError('Negative runtime ZIP seek')
        self._position=position;return position
    def read(self,size=-1):
        self._checkClosed()
        if type(size) is not int:raise TypeError('Integer ZIP read size required')
        remaining=max(0,self._offsets[-1]-self._position);size=remaining if size<0 else min(size,remaining)
        if size>MAX_READ:raise ValueError('Runtime ZIP read exceeds buffer limit')
        blocks=[]
        while size:
            index=bisect.bisect_right(self._offsets,self._position)-1
            amount=min(size,self._offsets[index+1]-self._position)
            stream=self._streams[index];stream.seek(self._position-self._offsets[index]);data=stream.read(amount)
            if len(data)!=amount:raise ValueError('Runtime ZIP part changed during reading')
            blocks.append(data);size-=amount;self._position+=amount
        return b''.join(blocks)
    def readinto(self,buffer):
        data=self.read(len(buffer));buffer[:len(data)]=data;return len(data)
    def validate(self):
        self._checkClosed()
        for path,stream,path_stamp,handle_stamp in zip(self._paths,self._streams,self._path_stamps,self._handle_stamps):
            current=plain_path(path).stat();handle=os.fstat(stream.fileno())
            if _stamp(current)!=path_stamp or _stamp(handle)!=handle_stamp or _identity(current)!=_identity(handle):
                raise ValueError('Runtime ZIP part changed during validation')
    def close(self):
        if not self.closed:
            try:
                for stream in self._streams:stream.close()
            finally:super().close()
