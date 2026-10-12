"""Measure generated 50k metadata paging and CPU-only scope counts, never model inference."""
import argparse
import json
from pathlib import Path
import sys
import time
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'app'))
from create_library_scale_fixture import create,digest
from production import ProductionCatalog
from ai_search import AISearch
from ai_settings import AIProfileSettings

class NoInference:
    available=False
    def encode(self,*args):raise AssertionError('Inference is outside this measurement')
    def close(self):pass

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    target=parser.parse_args().output.resolve()
    if not target.is_relative_to((REPO/'data/ai-ui').resolve()):parser.error('Fresh output inside data/ai-ui required')
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
