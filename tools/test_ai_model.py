"""Manual actual-model smoke test using generated fixtures only."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from production import ProductionCatalog
from ai_process import EncoderProcess
from ai_search import AISearch
from create_preview_fixture import create

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    target=args.output.resolve()
    target.mkdir(parents=True,exist_ok=False)
    media=create(target/'media')
    (media/'雨の夜の街並み.wav').write_bytes(b'generated placeholder; filename-only AI input')
    (media/'晴れた昼の海辺.wav').write_bytes(b'generated placeholder; filename-only AI input')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in media.iterdir()}
    catalog=ProductionCatalog(target/'catalog.sqlite')
    encoder=EncoderProcess(Path(__file__).resolve().parents[1]/'.venv-ai/Scripts/python.exe',
                           Path(__file__).resolve().parents[1]/'models/embeddinggemma-2')
    ai=AISearch(catalog,encoder)
    try:
        root=catalog.add_root(str(media))
        catalog.start_scan(root);catalog._worker.join(15)
        started=time.perf_counter()
        ai.start()
        for _ in range(240):
            if not ai.worker.is_alive(): break
            time.sleep(1)
        if ai.worker.is_alive(): raise RuntimeError('Index timeout')
        state=ai.status()
        print('Actual index:',json.dumps(state,ensure_ascii=False),flush=True)
        if state['state']!='complete': raise RuntimeError('Actual index failed')
        reports=[]
        for query,kind in [('傘が必要な暗い都会の景色','audio'),('青い画像','image'),('赤い表紙の本','book')]:
            started_query=time.perf_counter()
            result=ai.search(query,kind=kind,source='cover' if kind in ('image','book') else 'text')
            reports.append({'query':query,'kind':kind,'elapsed_ms':round((time.perf_counter()-started_query)*1000,1),
                            'top':[{'title':r['title'],'score':r['semantic_score']} for r in result['items'][:3]]})
        state['index_seconds']=round(time.perf_counter()-started,1)
        print('Actual ranking:',json.dumps(reports,ensure_ascii=False),flush=True)
        if not reports[0]['top'] or reports[0]['top'][0]['title']!='雨の夜の街並み.wav':
            raise RuntimeError('Japanese filename semantic ranking did not meet expected top hit')
        if reports[1]['top'][0]['title']!='image-01.png' or reports[2]['top'][0]['title']!='book-03.cbz':
            raise RuntimeError('Visual-mode color ranking did not meet expected top hits')
        if hashes!={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in media.iterdir()}:
            raise RuntimeError('Generated sources changed')
        (target/'actual-ai-result.json').write_text(json.dumps({'state':state,'queries':reports},ensure_ascii=False,indent=2),encoding='utf-8')
        print('PASS: actual offline GPU/model protocol, indexed fixtures, Japanese text top hit, sources unchanged',flush=True)
    finally: ai.close();catalog.close()

if __name__=='__main__': main()

