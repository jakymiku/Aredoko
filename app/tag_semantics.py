"""Separate pending-tag embeddings; never promote proposals to confirmed tags."""
import hashlib
import json
import sqlite3
import time

from ai_process import AIUnavailable
from ai_vectors import normalized
from previews import PreviewUnavailable, PreviewBusyError, ReaderChanged

CONTRACT='pending-raw-tags:v1'


class PendingTagVectors:
    def __init__(self,ai):self.ai=ai

    def snapshots(self,ids):
        if not ids:return {}
        if len(ids)>256:raise ValueError('Candidate metadata batch exceeds limit')
        with self.ai.catalog.connect() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tag_proposal_batches'").fetchone():return {}
            marks=','.join('?' for _ in ids)
            batches=db.execute('SELECT * FROM tag_proposal_batches b WHERE item_id IN ('+marks+
                ') AND b.id=(SELECT max(n.id) FROM tag_proposal_batches n WHERE n.item_id=b.item_id)',ids).fetchall()
            result={}
            current=self.ai._current_rows(ids)
            for batch in batches:
                source=current.get(batch['item_id'])
                if source is None:continue
                tags=[dict(p) for p in db.execute("SELECT id,tag,version FROM tag_proposals WHERE batch_id=? AND state='pending' ORDER BY id",(batch['id'],))]
                if not tags:continue
                value={'item_id':batch['item_id'],'batch_id':batch['id'],'source_revision':batch['source_revision'],
                    'tags':[p['tag'] for p in tags], 'producer':json.loads(batch['producer_json']),
                    'evidence':json.loads(batch['evidence_json'])}
                value['signature']=hashlib.sha256(json.dumps([CONTRACT,batch['id'],batch['source_revision'],batch['producer_key'],tags, [source[k] for k in ('root_id','relative_path','size_bytes','mtime_ns')]],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
                result[batch['item_id']]=value
        return result

    def vectors(self,snapshots):
        if not snapshots:return {}
        if len(snapshots)>256:raise ValueError('Candidate vector batch exceeds limit')
        with self.ai.store.connect() as db:
            db.row_factory=sqlite3.Row
            rows=db.execute('SELECT * FROM ai_proposal_vectors WHERE item_id IN ('+','.join('?' for _ in snapshots)+')',list(snapshots)).fetchall()
        result={}
        for row in rows:
            snapshot=snapshots[row['item_id']]
            if (row['signature']!=snapshot['signature'] or row['batch_id']!=snapshot['batch_id'] or row['source_revision']!=snapshot['source_revision']):continue
            try:
                from array import array
                vector=array('f');vector.frombytes(row['vector'])
                result[row['item_id']]=normalized(vector,self.ai.profile.dimension)
            except (ValueError,TypeError,OverflowError):continue
        return result

    def ready_ids(self,snapshots):return set(self.vectors(snapshots))

    def build(self,row,snapshot,scope,cancelled):
        """Caller owns the shared inference lock. Atomic per pending batch."""
        if snapshot is None:return True,False
        item=row['id']
        if item in self.ready_ids({item:snapshot}):return True,False
        try:
            if self.ai.previews.tag_source(item)['revision']!=snapshot['source_revision']:return False,False
        except (PreviewUnavailable,PreviewBusyError,ReaderChanged,OSError):return False,False
        if cancelled():return False,False
        name=row['title']+'\n'+row['relative_path']+'\n'+'、'.join(snapshot['tags'])
        vector=normalized(self.ai.encoder.encode('document',name[:4096]),self.ai.profile.dimension)
        if cancelled():return False,True
        from array import array
        packed=array('f',vector).tobytes()
        with self.ai.catalog._guard:
            current=self.ai._current_rows([item],scope).get(item)
            latest=self.snapshots([item]).get(item)
            if cancelled() or current is None or latest is None or latest['signature']!=snapshot['signature']:return False,True
            try:
                if self.ai.previews.tag_source(item)['revision']!=snapshot['source_revision']:return False,True
            except (PreviewUnavailable,PreviewBusyError,ReaderChanged,OSError):return False,True
            with self.ai.store.connect() as db:
                db.execute('INSERT INTO ai_proposal_vectors VALUES(?,?,?,?,?) ON CONFLICT(item_id) DO UPDATE SET '
                    'batch_id=excluded.batch_id,source_revision=excluded.source_revision,signature=excluded.signature,vector=excluded.vector',
                    (item,snapshot['batch_id'],snapshot['source_revision'],snapshot['signature'],packed))
        return True,True


def semantic_candidates(service,ai,query='',kind='',view='all',page=0,root_ids=None,shelf=None,model=None):
    from ai_search import AIBusy,MAX_ITEMS
    from tag_candidate_search import validate_candidate_search
    from tag_suggestions import SuggestionConflict
    validate_candidate_search(query,kind,view,page,root_ids,shelf,model)
    if not query.strip():raise ValueError('Enter a semantic tag query')
    if not hasattr(ai,'pending_tags') or not ai.encoder.available:raise AIUnavailable('タグ候補の意味検索にはAIモデルと索引が必要です。')
    scope=ai._scope({'root_ids':root_ids,'kind':kind,'shelf':shelf})
    if not ai.inference.acquire(blocking=False):raise AIBusy('AI処理中です。完了後に検索してください。')
    try:
        if ai._closed:raise AIUnavailable('AI is closing')
        def eligible():
            rows=list(ai._iter_rows(kind,view,MAX_ITEMS,scope))
            snapshots={};vectors={}
            for offset in range(0,len(rows),256):
                found=ai.pending_tags.snapshots([r['id'] for r in rows[offset:offset+256]])
                if model is not None:found={key:value for key,value in found.items() if value['producer']['model']==model}
                snapshots.update(found);vectors.update(ai.pending_tags.vectors(found))
            return {r['id']:r for r in rows},snapshots,vectors
        with service.catalog._guard:rows,snapshots,vectors=eligible()
        # A missing index must not load a GPU model or embed proposals at query time.
        query_vector=normalized(ai.encoder.encode('query',query),ai.profile.dimension) if vectors else None
        with service.catalog._guard:
            ai._scope(scope)  # A removed explicit root must fail, never widen.
            rows,snapshots,current=eligible()
            # Newly indexed entries cannot be used if no query vector was made.
            ranked=sorted(((item,sum(a*b for a,b in zip(query_vector,vec))) for item,vec in current.items()),key=lambda r:(-r[1],r[0])) if query_vector is not None else []
            items=[]
            for item,score in ranked[page*60:(page+1)*60]:
                snapshot=snapshots[item]
                try:state='current' if service._source(item)['revision']==snapshot['source_revision'] else 'stale'
                except SuggestionConflict:state='stale'
                except AIBusy:state='unverified'
                except (KeyError,OSError):state='unavailable'
                value={**rows[item],'semantic_score':round(max(-1,min(1,score)),6)}
                value['proposal_match']={key:snapshot[key] for key in ('batch_id','source_revision','tags','producer','evidence')}
                value['proposal_match'].update(state='pending',source_state=state,embedding_model=ai.profile.model_id)
                items.append(value)
            return {'total':len(ranked),'page':page,'limit':60,'search_mode':'pending-proposals-semantic','items':items,
                    'score_kind':'cosine','pending_total':len(snapshots),'indexed_total':len(current),
                    'index_remaining':len(snapshots)-len(current),'coverage_limit':MAX_ITEMS}
    finally:
        ai._last_activity=time.monotonic();ai.inference.release()
