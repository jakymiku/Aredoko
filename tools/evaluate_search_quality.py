"""Diagnostic Japanese retrieval baseline; fixed qrels, generated media, existing offline CUDA.

No tuning, downloads, private folders, GUI, Laya routing or production changes.
Runtime success and quality measurements are separate; no quality gate claimed.
"""
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
from ai_profiles import DEFAULT_PROFILE
from create_search_quality_fixture import create
from create_holdout_fixture import create as create_holdout
from holdout_manifest import SUITES,load_suite
from search_quality import metrics,summary
from test_index_gpu_scaling import MeasuredEncoder,source_digest
from test_index_gpu_api import vector_digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--suite',choices=tuple(SUITES),default='baseline-v1')
    args=parser.parse_args();target=args.output.resolve()
    if os.name!='nt' or not target.is_relative_to((REPO/'data/ai-ui').resolve()):
        parser.error('New generated output inside data/ai-ui on Windows required')
    if not DEFAULT_PROFILE.model_path(REPO).is_dir() or not (REPO/'.venv-ai/Scripts/python.exe').is_file():
        parser.error('Existing project AI environment and weights required; no download attempted')
    raw,manifest=load_suite(args.suite)
    manifest_path=REPO/'tests/fixtures'/SUITES[args.suite][0]
    target.mkdir(parents=True,exist_ok=False)
    report={'runtime_pass':False,'quality_gate':'not_defined_diagnostic_baseline',
        'suite':args.suite,'fixture_version':manifest['version'],'manifest_sha256':hashlib.sha256(raw).hexdigest(),
        'profile':DEFAULT_PROFILE.identity(),'ranking':'mean-rrf','generated_only':True,
        'native_gui_run':False,'cases':[],'checks':[]}
    catalog=None;ai=None;encoder=None;media=None;before=None
    def check(name,value):
        report['checks'].append({'name':name,'pass':bool(value)})
        if not value:raise RuntimeError(name)
    try:
        # Capture the exact immutable inputs before indexing or observing rankings.
        (target/'manifest.json').write_bytes(raw)
        creator=create_holdout if args.suite=='holdout-v2' else create
        media=creator(target/'generated',manifest['items']);before=source_digest(media)
        catalog=ProductionCatalog(target/'catalog.sqlite');encoder=MeasuredEncoder();ai=AISearch(catalog,encoder)
        root=catalog.add_root(str(media));catalog.start_scan(root);catalog._worker.join(20)
        check('generated scan complete',not catalog._worker.is_alive() and catalog.scan_state()['state']=='complete')
        rows=catalog.search(limit=60)['items'];by_file={row['title']:row for row in rows}
        check('all fixture sources registered',set(by_file)=={item['file'] for item in manifest['items']})
        by_id={};items={item['key']:item for item in manifest['items']}
        for item in manifest['items']:
            row=by_file[item['file']];check('kind '+item['key'],row['kind']==item['kind'])
            by_id[row['id']]=item['key']
            if item['tags']:catalog.update([row['id']],{'tags':item['tags']})
        scope={'root_ids':[root],'kind':'','shelf':None}
        check('counts without GPU',ai.coverage(scope)['target_total']==len(items) and not encoder.resident)
        started=time.perf_counter();ai.start(scope=scope);ai.worker.join(240)
        report['index_elapsed_seconds']=round(time.perf_counter()-started,3)
        check('real CUDA fixture index complete',not ai.worker.is_alive() and ai.status()['state']=='complete'
              and ai.status()['indexed']==len(items) and encoder.device=='cuda')
        check('expected text and cover inference',encoder.calls['document']==len(items) and encoder.calls['image']==sum(item['kind'] in ('image','book') for item in items.values()))
        vectors=vector_digest(ai)
        def record(case,source,kind,ranked,elapsed,result):
            eligible={key for key,item in items.items() if (not kind or item['kind']==kind)
                      and (source!='cover' or item['kind'] in ('image','book'))}
            check('results stay in eligible pool',set(ranked)<=eligible)
            relevant={key:grade for key,grade in case['relevance'].items() if key in eligible}
            report['cases'].append({'id':case['id'],'group':case['group'],'query':case['query'],
                'source':source,'filter':'kind' if kind else 'all-kinds','kind':kind,
                'query_evidence':case.get('evidence',case['group']),'qrel_evidence':{key:items[key].get('evidence') for key in relevant},
                'eligible_count':len(eligible),'relevance':relevant,'metrics':metrics(ranked,relevant),
                'no_answer_probe':case['group']=='no-answer','returned_count':len(ranked),
                'elapsed_ms':round(elapsed*1000,3),'ranking':result.get('ranking','literal-substring'),
                'score_kind':result.get('score_kind'),'top_5':ranked[:5],
                'top_score':result['items'][0].get('semantic_score') if result['items'] else None,
                'ranks':{key:ranked.index(key)+1 if key in ranked else None for key in relevant}})
        for case in manifest['cases']:
            for kind in (case['kind'],''):
                started=time.perf_counter();result=catalog.search(case['query'],kind=kind,limit=60)
                record(case,'literal',kind,[by_id[row['id']] for row in result['items']],time.perf_counter()-started,result)
                for source in case['sources']:
                    started=time.perf_counter();result=ai.search(case['query'],kind=kind,source=source,scope=scope)
                    record(case,source,kind,[by_id[row['id']] for row in result['items']],time.perf_counter()-started,result)
            print(json.dumps({'case':case['id'],'completed':True}),flush=True)
        check('searches retain indexed vector bytes',vector_digest(ai)==vectors)
        check('manifest unchanged after observations',manifest_path.read_bytes()==raw)
        report['summary']=summary(report['cases']);report['calls']=dict(encoder.calls)
        report['telemetry']=dict(encoder.telemetry);report['index_status']=ai.status()
        report['runtime_pass']=True
    except Exception as error:report['error']=str(error)
    finally:
        try:
            if ai:ai.close()
            if encoder:
                report['owned_exits']=encoder.observed_exits
                check('all observed owned handles stopped',bool(encoder.observed_exits) and all(row['stopped'] for row in encoder.observed_exits))
        except Exception as error:report['runtime_pass']=False;report['cleanup_error']=str(error)
        if catalog:catalog.close()
        if media and before:
            report['source_bytes_mtime_hash_unchanged']=source_digest(media)==before
            if not report['source_bytes_mtime_hash_unchanged']:report['runtime_pass']=False
        (target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'runtime_pass':report['runtime_pass'],'rows':len(report['cases']),'error':report.get('error')}),flush=True)
    return 0 if report['runtime_pass'] else 1

if __name__=='__main__':raise SystemExit(main())
