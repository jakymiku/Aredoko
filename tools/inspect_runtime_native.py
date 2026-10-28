"""Read-only native inventory/RECORD/NOTICE mapping; not redistribution approval.

Reads bounded metadata and PE architecture headers, never loads DLLs or imports
selected packages. Optional --imports lists static/delay DLL names. Payload
hashes come from the sealed manifest, not a new multi-GB verification. Dynamic
loading, loader resolution, export forwarders and extra-tree files are not audited.
"""
import argparse,csv,email.parser,hashlib,io,json,os,re,struct
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from ai_runtime import FORMAT,MARKER,LIMIT,relative,object_pairs
from storage_lease import plain_path,storage_parent
from collect_ai_runtime_notices import _read,validate_for_source
from msvc_component_contract import COMPONENT,validate_component

NATIVE=frozenset(('.exe','.dll','.pyd'))


def record_key(value):
    value=value.replace('\\','/')
    if value.startswith('/') or ':' in value:raise ValueError('External RECORD path')
    parts=['Lib','site-packages']
    for part in value.split('/'):
        if part in ('','.'):continue
        if part=='..':
            if not parts:raise ValueError('External RECORD path')
            parts.pop()
        else:parts.append(part)
    return relative('/'.join(parts)).casefold()


def pe_machine(path):
    path=plain_path(path)
    stamp=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
    initial=path.stat();coff=None
    with path.open('rb') as stream:
        before=os.fstat(stream.fileno());header=stream.read(64)
        if len(header)==64 and header[:2]==b'MZ':
            offset=struct.unpack_from('<I',header,60)[0]
            if 64<=offset<=min(1024*1024,before.st_size-6):stream.seek(offset);coff=stream.read(6)
        after=os.fstat(stream.fileno())
    current=plain_path(path).stat()
    # Python/Windows versions can expose creation time for path.stat().ctime
    # and change time for fstat().ctime. Compare each clock to its own source,
    # while matching identity/size/mtime across the path and open handle.
    if (stamp(before)!=stamp(after) or stamp(initial)!=stamp(current) or
        identity(initial)!=identity(before) or identity(after)!=identity(current)):raise RuntimeError('Native header source changed')
    if coff is None or len(coff)!=6 or coff[:4]!=b'PE\0\0':return None
    code=struct.unpack_from('<H',coff,4)[0]
    return {0x8664:'amd64',0x14c:'x86',0xaa64:'arm64'}.get(code,f'0x{code:04x}')


