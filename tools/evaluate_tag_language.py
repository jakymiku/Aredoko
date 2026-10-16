"""One frozen Japanese-query/English-tag run; existing offline EG2 only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from ai_process import EncoderProcess
from ai_profiles import DEFAULT_PROFILE
from search_quality import metrics

SHA256='dc3d32e09b86c6b291807ae350c9bc8b7fade1e7dfcccf9562e29fda6a89ff17'


def load_fixture():
    raw=(REPO/'tests/fixtures/tag-language-v1.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SHA256:raise ValueError('Frozen input changed')
    fixture=json.loads(raw)
    if fixture['conditions']!=['raw-tags','readable-tags'] or len(fixture['items'])!=16 or len(fixture['queries'])!=18:raise ValueError('Invalid fixture')
    ids={i['id'] for i in fixture['items']}
    if len(ids)!=16 or any(set(q['expected'])-ids for q in fixture['queries']):raise ValueError('Invalid qrels')
    return raw,fixture


def evaluate(output,encoder=None):
    raw,fixture=load_fixture()
    output.mkdir(parents=True,exist_ok=False);(output/'fixture.json').write_bytes(raw)
    actual=encoder is None
    encoder=encoder or EncoderProcess(REPO/'.venv-ai/Scripts/python.exe',DEFAULT_PROFILE.model_path(REPO))
    report={'passed':False,'fixture_sha256':SHA256,'generated_metadata_only':True,'actual_model':actual,
            'scope':'Synthetic English WD-style tags; not WD image accuracy or representative private-library quality',
            'profile':DEFAULT_PROFILE.identity(),'input_conditions_frozen_before_inference':True,
            'ranking':'cosine; no threshold/fusion tuning','cases':[],'summaries':[]}
    process=None
    try:
        queries={}
        for q in fixture['queries']:queries[q['id']]=encoder.encode('query',q['text'])
        for condition in fixture['conditions']:
            started=time.perf_counter();vectors={}
            for item in fixture['items']:
                tags=item['tags'] if condition=='raw-tags' else [tag.replace('_',' ') for tag in item['tags']]
                # Same title/relative-path/tag document shape as AISearch._build.
                name=item['id']+'.png'
                vectors[item['id']]=encoder.encode('document',name+'\n'+name+'\n'+'、'.join(tags))
            report.setdefault('index_seconds',{})[condition]=round(time.perf_counter()-started,3)
            scores=[]
            for q in fixture['queries']:
                ranked=sorted(((key,sum(a*b for a,b in zip(queries[q['id']],vec))) for key,vec in vectors.items()),key=lambda row:(-row[1],row[0]))
                scored=metrics([key for key,_ in ranked],{key:1 for key in q['expected']})
                report['cases'].append({'condition':condition,'query_id':q['id'],'query':q['text'],'group':q['group'],
                    'expected':q['expected'],'ranked':[[key,round(score,6)] for key,score in ranked], 'metrics':scored})
                if scored is not None:scores.append(scored)
            report['summaries'].append({'condition':condition,'positive_queries':len(scores),
                'means':{key:statistics.mean(row[key] for row in scores) for key in scores[0]},
                'no_answer_note':'Always returns a ranked corpus; no rejection threshold was introduced or tuned. Negative-query top scores are diagnostic only.'})
        report['device']=getattr(encoder,'device','test-double')
        if actual and encoder.device!='cuda':raise RuntimeError('Expected existing CUDA runtime; CPU results must be separately labelled')
        process=getattr(encoder,'process',None)
        report['passed']=True
    finally:
        if process is None:process=getattr(encoder,'process',None)
        encoder.close()
        report['worker_stopped']=process is None or process.poll() is not None
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();target=args.output.resolve();allowed=(REPO/'data/tag-language').resolve()
    if os.name!='nt' or target==allowed or not target.is_relative_to(allowed):parser.error('Fresh output under data/tag-language on this approved Windows runtime required')
    report=evaluate(target)
    print(json.dumps({key:report[key] for key in ('passed','fixture_sha256','device','summaries','worker_stopped')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
