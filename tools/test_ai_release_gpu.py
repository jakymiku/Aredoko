"""Offline CUDA release/reload regression on a fresh generated 17-item library.

Existing project runtime and weights only. No arbitrary roots or downloads.
Observe only process-instance handles obtained from this test's owned encoder.
"""
import argparse
import ctypes
from ctypes import wintypes
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from ai_process import EncoderProcess
from ai_search import AISearch
from ai_settings import AIProfileSettings
from production import ProductionCatalog
from production_server import production_handler
from create_preview_fixture import create
from test_index_gpu_scaling import MeasuredEncoder,source_digest
from test_index_gpu_api import vector_digest


class ReleaseEncoder(MeasuredEncoder):
    def encode(self,operation,value):
        # The fixture deliberately includes a damaged PNG. The production
        # decoder returns None; the scaling harness expects only valid PNGs.
        if operation=='image' and value[:8]!=b'\x89PNG\r\n\x1a\n':
            vector=EncoderProcess.encode(self,operation,value)
            if vector is not None:raise RuntimeError('Damaged generated image must be skipped')
            self.calls['invalid_image_skipped']+=1
            return vector
        return super().encode(operation,value)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); target=args.output.resolve()
    if os.name!='nt' or not target.is_relative_to((REPO/'data/ai-ui').resolve()):
        parser.error('Fresh output inside data/ai-ui on Windows required')
    target.mkdir(parents=True,exist_ok=False)
    media=create(target/'generated')
    for name in ('雨の夜の街並み.wav','晴れた昼の公園.wav'):
        (media/name).write_bytes(b'generated metadata fixture')
    sources=source_digest(media)
    catalog=ProductionCatalog(target/'catalog.sqlite')
    encoder=ReleaseEncoder(); ai=AISearch(catalog,encoder)
    server=None; http_thread=None; query_thread=None; gate=threading.Event()
    report={'pass':False,'actual_model':True,'native_gui_run':False,
            'generated_sources_only':True,'checks':[],'queries':[]}
    def check(name,condition):
        report['checks'].append({'name':name,'pass':bool(condition)})
        print(json.dumps({'check':name,'pass':bool(condition)}),flush=True)
        if not condition:raise RuntimeError(name)
    def stopped(handles,label):
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        observed=[{'pid':pid,'stopped':kernel.WaitForSingleObject(handle,10000)==0}
                  for pid,handle in handles.items()]
        report.setdefault('released_instances',[]).append({'label':label,'instances':observed})
        check(label+' owned launcher and worker exit',len(observed)>=2 and all(r['stopped'] for r in observed))
    try:
        root=catalog.add_root(str(media));catalog.start_scan(root);catalog._worker.join(30)
        check('generated scan 17',catalog.search()['total']==17)
        settings=AIProfileSettings(REPO,target/'settings.json');token=secrets.token_urlsafe(32)
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(catalog,token,ai=ai,profiles=settings))
        http_thread=threading.Thread(target=server.serve_forever,daemon=True);http_thread.start()
        origin=f'http://127.0.0.1:{server.server_port}'
        def api(route,body=None,expected=200):
            request=urllib.request.Request(origin+route,None if body is None else json.dumps(body).encode(),
                       {'Origin':origin,'X-Aredoko-Token':token,'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(request,timeout=180) as response:payload=json.load(response);code=response.status
            except urllib.error.HTTPError as ex:
                with ex:payload=json.load(ex);code=ex.code
            check(route+' HTTP '+str(expected),code==expected)
            return payload
        def search(label):
            started=time.perf_counter()
            result=api('/api/library/ai/search',{'query':'傘が必要な暗い都会の景色','source':'text'})
            report['queries'].append({'label':label,'seconds':time.perf_counter()-started})
            check(label+' actual CUDA and 17 results',ai.status()['device']=='cuda' and result['total']==17)
            return [r['id'] for r in result['items']]
        api('/api/library/ai/index',{})
        ai.worker.join(180)
        state=ai.status();report['indexed_state']=state
        check('actual CUDA index completed',state['state']=='complete' and state['indexed']==17 and state['device']=='cuda')
        vectors=vector_digest(ai);profile=ai.profile.key
        calls=dict(encoder.calls);ids=search('before release');encoder.observe()
        first=encoder.process;handles=dict(encoder.handles)
        result=api('/api/library/ai/release',{})
        check('manual release response',result['released'] and not result['resident'])
        state=ai.status()
        check('unloaded status clears CUDA telemetry',not state['resident'] and state['device']=='' and state['telemetry']=={})
        stopped(handles,'manual')
        check('manual release keeps vectors and profile',vector_digest(ai)==vectors and ai.profile.key==profile)
        check('lazy reload preserves ordering',search('manual reload')==ids and encoder.process is not first)
        # Hold the production inference guard immediately before a real CUDA query.
        # This instruments overlap deterministically; it is not a GPU load benchmark.
        original=encoder.encode;entered=threading.Event();failures=[]
        def blocked(operation,value):
            if operation=='query':
                entered.set()
                if not gate.wait(15):raise TimeoutError('owned query gate')
            return original(operation,value)
        encoder.encode=blocked
        def query():
            try:search('overlapping query')
            except Exception as ex:failures.append(str(ex))
        query_thread=threading.Thread(target=query);query_thread.start()
        check('query guard held',entered.wait(5))
        started=time.perf_counter();api('/api/library/ai/release',{},expected=409)
        check('busy release leaves worker resident',time.perf_counter()-started<2 and encoder.resident)
        gate.set();query_thread.join(30);encoder.encode=original
        check('overlapping CUDA query completed',not query_thread.is_alive() and not failures)
        encoder.observe();handles={pid:h for pid,h in encoder.handles.items() if pid not in handles}
        api('/api/library/ai/resource',{'idle_release_seconds':1,'index_pause_ms':50})
        deadline=time.monotonic()+15
        while encoder.resident and time.monotonic()<deadline:time.sleep(.1)
        check('automatic idle release',not encoder.resident)
        stopped(handles,'automatic')
        check('settings persist independently of vectors',settings.resource()=={'idle_release_seconds':1,'index_pause_ms':50} and vector_digest(ai)==vectors)
        api('/api/library/ai/resource',{'idle_release_seconds':0,'index_pause_ms':0})
        check('reload after idle release',search('idle reload')==ids)
        check('reload never reindexes documents or covers',all(encoder.calls[op]==calls.get(op,0) for op in ('document','image')))
        check('sources and persisted vectors unchanged',source_digest(media)==sources and vector_digest(ai)==vectors)
        report['inference_calls']=dict(encoder.calls)
        report['peak_cuda_allocated_mib']=encoder.peak_cuda_allocated_mib
        report['pass']=True
    except Exception as ex:
        report['error']=str(ex)
    finally:
        gate.set()
        if query_thread:query_thread.join(30)
        if server:server.shutdown();server.server_close()
        if http_thread:http_thread.join(5)
        try:
            ai.close()
            report['final_owned_exits']=encoder.observed_exits
            check('all final owned process handles stopped',bool(encoder.observed_exits) and all(r['stopped'] for r in encoder.observed_exits))
        except Exception as ex:report['pass']=False;report['cleanup_error']=str(ex)
        catalog.close()
        report['source_hashes_unchanged']=source_digest(media)==sources
        if not report['source_hashes_unchanged']:report['pass']=False
        (target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))
    return 0 if report['pass'] else 1

if __name__=='__main__':raise SystemExit(main())
