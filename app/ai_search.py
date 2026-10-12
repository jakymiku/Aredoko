"""Small, resumable semantic-search slice; source media remain read-only."""
from array import array
from contextlib import contextmanager
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
from previews import PreviewReader, PreviewUnavailable

MAX_ITEMS=10_000
ROW_BATCH_SIZE=256
PROGRESS_INTERVAL=16
class AIBusy(RuntimeError): pass

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
                CREATE TABLE IF NOT EXISTS ai_state(id INTEGER PRIMARY KEY CHECK(id=1), json TEXT NOT NULL);
            ''')
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
        eligible={row['id']:revision(row) for row in rows}
        with self.connect() as db:
            records=db.execute("SELECT item_id,revision FROM ai_vectors WHERE modality='text' AND item_id IN ("+
                ','.join('?' for _ in eligible)+')',list(eligible)).fetchall()
        return {item_id for item_id,rev in records if eligible.get(item_id)==rev}

    def fresh(self,item_id,rev):
        with self.connect() as db:
            return db.execute("SELECT 1 FROM ai_vectors WHERE item_id=? AND revision=? AND modality='text'",(item_id,rev)).fetchone() is not None
    def put(self,item_id,rev,vectors):
        # Validate every modality before replacing the previous revision atomically.
        if not vectors or any(mode not in self.profile.modalities for mode in vectors):
            raise ValueError('Unsupported vector modality')
        packed={mode:array('f',normalized(vec,self.dimension)).tobytes() for mode,vec in vectors.items()}
        with self.connect() as db:
            db.execute('DELETE FROM ai_vectors WHERE item_id=?',(item_id,))
            db.executemany('INSERT INTO ai_vectors VALUES(?,?,?,?)',[(item_id,rev,mode,data) for mode,data in packed.items()])
    def rank(self,rows,query,source="all",ranking="max"):
        if ranking not in POLICIES:raise ValueError('Unknown ranking policy')
        query=normalized(query,self.dimension)
        eligible={row['id']:revision(row) for row in rows}
        scores={}
        # Read only candidate IDs; unrelated persisted vectors need not be scanned.
        ids=list(eligible)
        with self.connect() as db:
            for offset in range(0,len(ids),ROW_BATCH_SIZE):
                batch=ids[offset:offset+ROW_BATCH_SIZE]
                sql='SELECT * FROM ai_vectors WHERE item_id IN ('+','.join('?' for _ in batch)+')'
                for item_id,rev,mode,data in db.execute(sql,batch):
                    if mode not in self.profile.modalities or eligible.get(item_id)!=rev or source!='all' and mode!=source: continue
                    vec=array('f');vec.frombytes(data)
                    if len(vec)!=self.dimension or any(not math.isfinite(x) for x in vec): continue
                    score=sum(a*b for a,b in zip(query,vec))
                    scores.setdefault(item_id,{})[mode]=score
        # Fusion uses global positions, never per-batch ranks.
        return fuse_modalities(scores,ranking)

class AISearch:
    def __init__(self,catalog,encoder,store_path=None,ranking='mean-rrf'):
        if ranking not in POLICIES:raise ValueError('Unknown ranking policy')
        self.ranking=ranking
        self.catalog,self.encoder=catalog,encoder
        self.profile=getattr(encoder,'profile',DEFAULT_PROFILE)
        self.store=VectorStore(store_path or self.profile.store_path(catalog.path),self.profile)
        self.previews=PreviewReader(catalog)
        self.guard=threading.Lock()
        self.cancel=threading.Event()
        self.worker=None
        self.inference=threading.Lock()
        self._closed=False
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
                count=db.execute('SELECT count(*) FROM library_roots WHERE id IN ('+
                    ','.join('?' for _ in roots)+')',roots).fetchone()[0]
            if count!=len(roots):raise ValueError('Unknown registered root')
        return scope

    def _iter_rows(self,kind='',view='all',limit=MAX_ITEMS,scope=None,*,all_candidates=False):
        if kind and kind not in TYPES or view not in ('all','favorites','unreviewed','shelf'):
            raise ValueError('Invalid filter')
        if type(limit) is not int or not 1<=limit<=MAX_ITEMS:
            raise ValueError('Invalid candidate limit')
        scope=self._scope(scope)
        scoped_where,values=scope_clause(scope)
        where=["l.status='present'",*scoped_where]
        if kind: where.append('i.kind=?');values.append(kind)
        where.extend({'favorites':['i.favorite=1'],'unreviewed':['i.reviewed=0'],'shelf':["i.shelf<>''"],'all':[]}[view])
        # New records cannot lengthen a running enumeration indefinitely.
        with self.catalog.connect() as db:
            upper=db.execute('SELECT COALESCE(MAX(id),0) FROM items').fetchone()[0]
        last=0;yielded=0
        while last<upper and (all_candidates or yielded<limit):
            with self.catalog.connect() as db:
                rows=db.execute('SELECT '+self.catalog.FIELDS+',r.excludes_json'+self.catalog.JOIN+
                    'JOIN library_roots r ON r.id=l.root_id WHERE '+' AND '.join(where)+
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
        # Search metadata/scores are bounded by MAX_ITEMS; build keeps only IDs.
        return list(self._iter_rows(kind,view,limit))
    def _current_rows(self,ids,scope=None):
        if not ids:return {}
        if len(ids)>ROW_BATCH_SIZE:raise ValueError('Metadata batch exceeds limit')
        scoped_where,values=scope_clause(scope)
        clause=" AND "+" AND ".join(scoped_where) if scoped_where else ''
        with self.catalog.connect() as db:
            rows=db.execute('SELECT '+self.catalog.FIELDS+',r.excludes_json'+self.catalog.JOIN+
                'JOIN library_roots r ON r.id=l.root_id WHERE i.id IN ('+
                ','.join('?' for _ in ids)+") AND l.status='present'"+clause,ids+values).fetchall()
        return {row['id']:self.catalog.item(row) for row in rows
                if not _excluded(row['relative_path'],tuple(json.loads(row['excludes_json'])))}
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
                    fresh+=len(self.store.fresh_ids(batch));batch.clear()
        fresh+=len(self.store.fresh_ids(batch))
        return {'scope':scope,'candidate_total':total,'target_total':targeted,
                'fresh_total':fresh,'remaining_total':targeted-fresh,
                'coverage_limit':MAX_ITEMS,'index_limit':limit,'refresh_required_on_change':True}

    def status(self):
        with self.guard: state=self.store.state()
        resident=bool(getattr(self.encoder,'resident',False))
        return {**state,'available':self.encoder.available,
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
    def _build(self,ids,scope=None):
        state={'state':'running','processed':0,'total':len(ids),'indexed':0,'skipped':0,'error':'','scope':scope}
        try:
            with self.inference:
                for offset in range(0,len(ids),ROW_BATCH_SIZE):
                    if self.cancel.is_set():break
                    batch=ids[offset:offset+ROW_BATCH_SIZE]
                    rows=self._current_rows(batch,scope)
                    for item_id in batch:
                        if self.cancel.is_set():break
                        did_infer=False
                        row=rows.get(item_id)
                        if row is None:
                            state['skipped']+=1
                        else:
                            rev=revision(row)
                            if not self.store.fresh(item_id,rev):
                                text=row['title']+'\n'+row['relative_path']+'\n'+'、'.join(row['tags'])
                                vectors={'text':self.encoder.encode('document',text[:4096])}
                                did_infer=True
                                if 'cover' in self.profile.modalities and row['kind'] in ('image','book','archive'):
                                    try:
                                        source,_=self.previews.read(item_id)
                                        cover=self.encoder.encode('image',source)
                                        if cover is not None:vectors['cover']=cover
                                    except (PreviewUnavailable,OSError):pass
                                # Recheck presence, exclusions and revision before publishing.
                                current=self._current_rows([item_id],scope).get(item_id)
                                if current is None or revision(current)!=rev:
                                    state['skipped']+=1
                                else:
                                    self.store.put(item_id,rev,vectors);state['indexed']+=1
                            else:state['indexed']+=1
                        state['processed']+=1
                        # Vectors commit atomically per item. Progress may lag by 15;
                        # a restart discovers saved revisions rather than re-encoding.
                        if state['processed']%PROGRESS_INTERVAL==0:
                            with self.guard:
                                self.store.save_state({**state,'state':'cancelling' if self.cancel.is_set() else 'running'})
                        # Load-shedding is optional and cancelable. Not a GPU
                        # utilization/FPS limit. Never pace interactive search.
                        if did_infer and state['processed']<len(ids) and self._index_pause_ms:
                            if self.cancel.wait(self._index_pause_ms/1000):
                                break
                state['state']='cancelled' if self.cancel.is_set() else 'complete'
        except Exception as ex:
            state['state']='failed';state['error']='AI索引を作成できませんでした（'+type(ex).__name__+'）。ローカルログを確認してください。'
        finally:
            # Covers both actual inference and cached rebuilds.
            self._last_activity=time.monotonic()
            with self.guard:self.store.save_state(state)
    def cancel_build(self):
        self.cancel.set()
        with self.guard:
            state=self.store.state()
            if state['state']=='running': self.store.save_state({**state,'state':'cancelling'})
        return {'cancel_requested':True}
    def search(self,query,kind='',view='all',page=0,limit=60,source='all',ranking=None,scope=None):
        if not isinstance(query,str) or not 0<len(query.strip())<=300 or type(page) is not int or page<0 or not 1<=limit<=120:
            raise ValueError('Invalid semantic search')
        scope=self._scope(scope)
        if not isinstance(kind,str) or kind and kind not in TYPES or view not in ('all','favorites','unreviewed','shelf'):
            raise ValueError('Invalid filter')
        ranking=self.ranking if ranking is None else ranking
        if ranking not in POLICIES:raise ValueError('Unknown ranking policy')
        if source not in ('all','text','cover'): raise ValueError('Invalid semantic source')
        if source=='cover' and 'cover' not in self.profile.modalities:
            raise AIUnavailable('選択中のモデルは画像・表紙検索に対応していません。AI意味検索を使ってください。')
        if not self.encoder.available: raise AIUnavailable('AI環境が未導入です。')
        if not self.inference.acquire(blocking=False): raise AIBusy('AI索引を作成中です。完了後に検索してください。')
        try:
            if self._closed: raise AIUnavailable('AI is closing')
            if scope is None:
                rows=self._rows(kind,view)
            else:
                # Apply search filters AFTER the shared scoped target cap.
                rows=[row for row in self._iter_rows(limit=MAX_ITEMS,scope=scope)
                      if (not kind or row['kind']==kind) and
                      (view=='all' or view=='favorites' and row['favorite'] or
                       view=='unreviewed' and not row['reviewed'] or view=='shelf' and row['shelf'])]
            policy=ranking if source=='all' and 'cover' in self.profile.modalities else 'max'
            ranked=self.store.rank(rows,self.encoder.encode('query',query),source,policy) if rows else []
            by_id={row['id']:row for row in rows}
            items=[{**by_id[item_id],'semantic_score':round(score,6)} for item_id,score in ranked[page*limit:(page+1)*limit]]
            return {'total':len(ranked),'page':page,'limit':limit,'items':items,'mode':'semantic','coverage_limit':MAX_ITEMS,'source':source,'ranking':policy,
                    'score_kind':'reciprocal-rank' if policy=='mean-rrf' else 'cosine','scope':scope}
        finally:
            self._last_activity=time.monotonic()
            self.inference.release()

    def release(self):
        """Refuse a busy encoder; never touch the profile, catalog or vector DB."""
        return self._release()

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
            self.cancel.set()
            self._idle_stop.set()
            self._idle_wake.set()
        if self._idle_thread and self._idle_thread is not threading.current_thread():
            self._idle_thread.join()
        if self.worker and self.worker.is_alive():
            self.worker.join()
        with self.inference:
            self.encoder.close()

