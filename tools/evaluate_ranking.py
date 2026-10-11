"""Actual EmbeddingGemma comparisons; fictional sources, fixed expected hits, no new models."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from production import ProductionCatalog
from ai_search import AISearch
from ai_process import EncoderProcess
from create_preview_fixture import create

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();target=args.output.resolve();target.mkdir(parents=True,exist_ok=False)
    media=create(target/'media')
    for name in ('雨の夜の街並み.wav','晴れた昼の海辺.wav','pattern-alpha.psd','pattern-beta.psd',
                 'garment-guide.pdf','scene-dawn.mp4','scene-night.mp4','art-flower.svg'):
        (media/name).write_bytes(b'fictional placeholder; metadata input only')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in media.iterdir()}
    catalog=ProductionCatalog(target/'catalog.sqlite')
    ai=AISearch(catalog,EncoderProcess(REPO/'.venv-ai/Scripts/python.exe',REPO/'models/embeddinggemma-2'))
    report={'cases':[],'ranking_parameters':{'policy':'mean-rrf','k':60,'tied_ranks':'average','normalization':'available modalities'}}
    try:
        root=catalog.add_root(str(media));catalog.start_scan(root);catalog._worker.join(15)
        if catalog._worker.is_alive():raise RuntimeError('Fixture scan timeout')
        tags={'pattern-alpha.psd':['下着デザイン','テンプレート','レース','服飾'],
              'pattern-beta.psd':['浴衣','和服','型紙'],
              'garment-guide.pdf':['下着','型紙','縫製'],
              'scene-dawn.mp4':['朝','にぎやかな街','動画'],
              'scene-night.mp4':['夜','静かな街','動画'],
              'art-flower.svg':['花柄','編集用デザイン','素材']}
        for row in ai._rows():
            if row['title'] in tags:catalog.update([row['id']],{'tags':tags[row['title']]})
        ai.start();ai.worker.join(240)
        if ai.worker.is_alive() or ai.status()['state']!='complete':raise RuntimeError('Index failed')
        # First six are previously observed development cases. Next eight are new
        # validation probes. Do not tune k/weights after inspecting the latter.
        cases=[('青い画像','image','image-01.png'),('赤い表紙の本','book','book-03.cbz'),
               ('青い表紙の本','book','book-01.cbz'),
               ('傘が必要な暗い都会の景色','audio','雨の夜の街並み.wav'),
               ('雨の夜の街並みという名前の音源','audio','雨の夜の街並み.wav'),
               ('晴れた昼の海辺という名前の音源','audio','晴れた昼の海辺.wav'),
               ('下着のデザインテンプレート','material','pattern-alpha.psd'),
               ('ランジェリーの制作に使えるひな形','material','pattern-alpha.psd'),
               ('下着の縫製に使う型紙','book','garment-guide.pdf'),
               ('花の模様を編集できるSVG','material','art-flower.svg'),
               ('活気のある朝の市街地の動画','video','scene-dawn.mp4'),
               ('静かな夜の街を映した動画','video','scene-night.mp4'),
               ('和服の型紙の元データ','material','pattern-beta.psd'),
               ('雨で暗い夜の市街地の音源','audio','雨の夜の街並み.wav')]
        for index,(query,explicit_kind,expected) in enumerate(cases):
            for kind in (explicit_kind,''):
                row={'query':query,'kind':kind,'expected':expected,'split':'development' if index<6 else 'validation'}
                for policy in ('max','mean-rrf'):
                    start=time.perf_counter();result=ai.search(query,kind=kind,ranking=policy)
                    titles=[r['title'] for r in result['items']]
                    row[policy]={'rank':titles.index(expected)+1 if expected in titles else None,
                                 'top':titles[:3],'elapsed_ms':round((time.perf_counter()-start)*1000,2),
                                 'ranking':result['ranking'],'score_kind':result['score_kind']}
                report['cases'].append(row)
        report['summary']={group:{policy:sum(r[policy]['rank']==1 for r in report['cases'] if r['split']==group)
                                 for policy in ('max','mean-rrf')} for group in ('development','validation')}
        report['record_count']=ai.status()['indexed']
        report['telemetry']=dict(ai.encoder.telemetry)
        report['source_hashes_unchanged']=hashes=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in media.iterdir()}
        if not report['source_hashes_unchanged']:raise RuntimeError('Source changed')
        report['runtime_pass']=True
        print(json.dumps(report,ensure_ascii=True),flush=True)
    finally:
        ai.close();catalog.close()
        (target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
