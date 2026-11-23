"""Bounded runtime ZIP materialization; never extracts or executes arbitrary code.

Caller supplies a source-owned sealed inventory identity. Outputs are exclusively
new directories, or an explicitly owned acquisition stage with resume=True.
"""
from dataclasses import dataclass
from contextlib import contextmanager
import hashlib,os,re,shutil,stat,zipfile
from pathlib import Path
from ai_runtime import LIMIT,MARKER,digest,files,inspect_runtime,parse_inventory,relative
from storage_lease import plain_path,storage_parent
from runtime_zip_parts import ZIPPartsReader,part_names


@dataclass(frozen=True)
class RuntimeArchive:
    manifest_sha256:str
    unpacked_bytes:int
    unpacked_files:int
    parts:tuple=()

    @classmethod
    def parse(cls,value):
        fields={'manifest_sha256','unpacked_bytes','unpacked_files'}
        if isinstance(value,dict) and 'parts' in value:fields.add('parts')
        if (not isinstance(value,dict) or set(value)!=fields or
                not isinstance(value['manifest_sha256'],str) or re.fullmatch('[0-9a-f]{64}',value['manifest_sha256']) is None or
                type(value['unpacked_bytes']) is not int or not 1<=value['unpacked_bytes']<=64*1024**3 or
                type(value['unpacked_files']) is not int or not 1<=value['unpacked_files']<=100000):
            raise ValueError('Invalid runtime archive binding')
        return cls(value['manifest_sha256'],value['unpacked_bytes'],value['unpacked_files'],part_names(value['parts']) if 'parts' in value else ())

    def to_dict(self):
        result=dict(manifest_sha256=self.manifest_sha256,unpacked_bytes=self.unpacked_bytes,unpacked_files=self.unpacked_files)
        if self.parts:result['parts']=list(self.parts)
        return result


@contextmanager
def _archive_input(path,parts):
    if parts:
        with ZIPPartsReader(path,parts) as stream:
            with zipfile.ZipFile(stream) as archive:yield archive
            stream.validate()
    else:
        path=plain_path(path)
        stamp=lambda:(lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns))(plain_path(path).stat())
        before=stamp()
        with zipfile.ZipFile(path) as archive:yield archive
        if stamp()!=before:raise ValueError('Runtime ZIP changed during validation')


def _members(archive,spec,cancelled):
    members={};folded=set();directories=set();infos=archive.infolist()
    if len(infos)>200001:raise ValueError('Runtime ZIP entry count exceeds limit')
    for info in infos:
        if cancelled():raise InterruptedError('Runtime expansion cancelled')
        if info.orig_filename!=info.filename or info.flag_bits&1 or info.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):
            raise ValueError('Unsupported runtime ZIP member')
        is_dir=info.is_dir();name=relative(info.filename[:-1] if is_dir else info.filename)
        if name.count('/')>31:raise ValueError('Runtime ZIP path depth exceeds limit')
        mode=stat.S_IFMT(info.external_attr>>16)
        if mode not in (0,stat.S_IFDIR if is_dir else stat.S_IFREG) or name.casefold() in folded:
            raise ValueError('Linked or duplicate runtime ZIP member')
        folded.add(name.casefold())
        if is_dir:
            if info.file_size:raise ValueError('Nonempty runtime ZIP directory')
            directories.add(name)
        else:members[name]=info
    # Adjacent segmented paths share every case-insensitive parent group;
    # avoid retaining every prefix of every potentially long archive path.
    named=sorted((*members,*directories),key=lambda name:name.casefold().split('/'))
    for left,right in zip(named,named[1:]):
        for first,second in zip(left.split('/'),right.split('/')):
            if first.casefold()!=second.casefold():break
            if first!=second:raise ValueError('Inconsistent runtime ZIP path case')
    ordered=sorted((key.casefold() for key in members),key=lambda key:key.split('/'))
    if any(right.startswith(left+'/') for left,right in zip(ordered,ordered[1:])):
        raise ValueError('Runtime ZIP path collision')
    if MARKER not in members or members[MARKER].file_size>LIMIT:raise ValueError('Missing bounded runtime ZIP inventory')
    with archive.open(members[MARKER]) as stream:raw=stream.read(LIMIT+1)
    value,abi,expected,_=parse_inventory(raw,expected=spec.manifest_sha256,cancelled=cancelled)
    if (value['total_bytes']!=spec.unpacked_bytes or value['files_count']!=spec.unpacked_files or
            set(members)!=set(expected)|{MARKER}):raise ValueError('Runtime ZIP inventory mismatch')
    for name,entry in expected.items():
        if members[name].file_size!=entry['bytes']:raise ValueError('Runtime ZIP declared size mismatch')
    allowed_dirs={'DLLs'}
    for name in members:
        allowed_dirs.update(parent.as_posix() for parent in Path(name).parents if parent.as_posix()!='.')
    file_names={n.casefold() for n in members}
    if not directories<=allowed_dirs or any(d.casefold() in file_names for d in directories):
        raise ValueError('Unexpected runtime ZIP directory')
    return members,raw,expected


