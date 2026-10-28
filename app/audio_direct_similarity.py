"""Exact max-window similarity inside the direct-audio namespace only.

No encoder or PCM input is needed. At most two bounded item frame sets and
one 120-item metadata page are retained; ranked results use the shared spool.
Exact max-pair scoring costs O(origin windows × candidate windows × dimension).
A request exceeding 100,000 pairs fails without publishing a partial ranking.
"""
from array import array
import math
import sys

from ai_score_spool import ScoreSpool,SearchCancelled
from ai_process import AIUnavailable
from ai_vectors import dot
from audio_direct_index import CONTRACT,valid_marker,valid_interval
from audio_direct_search import AudioSearchChanged
from previews import PreviewUnavailable

MAX_FRAME_BYTES=32*1024*1024
# Bound total exact pair comparisons across all candidates in one request.
MAX_PAIRS=100_000
PAIR_VERSION_INTERVAL=64


def validate_similarity_request(item_id,*,page=0,limit=60,result_sink=None,cancelled=None,**conditions):
    """Validate a cached PCM request without creating an index or workspace."""
    if type(item_id) is not int or not 1<=item_id<=9223372036854775807:raise ValueError('Invalid audio origin')
    if type(page) is not int or page<0 or type(limit) is not int or not 1<=limit<=120:raise ValueError('Invalid audio paging')
    if set(conditions)-{'view','root_id','root_ids','shelf','shelf_ids'}:raise ValueError('Invalid audio scope')
    if result_sink is not None and (not callable(result_sink) or page):raise ValueError('Result sink requires page zero')
    if cancelled is not None and not callable(cancelled):raise ValueError('Invalid cancellation')
    return conditions


