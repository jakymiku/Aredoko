"""Atomic, time-grounded direct-audio vectors in an explicit audio namespace.

Decode/encode stages are private and bounded. The caller supplies an owned
encoder; this module never selects a model, starts a job, or alters the active
image/text profile. Only a verified successful whole item becomes visible.
The explicit source_kind='video' option extracts the first audio track while
keeping the existing text/audio profile; video RGB vectors remain separate.
"""
from array import array
from contextlib import closing,contextmanager
import re
import math
import sqlite3
import sys
import tempfile
from pathlib import Path

from ai_profiles import AUDIO_VECTOR_CONTRACT
from ai_vectors import normalized
from audio_input import SAMPLE_RATE,MAX_WINDOW_MS,MAX_START_MS,MediaDecodeCancelled,validate_pcm
from previews import PreviewReader,ReaderChanged

CONTRACT='direct-audio-window:v1'
TABLES=(
    '''CREATE TABLE IF NOT EXISTS ai_audio_direct_sources(
        item_id INTEGER PRIMARY KEY,source_revision TEXT NOT NULL,contract TEXT NOT NULL,
        decoded_windows INTEGER NOT NULL,indexed_windows INTEGER NOT NULL,total_frames INTEGER NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS ai_audio_direct_windows(
        item_id INTEGER NOT NULL,ordinal INTEGER NOT NULL,start_ms INTEGER NOT NULL,
        end_ms INTEGER NOT NULL,vector BLOB NOT NULL,PRIMARY KEY(item_id,ordinal))''')
MAX_WINDOWS=MAX_START_MS//MAX_WINDOW_MS
WINDOW_FRAMES=SAMPLE_RATE*MAX_WINDOW_MS//1000
STAGE_BYTES=16*1024*1024


