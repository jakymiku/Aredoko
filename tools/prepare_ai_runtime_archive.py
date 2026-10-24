"""Compress one explicit sealed AI runtime; no download, install, or execution."""
import argparse,hashlib,json,os,sys,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from ai_runtime import MARKER,LIMIT,digest,files,inspect_runtime,parse_inventory
from runtime_archive import RuntimeArchive
from storage_lease import plain_path,storage_parent


def prepare_archive(source,output,*,cancelled=lambda:False,progress=None):
    source=plain_path(source,directory=True);output=Path(os.path.abspath(output))
    if output.is_relative_to(source):raise ValueError('Archive output overlaps sealed runtime')
    if output.exists() or output.is_symlink():raise FileExistsError('New archive output required')
    info=inspect_runtime(source,cancelled=cancelled)
    marker=plain_path(source/MARKER)
    with marker.open('rb') as stream:raw=stream.read(LIMIT+1)
    value,_,expected,checksum=parse_inventory(raw,expected=info['manifest_sha256'],cancelled=cancelled)
    expected={**expected,MARKER:{'path':MARKER,'bytes':len(raw),'sha256':checksum}}
    if {p.relative_to(source).as_posix() for p in files(source,cancelled)}!=set(expected):raise ValueError('Runtime archive source inventory mismatch')
    storage_parent(output)
    received=completed=0
    def stamp(path):
        st=plain_path(path).stat();return st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns
    with output.open('xb') as target,zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,allowZip64=True) as archive:
        for name,entry in expected.items():
            if cancelled():raise InterruptedError('Runtime archive creation cancelled')
            path=plain_path(source/name);before=stamp(path);hasher=hashlib.sha256();written=0
            member=zipfile.ZipInfo(name,(1980,1,1,0,0,0));member.compress_type=zipfile.ZIP_DEFLATED;member.external_attr=0o100644<<16
            with path.open('rb') as original,archive.open(member,'w',force_zip64=True) as destination:
                while True:
                    if cancelled():raise InterruptedError('Runtime archive creation cancelled')
                    chunk=original.read(1024**2)
                    if not chunk:break
                    written+=len(chunk)
                    if written>entry['bytes']:raise ValueError('Runtime archive source grew')
                    destination.write(chunk);hasher.update(chunk);received+=len(chunk)
                    if progress:progress({'bytes_done':received,'bytes_total':value['total_bytes']+len(raw),'files_done':completed,'files_total':len(expected)})
            if written!=entry['bytes'] or hasher.hexdigest()!=entry['sha256'] or stamp(path)!=before:raise ValueError('Runtime archive source changed')
            completed+=1
        if digest(marker,cancelled)!=checksum or {p.relative_to(source).as_posix() for p in files(source,cancelled)}!=set(expected):raise ValueError('Runtime archive source inventory changed')
    return {'archive_bytes':output.stat().st_size,'archive_sha256':digest(output,cancelled),'runtime_archive':RuntimeArchive(checksum,value['total_bytes'],value['files_count']).to_dict(),'executed':False,'uploaded':False,'publisher_reviewed':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    receipt=Path(str(a.output)+'.json')
    if receipt.exists() or receipt.is_symlink():raise FileExistsError('New archive receipt required')
    result=prepare_archive(a.source,a.output)
    plain_path(receipt,missing=True)
    with receipt.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result))


if __name__=='__main__':main()
