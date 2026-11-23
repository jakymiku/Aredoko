"""Actual local HTTP concurrency/timeout/ownership checks; synthetic query only."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from production import ProductionCatalog
from production_server import production_handler,DisabledAI
from laya_process import LayaProcess
from laya_config import model_path
from search_intent import SearchIntent

def process_handle(pid):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong]
    kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    return kernel,kernel.OpenProcess(0x00100000,False,pid)

def stopped(kernel,handle):
    return not handle or kernel.WaitForSingleObject(handle,5000)==0

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if os.name!='nt':raise RuntimeError('Windows lifecycle check')
    target=args.output.resolve();target.mkdir(parents=True,exist_ok=False)
    catalog=ProductionCatalog(target/'catalog.sqlite')
    provider=LayaProcess(REPO/'.venv-ai/Scripts/python.exe',model_path(REPO),question_set='v2-hybrid',check_order=True)
    service=SearchIntent(provider)
    server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(catalog,'generated-token',DisabledAI(),service))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{server.server_port}'
    report={};handles=[]
    def post():
        headers={'Origin':origin,'X-Aredoko-Token':'generated-token','Content-Type':'application/json'}
        request=urllib.request.Request(origin+'/api/library/intent/suggest',
            json.dumps({'query':'青い画像','source':'text','kind':'audio'},ensure_ascii=False).encode('utf-8'),headers)
        with urllib.request.urlopen(request,timeout=75) as response:return json.load(response)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(post)
            deadline=time.monotonic()+5
            while provider.process is None and not pending.done() and time.monotonic()<deadline:time.sleep(0.02)
            if provider.process is None:raise RuntimeError('Cold worker did not start')
            started=time.perf_counter()
            with urllib.request.urlopen(origin+'/api/items',timeout=3) as response:
                if json.load(response)['total']!=0:raise RuntimeError('Unexpected fixture records')
            report['literal_during_cold_ms']=round((time.perf_counter()-started)*1000,2)
            if report['literal_during_cold_ms']>1000:raise RuntimeError('Literal request blocked by Laya')
            started=time.perf_counter();busy=post()
            report['busy_ms']=round((time.perf_counter()-started)*1000,2)
            if busy['state']!='unavailable' or report['busy_ms']>1000:raise RuntimeError('Busy request queued')
            first=pending.result(timeout=75)
        if first['state']!='suggested':raise RuntimeError('Actual Laya API failed')
        if not first['suggestion']['order_checked']:raise RuntimeError('Order evidence missing')
        if first['requested']!={'source':'text','kind':'audio'}:raise RuntimeError('Manual settings changed')
        if first['suggestion']['source']!='cover' or first['suggestion']['kind']!='image':
            raise RuntimeError('Generated smoke suggestion failed')
        report['suggestion']=first
        report['telemetry']=dict(provider.telemetry)
        kernel,handle=process_handle(provider.worker_pid);handles.append((kernel,handle))
        provider.warm_timeout=0.0001
        failed=post()
        if failed['state']!='unavailable' or provider.process is not None:raise RuntimeError('Timeout fallback failed')
        report['timeout_worker_stopped']=stopped(kernel,handle)
        if not report['timeout_worker_stopped']:raise RuntimeError('Real worker survived timeout')
        report['manual_after_timeout']=catalog.search()['total']==0
        if not report['manual_after_timeout']:raise RuntimeError('Literal catalog unavailable after timeout')
        # Abrupt OWNER exit, without finally/close, must also stop the real worker.
        code="""import json,os,sys
from pathlib import Path
repo=Path(sys.argv[1]);sys.path.insert(0,str(repo/'app'))
from laya_process import LayaProcess
from laya_config import model_path
p=LayaProcess(repo/'.venv-ai/Scripts/python.exe',model_path(repo),question_set='v2-hybrid',check_order=True)
p.decide('generated query')
print(json.dumps({'worker_pid':p.worker_pid}),flush=True)
os._exit(0)
"""
        env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
        helper=subprocess.Popen([sys.executable,'-u','-c',code,str(REPO)],stdout=subprocess.PIPE,
                                 text=True,encoding='utf-8',env=env,
                                 creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            line=helper.stdout.readline()
            worker_pid=json.loads(line)['worker_pid']
            kernel,handle=process_handle(worker_pid);handles.append((kernel,handle))
            helper.wait(timeout=5)
            report['abrupt_owner_worker_stopped']=stopped(kernel,handle)
            if not report['abrupt_owner_worker_stopped']:raise RuntimeError('Worker survived owner exit')
        finally:
            if helper.poll() is None:helper.kill();helper.wait(timeout=5)
            helper.stdout.close()
        report['pass']=True
        print(json.dumps(report,ensure_ascii=True),flush=True)
    finally:
        service.close();server.shutdown();server.server_close();catalog.close()
        for kernel,handle in handles:
            if handle:kernel.CloseHandle(handle)
        (target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
