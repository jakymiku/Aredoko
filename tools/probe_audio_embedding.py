"""Explicit generated-only GPU audio API smoke; never writes an AI index.

Requires a passing inspect_audio_input_contract fixture and separate user
permission. This is experimental: production profiles/adapters are unchanged.
"""
import argparse,hashlib,json,os,sys,time,traceback
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from ai_profiles import DEFAULT_PROFILE
from runtime_paths import model_directory
from audio_input import read_window
from storage_lease import plain_path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--gpu',action='store_true',required=True,help='Explicit authorized GPU smoke; no CPU fallback')
    args=parser.parse_args();fixture=args.fixture.resolve();target=args.output.resolve()
    if target.exists() or not target.is_relative_to(REPO/'data/ai-ui') or not fixture.is_relative_to(REPO/'data/ai-ui'):
        parser.error('Dedicated generated fixture and new evidence directory required')
    evidence=json.loads((fixture/'report.json').read_text(encoding='utf-8'))
    if evidence.get('stage')!='preprocessing-contract' or evidence.get('pass') is not True:parser.error('Passing generated contract fixture required')
    target.mkdir(parents=True);report={'pass':False,'stage':'experimental-audio-api-smoke','model_loaded':False,'quality_evaluated':False,
        'normal_profiles_changed':False,'index_written':False,'gpu_inference':False,'external_download':False,
        'test_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    try:
        import numpy as np
        import torch
        from sentence_transformers import SentenceTransformer
        if not torch.cuda.is_available():raise RuntimeError('Authorized GPU unavailable; no CPU fallback')
        free,total=torch.cuda.mem_get_info()
        if free<3*1024**3:raise RuntimeError('Less than 3 GiB free; defer without loading the model')
        # Allocator cap for this process; driver/context allocations are separate.
        torch.cuda.set_per_process_memory_fraction(min(.9,3*1024**3/total));torch.set_num_threads(2)
        torch.cuda.reset_peak_memory_stats()
        source=plain_path(fixture/'media/generated-001.wav')
        if not 1<=source.stat().st_size<=2*1024*1024:raise ValueError('Small generated WAV required')
        original=(hashlib.sha256(source.read_bytes()).hexdigest(),source.stat().st_mtime_ns)
        with source.open('rb') as handle:pcm=read_window(handle,250,1000)
        samples=np.frombuffer(pcm.data,dtype='<f4')
        dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        started=time.monotonic()
        model=SentenceTransformer(str(model_directory(REPO,DEFAULT_PROFILE.directory)),local_files_only=True,device='cuda',
            config_kwargs={'vision_config':None},model_kwargs={'torch_dtype':dtype},trust_remote_code=False)
        report['model_loaded']=True;report['load_seconds']=time.monotonic()-started
        report['model']={'id':DEFAULT_PROFILE.model_id,'revision':DEFAULT_PROFILE.revision,
                         'experimental_audio_enabled':True,'experimental_vision_disabled':True,'dtype':str(dtype)}
        started=time.monotonic()
        report['gpu_inference']=True
        with torch.inference_mode():
            vector=model.encode({'audio':{'array':samples,'sampling_rate':pcm.sample_rate}},normalize_embeddings=True,show_progress_bar=False)
        torch.cuda.synchronize()
        report['encode_seconds']=time.monotonic()-started
        vector=np.asarray(vector);report['vector']={'shape':list(vector.shape),'finite':bool(np.isfinite(vector).all()),'norm':float(np.linalg.norm(vector))}
        report['memory']={'torch_peak_allocated':torch.cuda.max_memory_allocated(),'torch_peak_reserved':torch.cuda.max_memory_reserved(),
                          'note':'PyTorch allocator values; not total driver/native VRAM'}
        report['sources_unchanged']=original==(hashlib.sha256(source.read_bytes()).hexdigest(),source.stat().st_mtime_ns)
        report['pass']=vector.shape==(DEFAULT_PROFILE.dimension,) and report['vector']['finite'] and abs(report['vector']['norm']-1)<.002 and report['sources_unchanged']
    except Exception:report['error']=traceback.format_exc()
    finally:
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));return 0 if report['pass'] else 1


if __name__=='__main__':raise SystemExit(main())