def inspect(root,notices,*,imports=False):
    root=plain_path(root,directory=True);raw=_read(root/MARKER,LIMIT)
    manifest=json.loads(raw,object_pairs_hook=object_pairs)
    if manifest.get('format')!=FORMAT or not isinstance(manifest.get('entries'),list) or not 1<=len(manifest['entries'])<=250000:raise ValueError('Explicit sealed runtime inventory required')
    entries={};declared={}
    for entry in manifest['entries']:
        key=relative(entry['path']);folded=key.casefold()
        if (folded in declared or type(entry['bytes']) is not int or entry['bytes']<0 or
            not isinstance(entry['sha256'],str) or re.fullmatch('[0-9a-f]{64}',entry['sha256']) is None):raise ValueError('Invalid declared runtime entry')
        declared[folded]=entry
        if Path(key).suffix.casefold() in NATIVE:entries[folded]=entry
    if len(entries)>4096:raise ValueError('Native inventory exceeds audit limit')
    notice=validate_for_source(notices,root);declarations={}
    for distribution in notice['distributions']:
        key=(re.sub('[-_.]+','-',distribution['name']).casefold(),distribution['version'])
        declarations[key]=distribution['notice_files']
    owners={key:set() for key in entries};outside=0
    def bound_metadata(path,limit=4*1024**2):
        data=_read(path,limit);key=path.relative_to(root).as_posix().casefold();entry=declared.get(key)
        if entry is None or len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:
            raise ValueError('Native review metadata differs from sealed inventory')
        return data
    site=root/'Lib/site-packages'
    for directory in sorted(site.iterdir()):
        if not directory.name.endswith('.dist-info'):continue
        metadata=email.parser.BytesParser().parsebytes(bound_metadata(directory/'METADATA',1024**2),headersonly=True)
        name=str(metadata['Name']);version=str(metadata['Version']);identity=(re.sub('[-_.]+','-',name).casefold(),version)
        if identity not in declarations:raise ValueError('Distribution lacks bound notice metadata')
        record=directory/'RECORD'
        if not (record.exists() or record.is_symlink()):
            if record.relative_to(root).as_posix().casefold() in declared:raise ValueError('Declared native review metadata is missing')
            continue
        for row in csv.reader(io.StringIO(bound_metadata(record).decode('utf-8'))):
            if not row:continue
            try:key=record_key(row[0])
            except ValueError:outside+=1;continue
            if key in owners:owners[key].add((name,version))
    components=[];component_owners={}
    component_path=root/(COMPONENT+'/component.json')
    if component_path.exists() or component_path.is_symlink() or (COMPONENT+'/component.json').casefold() in declared:
        value=json.loads(bound_metadata(component_path),object_pairs_hook=object_pairs)
        component=validate_component(value,declared)
        # These 12 small DLLs and 3 terms files are fully hashed, unlike the
        # rest of this bounded header/metadata audit of the multi-GB pack.
        for entry in (*value['dlls'],*value['notices']):bound_metadata(root/entry['path'],16*1024**2 if entry in value['dlls'] else 4*1024**2)
        component['payload_hashes_verified']=True;components.append(component)
        for name in component['dll_files']:component_owners[name.casefold()]=component
    rows=[]
    for key,entry in sorted(entries.items()):
        path=plain_path(root/entry['path'])
        if path.stat().st_size!=entry['bytes']:raise ValueError('Native declared size changed')
        linked=[]
        for name,version in sorted(owners[key]):
            linked.append({'name':name,'version':version,'notice_files':declarations[(re.sub('[-_.]+','-',name).casefold(),version)]})
        component=component_owners.get(key);machine=pe_machine(path)
        if component is not None and machine!='amd64':raise ValueError('Native CRT component must be amd64')
        rows.append({'path':entry['path'],'bytes':entry['bytes'],'declared_sha256':entry['sha256'],
                     'pe_machine':machine,'distribution_record_owners':linked,'native_component_owner':component})
        if imports:
            from pe_imports import read_imports
            try:rows[-1]['static_imports']={'state':'inspected',**read_imports(path)}
            except ValueError as error:rows[-1]['static_imports']={'state':'invalid','error':str(error)}
    if imports:
        candidates={}
        for row in rows:candidates.setdefault(Path(row['path']).name.casefold(),[]).append(row)
        for row in rows:
            data=row['static_imports']
            data['edges']=[{'name':name,'kind':kind,
                'inventory_candidates':[item['path'] for item in candidates.get(name.casefold(),[])],
                'same_machine_candidates':[item['path'] for item in candidates.get(name.casefold(),[]) if item['pe_machine']==row['pe_machine']]}
                for kind in ('imports','delay_imports') for name in data.get(kind,[])]
    if _read(root/MARKER,LIMIT)!=raw:raise ValueError('Runtime manifest changed during audit')
    return {'format':'aredoko-runtime-native-review-v1','runtime_manifest_sha256':hashlib.sha256(raw).hexdigest(),
            'tool_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'native_count':len(rows),'unmapped_count':sum(not row['distribution_record_owners'] and row['native_component_owner'] is None for row in rows),
            'unmapped_distribution_record_count':sum(not row['distribution_record_owners'] for row in rows),
            'native_components':components,
            'ambiguous_owner_count':sum(len(row['distribution_record_owners'])>1 for row in rows),
            'unknown_pe_count':sum(row['pe_machine'] is None for row in rows),'outside_record_references':outside,
            'distribution_metadata_hashes_verified':True,'payload_hashes_verified':False,'extra_tree_verified':False,'native_dependency_graph_inspected':False,
            'static_imports_requested':imports,'static_imports_inspected':imports and all(row['static_imports']['state']=='inspected' for row in rows),
            'static_import_bytes_read':sum(row['static_imports'].get('bytes_read',0) for row in rows) if imports else 0,
            'unbundled_vc_imports':[{'path':row['path'],'name':edge['name'],'machine':row['pe_machine'],'kind':edge['kind']}
                for row in rows for edge in row.get('static_imports',{}).get('edges',[]) if not edge['same_machine_candidates'] and re.fullmatch(r'(?:msvcp|vcruntime|concrt)\d+(?:_\w+)?\.dll',edge['name'],re.I)],
            'dynamic_dependencies_inspected':False,'loader_resolution_verified':False,
            'redistribution_approved':False,'source_executed':False,'entries':rows}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--notices',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--imports',action='store_true',help='Read static/delay import names without loading DLLs; basename matches are candidates only')
    args=parser.parse_args();root=plain_path(args.source,directory=True);output=Path(os.path.abspath(args.output))
    if output.is_relative_to(root):parser.error('Audit output must stay outside the immutable runtime')
    storage_parent(output);plain_path(output,missing=True)
    report=inspect(root,args.notices,imports=args.imports)
    with output.open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k!='entries'},ensure_ascii=False));return 0


if __name__=='__main__':raise SystemExit(main())
