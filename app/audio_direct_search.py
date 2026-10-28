"""Scoped direct-audio text retrieval; no invented transcript or UI dependency.

Uses the common catalog filters and bounded score spool. A single request owns
ranking once, and can serve range pages through the existing result sink shape.
The encoder belongs to the explicit audio namespace, never the image worker.
"""
from array import array
import math
import sys

from ai_score_spool import ScoreSpool,SearchCancelled
from ai_vectors import normalized
from audio_direct_index import CONTRACT,valid_marker,valid_interval
from previews import PreviewUnavailable


class AudioSearchChanged(ValueError):pass


def _score(data,query):
    if type(data) is not bytes or len(data)!=len(query)*4:return None
    vector=array('f');vector.frombytes(data)
    if sys.byteorder!='little':vector.byteswap()
    norm=sum(value*value for value in vector)
    if not math.isfinite(norm) or abs(norm-1)>1e-4:return None
    divisor=math.sqrt(norm)
    return sum(a*b/divisor for a,b in zip(query,vector))


class AudioDirectSearch:
    def __init__(self,index):self.index=index

    def search(self,query,*,page=0,limit=60,result_sink=None,cancelled=None,**conditions):
        if not isinstance(query,str) or not 1<=len(query.strip())<=4096:raise ValueError('Invalid audio query')
        if type(page) is not int or page<0 or type(limit) is not int or not 1<=limit<=120:raise ValueError('Invalid audio paging')
        if set(conditions)-{'view','root_id','root_ids','shelf','shelf_ids'}:raise ValueError('Unsupported audio search conditions')
        if result_sink is not None and (not callable(result_sink) or page!=0):raise ValueError('Result sink requires page zero')
        if cancelled is not None and not callable(cancelled):raise ValueError('Invalid cancellation callback')
        index=self.index;catalog=index.catalog;generation=catalog.result_generation()
        with index.store.connect() as monitor,ScoreSpool(cancelled=cancelled,parent=index.stage_parent) as spool:
            version=monitor.execute('PRAGMA data_version').fetchone()[0]
            def check():
                if cancelled is not None and cancelled():raise SearchCancelled('Audio search cancelled')
                if (catalog.result_generation()!=generation or index.encoder.profile.key!=index.profile.key
                        or monitor.execute('PRAGMA data_version').fetchone()[0]!=version):
                    raise AudioSearchChanged('Audio search changed; refresh results')
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
                        spool.add(row['id'],{'audio':score},payload={'item':row,'revision':revision,
                            'audio_match_ms':start,'audio_match_end_ms':end})
                        scored_total+=1
                    if (number+1)*batch['limit']>=batch['total']:break
                    number+=1
                check();spool.finalize('max')
                def render(number):
                    check();selected=spool.page(number,limit)
                    payloads=spool.evidence([item for item,_ in selected['ranked']]);items=[]
                    for item,score in selected['ranked']:
                        payload=payloads[item]
                        try:revision=index.manifest(item)['revision']
                        except PreviewUnavailable:
                            raise AudioSearchChanged('Matched audio unavailable; refresh results') from None
                        if revision!=payload['revision']:
                            raise AudioSearchChanged('Matched audio changed; refresh results')
                        items.append({**payload['item'],'semantic_score':round(score,6),
                            'audio_match_ms':payload['audio_match_ms'],'audio_match_end_ms':payload['audio_match_end_ms'],
                            'audio_match_source':'video-audio' if index.source_kind=='video' else 'direct-audio','audio_match_contract':CONTRACT})
                    check()
                    return {'items':items,'total':selected['total'],'page':number,'limit':limit,
                            'source':'video-audio-direct' if index.source_kind=='video' else 'audio-direct','profile':index.profile.key,'score_kind':'cosine',
                            'candidate_total':candidate_total,'search_candidate_total':candidate_total,
                            'indexed_total':indexed_total,'scored_total':scored_total,'search_complete':True,
                            'search_status':('out_of_scope' if not candidate_total else 'unindexed' if not indexed_total else
                                             'partially_indexed' if indexed_total<candidate_total else 'ready')}
                return render(page) if result_sink is None else result_sink(render)
            return catalog.search(query='',kind=index.source_kind,limit=120,result_sink=consume,cancelled=cancelled,**conditions)

    def _rank(self,rows,query,check):
        if not rows:return {},0
        if len(rows)>120:raise ValueError('Audio ranking batch exceeds limit')
        index=self.index;ids=[row['id'] for row in rows];best={};fresh={};counts={}
        with index.store.connect() as db:
            markers=db.execute('SELECT item_id,source_revision,contract,decoded_windows,indexed_windows,total_frames '
                              'FROM ai_audio_direct_sources WHERE item_id IN ('+','.join('?' for _ in ids)+')',ids)
            for item,revision,contract,decoded,indexed,frames in markers:
                check()
                if contract!=CONTRACT or not valid_marker(decoded,indexed,frames):continue
                try:
                    if index.manifest(item)['revision']==revision:
                        fresh[item]=(revision,decoded,indexed,frames);counts[item]=0
                except PreviewUnavailable:continue
            markers.close()
            cursor=db.execute('SELECT item_id,ordinal,start_ms,end_ms,vector FROM ai_audio_direct_windows '
                              'WHERE item_id IN ('+','.join('?' for _ in ids)+') ORDER BY item_id,ordinal',ids)
            for item,ordinal,start,end,data in cursor:
                check()
                if item not in fresh:continue
                revision,decoded,indexed,frames=fresh[item]
                if counts[item]>=indexed or not valid_interval(ordinal,start,end,decoded,frames):
                    fresh.pop(item);best.pop(item,None);continue
                value=_score(data,query)
                if value is None:
                    fresh.pop(item);best.pop(item,None);continue
                counts[item]+=1
                if item not in best or value>best[item][0]:
                    best[item]=(value,start,end,revision)
            cursor.close()
        for item,(_,_,indexed,_) in tuple(fresh.items()):
            if counts[item]!=indexed:
                fresh.pop(item);best.pop(item,None)
        check();return best,len(fresh)
