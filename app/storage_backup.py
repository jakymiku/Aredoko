"""Local-only versioned recovery bundles. Never copy media or overwrite a restore target."""
from contextlib import ExitStack,closing,contextmanager
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sqlite3
import time

from ai_profiles import LEGACY_PROFILE,ModelProfile
from ai_scope import validate_scope
from ai_settings import NAME,validate_resource
from tagger_profile import WDProfile
from storage_lease import plain_path,identity,storage_lease,StorageBusyError

FORMAT='aredoko-recovery';VERSION=1
MAX_JSON=256*1024;MAX_FILES=148;DEFAULT_MAX_BYTES=32*1024**3
CATALOG='catalog.sqlite'
SCHEMA=json.loads(Path(__file__).with_name('storage_schema_v1.json').read_text(encoding='utf-8'))
REQUIRED={'catalog':{'items','item_locations','library_locations','library_roots','library_root_seq','production_marker','reader_progress','view_history','scan_jobs','term_relations'},'vectors':{'ai_profile','ai_vectors','ai_state'}}
class RecoveryError(ValueError):pass

def _pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise RecoveryError('Duplicate JSON key')
        result[key]=value
    return result

def _json(data):return json.loads(data.decode('utf-8-sig'),object_pairs_hook=_pairs)

def _read_small(path,limit=MAX_JSON):
    path=plain_path(path)
    with path.open('rb') as stream:
        before=os.fstat(stream.fileno());data=stream.read(limit+1);after=os.fstat(stream.fileno())
    if len(data)>limit or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns) or identity(path)!=(before.st_dev,before.st_ino):
        raise RecoveryError('Configuration changed or exceeds limit')
    return data

def _hash(path):
    digest=hashlib.sha256()
    with plain_path(path).open('rb') as stream:
        before=os.fstat(stream.fileno())
        while chunk:=stream.read(1024*1024):digest.update(chunk)
        after=os.fstat(stream.fileno())
    if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns) or identity(path)!=(before.st_dev,before.st_ino):raise RecoveryError('Bundle file changed')
    return after.st_size,digest.hexdigest()

def _connect(path,mode='ro'):
    db=sqlite3.connect(plain_path(path).as_uri()+'?mode='+mode,uri=True,timeout=1)
    db.execute('PRAGMA trusted_schema=OFF');return db

def _profile_suffix(key):
    if key==LEGACY_PROFILE:return '.ai.sqlite'
    if isinstance(key,str) and re.fullmatch('embedding-profile:[0-9a-f]{64}',key):return '.ai.'+hashlib.sha256(key.encode()).hexdigest()[:24]+'.sqlite'
    raise RecoveryError('Unknown vector profile identity')

