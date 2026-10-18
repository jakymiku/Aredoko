"""Small, resumable semantic-search slice; source media remain read-only."""
from array import array
from contextlib import contextmanager, nullcontext
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import threading
import time
from ai_process import AIUnavailable
from ai_profiles import DEFAULT_PROFILE
from ai_vectors import normalized
from ai_ranking import POLICIES,fuse_modalities
from library_index import TYPES, _excluded
from ai_scope import validate_scope, scope_clause
from search_terms import normalize, normalize_tags
from ai_result_groups import boundary
from ai_score_spool import ScoreSpool, ScoreSpoolError, SearchCancelled
from previews import PreviewReader, PreviewUnavailable
from search_requests import SearchRequests
from index_continuation import IndexContinuation, JOB as CONTINUATION_JOB, public_state
from tag_semantics import PendingTagVectors
from page_semantics import PageVectors, SCHEMA as PAGE_VECTOR_SCHEMA
from audio_semantics import AudioSpeechVectors, SCHEMA as AUDIO_SEGMENT_SCHEMA

MAX_ITEMS=10_000
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

class VectorStore:
    def __init__(self,path,profile=DEFAULT_PROFILE):
        self.path=Path(path)
        self.profile=profile
        self.dimension=profile.dimension
        with self.connect() as db:
            db.executescript('''
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
            profile=db.execute('SELECT value FROM ai_profile').fetchone()
            if profile and profile[0]!=self.profile.key: raise AIUnavailable('Vector profile mismatch')
            if not profile: db.execute('INSERT INTO ai_profile VALUES(?)',(self.profile.key,))
        state=self.state()
        if state.get('state') in ('running','cancelling'):
            self.save_state({**state,'state':'interrupted','error':'索引作成が中断されました。再実行で保存済み分から続けられます。'})
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=2)
        try:
            with db: yield db
        finally: db.close()
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
    def put(self,item_id,rev,vectors,video_frames=None,*,source_contract=None):
        # Validate every modality before replacing the previous revision atomically.
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
        with self.connect() as db:
            db.execute('DELETE FROM ai_vectors WHERE item_id=?',(item_id,))
            db.execute('DELETE FROM ai_video_frames WHERE item_id=?',(item_id,))
            db.execute('DELETE FROM ai_source_contracts WHERE item_id=?',(item_id,))
            db.executemany('INSERT INTO ai_vectors VALUES(?,?,?,?)',[(item_id,rev,mode,data) for mode,data in packed.items()])
            if packed_frames:
                db.executemany('INSERT INTO ai_video_frames VALUES(?,?,?,?)',packed_frames)
            if source_contract is not None:
                db.execute('INSERT INTO ai_source_contracts VALUES(?,?,?)',(item_id,rev,source_contract))
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
        with self.connect() as db:
            for offset in range(0,len(ids),ROW_BATCH_SIZE):
                batch=ids[offset:offset+ROW_BATCH_SIZE]
                sql='SELECT * FROM ai_vectors WHERE item_id IN ('+','.join('?' for _ in batch)+')'
                for item_id,rev,mode,data in db.execute(sql,batch):
                    if mode not in self.profile.modalities or eligible.get(item_id)!=rev or source!='all' and mode!=source: continue
                    try:
                        vec=array('f');vec.frombytes(data)
                    except (ValueError,TypeError):continue
                    if len(vec)!=self.dimension or any(not math.isfinite(x) for x in vec) or abs(sum(x*x for x in vec)-1)>1e-4: continue
                    if is_multi and mode=='cover':
                        best_score=None;best_orig_ms=0
                        for orig_ms,orig_vec in active_frames:
                            s=sum(a*b for a,b in zip(orig_vec,vec))
                            if best_score is None or s>best_score:
                                best_score=s;best_orig_ms=orig_ms
                        scores.setdefault(item_id,{})[mode]=best_score
                        if origin_hits is not None:origin_hits[item_id]=best_orig_ms
                    else:
                        score=sum(a*b for a,b in zip(active_frames[0][1],vec))
                        scores.setdefault(item_id,{})[mode]=score
                        if origin_hits is not None and mode=='cover':origin_hits[item_id]=active_frames[0][0]
                if source in ('all','cover') and 'cover' in self.profile.modalities:
                    vsql='SELECT item_id,revision,at_ms,vector FROM ai_video_frames WHERE item_id IN ('+','.join('?' for _ in batch)+') ORDER BY item_id,at_ms'
                    for item_id,rev,at_ms,data in db.execute(vsql,batch):
                        if eligible.get(item_id)!=rev:continue
                        if not (isinstance(at_ms,int) and 0<=at_ms<=86_400_000):continue
                        try:
                            vec=array('f');vec.frombytes(data)
                        except (ValueError,TypeError):continue
                        if len(vec)!=self.dimension or any(not math.isfinite(x) for x in vec) or abs(sum(x*x for x in vec)-1)>1e-4:continue
                        if is_multi:
                            for orig_ms,orig_vec in active_frames:
                                score=sum(a*b for a,b in zip(orig_vec,vec))
                                prev=scores.get(item_id,{}).get('cover')
                                if prev is None or score>prev or (score==prev and item_id not in video_hits):
                                    scores.setdefault(item_id,{})['cover']=score
                                    video_hits[item_id]=at_ms
                                    if origin_hits is not None:origin_hits[item_id]=orig_ms
                        else:
                            score=sum(a*b for a,b in zip(active_frames[0][1],vec))
                            prev=scores.get(item_id,{}).get('cover')
                            if prev is None or score>prev or (score==prev and item_id not in video_hits):
                                scores.setdefault(item_id,{})['cover']=score
                                video_hits[item_id]=at_ms
                                if origin_hits is not None:origin_hits[item_id]=active_frames[0][0]
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
                    if prev is None or score>prev:
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
        self.store=VectorStore(store_path or self.profile.store_path(catalog.path),self.profile)
        self.previews=PreviewReader(catalog)
        self.pages=PageVectors(self)
        self.audio_speech=AudioSpeechVectors(self)
        self.guard=threading.Lock()
        self.cancel=threading.Event()
        self.worker=None
        self.inference=threading.Lock()
        self._closed=False
        self.search_requests=SearchRequests()
        self.continuation=IndexContinuation(self,MAX_ITEMS)
        self._last_activity=time.monotonic()
        self._idle_seconds=0
        self._index_pause_ms=0
        self._idle_stop=threading.Event()
        self._idle_wake=threading.Event()
        self._idle_thread=None

    def configure(self,idle_release_seconds=0,index_pause_ms=0):
        """Runtime resource policy, independent of vector-space identity."""
        if type(idle_release_seconds) is not int or not 0<=idle_release_seconds<=3600:
            raise ValueError('Idle release must be 0..3600 seconds')
        if type(index_pause_ms) is not int or not 0<=index_pause_ms<=2000:
            raise ValueError('Index pause must be 0..2000 milliseconds')
        with self.guard:
            if self._closed: raise AIUnavailable('AI is closing')
            self._idle_seconds=idle_release_seconds
            self._index_pause_ms=index_pause_ms
            if idle_release_seconds and self._idle_thread is None:
                self._idle_thread=threading.Thread(target=self._idle_loop,name='aredoko-ai-idle',daemon=True)
                self._idle_thread.start()
            self._idle_wake.set()
        return self.resource_policy()

    def resource_policy(self):
        return {'idle_release_seconds':self._idle_seconds,'index_pause_ms':self._index_pause_ms}

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

    def _iter_rows(self,kind='',view='all',limit=MAX_ITEMS,scope=None,*,all_candidates=False,check=None):
        if kind and kind not in TYPES or view not in ('all','favorites','unreviewed','shelf'):
            raise ValueError('Invalid filter')
        if type(limit) is not int or not 1<=limit<=MAX_ITEMS:
            raise ValueError('Invalid candidate limit')
        scope=self._scope(scope)
        scoped_where,values=scope_clause(scope)
        where=["l.status='present'",'r.enabled=1',*scoped_where]
        if kind: where.append('i.kind=?');values.append(kind)
        where.extend({'favorites':['i.favorite=1'],'unreviewed':['i.reviewed=0'],'shelf':["i.shelf<>''"],'all':[]}[view])
        # New records cannot lengthen a running enumeration indefinitely.
        with self.catalog.connect() as db:
            upper=db.execute('SELECT COALESCE(MAX(id),0) FROM items').fetchone()[0]
        # Multiple root indexes can make SQLite repeatedly sort the whole
        # selected population for each 256-row page. Pin the ID-range driver
        # for multi-root keyset reads; keep the selective single-root plan.
        join=self.catalog.JOIN+'JOIN library_roots r ON r.id=l.root_id '
        if scope is not None and scope['root_ids'] is not None and len(scope['root_ids'])>1:
            join=join.replace(' JOIN ',' CROSS JOIN ')
        last=0;yielded=0
        while last<upper and (all_candidates or yielded<limit):
            if check is not None:check()
            with self.catalog.connect() as db:
                rows=db.execute('SELECT '+self.catalog.FIELDS+',r.excludes_json'+join+'WHERE '+' AND '.join(where)+
                    ' AND i.id>? AND i.id<=? ORDER BY i.id LIMIT ?',
                    values+[last,upper,ROW_BATCH_SIZE]).fetchall()
            if not rows:break
            last=rows[-1]['id']
            # Exclusions do not consume eligible coverage, even before a rescan.
            for row in rows:
                if _excluded(row['relative_path'],tuple(json.loads(row['excludes_json']))):continue
                yield self.catalog.item(row);yielded+=1
                if not all_candidates and yielded>=limit:break
    def _rows(self,kind='',view='all',limit=MAX_ITEMS):
        # Legacy bounded metadata helper; full searches use _search_batches.
        return list(self._iter_rows(kind,view,limit))
    def _current_rows(self,ids,scope=None):
        if not ids:return {}
        if len(ids)>ROW_BATCH_SIZE:raise ValueError('Metadata batch exceeds limit')
        scoped_where,values=scope_clause(scope)
        clause=" AND "+" AND ".join(scoped_where) if scoped_where else ''
        with self.catalog.connect() as db:
            rows=db.execute('SELECT '+self.catalog.FIELDS+',r.excludes_json'+self.catalog.JOIN+
                'JOIN library_roots r ON r.id=l.root_id WHERE i.id IN ('+
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
        scope=self._scope(scope)
        with self.guard:
            if self._closed:raise AIUnavailable('AI is closing')
        if self.catalog.scan_state()['state'] in ('running','cancelling'):
            raise AIBusy('フォルダのスキャン完了後に確認してください。')
        total=targeted=fresh=0;batch=[]
        for row in self._iter_rows(limit=limit,scope=scope,all_candidates=True):
            total+=1
            if targeted<limit:
                targeted+=1;batch.append(row)
                if len(batch)==ROW_BATCH_SIZE:
                    pending=self.pending_tags.snapshots([r['id'] for r in batch])
                    regular=self.store.fresh_ids(batch)
                    fresh+=len((regular-set(pending)) | (regular & self.pending_tags.ready_ids(pending)));batch.clear()
        pending=self.pending_tags.snapshots([r['id'] for r in batch])
        regular=self.store.fresh_ids(batch)
        fresh+=len((regular-set(pending)) | (regular & self.pending_tags.ready_ids(pending)))
        return {'scope':scope,'candidate_total':total,'target_total':targeted,
                'fresh_total':fresh,'remaining_total':targeted-fresh,
                'coverage_limit':MAX_ITEMS,'index_limit':limit,'refresh_required_on_change':True}

    def status(self):
        with self.guard: state=self.store.state()
        resident=bool(getattr(self.encoder,'resident',False))
        return {**public_state(state),'available':self.encoder.available,
                'resident':resident,'worker_state':'loaded' if resident else 'unloaded',
                'device':getattr(self.encoder,'device','') if resident else '',
                'limit':MAX_ITEMS,'model':self.profile.label,'model_id':self.profile.model_id,'profile':self.profile.key,
                'modalities':list(self.profile.modalities),'dimension':self.profile.dimension,'ranking':self.ranking,
                'telemetry':getattr(self.encoder,'telemetry',{}) if resident else {},
                'resource_policy':self.resource_policy()}
    def start(self,limit=MAX_ITEMS,scope=None):
        if type(limit) is not int or not 1<=limit<=MAX_ITEMS: raise ValueError('Invalid index limit')
        scope=self._scope(scope)
        if not self.encoder.available: raise AIUnavailable('AI環境が未導入です。setup-ai.ps1を実行してください。')
        with self.guard:
            if self._closed: raise AIUnavailable('AI is closing')
            if self.worker and self.worker.is_alive(): raise AIBusy('AI索引を作成中です。')
            if self.catalog.scan_state()['state'] in ('running','cancelling'): raise AIBusy('フォルダのスキャン完了後に実行してください。')
            ids=[row['id'] for row in self._iter_rows(limit=limit,scope=scope)]
            self.cancel.clear()
            self.store.save_state({'state':'running','processed':0,'total':len(ids),'indexed':0,'skipped':0,'error':'','scope':scope})
            self.worker=threading.Thread(target=self._build,args=(ids,scope),daemon=True)
            self.worker.start()
        return self.status()
    def _build(self,ids,scope=None,initial_state=None):
        state=dict(initial_state) if initial_state is not None else {'state':'running','processed':0,'total':len(ids),'indexed':0,'skipped':0,'error':'','scope':scope}
        continuing=state.get('job')==CONTINUATION_JOB
        if continuing:state['_pins']={item:(rev,sig) for item,rev,sig in state['continuation']['entries']}
        def saved():return {k:v for k,v in state.items() if k!='_pins'}
        try:
            with self.inference:
                for offset in range(0,len(ids),ROW_BATCH_SIZE):
                    if self.cancel.is_set():break
                    batch=ids[offset:offset+ROW_BATCH_SIZE]
                    if continuing:
                        with self.catalog._guard:self.continuation.check(state,batch)
                    rows=self._current_rows(batch,scope)
                    pending=self.pending_tags.snapshots(list(rows))
                    for item_id in batch:
                        if self.cancel.is_set():break
                        did_infer=False
                        indexed_before=state['indexed']
                        row=rows.get(item_id)
                        if row is None:
                            state['skipped']+=1
                        else:
                            rev=revision(row)
                            if not self.store.fresh_row(row):
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
                        if did_infer and state['processed']<len(ids) and self._index_pause_ms:
                            if self.cancel.wait(self._index_pause_ms/1000):
                                break
                if continuing and not self.cancel.is_set():
                    with self.catalog._guard:
                        for offset in range(0,len(ids),ROW_BATCH_SIZE):
                            self.continuation.check(state,ids[offset:offset+ROW_BATCH_SIZE])
                state['state']='cancelled' if self.cancel.is_set() else 'complete'
        except InterruptedError:
            state['state']='cancelled' if self.cancel.is_set() else 'failed'
            if not self.cancel.is_set():state['error']='索引を完了できませんでした。対象を確認してください。'
        except Exception as ex:
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
    def search(self,query,kind='',view='all',page=0,limit=60,source='all',ranking=None,scope=None,literal_only=False,group_threshold=None,result_group='all',*,cancelled=None):
        if not isinstance(query,str) or not 0<len(query.strip())<=300 or type(page) is not int or page<0 or type(limit) is not int or not 1<=limit<=120:
            raise ValueError('Invalid semantic search')
        if result_group not in ('all','leading','other'):raise ValueError('Invalid result group')
        if type(literal_only) is not bool:raise ValueError('Invalid literal evidence filter')
        scope=self._scope(scope)
        if not isinstance(kind,str) or kind and kind not in TYPES or view not in ('all','favorites','unreviewed','shelf'):
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
                for rows in self._search_batches(kind,view,scope,check,allowed):
                    candidate_total+=len(rows)
                    if query_vector is None:
                        query_vector=normalized(self.encoder.encode('query',query),self.profile.dimension)
                    check()
                    page_scores=self.pages.rank(rows,query_vector,check=check) if source in ('all','cover') else {}
                    audio_scores=self.audio_speech.rank(rows,query_vector,check=check) if source in ('all','text') else {}
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
                selected=spool.page(page,limit,literal_only=literal_only,group_threshold=group_threshold,result_group=result_group)
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
                    check()
                return {**{key:val for key,val in selected.items() if key!='ranked'},'items':items,'mode':'semantic',
                        'coverage_limit':MAX_ITEMS,'index_limit':MAX_ITEMS,'source':source,'ranking':selected_policy,
                        'score_kind':'reciprocal-rank' if selected_policy=='mean-rrf' else 'cosine',
                        'scope':scope,'literal_only':literal_only,'result_group':result_group,
                        'search_complete':True,'search_candidate_total':candidate_total,'indexed_total':indexed_total}
        finally:
            self._last_activity=time.monotonic()
            self.inference.release()

    def release(self):
        """Refuse a busy encoder; never touch the profile, catalog or vector DB."""
        return self._release()

    def similar(self,item_id,kind='',view='all',page=0,limit=60,scope=None,*,cancelled=None):
        """Item-origin cover cosine search. Cached vectors work with no model installed.

        The origin must be in scope, but need not satisfy result-only kind/view
        filters. Missing/stale cover vectors return an explicit empty fallback,
        never a text embedding masquerading as an image match.
        """
        if type(item_id) is not int or not 1<=item_id<=9223372036854775807:
            raise ValueError('Invalid item')
        if type(page) is not int or page<0 or type(limit) is not int or not 1<=limit<=120:
            raise ValueError('Invalid paging')
        if not isinstance(kind,str) or kind and kind not in TYPES or view not in ('all','favorites','unreviewed','shelf'):
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
                if origin['kind'] not in ('image','book','archive','video'):
                    raise ValueError('Invalid similarity source')
                result={'total':0,'items':[],'page':page,'limit':limit,'mode':'similar',
                        'origin_id':item_id,'origin_kind':origin['kind'],'origin_revision':revision(origin),'profile':self.profile.key,
                        'scope':scope,'source':'cover','ranking':'max','score_kind':'cosine',
                        'coverage_limit':MAX_ITEMS,'similarity_status':'unsupported_profile'}
                if 'cover' not in self.profile.modalities:return result
                if origin['kind']=='video':
                    origin_frames=self.store.video_frames(origin)
                    if not origin_frames:return {**result,'similarity_status':'unindexed'}
                    query=origin_frames[0][1]
                    track_origin_hits=True
                else:
                    query=self.store.cover(origin)
                    if query is None:return {**result,'similarity_status':'unindexed'}
                    origin_frames=None
                    track_origin_hits=False
                candidate_total=indexed_total=0
                for rows in self._search_batches(kind,view,scope,check,('image','book','archive','video'),item_id):
                    candidate_total+=len(rows)
                    origin_hits={} if track_origin_hits else None
                    scores,video_hits,_,_=self.store.scores_with_content(rows,query,'cover',query_frames=origin_frames,origin_hits=origin_hits)
                    for row in rows:
                        rid=row['id']
                        if rid in scores:
                            pl={'revision':revision(row)}
                            if rid in video_hits:pl['video_match_ms']=video_hits[rid]
                            if origin_hits is not None and rid in origin_hits:pl['origin_match_ms']=origin_hits[rid]
                            spool.add(rid,scores[rid],payload=pl)
                    indexed_total+=len(scores)
                    check()
                spool.finalize('max');selected=spool.page(page,limit)
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
                        if 'origin_match_ms' in pl:row_dict['origin_match_ms']=pl['origin_match_ms']
                        items.append(row_dict)
                    check()
                return {**result,'total':selected['total'],'items':items,'similarity_status':'ready',
                        'search_complete':True,'search_candidate_total':candidate_total,'indexed_total':indexed_total,'index_limit':MAX_ITEMS}
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

