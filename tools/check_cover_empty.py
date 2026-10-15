"""P0 trial1 confirmation, separate frozen synthetic queries, no downloads."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from production import ProductionCatalog
from ai_search import AISearch
from create_holdout_fixture import create
from test_index_gpu_scaling import MeasuredEncoder,source_digest
from test_index_gpu_api import vector_digest

SHA='f7a734f3a720732dfa93e491c358d95f6157222395ce2780e728e6ab1b4aa78a'

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();target=args.output.resolve()
    if os.name!='nt' or not target.is_relative_to((REPO/'data/ai-ui').resolve()):parser.error('Fresh generated output under data/ai-ui required')
    raw=(REPO/'tests/fixtures/cover-empty-v1.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SHA:parser.error('Frozen confirmation input changed')
    data=json.loads(raw);target.mkdir(parents=True,exist_ok=False);(target/'manifest.json').write_bytes(raw)
    report={'runtime_pass':False,'manifest_sha256':SHA,'actual_cuda':True,'generated_only':True,'cases':[]}
    catalog=ai=encoder=None;media=None;before=None
    try:
        media=create(target/'media',data['items']);before=source_digest(media)
        catalog=ProductionCatalog(target/'catalog.sqlite');root=catalog.add_root(str(media));catalog.start_scan(root);catalog._worker.join(20)
        if catalog.scan_state()['state']!='complete':raise RuntimeError('Generated scan failed')
        rows={r['title']:r for r in catalog.search()['items']};keys={rows[i['file']]['id']:i['key'] for i in data['items']}
        for i in data['items']:
            if i['tags']:catalog.update([rows[i['file']]['id']],{'tags':i['tags']})
        encoder=MeasuredEncoder();ai=AISearch(catalog,encoder);scope={'root_ids':[root],'kind':'','shelf':None}
        ai.start(scope=scope);ai.worker.join(240)
        if ai.status()['state']!='complete' or ai.status()['indexed']!=5 or encoder.device!='cuda':raise RuntimeError('Actual CUDA index required')
        vectors=vector_digest(ai)
        for case in data['cases']:
            previous=encoder.calls['query'];started=time.perf_counter()
            result=ai.search(case['query'],kind=case['kind'],source=case['source'],scope=scope)
            report['cases'].append({'id':case['id'],'ranked':[keys[r['id']] for r in result['items']],
                'query_calls':encoder.calls['query']-previous,'elapsed_ms':round((time.perf_counter()-started)*1000,3)})
        report['query_calls']=encoder.calls['query'];report['vectors_unchanged']=vector_digest(ai)==vectors
        report['runtime_pass']=report['vectors_unchanged']
    except Exception as error:report['error']=type(error).__name__+': '+str(error)
    finally:
        if ai:ai.close()
        elif encoder:encoder.close()
        if encoder:
            report['owned_exits']=encoder.observed_exits
            if not encoder.observed_exits or not all(r['stopped'] for r in encoder.observed_exits):report['runtime_pass']=False
        if catalog:catalog.close()
        if media and before:
            report['source_unchanged']=source_digest(media)==before
            if not report['source_unchanged']:report['runtime_pass']=False
        (target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'runtime_pass':report['runtime_pass'],'query_calls':report.get('query_calls'),'error':report.get('error')}))
    return 0 if report['runtime_pass'] else 1

if __name__=='__main__':raise SystemExit(main())
