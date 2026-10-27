"""Atomic, time-grounded direct-video vectors in an explicit video namespace.

Decode/encode stages are private and bounded. The caller supplies an owned
encoder; this module never selects a model, starts a job, or alters the active
image/text profile. Only a verified successful whole item becomes visible.
"""
from array import array
from contextlib import closing,contextmanager
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

from ai_profiles import VIDEO_VECTOR_CONTRACT
from ai_vectors import normalized
from video_input import MAX_FRAMES,MAX_START_MS,validate_video
from video_previews import MediaDecodeCancelled
from previews import PreviewReader,ReaderChanged

CONTRACT='direct-video-window:v1'
TABLES=(
    '''CREATE TABLE IF NOT EXISTS ai_video_direct_sources(
        item_id INTEGER PRIMARY KEY,source_revision TEXT NOT NULL,contract TEXT NOT NULL,
        decoded_windows INTEGER NOT NULL,indexed_windows INTEGER NOT NULL,total_frames INTEGER NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS ai_video_direct_windows(
        item_id INTEGER NOT NULL,ordinal INTEGER NOT NULL,start_ms INTEGER NOT NULL,
        end_ms INTEGER NOT NULL,vector BLOB NOT NULL,PRIMARY KEY(item_id,ordinal))''')
MAX_WINDOWS=MAX_START_MS//(MAX_FRAMES*1000)
# A 24h item stages at most 5400 float32 vectors of the profile dimension.
STAGE_BYTES=32*1024*1024


class VideoDirectIndex:
    def __init__(self,catalog,encoder,*,reader=None,stage_parent=None):
        profile=encoder.profile
        if profile.modalities!=('text','video') or profile.vector_contract!=VIDEO_VECTOR_CONTRACT:
            raise ValueError('An explicit direct-video encoder namespace is required')
        self.catalog,self.encoder,self.profile=catalog,encoder,profile
        self.reader=reader if reader is not None else PreviewReader(catalog)
        self.stage_parent=stage_parent
        from ai_search import VectorStore
        # The same catalog guard -> writer fence order as live capture. A backup
        # cannot discover a newly created sidecar between schema statements.
        with self._boundary(None),catalog.writer_fence.write():
            self.store=VectorStore(profile.store_path(catalog.path),profile,writer_fence=catalog.writer_fence)
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                for statement in TABLES:db.execute(statement)
                db.execute('PRAGMA user_version=1')

    @staticmethod
    def _check(cancel):
        if cancel is not None and cancel.is_set():raise MediaDecodeCancelled('Video index cancelled before publication')

    @contextmanager
    def _boundary(self,cancel):
        while not self.catalog._guard.acquire(timeout=.05):self._check(cancel)
        try:self._check(cancel);yield
        finally:self.catalog._guard.release()

    def fresh(self,item_id,revision):
        with self.store.connect() as db:
            return db.execute('SELECT 1 FROM ai_video_direct_sources WHERE item_id=? AND source_revision=? AND contract=?',
                              (item_id,revision,CONTRACT)).fetchone() is not None

    def index_item(self,item_id,revision,*,cancel=None,validate=None):
        if type(item_id) is not int or not 1<=item_id<=9223372036854775807:raise ValueError('Invalid video item')
        if type(revision) is not str or re.fullmatch('[0-9a-f]{64}',revision) is None:raise ValueError('Invalid video revision')
        self._check(cancel)
        if validate is not None:
            if not callable(validate):raise ValueError('Invalid video publication validator')
            validate()
        if self.encoder.profile.key!=self.profile.key:raise ValueError('Video encoder profile changed')
        with tempfile.TemporaryDirectory(prefix='aredoko-video-stage-',dir=self.stage_parent) as temporary:
            path=Path(temporary)/'stage.sqlite'
            with closing(sqlite3.connect(path)) as stage:
                stage.execute('PRAGMA page_size=4096')
                stage.execute('PRAGMA journal_mode=MEMORY')
                stage.execute('PRAGMA cache_size=-1024')
                stage.execute('PRAGMA max_page_count='+str(STAGE_BYTES//4096))
                stage.execute('CREATE TABLE windows(ordinal INTEGER PRIMARY KEY,start_ms INTEGER,end_ms INTEGER,vector BLOB)')
                decoded=indexed=frames=0;expected_start=0;short_seen=False
                with self.reader.video_coverage_stream(item_id,revision,cancel) as windows:
                    for window in windows:
                        self._check(cancel)
                        validate_video(window)
                        # One forward coverage from the probed plan: contiguous
                        # windows, only the final one may be shorter than the
                        # MAX_FRAMES bound, and no window is ever skipped.
                        duration=window.end_ms-window.start_ms
                        if (decoded>=MAX_WINDOWS or short_seen or window.start_ms!=expected_start
                                or not 1<=duration<=MAX_FRAMES*1000):
                            raise ValueError('Invalid direct-video window sequence')
                        short_seen=duration<MAX_FRAMES*1000
                        expected_start=window.end_ms
                        decoded+=1;frames+=len(window.frames)
                        vector=normalized(self.encoder.encode('video',window),self.profile.dimension)
                        self._check(cancel)
                        packed=array('f',vector)
                        if sys.byteorder!='little':packed.byteswap()
                        stage.execute('INSERT INTO windows VALUES(?,?,?,?)',
                            (decoded-1,window.start_ms,window.end_ms,packed.tobytes()))
                        indexed+=1
                if not decoded:raise ValueError('Empty video coverage cannot be published')
                stage.commit()
                try:self._publish(item_id,revision,path,decoded,indexed,frames,cancel,validate)
                except InterruptedError:
                    self._check(cancel)
                    raise
            return {'item_id':item_id,'revision':revision,'decoded_windows':decoded,
                    'indexed_windows':indexed,'total_frames':frames,'contract':CONTRACT}

    def _publish(self,item_id,revision,path,decoded,indexed,frames,cancel,validate):
        def check_source():
            self._check(cancel)
            if validate is not None:validate()
            if self.encoder.profile.key!=self.profile.key:raise ValueError('Video encoder namespace changed')
            if self.reader.video_manifest(item_id)['revision']!=revision:
                raise ReaderChanged('Video source changed before index publication')
            self._check(cancel)
        with self._boundary(cancel),self.catalog.writer_fence.write(cancelled=lambda:cancel is not None and cancel.is_set()):
            check_source()
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('DELETE FROM ai_video_direct_windows WHERE item_id=?',(item_id,))
                db.execute('DELETE FROM ai_video_direct_sources WHERE item_id=?',(item_id,))
                db.execute('INSERT INTO ai_video_direct_sources VALUES(?,?,?,?,?,?)',
                           (item_id,revision,CONTRACT,decoded,indexed,frames))
                # An explicit read-only connection avoids ATTACH inheriting the
                # primary connection's URI policy on Windows. At most 64 vectors
                # escape the stage cursor; the target transaction stays atomic.
                with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as stage:
                    cursor=stage.execute('SELECT ordinal,start_ms,end_ms,vector FROM windows ORDER BY ordinal')
                    while rows:=cursor.fetchmany(64):
                        self._check(cancel)
                        db.executemany('INSERT INTO ai_video_direct_windows VALUES(?,?,?,?,?)',
                                       ((item_id,*row) for row in rows))
                # File changes/cancel while copying roll back to the prior item.
                check_source()