def _database(path,role):
    with closing(_connect(path)) as db:
        if db.execute('PRAGMA user_version').fetchone()[0]!=0:raise RecoveryError('Unsupported database version')
        if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:raise RecoveryError('Database integrity check failed')
        objects=db.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND type IN ('table','view','trigger')").fetchall()
        if any(kind!='table' for _,kind in objects):raise RecoveryError('Unsupported database objects')
        tables={name for name,_ in objects};expected=SCHEMA[role]
        if not REQUIRED[role]<=tables or tables-set(expected):raise RecoveryError('Unsupported database tables')
        actual={name:[list(row[1:]) for row in db.execute('PRAGMA table_info('+name+')')] for name in sorted(tables)}
        if any(value!=expected[name] for name,value in actual.items()):raise RecoveryError('Unsupported database columns; use a compatible app version')
        if db.execute('PRAGMA foreign_key_check').fetchone() is not None:raise RecoveryError('Database relationships are invalid')
        profile=None
        if role=='vectors':
            rows=db.execute('SELECT value FROM ai_profile LIMIT 2').fetchall()
            if len(rows)!=1:raise RecoveryError('Invalid vector profile')
            profile=rows[0][0];_profile_suffix(profile)
    digest=hashlib.sha256(json.dumps(actual,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return digest,profile

def _configuration(role,data):
    value=_json(data)
    if role=='profile':ModelProfile.from_dict(value)
    elif role=='tagger_profile':WDProfile.from_dict(value)
    elif role=='ai_settings':
        if not isinstance(value,dict) or not {'version','profile'}<=set(value) or set(value)-{'version','profile','resource','scope'} or type(value['version']) is not int or value['version']!=1:raise RecoveryError('Unsupported AI settings')
        selected=value['profile']
        if selected!='default' and (not isinstance(selected,str) or not selected.startswith('local:') or NAME.fullmatch(selected[6:]) is None):raise RecoveryError('Invalid selected profile')
        if 'resource' in value:validate_resource(value['resource'])
        if 'scope' in value:validate_scope(value['scope'])
    elif role=='viewer_settings':
        if not isinstance(value,dict) or set(value)!={'version','wheel_up_advances'} or type(value['version']) is not int or value['version']!=1 or type(value['wheel_up_advances']) is not bool:raise RecoveryError('Unsupported viewer settings')
    else:raise RecoveryError('Invalid configuration role')

def _stores(catalog):
    pattern=re.compile(re.escape(catalog.name)+r'\.ai(?:\.[0-9a-f]{24})?\.sqlite')
    stores=sorted(plain_path(path) for path in catalog.parent.iterdir() if pattern.fullmatch(path.name))
    if len(stores)>64:raise RecoveryError('Too many vector stores')
    return stores

def _profiles(folder):
    if folder is None:return []
    folder=plain_path(folder,directory=True)
    paths=sorted(plain_path(path) for path in folder.iterdir() if path.suffix.lower()=='.json')
    if len(paths)>64 or any(NAME.fullmatch(path.name) is None for path in paths):raise RecoveryError('Unsupported profile filename/count')
    return paths

def _budget(value):
    if type(value) is not int or not 65536<=value<=256*1024**3:raise RecoveryError('Invalid backup byte limit')
    return value

@contextmanager
def _output(path,estimate):
    path=plain_path(path,missing=True,directory=True)
    if path.exists():raise RecoveryError('Output must be a new directory')
    if shutil.disk_usage(path.parent).free<2*estimate+8*1024**2:raise RecoveryError('Insufficient free space')
    path.mkdir(mode=0o700);owned=identity(path)
    try:yield path
    except BaseException:
        # Only our newly-created target, still at its checked absolute location.
        if plain_path(path,directory=True).parent==path.parent and identity(path)==owned:shutil.rmtree(path)
        raise

def _write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())

def _entry(folder,relative,role,*,schema=None,profile=None):
    size,digest=_hash(folder/relative);result={'path':relative,'role':role,'bytes':size,'sha256':digest}
    if schema is not None:result['schema']=schema
    if profile is not None:result['profile']=profile
    return result

def backup(catalog,output,*,settings=None,viewer_settings=None,profiles=None,extra_profiles=(),tagger_profiles=(),include_vectors=True,max_bytes=DEFAULT_MAX_BYTES,cancelled=None):
    max_bytes=_budget(max_bytes);catalog=plain_path(catalog);output=Path(os.path.abspath(output))
    if type(include_vectors) is not bool:raise RecoveryError('Invalid cache policy')
    def check():
        if cancelled is not None and cancelled():raise InterruptedError('Backup cancelled')
    with storage_lease(catalog),ExitStack() as stack:
        stores=_stores(catalog) if include_vectors else []
        directory_profiles=_profiles(profiles)
        profile_paths=directory_profiles+[plain_path(path) for path in extra_profiles]
        if len(profile_paths)>64 or len({p.name.casefold() for p in profile_paths})!=len(profile_paths) or any(NAME.fullmatch(p.name) is None for p in profile_paths):raise RecoveryError('Duplicate/invalid profiles')
        paths=[catalog,*stores];identities={p:identity(p) for p in paths}
        configurations=[];missing=[]
        for role,path,relative in [('ai_settings',settings,'settings/ai-settings.json'),('viewer_settings',viewer_settings,'settings/viewer-settings.json')]:
            if path is None:missing.append(role);continue
            data=_read_small(path,16384 if role=='ai_settings' else 2048);_configuration(role,data);configurations.append((plain_path(path),relative,role,data))
        for path in profile_paths:
            data=_read_small(path,16384);_configuration('profile',data);configurations.append((path,'profiles/'+path.name,'profile',data))
        if profiles is None and not extra_profiles:missing.append('profiles')
        tagger_paths=[plain_path(path) for path in tagger_profiles]
        if len(tagger_paths)>16 or len({p.name.casefold() for p in tagger_paths})!=len(tagger_paths) or any(NAME.fullmatch(p.name) is None for p in tagger_paths):raise RecoveryError('Duplicate/invalid tagger profiles')
        for path in tagger_paths:
            data=_read_small(path,16384);_configuration('tagger_profile',data);configurations.append((path,'tagger-profiles/'+path.name,'tagger_profile',data))
        if not tagger_paths:missing.append('tagger_profiles')
        if any(output==p or output in p.parents for p in [*paths,*(v[0] for v in configurations)]):raise RecoveryError('Output contains a source')
        estimate=sum(path.stat().st_size for path in paths)+sum(len(v[3]) for v in configurations)
        if estimate>max_bytes:raise RecoveryError('Backup exceeds byte limit')
        # Additional DB locks protect against non-host SQLite writers as well.
        guards=[]
        for path in paths:
            check();db=stack.enter_context(closing(_connect(path,'rw')));version=db.execute('PRAGMA data_version').fetchone()[0];guards.append((path,db,version))
        for _,db,_ in guards:
            try:db.execute('BEGIN IMMEDIATE')
            except sqlite3.OperationalError as error:raise StorageBusyError('Database is busy; close writers before backup') from error
            stack.callback(db.rollback)
            try:db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            except Exception:pass
        def unchanged():
            check()
            if (include_vectors and _stores(catalog)!=stores) or _profiles(profiles)!=directory_profiles:
                raise RecoveryError('Storage membership changed')
            for path,db,version in guards:
                plain_path(path)
                if identity(path)!=identities[path] or db.execute('PRAGMA data_version').fetchone()[0]!=version:raise RecoveryError('Storage changed during capture')
            for path,_,_,data in configurations:
                if _read_small(path,16384)!=data:raise RecoveryError('Settings changed during capture')
        unchanged()
        estimate=sum(db.execute('PRAGMA page_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0] for _,db,_ in guards)+sum(len(v[3]) for v in configurations)
        if estimate>max_bytes:raise RecoveryError('Backup exceeds byte limit')
        with _output(output,estimate) as folder:
            with storage_lease(folder/CATALOG):
                entries=[];used=0;started=time.monotonic()
                for number,(path,_,_) in enumerate(guards):
                    check();role='catalog' if number==0 else 'vectors'
                    schema,profile=_database(path,role)
                    if number and path.name!=catalog.name+_profile_suffix(profile):raise RecoveryError('Vector namespace filename mismatch')
                    relative=CATALOG if number==0 else CATALOG+_profile_suffix(profile)
                    with closing(_connect(path)) as source,closing(sqlite3.connect(folder/relative)) as target:
                        page_size=source.execute('PRAGMA page_size').fetchone()[0]
                        def progress(status,remaining,total):
                            check()
                            if status in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED):raise StorageBusyError('Snapshot blocked')
                            if used+total*page_size>max_bytes:raise RecoveryError('Backup exceeds byte limit')
                            if time.monotonic()-started>600:raise RecoveryError('Backup time limit exceeded')
                        source.backup(target,pages=256,progress=progress,sleep=.01)
                        target.execute('PRAGMA journal_mode=DELETE')
                    if _database(folder/relative,role)!=(schema,profile):raise RecoveryError('Snapshot schema mismatch')
                    entry=_entry(folder,relative,role,schema=schema,profile=profile);used+=entry['bytes'];entries.append(entry)
                for _,relative,role,data in configurations:
                    check();_write(folder/relative,data);entry=_entry(folder,relative,role);used+=entry['bytes'];entries.append(entry)
                if used>max_bytes:raise RecoveryError('Backup exceeds byte limit')
                unchanged()
                manifest={'format':FORMAT,'version':VERSION,'created_at':datetime.now(timezone.utc).isoformat(),'runtime':{'python':platform.python_version(),'platform':platform.system()},'cache_policy':'included' if include_vectors else 'omitted','not_included':missing,'entries':entries}
                _write(folder/'manifest.json',(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode())
        return {'directory':str(output),'files':len(entries),'bytes':used,'cache_policy':manifest['cache_policy']}

def _manifest(folder,max_bytes):
    folder=plain_path(folder,directory=True);raw=_read_small(folder/'manifest.json');manifest=_json(raw)
    if not isinstance(manifest,dict) or set(manifest)!={'format','version','created_at','runtime','cache_policy','not_included','entries'} or manifest['format']!=FORMAT or type(manifest['version']) is not int or manifest['version']!=VERSION:raise RecoveryError('Unsupported backup format/version')
    if manifest['cache_policy'] not in ('included','omitted') or not isinstance(manifest['created_at'],str) or len(manifest['created_at'])>64:raise RecoveryError('Invalid manifest metadata')
    if not isinstance(manifest['runtime'],dict) or set(manifest['runtime'])!={'python','platform'} or any(not isinstance(v,str) or len(v)>64 for v in manifest['runtime'].values()):raise RecoveryError('Invalid runtime metadata')
    missing=manifest['not_included']
    if not isinstance(missing,list) or any(v not in ('ai_settings','viewer_settings','profiles','tagger_profiles') for v in missing) or len(set(missing))!=len(missing):raise RecoveryError('Invalid omitted settings')
    entries=manifest['entries']
    if not isinstance(entries,list) or not 1<=len(entries)<=MAX_FILES:raise RecoveryError('Invalid file count')
    seen=set();counts={};total=0
    for entry in entries:
        if not isinstance(entry,dict):raise RecoveryError('Invalid file entry')
        role=entry.get('role');expected={'path','role','bytes','sha256'}|({'schema'} if role in ('catalog','vectors') else set())|({'profile'} if role=='vectors' else set())
        if set(entry)!=expected:raise RecoveryError('Invalid file entry fields')
        name=entry['path'];size=entry['bytes'];digest=entry['sha256']
        if not isinstance(name,str) or not isinstance(digest,str) or re.fullmatch('[0-9a-f]{64}',digest) is None or type(size) is not int or size<0:raise RecoveryError('Invalid file identity')
        relative=CATALOG if role=='catalog' else CATALOG+_profile_suffix(entry['profile']) if role=='vectors' else 'settings/ai-settings.json' if role=='ai_settings' else 'settings/viewer-settings.json' if role=='viewer_settings' else name if role=='profile' and re.fullmatch(r'profiles/[A-Za-z0-9][A-Za-z0-9._-]{0,63}\.json',name) else name if role=='tagger_profile' and re.fullmatch(r'tagger-profiles/[A-Za-z0-9][A-Za-z0-9._-]{0,63}\.json',name) else None
        if name!=relative or name.casefold() in seen:raise RecoveryError('Unsafe or duplicate backup path')
        if role in ('catalog','vectors') and (not isinstance(entry['schema'],str) or re.fullmatch('[0-9a-f]{64}',entry['schema']) is None):raise RecoveryError('Invalid schema identity')
        seen.add(name.casefold());counts[role]=counts.get(role,0)+1;total+=size
        if total>max_bytes:raise RecoveryError('Backup exceeds byte limit')
    if counts.get('catalog')!=1 or counts.get('vectors',0)>64 or counts.get('profile',0)>64 or counts.get('tagger_profile',0)>16 or any(counts.get(role,0)>1 for role in ('ai_settings','viewer_settings')):raise RecoveryError('Invalid role counts')
    if any((role in missing)!=(counts.get(role,0)==0) for role in ('ai_settings','viewer_settings')):raise RecoveryError('Missing settings declaration')
    if manifest['cache_policy']=='omitted' and counts.get('vectors',0) or any(role in missing and counts.get({'profiles':'profile','tagger_profiles':'tagger_profile'}.get(role,role),0) for role in missing):raise RecoveryError('Conflicting cache/settings policy')
    return manifest,hashlib.sha256(raw).hexdigest(),total

def _sealed(path):
    if any(Path(str(path)+suffix).exists() or Path(str(path)+suffix).is_symlink() for suffix in ('-wal','-shm','-journal')):
        raise RecoveryError('Backup payload has live SQLite companion files')

def restore(bundle,output,*,without_vectors=False,max_bytes=DEFAULT_MAX_BYTES,cancelled=None):
    max_bytes=_budget(max_bytes)
    if type(without_vectors) is not bool:raise RecoveryError('Invalid restore policy')
    bundle=plain_path(bundle,directory=True);manifest,manifest_hash,total=_manifest(bundle,max_bytes)
    output=Path(os.path.abspath(output))
    if output==bundle or output in bundle.parents or bundle in output.parents:raise RecoveryError('Restore output overlaps backup')
    entries=[entry for entry in manifest['entries'] if not without_vectors or entry['role']!='vectors']
    def check():
        if cancelled is not None and cancelled():raise InterruptedError('Restore cancelled')
    # Validate every requested payload before creating a destination. Explicit
    # cache omission may recover manual metadata even if derived files are gone.
    for entry in entries:
        check();path=bundle/entry['path']
        if _hash(path)!=(entry['bytes'],entry['sha256']):raise RecoveryError('Backup hash/size mismatch')
        if entry['role'] in ('catalog','vectors'):
            _sealed(path)
            if _database(path,entry['role'])!=(entry['schema'],entry.get('profile')):raise RecoveryError('Backup schema/profile mismatch')
        else:_configuration(entry['role'],_read_small(path,16384))
    with _output(output,total) as folder:
        with storage_lease(folder/CATALOG):
            for entry in entries:
                check();source=plain_path(bundle/entry['path']);target=folder/entry['path'];target.parent.mkdir(parents=True,exist_ok=True)
                with source.open('rb') as reader,target.open('xb') as writer:
                    copied=0
                    while chunk:=reader.read(1024*1024):
                        check();copied+=len(chunk)
                        if copied>entry['bytes']:raise RecoveryError('Backup file grew during restore')
                        writer.write(chunk)
                    writer.flush();os.fsync(writer.fileno())
                if _hash(target)!=(entry['bytes'],entry['sha256']):raise RecoveryError('Restore copy changed')
                if entry['role'] in ('catalog','vectors'):
                    _sealed(source)
                    try:
                        with closing(sqlite3.connect(target)) as db:db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                    except Exception:pass
            check()
            if hashlib.sha256(_read_small(bundle/'manifest.json')).hexdigest()!=manifest_hash:raise RecoveryError('Backup manifest changed')
            report={'format':'aredoko-restored','version':1,'source_manifest_sha256':manifest_hash,'cache_policy':'omitted' if without_vectors else manifest['cache_policy'],'automatic_resume':False,'requires_source_revalidation':True,'not_included':manifest['not_included'],'runtime':manifest['runtime'],'entries':entries}
            _write(folder/'recovery.json',(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
    return {'directory':str(output),'catalog':str(output/CATALOG),'files':len(entries),'cache_policy':report['cache_policy'],'requires_source_revalidation':True,'automatic_resume':False}
