"""Add fixed native notice bindings to a NEW local runtime; never execute or publish it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tools')]
from ai_runtime import FORMAT,MARKER,LIMIT,files,parse_inventory,inspect_runtime,object_pairs
from storage_lease import plain_path,storage_parent
from package_release import validate_output
from collect_ai_runtime_notices import _read
from prepare_ai_runtime_crt import _copy_checked
from inspect_runtime_native import pe_machine
from cpython_component_contract import COMPONENT,NATIVE_NAMES,SOURCE_NAMES,validate_sources,validate_component,notice_bindings,validate_reference


def prepare(source,output,*,notices,reference,check=False,cancelled=lambda:False,progress=None):
    source=plain_path(source,directory=True);notices=plain_path(notices,directory=True);reference=plain_path(reference)
    output=Path(os.path.abspath(output));validate_output(output)
    for path in (source,notices,reference):
        if output.is_relative_to(path) or path.is_relative_to(output):raise ValueError('CPython output overlaps input')
    raw=_read(source/MARKER,LIMIT);manifest,abi,declared,parent_sha=parse_inventory(raw)
    inspect_runtime(source,expected=parent_sha)
    if abi['python']!='3.11' or any(n.casefold().startswith(COMPONENT.casefold()+'/') for n in declared):raise ValueError('Original Python 3.11 pack required')
    if {p.relative_to(source).as_posix() for p in files(source,cancelled)}!=set(declared)|{MARKER}:raise ValueError('Unlisted or missing source files')
    ref_raw=_read(reference,1024**2);ref=json.loads(ref_raw,object_pairs_hook=object_pairs)
    validate_reference(ref,parent_sha,{k.casefold():v for k,v in declared.items()})
    for key in NATIVE_NAMES:
        if pe_machine(source/key)!='amd64':raise ValueError('CPython native reference must be amd64')
    license_data=_read(source/'LICENSE.txt')
    license_entry=declared.get('LICENSE.txt')
    if license_entry is None or (len(license_data),hashlib.sha256(license_data).hexdigest())!=(license_entry['bytes'],license_entry['sha256']):
        raise ValueError('Installed Python license changed')
    source_raw=_read(notices/'sources.json');sources=json.loads(source_raw,object_pairs_hook=object_pairs)
    source_rows=validate_sources(sources);content={}
    if {p.relative_to(notices).as_posix() for p in files(notices,cancelled)}!=SOURCE_NAMES|{'sources.json'}:raise ValueError('Unlisted or missing notice sources')
    for row in source_rows:
        data=_read(notices/row['path'],1024**2)
        if (len(data),hashlib.sha256(data).hexdigest())!=(row['bytes'],row['sha256']):raise ValueError('Notice source changed')
        content[row['path']]=data
    result={'format':'aredoko-cpython-pack-review-v1','source_manifest_sha256':parent_sha,'prepared':False,
            'native_files':len(NATIVE_NAMES),'source_executed':False,'redistribution_approved':False,
            'supplier_binary_hashes_verified':False,'notice_coverage_reviewed':False,'clean_windows_verified':False}
    if check:return result
    storage_parent(output);output.mkdir();entries=[]
    def add(name,data):
        if cancelled():raise InterruptedError('CPython notice pack cancelled')
        target=output/name;storage_parent(target);plain_path(target,missing=True)
        with target.open('xb') as f:f.write(data)
        entries.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    try:
        for i,entry in enumerate(manifest['entries'],1):
            _copy_checked(source/entry['path'],output/entry['path'],entry,cancelled);entries.append(entry.copy())
            if progress and (i%120==0 or i==len(manifest['entries'])):progress({'stage':'copying_runtime','files_done':i,'files_total':len(manifest['entries'])})
        for name,data in content.items():add(COMPONENT+'/'+name,data)
        add(COMPONENT+'/sources.json',source_raw);add(COMPONENT+'/reference.json',ref_raw);add(COMPONENT+'/python-installed-LICENSE.txt',license_data)
        add(COMPONENT+'/NOTICE.txt',b'CPython 3.11.9 Windows distribution native notice inventory.\nNative bytes are unchanged from the selected sealed parent runtime.\nOriginal notices, commit-pinned sources and a dated SQLite copyright snapshot are supplied for review.\nThe mpdecimal license is the leading original comment, without code.\nVersion resources and local hashes do not prove supplier provenance or legal coverage.\nRedistribution eligibility, all linked-code coverage and clean Windows remain separate.\n')
        component={'format':'aredoko-cpython-component-v1','version':'3.11.9','source_runtime_manifest_sha256':parent_sha,
            'reference_sha256':hashlib.sha256(ref_raw).hexdigest(),'notice_sources_sha256':hashlib.sha256(source_raw).hexdigest(),
            'redistribution_approved':False,'supplier_binary_hashes_verified':False,'notice_coverage_reviewed':False,
            'natives':[e.copy() for e in entries if e['path'] in NATIVE_NAMES],
            'notices':[e.copy() for e in entries if e['path'].startswith(COMPONENT+'/')],'file_notice_bindings':notice_bindings()}
        validate_component(component,{e['path'].casefold():e for e in entries})
        add(COMPONENT+'/component.json',json.dumps(component,indent=2).encode('utf-8'))
        if (_read(source/MARKER,LIMIT)!=raw or _read(reference,1024**2)!=ref_raw or _read(notices/'sources.json')!=source_raw
            or {p.relative_to(source).as_posix() for p in files(source,cancelled)}!=set(declared)|{MARKER}):raise ValueError('CPython preparation inputs changed')
        entries.sort(key=lambda e:e['path']);value={'format':FORMAT,'abi':abi,'entries':entries,'files_count':len(entries),'total_bytes':sum(e['bytes'] for e in entries)}
        with (output/MARKER).open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
        info=inspect_runtime(output,verify=True,cancelled=cancelled,progress=progress)
        return {**result,'prepared':True,'manifest_sha256':info['manifest_sha256'],'files_count':len(entries),'total_bytes':value['total_bytes'],'verification':'full'}
    except BaseException:
        marker=output/MARKER
        if marker.exists():plain_path(marker).unlink()
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--notices',type=Path,default=ROOT/'config/runtime-notices/cpython311-20261029')
    parser.add_argument('--reference',type=Path,default=ROOT/'docs/cpython-native-reference-20261029.json')
    parser.add_argument('--check',action='store_true');args=parser.parse_args();last=[0,None]
    def progress(value):
        now=time.monotonic()
        if now-last[0]>=1 or value['stage']!=last[1]:print(json.dumps(value),flush=True);last[:]=[now,value['stage']]
    print(json.dumps(prepare(args.source,args.output,notices=args.notices,reference=args.reference,check=args.check,progress=progress)))


if __name__=='__main__':main()
