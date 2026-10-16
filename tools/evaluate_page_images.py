"""Direct image retrieval over fixed original Japanese page PNGs; never OCR.

Uses the existing ocr-eval-v1 rendering as *input*, plus a blank cover per book.
The changed retrieval qrels below are declared before inference: meaning across
pages is allowed. This is synthetic coverage evidence, not a new P0 holdout.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
import zipfile

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from ai_process import EncoderProcess
from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch
from production import ProductionCatalog
from page_index import PageIndex
from create_preview_fixture import png
from ocr_quality import digest
from search_quality import metrics

QUERIES=[('青い傘を忘れた','item-01','page-01'),('下着のデザイン素材','item-02','page-02'),
    ('素材の番号123','item-02','page-02'),('教室の机','item-03','page-03'),
    ('雨の日の約束','item-03','page-04'),('幼なじみと再会','item-04','page-05'),
    ('看板の文字','item-06','page-07'),('AIのPNG背景素材','item-07','page-08')]
NEGATIVE=['宇宙船の地下室','青い教室']


def evaluate(output,rendered):
    fixture=json.loads((REPO/'tests/fixtures/ocr-eval-v1.json').read_bytes())
    receipt=json.loads((rendered/'receipt.json').read_bytes())
    if receipt['fixture_sha256']!=digest(fixture):raise ValueError('Frozen input mismatch')
    for image in receipt['images']:
        if hashlib.sha256((rendered/image['file']).read_bytes()).hexdigest()!=image['sha256']:
            raise ValueError('Rendered image changed')
    output.mkdir(parents=True,exist_ok=False)
    protocol={'queries':QUERIES,'negative_queries':NEGATIVE,'render_receipt':receipt,
        'book_layout':'blank cover then original page(s), file names are opaque item IDs',
        'source':'cover','ranking':'existing cosine maximum per book; no thresholds or weights changed'}
    raw=json.dumps(protocol,ensure_ascii=False,sort_keys=True,indent=2).encode()
    (output/'frozen-protocol.json').write_bytes(raw)
    report={'passed':False,'fixture':'ocr-eval-v1 Japanese PNGs as direct image inputs; no OCR',
        'synthetic_only':True,'protocol_sha256':hashlib.sha256(raw).hexdigest(),'cases':[],
        'profile':DEFAULT_PROFILE.identity(),'scope':'Coverage of predeclared synthetic pages, not representative library precision or P0 tuning.'}
    media=output/'generated-books';media.mkdir()
    groups={}
    for page in fixture['pages']:groups.setdefault(page['item'],[]).append(page)
    for item,pages in groups.items():
        with zipfile.ZipFile(media/(item+'.cbz'),'w') as book:
            book.writestr('p00.png',png(600,420,(240,240,240)))
            for n,page in enumerate(pages,1):book.writestr(f'p{n:02}.png',(rendered/(page['id']+'.png')).read_bytes())
    before={p.name:(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in media.iterdir()}
    catalog=ProductionCatalog(output/'catalog.sqlite');encoder=EncoderProcess(REPO/'.venv-ai/Scripts/python.exe',DEFAULT_PROFILE.model_path(REPO))
    ai=AISearch(catalog,encoder);process=None
    try:
        root=catalog.add_root(str(media.resolve()));catalog.index.scan(root);catalog.sync_index();scope={'root_ids':[root]}
        rows=catalog.search()['items'];ids={r['title'].removesuffix('.cbz'):r['id'] for r in rows};keys={v:k for k,v in ids.items()}
        start=time.perf_counter();ai.start(scope=scope);ai.worker.join(240)
        if ai.worker.is_alive() or ai.status()['state']!='complete':raise RuntimeError('Normal cover build failed')
        report['cover_index_seconds']=round(time.perf_counter()-start,3)
        def measure(stage):
            values=[];page_hits=[]
            for query,expected,page_key in QUERIES:
                result=ai.search(query,source='cover',scope=scope)
                ranked=[keys[r['id']] for r in result['items']]
                m=metrics(ranked,{expected:1});values.append(m)
                actual=next((r.get('ai_page_match') for r in result['items'] if r['id']==ids[expected]),None)
                expected_page=next(i for i,p in enumerate(groups[expected],1) if p['id']==page_key)
                page_hit=bool(ranked and ranked[0]==expected and actual and actual['page']==expected_page)
                page_hits.append(page_hit)
                report['cases'].append({'stage':stage,'query':query,'expected_item':expected,'expected_page':expected_page,
                    'ranked':ranked,'metrics':m,'expected_book_evidence':actual,'exact_page_at_1':page_hit})
            report[stage]={'queries':len(values),'means':{k:statistics.mean(v[k] for v in values) for k in values[0]},
                'exact_page_at_1':sum(page_hits)/len(page_hits)}
        measure('cover_only')
        start=time.perf_counter();index=PageIndex(catalog)
        for item,item_id in ids.items():
            index.refresh(item_id);snapshot=index.list(item_id)
            ai.pages.start(item_id,[p['page_id'] for p in snapshot['pages'] if p['page']>0],snapshot['source_revision'],scope)
            ai.worker.join(240)
            if ai.worker.is_alive() or ai.status()['state']!='complete':raise RuntimeError('Explicit page build failed')
        report['page_index_seconds']=round(time.perf_counter()-start,3)
        measure('with_internal_pages')
        report['negative_cases']=[{'query':query,'top':[(keys[r['id']],r['semantic_score']) for r in ai.search(query,source='cover',scope=scope)['items'][:3]]} for query in NEGATIVE]
        report['negative_note']='Ranked candidates are always returned; these are diagnostics, not rejection successes.'
        with ai.store.connect() as db:
            report['page_vectors'],report['vector_bytes']=db.execute('SELECT count(*),coalesce(sum(length(vector)),0) FROM ai_page_vectors').fetchone()
        report['device']=encoder.device
        if encoder.device!='cuda':raise RuntimeError('Expected existing CUDA runtime')
        report['source_unchanged']=before=={p.name:(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in media.iterdir()}
        if not report['source_unchanged']:raise RuntimeError('Generated originals changed')
        report['passed']=True
    finally:
        process=encoder.process;ai.close();catalog.close()
        report['worker_stopped']=process is None or process.poll() is not None
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rendered',type=Path,required=True);args=parser.parse_args()
    result=evaluate(args.output,args.rendered)
    print(json.dumps({k:result[k] for k in ('passed','device','page_vectors','cover_only','with_internal_pages','page_index_seconds','worker_stopped')},ensure_ascii=False))
