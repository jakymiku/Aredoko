"""Small, resumable semantic-search slice; source media remain read-only."""
from array import array
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import threading
from ai_process import AIUnavailable
from ai_profiles import DEFAULT_PROFILE
from ai_vectors import normalized
from library_index import TYPES, _excluded
from previews import PreviewReader, PreviewUnavailable

MAX_ITEMS=2000
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
    def rank(self,rows,query,source="all"):
        query=normalized(query,self.dimension)
        eligible={row['id']:revision(row) for row in rows}
        scores={}
        with self.connect() as db:
            for item_id,rev,mode,data in db.execute('SELECT * FROM ai_vectors'):
                if mode not in self.profile.modalities or eligible.get(item_id)!=rev or source!='all' and mode!=source: continue
                vec=array('f');vec.frombytes(data)
                if len(vec)!=self.dimension or any(not math.isfinite(x) for x in vec): continue
                score=sum(a*b for a,b in zip(query,vec))
                # Separate text and cover vectors; either modality can find the item.
                scores[item_id]=max(scores.get(item_id,-2),score)
        return sorted(scores.items(),key=lambda x:(-x[1],x[0]))

class AISearch:
    def __init__(self,catalog,encoder,store_path=None):
        self.catalog,self.encoder=catalog,encoder
        self.profile=getattr(encoder,'profile',DEFAULT_PROFILE)
        self.store=VectorStore(store_path or self.profile.store_path(catalog.path),self.profile)
        self.previews=PreviewReader(catalog)
        self.guard=threading.Lock()
        self.cancel=threading.Event()
        self.worker=None
        self.inference=threading.Lock()
    def _rows(self,kind='',view='all',limit=MAX_ITEMS):
        if kind and kind not in TYPES or view not in ('all','favorites','unreviewed','shelf'):
            raise ValueError('Invalid filter')
        where=["l.status='present'"]
        values=[]
        if kind: where.append('i.kind=?');values.append(kind)
        where.extend({'favorites':['i.favorite=1'],'unreviewed':['i.reviewed=0'],'shelf':["i.shelf<>''"],'all':[]}[view])
        with self.catalog.connect() as db:
            rows=db.execute('SELECT '+self.catalog.FIELDS+',r.excludes_json'+self.catalog.JOIN+
                'JOIN library_roots r ON r.id=l.root_id WHERE '+' AND '.join(where)+' ORDER BY i.id LIMIT ?',values+[limit]).fetchall()
        # Current exclusions apply even before a filesystem rescan.
        return [self.catalog.item(row) for row in rows if not _excluded(row['relative_path'],tuple(json.loads(row['excludes_json'])))]
    def status(self):
        with self.guard: state=self.store.state()
        return {**state,'available':self.encoder.available,'device':getattr(self.encoder,'device',''),
                'limit':MAX_ITEMS,'model':self.profile.label,'model_id':self.profile.model_id,'profile':self.profile.key,
                'modalities':list(self.profile.modalities),'dimension':self.profile.dimension,'telemetry':getattr(self.encoder,'telemetry',{})}
    def start(self,limit=MAX_ITEMS):
        if type(limit) is not int or not 1<=limit<=MAX_ITEMS: raise ValueError('Invalid index limit')
        if not self.encoder.available: raise AIUnavailable('AI環境が未導入です。setup-ai.ps1を実行してください。')
        with self.guard:
            if self.worker and self.worker.is_alive(): raise AIBusy('AI索引を作成中です。')
            if self.catalog.scan_state()['state'] in ('running','cancelling'): raise AIBusy('フォルダのスキャン完了後に実行してください。')
            rows=self._rows(limit=limit)
            self.cancel.clear()
            self.store.save_state({'state':'running','processed':0,'total':len(rows),'indexed':0,'skipped':0,'error':''})
            self.worker=threading.Thread(target=self._build,args=(rows,),daemon=True)
            self.worker.start()
        return self.status()
    def _build(self,rows):
        state={'state':'running','processed':0,'total':len(rows),'indexed':0,'skipped':0,'error':''}
        try:
            with self.inference:
                for row in rows:
                    if self.cancel.is_set(): state['state']='cancelled';break
                    rev=revision(row)
                    if not self.store.fresh(row['id'],rev):
                        text=row['title']+'\n'+row['relative_path']+'\n'+'、'.join(row['tags'])
                        vectors={'text':self.encoder.encode('document',text[:4096])}
                        if 'cover' in self.profile.modalities and row['kind'] in ('image','book','archive'):
                            try:
                                source,_=self.previews.read(row['id'])
                                cover=self.encoder.encode('image',source)
                                if cover is not None: vectors['cover']=cover
                            except (PreviewUnavailable,OSError):
                                pass
                        # A metadata/scan change while encoding cannot publish a stale result.
                        current=self.catalog.get(row['id'])
                        if revision(current)!=rev or current['availability']!='present':
                            state['skipped']+=1
                        else:
                            self.store.put(row['id'],rev,vectors);state['indexed']+=1
                    else: state['indexed']+=1
                    state['processed']+=1
                    with self.guard: self.store.save_state(state)
                else: state['state']='complete'
        except Exception as ex:
            state['state']='failed';state['error']='AI索引を作成できませんでした（'+type(ex).__name__+'）。ローカルログを確認してください。'
        finally:
            with self.guard: self.store.save_state(state)
    def cancel_build(self):
        self.cancel.set()
        with self.guard:
            state=self.store.state()
            if state['state']=='running': self.store.save_state({**state,'state':'cancelling'})
        return {'cancel_requested':True}
    def search(self,query,kind='',view='all',page=0,limit=60,source='all'):
        if not isinstance(query,str) or not 0<len(query.strip())<=300 or type(page) is not int or page<0 or not 1<=limit<=120:
            raise ValueError('Invalid semantic search')
        if source not in ('all','text','cover'): raise ValueError('Invalid semantic source')
        if source=='cover' and 'cover' not in self.profile.modalities:
            raise AIUnavailable('選択中のモデルは画像・表紙検索に対応していません。AI意味検索を使ってください。')
        if not self.encoder.available: raise AIUnavailable('AI環境が未導入です。')
        if not self.inference.acquire(blocking=False): raise AIBusy('AI索引を作成中です。完了後に検索してください。')
        try:
            rows=self._rows(kind,view)
            ranked=self.store.rank(rows,self.encoder.encode('query',query),source)
            by_id={row['id']:row for row in rows}
            items=[{**by_id[item_id],'semantic_score':round(score,6)} for item_id,score in ranked[page*limit:(page+1)*limit]]
            return {'total':len(ranked),'page':page,'limit':limit,'items':items,'mode':'semantic','coverage_limit':MAX_ITEMS,'source':source}
        finally: self.inference.release()
    def close(self):
        self.cancel.set()
        self.encoder.close()
        if self.worker: self.worker.join(timeout=10)

