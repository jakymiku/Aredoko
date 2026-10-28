"""Explicitly authorized generated-only GPU decode/index/search integration.

One audio-only adapter, two existing synthetic clips, two Japanese queries.
--owned-worker uses the production owner and actual private subprocess instead.
Neither route tests normal UI or general audio quality.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import traceback

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))


def copy_sources(sources,media,*,video_audio=False):
    """Mux the same generated PCM into small silent-image videos on the CPU."""
    if video_audio:
        from video_previews import _executable
        for name,(source,_,__) in sources.items():
            target=media/(Path(name).stem+'.mkv')
            subprocess.run([_executable('ffmpeg'),'-nostdin','-v','error','-f','lavfi','-i','color=c=blue:s=160x90:r=4',
                '-i',str(source),'-map','0:v:0','-map','1:a:0','-c:v','mpeg4','-threads','1','-c:a','pcm_s16le',
                '-shortest',str(target)],check=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    else:
        for name,(source,_,__) in sources.items():shutil.copyfile(source,media/name)


def verify_before_gpu(python,target):
    """Keep filesystem validation outside the model's 180-second job budget.

    The production verifier's normal same-process cache is then reused at spawn.
    Nothing disables verification or imports torch while this stage is running.
    """
    from runtime_paths import verify_runtime_pack,runtime_verification_status
    started=time.monotonic();stop=threading.Event()
    with (target/'runtime-verification.log').open('x',encoding='utf-8') as output:
        def sample():
            value=runtime_verification_status(python)
            output.write(json.dumps(value,ensure_ascii=False)+'\n');output.flush()
        def observe():
            while not stop.wait(2):sample()
        thread=threading.Thread(target=observe,name='generated-runtime-progress',daemon=True);thread.start()
        print('Checking selected runtime on CPU before GPU/model startup',flush=True)
        try:info=verify_runtime_pack(python,cancelled=lambda:time.monotonic()-started>=600)
        finally:stop.set();thread.join();sample()
    status=runtime_verification_status(python)
    if info is not None and status['state']!='verified':raise RuntimeError('Selected runtime integrity verification must not be skipped')
    return {'seconds':round(time.monotonic()-started,3),'state':status['state'],
        'manifest_sha256':info.get('manifest_sha256') if info else None,'files':info.get('files') if info else None,
        'bytes':info.get('bytes') if info else None,'verification_disabled':False}


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr,'reconfigure'):sys.stderr.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--gpu',action='store_true',required=True)
    parser.add_argument('--owned-worker',action='store_true',help='Actual production owner/private worker, explicit 3 GiB CUDA allocator limit')
    parser.add_argument('--video-audio',action='store_true',help='Requires separate human GPU approval: mux generated clips into videos and use the production video-audio owner')
    args=parser.parse_args();fixture=args.fixture.resolve();target=args.output.resolve()
    if args.video_audio and not args.owned_worker:parser.error('Video audio requires the actual owned worker route')
    if not fixture.is_relative_to(REPO/'data/ai-ui') or not target.is_relative_to(REPO/'data/ai-ui') or target.exists():
        parser.error('Existing generated fixture and new dedicated output required')
    from storage_lease import plain_path
    manifest=json.loads(plain_path(fixture/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format')!='aredoko-generated-audio-eval-v1':parser.error('Generated evaluation manifest required')
    selected=[item for item in manifest['items'] if item['id'] in ('001','002')]
    if len(selected)!=2 or {item['file'] for item in selected}!={'001.wav','002.wav'}:parser.error('Two fixed generated clips required')
    sources={}
    for item in selected:
        source=plain_path(fixture/'media'/item['file'])
        if not 1<=source.stat().st_size<=2*1024*1024:parser.error('Small generated WAVs required')
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        if digest!=item['sha256']:parser.error('Generated source changed')
        sources[item['file']]=(source,digest,source.stat().st_mtime_ns)
    target.mkdir(parents=True);media=target/'media';media.mkdir()
    copy_sources(sources,media,video_audio=args.video_audio)
    suffix='.mkv' if args.video_audio else '.wav'
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    report={'pass':False,'gpu_inference':False,'external_download':False,'normal_profiles_changed':False,
            'scope':'two generated video audio clips' if args.video_audio else 'two generated audio clips',
            'broad_quality_acceptance':False,'playback':False,
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'items':[],'queries':[]}
    catalog=image_owner=audio_owner=None;owned_process=None
    report['execution_route']='owned-private-worker' if args.owned_worker else 'direct-adapter'
    try:
        if args.owned_worker:report['runtime_preflight']=verify_before_gpu(sys.executable,target)
        import torch
        from ai_profiles import audio_profile_for
        from audio_direct_index import AudioDirectIndex
        from audio_direct_search import AudioDirectSearch
        from production import ProductionCatalog
        from previews import PreviewReader
        from runtime_paths import model_directory
        if not torch.cuda.is_available():raise RuntimeError('Authorized GPU unavailable; no fallback')
        free,total=torch.cuda.mem_get_info()
        if free<3*1024**3:raise RuntimeError('Less than 3 GiB free; defer before loading')
        torch.cuda.set_per_process_memory_fraction(min(.9,3*1024**3/total))
        torch.set_num_threads(2);torch.cuda.reset_peak_memory_stats()
        profile=audio_profile_for();dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        model_path=model_directory(REPO,profile.directory)
        if (model_path/'aredoko-revision.txt').read_text(encoding='utf-8').strip()!=profile.revision:
            raise RuntimeError('Existing model revision marker mismatch')
        report['model']={'id':profile.model_id,'revision':profile.revision,'profile':profile.key}
        catalog=ProductionCatalog(target/'catalog.sqlite');root=catalog.add_root(str(media))
        catalog.index.scan(root);catalog.sync_index();reader=PreviewReader(catalog)
        items={row['title']:row['id'] for row in catalog.search()['items']}
        if args.owned_worker:
            from ai_process import EncoderProcess
            from ai_profiles import DEFAULT_PROFILE
            from ai_search import AISearch
            from audio_direct_feature import AudioDirectFeature
            image_owner=AISearch(catalog,EncoderProcess(sys.executable,model_path,DEFAULT_PROFILE,gpu_budget_mib=3072))
            audio_owner=AudioDirectFeature(catalog,image_owner)
            report['status_before']=audio_owner.status()
            begin=audio_owner.start_video_audio if args.video_audio else audio_owner.start
            began=time.monotonic();begin({'consent':True,'conditions':{'root_ids':[root]}})
            audio_owner.owner.thread.join(180)
            owned_process=audio_owner.encoder.process
            report['index_seconds']=round(time.monotonic()-began,3)
            report['status_after']=audio_owner.status()
            if report['status_after']['state']!='completed' or report['status_after']['indexed']!=2:
                raise RuntimeError('Owned audio indexing did not complete')
            if audio_owner.encoder.device!='cuda' or image_owner.encoder.resident:
                raise RuntimeError('Owned CUDA routing or residency mismatch')
            report['gpu_inference']=True;report['worker_pid']=owned_process.pid
            report['worker_profile']=audio_owner.encoder.profile.key
            report['worker_allocator_budget_mib']=audio_owner.encoder.gpu_budget_mib
            index=audio_owner.owner.index.for_source_kind('video' if args.video_audio else 'audio')
            search=audio_owner.search_video_audio if args.video_audio else audio_owner.search
            for name,item in items.items():
                revision=index.manifest(item)['revision']
                report['items'].append({'item_id':item,'fresh':index.fresh(item,revision)})
        else:
            from ai_adapters import load_adapter
            started=time.monotonic();adapter=load_adapter(profile,model_path,'cuda',dtype)
            report['load_seconds']=round(time.monotonic()-started,3)
            class Encoder:
                def __init__(self):self.profile=profile
                def encode(self,operation,value):
                    report['gpu_inference']=True
                    with torch.inference_mode():
                        result=adapter.encode_audio(value) if operation=='audio' else adapter.encode_text(operation,value)
                    torch.cuda.synchronize()
                    return result.tolist()
            index=AudioDirectIndex(catalog,Encoder(),reader=reader)
            for name,item in items.items():
                revision=reader.audio_manifest(item)['revision'];began=time.monotonic()
                report['items'].append({**index.index_item(item,revision),'seconds':round(time.monotonic()-began,3)})
            search=AudioDirectSearch(index).search
        for query in manifest['queries']:
            if query['axis']!='speech_ja' or query['expected'] not in (['001'],['002']):continue
            result=search(query['text']);top=result['items'][0]
            expected=items[query['expected'][0]+suffix]
            report['queries'].append({'query':query['text'],'top1_id':top['id'],'expected_id':expected,
                'top1':top['id']==expected,'audio_match_ms':top['audio_match_ms'],
                'audio_match_source':top.get('audio_match_source'),
                'no_fabricated_snippet':'audio_match_snippet' not in top})
        report['sources_unchanged']=all(hashlib.sha256(path.read_bytes()).hexdigest()==digest and path.stat().st_mtime_ns==mtime
                                             for path,digest,mtime in sources.values())
        report['memory']=({'worker_peak_allocated_mib':audio_owner.encoder.telemetry.get('peak_memory_mib'),
                           'note':'Child allocator telemetry only; not total native/driver VRAM'} if args.owned_worker else
                          {'torch_peak_allocated':torch.cuda.max_memory_allocated(),'torch_peak_reserved':torch.cuda.max_memory_reserved(),
                           'note':'Allocator only; not total native/driver VRAM'})
        report['pass']=(len(report['items'])==2 and len(report['queries'])==2 and report['sources_unchanged']
                        and all(q['top1'] and q['no_fabricated_snippet'] for q in report['queries']))
        if args.video_audio:
            from unittest.mock import patch
            released=audio_owner.release()
            with patch.object(audio_owner.encoder,'encode',side_effect=AssertionError('Cached video audio must not infer')):
                origin=items['001.mkv'];similar=audio_owner.similar_video_audio(origin)
            report['cached_similarity']={'origin':origin,'ids':[row['id'] for row in similar['items']],
                'model_released':released['released'] and not audio_owner.encoder.resident,
                'both_intervals':all(type(row.get(key)) is int for row in similar['items'] for key in
                    ('audio_match_ms','audio_match_end_ms','origin_match_ms','origin_match_end_ms'))}
            report['pass']=report['pass'] and report['cached_similarity']['ids']==[items['002.mkv']] and report['cached_similarity']['both_intervals'] and report['cached_similarity']['model_released']
    except Exception:report['error']=traceback.format_exc()
    finally:
        if audio_owner:
            if owned_process is None:owned_process=audio_owner.encoder.process
            audio_owner.close()
        if image_owner:image_owner.close()
        if args.owned_worker:
            report['owned_worker_started']=owned_process is not None
            report['owned_worker_stopped']=owned_process is None or owned_process.poll() is not None
            report['owned_worker_exit']=owned_process.poll() if owned_process is not None else None
            report['pass']=report['pass'] and report['owned_worker_stopped']
        if catalog:catalog.close()
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));return 0 if report['pass'] else 1


if __name__=='__main__':raise SystemExit(main())
