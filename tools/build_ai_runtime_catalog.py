"""Prepare a draft trusted catalog from one explicit sealed runtime pack.

No downloads, uploads, execution, registration, or source changes. Publisher
origin, revision and license/NOTICE must still be reviewed before shipping.
"""
import argparse,hashlib,json,os,sys
from pathlib import Path
from urllib.parse import quote,urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from ai_runtime import MARKER,LIMIT,inspect_runtime,files,object_pairs
from ai_acquisition import Catalog
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


def write_new(document,output,root):
    output=Path(os.path.abspath(output));root=plain_path(root,directory=True)
    if output.is_relative_to(root):raise ValueError('Catalog output must stay outside the runtime pack')
    storage_parent(output);plain_path(output,missing=True)
    # Exclusive creation, including a final concurrent-existence check by OS.
    # A partial failed output is evidence, never automatically registered.
    with output.open('xb') as stream:stream.write(document);stream.flush();os.fsync(stream.fileno())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    for field in ('id','revision','base-url','license','license-url'):parser.add_argument('--'+field,required=True)
    parser.add_argument('--allow-host',action='append',required=True)
    args=parser.parse_args()
    document,catalog=build_catalog(args.runtime_root,key=args.id,revision=args.revision,base_url=args.base_url,license=args.license,license_url=args.license_url,allowed_hosts=args.allow_host)
    write_new(document,args.output,args.runtime_root)
    print(json.dumps({'catalog_id':catalog.fingerprint,'files':len(catalog.entries),'bytes':sum(item.size for item in catalog.entries),'registered':False,'downloaded':False,'inference_verified':False}))

if __name__=='__main__':main()
