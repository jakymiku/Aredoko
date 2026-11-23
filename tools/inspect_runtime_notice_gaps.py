"""Read-only evidence for unowned native files; no ownership or rights approval.

Ties a prior native audit to the current sealed manifest, hashes only its gaps
and LICENSE.txt, and locates notice terms for a human review. Never imports or
executes code from the selected runtime and never changes its inventory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
from ai_runtime import FORMAT,MARKER,LIMIT,relative,object_pairs
from collect_ai_runtime_notices import _read
from storage_lease import plain_path,storage_parent

CORE=frozenset(('python.exe','pythonw.exe','python3.dll','python311.dll'))
TERMS={'cpython':r'Python Software Foundation','openssl':r'OpenSSL','libffi':r'libffi',
       'sqlite':r'SQLite','tcl_tk':r'Tcl|Tkinter','bzip2':r'bzip2','lzma':r'LZMA|liblzma',
       'zlib':r'zlib','expat':r'Expat','decimal':r'mpdecimal|libmpdec'}


def inspect_gaps(root,audit):
    root=plain_path(root,directory=True)
    raw=_read(root/MARKER,LIMIT);manifest=json.loads(raw,object_pairs_hook=object_pairs)
    if manifest.get('format')!=FORMAT or not isinstance(manifest.get('entries'),list):
        raise ValueError('Sealed runtime inventory required')
    if not 1<=len(manifest['entries'])<=250000:raise ValueError('Invalid inventory count')
    declared={}
    for entry in manifest['entries']:
        key=relative(entry['path'])
        if key.casefold() in declared or type(entry['bytes']) is not int or entry['bytes']<0 or not isinstance(entry['sha256'],str) or re.fullmatch('[0-9a-f]{64}',entry['sha256']) is None:
            raise ValueError('Invalid runtime entry')
        declared[key.casefold()]=entry
    audit_raw=_read(audit,16*1024**2);review=json.loads(audit_raw,object_pairs_hook=object_pairs)
    if (review.get('format')!='aredoko-runtime-native-review-v1' or
            review.get('runtime_manifest_sha256')!=hashlib.sha256(raw).hexdigest()):
        raise ValueError('Native audit belongs to another runtime inventory')
    rows=review.get('entries')
    if not isinstance(rows,list) or not 1<=len(rows)<=4096:raise ValueError('Invalid native audit rows')
    def bound(key,limit):
        entry=declared.get(key.casefold())
        if entry is None or entry['bytes']>limit:raise ValueError('Missing or oversized bound review input')
        data=_read(root/key,limit)
        if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:
            raise ValueError('Review input differs from sealed inventory')
        return data
    license_data=bound('LICENSE.txt',4*1024**2);lines=license_data.decode('utf-8-sig').splitlines()
    hits={name:[i+1 for i,line in enumerate(lines) if re.search(pattern,line,re.I)][:20] for name,pattern in TERMS.items()}
    result=[];seen=set();total=0
    for row in rows:
        key=relative(row['path']);folded=key.casefold();entry=declared.get(folded)
        if (folded in seen or Path(key).suffix.casefold() not in ('.dll','.pyd','.exe') or entry is None or
                row.get('bytes')!=entry['bytes'] or row.get('declared_sha256')!=entry['sha256'] or
                not isinstance(row.get('distribution_record_owners'),list)):
            raise ValueError('Invalid or unbound native audit entry')
        seen.add(folded)
        if row['distribution_record_owners'] or row.get('native_component_owner') is not None:continue
        total+=entry['bytes']
        if total>128*1024**2:raise ValueError('Notice-gap review exceeds bounded payload budget')
        bound(key,32*1024**2)
        group='cpython-core-candidate' if folded in CORE else 'cpython-distribution-candidate' if key.startswith('DLLs/') else 'unclassified'
        result.append({'path':key,'bytes':entry['bytes'],'sha256':entry['sha256'],'review_group':group,
                       'owner_verified':False,'notice_coverage_verified':False})
    if len(result)!=review.get('unmapped_count'):raise ValueError('Native audit gap count differs')
    if _read(root/MARKER,LIMIT)!=raw or _read(audit,16*1024**2)!=audit_raw:raise ValueError('Review metadata changed')
    return {'format':'aredoko-runtime-notice-gaps-v1','runtime_manifest_sha256':hashlib.sha256(raw).hexdigest(),
            'native_audit_sha256':hashlib.sha256(audit_raw).hexdigest(),'gap_count':len(result),
            'gap_payload_hashes_verified':True,'gap_payload_bytes_read':total,
            'notice':{'path':'LICENSE.txt','bytes':len(license_data),'sha256':hashlib.sha256(license_data).hexdigest(),
                      'term_line_candidates':hits,'term_hits_prove_coverage':False},
            'entries':result,'owner_assignments_changed':False,'redistribution_approved':False,
            'source_executed':False,'full_runtime_payload_verified':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--audit',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    root=plain_path(args.source,directory=True);output=Path(os.path.abspath(args.output))
    if output.is_relative_to(root):parser.error('Read-only report must stay outside selected runtime')
    report=inspect_gaps(root,args.audit);storage_parent(output);plain_path(output,missing=True)
    with output.open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k not in ('entries','notice')},indent=2))


if __name__=='__main__':main()
