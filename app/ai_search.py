"""Small, resumable semantic-search slice; source media remain read-only."""
from array import array
from contextlib import contextmanager, nullcontext, closing
import hashlib
import json
import math
import operator
from pathlib import Path
import sqlite3
import sys
import threading
import time
import traceback
import native_accel
from ai_process import AIUnavailable
from ai_profiles import DEFAULT_PROFILE
from runtime_paths import runtime_verification_status
from ai_vectors import normalized
from ai_ranking import POLICIES,fuse_modalities
from library_index import TYPES, _excluded
from media_filters import QUERY_KINDS,kind_clause
from ai_scope import validate_scope, scope_clause
from writer_fence import ConnectionWriteFence
from inference_ownership import InferenceOwnership
from search_terms import normalize, normalize_tags
from ai_result_groups import boundary
from ai_score_spool import ScoreSpool, ScoreSpoolError, SearchCancelled
from previews import PreviewReader, PreviewUnavailable, PreviewBusyError, ReaderChanged
from search_requests import SearchRequests
from index_continuation import IndexContinuation, JOB as CONTINUATION_JOB, public_state
from tag_semantics import PendingTagVectors
from page_semantics import CONTRACT as PAGE_CONTRACT, PageVectors, SCHEMA as PAGE_VECTOR_SCHEMA, unpack as unpack_page_vector
from audio_semantics import AudioSpeechVectors, SCHEMA as AUDIO_SEGMENT_SCHEMA
from audio_acoustics import AudioAcousticVectors, SCHEMA as AUDIO_ACOUSTIC_SCHEMA

MAX_ITEMS=1_000_000
ROW_BATCH_SIZE=256
PROGRESS_INTERVAL=16
# Input preprocessing is independent of the embedding model/vector space. Old
# text vectors stay reusable; images/video need one explicit rebuild after the
# representative-frame implementations change.
IMAGE_SOURCE_CONTRACT='representative-image:v1'
VIDEO_SOURCE_CONTRACT='timecoded-video:v1'
class AIBusy(RuntimeError): pass

def source_contract(row,profile):
    if 'cover' not in profile.modalities:return None
    return {'image':IMAGE_SOURCE_CONTRACT,'video':VIDEO_SOURCE_CONTRACT}.get(row.get('kind'))

