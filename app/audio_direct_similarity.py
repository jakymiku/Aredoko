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
from audio_direct_index import CONTRACT,MAX_WINDOWS
from audio_direct_search import AudioSearchChanged
from audio_input import MAX_START_MS,SAMPLE_RATE,MAX_WINDOW_MS
from previews import PreviewUnavailable

MAX_FRAME_BYTES=32*1024*1024
# Bound total exact pair comparisons across all candidates in one request.
MAX_PAIRS=100_000
WINDOW_FRAMES=SAMPLE_RATE*MAX_WINDOW_MS//1000


class AudioDirectSimilarity:
    def __init__(self,index):self.index=index

    def _frames(self,row,db,check):
        check();index=self.index
        try:revision=index.reader.audio_manifest(row['id'])['revision']
        except PreviewUnavailable:return None,[]
        marker=db.execute('SELECT source_revision,contract,decoded_windows,indexed_windows,total_frames '
                          'FROM ai_audio_direct_sources WHERE item_id=?',(row['id'],)).fetchone()
        if marker is None:return revision,[]
        saved,contract,decoded,indexed,frames=marker
        if (saved!=revision or contract!=CONTRACT
                or any(type(value) is not int for value in (decoded,indexed,frames))
                or not (0<indexed<=decoded<=MAX_WINDOWS and 1<=frames<=MAX_START_MS*SAMPLE_RATE//1000)
                or decoded!=(frames+WINDOW_FRAMES-1)//WINDOW_FRAMES):
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
                if (any(type(value) is not int for value in (ordinal,start,end))
                        or not (0<=ordinal<decoded and start==ordinal*MAX_WINDOW_MS
                            and start<end==min(start+MAX_WINDOW_MS,(frames*1000+SAMPLE_RATE-1)//SAMPLE_RATE))
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
        if type(item_id) is not int or not 1<=item_id<=9223372036854775807:raise ValueError('Invalid audio origin')
        if type(page) is not int or page<0 or type(limit) is not int or not 1<=limit<=120:raise ValueError('Invalid audio paging')
        if set(conditions)-{'view','root_id','root_ids','shelf','shelf_ids'}:raise ValueError('Invalid audio scope')
        if result_sink is not None and (not callable(result_sink) or page):raise ValueError('Result sink requires page zero')
        if cancelled is not None and not callable(cancelled):raise ValueError('Invalid cancellation')
        index=self.index;catalog=index.catalog;generation=catalog.result_generation()
        with index.store.connect() as monitor,ScoreSpool(cancelled=cancelled,parent=index.stage_parent) as spool:
            version=monitor.execute('PRAGMA data_version').fetchone()[0]
            def check():
                if cancelled is not None and cancelled():raise SearchCancelled('Audio similarity cancelled')
                if (catalog.result_generation()!=generation or index.encoder.profile.key!=index.profile.key
                        or monitor.execute('PRAGMA data_version').fetchone()[0]!=version):
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
            origin=catalog.search(kind='audio',limit=120,result_sink=find_origin,cancelled=cancelled,
                                  **{k:v for k,v in conditions.items() if k!='view'})
            origin_revision,origin_frames=self._frames(origin,monitor,check)
            if origin_revision is None:raise AudioSearchChanged('Audio origin unavailable')
            base={'mode':'audio-similar','origin_id':item_id,'origin_kind':'audio','origin_revision':origin_revision,
                  'source':'audio-direct','profile':index.profile.key,'score_kind':'cosine',
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
                                check();score=sum(a*b for a,b in zip(query,vector))
                                if best is None or score>best[0]:best=(score,at,end,origin_at,origin_end)
                        score,at,end,origin_at,origin_end=best
                        spool.add(row['id'],{'audio':score},payload={'item':row,'revision':revision,
                            'audio_match_ms':at,'audio_match_end_ms':end,
                            'origin_match_ms':origin_at,'origin_match_end_ms':origin_end})
                    if (number+1)*batch['limit']>=batch['total']:break
                    number+=1
                check();spool.finalize('max')
                def check_revision(item,expected):
                    try:current=index.reader.audio_manifest(item)['revision']
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
                            'audio_match_source':'direct-audio','audio_match_contract':CONTRACT,
                            **{name:payload[name] for name in ('audio_match_ms','audio_match_end_ms','origin_match_ms','origin_match_end_ms')}})
                    check()
                    return {**base,'items':items,'total':selected['total'],'page':number,'limit':limit,
                            'candidate_total':candidate_total,'search_candidate_total':candidate_total,
                            'indexed_total':indexed_total,'search_complete':True}
                return render(page) if result_sink is None else result_sink(render)
            return catalog.search(kind='audio',limit=120,result_sink=consume,cancelled=cancelled,**conditions)
