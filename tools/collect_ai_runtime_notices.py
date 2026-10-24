"""Collect explicit runtime license texts for operator review; never import packages.

This inventories distribution notices, not legal permission or all native deps.
"""
import argparse,csv,email.parser,hashlib,io,json,os,re,sys
from urllib.parse import urlsplit
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from ai_runtime import relative,files,object_pairs
from storage_lease import plain_path,storage_parent

FORMAT='aredoko-runtime-notices-v1'
MAX_FILE=4*1024**2
MAX_TOTAL=32*1024**2
MAX_FILES=2048
PREFIXES=('LICENSE','LICENCE','NOTICE','COPYING','COPYRIGHT','AUTHORS')


def _read(path,limit=MAX_FILE):
    path=plain_path(path);before=path.stat()
    with path.open('rb') as stream:data=stream.read(limit+1)
    after=plain_path(path).stat()
    stamp=lambda info:(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
    if len(data)>limit or stamp(before)!=stamp(after):raise ValueError('Notice input changed or exceeds limit')
    return data


def collect(source):
    source=plain_path(source,directory=True)
    site=plain_path(source/'Lib/site-packages',directory=True)
    payload={};distributions=[];names=set();total=0
    def add(path):
        nonlocal total
        path=plain_path(path);key=relative(path.relative_to(source).as_posix())
        if key not in payload:
            if len(payload)>=MAX_FILES:raise ValueError('Notice file count exceeds limit')
            value=_read(path)
            if not value:raise ValueError('Empty notice input')
            total+=len(value)
            if total>MAX_TOTAL:raise ValueError('Notice byte budget exceeded')
            payload[key]=value
        return 'files/'+key
    for name in ('LICENSE.txt','LICENSE','NOTICE.txt'):
        path=source/name
        if path.exists() or path.is_symlink():add(path)
    for directory in sorted(site.iterdir()):
        if not directory.name.endswith('.dist-info'):continue
        plain_path(directory,directory=True)
        metadata=email.parser.BytesParser().parsebytes(_read(directory/'METADATA',1024**2),headersonly=True)
        if len(metadata.get_all('Name',[]))!=1 or len(metadata.get_all('Version',[]))!=1:
            raise ValueError('One distribution name and version required')
        name=str(metadata['Name']);version=str(metadata['Version'])
        if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',name) is None or not 1<=len(version)<=128 or any(ord(c)<32 for c in version):
            raise ValueError('Invalid distribution identity')
        normalized=re.sub(r'[-_.]+','-',name).lower()
        if normalized in names:raise ValueError('Duplicate distribution identity')
        names.add(normalized);notices=set();missing=[]
        for child in directory.iterdir():
            if child.name.upper().startswith(PREFIXES) and not child.is_dir():notices.add(add(child))
        license_dir=directory/'licenses'
        if license_dir.exists() or license_dir.is_symlink():
            for path in files(plain_path(license_dir,directory=True)):notices.add(add(path))
        # PEP 639 puts declared files below licenses; legacy wheels put them
        # directly in dist-info. RECORD also covers package-owned notices.
        declared=[]
        for value in metadata.get_all('License-File',[]):
            key=str(value).strip();declared.append(key)
            try:relative(key)
            except ValueError:
                # Some legacy wheels declare ../LICENSE. Do not follow it or
                # silently approve coverage; retain it as a reviewable gap.
                missing.append(key)
                continue
            candidates=(directory/'licenses'/key,directory/key)
            match=next((p for p in candidates if p.exists() or p.is_symlink()),None)
            if match is None:missing.append(key)
            else:notices.add(add(match))
        record=directory/'RECORD'
        if record.exists() or record.is_symlink():
            for row in csv.reader(io.StringIO(_read(record).decode('utf-8'))):
                if not row:continue
                candidate=row[0]
                if not Path(candidate).name.upper().startswith(PREFIXES):continue
                # RECORD uses the installing OS path syntax (including native
                # Windows separators); then enforce a safe relative identity.
                candidate=site/relative(Path(candidate).as_posix())
                if candidate.exists() or candidate.is_symlink():notices.add(add(candidate))
        declaration=str(metadata.get('License-Expression') or metadata.get('License') or '').strip()
        distributions.append({'name':name,'version':version,'license_declaration':declaration[:4096],
                              'declared_files':declared,'notice_files':sorted(notices),'missing_declared':missing})
    missing=[d['name'] for d in distributions if not d['notice_files'] or d['missing_declared']]
    if not distributions:missing=['distribution metadata unavailable']
    summary={'format':FORMAT,'distribution_count':len(distributions),'distributions':distributions,
             'missing_distribution_notices':missing,'complete_distribution_notices':not missing,
             'redistribution_approved':False,'source_executed':False}
    return summary,payload



def _review_rows(value):
    if not isinstance(value,list) or not 1<=len(value)<=64:raise ValueError('Invalid supplemental notice reviews')
    names=set()
    for row in value:
        if not isinstance(row,dict) or set(row)!={'name','version','metadata_sha256','clears_declared','files'}:
            raise ValueError('Invalid supplemental distribution identity')
        if not isinstance(row['name'],str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',row['name']) is None:
            raise ValueError('Invalid supplemental name')
        normalized=re.sub(r'[-_.]+','-',row['name']).lower()
        if normalized in names:raise ValueError('Duplicate supplemental distribution')
        names.add(normalized)
        if (not isinstance(row['version'],str) or not 1<=len(row['version'])<=128 or
                not isinstance(row['metadata_sha256'],str) or re.fullmatch('[0-9a-f]{64}',row['metadata_sha256']) is None or
                not isinstance(row['clears_declared'],list) or not all(isinstance(x,str) for x in row['clears_declared']) or
                not isinstance(row['files'],list) or not 1<=len(row['files'])<=32):
            raise ValueError('Invalid supplemental binding')
        seen=set()
        for entry in row['files']:
            if not isinstance(entry,dict) or set(entry)!={'path','bytes','sha256','source'}:raise ValueError('Invalid supplemental file')
            key=relative(entry['path'])
            if key.casefold() in seen:raise ValueError('Duplicate supplemental path')
            seen.add(key.casefold())
            if (type(entry['bytes']) is not int or not 1<=entry['bytes']<=MAX_FILE or not isinstance(entry['sha256'],str) or
                    re.fullmatch('[0-9a-f]{64}',entry['sha256']) is None or not isinstance(entry['source'],str)):
                raise ValueError('Invalid supplemental checksum')
            url=urlsplit(entry['source'])
            if (url.scheme!='https' or url.netloc!='raw.githubusercontent.com' or url.query or url.fragment or
                    re.fullmatch(r'/[^/]+/[^/]+/[0-9a-f]{40}/[^?#]+',url.path) is None):
                raise ValueError('Fixed upstream commit URL required')
    return value


def _supplement(summary,payload,source,reviews,read):
    _review_rows(reviews)
    site=plain_path(source/'Lib/site-packages',directory=True)
    # Bind reviews to exact installed METADATA, not merely a version label.
    metadata={}
    for directory in site.iterdir():
        if not directory.name.endswith('.dist-info'):continue
        data=_read(directory/'METADATA',1024**2)
        parsed=email.parser.BytesParser().parsebytes(data,headersonly=True)
        metadata[(str(parsed['Name']),str(parsed['Version']))]=hashlib.sha256(data).hexdigest()
    for row in reviews:
        match=next((d for d in summary['distributions'] if (d['name'],d['version'])==(row['name'],row['version'])),None)
        if (match is None or metadata.get((row['name'],row['version']))!=row['metadata_sha256'] or
                match['missing_declared']!=row['clears_declared'] or
                (match['notice_files'] and not match['missing_declared'])):
            raise ValueError('Supplement review does not match unresolved source metadata')
        normalized=re.sub(r'[-_.]+','-',row['name']).lower()
        for entry in row['files']:
            data=read(entry['path'])
            if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:
                raise ValueError('Supplement notice checksum mismatch')
            key='supplements/'+normalized+'/'+relative(entry['path'])
            if key in payload:raise ValueError('Supplement notice collision')
            payload[key]=data;match['notice_files'].append('files/'+key)
        match['notice_files'].sort();match['missing_declared']=[]
    if len(payload)>MAX_FILES or sum(len(d) for d in payload.values())>MAX_TOTAL:raise ValueError('Supplement notice budget exceeded')
    summary['supplements']=reviews
    summary['missing_distribution_notices']=[d['name'] for d in summary['distributions'] if not d['notice_files'] or d['missing_declared']]
    summary['complete_distribution_notices']=not summary['missing_distribution_notices']


def write_bundle(source,output,*,supplements=None):
    source=plain_path(source,directory=True);output=Path(os.path.abspath(output))
    if output.is_relative_to(source) or source.is_relative_to(output):raise ValueError('Notice output overlaps source')
    if output.exists() or output.is_symlink():raise FileExistsError('New notice output required')
    summary,payload=collect(source)
    if supplements is not None:
        supplements=plain_path(supplements)
        reviews=json.loads(_read(supplements,1024**2),object_pairs_hook=object_pairs)
        _supplement(summary,payload,source,reviews,lambda key:_read(supplements.parent/relative(key)))
    text='AI runtime distribution notice inventory\n\n'
    text+='Package license text is preserved under files/. This index is for review;\nit does not approve redistribution or certify native dependency coverage.\n\n'
    for d in summary['distributions']:
        text+=d['name']+' '+d['version']+'\n'
        text+='\n'.join('  '+path for path in d['notice_files'])+'\n'
        if d['missing_declared']:text+='  Missing declared: '+', '.join(d['missing_declared'])+'\n'
    inputs={**{'files/'+name:data for name,data in payload.items()},'NOTICE.txt':text.encode('utf-8')}
    summary['entries']=[{'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in sorted(inputs.items())]
    storage_parent(output);output.mkdir()
    for name,data in inputs.items():
        destination=output/relative(name);storage_parent(destination)
        with destination.open('xb') as stream:stream.write(data)
    with (output/'manifest.json').open('x',encoding='utf-8') as stream:json.dump(summary,stream,ensure_ascii=False,indent=2)
    validate_bundle(output)
    return summary


def validate_bundle(root,*,require_complete=False):
    root=plain_path(root,directory=True)
    value=json.loads(_read(root/'manifest.json',16*1024**2),object_pairs_hook=object_pairs)
    if (not isinstance(value,dict) or value.get('format')!=FORMAT or value.get('redistribution_approved') is not False
            or value.get('source_executed') is not False or type(value.get('complete_distribution_notices')) is not bool):
        raise ValueError('Unsupported notice inventory')
    if 'supplements' in value:_review_rows(value['supplements'])
    distributions=value.get('distributions')
    if not isinstance(distributions,list) or type(value.get('distribution_count')) is not int or value['distribution_count']!=len(distributions):
        raise ValueError('Invalid distribution notice list')
    missing=[];references=set()
    for d in distributions:
        if not isinstance(d,dict) or not isinstance(d.get('name'),str) or not isinstance(d.get('notice_files'),list) or not isinstance(d.get('missing_declared'),list):
            raise ValueError('Invalid distribution notice reference')
        for reference in d['notice_files']:
            name=relative(reference)
            if not name.startswith('files/'):raise ValueError('Invalid notice source reference')
            references.add(name.casefold())
        if not d['notice_files'] or d['missing_declared']:missing.append(d['name'])
    if not distributions:missing=['distribution metadata unavailable']
    if value.get('missing_distribution_notices')!=missing or value['complete_distribution_notices']!=(not missing):
        raise ValueError('Inconsistent notice completeness')
    if require_complete and missing:raise ValueError('Distribution notices are incomplete')
    entries=value.get('entries');seen=set();total=0
    if not isinstance(entries,list) or not 1<=len(entries)<=MAX_FILES+1:raise ValueError('Invalid notice inventory entries')
    for entry in entries:
        if not isinstance(entry,dict) or set(entry)!={'path','bytes','sha256'}:raise ValueError('Invalid notice entry')
        name=relative(entry['path']);size=entry['bytes'];checksum=entry['sha256']
        if name.casefold() in seen or type(size) is not int or size<0 or not isinstance(checksum,str) or re.fullmatch('[0-9a-f]{64}',checksum) is None:
            raise ValueError('Invalid notice identity')
        seen.add(name.casefold());data=_read(root/name);total+=len(data)
        if total>MAX_TOTAL+MAX_FILE or len(data)!=size or hashlib.sha256(data).hexdigest()!=checksum:
            raise ValueError('Notice checksum or size mismatch')
    if not references.issubset(seen):raise ValueError('Missing referenced notice')
    if {p.relative_to(root).as_posix().casefold() for p in files(root)}!=seen|{'manifest.json'}:
        raise ValueError('Unlisted notice file')
    return value


def validate_for_source(root,source):
    root=plain_path(root,directory=True)
    value=validate_bundle(root,require_complete=True)
    source=plain_path(source,directory=True)
    expected,payload=collect(source)
    if 'supplements' in value:
        # Only read already sealed supplemental texts. Never fetch provenance URLs.
        current={}
        def read_review(key):return _read(current['path']/relative(key))
        # Each row has an independent base, so identical LICENSE names are safe.
        for row in value['supplements']:
            normalized=re.sub(r'[-_.]+','-',row['name']).lower()
            current['path']=root/('files/supplements/'+normalized)
            _supplement(expected,payload,source,[row],read_review)
    if value['distributions']!=expected['distributions']:
        raise ValueError('Notice source changed')
    declared={e['path']:(e['bytes'],e['sha256']) for e in value['entries']}
    actual={'files/'+key:(len(data),hashlib.sha256(data).hexdigest()) for key,data in payload.items()}
    if {key:identity for key,identity in declared.items() if key!='NOTICE.txt'}!=actual:
        raise ValueError('Notice source changed')
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path);parser.add_argument('--check',action='store_true')
    parser.add_argument('--supplements',type=Path,help='Explicit fixed-source, METADATA-bound reviewed notice mapping')
    args=parser.parse_args()
    if not args.check and args.output is None:parser.error('New output required unless --check')
    if args.check and args.supplements is not None:parser.error('Supplement review requires a new bundle output')
    summary=collect(args.source)[0] if args.check else write_bundle(args.source,args.output,supplements=args.supplements)
    print(json.dumps({k:summary[k] for k in ('distribution_count','complete_distribution_notices','missing_distribution_notices','redistribution_approved','source_executed')},ensure_ascii=False))
    return 0 if summary['complete_distribution_notices'] else 2

if __name__=='__main__':raise SystemExit(main())