def unpack_runtime(archive_path,output,spec,*,resume=False,cancelled=lambda:False,progress=None):
    if not isinstance(spec,RuntimeArchive):raise ValueError('Source-owned runtime archive binding required')
    RuntimeArchive.parse(spec.to_dict())
    archive_path=plain_path(archive_path,directory=bool(spec.parts));output=Path(os.path.abspath(output))
    if output==archive_path or archive_path.is_relative_to(output) or spec.parts and output.is_relative_to(archive_path):raise ValueError('Runtime ZIP overlaps output')
    if output.exists() and not resume:raise FileExistsError('New runtime expansion output required')
    def check():
        if cancelled():raise InterruptedError('Runtime expansion cancelled')
    check()
    with _archive_input(archive_path,spec.parts) as archive:
        members,raw,expected=_members(archive,spec,cancelled)
        storage_parent(output/'marker');plain_path(output,directory=True)
        existing={p.relative_to(output).as_posix():p.stat().st_size for p in files(output,cancelled)}
        if set(existing)-set(members):
            raise ValueError('Unlisted runtime expansion file')
        remaining=sum(max(0,info.file_size-existing.get(name,0)) for name,info in members.items())
        if shutil.disk_usage(output).free<remaining+16*1024**2:
            raise OSError('Insufficient runtime expansion space')
        completed=received=0
        def report():
            if progress:progress({'files_done':completed,'files_total':len(members),'bytes_done':received,'bytes_total':spec.unpacked_bytes+len(raw)})
        for name,info in members.items():
            check();entry=expected.get(name);size=entry['bytes'] if entry else len(raw);checksum=entry['sha256'] if entry else spec.manifest_sha256
            path=output/name;storage_parent(path);path=plain_path(path,missing=True)
            if path.exists() and path.stat().st_size==size and digest(path,cancelled)==checksum:
                received+=size;completed+=1;report();continue
            if path.exists():path.unlink()  # Only the owned stage's declared ordinary file.
            hasher=hashlib.sha256();written=0
            with archive.open(info) as source,path.open('xb') as destination:
                while True:
                    check();chunk=source.read(min(1024**2,size-written+1))
                    if not chunk:break
                    written+=len(chunk)
                    if written>size:raise ValueError('Runtime ZIP member exceeds inventory')
                    destination.write(chunk);hasher.update(chunk);received+=len(chunk);report()
                destination.flush();os.fsync(destination.fileno())
            if written!=size or hasher.hexdigest()!=checksum:raise ValueError('Runtime ZIP checksum mismatch')
            completed+=1;report()
        storage_parent(output/'DLLs/marker')
        check();info=inspect_runtime(output,expected=spec.manifest_sha256,cancelled=cancelled)
        if {p.relative_to(output).as_posix() for p in files(output,cancelled)}!=set(members):raise ValueError('Runtime expansion inventory changed')
    return {**info,'verification':'expanded_full','archive_executed':False}


def inspect_archive(archive_path,*,cancelled=lambda:False,parts=()):
    """Publisher-side streaming check; returns binding without extraction/imports."""
    parts=part_names(parts) if parts else ()
    with _archive_input(archive_path,parts) as archive:
        marker=archive.getinfo(MARKER)
        if marker.file_size>LIMIT:raise ValueError('Runtime ZIP inventory exceeds limit')
        with archive.open(marker) as stream:raw=stream.read(LIMIT+1)
        value,_,_,checksum=parse_inventory(raw,cancelled=cancelled)
        spec=RuntimeArchive(checksum,value['total_bytes'],value['files_count'],parts)
        members,raw,expected=_members(archive,spec,cancelled)
        for name,info in members.items():
            entry=expected.get(name);size=entry['bytes'] if entry else len(raw);checksum=entry['sha256'] if entry else spec.manifest_sha256
            hasher=hashlib.sha256();received=0
            with archive.open(info) as source:
                while True:
                    if cancelled():raise InterruptedError('Runtime archive validation cancelled')
                    chunk=source.read(min(1024**2,size-received+1))
                    if not chunk:break
                    received+=len(chunk)
                    if received>size:raise ValueError('Runtime ZIP member exceeds inventory')
                    hasher.update(chunk)
            if received!=size or hasher.hexdigest()!=checksum:raise ValueError('Runtime ZIP checksum mismatch')
    return spec
