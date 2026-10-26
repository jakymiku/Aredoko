"""Measure generated 50k metadata paging and CPU-only scope counts, never model inference."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'app'))
from create_library_scale_fixture import create,digest
from production import ProductionCatalog
from ai_search import AISearch
from ai_settings import AIProfileSettings
from result_sessions import ResultSessions

class NoInference:
    available=False
    def encode(self,*args):raise AssertionError('Inference is outside this measurement')
    def close(self):pass

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--snapshot-only',action='store_true',help='One fixed-order result snapshot; no repeated coverage timings')
    parser.add_argument('--count',type=int,default=50000,help='Generated metadata count for snapshot-only (120..50000)')
    parser.add_argument('--real-files',action='store_true',help='Snapshot-only: create one ordinary generated PNG for every metadata row')
    parser.add_argument('--fixture',type=Path,help='Snapshot-only: reuse an explicitly generated data/ai-ui fixture without duplicating its media')
    args=parser.parse_args();target=args.output.resolve()
    if not 120<=args.count<=50000 or (not args.snapshot_only and args.count!=50000):parser.error('Custom count is for bounded snapshot-only fixtures')
    if args.real_files and not args.snapshot_only:parser.error('Real-file mode is one snapshot, not repeated broad benchmarks')
    if args.fixture and not args.snapshot_only:parser.error('Fixture reuse is for one fixed snapshot')
    if not target.is_relative_to((REPO/'data/ai-ui').resolve()):parser.error('Fresh output inside data/ai-ui required')
    if args.snapshot_only:
        began=time.perf_counter();source=target
        if args.fixture:
            source=args.fixture.resolve()
            if not source.is_relative_to(REPO/'data/ai-ui') or (source/'fixture.json').stat().st_size>16384:parser.error('Bounded generated fixture required')
            fixture=json.loads((source/'fixture.json').read_text(encoding='utf-8'))
            if (fixture.get('generated_only') is not True or fixture.get('metadata_count')!=args.count or
                args.real_files and fixture.get('all_items_backed_by_generated_files') is not True):parser.error('Generated fixture scope mismatch')
            if digest(source/'generated')!=fixture['source_digest']:parser.error('Generated fixture sources changed')
            target.mkdir(parents=True,exist_ok=False)
        else:fixture=create(target,count=args.count,root_count=2,materialize_images=args.real_files)
        preparation_seconds=time.perf_counter()-began;catalog=ProductionCatalog(source/'catalog.sqlite')
        def provider(conditions,consume,cancelled):return catalog.search(limit=120,result_sink=consume,cancelled=cancelled,**conditions)
        owner=ResultSessions(catalog,provider,parent=target);report={'pass':False,'fixture':fixture,'actual_model':False,'native_gui_run':False}
        try:
            started=time.perf_counter();result=owner.create('a'*32,{});elapsed=time.perf_counter()-started
            session=owner.sessions['a'*32];payload_hash=hashlib.sha256();captured_sources=0
            for row in session.db.execute('SELECT ordinal,item_id,image,payload FROM results ORDER BY ordinal'):
                payload_hash.update(json.dumps(tuple(row),ensure_ascii=False,separators=(',',':')).encode('utf-8'))
                captured_sources+=isinstance(json.loads(row[3]).get('_source_identity'),list)
            report.update(seconds=elapsed,total=result['total'],workspace_bytes=session.bytes(),payload_sha256=payload_hash.hexdigest(),
                          generated_seconds=0 if args.fixture else preparation_seconds,fixture_preparation_seconds=preparation_seconds,
                          fixture_reused=bool(args.fixture),captured_source_count=captured_sources,
                          sources_unchanged=digest(source/'generated')==fixture['source_digest'])
            report['pass']=result['total']==args.count and report['sources_unchanged']
            if args.real_files:
                first=session.read(0,1);last=session.read(args.count-1,1)
                report['first_and_last_source_present']=all(reply['items'][0]['availability']=='present' for reply in (first,last))
                report['pass']=report['pass'] and captured_sources==args.count and report['first_and_last_source_present']
        finally:
            report['owned_jobs_closed']=owner.close();catalog.close()
            report['pass']=report['pass'] and report['owned_jobs_closed']
            (target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=True));return 0 if report['pass'] else 1
    started=time.perf_counter();fixture=create(target);generated_seconds=time.perf_counter()-started
    catalog=ProductionCatalog(target/'catalog.sqlite');ai=AISearch(catalog,NoInference())
    report={'pass':False,'fixture':fixture,'generated_seconds':round(generated_seconds,3),'actual_model':False,'native_gui_run':False,'checks':[],'timings_ms':{}}
    def check(name,condition):
        report['checks'].append({'name':name,'pass':bool(condition)})
        if not condition:raise AssertionError(name)
    def measured(name,operation):
        values=[]
        for _ in range(5):
            start=time.perf_counter();result=operation();values.append(round((time.perf_counter()-start)*1000,3))
        report['timings_ms'][name]={'samples':values,'median':sorted(values)[2],'max':max(values)}
        return result
    try:
        check('50k metadata first page',len(measured('first_page',lambda:catalog.search())['items'])==60)
        last=measured('last_page',lambda:catalog.search(page=833));check('last page20',len(last['items'])==20 and last['items'][-1]['id']==50000)
        check('literal tag last candidate',measured('literal_tag',lambda:catalog.search('最後の検証候補'))['items'][0]['id']==50000)
        check('500 favorites',measured('favorites',lambda:catalog.search(view='favorites'))['total']==500)
        all_scope=measured('coverage_all',lambda:ai.coverage())
        check('50k candidates capped at10k',all_scope['candidate_total']==50000 and all_scope['target_total']==10000 and all_scope['fresh_total']==0)
        ids=fixture['roots'];selected=ids[:256]
        check('maximum256 roots accepted',measured('coverage_256',lambda:ai.coverage({'root_ids':selected}))['target_total']==10000)
        one=measured('coverage_last_root',lambda:ai.coverage({'root_ids':[ids[-1]]}))
        check('root beyond256 narrowed',one['candidate_total']==fixture['per_root'][str(ids[-1])])
        settings=AIProfileSettings(REPO,target/'settings.json');scope={'root_ids':selected,'kind':'','shelf':None};settings.set_scope(scope)
        check('256 root setting restart',AIProfileSettings(REPO,target/'settings.json').scope()==scope)
        check('settings size bounded',(target/'settings.json').stat().st_size<=16384)
        settings.set_scope({'root_ids':[ids[-1]]})
        check('beyond256 preference saved',settings.scope()['root_ids']==[ids[-1]])
        for bad in (ids[:257],[ids[-1]+1000]):
            try:ai.coverage({'root_ids':bad})
            except ValueError:check('oversize/unknown selection rejected',True)
            else:raise AssertionError('Invalid roots accepted')
        check('empty selection never widens',ai.coverage({'root_ids':[]})['target_total']==0)
        check('source digest unchanged',digest(target/'generated')==fixture['source_digest'])
        report['pass']=True
    except Exception as error:report['error']=str(error)
    finally:
        ai.close();catalog.close();(target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('pass','checks','timings_ms')},ensure_ascii=True))
    return 0 if report['pass'] else 1

if __name__=='__main__':raise SystemExit(main())
