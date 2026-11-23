"""Compare registered questions on development data before fresh held-out validation."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from laya_config import IDENTITY,model_path
from laya_process import LayaProcess
from search_intent import SearchIntent
from intent_questions import QUESTION_SETS,question_key
from evaluate_laya import process_memory

def summarize(rows):
    result={'count':len(rows),'runtime_unavailable':sum(r['state']!='suggested' for r in rows)}
    for key in ('intent','kind'):
        offered=[r for r in rows if r['suggestion'] and key not in r['suggestion']['abstained']]
        result[key]={'raw_correct':sum(bool(r['suggestion']) and r['suggestion']['scores'][key]['choice']==r[key] for r in rows),
            'effective_correct':sum(bool(r['suggestion']) and r['suggestion'][key]==r[key] for r in rows),
            'offered':len(offered),'offered_correct':sum(r['suggestion'][key]==r[key] for r in offered),
            'abstained':sum(bool(r['suggestion']) and key in r['suggestion']['abstained'] for r in rows)}
    return result

def evaluate(name,examples):
    provider=LayaProcess(REPO/'.venv-ai/Scripts/python.exe',model_path(REPO),question_set=name,check_order=True)
    service=SearchIntent(provider)
    rows=[];durations=[]
    try:
        for i,example in enumerate(examples):
            start=time.perf_counter();response=service.suggest(example['query'])
            elapsed=round((time.perf_counter()-start)*1000,2)
            if i:durations.append(elapsed)
            rows.append({**example,**response,'elapsed_ms':elapsed})
        return {'question_key':question_key(name),'check_order':True,'summary':summarize(rows),
                'warm_median_ms':statistics.median(durations),'cold_ms':rows[0]['elapsed_ms'],
                'telemetry':dict(provider.telemetry),'memory':process_memory(provider.worker_pid) if provider.worker_pid else {},
                'rows':rows}
    finally:service.close()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--phase',choices=('development','held-out'),required=True)
    parser.add_argument('--selected',choices=tuple(QUESTION_SETS))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.phase=='held-out' and not args.selected:parser.error('Freeze selected question set before held-out evaluation')
    fixture=REPO/'tests/fixtures/laya-ja-v2.json'
    examples=json.loads(fixture.read_text(encoding='utf-8'))
    expected='development' if args.phase=='development' else 'held-out-v2'
    examples=[r for r in examples if r['split']==expected]
    target=args.output.resolve();target.mkdir(parents=True,exist_ok=False)
    names=((args.selected,) if args.selected else tuple(QUESTION_SETS)) if args.phase=='development' else tuple(dict.fromkeys(('v1',args.selected)))
    report={'phase':args.phase,'selected_before_holdout':args.selected,'identity':IDENTITY,
        'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),'evaluations':{}}
    try:
        for name in names:
            data=evaluate(name,examples);report['evaluations'][name]=data
            print(json.dumps({'question_set':name,**{k:data[k] for k in ('summary','warm_median_ms','cold_ms','telemetry')}},ensure_ascii=True),flush=True)
    finally:(target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if any(d['summary']['runtime_unavailable'] for d in report['evaluations'].values()):raise SystemExit('Runtime failure')

if __name__=='__main__':main()
