"""Offline static review of an explicitly approved, pinned Microsoft bundle.

Uses an explicitly selected existing 7-Zip, never the selected installer, DLLs,
MSI actions, package installation or network. Every destination is new and flat.
Output is a review directory, not an app-local runtime or redistribution grant.
"""
import argparse
import hashlib
import json
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import threading

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from storage_lease import plain_path,storage_parent
from burn_containers import containers
from inspect_msvc_redist import inspect as inspect_installer

MAX_FILES=512
MAX_MEMBER=64*1024*1024
MAX_TOTAL=256*1024*1024


def cabinet_members(listing):
    if type(listing) is not str or len(listing)>2*1024*1024:raise ValueError('Cabinet list exceeds review limit')
    result=[];seen=set();total=0
    for block in re.split(r'\r?\n\s*\r?\n',listing.strip()):
        fields={}
        for line in block.splitlines():
            if ' = ' not in line:raise ValueError('Unexpected Cabinet list format')
            key,value=line.split(' = ',1)
            if key in fields:raise ValueError('Duplicate Cabinet list field')
            fields[key]=value
        name=fields.get('Path','');size=fields.get('Size','')
        if (not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,159}',name)
                or name.endswith('.') or name.casefold() in seen
                or re.fullmatch(r'(?i)(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?',name)
                or fields.get('Folder','-')!='-' or 'D' in fields.get('Attributes','')
                or not re.fullmatch(r'\d{1,10}',size)):
            raise ValueError('Cabinet member is not one safe flat file')
        count=int(size);total+=count
        if not 0<=count<=MAX_MEMBER or total>MAX_TOTAL or len(result)>=MAX_FILES:raise ValueError('Cabinet extraction exceeds review limit')
        seen.add(name.casefold());result.append({'name':name,'bytes':count})
    if not result:raise ValueError('Cabinet has no reviewable members')
    return result


def _pipe(extractor,arguments,target,limit):
    """Enforce the byte cap while reading, including a blocked child timeout."""
    process=subprocess.Popen([str(extractor),*map(str,arguments)],shell=False,
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    expired=threading.Event()
    def timeout():
        expired.set()
        if process.poll() is None:process.kill()  # This exact owned tool only.
    timer=threading.Timer(60,timeout);timer.daemon=True;count=0;digest=hashlib.sha256()
    try:
        timer.start()
        while block:=process.stdout.read(min(1024*1024,limit-count+1)):
            count+=len(block)
            if count>limit:raise ValueError('Archive tool output exceeds review limit')
            target.write(block);digest.update(block)
        code=process.wait(timeout=5)
        if expired.is_set() or code:raise RuntimeError('Existing archive tool could not inspect the pinned Cabinet')
        return count,digest.hexdigest()
    finally:
        timer.cancel()
        if process.poll() is None:process.kill()
        process.wait(timeout=5);process.stdout.close();timer.join()


def extract_cabinet(path,directory,extractor,*,remaining_bytes=MAX_TOTAL,remaining_files=MAX_FILES):
    """Extract flat data only, including a nested CAB selected from the bundle."""
    path=plain_path(path);directory=Path(os.path.abspath(directory));storage_parent(directory)
    if path.is_relative_to(directory):raise ValueError('Cabinet output overlaps input')
    plain_path(directory,missing=True)
    listing=io.BytesIO()
    _pipe(extractor,['l','-slt','-ba','-sccUTF-8','-tCab',path],listing,2*1024*1024)
    members=cabinet_members(listing.getvalue().decode('utf-8-sig'))
    if sum(item['bytes'] for item in members)>remaining_bytes or len(members)>remaining_files:
        raise ValueError('Remaining bundle extraction budget exceeded')
    directory.mkdir();result=[]
    for item in members:
        # stdout redirection avoids archive destination paths and links.
        destination=directory/item['name'];plain_path(destination,missing=True)
        with destination.open('xb') as target:
            length,checksum=_pipe(extractor,['x','-so','-y','-tCab',path,item['name']],target,item['bytes'])
        destination=plain_path(destination)
        if length!=item['bytes'] or destination.stat().st_size!=length:raise ValueError('Cabinet member differs from declared size')
        result.append({'path':item['name'],'bytes':length,'sha256':checksum})
    return result


def extract(source,reference,output,extractor):
    source=plain_path(source);reference=plain_path(reference);extractor=plain_path(extractor)
    if reference.stat().st_size>16384:raise ValueError('Source reference exceeds limit')
    declared=json.loads(reference.read_text(encoding='utf-8'))
    if declared.get('format')!='aredoko-msvc-source-reference-v1':raise ValueError('Expected a reviewed Microsoft source reference')
    reviewed=inspect_installer(source,declared['observed_artifact_url'])
    if (reviewed['sha256']!=declared['sha256'] or reviewed['bytes']!=declared['bytes']
            or reviewed['metadata']['file_version']!=declared['file_version']):raise ValueError('Installer differs from reviewed source')
    spans=containers(source);output=Path(os.path.abspath(output))
    if output.is_relative_to(source.parent) or source.is_relative_to(output):raise ValueError('Review output overlaps source')
    storage_parent(output);plain_path(output,missing=True);output.mkdir()
    inventory=[];used=0
    with source.open('rb') as original:
        for span in spans:
            path=output/('container-'+str(span['index'])+'.cab');original.seek(span['offset'])
            remaining=span['bytes']
            with path.open('xb') as target:
                while remaining:
                    block=original.read(min(1024*1024,remaining))
                    if not block:raise RuntimeError('Installer changed during container copy')
                    target.write(block);remaining-=len(block)
            directory=output/('container-'+str(span['index']))
            members=extract_cabinet(path,directory,extractor,remaining_bytes=MAX_TOTAL-used,remaining_files=MAX_FILES-len(inventory))
            used+=sum(item['bytes'] for item in members)
            if used>MAX_TOTAL or len(inventory)+len(members)>MAX_FILES:raise ValueError('Bundle extraction exceeds review limit')
            for item in members:
                inventory.append({**item,'path':(directory/item['path']).relative_to(output).as_posix()})
    # Include the actual source bytes in the before/after binding; a changed
    # source leaves an unapproved partial directory rather than a success receipt.
    hasher=hashlib.sha256()
    with plain_path(source).open('rb') as stream:
        while block:=stream.read(1024*1024):hasher.update(block)
    if hasher.hexdigest()!=reviewed['sha256']:raise RuntimeError('Installer changed during extraction')
    value={'format':'aredoko-msvc-static-extraction-v1','source_sha256':reviewed['sha256'],
        'source_bytes':reviewed['bytes'],'source_version':declared['file_version'],'containers':spans,'entries':inventory,
        'source_executed':False,'msi_actions_run':False,'os_installed':False,'runtime_modified':False,'redistribution_approved':False}
    with (output/'extraction.json').open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2)
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','reference','output','seven-zip'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--static-extraction-consent',action='store_true',required=True,help='Run only after the human authorizes static extraction; never installation')
    args=parser.parse_args();value=extract(args.source,args.reference,args.output,args.seven_zip)
    print(json.dumps({'files':len(value['entries']),'bytes':sum(item['bytes'] for item in value['entries']),'source_executed':False,'os_installed':False}))


if __name__=='__main__':main()
