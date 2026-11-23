"""Prepare a draft trusted catalog from one explicit sealed runtime pack.

No downloads, uploads, execution, registration, or source changes. Publisher
origin, revision and license/NOTICE must still be reviewed before shipping.
"""
import argparse,hashlib,json,os,sys
from pathlib import Path
from urllib.parse import quote,urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from ai_runtime import MARKER,LIMIT,inspect_runtime,files,object_pairs,digest
from ai_acquisition import Catalog
from runtime_archive import inspect_archive
from storage_lease import plain_path,storage_parent


def build_catalog(root,*,key,revision,base_url,license,license_url,allowed_hosts,cancelled=lambda:False):
    root=plain_path(root,directory=True)
    if not isinstance(base_url,str) or any(c.isspace() for c in base_url):raise ValueError('Explicit HTTPS artifact base required')
    location=urlsplit(base_url)
    if location.scheme!='https' or not location.hostname or location.query or location.fragment or location.username or location.password:raise ValueError('Explicit HTTPS artifact base required')
    info=inspect_runtime(root,verify=True,cancelled=cancelled)
    # Full validation already read every artifact. Reuse its verified inventory
    # instead of hashing all PyTorch files a second time just to build JSON.
    with (root/MARKER).open('rb') as stream:raw=stream.read(LIMIT+1)
    if len(raw)>LIMIT or hashlib.sha256(raw).hexdigest()!=info['manifest_sha256']:raise ValueError('Runtime inventory changed')
    inventory=json.loads(raw,object_pairs_hook=object_pairs)
    inputs=[*inventory['entries'],{'path':MARKER,'bytes':len(raw),'sha256':info['manifest_sha256']}]
    value={'format':'aredoko-acquisition-v1','id':key,'revision':revision,'kind':'runtime','license':license,'license_url':license_url,'allowed_hosts':list(allowed_hosts),'entries':[]}
    for entry in inputs:
        if cancelled():raise InterruptedError('Catalog preparation cancelled')
        name=entry['path'];leaf=Path(name).name.upper()
        role='inventory' if name==MARKER else 'license' if leaf.startswith(('LICENSE','COPYING','NOTICE')) else 'runtime'
        value['entries'].append({'path':name,'url':base_url.rstrip('/')+'/'+quote(name,safe='/'),'bytes':entry['bytes'],'sha256':entry['sha256'],'role':role})
    document=json.dumps(value,ensure_ascii=False,indent=2).encode('utf-8')
    catalog=Catalog.parse(document)
    if {p.relative_to(root).as_posix() for p in files(root,cancelled)}!={entry['path'] for entry in inputs}:raise ValueError('Runtime inventory changed')
    if cancelled():raise InterruptedError('Catalog preparation cancelled')
    return document,catalog


def build_archive_catalog(archive,*,key,revision,base_url,license,license_url,allowed_hosts,cancelled=lambda:False):
    archive=plain_path(archive)
    if not isinstance(base_url,str) or any(c.isspace() for c in base_url):raise ValueError('Explicit HTTPS artifact base required')
    location=urlsplit(base_url)
    if location.scheme!='https' or not location.hostname or location.query or location.fragment or location.username or location.password:raise ValueError('Explicit HTTPS artifact base required')
    spec=inspect_archive(archive,cancelled=cancelled)
    value={'format':'aredoko-acquisition-v3','id':key,'revision':revision,'kind':'runtime','license':license,'license_url':license_url,'allowed_hosts':list(allowed_hosts),'runtime_archive':spec.to_dict(),
           'entries':[{'path':archive.name,'url':base_url.rstrip('/')+'/'+quote(archive.name,safe=''),'bytes':archive.stat().st_size,'sha256':digest(archive,cancelled),'role':'archive'}]}
    raw=json.dumps(value,ensure_ascii=False,indent=2).encode('utf-8');return raw,Catalog.parse(raw)


def build_parts_catalog(directory,*,key,revision,base_url,license,license_url,allowed_hosts,cancelled=lambda:False):
    from split_ai_runtime_archive import verify_parts
    if not isinstance(base_url,str) or any(c.isspace() for c in base_url):raise ValueError('Explicit HTTPS artifact base required')
    location=urlsplit(base_url)
    if location.scheme!='https' or not location.hostname or location.query or location.fragment or location.username or location.password:raise ValueError('Explicit HTTPS artifact base required')
    value,spec=verify_parts(directory,cancelled=cancelled)
    document={'format':'aredoko-acquisition-v4','id':key,'revision':revision,'kind':'runtime','license':license,
        'license_url':license_url,'allowed_hosts':list(allowed_hosts),'runtime_archive':spec.to_dict(),
        'entries':[{**entry,'url':base_url.rstrip('/')+'/'+quote(entry['path'],safe=''),'role':'archive'} for entry in value['entries']]}
    raw=json.dumps(document,ensure_ascii=False,indent=2).encode('utf-8');return raw,Catalog.parse(raw)


def write_new(document,output,root):
    output=Path(os.path.abspath(output));root=plain_path(root,directory=True)
    if output.is_relative_to(root):raise ValueError('Catalog output must stay outside the runtime pack')
    storage_parent(output);plain_path(output,missing=True)
    # Exclusive creation, including a final concurrent-existence check by OS.
    # A partial failed output is evidence, never automatically registered.
    with output.open('xb') as stream:stream.write(document);stream.flush();os.fsync(stream.fileno())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True);source.add_argument('--runtime-root',type=Path);source.add_argument('--archive-path',type=Path);source.add_argument('--parts-directory',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    for field in ('id','revision','base-url','license','license-url'):parser.add_argument('--'+field,required=True)
    parser.add_argument('--allow-host',action='append',required=True)
    args=parser.parse_args()
    selected=args.parts_directory if args.parts_directory is not None else args.archive_path if args.archive_path is not None else args.runtime_root
    build=build_parts_catalog if args.parts_directory is not None else build_archive_catalog if args.archive_path is not None else build_catalog
    document,catalog=build(selected,key=args.id,revision=args.revision,base_url=args.base_url,license=args.license,license_url=args.license_url,allowed_hosts=args.allow_host)
    if args.archive_path is not None:
        if Path(os.path.abspath(args.output))==selected.absolute():raise ValueError('Catalog overlaps runtime ZIP')
        storage_parent(args.output)
        with Path(args.output).open('xb') as stream:stream.write(document);stream.flush();os.fsync(stream.fileno())
    else:write_new(document,args.output,selected)
    print(json.dumps({'catalog_id':catalog.fingerprint,'files':len(catalog.entries),'bytes':sum(item.size for item in catalog.entries),'registered':False,'downloaded':False,'inference_verified':False}))

if __name__=='__main__':main()
