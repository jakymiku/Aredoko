"""Frozen, generated-only CPU page retrieval benchmark. Never loads a model."""
import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import threading
import time
import tracemalloc
import zipfile

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch,MAX_ITEMS
from page_index import PageIndex
from page_semantics import CONTRACT
from production import ProductionCatalog
from create_preview_fixture import png


class NoModel:
    profile=DEFAULT_PROFILE;available=False;resident=False;calls=0
    def encode(self,*args):self.calls+=1;raise AssertionError('No model calls in CPU retrieval benchmark')
    def close(self):pass


class GuardMeter:
    """Measure outer hold/wait time on this benchmark thread only."""
    def __init__(self,lock):
        self.lock=lock;self.owner=threading.get_ident();self.depth=0
        self.calls=self.holds=0;self.seconds=self.maximum=self.wait=0.0
    def acquire(self,*args,**kwargs):
        start=time.perf_counter();ok=self.lock.acquire(*args,**kwargs)
        if ok and threading.get_ident()==self.owner:
            self.calls+=1;self.wait+=time.perf_counter()-start
            if self.depth==0:self.start=time.perf_counter();self.holds+=1
            self.depth+=1
        return ok
    def release(self):
        if threading.get_ident()==self.owner:
            self.depth-=1
            if self.depth==0:
                elapsed=time.perf_counter()-self.start;self.seconds+=elapsed;self.maximum=max(self.maximum,elapsed)
        return self.lock.release()
    def __enter__(self):self.acquire();return self
    def __exit__(self,*args):self.release()
    def __getattr__(self,name):return getattr(self.lock,name)
    def summary(self):return dict(calls=self.calls,outer_holds=self.holds,hold_seconds=round(self.seconds,6),max_hold_seconds=round(self.maximum,6),wait_seconds=round(self.wait,6))


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def fingerprint(media):
    return {p.relative_to(media).as_posix():{'bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns,'sha256':sha(p)}
        for p in sorted(media.rglob('*.cbz'))}


def opened(output):
    catalog=ProductionCatalog(output/'catalog.sqlite');encoder=NoModel();ai=AISearch(catalog,encoder)
    return catalog,encoder,ai


def prepare(output,books,pages):
    if type(books) is not int or not 1<=books<=1024 or type(pages) is not int or not 1<=pages<=64:
        raise ValueError('At most 1024 books x 64 pages for generated benchmark')
    output.mkdir(parents=True,exist_ok=False);media=output/'generated';media.mkdir()
    protocol={'version':1,'generated_only':True,'books':books,'pages_per_book':pages,'dimension':DEFAULT_PROFILE.dimension,
        'seed':20261017,'book_limits':sorted(set(min(books,n) for n in (64,256,1024))),
        'vector_source':'128 fixed dense normalized float32 patterns, repeated across books; not model inference',
        'query':'fixed dense random normalized float64, same seed',
        'limits':'CPU rank and per-book coverage only; no embedding quality, GPU inference, end-to-end UI latency or private-library performance claim',
        'memory':'One separate full-rank tracemalloc pass; Python allocations only, excluding SQLite native/OS/GPU. Never compare traced time to untraced timing.'}
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n',encoding='utf-8')
    image=png(16,16,(40,80,120))
    for n in range(books):
        directory=media/('A' if n<max(1,books//2) else 'B');directory.mkdir(exist_ok=True)
        with zipfile.ZipFile(directory/f'book-{n:04}.cbz','w') as archive:
            for page in range(pages):archive.writestr(f'p{page:03}.png',image)
    catalog,encoder,ai=opened(output)
    try:
        roots=[]
        for directory in sorted(media.iterdir()):
            root=catalog.add_root(str(directory));roots.append(root);catalog.index.scan(root)
        catalog.sync_index();rows=ai._rows('','all');assert len(rows)==books
        rng=random.Random(protocol['seed']);vectors=[]
        for _ in range(128):
            values=[rng.uniform(-1,1) for _ in range(DEFAULT_PROFILE.dimension)];norm=math.sqrt(sum(x*x for x in values))
            vectors.append(array('f',(x/norm for x in values)).tobytes())
        index=PageIndex(catalog)
        with ai.store.connect() as target:
            for number,row in enumerate(rows):
                head=index.refresh(row['id'])
                with catalog.connect() as db:
                    snapshot=index._head(db,row['id'])['id']
                    entries=[dict(p) for p in db.execute('SELECT page_id,page FROM page_entries WHERE snapshot_id=? ORDER BY page',(snapshot,))]
                target.executemany('INSERT INTO ai_page_vectors VALUES(?,?,?,?,?,?)',
                    ((row['id'],head['source_revision'],p['page_id'],p['page'],vectors[(number*17+p['page'])%128],CONTRACT) for p in entries))
        assert encoder.calls==0
        receipt={'protocol_sha256':sha(output/'protocol.json'),'roots':roots,'sources':fingerprint(media),
            'vector_db_sha256':sha(ai.store.path),'vector_db_bytes':ai.store.path.stat().st_size,'page_vectors':books*pages}
        (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    finally:ai.close();catalog.close()
    return {'prepared':True,'books':books,'page_vectors':books*pages,'vector_db_bytes':receipt['vector_db_bytes'],'protocol_sha256':receipt['protocol_sha256']}


def digest_result(result):
    rows=[(key,value[0].hex(),value[1]) for key,value in sorted(result.items())]
    return hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()


def measure(output,label):
    path=output/(label+'.json')
    if path.exists():raise ValueError('Never overwrite a benchmark result')
    receipt=json.loads((output/'receipt.json').read_text());protocol=json.loads((output/'protocol.json').read_text())
    assert receipt['protocol_sha256']==sha(output/'protocol.json')
    assert receipt['sources']==fingerprint(output/'generated')
    catalog,encoder,ai=opened(output)
    report={'passed':False,'label':label,'protocol_sha256':receipt['protocol_sha256'],
        'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'page_semantics_sha256':sha(REPO/'app/page_semantics.py'),'profile':ai.profile.key,
        'dimension':protocol['dimension'],'cases':[],'measurement':'Each untraced case once in ascending order; OS/SQLite caches may warm. Separate traced pass follows.'}
    original_guard=catalog._guard
    try:
        assert sha(ai.store.path)==receipt['vector_db_sha256']
        rng=random.Random(protocol['seed']);query=[rng.uniform(-1,1) for _ in range(ai.profile.dimension)]
        norm=math.sqrt(sum(x*x for x in query));query=[x/norm for x in query]
        rows=ai._rows('','all')
        for count in protocol['book_limits']:
            selected=rows[:count];meter=GuardMeter(original_guard);catalog._guard=meter
            start=time.perf_counter();result=ai.pages.rank(selected,query);elapsed=time.perf_counter()-start
            catalog._guard=original_guard
            assert len(result)==count
            # Repeat score calculations through the normal image modality merger,
            # without asking the encoder to embed a natural-language query.
            ranked,video,page_hits=ai.store.rank_with_content(selected,query,'cover','max',result)
            assert len(ranked)==count and not video and len(page_hits)==count
            report['cases'].append({'books':count,'vectors':count*protocol['pages_per_book'],'rank_seconds':round(elapsed,6),
                'guard':meter.summary(),'result_sha256':digest_result(result),
                'merged_sha256':hashlib.sha256(json.dumps([ranked,page_hits],sort_keys=True).encode()).hexdigest()})
            print(json.dumps({'case':count,'rank_seconds':round(elapsed,6),'guard':meter.summary()}),flush=True)
        start=time.perf_counter();scoped=list(ai._iter_rows(limit=MAX_ITEMS,scope={'root_ids':[receipt['roots'][0]]}));selection_time=time.perf_counter()-start
        scoped_result=ai.pages.rank(scoped,query);assert len(scoped_result)==len(scoped)
        assert not ai.pages.rank([],query)
        report['scope']={'books':len(scoped),'selection_seconds':round(selection_time,6),'result_sha256':digest_result(scoped_result),'empty_results':0}
        meter=GuardMeter(original_guard);catalog._guard=meter;start=time.perf_counter()
        for row in rows[:8]:
            with catalog.connect() as db:revision=ai.pages.index._head(db,row['id'])['source_revision']
            coverage=ai.pages.coverage(row['id'],revision,{'root_ids':receipt['roots']})
            assert coverage['indexed_pages']==protocol['pages_per_book'] and coverage['remaining_pages']==0 and coverage['next_range'] is None
        report['coverage_eight']={'seconds':round(time.perf_counter()-start,6),'guard':meter.summary()};catalog._guard=original_guard
        tracemalloc.start();start=time.perf_counter();traced=ai.pages.rank(rows,query)
        _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        assert digest_result(traced)==report['cases'][-1]['result_sha256']
        report['traced_full']={'seconds':round(time.perf_counter()-start,6),'python_peak_bytes':peak,'books':len(rows)}
        report['source_unchanged']=receipt['sources']==fingerprint(output/'generated')
        report['vectors_unchanged']=sha(ai.store.path)==receipt['vector_db_sha256'];report['encoder_calls']=encoder.calls
        assert report['source_unchanged'] and report['vectors_unchanged'] and encoder.calls==0
        report['passed']=True
    finally:
        catalog._guard=original_guard
        if tracemalloc.is_tracing():tracemalloc.stop()
        ai.close();catalog.close();path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return {'passed':report['passed'],'label':label,'traced_full':report.get('traced_full'),'encoder_calls':encoder.calls}


def compare(output,before,after):
    """Fail closed on any raw score, provenance, order or scope difference."""
    baseline=json.loads((output/(before+'.json')).read_text())
    optimized=json.loads((output/(after+'.json')).read_text())
    receipt=json.loads((output/'receipt.json').read_text())
    for report in (baseline,optimized):
        assert report['passed'] and report['source_unchanged'] and report['vectors_unchanged']
        assert report['encoder_calls']==0
        assert report['protocol_sha256']==receipt['protocol_sha256']==sha(output/'protocol.json')
    assert baseline['profile']==optimized['profile'] and baseline['dimension']==optimized['dimension']
    assert len(baseline['cases'])==len(optimized['cases'])
    cases=[]
    for old,new in zip(baseline['cases'],optimized['cases']):
        for key in ('books','vectors','result_sha256','merged_sha256'):
            assert old[key]==new[key],(key,old['books'])
        cases.append({'books':old['books'],'vectors':old['vectors'],
            'before_seconds':old['rank_seconds'],'after_seconds':new['rank_seconds'],
            'reduction_percent':round(100*(1-new['rank_seconds']/old['rank_seconds']),2),
            'exact_results':True})
    for key in ('books','result_sha256','empty_results'):
        assert baseline['scope'][key]==optimized['scope'][key]
    return {'passed':True,'protocol_sha256':receipt['protocol_sha256'],'cases':cases,
        'exact_scope':True,'before_python_peak_bytes':baseline['traced_full']['python_peak_bytes'],
        'after_python_peak_bytes':optimized['traced_full']['python_peak_bytes']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','measure','compare'));parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--books',type=int,default=1024);parser.add_argument('--pages',type=int,default=64);parser.add_argument('--label',default='baseline')
    parser.add_argument('--before',default='baseline');parser.add_argument('--after',default='optimized')
    args=parser.parse_args();directory=args.output.resolve()
    if not directory.is_relative_to((REPO/'data/page-search-scale').resolve()):parser.error('Use data/page-search-scale/<fresh-run>')
    for label in (args.label,args.before,args.after):
        if not label.isascii() or not label.replace('-','').isalnum() or len(label)>40:parser.error('Use a short ASCII alphanumeric label')
    result=prepare(directory,args.books,args.pages) if args.mode=='prepare' else (measure(directory,args.label) if args.mode=='measure' else compare(directory,args.before,args.after))
    print(json.dumps(result),flush=True)
