"""Scoped direct-video text retrieval; no invented description or UI dependency.

Uses the common catalog filters and bounded score spool. A single request owns
ranking once, and can serve range pages through the existing result sink shape.
The encoder belongs to the explicit video namespace, never the image worker.
"""
from array import array
import math
import sys

from ai_score_spool import ScoreSpool,SearchCancelled
from ai_vectors import normalized
from video_direct_index import CONTRACT,MAX_WINDOWS
from video_input import MAX_START_MS
from previews import PreviewUnavailable

# Each covered second yields one frame, plus at most one partial-second
# frame per window; anything beyond that cannot come from the index.
MAX_FRAMES_TOTAL=MAX_START_MS//1000+MAX_WINDOWS


class VideoSearchChanged(ValueError):pass


def _score(data,query):
    if type(data) is not bytes or len(data)!=len(query)*4:return None
    vector=array('f');vector.frombytes(data)
    if sys.byteorder!='little':vector.byteswap()
    norm=sum(value*value for value in vector)
    if not math.isfinite(norm) or abs(norm-1)>1e-4:return None
    divisor=math.sqrt(norm)
    return sum(a*b/divisor for a,b in zip(query,vector))


class VideoDirectSearch:
    def __init__(self,index):self.index=index

    def search(self,query,*,page=0,limit=60,result_sink=None,cancelled=None,**conditions):
        if not isinstance(query,str) or not 1<=len(query.strip())<=4096:raise ValueError('Invalid video query')
        if type(page) is not int or page<0 or type(limit) is not int or not 1<=limit<=120:raise ValueError('Invalid video paging')
        if set(conditions)-{'view','root_id','root_ids','shelf','shelf_ids'}:raise ValueError('Unsupported video search conditions')
        if result_sink is not None and (not callable(result_sink) or page!=0):raise ValueError('Result sink requires page zero')
        if cancelled is not None and not callable(cancelled):raise ValueError('Invalid cancellation callback')
        index=self.index;catalog=index.catalog;generation=catalog.result_generation()
        with index.store.connect() as monitor,ScoreSpool(cancelled=cancelled,parent=index.stage_parent) as spool:
            version=monitor.execute('PRAGMA data_version').fetchone()[0]
            def check():
                if cancelled is not None and cancelled():raise SearchCancelled('Video search cancelled')
                if (catalog.result_generation()!=generation or index.encoder.profile.key!=index.profile.key
                        or monitor.execute('PRAGMA data_version').fetchone()[0]!=version):
                    raise VideoSearchChanged('Video search changed; refresh results')
            check()
            candidate_total=indexed_total=scored_total=0
            def consume(fetch):
                nonlocal candidate_total,indexed_total,scored_total
                number=0;vector=None
                while True:
                    check();batch=fetch(number);rows=batch['items'];candidate_total=batch['total']
                    # Filter validation/selection precedes inference, including
                    # an empty root/shelf/favorite scope.
                    if rows and vector is None:
                        vector=normalized(index.encoder.encode('query',query),index.profile.dimension);check()
                    hits,fresh=self._rank(rows,vector,check) if rows else ({},0)
                    indexed_total+=fresh
                    for row in rows:
                        if row['id'] not in hits:continue
                        score,start,end,revision=hits[row['id']]
                        spool.add(row['id'],{'video':score},payload={'item':row,'revision':revision,
                            'video_match_ms':start,'video_match_end_ms':end})
                        scored_total+=1
                    if (number+1)*batch['limit']>=batch['total']:break
                    number+=1
                check();spool.finalize('max')
                def render(number):
                    check();selected=spool.page(number,limit)
                    payloads=spool.evidence([item for item,_ in selected['ranked']]);items=[]
                    for item,score in selected['ranked']:
                        payload=payloads[item]
                        if index.reader.video_manifest(item)['revision']!=payload['revision']:
                            raise VideoSearchChanged('Matched video changed; refresh results')
                        items.append({**payload['item'],'semantic_score':round(score,6),
                            'video_match_ms':payload['video_match_ms'],'video_match_end_ms':payload['video_match_end_ms'],
                            'video_match_source':'direct-video','video_match_contract':CONTRACT})
                    check()
                    return {'items':items,'total':selected['total'],'page':number,'limit':limit,
                            'source':'video-direct','profile':index.profile.key,'score_kind':'cosine',
                            'candidate_total':candidate_total,'search_candidate_total':candidate_total,
                            'indexed_total':indexed_total,'scored_total':scored_total,'search_complete':True,
                            'search_status':('out_of_scope' if not candidate_total else 'unindexed' if not indexed_total else
                                             'partially_indexed' if indexed_total<candidate_total else 'ready')}
                return render(page) if result_sink is None else result_sink(render)
            return catalog.search(query='',kind='video',limit=120,result_sink=consume,cancelled=cancelled,**conditions)

    def _rank(self,rows,query,check):
        if not rows:return {},0
        if len(rows)>120:raise ValueError('Video ranking batch exceeds limit')
        index=self.index;ids=[row['id'] for row in rows];best={};fresh={}
        with index.store.connect() as db:
            markers=db.execute('SELECT item_id,source_revision,contract,decoded_windows,indexed_windows,total_frames '
                              'FROM ai_video_direct_sources WHERE item_id IN ('+','.join('?' for _ in ids)+')',ids)
            for item,revision,contract,decoded,indexed,frames in markers:
                check()
                if not (contract==CONTRACT and 0<=indexed<=decoded<=MAX_WINDOWS
                        and 1<=frames<=MAX_FRAMES_TOTAL):continue
                try:
                    if index.reader.video_manifest(item)['revision']==revision:fresh[item]=(revision,decoded,indexed)
                except PreviewUnavailable:continue
            markers.close()
            cursor=db.execute('SELECT item_id,ordinal,start_ms,end_ms,vector FROM ai_video_direct_windows '
                              'WHERE item_id IN ('+','.join('?' for _ in ids)+') ORDER BY item_id,ordinal',ids)
            for item,ordinal,start,end,data in cursor:
                check()
                if item not in fresh:continue
                revision,decoded,indexed=fresh[item]
                if not indexed or not (0<=ordinal<decoded and 0<=start<end<=MAX_START_MS):continue
                value=_score(data,query)
                if value is not None and (item not in best or value>best[item][0]):
                    best[item]=(value,start,end,revision)
            cursor.close()
        check();return best,len(fresh)
