"""Offline startup verification + Japanese CUDA queries on two generated PNGs.

Uses an existing sealed runtime and existing weights; never downloads, reads a
user catalog, or scans any folder other than the new dedicated output/media.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'app'),str(REPO/'tools')]
from ai_process import EncoderProcess
from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch
from ai_runtime import inspect_runtime
from create_preview_fixture import png
from production import ProductionCatalog
from runtime_paths import bind_runtime,start_runtime_verification,runtime_verification_status


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--models',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();target=args.output.resolve()
    if not target.is_relative_to(REPO/'data/ai-ui') or target.exists():parser.error('New dedicated output inside data/ai-ui required')
    runtime=inspect_runtime(args.runtime)
    target.mkdir(parents=True);media=target/'media';media.mkdir()
    for name,color in [('雨の日の青い画像.png',(40,80,180)),('晴れた日の赤い画像.png',(180,70,40))]:
        (media/name).write_bytes(png(width=128,height=128,color=color))
    sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in media.iterdir()}
    report={'pass':False,'generated_only':True,'downloads':False,'checks':[],'queries':[],'runtime_hash_passes':0}
    catalog=ai=job=None
    def check(name,value):
        report['checks'].append({'name':name,'pass':bool(value)})
        print(name,bool(value),flush=True)
        if not value:raise AssertionError(name)
    def inspected(*a,**kw):
        if kw.get('verify'):report['runtime_hash_passes']+=1
        return inspect_runtime(*a,**kw)
    try:
        bind_runtime(args.runtime,runtime['manifest_sha256'])
        with patch('ai_runtime.inspect_runtime',side_effect=inspected):
            before=time.monotonic();job=start_runtime_verification(Path(runtime['python']))
            check('background verification has an owner',job is not None)
            while job.thread.is_alive() and time.monotonic()-before<180:
                state=runtime_verification_status(Path(runtime['python']))
                report['verification_last']=state
                time.sleep(.1)
            check('full verification finished',not job.thread.is_alive() and runtime_verification_status(Path(runtime['python']))['state']=='verified')
            report['verification_seconds']=time.monotonic()-before
            catalog=ProductionCatalog(target/'catalog.sqlite')
            root=catalog.add_root(str(media));catalog.start_scan(root);catalog._worker.join(10)
            check('only the generated pair is catalogued',catalog.search()['total']==2)
            encoder=EncoderProcess(runtime['python'],DEFAULT_PROFILE.model_path(REPO,models_root=args.models))
            ai=AISearch(catalog,encoder);check('existing model available',encoder.available)
            ai.start(limit=2);ai.worker.join(180)
            state=ai.status();report['index']={k:state.get(k) for k in ('state','indexed','device','error')}
            check('generated pair indexed on CUDA',state['state']=='complete' and state['indexed']==2 and state['device']=='cuda')
            encoder.release()
            for label,query in [('cold','雨の日の青い画像'),('warm','晴れた日の赤い画像')]:
                before=time.monotonic();result=ai.search(query,source='cover')
                report['queries'].append({'label':label,'query':query,'seconds':time.monotonic()-before,'total':result['total']})
                check(label+' Japanese visual query returns the indexed pair',result['total']==2 and encoder.device=='cuda')
            check('worker relaunch and warm search reuse one full verification',report['runtime_hash_passes']==1)
        check('generated originals unchanged',sources=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in media.iterdir()})
        report['pass']=True
    except Exception:
        report['error']=traceback.format_exc();print(report['error'],flush=True)
    finally:
        try:
            if ai:ai.close()
            if job:check('verification owner closed',job.close())
            if catalog:catalog.close()
        except Exception:
            report['cleanup_error']=traceback.format_exc();report['pass']=False
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['pass'] else 1


if __name__=='__main__':raise SystemExit(main())
