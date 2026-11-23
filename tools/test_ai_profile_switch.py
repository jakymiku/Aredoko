"""Actual local weights, two profiles, no extra model or private sources."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from ai_profiles import DEFAULT_PROFILE
from ai_process import EncoderProcess
from ai_search import AISearch
from production import ProductionCatalog

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    target=args.output.resolve();target.mkdir(parents=True,exist_ok=False)
    media=target/'media';media.mkdir()
    for name in ('雨の夜の街並み.wav','晴れた昼の海辺.wav'):
        (media/name).write_bytes(b'generated filename-only placeholder')
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in media.iterdir()}
    cat=ProductionCatalog(target/'catalog.sqlite')
    root=cat.add_root(str(media));cat.start_scan(root);cat._worker.join(10)
    alternative=replace(DEFAULT_PROFILE,modalities=('text',),precision='float32',label='EmbeddingGemma 2 text-only test')
    repo=Path(__file__).resolve().parents[1]
    report=[]
    try:
        original_path=None
        for profile,build in ((DEFAULT_PROFILE,True),(alternative,True),(DEFAULT_PROFILE,False)):
            encoder=EncoderProcess(repo/'.venv-ai/Scripts/python.exe',profile.model_path(repo),profile)
            ai=AISearch(cat,encoder)
            try:
                if build:
                    ai.start();ai.worker.join(180)
                    if ai.worker.is_alive() or ai.status()['state']!='complete':
                        raise RuntimeError('Actual profile index failed')
                result=ai.search('傘が必要な暗い都会の景色',source='text')
                if result['items'][0]['title']!='雨の夜の街並み.wav':
                    raise RuntimeError('Actual profile query top hit failed')
                if encoder.device!='cuda': raise RuntimeError('CUDA required for this local smoke')
                if profile is DEFAULT_PROFILE:
                    if original_path is None: original_path=ai.store.path
                    elif original_path!=ai.store.path: raise RuntimeError('Original index was not reused')
                elif ai.store.path==original_path: raise RuntimeError('Profile indexes mixed')
                report.append({'profile':profile.key,'state':ai.status(),'built':build,'top':result['items'][0]['title']})
            finally: ai.close()
        if before!={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in media.iterdir()}:
            raise RuntimeError('Source changed')
        (target/'profile-switch-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('PASS actual CUDA default/text-only/default switch, separate indexes, reuse without rebuild, sources unchanged')
    finally: cat.close()

if __name__=='__main__': main()
