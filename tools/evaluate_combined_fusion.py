"""One frozen fusion trial: existing offline CUDA scores, then CPU-only replay."""
import argparse
import hashlib
import json
import sqlite3
import statistics
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from ai_profiles import DEFAULT_PROFILE
from ai_process import EncoderProcess
from ai_search import AISearch
from ai_ranking import fuse_modalities
from production import ProductionCatalog
from create_preview_fixture import png
from create_search_quality_fixture import create as create_controls
from evaluate_representative_assets import load_assets_from_zip,build_evaluation_library,match_asset_key

MANIFEST=REPO/'tests/fixtures/combined-fusion-v8.json'
SHA256='1ad69335c9d1889efb017f48028f5eb860e980b7d1b4a9fa47e31d3c7c5556ef'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
    return h.hexdigest()


def load_manifest():
    raw=MANIFEST.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SHA256:raise ValueError('Frozen fusion fixture changed')
    return json.loads(raw)


def metrics(keys,target):
    if target is None:return None
    rank=keys.index(target)+1 if target in keys else None
    return {'top1':int(rank==1),'recall3':int(rank is not None and rank<=3),'mrr':1/rank if rank else 0}


def summary(cases,field):
    result={}
    for group in sorted({c['group'] for c in cases}|{'overall'}):
        rows=[c[field] for c in cases if c['target'] is not None and (group=='overall' or c['group']==group)]
        if rows:result[group]={'count':len(rows),**{key:round(statistics.mean(r[key] for r in rows),6) for key in ('top1','recall3','mrr')}}
    return result


def capture(ai,query,vector,scope,label):
    rows=list(ai._iter_rows(scope=scope));pages=ai.pages.rank(rows,vector);saved=[]
    def fusion(scores,policy):saved.append(scores);return fuse_modalities(scores,policy)
    with patch('ai_search.fuse_modalities',side_effect=fusion):
        combined,_,_=ai.store.rank_with_content(rows,vector,'all','mean-rrf',pages)
    text,_,_=ai.store.rank_with_content(rows,vector,'text','max')
    cover,_,_=ai.store.rank_with_content(rows,vector,'cover','max',pages)
    return {'scores':saved[0], 'baseline_ids':[i for i,_ in combined],
        'text':text,'cover':cover,'labels':label,'scope':scope,'query':query}