def revision(row):
    fields=[row['root_id'],row['relative_path'],row['size_bytes'],row['mtime_ns'],row['title'],row['tags']]
    return hashlib.sha256(json.dumps(fields,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

CURRENT_VECTOR_STORE_USER_VERSION = 1

class VectorStore:
    def __init__(self,path,profile=DEFAULT_PROFILE,*,writer_fence=None):
        self.path=Path(path)
        self.profile=profile
        self.dimension=profile.dimension
        self.writer_fence=writer_fence
        if self.path.exists() and self.path.stat().st_size > 0:
            with closing(sqlite3.connect(self.path, timeout=5)) as check_db:
                ver = check_db.execute('PRAGMA user_version').fetchone()[0]
                supported=CURRENT_VECTOR_STORE_USER_VERSION
                # Historical in-catalog vector tables share the catalog's version;
                # Standalone v1 adds direct-audio tables; legacy stores stay v0.
                if ver in (1,2,3):
                    tables={row[0] for row in check_db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    if {'production_marker','items','item_locations','library_roots','shelves','item_shelves','root_shelves'}<=tables and (ver==1 or 'registered_root_preferences' in tables):supported=ver
                if ver > supported:
                    raise AIUnavailable(f'Unsupported vector store user_version {ver} > {supported}; please update Aredoko.')
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS ai_profile(value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS ai_vectors(item_id INTEGER NOT NULL, revision TEXT NOT NULL,
                    modality TEXT NOT NULL, vector BLOB NOT NULL, PRIMARY KEY(item_id,modality));
                CREATE TABLE IF NOT EXISTS ai_proposal_vectors(item_id INTEGER PRIMARY KEY,batch_id INTEGER NOT NULL,
                    source_revision TEXT NOT NULL,signature TEXT NOT NULL,vector BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS ai_video_frames(item_id INTEGER NOT NULL, revision TEXT NOT NULL,
                    at_ms INTEGER NOT NULL CHECK(at_ms>=0 AND at_ms<=86400000), vector BLOB NOT NULL,
                    PRIMARY KEY(item_id,at_ms));
                CREATE TABLE IF NOT EXISTS ai_source_contracts(item_id INTEGER PRIMARY KEY,
                    revision TEXT NOT NULL, contract TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS ai_state(id INTEGER PRIMARY KEY CHECK(id=1), json TEXT NOT NULL);
            ''')
            db.executescript(PAGE_VECTOR_SCHEMA)
            db.executescript(AUDIO_SEGMENT_SCHEMA)
            db.executescript(AUDIO_ACOUSTIC_SCHEMA)
            profile=db.execute('SELECT value FROM ai_profile').fetchone()
            if profile and profile[0]!=self.profile.key: raise AIUnavailable('Vector profile mismatch')
            if not profile: db.execute('INSERT INTO ai_profile VALUES(?)',(self.profile.key,))
        state=self.state()
        if state.get('state') in ('running','cancelling'):
            self.save_state({**state,'state':'interrupted','error':'索引作成が中断されました。再実行で保存済み分から続けられます。'})
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=2)
        fenced=ConnectionWriteFence(self.writer_fence) if self.writer_fence is not None else None
        if fenced is not None:db.set_authorizer(fenced.authorize)
        try:
            with db:yield db
        finally:
            try:db.close()
            finally:
                if fenced is not None:fenced.close()
    def checkpoint(self):
        try:
            with self.connect() as db:
                db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        except Exception:
            pass
    def state(self):
        with self.connect() as db: row=db.execute('SELECT json FROM ai_state WHERE id=1').fetchone()
        return json.loads(row[0]) if row else {'state':'idle','processed':0,'total':0,'indexed':0,'skipped':0,'error':''}
    def save_state(self,state):
        with self.connect() as db: db.execute('INSERT OR REPLACE INTO ai_state VALUES(1,?)',(json.dumps(state,ensure_ascii=False),))
    def fresh_ids(self,rows):
        if not rows:return set()
        if len(rows)>ROW_BATCH_SIZE:raise ValueError('Freshness batch exceeds limit')
        eligible={row['id']:(revision(row),source_contract(row,self.profile)) for row in rows}
        with self.connect() as db:
            records=db.execute("SELECT v.item_id,v.revision,c.revision,c.contract FROM ai_vectors v "
                "LEFT JOIN ai_source_contracts c ON c.item_id=v.item_id WHERE v.modality='text' AND v.item_id IN ("+
                ','.join('?' for _ in eligible)+')',list(eligible)).fetchall()
        return {item_id for item_id,rev,source_rev,contract in records
                if eligible[item_id][0]==rev and (eligible[item_id][1] is None or
                   (source_rev==rev and contract==eligible[item_id][1]))}

    def fresh(self,item_id,rev,contract=None):
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM ai_vectors WHERE item_id=? AND revision=? AND modality='text'",(item_id,rev)).fetchone():return False
            return contract is None or db.execute('SELECT 1 FROM ai_source_contracts WHERE item_id=? AND revision=? AND contract=?',(item_id,rev,contract)).fetchone() is not None
    def fresh_row(self,row):
        return self.fresh(row['id'],revision(row),source_contract(row,self.profile))
    def text(self,row):
        return self._vector(row,'text')
    def texts(self,rows):
        if not rows:return {}
        if len(rows)>ROW_BATCH_SIZE:raise ValueError('Text vector batch exceeds limit')
        expected={row['id']:revision(row) for row in rows}
        with self.connect() as db:
            records=db.execute("SELECT item_id,revision,vector FROM ai_vectors WHERE modality='text' AND item_id IN ("+
                ','.join('?' for _ in expected)+')',list(expected)).fetchall()
        out={}
        for item_id,rev,blob in records:
            if expected.get(item_id)!=rev:continue
            try:
                vec=array('f');vec.frombytes(blob)
                if len(vec)!=self.dimension or any(not math.isfinite(x) for x in vec) or abs(sum(x*x for x in vec)-1)>1e-4:continue
                out[item_id]=normalized(vec,self.dimension)
            except (ValueError,TypeError):continue
        return out
    def put(self,item_id,rev,vectors,video_frames=None,*,source_contract=None):
        self.put_many([(item_id,rev,vectors,video_frames,source_contract)])
    def put_many(self,records):
        if not records:return
        prepared=[]
        for item_id,rev,vectors,video_frames,source_contract in records:
            # Validate every modality before replacing any previous revision atomically.
            if not vectors or any(mode not in self.profile.modalities for mode in vectors):
                raise ValueError('Unsupported vector modality')
            if source_contract is not None and (source_contract not in (IMAGE_SOURCE_CONTRACT,VIDEO_SOURCE_CONTRACT) or 'cover' not in self.profile.modalities):
                raise ValueError('Unsupported source preprocessing')
            packed={mode:array('f',normalized(vec,self.dimension)).tobytes() for mode,vec in vectors.items()}
            packed_frames=[]
            if video_frames:
                if 'cover' not in self.profile.modalities:
                    raise ValueError('Unsupported vector modality')
                for at_ms,vec in video_frames:
                    if type(at_ms) is not int or not 0<=at_ms<=86_400_000:
                        raise ValueError('Invalid video frame timestamp')
                    packed_frames.append((item_id,rev,at_ms,array('f',normalized(vec,self.dimension)).tobytes()))
            prepared.append((item_id,rev,packed,packed_frames,source_contract))
        ids=[entry[0] for entry in prepared]
        marks=','.join('?' for _ in ids)
        vector_rows=[(item_id,rev,mode,data) for item_id,rev,packed,_,_ in prepared for mode,data in packed.items()]
        frame_rows=[row for _,_,_,frames,_ in prepared for row in frames]
        contract_rows=[(item_id,rev,contract) for item_id,rev,_,_,contract in prepared if contract is not None]
        with self.connect() as db:
            db.execute('DELETE FROM ai_vectors WHERE item_id IN ('+marks+')',ids)
            db.execute('DELETE FROM ai_video_frames WHERE item_id IN ('+marks+')',ids)
            db.execute('DELETE FROM ai_source_contracts WHERE item_id IN ('+marks+')',ids)
            db.executemany('INSERT INTO ai_vectors VALUES(?,?,?,?)',vector_rows)
            if frame_rows:
                db.executemany('INSERT INTO ai_video_frames VALUES(?,?,?,?)',frame_rows)
            if contract_rows:
                db.executemany('INSERT INTO ai_source_contracts VALUES(?,?,?)',contract_rows)
    def cover(self,row):
        """Current-profile, current-revision origin; never infer or read media."""
        return self._vector(row,'cover')
    def video_frames(self,row):
        """Current-profile, current-revision video frames [(at_ms, vector), ...]."""
        with self.connect() as db:
            records=db.execute("SELECT at_ms,vector FROM ai_video_frames WHERE item_id=? AND revision=? ORDER BY at_ms",
                               (row['id'],revision(row))).fetchall()
        frames=[]
        for at_ms,data in records:
            if not (isinstance(at_ms,int) and 0<=at_ms<=86_400_000):continue
            try:
                vec=array('f');vec.frombytes(data)
                if len(vec)!=self.dimension or any(not math.isfinite(x) for x in vec) or abs(sum(x*x for x in vec)-1)>1e-4:continue
                frames.append((at_ms,normalized(vec,self.dimension)))
            except (ValueError,TypeError):continue
        if not frames:
            cover=self.cover(row)
            if cover is not None:
                frames=[(0,cover)]
        return frames
    def _vector(self,row,modality):
        with self.connect() as db:
            record=db.execute("SELECT vector FROM ai_vectors WHERE item_id=? AND revision=? AND modality=?",
                              (row['id'],revision(row),modality)).fetchone()
        if record is None:return None
        try:
            vec=array('f');vec.frombytes(record[0])
            if len(vec)!=self.dimension or any(not math.isfinite(x) for x in vec) or abs(sum(x*x for x in vec)-1)>1e-4:return None
            return normalized(vec,self.dimension)
        except (ValueError,TypeError):return None
    def rank_with_content(self,rows,query,source="all",ranking="max",page_scores=None,audio_scores=None):
        if ranking not in POLICIES:raise ValueError('Unknown ranking policy')
        scores,video_hits,page_hits,audio_hits=self.scores_with_content(rows,query,source,page_scores,audio_scores=audio_scores)
        # Keep the whole-pool oracle available; streaming callers fuse only once.
        return fuse_modalities(scores,ranking),video_hits,page_hits
    def scores_with_content(self,rows,query,source="all",page_scores=None,*,query_frames=None,origin_hits=None,audio_scores=None):
        """Raw modality scores with exactly the existing normalization/dot order."""
        if query_frames is not None and len(query_frames)>0:
            active_frames=[(ms,normalized(v,self.dimension)) for ms,v in query_frames]
            is_multi=True
        else:
            active_frames=[(0,normalized(query,self.dimension))]
            is_multi=False
        eligible={row['id']:revision(row) for row in rows}
        video_ids={row['id'] for row in rows if row.get('kind')=='video'}
        scores={}
        video_hits={}
        # Read only candidate IDs; unrelated persisted vectors need not be scanned.
        ids=list(eligible)
        dim=self.dimension
        expect_bytes=dim*4
        use_native=native_accel.available()
        single_meta=[];single_chunks=[]
        multi_meta=[];multi_chunks=[]
        vf_meta=[];vf_chunks=[]
        with self.connect() as db:
            for offset in range(0,len(ids),ROW_BATCH_SIZE):
                batch=ids[offset:offset+ROW_BATCH_SIZE]
                sql='SELECT * FROM ai_vectors WHERE item_id IN ('+','.join('?' for _ in batch)+')'
                for item_id,rev,mode,data in db.execute(sql,batch):
                    if mode not in self.profile.modalities or eligible.get(item_id)!=rev or source!='all' and mode!=source: continue
                    if use_native:
                        if not isinstance(data,(bytes,bytearray,memoryview)) or len(data)!=expect_bytes:continue
                        raw=bytes(data)
                        if is_multi and mode=='cover':
                            multi_meta.append((item_id,mode));multi_chunks.append(raw)
                        else:
                            single_meta.append((item_id,mode));single_chunks.append(raw)
                        continue
                    try:
                        vec=array('f');vec.frombytes(data)
                    except (ValueError,TypeError):continue
                    if len(vec)!=dim: continue
                    sq=sum(map(operator.mul,vec,vec))
                    if not math.isfinite(sq) or abs(sq-1)>1e-4: continue
                    if is_multi and mode=='cover':
                        best_score=None;best_orig_ms=0
                        for orig_ms,orig_vec in active_frames:
                            s=sum(map(operator.mul,orig_vec,vec))
                            if best_score is None or s>best_score:
                                best_score=s;best_orig_ms=orig_ms
                        scores.setdefault(item_id,{})[mode]=best_score
                        if origin_hits is not None:origin_hits[item_id]=best_orig_ms
                    else:
                        score=sum(map(operator.mul,active_frames[0][1],vec))
                        scores.setdefault(item_id,{})[mode]=score
                        if origin_hits is not None and mode=='cover':origin_hits[item_id]=active_frames[0][0]
                if source in ('all','cover') and 'cover' in self.profile.modalities:
                    vsql='SELECT item_id,revision,at_ms,vector FROM ai_video_frames WHERE item_id IN ('+','.join('?' for _ in batch)+') ORDER BY item_id,at_ms'
                    for item_id,rev,at_ms,data in db.execute(vsql,batch):
                        if eligible.get(item_id)!=rev:continue
                        if not (isinstance(at_ms,int) and 0<=at_ms<=86_400_000):continue
                        if use_native:
                            if not isinstance(data,(bytes,bytearray,memoryview)) or len(data)!=expect_bytes:continue
                            vf_meta.append((item_id,at_ms));vf_chunks.append(bytes(data))
                            continue
                        try:
                            vec=array('f');vec.frombytes(data)
                        except (ValueError,TypeError):continue
                        if len(vec)!=dim: continue
                        sq=sum(map(operator.mul,vec,vec))
                        if not math.isfinite(sq) or abs(sq-1)>1e-4: continue
                        if is_multi:
                            for orig_ms,orig_vec in active_frames:
                                score=sum(map(operator.mul,orig_vec,vec))
                                prev=scores.get(item_id,{}).get('cover')
                                if prev is None or score>prev or (score==prev and item_id not in video_hits):
                                    scores.setdefault(item_id,{})['cover']=score
                                    video_hits[item_id]=at_ms
                                    if origin_hits is not None:origin_hits[item_id]=orig_ms
                        else:
                            score=sum(map(operator.mul,active_frames[0][1],vec))
                            prev=scores.get(item_id,{}).get('cover')
                            if prev is None or score>prev or (score==prev and item_id not in video_hits):
                                scores.setdefault(item_id,{})['cover']=score
                                video_hits[item_id]=at_ms
                                if origin_hits is not None:origin_hits[item_id]=active_frames[0][0]
        if use_native:
            query_vecs=[v for _,v in active_frames] if is_multi else [active_frames[0][1]]
            if single_meta:
                ns,_,nv=native_accel.score_f32_batch([active_frames[0][1]],b''.join(single_chunks),len(single_meta),dim,normalize_vec=False)
                for idx,(item_id,mode) in enumerate(single_meta):
                    if nv[idx]:
                        scores.setdefault(item_id,{})[mode]=ns[idx]
                        if origin_hits is not None and mode=='cover':origin_hits[item_id]=active_frames[0][0]
            if multi_meta:
                ms_scores,mbq,mv=native_accel.score_f32_batch(query_vecs,b''.join(multi_chunks),len(multi_meta),dim,normalize_vec=False)
                for idx,(item_id,mode) in enumerate(multi_meta):
                    if mv[idx]:
                        scores.setdefault(item_id,{})[mode]=ms_scores[idx]
                        if origin_hits is not None:origin_hits[item_id]=active_frames[mbq[idx]][0]
            if vf_meta:
                vs,vbq,vv=native_accel.score_f32_batch(query_vecs,b''.join(vf_chunks),len(vf_meta),dim,normalize_vec=False)
                for idx,(item_id,at_ms) in enumerate(vf_meta):
                    if not vv[idx]:continue
                    score=vs[idx]
                    prev=scores.get(item_id,{}).get('cover')
                    if prev is None or score>prev or (score==prev and item_id not in video_hits):
                        scores.setdefault(item_id,{})['cover']=score
                        video_hits[item_id]=at_ms
                        if origin_hits is not None:origin_hits[item_id]=active_frames[vbq[idx]][0]
        for vid in video_ids:
            if vid in scores and 'cover' in scores[vid] and vid not in video_hits:
                video_hits[vid]=0
        page_hits={}
        if source in ('all','cover') and 'cover' in self.profile.modalities:
            for item_id,(score,evidence) in (page_scores or {}).items():
                if item_id in eligible and score>=scores.get(item_id,{}).get('cover',-2):
                    scores.setdefault(item_id,{})['cover']=score
                    page_hits[item_id]=evidence
                    video_hits.pop(item_id,None)
        audio_hits={}
        if source in ('all','text') and audio_scores:
            for item_id,(score,evidence) in audio_scores.items():
                if item_id in eligible:
                    prev=scores.get(item_id,{}).get('text')
                    if prev is None or score>=prev:
                        scores.setdefault(item_id,{})['text']=score
                        audio_hits[item_id]=evidence
        return scores,video_hits,page_hits,audio_hits
    def rank_with_evidence(self,rows,query,source="all",ranking="max"):
        ranked,video_hits,_=self.rank_with_content(rows,query,source,ranking)
        return ranked,video_hits
    def rank(self,rows,query,source="all",ranking="max"):
        ranked,_=self.rank_with_evidence(rows,query,source,ranking)
        return ranked

class AISearch:
    def __init__(self,catalog,encoder,store_path=None,ranking='mean-rrf'):
        if ranking not in POLICIES:raise ValueError('Unknown ranking policy')
        self.ranking=ranking
        self.catalog,self.encoder=catalog,encoder
        self.profile=getattr(encoder,'profile',DEFAULT_PROFILE)
        self.pending_tags=PendingTagVectors(self)
        self.store=VectorStore(store_path or self.profile.store_path(catalog.path),self.profile,writer_fence=getattr(catalog,'writer_fence',None))
        self.previews=PreviewReader(catalog)
        self.pages=PageVectors(self)
        self.audio_speech=AudioSpeechVectors(self)
        self.audio_acoustics=AudioAcousticVectors(self)
        # A scan follow-up captures/observes its exact worker under this guard
        # while calling start/status/cancel, which share the same lock.
        self.guard=threading.RLock()
        self.cancel=threading.Event()
        self.worker=None
        self.inference_group=InferenceOwnership() if callable(getattr(encoder,'release',None)) else None
        self.inference=self.inference_group.for_encoder(encoder) if self.inference_group is not None else threading.Lock()
        self._closed=False
        self.search_requests=SearchRequests()
        self.continuation=IndexContinuation(self,MAX_ITEMS)
        self._last_activity=time.monotonic()
        self._idle_seconds=0
        self._index_pause_ms=0
        self._index_mode='normal'
        self._index_mode_explicit=False
        self._idle_stop=threading.Event()
        self._idle_wake=threading.Event()
        self._idle_thread=None

    def configure(self,idle_release_seconds=0,index_pause_ms=0,index_mode=None):
        """Runtime resource policy, independent of vector-space identity."""
        if type(idle_release_seconds) is not int or not 0<=idle_release_seconds<=3600:
            raise ValueError('Idle release must be 0..3600 seconds')
        if type(index_pause_ms) is not int or not 0<=index_pause_ms<=2000:
            raise ValueError('Index pause must be 0..2000 milliseconds')
        if index_mode is not None and (type(index_mode) is not str or index_mode not in ('normal','turbo')):
            raise ValueError('Index mode must be normal or turbo')
        with self.guard:
            if self._closed: raise AIUnavailable('AI is closing')
            self._idle_seconds=idle_release_seconds
            self._index_pause_ms=index_pause_ms
            if index_mode is not None:
                self._index_mode=index_mode
                self._index_mode_explicit=True
            if idle_release_seconds and self._idle_thread is None:
                self._idle_thread=threading.Thread(target=self._idle_loop,name='aredoko-ai-idle',daemon=True)
                self._idle_thread.start()
            self._idle_wake.set()
        return self.resource_policy()

    def resource_policy(self):
        policy={'idle_release_seconds':self._idle_seconds,'index_pause_ms':self._index_pause_ms}
        if self._index_mode_explicit:policy['index_mode']=self._index_mode
        return policy

    def _idle_loop(self):
        """Cancelable monotonic timer; release() shares the inference guard."""
        while not self._idle_stop.is_set():
            self._idle_wake.wait(timeout=0.2)
            self._idle_wake.clear()
            if self._idle_stop.is_set() or not self._idle_seconds:
                continue
            if not bool(getattr(self.encoder,'resident',False)):
                continue
            if time.monotonic()-self._last_activity < self._idle_seconds:
                continue
            try:
                self._release(if_idle=True)
            except (AIBusy,AIUnavailable):
                # The next tick checks again. Never interrupt a live query/job.
                continue

    def _scope(self,value):
        if value is None:return None  # Existing unscoped API behavior.
        scope=validate_scope(value)
        roots=scope['root_ids']
        if roots:
            with self.catalog.connect() as db:
                count=db.execute('SELECT count(*) FROM library_roots WHERE enabled=1 AND id IN ('+
                    ','.join('?' for _ in roots)+')',roots).fetchone()[0]
            if count!=len(roots):raise ValueError('Unknown registered root')
        return scope

    def _row_query_parts(self,kind='',view='all',scope=None):
        if not isinstance(kind,str) or kind and kind not in QUERY_KINDS or view not in ('all','favorites','unreviewed','shelf'):
            raise ValueError('Invalid filter')
        scope=self._scope(scope)
        scoped_where,values=scope_clause(scope)
        where=["l.status='present'",'r.enabled=1',*scoped_where]
        clauses,parameters=kind_clause(kind);where.extend(clauses);values.extend(parameters)
        where.extend({'favorites':['i.favorite=1'],'unreviewed':['i.reviewed=0'],'shelf':["i.shelf<>''"],'all':[]}[view])
        # Multiple root indexes can make SQLite repeatedly sort the whole
        # selected population for each 256-row page. Pin the ID-range driver
        # for multi-root keyset reads; keep the selective single-root plan.
        join=self.catalog.JOIN+'JOIN library_roots r ON r.id=l.root_id '
        if scope is not None and scope['root_ids'] is not None:
            join=join.replace(' JOIN ',' CROSS JOIN ')
        return scope,join,' AND '.join(where),values

    def _iter_rows(self,kind='',view='all',limit=MAX_ITEMS,scope=None,*,all_candidates=False,check=None):
        if type(limit) is not int or not 1<=limit<=MAX_ITEMS:
            raise ValueError('Invalid candidate limit')
        scope,join,where_sql,values=self._row_query_parts(kind,view,scope)
        # New records cannot lengthen a running enumeration indefinitely.
        with self.catalog.connect() as db:
            upper=db.execute('SELECT COALESCE(MAX(id),0) FROM items').fetchone()[0]
        excludes_cache={}
        last=0;yielded=0
        while last<upper and (all_candidates or yielded<limit):
            if check is not None:check()
            with self.catalog.connect() as db:
                rows=db.execute('SELECT '+self.catalog.FIELDS+',r.excludes_json'+join+'WHERE '+where_sql+
                    ' AND i.id>? AND i.id<=? ORDER BY i.id LIMIT ?',
                    values+[last,upper,ROW_BATCH_SIZE]).fetchall()
            if not rows:break
            last=rows[-1]['id']
            # Exclusions do not consume eligible coverage, even before a rescan.
            for row in rows:
                ex_json=row['excludes_json']
                ex=excludes_cache.get(ex_json)
                if ex is None:
                    ex=tuple(json.loads(ex_json))
                    excludes_cache[ex_json]=ex
                if _excluded(row['relative_path'],ex):continue
                yield self.catalog.item(row);yielded+=1
                if not all_candidates and yielded>=limit:break

    def _count_candidates(self,limit=MAX_ITEMS,scope=None):
        _,join,where_sql,values=self._row_query_parts(scope=scope)
        from production import _exclude_matcher
        excludes_cache={}
        total=0;last_included=0
        with self.catalog.connect() as db:
            upper=db.execute('SELECT COALESCE(MAX(id),0) FROM items').fetchone()[0]
            last=0
            while last<upper and total<limit:
                rows=db.execute('SELECT i.id,l.relative_path,r.excludes_json'+join+'WHERE '+where_sql+
                    ' AND i.id>? AND i.id<=? ORDER BY i.id LIMIT ?',
                    values+[last,upper,1024]).fetchall()
                if not rows:break
                last=rows[-1]['id']
                for row in rows:
                    ex_json=row['excludes_json']
                    if ex_json not in excludes_cache:
                        excludes_cache[ex_json]=None if ex_json=='[]' else _exclude_matcher(tuple(json.loads(ex_json)))
                    matcher=excludes_cache[ex_json]
                    if matcher is not None and matcher(row['relative_path']):continue
                    total+=1;last_included=row['id']
                    if total>=limit:break
        return total,last_included

    def _iter_id_batches(self,limit=MAX_ITEMS,scope=None,*,upper_id=None):
        _,join,where_sql,values=self._row_query_parts(scope=scope)
        if upper_id is None:
            with self.catalog.connect() as db:
                upper_id=db.execute('SELECT COALESCE(MAX(id),0) FROM items').fetchone()[0]
        excludes_cache={}
        last=0;yielded=0
        while last<upper_id and yielded<limit:
            with self.catalog.connect() as db:
                rows=db.execute('SELECT i.id,l.relative_path,r.excludes_json'+join+'WHERE '+where_sql+
                    ' AND i.id>? AND i.id<=? ORDER BY i.id LIMIT ?',
                    values+[last,upper_id,ROW_BATCH_SIZE]).fetchall()
            if not rows:break
            last=rows[-1]['id']
            batch=[]
            for row in rows:
                ex_json=row['excludes_json']
                ex=excludes_cache.get(ex_json)
                if ex is None:
                    ex=tuple(json.loads(ex_json))
                    excludes_cache[ex_json]=ex
                if _excluded(row['relative_path'],ex):continue
                batch.append(row['id']);yielded+=1
                if yielded>=limit:break
            if batch:yield batch
    def _rows(self,kind='',view='all',limit=MAX_ITEMS):
        # Legacy bounded metadata helper; full searches use _search_batches.
        return list(self._iter_rows(kind,view,limit))
    def _current_rows(self,ids,scope=None):
        if not ids:return {}
        if len(ids)>ROW_BATCH_SIZE:raise ValueError('Metadata batch exceeds limit')
        scoped_where,values=scope_clause(scope)
        clause=" AND "+" AND ".join(scoped_where) if scoped_where else ''
        join=self.catalog.JOIN.replace(' JOIN ',' CROSS JOIN ')+'JOIN library_roots r ON r.id=l.root_id'
        with self.catalog.connect() as db:
            rows=db.execute('SELECT '+self.catalog.FIELDS+',r.excludes_json'+join+' WHERE i.id IN ('+
                ','.join('?' for _ in ids)+") AND l.status='present' AND r.enabled=1"+clause,ids+values).fetchall()
        return {row['id']:self.catalog.item(row) for row in rows
                if not _excluded(row['relative_path'],tuple(json.loads(row['excludes_json'])))}
    def _search_batches(self,kind,view,scope,check,allowed=None,exclude_id=None):
        batch=[]
        for row in self._iter_rows(kind,view,limit=MAX_ITEMS,scope=scope,all_candidates=True,check=check):
            if row['id']==exclude_id or allowed is not None and row['kind'] not in allowed:continue
            batch.append(row)
            if len(batch)==ROW_BATCH_SIZE:
                yield batch
                batch=[]
        if batch:yield batch

    @contextmanager
    def _search_workspace(self,scope,cancelled=None):
        """Optimistic change detection, not an atomic snapshot of several DBs.

        Keep the same monitor connections: data_version is connection-relative.
        Ordinary annotation writes do not increment catalog._state_epoch.
        """
        with self.catalog.connect() as catalog_db,self.store.connect() as vector_db:
            def versions():
                return (catalog_db.execute('PRAGMA data_version').fetchone()[0],
                        vector_db.execute('PRAGMA data_version').fetchone()[0])
            with self.catalog._guard:
                version=versions();epoch=self.catalog._state_epoch;profile=self.profile.key
            def interrupted():return self._closed or cancelled is not None and cancelled()
            def check():
                if cancelled is not None and cancelled():raise SearchCancelled('Search cancelled')
                if self._closed:raise AIUnavailable('AI is closing')
                self._scope(scope)
                if self.catalog.scan_state()['state'] in ('running','cancelling'):
                    raise AIBusy('フォルダのスキャン完了後に検索してください。')
                if epoch!=self.catalog._state_epoch or profile!=self.profile.key or version!=versions():
                    raise AIBusy('検索対象または索引が更新されました。もう一度検索してください。')
            check()
            try:
                with ScoreSpool(cancelled=interrupted) as spool:
                    yield spool,check
            except SearchCancelled as error:
                if self._closed:raise AIUnavailable('AI is closing') from error
                raise
            except (ScoreSpoolError,OSError) as error:
                raise AIUnavailable('検索用の作業領域を使用できません。空き容量を確認して再検索してください。') from error

    def _search_page_rows(self,spool,selected,scope,check):
        ids=[item for item,_ in selected['ranked']]
        evidence=spool.evidence(ids)
        current=self._current_rows(ids,scope)
        if any(item not in current or revision(current[item])!=evidence[item]['revision'] for item in ids):
            raise AIBusy('検索対象が更新されました。もう一度検索してください。')
        # Page evidence was checked per batch; recheck returned pages against
        # physical changes that do not write the catalog during later batches.
        for item in ids:
            match=evidence[item].get('ai_page_match')
            if match is not None:
                try:
                    source=self.pages.index.previews.tag_source(item)
                except (PreviewUnavailable,OSError) as error:
                    raise AIBusy('一致ページの元ファイルを確認できません。もう一度検索してください。') from error
                if source['revision']!=match['source_revision']:
                    raise AIBusy('一致ページの元ファイルが更新されました。もう一度検索してください。')
        check()
        return current,evidence

    def coverage(self,scope=None,limit=MAX_ITEMS):
        """CPU-only, refreshable counts. Retains at most one 256-row batch."""
        if type(limit) is not int or not 1<=limit<=MAX_ITEMS:raise ValueError('Invalid index limit')
        with self.guard:
            if self._closed:raise AIUnavailable('AI is closing')
        scope,join,where_sql,values=self._row_query_parts(scope=scope)
        if self.catalog.scan_state()['state'] in ('running','cancelling'):
            raise AIBusy('フォルダのスキャン完了後に確認してください。')
        from production import _exclude_matcher
        excludes_cache={}
        want_all_pages=bool(scope and scope.get('book_pages')=='all_pages' and 'cover' in self.profile.modalities)
        total=targeted=fresh=0;batch=[]
        book_target=book_pages_ready=0;book_batch=[]
        with self.catalog.connect() as cat_db, self.store.connect() as vec_db:
            upper=cat_db.execute('SELECT COALESCE(MAX(id),0) FROM items').fetchone()[0]
            has_vectors=vec_db.execute("SELECT 1 FROM ai_vectors WHERE modality='text' LIMIT 1").fetchone() is not None
            has_pending=bool(
                cat_db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tag_proposal_batches'").fetchone()
                and cat_db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tag_proposals'").fetchone()
                and cat_db.execute("SELECT 1 FROM tag_proposals WHERE state='pending' LIMIT 1").fetchone()
            )
            has_page_heads=bool(want_all_pages and cat_db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='page_heads'").fetchone())
            has_page_vectors=bool(want_all_pages and vec_db.execute('SELECT 1 FROM ai_page_vectors LIMIT 1').fetchone())
            def flush(rows_batch):
                nonlocal fresh
                if not rows_batch:return
                eligible={r['id']:(revision(r),source_contract(r,self.profile)) for r in rows_batch}
                records=vec_db.execute(
                    "SELECT v.item_id,v.revision,c.revision,c.contract FROM ai_vectors v "
                    "LEFT JOIN ai_source_contracts c ON c.item_id=v.item_id WHERE v.modality='text' AND v.item_id IN ("
                    +','.join('?' for _ in eligible)+')',list(eligible)).fetchall()
                regular={item_id for item_id,rev,source_rev,contract in records
                         if eligible[item_id][0]==rev and (eligible[item_id][1] is None or
                            (source_rev==rev and contract==eligible[item_id][1]))}
                if has_pending and regular:
                    pending=self.pending_tags.snapshots([r['id'] for r in rows_batch])
                    fresh+=len((regular-set(pending)) | (regular & self.pending_tags.ready_ids(pending)))
                else:
                    fresh+=len(regular)
                rows_batch.clear()
            def flush_books(book_ids):
                nonlocal book_pages_ready
                if not book_ids or not has_page_heads or not has_page_vectors:
                    book_ids.clear();return
                marks=','.join('?' for _ in book_ids)
                head_rows=cat_db.execute(
                    'SELECT h.item_id,s.source_revision,s.page_count FROM page_heads h '
                    'JOIN page_snapshots s ON s.id=h.snapshot_id WHERE h.item_id IN ('+marks+')',
                    book_ids).fetchall()
                expected_books={r[0]:(r[1],r[2]) for r in head_rows}
                if expected_books:
                    v_marks=','.join('?' for _ in expected_books)
                    vec_rows=vec_db.execute(
                        'SELECT item_id,source_revision,COUNT(*) FROM ai_page_vectors '
                        'WHERE contract=? AND item_id IN ('+v_marks+') GROUP BY item_id,source_revision',
                        [PAGE_CONTRACT,*expected_books]).fetchall()
                    for item_id,rev,cnt in vec_rows:
                        exp=expected_books.get(item_id)
                        if exp is not None and exp[0]==rev and cnt>=exp[1]:
                            book_pages_ready+=1
                book_ids.clear()
            last=0
            sql=('SELECT i.id,i.title,i.kind,i.tags,l.root_id,l.relative_path,l.size_bytes,l.mtime_ns,r.excludes_json'
                 +join+'WHERE '+where_sql+' AND i.id>? AND i.id<=? ORDER BY i.id LIMIT ?')
            while last<upper:
                rows=cat_db.execute(sql,values+[last,upper,1024]).fetchall()
                if not rows:break
                last=rows[-1]['id']
                for row in rows:
                    ex_json=row['excludes_json']
                    if ex_json not in excludes_cache:
                        excludes_cache[ex_json]=None if ex_json=='[]' else _exclude_matcher(tuple(json.loads(ex_json)))
                    matcher=excludes_cache[ex_json]
                    if matcher is not None and matcher(row['relative_path']):continue
                    total+=1
                    if targeted<limit:
                        targeted+=1
                        if want_all_pages and row['kind'] in ('book','archive'):
                            book_target+=1
                            if has_page_heads and has_page_vectors:
                                book_batch.append(row['id'])
                                if len(book_batch)==ROW_BATCH_SIZE:
                                    flush_books(book_batch)
                        if has_vectors:
                            raw_tags=row['tags']
                            batch.append({
                                'id':row['id'],'title':row['title'],'kind':row['kind'],
                                'tags':[] if raw_tags=='[]' else json.loads(raw_tags),
                                'root_id':row['root_id'],'relative_path':row['relative_path'],
                                'size_bytes':row['size_bytes'],'mtime_ns':row['mtime_ns'],
                            })
                            if len(batch)==ROW_BATCH_SIZE:
                                flush(batch)
            flush(batch)
            flush_books(book_batch)
        book_pages_remaining=max(0,book_target-book_pages_ready)
        cov_status=('empty_scope' if targeted==0
                    else ('unindexed' if fresh==0
                          else ('partially_indexed' if fresh<targeted or book_pages_remaining>0
                                else 'ready')))
        return {'scope':scope,'candidate_total':total,'target_total':targeted,
                'fresh_total':fresh,'remaining_total':targeted-fresh,
                'coverage_limit':MAX_ITEMS,'index_limit':limit,'refresh_required_on_change':True,
                'coverage_status':cov_status,
                'book_pages':'all_pages' if want_all_pages else 'cover_only',
                'book_target_total':book_target,
                'book_pages_ready_total':book_pages_ready,
                'book_pages_remaining_total':book_pages_remaining}

    def status(self):
        with self.guard: state=self.store.state()
        resident=bool(getattr(self.encoder,'resident',False))
        available=bool(self.encoder.available)
        st=state.get('state','idle')
        if not available:
            status_code = 'model_missing'
        elif st in ('failed', 'error'):
            status_code = 'worker_failed'
        elif st in ('running', 'cancelling', 'interrupted', 'cancelled'):
            status_code = st
        else:
            status_code = 'ready'
        return {**public_state(state),'available':available,
                'status_code':status_code,
                'resident':resident,'worker_state':'loaded' if resident else 'unloaded',
                'device':getattr(self.encoder,'device','') if resident else '',
                'index_mode':self._index_mode,
                'limit':MAX_ITEMS,'model':self.profile.label,'model_id':self.profile.model_id,'profile':self.profile.key,
                'modalities':list(self.profile.modalities),'dimension':self.profile.dimension,'ranking':self.ranking,
                'telemetry':getattr(self.encoder,'telemetry',{}) if resident else {},
                'resource_policy':self.resource_policy(),
                'runtime_verification':runtime_verification_status(getattr(self.encoder,'python',None)) if available else {'state':'idle','files_done':0,'files_total':0,'bytes_done':0,'bytes_total':0,'elapsed_seconds':0.0,'slow':False,'error':''}}
    def start(self,limit=MAX_ITEMS,scope=None):
        if type(limit) is not int or not 1<=limit<=MAX_ITEMS: raise ValueError('Invalid index limit')
        scope=self._scope(scope)
        if not self.encoder.available: raise AIUnavailable('AI環境が未導入です。setup-ai.ps1を実行してください。')
        with self.guard:
            if self._closed: raise AIUnavailable('AI is closing')
            if self.worker and self.worker.is_alive(): raise AIBusy('AI索引を作成中です。')
            if self.catalog.scan_state()['state'] in ('running','cancelling'): raise AIBusy('フォルダのスキャン完了後に実行してください。')
        total,upper_id=self._count_candidates(limit=limit,scope=scope)
        with self.guard:
            if self._closed: raise AIUnavailable('AI is closing')
            if self.worker and self.worker.is_alive(): raise AIBusy('AI索引を作成中です。')
            if self.catalog.scan_state()['state'] in ('running','cancelling'): raise AIBusy('フォルダのスキャン完了後に実行してください。')
            self.cancel.clear()
            self.store.save_state({'state':'running','processed':0,'total':total,'indexed':0,'skipped':0,'reused':0,'error':'','scope':scope})
            self.worker=threading.Thread(target=self._build,args=(None,scope),kwargs={'upper_id':upper_id,'limit':total},daemon=True)
            self.worker.start()
            return self.status()
    def _build(self,ids,scope=None,initial_state=None,*,upper_id=0,limit=0):
        total_hint=len(ids) if ids is not None else (initial_state['total'] if initial_state is not None else limit)
        state=dict(initial_state) if initial_state is not None else {'state':'running','processed':0,'total':total_hint,'indexed':0,'skipped':0,'reused':0,'error':'','scope':scope}
        continuing=state.get('job')==CONTINUATION_JOB
        if continuing and state['continuation'].get('version')==1:
            state['_pins']={item:(rev,sig) for item,rev,sig in state['continuation']['entries']}
        def saved():return {k:v for k,v in state.items() if k!='_pins'}
        def save_progress():
            with self.guard:
                self.store.save_state({**saved(),'state':'cancelling' if self.cancel.is_set() else 'running'})
        try:
            with self.inference:
                if continuing and state['continuation'].get('version')==2:
                    batch_iter=self.continuation.iter_chunks(state['continuation'])
                elif ids is not None:
                    batch_iter=((None,ids[offset:offset+ROW_BATCH_SIZE]) for offset in range(0,len(ids),ROW_BATCH_SIZE))
                elif limit>0:
                    batch_iter=((None,batch) for batch in self._iter_id_batches(limit=limit,scope=scope,upper_id=upper_id))
                else:
                    batch_iter=()
                want_all_pages=bool(scope and scope.get('book_pages')=='all_pages' and 'cover' in self.profile.modalities)
                for chunk_idx,batch in batch_iter:
                    if self.cancel.is_set():break
                    if continuing:
                        with self.catalog._guard:
                            if chunk_idx is not None:
                                self.continuation.check_chunk(state,chunk_idx,batch)
                            else:
                                self.continuation.check(state,batch)
                    rows=self._current_rows(batch,scope)
                    pending=self.pending_tags.snapshots(list(rows))
                    if hasattr(self.encoder,'encode_batch') and not self._index_pause_ms:
                        from concurrent.futures import ThreadPoolExecutor
                        present_rows=[]
                        for item_id in batch:
                            row=rows.get(item_id)
                            if row is None:
                                state['skipped']+=1
                                state['processed']+=1
                            else:
                                present_rows.append(row)
                        if not present_rows:
                            save_progress()
                            continue
                        fresh_set=self.store.fresh_ids(present_rows)
                        ready_rows=[r for r in present_rows if r['id'] in fresh_set and r['id'] not in pending and not (want_all_pages and r['kind'] in ('book','archive'))]
                        if ready_rows:
                            if continuing:
                                with self.catalog._guard:
                                    self.continuation.check(state,[r['id'] for r in ready_rows])
                                    ready_checked=self.continuation.ready(ready_rows,{})
                                    state['indexed']+=len(ready_checked)
                                    state['reused']+=len(ready_checked)
                                    state['skipped']+=len(ready_rows)-len(ready_checked)
                            else:
                                state['indexed']+=len(ready_rows)
                                state['reused']=state.get('reused',0)+len(ready_rows)
                            state['processed']+=len(ready_rows)
                        ready_ids={r['id'] for r in ready_rows}
                        work_rows=[r for r in present_rows if r['id'] not in ready_ids]
                        if not work_rows:
                            save_progress()
                            continue
                        sub_offset=0
                        while sub_offset<len(work_rows):
                            if self.cancel.is_set():break
                            mode=self._index_mode
                            sub_step=32 if mode=='turbo' else 8
                            sub_rows=work_rows[sub_offset:sub_offset+sub_step]
                            sub_offset+=len(sub_rows)
                            unfresh_rows=[r for r in sub_rows if r['id'] not in fresh_set]
                            committed_ids=set();stale_ids=set();contract_skipped_ids=set()
                            if unfresh_rows:
                                rev_by_id={r['id']:revision(r) for r in unfresh_rows}
                                saved_texts=self.store.texts(unfresh_rows)
                                need_text_rows=[r for r in unfresh_rows if r['id'] not in saved_texts]
                                text_vecs=dict(saved_texts)
                                if need_text_rows:
                                    doc_inputs=[(r['title']+'\n'+r['relative_path']+'\n'+'、'.join(r['tags']))[:4096] for r in need_text_rows]
                                    encoded_texts=self.encoder.encode_batch('document',doc_inputs,mode=mode)
                                    for r,vec in zip(need_text_rows,encoded_texts):
                                        text_vecs[r['id']]=vec
                                if self.cancel.is_set():break
                                cover_vecs={};video_frames_by_id={}
                                if 'cover' in self.profile.modalities:
                                    cover_rows=[r for r in unfresh_rows if r['kind'] in ('image','book','archive')]
                                    def _read_cover(iid):
                                        try:
                                            src,_=self.previews.read_cover(iid) if hasattr(self.previews,'read_cover') else self.previews.read(iid)
                                            return src
                                        except PreviewBusyError:
                                            time.sleep(0.01)
                                            try:
                                                src,_=self.previews.read_cover(iid) if hasattr(self.previews,'read_cover') else self.previews.read(iid)
                                                return src
                                            except (PreviewUnavailable,OSError):
                                                return None
                                        except (PreviewUnavailable,OSError):
                                            return None
                                    if cover_rows:
                                        if mode=='turbo' and len(cover_rows)>1:
                                            with ThreadPoolExecutor(max_workers=2) as cover_pool:
                                                cover_bytes=list(cover_pool.map(_read_cover,[r['id'] for r in cover_rows]))
                                        else:
                                            cover_bytes=[_read_cover(r['id']) for r in cover_rows]
                                        if self.cancel.is_set():break
                                        valid_covers=[(r['id'],data) for r,data in zip(cover_rows,cover_bytes) if data is not None]
                                        if valid_covers:
                                            encoded_covers=self.encoder.encode_batch('image',[data for _,data in valid_covers],mode=mode)
                                            for (cid,_),vec in zip(valid_covers,encoded_covers):
                                                if vec is not None:
                                                    cover_vecs[cid]=vec
                                    video_rows=[r for r in unfresh_rows if r['kind']=='video']
                                    if video_rows:
                                        frame_requests=[]
                                        for vr in video_rows:
                                            if self.cancel.is_set():break
                                            vid=vr['id']
                                            try:
                                                extracted=self.previews.video_representative_frames(vid) if hasattr(self.previews,'video_representative_frames') else [(0,self.previews.read(vid)[0])]
                                                for at_ms,frame_png in extracted:
                                                    frame_requests.append((vid,at_ms,frame_png))
                                            except (PreviewUnavailable,OSError):
                                                pass
                                        if self.cancel.is_set():break
                                        if frame_requests:
                                            encoded_frames=self.encoder.encode_batch('image',[fp for _,_,fp in frame_requests],mode=mode)
                                            if self.cancel.is_set():break
                                            for (vid,at_ms,_),vec in zip(frame_requests,encoded_frames):
                                                if vec is not None:
                                                    video_frames_by_id.setdefault(vid,[]).append((at_ms,vec))
                                            for vid,vlist in video_frames_by_id.items():
                                                if vlist:cover_vecs[vid]=vlist[0][1]
                                if self.cancel.is_set():break
                                with self.catalog._guard if continuing else nullcontext():
                                    if continuing:
                                        if self.cancel.is_set():raise InterruptedError()
                                        self.continuation.check(state,[r['id'] for r in unfresh_rows])
                                    current_map=self._current_rows([r['id'] for r in unfresh_rows],scope)
                                    to_commit=[]
                                    for r in unfresh_rows:
                                        iid=r['id'];rev=rev_by_id[iid]
                                        current=current_map.get(iid)
                                        if current is None or revision(current)!=rev:
                                            stale_ids.add(iid)
                                            continue
                                        vectors={'text':text_vecs[iid]}
                                        if iid in cover_vecs:vectors['cover']=cover_vecs[iid]
                                        vframes=video_frames_by_id.get(iid)
                                        expected=source_contract(r,self.profile)
                                        visual_ready='cover' in vectors and (r['kind']!='video' or bool(vframes))
                                        if expected is not None and not visual_ready and iid in saved_texts:
                                            contract_skipped_ids.add(iid)
                                            continue
                                        to_commit.append((iid,rev,vectors,vframes,expected if visual_ready else None))
                                        committed_ids.add(iid)
                                    if to_commit:
                                        self.store.put_many(to_commit)
                            newly_indexed_ids=[];did_infer_ids=set()
                            for r in sub_rows:
                                if self.cancel.is_set():break
                                item_id=r['id']
                                if item_id in stale_ids:
                                    state['skipped']+=1
                                    state['processed']+=1
                                    continue
                                did_infer=item_id in committed_ids
                                indexed_before=state['indexed']
                                if item_id in contract_skipped_ids:
                                    state['skipped']+=1
                                else:
                                    state['indexed']+=1
                                tag_ready,tag_inferred=self.pending_tags.build(r,pending.get(item_id),scope,self.cancel.is_set)
                                did_infer=did_infer or tag_inferred
                                if not tag_ready and state['indexed']>indexed_before:
                                    state['indexed']-=1;state['skipped']+=1
                                if (not self.cancel.is_set()
                                        and want_all_pages and r['kind'] in ('book','archive')):
                                    try:
                                        if self.pages.index_all_pages(item_id,scope):
                                            did_infer=True
                                    except (PreviewUnavailable,ReaderChanged,PreviewBusyError,KeyError,OSError):
                                        pass
                                if state['indexed']>indexed_before:
                                    newly_indexed_ids.append(item_id)
                                    if did_infer:did_infer_ids.add(item_id)
                                    elif not continuing:state['reused']=state.get('reused',0)+1
                                state['processed']+=1
                            if continuing and newly_indexed_ids and not self.cancel.is_set():
                                with self.catalog._guard:
                                    self.continuation.check(state,newly_indexed_ids)
                                    current_verify=self._current_rows(newly_indexed_ids,scope)
                                    snapshots=self.pending_tags.snapshots(newly_indexed_ids)
                                    ready_set=self.continuation.ready(list(current_verify.values()),snapshots)
                                    for item_id in newly_indexed_ids:
                                        if item_id not in ready_set:
                                            state['indexed']-=1;state['skipped']+=1
                                        elif item_id not in did_infer_ids:
                                            state['reused']+=1
                            save_progress()
                        continue
                    fresh_set=self.store.fresh_ids(list(rows.values()))
                    for item_id in batch:
                        if self.cancel.is_set():break
                        did_infer=False
                        indexed_before=state['indexed']
                        row=rows.get(item_id)
                        if row is None:
                            state['skipped']+=1
                        else:
                            rev=revision(row)
                            if item_id not in fresh_set:
                                text=row['title']+'\n'+row['relative_path']+'\n'+'、'.join(row['tags'])
                                saved_text=self.store.text(row)
                                vectors={'text':saved_text if saved_text is not None else self.encoder.encode('document',text[:4096])}
                                did_infer=True
                                video_frames=[]
                                if 'cover' in self.profile.modalities and row['kind'] in ('image','book','archive'):
                                    try:
                                        source,_=self.previews.read_cover(item_id) if hasattr(self.previews,'read_cover') else self.previews.read(item_id)
                                        cover=self.encoder.encode('image',source)
                                        if cover is not None:vectors['cover']=cover
                                    except (PreviewUnavailable,OSError):pass
                                elif 'cover' in self.profile.modalities and row['kind']=='video':
                                    try:
                                        extracted=self.previews.video_representative_frames(item_id) if hasattr(self.previews,'video_representative_frames') else [(0,self.previews.read(item_id)[0])]
                                        for at_ms,frame_png in extracted:
                                            if self.cancel.is_set():break
                                            vec=self.encoder.encode('image',frame_png)
                                            if vec is not None:video_frames.append((at_ms,vec))
                                        if video_frames:
                                            vectors['cover']=video_frames[0][1]
                                    except (PreviewUnavailable,OSError):pass
                                # A cancelled multi-frame pass must not mark a partial video
                                # as fresh or replace its previous complete revision.
                                if row['kind']=='video' and self.cancel.is_set():
                                    state['processed']+=1
                                    break
                                # Recheck presence, exclusions and revision before publishing.
                                with self.catalog._guard if continuing else nullcontext():
                                    if continuing:
                                        if self.cancel.is_set():raise InterruptedError()
                                        self.continuation.check(state,[item_id])
                                    current=self._current_rows([item_id],scope).get(item_id)
                                    if current is None or revision(current)!=rev:
                                        state['skipped']+=1
                                    else:
                                        expected=source_contract(row,self.profile)
                                        visual_ready='cover' in vectors and (row['kind']!='video' or bool(video_frames))
                                        if expected is not None and not visual_ready and saved_text is not None:
                                            # A transient preview failure must not erase a usable
                                            # legacy cover or mark missing content as refreshed.
                                            state['skipped']+=1
                                        else:
                                            self.store.put(item_id,rev,vectors,video_frames,source_contract=expected if visual_ready else None);state['indexed']+=1
                            else:state['indexed']+=1
                        if row is not None and not self.cancel.is_set():
                            tag_ready,tag_inferred=self.pending_tags.build(row,pending.get(item_id),scope,self.cancel.is_set)
                            did_infer=did_infer or tag_inferred
                            if not tag_ready and state['indexed']>indexed_before:
                                state['indexed']-=1;state['skipped']+=1
                        if (row is not None and not self.cancel.is_set()
                                and scope and scope.get('book_pages')=='all_pages'
                                and 'cover' in self.profile.modalities and row['kind'] in ('book','archive')):
                            try:
                                if self.pages.index_all_pages(item_id,scope):
                                    did_infer=True
                            except (PreviewUnavailable,ReaderChanged,PreviewBusyError,KeyError,OSError):
                                pass
                        if not continuing and not self.cancel.is_set() and state['indexed']>indexed_before and not did_infer:
                            state['reused']=state.get('reused',0)+1
                        if continuing and not self.cancel.is_set():
                            with self.catalog._guard:
                                self.continuation.check(state,[item_id])
                                current=self._current_rows([item_id],scope).get(item_id)
                                snapshots=self.pending_tags.snapshots([item_id])
                                if state['indexed']>indexed_before:
                                    if item_id not in self.continuation.ready([current],snapshots):
                                        state['indexed']-=1;state['skipped']+=1
                                    elif not did_infer:state['reused']+=1
                        state['processed']+=1
                        # Vectors commit atomically per item. Progress may lag by 15;
                        # a restart discovers saved revisions rather than re-encoding.
                        if state['processed']%PROGRESS_INTERVAL==0:
                            with self.guard:
                                self.store.save_state({**saved(),'state':'cancelling' if self.cancel.is_set() else 'running'})
                        # Load-shedding is optional and cancelable. Not a GPU
                        # utilization/FPS limit. Never pace interactive search.
                        if did_infer and state['processed']<state['total'] and self._index_pause_ms:
                            if self.cancel.wait(self._index_pause_ms/1000):
                                break
                if ids is None and not continuing and not self.cancel.is_set() and state['processed']<state['total']:
                    missing=state['total']-state['processed']
                    state['skipped']+=missing;state['processed']+=missing
                if continuing and not self.cancel.is_set():
                    with self.catalog._guard:
                        if state['continuation'].get('version')==2:
                            for c_idx,c_ids in self.continuation.iter_chunks(state['continuation']):
                                self.continuation.check_chunk(state,c_idx,c_ids)
                        else:
                            for offset in range(0,len(ids),ROW_BATCH_SIZE):
                                self.continuation.check(state,ids[offset:offset+ROW_BATCH_SIZE])
                state['state']='cancelled' if self.cancel.is_set() else 'complete'
                if state['state']=='complete':
                    state.pop('continuation',None)
        except InterruptedError:
            state['state']='cancelled' if self.cancel.is_set() else 'failed'
            if not self.cancel.is_set():state['error']='索引を完了できませんでした。対象を確認してください。'
        except Exception as ex:
            traceback.print_exc(file=sys.stderr); sys.stderr.flush()
            state['state']='failed';state['error']='AI索引を作成できませんでした（'+type(ex).__name__+'）。ローカルログを確認してください。'
        finally:
            # Covers both actual inference and cached rebuilds.
            self._last_activity=time.monotonic()
            with self.guard:self.store.save_state(saved())
    def cancel_build(self):
        self.cancel.set()
        with self.guard:
            state=self.store.state()
            if state['state']=='running': self.store.save_state({**state,'state':'cancelling'})
        return {'cancel_requested':True}
    def search(self,query,kind='',view='all',page=0,limit=60,source='all',ranking=None,scope=None,literal_only=False,group_threshold=None,result_group='all',*,cancelled=None,result_sink=None):
        if not isinstance(query,str) or not 0<len(query.strip())<=300 or type(page) is not int or page<0 or type(limit) is not int or not 1<=limit<=120:
            raise ValueError('Invalid semantic search')
        if result_group not in ('all','leading','other'):raise ValueError('Invalid result group')
        if type(literal_only) is not bool:raise ValueError('Invalid literal evidence filter')
        scope=self._scope(scope)
        if not isinstance(kind,str) or kind and kind not in QUERY_KINDS or view not in ('all','favorites','unreviewed','shelf'):
            raise ValueError('Invalid filter')
        ranking=self.ranking if ranking is None else ranking
        if ranking not in POLICIES:raise ValueError('Unknown ranking policy')
        if source not in ('all','text','cover'): raise ValueError('Invalid semantic source')
        if source=='cover' and 'cover' not in self.profile.modalities:
            raise AIUnavailable('選択中のモデルは画像の見た目の検索に対応していません。名前・タグの意味（AI）を使ってください。')
        selected_policy=ranking if source=='all' and 'cover' in self.profile.modalities else 'max'
        boundary([], 'reciprocal-rank' if selected_policy=='mean-rrf' else 'cosine',group_threshold)
        if not self.encoder.available: raise AIUnavailable('AI環境が未導入です。')
        if not self.inference.acquire(blocking=False): raise AIBusy('AI索引を作成中です。完了後に検索してください。')
        try:
            with self._search_workspace(scope,cancelled) as (spool,check):
                query_vector=None;candidate_total=indexed_total=0
                words=list(dict.fromkeys(normalize(query).split()))
                allowed=('image','book','archive','video') if source=='cover' else None
                include_pages=scope is None or scope.get('book_pages')!='cover_only'
                for rows in self._search_batches(kind,view,scope,check,allowed):
                    candidate_total+=len(rows)
                    if query_vector is None:
                        query_vector=normalized(self.encoder.encode('query',query),self.profile.dimension)
                    check()
                    page_scores=self.pages.rank(rows,query_vector,check=check) if (source in ('all','cover') and include_pages) else {}
                    speech_scores=self.audio_speech.rank(rows,query_vector,check=check) if source in ('all','text') else {}
                    acoustic_scores=self.audio_acoustics.rank(rows,query,query_vector,check=check) if source in ('all','text') else {}
                    audio_scores=dict(speech_scores)
                    for aid,(ascore,aevid) in acoustic_scores.items():
                        if aid not in audio_scores or ascore>audio_scores[aid][0]:
                            audio_scores[aid]=(ascore,aevid)
                    scores,video_hits,page_hits,audio_hits=self.store.scores_with_content(rows,query_vector,source,page_scores,audio_scores=audio_scores)
                    for row in rows:
                        item=row['id']
                        if item not in scores:continue
                        hay=normalize(row['title'])+'\x1f'+normalize_tags(row['tags'])
                        hits=sum(word in hay for word in words)
                        payload={'revision':revision(row),'literal_hits':hits,'literal_words':len(words)}
                        if item in video_hits:payload['video_match_ms']=video_hits[item]
                        if item in page_hits:payload['ai_page_match']=page_hits[item]
                        if item in audio_hits:
                            payload['audio_match_ms']=audio_hits[item]['start_ms']
                            payload['audio_match_snippet']=audio_hits[item]['snippet']
                        spool.add(item,scores[item],literal_hits=hits,literal_words=len(words),payload=payload)
                    indexed_total+=len(scores)
                    check()
                spool.finalize(selected_policy)
                def render_page(number):
                    selected=spool.page(number,limit,literal_only=literal_only,group_threshold=group_threshold,result_group=result_group)
                    with self.catalog._guard:
                        check()
                        current,evidence=self._search_page_rows(spool,selected,scope,check)
                        items=[]
                        cut=selected['group_boundary']
                        for item,score in selected['ranked']:
                            payload=evidence[item]
                            entry={**current[item],'literal_hits':payload['literal_hits'],'literal_words':payload['literal_words'],
                                   'semantic_score':round(score,6),'similarity_group':'leading' if cut is None or score>=cut else 'other'}
                            for key in ('video_match_ms','ai_page_match','audio_match_ms','audio_match_snippet'):
                                if key in payload:entry[key]=payload[key]
                            items.append(entry)
                    if candidate_total == 0:
                        search_status = 'out_of_scope'
                    elif indexed_total == 0:
                        search_status = 'unindexed'
                    elif indexed_total < candidate_total:
                        search_status = 'partially_indexed'
                    else:
                        search_status = 'ready'
                    return {**{key:val for key,val in selected.items() if key!='ranked'},'items':items,'mode':'semantic',
                            'coverage_limit':MAX_ITEMS,'index_limit':MAX_ITEMS,'source':source,'ranking':selected_policy,
                            'score_kind':'reciprocal-rank' if selected_policy=='mean-rrf' else 'cosine',
                            'scope':scope,'literal_only':literal_only,'result_group':result_group,
                            'search_status':search_status,
                            'search_complete':True,'search_candidate_total':candidate_total,'indexed_total':indexed_total}
                return render_page(page) if result_sink is None else result_sink(render_page)
        finally:
            self._last_activity=time.monotonic()
            self.inference.release()

    def release(self):
        """Refuse a busy encoder; never touch the profile, catalog or vector DB."""
        return self._release()

    def similar(self,item_id,kind='',view='all',page=0,limit=60,scope=None,origin_page=None,origin_ms=None,*,cancelled=None,result_sink=None):
        """Item-origin, page-origin, or video-frame-origin visual cosine search.

        The origin must be in scope, but need not satisfy result-only kind/view
        filters. Missing/stale cover vectors return an explicit empty fallback,
        never a text embedding masquerading as an image match.
        """
        if type(item_id) is not int or not 1<=item_id<=9223372036854775807:
            raise ValueError('Invalid item')
        if type(page) is not int or page<0 or type(limit) is not int or not 1<=limit<=120:
            raise ValueError('Invalid paging')
        if origin_page is not None and origin_ms is not None:
            raise ValueError('Cannot specify both origin_page and origin_ms')
        if origin_page is not None and (type(origin_page) is not int or not 0<=origin_page<10000):
            raise ValueError('Invalid origin page')
        if origin_ms is not None and (type(origin_ms) is not int or not 0<=origin_ms<=86_400_000):
            raise ValueError('Invalid origin timestamp')
        if not isinstance(kind,str) or kind and kind not in QUERY_KINDS or view not in ('all','favorites','unreviewed','shelf'):
            raise ValueError('Invalid filter')
        scope=self._scope(scope)
        if not self.inference.acquire(blocking=False):raise AIBusy('AI索引または検索を処理中です。完了後に類似検索してください。')
        try:
            if self._closed:raise AIUnavailable('AI is closing')
            if self.catalog.scan_state()['state'] in ('running','cancelling'):
                raise AIBusy('フォルダのスキャン完了後に類似検索してください。')
            with self._search_workspace(scope,cancelled) as (spool,check):
                origin=self._current_rows([item_id],scope).get(item_id)
                if origin is None:raise KeyError(item_id)
                if origin['kind'] not in ('image','book','archive','video','audio'):
                    raise ValueError('Invalid similarity source')
                if origin_page is not None and origin['kind'] not in ('book','archive'):
                    raise ValueError('Origin page requires a book or archive')
                if origin_ms is not None and origin['kind']!='video':
                    raise ValueError('Origin timestamp requires a video')
                is_audio=origin['kind']=='audio'
                result={'total':0,'items':[],'page':page,'limit':limit,'mode':'similar',
                        'origin_id':item_id,'origin_kind':origin['kind'],'origin_revision':revision(origin),'profile':self.profile.key,
                        'scope':scope,'source':'acoustic' if is_audio else 'cover','ranking':'max','score_kind':'cosine',
                        'coverage_limit':MAX_ITEMS,'similarity_status':'unsupported_profile'}
                if origin_page is not None:
                    result['origin_page']=origin_page
                if origin_ms is not None:
                    result['origin_ms']=origin_ms
                if not is_audio and 'cover' not in self.profile.modalities:
                    return result if result_sink is None else result_sink(lambda number:{**result,'page':number})
                if is_audio:
                    origin_frames=self.audio_acoustics.acoustic_frames(origin)
                    if not origin_frames:
                        empty={**result,'similarity_status':'unindexed'}
                        return empty if result_sink is None else result_sink(lambda number:{**empty,'page':number})
                    candidate_total=indexed_total=0
                    for rows in self._search_batches(kind,view,scope,check,('audio',),item_id):
                        candidate_total+=len(rows)
                        scores,audio_hits,origin_hits=self.audio_acoustics.score_candidates(rows,origin_frames,check=check)
                        for row in rows:
                            rid=row['id']
                            if rid in scores:
                                pl={'revision':revision(row)}
                                if rid in audio_hits:pl['audio_match_ms']=audio_hits[rid]
                                if rid in origin_hits:pl['origin_match_ms']=origin_hits[rid]
                                spool.add(rid,{'acoustic':scores[rid]},payload=pl)
                        indexed_total+=len(scores)
                        check()
                    spool.finalize('max')
                    def render_page(number):
                        selected=spool.page(number,limit)
                        with self.catalog._guard:
                            check()
                            current,payloads=self._search_page_rows(spool,selected,scope,check)
                            latest=self._current_rows([item_id],scope).get(item_id)
                            if latest is None:raise KeyError(item_id)
                            if revision(latest)!=revision(origin):raise AIBusy('起点の作品が更新されました。類似検索をやり直してください。')
                            items=[]
                            for key,score in selected['ranked']:
                                row_dict={**current[key],'semantic_score':round(score,6),'similarity_origin_id':item_id,
                                          'similarity_evidence':'acoustic'}
                                pl=payloads.get(key,{})
                                if 'audio_match_ms' in pl:row_dict['audio_match_ms']=pl['audio_match_ms']
                                if 'origin_match_ms' in pl:row_dict['origin_match_ms']=pl['origin_match_ms']
                                items.append(row_dict)
                            check()
                        return {**result,'total':selected['total'],'page':number,'items':items,'similarity_status':'ready',
                                'search_complete':True,'search_candidate_total':candidate_total,'indexed_total':indexed_total,'index_limit':MAX_ITEMS}
                    return render_page(page) if result_sink is None else result_sink(render_page)
                if origin_page is not None:
                    query=None
                    try:
                        tag_rev=self.previews.tag_source(item_id)['revision']
                    except (PreviewUnavailable,ReaderChanged,OSError):
                        tag_rev=None
                    if tag_rev is not None:
                        with self.store.connect() as db:
                            rec=db.execute('SELECT vector FROM ai_page_vectors WHERE item_id=? AND source_revision=? AND page=? AND contract=?',
                                (item_id,tag_rev,origin_page,PAGE_CONTRACT)).fetchone()
                        if rec is not None:
                            query=unpack_page_vector(rec[0],self.profile.dimension)
                    if query is None:
                        if not self.encoder.available:
                            empty={**result,'similarity_status':'unindexed'}
                            return empty if result_sink is None else result_sink(lambda number:{**empty,'page':number})
                        try:
                            manifest=self.previews.page_catalog(item_id)
                            if origin_page>=len(manifest['pages']):raise KeyError(item_id)
                            page_bytes,_,_=self.previews.page_source(item_id,origin_page,manifest['revision'])
                            encoded=self.encoder.encode('image',page_bytes)
                            if encoded is not None:query=normalized(encoded,self.profile.dimension)
                        except PreviewBusyError as ex:
                            raise AIBusy('元ページを読み込み中です。少し待ってから再度お試しください。') from ex
                        except (PreviewUnavailable,ReaderChanged,OSError) as ex:
                            raise KeyError(item_id) from ex
                    if query is None:
                        empty={**result,'similarity_status':'unindexed'}
                        return empty if result_sink is None else result_sink(lambda number:{**empty,'page':number})
                    origin_frames=None
                    track_origin_hits=False
                elif origin_ms is not None:
                    query=None
                    if self.encoder.available:
                        try:
                            manifest=self.previews.video_manifest(item_id)
                            try:
                                frame_png,_=self.previews.video_frame(item_id,origin_ms,manifest['revision'])
                            except PreviewUnavailable:
                                if origin_ms<=0:raise
                                frame_png,_=self.previews.video_frame(item_id,max(0,origin_ms-250),manifest['revision'])
                            encoded=self.encoder.encode('image',frame_png)
                            if encoded is not None:query=normalized(encoded,self.profile.dimension)
                        except PreviewBusyError as ex:
                            raise AIBusy('動画のフレームを読み込み中です。少し待ってから再度お試しください。') from ex
                        except (PreviewUnavailable,ReaderChanged,OSError) as ex:
                            raise KeyError(item_id) from ex
                    else:
                        saved_frames=self.store.video_frames(origin)
                        if saved_frames:
                            closest=min(saved_frames,key=lambda pair:abs(pair[0]-origin_ms))
                            if abs(closest[0]-origin_ms)<=1000:
                                query=closest[1]
                    if query is None:
                        empty={**result,'similarity_status':'unindexed'}
                        return empty if result_sink is None else result_sink(lambda number:{**empty,'page':number})
                    origin_frames=None
                    track_origin_hits=False
                elif origin['kind']=='video':
                    origin_frames=self.store.video_frames(origin)
                    if not origin_frames:
                        empty={**result,'similarity_status':'unindexed'}
                        return empty if result_sink is None else result_sink(lambda number:{**empty,'page':number})
                    query=origin_frames[0][1]
                    track_origin_hits=True
                else:
                    query=self.store.cover(origin)
                    if query is None:
                        empty={**result,'similarity_status':'unindexed'}
                        return empty if result_sink is None else result_sink(lambda number:{**empty,'page':number})
                    origin_frames=None
                    track_origin_hits=False
                include_pages=scope is None or scope.get('book_pages')!='cover_only'
                candidate_total=indexed_total=0
                for rows in self._search_batches(kind,view,scope,check,('image','book','archive','video'),item_id):
                    candidate_total+=len(rows)
                    origin_hits={} if track_origin_hits else None
                    page_scores=self.pages.rank(rows,query,check=check) if include_pages else {}
                    scores,video_hits,page_hits,_=self.store.scores_with_content(rows,query,'cover',page_scores=page_scores,query_frames=origin_frames,origin_hits=origin_hits)
                    for row in rows:
                        rid=row['id']
                        if rid in scores:
                            pl={'revision':revision(row)}
                            if rid in video_hits:pl['video_match_ms']=video_hits[rid]
                            if rid in page_hits:pl['ai_page_match']=page_hits[rid]
                            if origin_hits is not None and rid in origin_hits:pl['origin_match_ms']=origin_hits[rid]
                            spool.add(rid,scores[rid],payload=pl)
                    indexed_total+=len(scores)
                    check()
                spool.finalize('max')
                def render_page(number):
                    selected=spool.page(number,limit)
                    with self.catalog._guard:
                        check()
                        current,payloads=self._search_page_rows(spool,selected,scope,check)
                        latest=self._current_rows([item_id],scope).get(item_id)
                        if latest is None:raise KeyError(item_id)
                        if revision(latest)!=revision(origin):raise AIBusy('起点の作品が更新されました。類似検索をやり直してください。')
                        items=[]
                        for key,score in selected['ranked']:
                            row_dict={**current[key],'semantic_score':round(score,6),'similarity_origin_id':item_id,
                                      'similarity_evidence':'cover'}
                            pl=payloads.get(key,{})
                            if 'video_match_ms' in pl:row_dict['video_match_ms']=pl['video_match_ms']
                            if 'ai_page_match' in pl:row_dict['ai_page_match']=pl['ai_page_match']
                            if 'origin_match_ms' in pl:row_dict['origin_match_ms']=pl['origin_match_ms']
                            items.append(row_dict)
                        check()
                    return {**result,'total':selected['total'],'page':number,'items':items,'similarity_status':'ready',
                            'search_complete':True,'search_candidate_total':candidate_total,'indexed_total':indexed_total,'index_limit':MAX_ITEMS}
                return render_page(page) if result_sink is None else result_sink(render_page)
        finally:
            self.inference.release()

    def _release(self,if_idle=False):
        if not self.inference.acquire(blocking=False):
            raise AIBusy('AI検索または索引を処理中です。完了後に解放してください。')
        try:
            if not self.guard.acquire(blocking=False):
                raise AIBusy('AIの状態更新中です。')
            try:
                if self._closed: raise AIUnavailable('AI is closing')
                if self.worker and self.worker.is_alive():
                    raise AIBusy('AI索引を作成中です。')
                # A query or policy update can finish after the timer
                # precheck. Recheck age under both shared guards.
                if if_idle and (not self._idle_seconds or
                        time.monotonic()-self._last_activity < self._idle_seconds):
                    return {"released":False,"resident":bool(getattr(self.encoder,"resident",False))}
                result=self.encoder.release()
                self._last_activity=time.monotonic()
                return result
            finally:
                self.guard.release()
        finally:
            self.inference.release()

    def close(self):
        # Set shutdown first; a pending search cannot relaunch after close.
        with self.guard:
            if self._closed:return
            self._closed=True
            self.search_requests.close()
            self.cancel.set()
            self._idle_stop.set()
            self._idle_wake.set()
        if self._idle_thread and self._idle_thread is not threading.current_thread():
            self._idle_thread.join()
        if self.worker and self.worker.is_alive():
            self.worker.join()
        with self.inference:
            self.encoder.close()
        self.store.checkpoint()

