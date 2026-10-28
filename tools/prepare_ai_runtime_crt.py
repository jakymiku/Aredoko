"""Stage an immutable LOCAL TEST pack with a pinned, complete x64 MSVC set.

No download, installer, native execution, registry or existing-pack edits.
Publication/redistribution rights and clean-Windows acceptance remain separate.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tools')]
from ai_runtime import FORMAT,MARKER,LIMIT,files,digest,object_pairs,parse_inventory,inspect_runtime,relative
from storage_lease import plain_path,storage_parent
from package_release import validate_output
from collect_ai_runtime_notices import _read,validate_for_source
from inspect_runtime_native import pe_machine

COMPONENT='THIRD_PARTY_NATIVE_LICENSES/msvc-v14'
CRT_NAMES=frozenset(('concrt140.dll','msvcp140.dll','msvcp140_1.dll','msvcp140_2.dll',
    'msvcp140_atomic_wait.dll','msvcp140_codecvt_ids.dll','vcamp140.dll','vccorlib140.dll',
    'vcomp140.dll','vcruntime140.dll','vcruntime140_1.dll','vcruntime140_threads.dll'))


def _json(path,limit=1024*1024):
    return json.loads(_read(path,limit),object_pairs_hook=object_pairs)


def crt_inputs(directory,inventory,reference,license_document):
    directory=plain_path(directory,directory=True)
    value=_json(inventory);ref=_json(reference)
    if (value.get('format')!='aredoko-msvc-static-source-inventory-v1'
            or ref.get('format')!='aredoko-msvc-source-reference-v1'
            or not re.fullmatch('[0-9a-f]{64}',str(ref.get('sha256','')))
            or value.get('source_sha256')!=ref['sha256']):
        raise ValueError('CRT inventory is not bound to its fixed source')
    if (not isinstance(ref.get('file_version'),str) or re.fullmatch(r'14\.\d+\.\d+\.\d+',ref['file_version']) is None
            or not isinstance(ref.get('official_license_page'),str)
            or urlsplit(ref['official_license_page']).scheme!='https'
            or urlsplit(ref['official_license_page']).netloc!='visualstudio.microsoft.com'):
        raise ValueError('Invalid fixed CRT version or terms source')
    rows=value.get('entries');names=set();paths=set();total=0
    if not isinstance(rows,list) or len(rows)!=len(CRT_NAMES):raise ValueError('Complete x64 CRT set required')
    for row in rows:
        if not isinstance(row,dict):raise ValueError('Invalid pinned x64 CRT member')
        name=row.get('name');key=relative(row.get('path',''));metadata=row.get('metadata',{})
        if (not isinstance(metadata,dict) or not isinstance(name,str) or name not in CRT_NAMES or name in names or '/' in key or key.casefold() in paths
                or type(row.get('bytes')) is not int or not 1<=row['bytes']<=16*1024**2
                or re.fullmatch('[0-9a-f]{64}',str(row.get('sha256',''))) is None
                or row.get('pe_machine')!='amd64' or metadata.get('status')!='Valid'
                or metadata.get('file_version')!=ref.get('file_version')
                or metadata.get('signer_name') not in ('Microsoft Corporation','Microsoft Windows Software Compatibility Publisher')):
            raise ValueError('Invalid pinned x64 CRT member')
        names.add(name);paths.add(key.casefold());total+=row['bytes']
        path=plain_path(directory/key)
        if path.stat().st_size!=row['bytes'] or digest(path)!=row['sha256'] or pe_machine(path)!='amd64':
            raise ValueError('CRT member differs from pinned inventory')
    if names!=CRT_NAMES or total>64*1024**2:raise ValueError('Complete x64 CRT set required')
    if {p.relative_to(directory).as_posix().casefold() for p in files(directory)}!=paths:
        raise ValueError('Unlisted CRT source file')
    document=_read(license_document)
    if hashlib.sha256(document).hexdigest()!=ref.get('license_document_sha256'):
        raise ValueError('CRT license document differs from fixed source')
    return value,ref,document


def license_text(document):
    import io
    with zipfile.ZipFile(io.BytesIO(document)) as archive:
        member=archive.getinfo('word/document.xml')
        if member.file_size>2*1024**2:raise ValueError('License text exceeds limit')
        raw=archive.read(member)
    if b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:raise ValueError('Unexpected license XML declaration')
    root=ET.fromstring(raw);ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    text='\n'.join(''.join(t.text or '' for t in p.findall('.//w:t',ns)) for p in root.findall('.//w:p',ns))
    if not text.strip():raise ValueError('Empty CRT license document')
    return text.encode('utf-8')


def _copy_checked(source,destination,entry,cancelled):
    if cancelled():raise InterruptedError('CRT pack preparation cancelled')
    source=plain_path(source);before=source.stat();storage_parent(destination)
    plain_path(destination,missing=True);hasher=hashlib.sha256();count=0
    with source.open('rb') as incoming,destination.open('xb') as outgoing:
        while block:=incoming.read(1024*1024):
            if cancelled():raise InterruptedError('CRT pack preparation cancelled')
            count+=len(block)
            if count>entry['bytes']:raise ValueError('Runtime source grew during copy')
            hasher.update(block);outgoing.write(block)
    after=plain_path(source).stat()
    stamp=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_nlink)
    if stamp(before)!=stamp(after) or count!=entry['bytes'] or hasher.hexdigest()!=entry['sha256']:
        raise ValueError('Runtime source changed during copy')
    plain_path(destination)


def prepare(source,output,*,crt,inventory,reference,notices,license_document,check=False,
            cancelled=lambda:False,progress=None):
    source=plain_path(source,directory=True);crt=plain_path(crt,directory=True)
    notices=plain_path(notices,directory=True);output=Path(os.path.abspath(output))
    validate_output(output)
    for item in (source,crt,notices,plain_path(inventory),plain_path(reference),plain_path(license_document)):
        if output.is_relative_to(item) or item.is_relative_to(output):raise ValueError('CRT pack output overlaps input')
    raw=_read(source/MARKER,LIMIT);manifest,abi,by_name,checksum=parse_inventory(raw)
    inspect_runtime(source,expected=checksum)
    source_names=set(by_name)
    if {p.relative_to(source).as_posix() for p in files(source,cancelled)}!=source_names|{MARKER}:
        raise ValueError('Unlisted or missing source runtime files')
    if any(key.casefold().startswith(COMPONENT.casefold()+'/') for key in source_names):
        raise ValueError('Select the original pack, not an already supplemented pack')
    validate_for_source(notices,source)
    crt_value,ref,document=crt_inputs(crt,inventory,reference,license_document)
    readable=license_text(document)
    replaced=[e for e in manifest['entries'] if e['path'].casefold() in CRT_NAMES]
    nested=[e['path'] for e in manifest['entries'] if '/' in e['path'] and Path(e['path']).name.casefold() in CRT_NAMES]
    report={'format':'aredoko-local-crt-pack-review-v1','source_manifest_sha256':checksum,
        'crt_source_sha256':ref['sha256'],'crt_version':ref['file_version'],'crt_files':len(CRT_NAMES),
        'replaced_root_files':replaced,'preserved_nested_crt':nested,'prepared':False,
        'source_executed':False,'os_modified':False,'redistribution_approved':False,'clean_windows_verified':False}
    if check:return report
    storage_parent(output);output.mkdir()
    entries=[];copied=0
    def announce(stage):
        if progress is not None:progress({'stage':stage,'files_done':copied,'files_total':len(by_name)})
    def add_bytes(name,data):
        if cancelled():raise InterruptedError('CRT pack preparation cancelled')
        path=output/name;storage_parent(path);plain_path(path,missing=True)
        with path.open('xb') as stream:stream.write(data)
        entries.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    try:
        announce('copying_runtime')
        for entry in manifest['entries']:
            key=entry['path'];path=source/key
            if key.casefold() in CRT_NAMES or key.casefold().startswith('third_party_licenses/'):
                if path.stat().st_size!=entry['bytes'] or digest(path,cancelled)!=entry['sha256']:
                    raise ValueError('Replaced runtime source changed')
            else:
                _copy_checked(path,output/key,entry,cancelled);entries.append(entry.copy())
            copied+=1
            if copied%120==0:announce('copying_runtime')
        for entry in crt_value['entries']:
            destination=entry['name'];_copy_checked(crt/entry['path'],output/destination,entry,cancelled)
            entries.append({'path':destination,'bytes':entry['bytes'],'sha256':entry['sha256']})
        validate_for_source(notices,output)
        for path in files(notices,cancelled):add_bytes('THIRD_PARTY_LICENSES/'+path.relative_to(notices).as_posix(),_read(path))
        add_bytes(COMPONENT+'/runtime-license.docx',document)
        add_bytes(COMPONENT+'/runtime-license.txt',readable)
        notice=('Microsoft Visual C++ v14 runtime '+ref['file_version']+'\n'
            'Unmodified x64 DLL bytes from the pinned Microsoft source.\n'
            'The accompanying DOCX is the original license; TXT is a readable paragraph extraction.\n'
            'Local test candidate only. Redistribution eligibility/terms, updates and clean Windows remain separate.\n'
            'Official terms: '+ref['official_license_page']+'\n'
            'Redistributable list: https://learn.microsoft.com/en-us/visualstudio/releases/2026/redistribution\n')
        add_bytes(COMPONENT+'/NOTICE.txt',notice.encode('utf-8'))
        component={'format':'aredoko-msvc-component-v1','source_sha256':ref['sha256'],
            'version':ref['file_version'],'license_document_sha256':ref['license_document_sha256'],
            'license_url':ref['official_license_page'],'redistribution_approved':False,
            'dlls':[e.copy() for e in entries if e['path'] in CRT_NAMES],
            'notices':[e.copy() for e in entries if e['path'].startswith(COMPONENT+'/')]}
        add_bytes(COMPONENT+'/component.json',json.dumps(component,indent=2).encode('utf-8'))
        if _read(source/MARKER,LIMIT)!=raw or {p.relative_to(source).as_posix() for p in files(source,cancelled)}!=source_names|{MARKER}:
            raise ValueError('Source inventory changed during preparation')
        entries.sort(key=lambda e:e['path'])
        value={'format':FORMAT,'abi':abi,'entries':entries,'files_count':len(entries),'total_bytes':sum(e['bytes'] for e in entries)}
        marker=output/MARKER
        with marker.open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2)
        announce('verifying_output')
        info=inspect_runtime(output,verify=True,cancelled=cancelled,progress=progress)
        return {**report,'prepared':True,'manifest_sha256':info['manifest_sha256'],
                'files_count':len(entries),'total_bytes':value['total_bytes'],'verification':'full'}
    except BaseException:
        # Only our own final marker is removed; keep partial evidence, never delete inputs.
        marker=output/MARKER
        if marker.exists():plain_path(marker).unlink()
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','output','crt','notices','license-document'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--inventory',type=Path,default=ROOT/'docs/msvc-crt-inventory-20261029.json')
    parser.add_argument('--reference',type=Path,default=ROOT/'docs/msvc-runtime-source-20261028.json')
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    last=[-float('inf'),None]
    def progress(value):
        now=time.monotonic();stage=value.get('stage')
        if stage!=last[1] or now-last[0]>=1 or value.get('files_done')==value.get('files_total'):
            print(json.dumps(value),flush=True);last[:]=[now,stage]
    print(json.dumps(prepare(args.source,args.output,crt=args.crt,inventory=args.inventory,reference=args.reference,
        notices=args.notices,license_document=args.license_document,check=args.check,progress=progress),ensure_ascii=False))


if __name__=='__main__':main()