def prepare(output):
    manifest=load_manifest();output.mkdir(parents=True,exist_ok=False)
    source=REPO/'data/representative-eval/real-v1-20261017'
    zips=[REPO.parent/'Aredoko-test'/name for name in ('Aredoko_search_test_images_8.zip','Aredoko_text_recognition_test_images_6.zip')]
    original={str(p):sha(p) for p in [*zips,source/'catalog.sqlite',source/'catalog.sqlite.ai.sqlite',source/'report.json',source/'frozen-protocol.json']}
    protocol={'manifest_sha256':SHA256,'profile':DEFAULT_PROFILE.identity(),'python':sys.version,
        'original_hashes':original,'mode':'score capture before product change; no WD/OCR/new download',
        'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()}
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    assets=load_assets_from_zip(zips);lib=build_evaluation_library(output/'library',assets)
    controls=output/'controls'
    create_controls(controls,[i for i in manifest['extra_items'] if i['kind']!='image'])
    for item in manifest['extra_items']:
        if item['kind']=='image':(controls/item['file']).write_bytes(png(200,200,(120,120,120)))
    sources=[p for folder in (output/'library',controls) for p in folder.rglob('*') if p.is_file()]
    source_hashes={str(p):[sha(p),p.stat().st_mtime_ns] for p in sources}
    encoder=EncoderProcess(REPO/'.venv-ai/Scripts/python.exe',DEFAULT_PROFILE.model_path(REPO))
    catalog=None;ai=None;dev=None;dev_ai=None;cache=[]
    try:
        catalog=ProductionCatalog(output/'catalog.sqlite')
        roots=[catalog.add_root(str(lib['cbz_dir'])),catalog.add_root(str(lib['folder_dir']),folder_books=True),
               catalog.add_root(str(lib['assets_dir'])),catalog.add_root(str(controls))]
        for root in roots:catalog.index.scan(root)
        catalog.sync_index();scope={'root_ids':roots}
        extra={i['file']:i for i in manifest['extra_items']};labels={};root_for={}
        for row in catalog.search(limit=120)['items']:
            name=row['title'];key='bookA' if name=='bookA.cbz' else 'bookB' if name=='bookB' else match_asset_key(name)
            if name in extra:key=extra[name]['key']
            labels[row['id']]=key;root_for[key]=row['root_id']
            tags=extra[name]['tags'] if name in extra else manifest['agreed_tags'].get(key,[])
            if tags:catalog.update([row['id']],{'tags':tags})
        assert len(labels)==16 and None not in labels.values()
        ai=AISearch(catalog,encoder);ai.start(scope=scope);ai.worker.join(240)
        assert not ai.worker.is_alive() and ai.status()['state']=='complete',ai.status()
        for row in ai._rows('','all'):
            if labels[row['id']] in ('bookA','bookB'):
                ai.pages.index.refresh(row['id']);snap=ai.pages.index.list(row['id'])
                ai.pages.start(row['id'],[p['page_id'] for p in snap['pages']],snap['source_revision'],scope)
                ai.worker.join(240);assert not ai.worker.is_alive() and ai.status()['state']=='complete'
        vectors={q:encoder.encode('query',q) for q in dict.fromkeys(c['query'] for c in manifest['cases'])}
        for case in manifest['cases']:
            for name,selected in [('all',scope),('root',{'root_ids':[root_for[case['target']]]})] if case['target'] else [('all',scope)]:
                result=capture(ai,case['query'],vectors[case['query']],selected,labels)
                cache.append({**case,'condition':name,**result})
        # Development set: preserve the exact original catalog, IDs and namespaces.
        for old,new in (('catalog.sqlite','dev.sqlite'),('catalog.sqlite.ai.sqlite','dev-vectors.sqlite')):
            with sqlite3.connect((source/old).as_uri()+'?mode=ro',uri=True) as src:
                with sqlite3.connect(output/new) as dst:src.backup(dst)
        dev=ProductionCatalog(output/'dev.sqlite');dev_ai=AISearch(dev,encoder,store_path=output/'dev-vectors.sqlite')
        old=json.loads((source/'report.json').read_text(encoding='utf-8'))
        labels={r['id']:('bookA' if r['title']=='bookA.cbz' else 'bookB' if r['title']=='bookB' else match_asset_key(r['title'])) for r in dev_ai._rows('','all')}
        for row in dev_ai._rows('','all'):
            if row['kind'] in ('book','archive'):
                with dev.connect() as db:head=dev_ai.pages.index._head(db,row['id'])
                assert dev_ai.pages.index.state(row['id'],head['source_revision'])=='current','Use original evaluation Python; never bypass stale source guards'
        development=[]
        for case in old['cases']:
            result=capture(dev_ai,case['query'],encoder.encode('query',case['query']),{'root_ids':[r['id'] for r in dev.index.roots()]},labels)
            assert [labels[i] for i in result['baseline_ids']]==case['combined']['ranked_keys']
            development.append({'id':case['id'],'group':'development','target':case['target_item'],'condition':'all',**result})
        assert original=={str(p):sha(p) for p in [*zips,source/'catalog.sqlite',source/'catalog.sqlite.ai.sqlite',source/'report.json',source/'frozen-protocol.json']}
        assert source_hashes=={str(p):[sha(p),p.stat().st_mtime_ns] for p in sources}
        payload={'manifest_sha256':SHA256,'profile':DEFAULT_PROFILE.key,'cases':cache,'development':development,
            'sources':source_hashes,'original_hashes':original,'device':encoder.device,'vector_sha256':sha(ai.store.path),'vector_file':ai.store.path.name}
        (output/'cache.json').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
        print(json.dumps({'prepared':True,'device':encoder.device,'cases':len(cache),'development':len(development)}),flush=True)
    finally:
        if dev_ai:dev_ai.close()
        if ai:ai.close()
        else:encoder.close()
        if dev:dev.close()
        if catalog:catalog.close()


def compare(output,label):
    load_manifest();path=output/(label+'.json')
    if path.exists():raise ValueError('Do not overwrite a fusion result')
    cache=json.loads((output/'cache.json').read_text(encoding='utf-8'))
    assert cache['manifest_sha256']==SHA256
    assert sha(output/cache['vector_file'])==cache['vector_sha256']
    all_results=[]
    for case in cache['cases']+cache['development']:
        scores={int(i):s for i,s in case['scores'].items()};labels={int(i):name for i,name in case['labels'].items()}
        ranked=fuse_modalities(scores,'mean-rrf');ids=[i for i,_ in ranked]
        assert set(ids)==set(case['baseline_ids'])
        for mode in ('text','cover'):
            current=fuse_modalities({i:{mode:m[mode]} for i,m in scores.items() if mode in m},'max')
            assert current==[tuple(pair) for pair in case[mode]]
        old_keys=[labels[i] for i in case['baseline_ids']];new_keys=[labels[i] for i in ids]
        all_results.append({k:case[k] for k in ('id','group','condition','target')}|{
            'before':metrics(old_keys,case['target']),'after':metrics(new_keys,case['target']),
            'old_top':old_keys[:5],'new_top':new_keys[:5]})
    new=[c for c in all_results if c['group']!='development'];dev=[c for c in all_results if c['group']=='development']
    regressions=[c['id']+':'+c['condition'] for c in new if c['before'] and c['before']['top1']>c['after']['top1']]
    for paths in (cache['sources'],cache['original_hashes']):
        for name,before in paths.items():
            p=Path(name);actual=[sha(p),p.stat().st_mtime_ns] if type(before) is list else sha(p)
            assert actual==before
    result={'passed':True,'manifest_sha256':SHA256,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'device_at_capture':cache['device'],'python_at_capture':json.loads((output/'protocol.json').read_text(encoding='utf-8'))['python'],
        'ranking_source_sha256':sha(REPO/'app/ai_ranking.py'),'model_calls_for_compare':0,'cases':all_results,'regressions':regressions,
        'new_all_before':summary([c for c in new if c['condition']=='all'],'before'),
        'new_all_after':summary([c for c in new if c['condition']=='all'],'after'),
        'development_before':summary(dev,'before'),'development_after':summary(dev,'after')}
    result['quality_gate']=not regressions and result['development_after']['overall']['top1']>result['development_before']['overall']['top1']
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='cases'},ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','compare'));parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--label',default='candidate');args=parser.parse_args()
    output=args.output.resolve()
    if not output.is_relative_to((REPO/'data/combined-fusion').resolve()):parser.error('Use a fresh data/combined-fusion/<run>')
    if not args.label.isascii() or not args.label.replace('-','').isalnum():parser.error('Use an ASCII alphanumeric label')
    prepare(output) if args.mode=='prepare' else compare(output,args.label)
