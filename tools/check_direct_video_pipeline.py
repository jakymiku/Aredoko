"""Explicit GPU acceptance: generated silent clips through the owned pipeline.

Real guarded duration/decode, private video worker, atomic index, two Japanese
queries and cached similarity. No ordinary DB/UI, downloads or audio playback.
This is a limited synthetic wiring check, not real-video quality acceptance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'app'),str(REPO/'tools')]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--gpu',action='store_true',required=True)
    args=parser.parse_args();target=args.output.resolve()
    if not target.is_relative_to(REPO/'data/ai-ui') or target.exists():parser.error('New dedicated output required')
    target.mkdir(parents=True);media=target/'media';media.mkdir()
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    report={'pass':False,'gpu_inference':False,'gui':False,'download':False,'normal_db_changed':False,
            'scope':'generated red/blue silent clips only; no broad video quality acceptance',
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    catalog=image_owner=feature=process=None
    try:
        import torch
        from ai_process import EncoderProcess
        from ai_profiles import DEFAULT_PROFILE
        from ai_search import AISearch
        from production import ProductionCatalog
        from runtime_paths import model_directory
        from ui_video_content_audit import create_media
        from video_direct_feature import VideoDirectFeature
        if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable; defer')
        free,_=torch.cuda.mem_get_info()
        if free<3*1024**3:raise RuntimeError('Less than 3 GiB free; defer before model loading')
        model=model_directory(REPO,DEFAULT_PROFILE.directory)
        if (model/'aredoko-revision.txt').read_text(encoding='utf-8').strip()!=DEFAULT_PROFILE.revision:
            raise RuntimeError('Existing model revision mismatch')
        create_media(media)
        def sources():return {p.name:(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in media.iterdir()}
        before=sources()
        report['source_before']=before
        catalog=ProductionCatalog(target/'catalog.sqlite');root=catalog.add_root(str(media))
        catalog.index.scan(root);catalog.sync_index()
        items={row['title']:row['id'] for row in catalog.search()['items']}
        image_owner=AISearch(catalog,EncoderProcess(sys.executable,model,DEFAULT_PROFILE,gpu_budget_mib=3072))
        feature=VideoDirectFeature(catalog,image_owner,stage_parent=target)
        report['status_before']=feature.status()
        assert feature.owner is None and not image_owner.encoder.resident
        start=time.monotonic();feature.start({'consent':True,'conditions':{'root_ids':[root]}})
        feature.owner.thread.join(180)
        if feature.owner.thread.is_alive():feature.cancel();raise TimeoutError('Generated video batch exceeded deadline')
        report['index_seconds']=round(time.monotonic()-start,3);report['status_after']=feature.status()
        if feature.status()['state']!='completed':raise RuntimeError('Video index failed: '+str(feature.status()))
        process=feature.encoder.process
        report['gpu_inference']=feature.encoder.device=='cuda'
        with feature.owner.index.store.connect() as db:
            report['markers']=db.execute('SELECT item_id,decoded_windows,indexed_windows,total_frames FROM ai_video_direct_sources ORDER BY item_id').fetchall()
            report['intervals']=db.execute('SELECT item_id,start_ms,end_ms FROM ai_video_direct_windows ORDER BY item_id,ordinal').fetchall()
        assert report['intervals']==[(1,0,3300),(2,0,16000),(2,16000,17500)]
        report['queries']=[]
        for query,name in (('赤い画面の動画','generated-001.mp4'),('青い画面の動画','generated-002.mp4')):
            result=feature.search(query,root_ids=[root]);top=result['items'][0]
            report['queries'].append({'query':query,'expected':items[name],'top':top['id'],'top1':top['id']==items[name],
                                      'interval':[top['video_match_ms'],top['video_match_end_ms']]})
        report['telemetry']=feature.encoder.telemetry
        feature.release();report['worker_released']=not feature.encoder.resident
        with patch.object(feature.encoder,'encode',side_effect=AssertionError('Cached similarity must not infer')):
            similar=feature.similar(items['generated-001.mp4'],root_ids=[root])
        report['cached_similarity']={'total':similar['total'],'candidate':similar['items'][0]['id'],
            'origin_interval':[similar['items'][0]['origin_match_ms'],similar['items'][0]['origin_match_end_ms']],
            'candidate_interval':[similar['items'][0]['video_match_ms'],similar['items'][0]['video_match_end_ms']]}
        report['no_model_for_cached_similarity']=not feature.encoder.resident
        report['image_worker_not_started']=not image_owner.encoder.resident
        report['sources_unchanged']=sources()==before
        report['pass']=(report['gpu_inference'] and report['worker_released'] and report['no_model_for_cached_similarity']
                        and report['image_worker_not_started'] and report['sources_unchanged']
                        and similar['total']==1 and similar['items'][0]['id']==items['generated-002.mp4']
                        and all(row['top1'] for row in report['queries']))
    except Exception:report['error']=traceback.format_exc()
    finally:
        if feature:
            if process is None:process=feature.encoder.process
            feature.close()
        if image_owner:image_owner.close()
        if catalog:catalog.close()
        report['owned_worker_stopped']=process is not None and process.poll() is not None
        report['owned_worker_exit']=process.poll() if process is not None else None
        report['pass']=report['pass'] and report['owned_worker_stopped']
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));return 0 if report['pass'] else 1


if __name__=='__main__':raise SystemExit(main())
