"""Online capture primitive. Caller MUST quiesce every logical writer owner.

Production callers use the shared writer fence. Media/runtime/model/thumbnail
files are never read; frontend settings may be supplied as validated bytes.
"""
from contextlib import ExitStack,closing
from dataclasses import dataclass
from pathlib import Path
import os,secrets,shutil,sqlite3,time
from storage_backup import (backup,_budget,_stores,_profiles,_read_small,_configuration,
                            _write,_profile_suffix,_database,DEFAULT_MAX_BYTES,RecoveryError,CATALOG,NAME)
from storage_lease import plain_path,identity,StorageBusyError

@dataclass(frozen=True)
class BackupSelection:
    settings:bool=True
    history:bool=True
    reader_progress:bool=True
    vectors:bool=False
    def __post_init__(self):
        if any(type(value) is not bool for value in (self.settings,self.history,self.reader_progress,self.vectors)):raise RecoveryError('Invalid backup selection')


def capture_live(catalog,output,*,quiesce,selection=BackupSelection(),settings=None,viewer_settings=None,
                 profiles=None,extra_profiles=(),tagger_profiles=(),viewer_data=None,max_bytes=DEFAULT_MAX_BYTES,
                 cancelled=None,progress=None,publish=None):
    if not isinstance(selection,BackupSelection) or not callable(quiesce):raise RecoveryError('Explicit writer coordination required')
    if viewer_data is not None:
        if viewer_settings is not None or not isinstance(viewer_data,bytes):raise RecoveryError('Invalid viewer snapshot')
        _configuration('viewer_settings',viewer_data)
    limit=_budget(max_bytes);source=plain_path(catalog.path);output=plain_path(Path(os.path.abspath(output)),missing=True,directory=True)
    if output.exists():raise RecoveryError('Output must be a new directory')
    parent=plain_path(output.parent,directory=True)
    stage=parent/('.aredoko-capture-'+secrets.token_hex(16));stage.mkdir(mode=0o700);owned=identity(stage)
    def check():
        if cancelled is not None and cancelled():raise InterruptedError('Backup cancelled')
    def report(stage_name,done=0,total=None):
        check()
        if progress is not None:progress({'stage':stage_name,'bytes_done':done,'bytes_total':total})
    try:
        report('waiting')
        # Safe operation boundaries, not a raw file copy of a live SQLite DB.
        with catalog._guard,quiesce(cancelled=cancelled),ExitStack() as stack:
            catalog._require_idle();check();report('capturing')
            stores=_stores(source) if selection.vectors else []
            paths=[source,*stores];sources=[];reserved=[];configs=[];config_sources=[];directory_profiles=[]
            if selection.settings:
                for role,path,relative,budget in [('ai_settings',settings,'settings/ai-settings.json',16384),('viewer_settings',viewer_settings,'settings/viewer-settings.json',2048)]:
                    if path is not None:
                        data=_read_small(path,budget);_configuration(role,data);configs.append((relative,data,role));config_sources.append((path,data,budget))
                if viewer_data is not None:configs.append(('settings/viewer-settings.json',viewer_data,'viewer_settings'))
                directory_profiles=_profiles(profiles)
                for path in [*directory_profiles,*map(plain_path,extra_profiles)]:
                    data=_read_small(path,16384);_configuration('profile',data);configs.append(('profiles/'+path.name,data,'profile'));config_sources.append((path,data,16384))
                for path in map(plain_path,tagger_profiles):
                    data=_read_small(path,16384);_configuration('tagger_profile',data);configs.append(('tagger-profiles/'+path.name,data,'tagger_profile'));config_sources.append((path,data,16384))
            names=[relative.casefold() for relative,_,_ in configs]
            if len(set(names))!=len(names) or sum(role=='profile' for _,_,role in configs)>64 or sum(role=='tagger_profile' for _,_,role in configs)>16:raise RecoveryError('Duplicate or excessive profiles')
            if any(role in ('profile','tagger_profile') and NAME.fullmatch(Path(relative).name) is None for relative,_,role in configs):raise RecoveryError('Invalid profile filename')
            for path in paths:
                expected=identity(path);guard=stack.enter_context(closing(sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=1)))
                try:guard.execute('BEGIN IMMEDIATE')
                except sqlite3.OperationalError as error:raise StorageBusyError('Database busy at backup boundary') from error
                stack.callback(guard.rollback);reserved.append((path,guard,expected))
            # Reserve every database before pinning any reader, including
            # cooperating external SQLite writers, so the cut is cross-DB.
            for path,_,expected in reserved:
                reader=stack.enter_context(closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=1)))
                reader.execute('PRAGMA trusted_schema=OFF');reader.execute('BEGIN');reader.execute('SELECT count(*) FROM sqlite_schema').fetchone()
                if identity(path)!=expected:raise RecoveryError('Database identity changed during capture')
                sources.append((path,reader,expected))
            estimate=sum(db.execute('PRAGMA page_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0] for _,db,_ in sources)+sum(len(data) for _,data,_ in configs)
            if estimate>limit:raise RecoveryError('Backup exceeds byte limit')
            if shutil.disk_usage(parent).free<3*estimate+16*1024**2:raise RecoveryError('Insufficient free space')
            # All read snapshots are pinned while writers were reserved. Once
            # pinned, SQLite readers can copy without exclusive writer locks.
            for _,guard,_ in reserved:guard.rollback()
            started=time.monotonic();done=0
            for index,(path,reader,expected) in enumerate(sources):
                role='catalog' if index==0 else 'vectors'
                relative=CATALOG if index==0 else CATALOG+_profile_suffix(_database(path,role)[1])
                with closing(sqlite3.connect(stage/relative)) as target:
                    page_size=reader.execute('PRAGMA page_size').fetchone()[0]
                    def copying(status,remaining,total):
                        check()
                        if status in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED):raise StorageBusyError('Snapshot blocked')
                        if done+total*page_size>limit:raise RecoveryError('Backup exceeds byte limit')
                        if time.monotonic()-started>600:raise RecoveryError('Capture time limit exceeded')
                        report('capturing',done+(total-remaining)*page_size,estimate)
                    reader.backup(target,pages=256,progress=copying,sleep=.01);target.execute('PRAGMA journal_mode=DELETE');target.commit()
                done+=(stage/relative).stat().st_size
                if identity(path)!=expected:raise RecoveryError('Database identity changed during capture')
                check();_database(stage/relative,role)
            for relative,data,_ in configs:_write(stage/relative,data)
            if selection.settings:
                if _profiles(profiles)!=directory_profiles:raise RecoveryError('Profile membership changed during capture')
                for path,data,budget in config_sources:
                    if _read_small(path,budget)!=data:raise RecoveryError('Settings changed during capture')
            # Source reader transactions close here; no long-lived WAL snapshot
            # remains while the sealed staging databases are packaged/hashed.
        report('packing')
        result=backup(stage/CATALOG,output,
            settings=stage/'settings/ai-settings.json' if any(role=='ai_settings' for _,_,role in configs) else None,
            viewer_settings=stage/'settings/viewer-settings.json' if any(role=='viewer_settings' for _,_,role in configs) else None,
            profiles=stage/'profiles' if (stage/'profiles').is_dir() else None,
            tagger_profiles=list((stage/'tagger-profiles').glob('*.json')) if (stage/'tagger-profiles').is_dir() else (),
            include_vectors=selection.vectors,include_history=selection.history,include_reader_progress=selection.reader_progress,
            max_bytes=limit,cancelled=cancelled,publish=publish)
        return {**result,'selection':{'settings':selection.settings,'history':selection.history,'reader_progress':selection.reader_progress,'vectors':selection.vectors}}
    finally:
        # Recursive cleanup is restricted to the freshly created absolute
        # staging child and its original physical identity. Never remove output.
        if stage.exists():
            if stage.parent!=parent or not stage.is_absolute() or plain_path(stage,directory=True)!=stage or identity(stage)!=owned:raise RecoveryError('Capture staging identity changed; kept untouched')
            shutil.rmtree(stage)
