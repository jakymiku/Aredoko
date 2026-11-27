"""Separate pending-tag embeddings; never promote proposals to confirmed tags."""
from array import array
import hashlib
import json
import sqlite3
import time

from ai_process import AIUnavailable
from ai_vectors import normalized
import native_accel
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
            if not batches:return {}
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


def semantic_candidates(service,ai,query='',kind='',view='all',page=0,root_ids=None,shelf=None,model=None,*,shelf_ids=None,tag=None,cancelled=None,result_sink=None):
    from ai_search import AIBusy,MAX_ITEMS,revision
    from tag_candidate_search import validate_candidate_search
    from tag_suggestions import SuggestionConflict
    validate_candidate_search(query,kind,view,page,root_ids,shelf,model,shelf_ids,tag)
    if not query.strip():raise ValueError('Enter a semantic tag query')
    if not hasattr(ai,'pending_tags') or not ai.encoder.available:raise AIUnavailable('タグ候補の意味検索にはAIモデルと索引が必要です。')
    scope=ai._scope({'root_ids':root_ids,'kind':kind,'shelf':shelf,**({'shelf_ids':shelf_ids} if shelf_ids is not None else {}),**({'tag':tag} if tag is not None else {})})
    if not ai.inference.acquire(blocking=False):raise AIBusy('AI処理中です。完了後に検索してください。')
    try:
        with ai._search_workspace(scope,cancelled) as (spool,check):
            query_vector=None;pending_total=indexed_total=candidate_total=0
            for rows in ai._search_batches(kind,view,scope,check):
                candidate_total+=len(rows)
                snapshots=ai.pending_tags.snapshots([row['id'] for row in rows])
                if model is not None:snapshots={key:value for key,value in snapshots.items() if value['producer']['model']==model}
                vectors=ai.pending_tags.vectors(snapshots)
                pending_total+=len(snapshots);indexed_total+=len(vectors)
                if vectors and query_vector is None:
                    query_vector=normalized(ai.encoder.encode('query',query),ai.profile.dimension)
                check()
                matched_rows=[row for row in rows if row['id'] in vectors]
                if matched_rows and native_accel.available():
                    blobs=b''.join(array('f',vectors[row['id']]).tobytes() for row in matched_rows)
                    scores_arr,_,valid_arr=native_accel.score_f32_batch([query_vector],blobs,len(matched_rows),ai.profile.dimension,normalize_vec=False)
                    for idx,row in enumerate(matched_rows):
                        if valid_arr[idx]:
                            spool.add(row['id'],{'text':scores_arr[idx]},payload={'revision':revision(row),'proposal':snapshots[row['id']]})
                else:
                    for row in matched_rows:
                        item=row['id']
                        score=sum(a*b for a,b in zip(query_vector,vectors[item]))
                        spool.add(item,{'text':score},payload={'revision':revision(row),'proposal':snapshots[item]})
                check()
            spool.finalize('max')
            def render_page(number):
                selected=spool.page(number,60)
                with service.catalog._guard:
                    check()
                    rows,evidence=ai._search_page_rows(spool,selected,scope,check)
                    latest=ai.pending_tags.snapshots([item for item,_ in selected['ranked']])
                    items=[]
                    for item,score in selected['ranked']:
                        snapshot=evidence[item]['proposal']
                        if item not in latest or latest[item]['signature']!=snapshot['signature']:
                            raise AIBusy('タグ候補が更新されました。もう一度検索してください。')
                        try:state='current' if service._source(item)['revision']==snapshot['source_revision'] else 'stale'
                        except SuggestionConflict:state='stale'
                        except AIBusy:state='unverified'
                        except (KeyError,OSError):state='unavailable'
                        value={**rows[item],'semantic_score':round(max(-1,min(1,score)),6)}
                        value['proposal_match']={key:snapshot[key] for key in ('batch_id','source_revision','tags','producer','evidence')}
                        value['proposal_match'].update(state='pending',source_state=state,embedding_model=ai.profile.model_id)
                        items.append(value)
                    check()
                return {'total':selected['total'],'page':number,'limit':60,'search_mode':'pending-proposals-semantic','items':items,
                        'score_kind':'cosine','pending_total':pending_total,'indexed_total':indexed_total,
                        'index_remaining':pending_total-indexed_total,'coverage_limit':MAX_ITEMS,'index_limit':MAX_ITEMS,
                        'search_complete':True,'search_candidate_total':candidate_total}
            return render_page(page) if result_sink is None else result_sink(render_page)
    finally:
        ai._last_activity=time.monotonic();ai.inference.release()