class AudioDirectSimilarity:
    SOURCE_KIND='audio'
    RESULT_MODE='audio-similar'
    RESULT_SOURCE='audio-direct'
    EVIDENCE_SOURCE='direct-audio'
    def __init__(self,index):
        if index.source_kind!=self.SOURCE_KIND:raise ValueError('Similarity index source does not match the requested media kind')
        self.index=index

    def _frames(self,row,db,check):
        check();index=self.index
        try:revision=index.manifest(row['id'])['revision']
        except PreviewUnavailable:return None,[]
        marker=db.execute('SELECT source_revision,contract,decoded_windows,indexed_windows,total_frames '
                          'FROM ai_audio_direct_sources WHERE item_id=?',(row['id'],)).fetchone()
        if marker is None:return revision,[]
        saved,contract,decoded,indexed,frames=marker
        if saved!=revision or contract!=CONTRACT or not valid_marker(decoded,indexed,frames) or not indexed:
            return revision,[]
        result=[]
        cursor=db.execute('SELECT ordinal,start_ms,end_ms,vector FROM ai_audio_direct_windows '
                          'WHERE item_id=? ORDER BY ordinal',(row['id'],))
        try:
            for ordinal,start,end,data in cursor:
                check()
                if len(result)>=indexed:return revision,[]
                if (len(result)+1)*index.profile.dimension*8>MAX_FRAME_BYTES:
                    raise AIUnavailable('音声の比較に必要なメモリが上限を超えました。結果は作成していません。')
                if (not valid_interval(ordinal,start,end,decoded,frames)
                        or type(data) is not bytes or len(data)!=index.profile.dimension*4):return revision,[]
                packed=array('f');packed.frombytes(data)
                if sys.byteorder!='little':packed.byteswap()
                norm=sum(value*value for value in packed)
                if not math.isfinite(norm) or abs(norm-1)>1e-4:return revision,[]
                scale=math.sqrt(norm)
                result.append((start,end,array('d',(value/scale for value in packed))))
        finally:cursor.close()
        return revision,result if len(result)==indexed else []

    def similar(self,item_id,*,page=0,limit=60,result_sink=None,cancelled=None,**conditions):
        validate_similarity_request(item_id,page=page,limit=limit,result_sink=result_sink,cancelled=cancelled,**conditions)
        index=self.index;catalog=index.catalog;generation=catalog.result_generation()
        with index.store.connect() as monitor,ScoreSpool(cancelled=cancelled,parent=index.stage_parent) as spool:
            version=monitor.execute('PRAGMA data_version').fetchone()[0]
            private_pairs=0
            def check(*,pair=False):
                nonlocal private_pairs
                if cancelled is not None and cancelled():raise SearchCancelled('Audio similarity cancelled')
                # Cancellation and catalog/profile guards remain per pair.
                # SQLite commits may be polled in bounded private work only:
                # all window/candidate/finalization/render checks stay immediate.
                private_pairs=private_pairs+1 if pair else 0
                if (catalog.result_generation()!=generation or index.encoder.profile.key!=index.profile.key
                        or ((not pair or private_pairs%PAIR_VERSION_INTERVAL==0)
                            and monitor.execute('PRAGMA data_version').fetchone()[0]!=version)):
                    raise AudioSearchChanged('Audio similarity changed; refresh results')
            # The origin obeys roots/shelves/exclusions, but the candidate-only
            # favorites view must not make an otherwise valid origin disappear.
            def find_origin(fetch):
                number=0
                while True:
                    check();batch=fetch(number)
                    for row in batch['items']:
                        if row['id']==item_id:return row
                    if (number+1)*batch['limit']>=batch['total']:raise KeyError(item_id)
                    number+=1
            origin=catalog.search(kind=self.SOURCE_KIND,limit=120,result_sink=find_origin,cancelled=cancelled,
                                  **{k:v for k,v in conditions.items() if k!='view'})
            origin_revision,origin_frames=self._frames(origin,monitor,check)
            if origin_revision is None:raise AudioSearchChanged('Audio origin unavailable')
            base={'mode':self.RESULT_MODE,'origin_id':item_id,'origin_kind':self.SOURCE_KIND,'origin_revision':origin_revision,
                  'source':self.RESULT_SOURCE,'profile':index.profile.key,'score_kind':'cosine',
                  'similarity_status':'ready' if origin_frames else 'unindexed'}
            candidate_total=indexed_total=pair_total=0
            def consume(fetch):
                nonlocal candidate_total,indexed_total,pair_total
                number=0
                while True:
                    check();batch=fetch(number)
                    for row in batch['items']:
                        if row['id']==item_id:continue
                        candidate_total+=1
                        # Release the previous candidate before allocating the next.
                        frames=None;vector=None
                        revision,frames=self._frames(row,monitor,check) if origin_frames else (None,[])
                        if not frames:continue
                        indexed_total+=1;best=None
                        pair_total+=len(frames)*len(origin_frames)
                        if pair_total>MAX_PAIRS:
                            raise AIUnavailable('音声の比較範囲が上限を超えました。対象フォルダーや棚を絞って再実行してください。')
                        for at,end,vector in frames:
                            for origin_at,origin_end,query in origin_frames:
                                check(pair=True);score=dot(query,vector)
                                if best is None or score>best[0]:best=(score,at,end,origin_at,origin_end)
                        score,at,end,origin_at,origin_end=best
                        spool.add(row['id'],{'audio':score},payload={'item':row,'revision':revision,
                            'audio_match_ms':at,'audio_match_end_ms':end,
                            'origin_match_ms':origin_at,'origin_match_end_ms':origin_end})
                    if (number+1)*batch['limit']>=batch['total']:break
                    number+=1
                check();spool.finalize('max')
                def check_revision(item,expected):
                    try:current=index.manifest(item)['revision']
                    except PreviewUnavailable:
                        raise AudioSearchChanged('Audio source unavailable; refresh results') from None
                    if current!=expected:raise AudioSearchChanged('Audio source changed; refresh results')
                def render(number):
                    check()
                    check_revision(item_id,origin_revision)
                    selected=spool.page(number,limit);payloads=spool.evidence([key for key,_ in selected['ranked']]);items=[]
                    for key,score in selected['ranked']:
                        payload=payloads[key]
                        check_revision(key,payload['revision'])
                        items.append({**payload['item'],'semantic_score':round(score,6),'similarity_origin_id':item_id,
                            'audio_match_source':self.EVIDENCE_SOURCE,'audio_match_contract':CONTRACT,
                            **{name:payload[name] for name in ('audio_match_ms','audio_match_end_ms','origin_match_ms','origin_match_end_ms')}})
                    check()
                    return {**base,'items':items,'total':selected['total'],'page':number,'limit':limit,
                            'candidate_total':candidate_total,'search_candidate_total':candidate_total,
                            'indexed_total':indexed_total,'search_complete':True}
                return render(page) if result_sink is None else result_sink(render)
            return catalog.search(kind=self.SOURCE_KIND,limit=120,result_sink=consume,cancelled=cancelled,**conditions)
