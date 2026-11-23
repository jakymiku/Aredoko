"""Offline actual-CUDA scope slice on six generated files in two roots."""
import argparse
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import urllib.request

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from ai_search import AISearch
from ai_settings import AIProfileSettings
from production import ProductionCatalog
from production_server import production_handler
from create_preview_fixture import png
from test_index_gpu_scaling import MeasuredEncoder, source_digest
from test_index_gpu_api import vector_digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();target=args.output.resolve()
    if os.name!='nt' or not target.is_relative_to((REPO/'data/ai-ui').resolve()):
        parser.error('New generated output inside data/ai-ui on Windows required')
    target.mkdir(parents=True,exist_ok=False)
    folders=[]
    for number,colors in ((1,((50,80,200),(200,50,50))),(2,((50,180,80),(200,180,50)))):
        folder=target/f'generated-{number}';folder.mkdir();folders.append(folder)
        for index,color in enumerate(colors):
            (folder/f'素材-{index}.png').write_bytes(png(color=color))
        (folder/'音楽.wav').write_bytes(b'generated audio metadata only')
    sources=[source_digest(folder) for folder in folders]
    catalog=ProductionCatalog(target/'catalog.sqlite');encoder=MeasuredEncoder();ai=AISearch(catalog,encoder)
    report={'pass':False,'actual_model':True,'native_gui_run':False,'generated_sources_only':True,'checks':[]}
    server=None;http_thread=None;restart=None;restarted_encoder=None
    def check(name,condition):
        report['checks'].append({'name':name,'pass':bool(condition)})
        print(json.dumps({'check':name,'pass':bool(condition)}),flush=True)
        if not condition:raise RuntimeError(name)
    try:
        roots=[]
        for folder in folders:
            root=catalog.add_root(str(folder));roots.append(root)
            catalog.start_scan(root);catalog._worker.join(15)
        check('six generated files registered',catalog.search()['total']==6)
        images=[row for row in catalog.search()['items'] if row['kind']=='image']
        catalog.update([row['id'] for row in images if row['root_id']==roots[0]],{'shelf':'素材'})
        a={'root_ids':[roots[0]],'kind':'image','shelf':'素材'}
        b={'root_ids':[roots[1]],'kind':'image'}
        ids={root:{row['id'] for row in images if row['root_id']==root} for root in roots}
        key,path=ai.profile.key,ai.store.path
        settings=AIProfileSettings(REPO,target/'settings.json')
        token=secrets.token_urlsafe(24)
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(catalog,token,ai=ai,profiles=settings))
        http_thread=threading.Thread(target=server.serve_forever,daemon=True);http_thread.start()
        origin=f'http://127.0.0.1:{server.server_port}'
        def api(route,body):
            request=urllib.request.Request(origin+route,json.dumps(body,ensure_ascii=False).encode(),
                {'Origin':origin,'X-Aredoko-Token':token,'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=180) as response:return json.load(response)
        counts=api('/api/library/ai/coverage',{'scope':a})
        check('CPU-only scoped counts without worker',counts['target_total']==2 and counts['fresh_total']==0 and not encoder.resident and not encoder.calls)
        for label,scope,root in (('A',a,roots[0]),('B',b,roots[1])):
            api('/api/library/ai/index',{'scope':scope});ai.worker.join(90)
            check(label+' two scoped CUDA works indexed',not ai.worker.is_alive() and ai.status()['state']=='complete' and ai.status()['indexed']==2 and encoder.device=='cuda')
            result=api('/api/library/ai/search',{'scope':scope,'query':'デザイン素材の画像','source':'text'})
            check(label+' query cannot escape selected root',{row['id'] for row in result['items']}==ids[root] and result['total']==2)
            check(label+' scoped freshness counts',api('/api/library/ai/coverage',{'scope':scope})['remaining_total']==0)
        before=vector_digest(ai);documents=encoder.calls['document'];images_encoded=encoder.calls['image']
        api('/api/library/ai/index',{'scope':a});ai.worker.join(20)
        check('A cache rebuild has no new document or cover inference',encoder.calls['document']==documents==4 and encoder.calls['image']==images_encoded==4)
        check('all vectors retained after scope switch',vector_digest(ai)==before and (ai.profile.key,ai.store.path)==(key,path))
        result=api('/api/library/ai/search',{'scope':a,'query':'青い素材','source':'cover'})
        check('actual scoped cover query',{row['id'] for row in result['items']}==ids[roots[0]] and encoder.device=='cuda')
        server.shutdown();server.server_close();server=None;http_thread.join(5);http_thread=None
        ai.close()
        check('owned CUDA process instances stopped',len(encoder.observed_exits)>=2 and all(row['stopped'] for row in encoder.observed_exits))
        restarted_encoder=MeasuredEncoder();restart=AISearch(catalog,restarted_encoder)
        check('job scope survives restart',restart.status()['scope']=={'root_ids':[roots[0]],'kind':'image','shelf':'素材'})
        check('restart counts use saved cache without GPU',restart.coverage(a)['fresh_total']==2 and not restarted_encoder.resident)
        restart.start(scope=a);restart.worker.join(20)
        check('restart scoped rebuild does not load worker',restart.status()['state']=='complete' and restart.status()['indexed']==2 and not restarted_encoder.calls and not restarted_encoder.resident)
        report['calls']=dict(encoder.calls);report['owned_exits']=encoder.observed_exits
        report['pass']=True
    except Exception as error:
        report['error']=str(error)
    finally:
        if server:server.shutdown();server.server_close()
        if http_thread:http_thread.join(5)
        try:
            if restart:restart.close()
            ai.close()
        except Exception as error:report['pass']=False;report['cleanup_error']=str(error)
        catalog.close()
        report['source_hashes_unchanged']=sources==[source_digest(folder) for folder in folders]
        if not report['source_hashes_unchanged']:report['pass']=False
        (target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['pass'] else 1


if __name__=='__main__':raise SystemExit(main())
