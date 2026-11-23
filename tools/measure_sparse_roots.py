"""CPU-only synthetic sparse-root measurements with fresh isolated output."""
import json
from pathlib import Path
import argparse,sys,time
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo/'tools'));sys.path.insert(0,str(repo/'app'))
from create_library_scale_fixture import create,digest
from measure_library_scale import NoInference
from production import ProductionCatalog
from ai_search import AISearch
def main():
    parser=argparse.ArgumentParser(description='Measure generated metadata with sparse selected roots; no inference or real scans');parser.add_argument('--output',type=Path,required=True)
    target=parser.parse_args().output.resolve()
    if not target.is_relative_to((repo/'data/ai-ui').resolve()):parser.error('Fresh output inside data/ai-ui required')
    info=create(target)
    catalog=ProductionCatalog(target/'catalog.sqlite');ai=AISearch(catalog,NoInference())
    report={'pass':False,'metadata_count':50000,'actual_model':False,'checks':[],'scenarios':[]}
    def check(name,value):
        report['checks'].append({'name':name,'pass':bool(value)})
        if not value:raise AssertionError(name)
    try:
        for name,ids in [('early-two',[76,77]),('late-two',[49999,50000]),('distributed-500',list(range(100,50001,100)))]:
            with catalog.connect() as db:
                db.execute('UPDATE library_locations SET root_id=1 WHERE id>75')
                for pos,item in enumerate(ids):db.execute('UPDATE library_locations SET root_id=? WHERE id=?',(257+pos%2,item))
            scope={'root_ids':[257,258]};times=[]
            for _ in range(5):
                start=time.perf_counter();value=ai.coverage(scope);times.append(round((time.perf_counter()-start)*1000,3))
            check(name+' candidate count',value['candidate_total']==len(ids))
            check(name+' exact ID order',[r['id'] for r in ai._iter_rows(scope=scope,all_candidates=True)]==ids)
            check(name+' cap/fresh',value['target_total']==len(ids) and value['fresh_total']==0)
            report['scenarios'].append({'name':name,'candidate_count':len(ids),'samples_ms':times,'median_ms':sorted(times)[2],'max_ms':max(times)})
        check('real PNG bytes/mtime unchanged',digest(target/'generated')==info['source_digest'])
        report['pass']=True
    except Exception as ex:report['error']=str(ex)
    finally:
        ai.close();catalog.close();(target/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report));raise SystemExit(0 if report['pass'] else 1)

if __name__=="__main__":main()
