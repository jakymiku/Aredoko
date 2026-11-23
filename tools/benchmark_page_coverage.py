"""Generated-only, no-model page coverage cost at the 10,000-page ceiling."""
import argparse
from array import array
import hashlib
import json
from pathlib import Path
import sys
import time
import tracemalloc
import zipfile

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch
from page_index import PageIndex
from page_semantics import CONTRACT
from production import ProductionCatalog
from create_preview_fixture import png


class NoModel:
    profile=DEFAULT_PROFILE
    available=False
    resident=False
    calls=0
    def encode(self,*args):
        self.calls+=1;raise AssertionError('Coverage must never infer')
    def close(self):pass


def benchmark(output,pages=10000):
    if type(pages) is not int or not 1<=pages<=10000:raise ValueError('pages must be 1..10000')
    output=output.resolve()
    if not output.is_relative_to((REPO/'data/page-coverage').resolve()):raise ValueError('Use a fresh data/page-coverage output directory')
    output.mkdir(parents=True,exist_ok=False);media=output/'generated';media.mkdir();source=media/'book.cbz'
    with zipfile.ZipFile(source,'w') as book:
        for n in range(pages):book.writestr(f'p{n:05}.png',png(16,16,(40,80,120)))
    original=(hashlib.sha256(source.read_bytes()).hexdigest(),source.stat().st_mtime_ns)
    catalog=ProductionCatalog(output/'catalog.sqlite');encoder=NoModel();ai=AISearch(catalog,encoder)
    report={'passed':False,'generated_only':True,'pages':pages,'dimension':DEFAULT_PROFILE.dimension,'cases':[],
        'measurement':'Each case timed once without allocation tracing; final full case additionally measured with tracemalloc. Python peak excludes SQLite native/OS/GPU allocations.'}
    try:
        root=catalog.add_root(str(media));catalog.index.scan(root);catalog.sync_index();item=catalog.search()['items'][0]['id']
        index=PageIndex(catalog);head=index.refresh(item);revision=head['source_revision']
        with catalog.connect() as db:
            sid=index._head(db,item)['id'];entries=[dict(p) for p in db.execute('SELECT page_id,page FROM page_entries WHERE snapshot_id=? ORDER BY page',(sid,))]
        scope={'root_ids':[root]};blob=array('f',[1]+[0]*(DEFAULT_PROFILE.dimension-1)).tobytes()
        def seed(selected):
            with ai.store.connect() as db:
                db.execute('DELETE FROM ai_page_vectors')
                db.executemany('INSERT INTO ai_page_vectors VALUES(?,?,?,?,?,?)',
                    ((item,revision,p['page_id'],p['page'],blob,CONTRACT) for p in selected))
        for name,selected in [('empty',[]),('alternating',entries[::2]),('complete',entries)]:
            seed(selected);start=time.perf_counter();result=ai.pages.coverage(item,revision,scope);elapsed=time.perf_counter()-start
            assert result['indexed_pages']==len(selected) and result['remaining_pages']==pages-len(selected)
            report['cases'].append({'name':name,'seconds':round(elapsed,6),'indexed_pages':result['indexed_pages'],
                'ranges':len(result['indexed_ranges']),'next_range':result['next_range'],'response_bytes':len(json.dumps(result).encode())})
        tracemalloc.start();start=time.perf_counter();ai.pages.coverage(item,revision,scope)
        _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        report['traced_complete_seconds']=round(time.perf_counter()-start,6);report['python_peak_bytes']=peak
        report['store_bytes']=ai.store.path.stat().st_size;report['encoder_calls']=encoder.calls
        report['source_unchanged']=original==(hashlib.sha256(source.read_bytes()).hexdigest(),source.stat().st_mtime_ns)
        assert report['source_unchanged'] and encoder.calls==0
        report['passed']=True
    finally:
        ai.close();catalog.close()
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--pages',type=int,default=10000)
    args=parser.parse_args();print(json.dumps(benchmark(args.output,args.pages),ensure_ascii=False))
