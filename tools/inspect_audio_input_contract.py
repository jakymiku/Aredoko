"""Offline CPU-only audio preprocessing contract; no model load or inference.

Run with the existing AI Python. Generates one WAV, uses the validated PCM
boundary, reads bounded safetensors metadata and invokes the local processor.
This does not evaluate recognition, retrieval quality, embeddings or VRAM.
"""
import argparse,hashlib,json,math,os,struct,sys,time,traceback,wave
from importlib.metadata import version
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from ai_profiles import DEFAULT_PROFILE
from runtime_paths import model_directory
from production import ProductionCatalog
from previews import PreviewReader


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();target=args.output.resolve()
    if target.exists() or not target.is_relative_to(REPO/'data/ai-ui'):parser.error('New dedicated data/ai-ui directory required')
    target.mkdir(parents=True);report={'pass':False,'stage':'preprocessing-contract','model_loaded':False,'gpu_inference':False,'external_download':False}
    catalog=None
    # Applied before optional ML imports, inside this process only.
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',CUDA_VISIBLE_DEVICES='')
    try:
        model=model_directory(REPO,DEFAULT_PROFILE.directory)
        config=json.loads((model/'config.json').read_text());preprocessor=json.loads((model/'preprocessor_config.json').read_text())
        report['profile']={'model_id':DEFAULT_PROFILE.model_id,'revision':DEFAULT_PROFILE.revision,
                           'production_modalities':list(DEFAULT_PROFILE.modalities)}
        report['config']={'model_type':config.get('model_type'),'audio_model_type':(config.get('audio_config') or {}).get('model_type'),
                          'audio_feature_extractor':preprocessor.get('feature_extractor_type'),'sampling_rate':preprocessor.get('sampling_rate')}
        weights=model/'model.safetensors';before=(weights.stat().st_size,weights.stat().st_mtime_ns)
        with weights.open('rb') as source:
            size=struct.unpack('<Q',source.read(8))[0]
            if not 1<=size<=16*1024*1024:raise ValueError('Bounded safetensors header required')
            header=json.loads(source.read(size))
        audio=[value for key,value in header.items() if key!='__metadata__' and 'audio' in key]
        report['audio_weight_header']={'tensors':len(audio),'payload_bytes':sum(v['data_offsets'][1]-v['data_offsets'][0] for v in audio),
                                       'note':'Structural presence, not loaded memory or quality evidence'}
        media=target/'media';media.mkdir();path=media/'generated-001.wav'
        with wave.open(str(path),'wb') as output:
            output.setnchannels(1);output.setsampwidth(2);output.setframerate(16000)
            output.writeframes(b''.join(struct.pack('<h',int(6000*math.sin(2*math.pi*440*i/16000))) for i in range(32000)))
        original=(hashlib.sha256(path.read_bytes()).hexdigest(),path.stat().st_mtime_ns)
        catalog=ProductionCatalog(target/'catalog.sqlite');root=catalog.add_root(str(media));catalog.index.scan(root);catalog.sync_index()
        item=catalog.search()['items'][0]['id'];reader=PreviewReader(catalog);revision=reader.audio_manifest(item)['revision']
        pcm=reader.audio_pcm_window(item,250,1000,revision)['window']
        import numpy as np
        from transformers import AutoProcessor
        report['versions']={name:version(name) for name in ('sentence-transformers','transformers','numpy')}
        processor=AutoProcessor.from_pretrained(str(model),local_files_only=True,trust_remote_code=False)
        samples=np.frombuffer(pcm.data,dtype='<f4')
        started=time.monotonic();features=processor(audio=samples,sampling_rate=pcm.sample_rate,return_tensors='np')
        report['processor_seconds']=time.monotonic()-started
        report['input']={'frames':pcm.frame_count,'sample_rate':pcm.sample_rate,'channels':pcm.channels,'sample_format':pcm.sample_format}
        report['output']={key:{'shape':list(value.shape),'dtype':str(value.dtype)} for key,value in features.items() if hasattr(value,'shape')}
        if 'input_features' not in features or 'input_features_mask' not in features or not np.isfinite(features['input_features']).all():
            raise ValueError('Finite audio features and mask required')
        report['sources_unchanged']=original==(hashlib.sha256(path.read_bytes()).hexdigest(),path.stat().st_mtime_ns) and before==(weights.stat().st_size,weights.stat().st_mtime_ns)
        report['pass']=report['sources_unchanged']
    except Exception:report['error']=traceback.format_exc()
    finally:
        if catalog:catalog.close()
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));return 0 if report['pass'] else 1


if __name__=='__main__':raise SystemExit(main())