def valid_marker(decoded,indexed,frames):
    # Silent windows have no vector but still count as decoded coverage.
    return (all(type(value) is int for value in (decoded,indexed,frames))
            and 0<=indexed<=decoded<=MAX_WINDOWS
            and 1<=frames<=MAX_START_MS*SAMPLE_RATE//1000
            and decoded==(frames+WINDOW_FRAMES-1)//WINDOW_FRAMES)


def valid_interval(ordinal,start,end,decoded,frames):
    # Call only after validating the marker. Ordinal gaps may mean silence.
    return (all(type(value) is int for value in (ordinal,start,end))
            and 0<=ordinal<decoded and start==ordinal*MAX_WINDOW_MS
            and start<end==min(start+MAX_WINDOW_MS,(frames*1000+SAMPLE_RATE-1)//SAMPLE_RATE))


class AudioDirectIndex:
    def __init__(self,catalog,encoder,*,reader=None,stage_parent=None,init_cancel=None,source_kind='audio'):
        if type(source_kind) is not str or source_kind not in ('audio','video'):raise ValueError('Invalid audio source kind')
        self._source_kind=source_kind
        profile=encoder.profile
        if profile.modalities!=('text','audio') or profile.vector_contract!=AUDIO_VECTOR_CONTRACT:
            raise ValueError('An explicit direct-audio encoder namespace is required')
        self.catalog,self.encoder,self.profile=catalog,encoder,profile
        self.reader=reader if reader is not None else PreviewReader(catalog)
        self.stage_parent=stage_parent
        from ai_search import VectorStore
        # The same catalog guard -> writer fence order as live capture. A backup
        # cannot discover a newly created sidecar between schema statements.
        with self._boundary(init_cancel),catalog.writer_fence.write(cancelled=lambda:init_cancel is not None and init_cancel.is_set()):
            self._check(init_cancel)
            self.store=VectorStore(profile.store_path(catalog.path),profile,writer_fence=catalog.writer_fence)
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                for statement in TABLES:db.execute(statement)
                db.execute('PRAGMA user_version=1')
                self._check(init_cancel)

    @staticmethod
    def _check(cancel):
        if cancel is not None and cancel.is_set():raise MediaDecodeCancelled('Audio index cancelled before publication')

    @property
    def source_kind(self):return self._source_kind

    def manifest(self,item_id):
        return (self.reader.video_manifest if self.source_kind=='video' else self.reader.audio_manifest)(item_id)

    def pcm_stream(self,item_id,revision,cancel=None):
        return (self.reader.video_audio_pcm_stream if self.source_kind=='video' else self.reader.audio_pcm_stream)(item_id,revision,cancel)

    @contextmanager
    def _boundary(self,cancel):
        while not self.catalog._guard.acquire(timeout=.05):self._check(cancel)
        try:self._check(cancel);yield
        finally:self.catalog._guard.release()

    def fresh(self,item_id,revision,*,cancel=None):
        # A matching success marker cannot certify missing or damaged vectors.
        # Validate one stored window at a time, without decoding or inference.
        self._check(cancel)
        with self.store.connect() as db:
            marker=db.execute('SELECT decoded_windows,indexed_windows,total_frames FROM ai_audio_direct_sources '
                              'WHERE item_id=? AND source_revision=? AND contract=?',(item_id,revision,CONTRACT)).fetchone()
            if marker is None or not valid_marker(*marker):return False
            decoded,indexed,frames=marker;count=0
            with closing(db.execute('SELECT ordinal,start_ms,end_ms,vector FROM ai_audio_direct_windows '
                                    'WHERE item_id=? ORDER BY ordinal',(item_id,))) as cursor:
                for ordinal,start,end,data in cursor:
                    self._check(cancel)
                    if (count>=indexed or not valid_interval(ordinal,start,end,decoded,frames)
                            or type(data) is not bytes or len(data)!=self.profile.dimension*4):return False
                    values=array('f');values.frombytes(data)
                    if sys.byteorder!='little':values.byteswap()
                    norm=sum(value*value for value in values)
                    if not math.isfinite(norm) or abs(norm-1)>1e-4:return False
                    count+=1
            self._check(cancel)
            return count==indexed

    def index_item(self,item_id,revision,*,cancel=None,validate=None,publication_guard=None,on_published=None,progress=None):
        if type(item_id) is not int or not 1<=item_id<=9223372036854775807:raise ValueError('Invalid audio item')
        if type(revision) is not str or re.fullmatch('[0-9a-f]{64}',revision) is None:raise ValueError('Invalid audio revision')
        self._check(cancel)
        if validate is not None:
            if not callable(validate):raise ValueError('Invalid audio publication validator')
            validate()
        if on_published is not None and (publication_guard is None or not callable(on_published)):
            raise ValueError('Invalid audio publication callback')
        if progress is not None and not callable(progress):raise ValueError('Invalid audio progress callback')
        if self.encoder.profile.key!=self.profile.key:raise ValueError('Audio encoder profile changed')
        with tempfile.TemporaryDirectory(prefix='aredoko-audio-stage-',dir=self.stage_parent) as temporary:
            path=Path(temporary)/'stage.sqlite'
            with closing(sqlite3.connect(path)) as stage:
                stage.execute('PRAGMA page_size=4096')
                stage.execute('PRAGMA journal_mode=MEMORY')
                stage.execute('PRAGMA cache_size=-1024')
                stage.execute('PRAGMA max_page_count='+str(STAGE_BYTES//4096))
                stage.execute('CREATE TABLE windows(ordinal INTEGER PRIMARY KEY,start_ms INTEGER,end_ms INTEGER,vector BLOB)')
                decoded=indexed=frames=prepared_ms=prepared_windows=0
                def report(phase,total=None):
                    if progress is None:return
                    self._check(cancel)
                    progress({'item_id':item_id,'prepared_ms':prepared_ms,'total_ms':total,
                              'prepared_windows':prepared_windows,'phase':phase})
                    self._check(cancel)
                with self.pcm_stream(item_id,revision,cancel) as stream:
                    report('decoding')
                    for window in stream:
                        self._check(cancel)
                        validate_pcm(window)
                        # One forward 30s producer, no repeat/overlap or unbounded
                        # custom tiny windows in this persistent index contract.
                        if (decoded>=MAX_WINDOWS or frames%WINDOW_FRAMES or window.start_ms!=frames*1000//SAMPLE_RATE
                                or window.requested_duration_ms!=MAX_WINDOW_MS):
                            raise ValueError('Invalid direct-audio window sequence')
                        decoded+=1;frames+=window.frame_count
                        if frames>MAX_START_MS*SAMPLE_RATE//1000:raise ValueError('Audio exceeds duration limit')
                        if not window.is_digital_silence:
                            report('encoding')
                            vector=normalized(self.encoder.encode('audio',window),self.profile.dimension)
                            self._check(cancel)
                            packed=array('f',vector)
                            if sys.byteorder!='little':packed.byteswap()
                            end_ms=(frames*1000+SAMPLE_RATE-1)//SAMPLE_RATE
                            stage.execute('INSERT INTO windows VALUES(?,?,?,?)',
                                (decoded-1,window.start_ms,end_ms,packed.tobytes()))
                            indexed+=1
                        # Silence advances decoded coverage without inference.
                        prepared_ms=(frames*1000+SAMPLE_RATE-1)//SAMPLE_RATE
                        prepared_windows=decoded
                        report('decoding')
                    if not stream.complete or not frames:raise ValueError('Incomplete audio input cannot be published')
                stage.commit()
                report('saving',prepared_ms)
                try:self._publish(item_id,revision,path,decoded,indexed,frames,cancel,validate,publication_guard,on_published)
                except InterruptedError:
                    self._check(cancel)
                    raise
            return {'item_id':item_id,'revision':revision,'decoded_windows':decoded,
                    'indexed_windows':indexed,'total_frames':frames,'contract':CONTRACT}

    def _publish(self,item_id,revision,path,decoded,indexed,frames,cancel,validate,publication_guard,on_published):
        def check_source():
            self._check(cancel)
            if validate is not None:validate()
            if self.encoder.profile.key!=self.profile.key:raise ValueError('Audio encoder namespace changed')
            if self.manifest(item_id)['revision']!=revision:
                raise ReaderChanged('Audio source changed before index publication')
            self._check(cancel)
        with self._boundary(cancel),self.catalog.writer_fence.write(cancelled=lambda:cancel is not None and cancel.is_set()):
            check_source()
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('DELETE FROM ai_audio_direct_windows WHERE item_id=?',(item_id,))
                db.execute('DELETE FROM ai_audio_direct_sources WHERE item_id=?',(item_id,))
                db.execute('INSERT INTO ai_audio_direct_sources VALUES(?,?,?,?,?,?)',
                           (item_id,revision,CONTRACT,decoded,indexed,frames))
                # An explicit read-only connection avoids ATTACH inheriting the
                # primary connection's URI policy on Windows. At most 64 vectors
                # escape the stage cursor; the target transaction stays atomic.
                with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as stage:
                    cursor=stage.execute('SELECT ordinal,start_ms,end_ms,vector FROM windows ORDER BY ordinal')
                    while rows:=cursor.fetchmany(64):
                        self._check(cancel)
                        db.executemany('INSERT INTO ai_audio_direct_windows VALUES(?,?,?,?,?)',
                                       ((item_id,*row) for row in rows))
                # Staging and copying do not hold the cancellation gate. The
                # final check and commit are one decision with job cancellation.
                def commit():
                    check_source()
                    db.commit()
                    if on_published is not None:on_published()
                if publication_guard is None:commit()
                else:
                    with publication_guard:commit()
