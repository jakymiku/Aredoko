"""Explicit GPU evaluation of a generated-only, numeric-name R06 fixture.

Audio arrays and query strings are the only model inputs. No normal profiles,
AI indexes, user media, downloads or GUI. Quality metrics describe this small
synthetic set only; execution_pass does not mean product acceptance.
"""
import argparse,hashlib,json,os,sys,time,traceback
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from ai_profiles import DEFAULT_PROFILE
from runtime_paths import model_directory
from production import ProductionCatalog
from previews import PreviewReader
from storage_lease import plain_path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--gpu',action='store_true',required=True)
    args=parser.parse_args();fixture=args.fixture.resolve();target=args.output.resolve()
    if (target.exists() or not target.is_relative_to(REPO/'data/ai-ui') or not fixture.is_relative_to(REPO/'data/ai-ui')):
        parser.error('Generated fixture and new dedicated evidence directory required')
    manifest=json.loads((fixture/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format')!='aredoko-generated-audio-eval-v1' or len(manifest['items'])!=8:parser.error('Eight generated clips required')
    for item in manifest['items']:
        if item['file']!=item['id']+'.wav' or item['id'] not in {f'{n:03}' for n in range(1,9)}:parser.error('Numeric generated WAV only')
    if len({item['id'] for item in manifest['items']})!=8:parser.error('Unique generated clips required')
    target.mkdir(parents=True)
    report={'execution_pass':False,'quality_scope':'limited synthetic speech/signals; no ASR or real-media comparison',
            'gpu_inference':False,'external_download':False,'normal_profiles_changed':False,'ai_index_written':False,
            'test_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'audio':[],'queries':[],'similarity':[]}
    catalog=None
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    try:
        import numpy as np
        import torch
        from sentence_transformers import SentenceTransformer
        if not torch.cuda.is_available():raise RuntimeError('Authorized GPU unavailable; no CPU fallback')
        free,total=torch.cuda.mem_get_info()
        if free<3*1024**3:raise RuntimeError('Less than 3 GiB free; defer without loading')
        torch.cuda.set_per_process_memory_fraction(min(.9,3*1024**3/total));torch.set_num_threads(2);torch.cuda.reset_peak_memory_stats()
        dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        model=SentenceTransformer(str(model_directory(REPO,DEFAULT_PROFILE.directory)),local_files_only=True,device='cuda',
            config_kwargs={'vision_config':None},model_kwargs={'torch_dtype':dtype},trust_remote_code=False)
        report['model']={'id':DEFAULT_PROFILE.model_id,'revision':DEFAULT_PROFILE.revision,'audio_enabled':True,'vision_disabled':True,'dtype':str(dtype)}
        catalog=ProductionCatalog(target/'catalog.sqlite');root=catalog.add_root(str(fixture/'media'));catalog.index.scan(root);catalog.sync_index()
        indexed={row['title']:row['id'] for row in catalog.search()['items']};reader=PreviewReader(catalog);vectors={}
        def normalized(value):
            array=np.asarray(value,dtype=np.float64)
            if array.shape!=(DEFAULT_PROFILE.dimension,) or not np.isfinite(array).all() or not .9<float(np.linalg.norm(array))<1.1:
                raise ValueError('Finite near-normalized 768D output required')
            return array/np.linalg.norm(array)
        for item in manifest['items']:
            source=plain_path(fixture/'media'/item['file'])
            if not 1<=source.stat().st_size<=2*1024*1024:raise ValueError('Small generated WAV required')
            if hashlib.sha256(source.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Generated source changed')
            identity=indexed[item['file']];revision=reader.audio_manifest(identity)['revision']
            pcm=reader.audio_pcm_window(identity,0,30000,revision)['window'];samples=np.frombuffer(pcm.data,dtype='<f4')
            started=time.monotonic();report['gpu_inference']=True
            with torch.inference_mode():
                vector=model.encode({'audio':{'array':samples,'sampling_rate':pcm.sample_rate}},normalize_embeddings=True,show_progress_bar=False)
            torch.cuda.synchronize();vectors[item['id']]=normalized(vector)
            report['audio'].append({'id':item['id'],'frames':pcm.frame_count,'encode_seconds':time.monotonic()-started})
        def ranked(query,exclude=None):
            return [{'id':identity,'score':float(score)} for score,identity in sorted(
                ((float(np.dot(query,vector)),identity) for identity,vector in vectors.items() if identity!=exclude),key=lambda pair:(-pair[0],pair[1]))]
        def outcome(ranks,expected):
            positions=[i+1 for i,row in enumerate(ranks) if row['id'] in expected]
            rank=min(positions) if positions else None
            recall=len({row['id'] for row in ranks[:3]}&set(expected))/len(set(expected))
            return {'rank':rank,'top1':rank==1,'recall_at_3':recall,'reciprocal_rank':0 if rank is None else 1/rank}
        for query in manifest['queries']:
            with torch.inference_mode():
                vector=model.encode(query['text'],prompt_name=DEFAULT_PROFILE.query_prompt_name,normalize_embeddings=True,show_progress_bar=False)
            ranks=ranked(normalized(vector));report['queries'].append({**query,'ranking':ranks,**outcome(ranks,query['expected'])})
        for query in manifest['similarity']:
            ranks=ranked(vectors[query['origin']],exclude=query['origin'])
            report['similarity'].append({**query,'ranking':ranks,**outcome(ranks,query['expected'])})
        report['metrics']={}
        for axis in sorted({q['axis'] for q in report['queries']}):
            rows=[q for q in report['queries'] if q['axis']==axis]
            report['metrics'][axis]={'count':len(rows),**{key:sum(row[key] for row in rows)/len(rows) for key in ('top1','recall_at_3','reciprocal_rank')}}
        rows=report['similarity'];report['metrics']['similarity']={'count':len(rows),**{key:sum(row[key] for row in rows)/len(rows) for key in ('top1','recall_at_3','reciprocal_rank')}}
        report['memory']={'torch_peak_allocated':torch.cuda.max_memory_allocated(),'torch_peak_reserved':torch.cuda.max_memory_reserved(),
                          'note':'Allocator only; not total native/driver VRAM'}
        report['sources_unchanged']=all(hashlib.sha256((fixture/'media'/item['file']).read_bytes()).hexdigest()==item['sha256'] for item in manifest['items'])
        report['execution_pass']=report['sources_unchanged']
    except Exception:report['error']=traceback.format_exc()
    finally:
        if catalog:catalog.close()
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('audio','queries','similarity')},ensure_ascii=False))
    return 0 if report['execution_pass'] else 1


if __name__=='__main__':raise SystemExit(main())
