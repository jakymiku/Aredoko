"""Frozen generated-only CPU coverage/plan lock benchmark. Never loads a model."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

import benchmark_page_coverage as fixture
from benchmark_page_search import GuardMeter, sha
from page_chunks import plan_chunked

REPO=fixture.REPO


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def opened(output):
    catalog=fixture.ProductionCatalog(output/'catalog.sqlite')
    encoder=fixture.NoModel();ai=fixture.AISearch(catalog,encoder)
    return catalog,encoder,ai


def prepare(output,pages):
    fixture.benchmark(output,pages)  # Fresh generated-only directory; no downloads.
    catalog,encoder,ai=opened(output)
    try:
        row=catalog.search()['items'][0];item=row['id']
        with catalog.connect() as db:head=dict(ai.pages.index._head(db,item))
        with ai.store.connect() as db:db.execute('DELETE FROM ai_page_vectors WHERE page%2=1')
        source=output/'generated/book.cbz'
        receipt=dict(version=1,pages=pages,item=item,revision=head['source_revision'],scope={'root_ids':[row['root_id']]},
                     profile=ai.profile.key,dimension=ai.profile.dimension,source_sha256=sha(source),source_mtime_ns=source.stat().st_mtime_ns,
                     vectors_sha256=sha(ai.store.path),snapshot_id=head['id'],head_page_count=head['page_count'],
                     selection='even pages stored; 128 next missing pages planned, no inference',encoder_calls=encoder.calls)
        assert encoder.calls==0
        (output/'lock-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
        return dict(prepared=True,pages=pages,stored_pages=(pages+1)//2,dimension=ai.profile.dimension)
    finally:ai.close();catalog.close()


def measure(output,label):
    path=output/(label+'.json')
    if path.exists():raise ValueError('Never overwrite evidence')
    receipt=json.loads((output/'lock-receipt.json').read_text())
    catalog,encoder,ai=opened(output);original=catalog._guard
    report=dict(passed=False,label=label,receipt_sha256=sha(output/'lock-receipt.json'),
                head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
                page_semantics_sha256=sha(REPO/'app/page_semantics.py'),cases=[],
                measurement='CPU, each operation once; instrumented guard, no tracemalloc or model. '
                            'No cold/warm, competing processes or order separation; not end-to-end or throughput guarantee.')
    source=output/'generated/book.cbz'
    def unchanged():
        return sha(source)==receipt['source_sha256'] and source.stat().st_mtime_ns==receipt['source_mtime_ns'] and sha(ai.store.path)==receipt['vectors_sha256']
    try:
        assert unchanged() and ai.profile.key==receipt['profile'] and ai.profile.dimension==receipt['dimension']
        operations=(('coverage',lambda:ai.pages.coverage(receipt['item'],receipt['revision'],receipt['scope'])),
                    ('plan',lambda:plan_chunked(ai,receipt['item'],receipt['revision'],receipt['scope'],128,ai.profile.key)))
        for name,operation in operations:
            meter=GuardMeter(original);catalog._guard=meter
            start=time.perf_counter();value=operation();seconds=time.perf_counter()-start
            catalog._guard=original
            assert value['source_state']=='current' and value['indexed_pages']==(receipt['pages']+1)//2
            if name=='plan':assert len(value['page_ids'])==min(128,receipt['pages']//2)
            case=dict(operation=name,seconds=seconds,guard=meter.summary(),result_sha256=digest(value),
                      indexed_pages=value['indexed_pages'],response_bytes=len(json.dumps(value).encode()))
            report['cases'].append(case);print(json.dumps(case),flush=True)
        with catalog.connect() as db:head=dict(ai.pages.index._head(db,receipt['item']))
        assert (head['id'],head['source_revision'],head['page_count'])==(receipt['snapshot_id'],receipt['revision'],receipt['head_page_count'])
        report.update(source_and_vectors_unchanged=unchanged(),snapshot_unchanged=True,encoder_calls=encoder.calls)
        assert report['source_and_vectors_unchanged'] and encoder.calls==0
        report['passed']=True
    finally:
        catalog._guard=original;ai.close();catalog.close();path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return {'passed':report['passed'],'label':label,'encoder_calls':encoder.calls}


def compare(output,before,after):
    old=json.loads((output/(before+'.json')).read_text());new=json.loads((output/(after+'.json')).read_text())
    for report in (old,new):
        assert report['passed'] and report['source_and_vectors_unchanged'] and report['snapshot_unchanged'] and report['encoder_calls']==0
        assert report['receipt_sha256']==sha(output/'lock-receipt.json')
    assert len(old['cases'])==len(new['cases'])
    results=[]
    for a,b in zip(old['cases'],new['cases']):
        for key in ('operation','result_sha256','indexed_pages','response_bytes'):assert a[key]==b[key]
        results.append(dict(operation=a['operation'],exact_response=True,before_seconds=a['seconds'],after_seconds=b['seconds'],
                            before_guard=a['guard'],after_guard=b['guard']))
    return dict(passed=True,cases=results)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','measure','compare'));parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--pages',type=int,default=10000);parser.add_argument('--label',default='lock-before')
    parser.add_argument('--before',default='lock-before');parser.add_argument('--after',default='lock-after')
    args=parser.parse_args();output=args.output.resolve()
    if not output.is_relative_to((REPO/'data/page-coverage').resolve()) or output==(REPO/'data/page-coverage').resolve():parser.error('Use data/page-coverage/<fresh-run>')
    for label in (args.label,args.before,args.after):
        if not label.isascii() or not label.replace('-','').isalnum() or len(label)>40:parser.error('Use short ASCII labels')
    result=prepare(output,args.pages) if args.mode=='prepare' else measure(output,args.label) if args.mode=='measure' else compare(output,args.before,args.after)
    print(json.dumps(result),flush=True)
