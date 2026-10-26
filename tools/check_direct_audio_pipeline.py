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
import sys
import time
import traceback

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--gpu',action='store_true',required=True)
    parser.add_argument('--owned-worker',action='store_true',help='Actual production owner/private worker, explicit 3 GiB CUDA allocator limit')
    args=parser.parse_args();fixture=args.fixture.resolve();target=args.output.resolve()
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
    for name,(source,_,__) in sources.items():shutil.copyfile(source,media/name)
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    report={'pass':False,'gpu_inference':False,'external_download':False,'normal_profiles_changed':False,
            'scope':'two generated clips: real decode/index/text retrieval; not private worker or broad quality acceptance',
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'items':[],'queries':[]}
    catalog=image_owner=audio_owner=None;owned_process=None
    report['execution_route']='owned-private-worker' if args.owned_worker else 'direct-adapter'
    try:
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
            began=time.monotonic();audio_owner.start({'consent':True,'conditions':{'root_ids':[root]}})
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
            index=audio_owner.owner.index;search=audio_owner
            for name,item in items.items():
                revision=reader.audio_manifest(item)['revision']
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
            search=AudioDirectSearch(index)
        for query in manifest['queries']:
            if query['axis']!='speech_ja' or query['expected'] not in (['001'],['002']):continue
            result=search.search(query['text']);top=result['items'][0]
            expected=items[query['expected'][0]+'.wav']
            report['queries'].append({'query':query['text'],'top1_id':top['id'],'expected_id':expected,
                'top1':top['id']==expected,'audio_match_ms':top['audio_match_ms'],
                'no_fabricated_snippet':'audio_match_snippet' not in top})
        report['sources_unchanged']=all(hashlib.sha256(path.read_bytes()).hexdigest()==digest and path.stat().st_mtime_ns==mtime
                                             for path,digest,mtime in sources.values())
        report['memory']=({'worker_peak_allocated_mib':audio_owner.encoder.telemetry.get('peak_memory_mib'),
                           'note':'Child allocator telemetry only; not total native/driver VRAM'} if args.owned_worker else
                          {'torch_peak_allocated':torch.cuda.max_memory_allocated(),'torch_peak_reserved':torch.cuda.max_memory_reserved(),
                           'note':'Allocator only; not total native/driver VRAM'})
        report['pass']=(len(report['items'])==2 and len(report['queries'])==2 and report['sources_unchanged']
                        and all(q['top1'] and q['no_fabricated_snippet'] for q in report['queries']))
    except Exception:report['error']=traceback.format_exc()
    finally:
        if audio_owner:
            if owned_process is None:owned_process=audio_owner.encoder.process
            audio_owner.close()
        if image_owner:image_owner.close()
        if args.owned_worker:
            report['owned_worker_stopped']=owned_process is not None and owned_process.poll() is not None
            report['owned_worker_exit']=owned_process.poll() if owned_process is not None else None
            report['pass']=report['pass'] and report['owned_worker_stopped']
        if catalog:catalog.close()
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));return 0 if report['pass'] else 1


if __name__=='__main__':raise SystemExit(main())
