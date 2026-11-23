"""Split a verified ZIP for transport; no recompression, execution or publishing."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tools')]
from ai_runtime import object_pairs,files
from runtime_archive import inspect_archive,RuntimeArchive
from runtime_zip_parts import MAX_PART_BYTES,part_names
from storage_lease import plain_path,storage_parent
from package_release import validate_output
from collect_ai_runtime_notices import _read


def stamp(path):
    s=plain_path(path).stat();return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns


def split_archive(source,output,*,part_bytes=1_900_000_000,cancelled=lambda:False,progress=None):
    source=plain_path(source);output=Path(os.path.abspath(output));validate_output(output)
    if source.is_relative_to(output):raise ValueError('Parts output overlaps source')
    if type(part_bytes) is not int or not 1<=part_bytes<=MAX_PART_BYTES:raise ValueError('Invalid runtime part size')
    before=stamp(source);count=math.ceil(before[2]/part_bytes)
    if not 2<=count<=8:raise ValueError('Choose two to eight parts, or keep the existing single ZIP')
    names=part_names([source.name+f'.part{i:03}' for i in range(1,count+1)])
    spec=inspect_archive(source,cancelled=cancelled)
    storage_parent(output);output.mkdir();entries=[];whole=hashlib.sha256();done=0
    with source.open('rb') as incoming:
        for name in names:
            hasher=hashlib.sha256();written=0;destination=output/name;plain_path(destination,missing=True)
            with destination.open('xb') as outgoing:
                while written<part_bytes:
                    if cancelled():raise InterruptedError('Runtime ZIP split cancelled')
                    block=incoming.read(min(1024**2,part_bytes-written))
                    if not block:break
                    outgoing.write(block);hasher.update(block);whole.update(block);written+=len(block);done+=len(block)
                    if progress:progress({'bytes_done':done,'bytes_total':before[2],'parts_done':len(entries),'parts_total':count})
                outgoing.flush();os.fsync(outgoing.fileno())
            if not written:raise ValueError('Runtime ZIP source changed during split')
            entries.append({'path':name,'bytes':written,'sha256':hasher.hexdigest()})
        if incoming.read(1) or done!=before[2] or stamp(source)!=before:raise ValueError('Runtime ZIP source changed during split')
    result={'format':'aredoko-runtime-parts-v1','archive_bytes':done,'archive_sha256':whole.hexdigest(),
        'runtime_archive':RuntimeArchive(spec.manifest_sha256,spec.unpacked_bytes,spec.unpacked_files,names).to_dict(),'entries':entries}
    if cancelled():raise InterruptedError('Runtime ZIP split cancelled')
    with (output/'parts.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    return result


def verify_parts(directory,*,cancelled=lambda:False):
    directory=plain_path(directory,directory=True);raw=_read(directory/'parts.json',65536)
    value=json.loads(raw,object_pairs_hook=object_pairs)
    if not isinstance(value,dict) or set(value)!={'format','archive_bytes','archive_sha256','runtime_archive','entries'} or value['format']!='aredoko-runtime-parts-v1':
        raise ValueError('Invalid runtime parts receipt')
    spec=RuntimeArchive.parse(value['runtime_archive']);rows=value['entries']
    if (not spec.parts or not isinstance(rows,list) or len(rows)!=len(spec.parts) or type(value['archive_bytes']) is not int
            or not isinstance(value['archive_sha256'],str) or re.fullmatch('[0-9a-f]{64}',value['archive_sha256']) is None):
        raise ValueError('Incomplete runtime parts receipt')
    total=0;whole=hashlib.sha256()
    for expected,row in zip(spec.parts,rows):
        if (not isinstance(row,dict) or set(row)!={'path','bytes','sha256'} or row['path']!=expected
                or type(row['bytes']) is not int or not 1<=row['bytes']<=MAX_PART_BYTES
                or not isinstance(row['sha256'],str) or re.fullmatch('[0-9a-f]{64}',row['sha256']) is None):
            raise ValueError('Invalid runtime ZIP part receipt')
        path=plain_path(directory/expected);before=stamp(path);hasher=hashlib.sha256();count=0
        with path.open('rb') as stream:
            while block:=stream.read(1024**2):
                if cancelled():raise InterruptedError('Runtime parts verification cancelled')
                count+=len(block)
                if count>row['bytes']:raise ValueError('Runtime ZIP part grew')
                hasher.update(block);whole.update(block)
        if count!=row['bytes'] or hasher.hexdigest()!=row['sha256'] or stamp(path)!=before:raise ValueError('Runtime ZIP part checksum mismatch')
        total+=count
    if total!=value['archive_bytes'] or whole.hexdigest()!=value['archive_sha256']:raise ValueError('Runtime ZIP concatenation binding differs')
    if inspect_archive(directory,parts=spec.parts,cancelled=cancelled)!=spec:raise ValueError('Runtime parts inventory differs')
    if (_read(directory/'parts.json',65536)!=raw
            or {p.relative_to(directory).as_posix() for p in files(directory,cancelled)}!=set(spec.parts)|{'parts.json'}):
        raise ValueError('Runtime parts directory changed')
    return value,spec


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--part-bytes',type=int,default=1_900_000_000);args=parser.parse_args()
    value=split_archive(args.archive,args.output,part_bytes=args.part_bytes);verify_parts(args.output)
    print(json.dumps({'pass':True,'bytes':value['archive_bytes'],'parts':len(value['entries']),'uploaded':False,'registered':False}))


if __name__=='__main__':main()
