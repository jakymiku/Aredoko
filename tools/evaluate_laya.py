"""Offline evaluation on frozen synthetic Japanese requests and generated media."""
import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from laya_config import model_path, IDENTITY
from laya_process import LayaProcess
from search_intent import SearchIntent, QUESTIONS
from production import ProductionCatalog
from ai_process import EncoderProcess
from ai_search import AISearch
from create_preview_fixture import create

def process_memory(pid):
    if os.name!='nt':return {'available':False}
    class Counters(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in (
            'PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
            'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong]
    kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    psapi=ctypes.WinDLL('psapi',use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.POINTER(Counters),ctypes.c_ulong]
    handle=kernel.OpenProcess(0x0410,False,pid)
    if not handle:return {'available':False}
    try:
        counters=Counters();counters.cb=ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(handle,ctypes.byref(counters),counters.cb):return {'available':False}
        return {'available':True,'private_mib':round(counters.PrivateUsage/1024**2,2),
                'working_set_mib':round(counters.WorkingSetSize/1024**2,2),
                'peak_working_set_mib':round(counters.PeakWorkingSetSize/1024**2,2)}
    finally:kernel.CloseHandle(handle)

def metrics(rows):
    total=len(rows)
    return {'count':total,'intent_correct':sum(r['intent_correct'] for r in rows),
            'kind_correct':sum(r['kind_correct'] for r in rows),
            'both_correct':sum(r['intent_correct'] and r['kind_correct'] for r in rows),
            'unavailable':sum(r['state']!='suggested' for r in rows)}

def compare_retrieval(target,service):
    media=create(target/'media')
    (media/'雨の夜の街並み.wav').write_bytes(b'generated filename-only placeholder')
    (media/'晴れた昼の海辺.wav').write_bytes(b'generated filename-only placeholder')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in media.iterdir()}
    catalog=ProductionCatalog(target/'catalog.sqlite')
    ai=AISearch(catalog,EncoderProcess(REPO/'.venv-ai/Scripts/python.exe',REPO/'models/embeddinggemma-2'))
    try:
        root=catalog.add_root(str(media));catalog.start_scan(root);catalog._worker.join(15)
        if catalog._worker.is_alive():raise RuntimeError('Fixture scan timeout')
        ai.start();ai.worker.join(240)
        if ai.worker.is_alive() or ai.status()['state']!='complete':raise RuntimeError('Fixture index failed')
        cases=[('青い画像','image','cover','image-01.png'),('赤い表紙の本','book','cover','book-03.cbz'),
               ('青い表紙の本','book','cover','book-01.cbz'),
               ('傘が必要な暗い都会の景色','audio','text','雨の夜の街並み.wav'),
               ('雨の夜の街並みという名前の音源','audio','text','雨の夜の街並み.wav'),
               ('晴れた昼の海辺という名前の音源','audio','text','晴れた昼の海辺.wav')]
        comparisons=[]
        for query,kind,manual,expected in cases:
            suggestion=service.suggest(query,kind=kind)
            suggested=suggestion['suggestion']['source'] if suggestion['suggestion'] else 'all'
            row={'query':query,'explicit_kind':kind,'expected':expected,'suggested_source':suggested}
            # Apply source ONLY in this controlled experiment, never guessed kind.
            for label,source in [('mixed','all'),('manual',manual),('laya_experiment',suggested)]:
                hits=ai.search(query,kind=kind,source=source)['items']
                titles=[r['title'] for r in hits]
                row[label]={'top':titles[:3],'expected_rank':titles.index(expected)+1 if expected in titles else None}
            comparisons.append(row)
        if hashes!={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in media.iterdir()}:
            raise RuntimeError('Generated sources changed')
        return {'cases':comparisons,'source_hashes_unchanged':True,'records':ai.status()['indexed']}
    finally:ai.close();catalog.close()

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path,help='New directory for generated evidence only')
    args=parser.parse_args()
    target=args.output.resolve();target.mkdir(parents=True,exist_ok=False)
    fixture=REPO/'tests/fixtures/laya-ja-queries.json'
    examples=json.loads(fixture.read_text(encoding='utf-8'))
    provider=LayaProcess(REPO/'.venv-ai/Scripts/python.exe',model_path(REPO))
    service=SearchIntent(provider)
    report={'identity':IDENTITY,'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),
            'questions':QUESTIONS,'manual_search_unchanged':True,'rows':[]}
    try:
        latencies=[]
        for index,row in enumerate(examples):
            start=time.perf_counter();result=service.suggest(row['query'])
            duration=round((time.perf_counter()-start)*1000,2)
            if index:latencies.append(duration)
            else:report['cold_request_ms']=duration
            suggestion=result['suggestion'] or {}
            report['rows'].append({**row,**result,'elapsed_ms':duration,
                'intent_correct':suggestion.get('intent')==row['intent'],
                'kind_correct':suggestion.get('kind')==row['kind']})
        report['metrics']={split:metrics([r for r in report['rows'] if r['split']==split])
                           for split in ('development','held-out')}
        report['telemetry']=dict(provider.telemetry)
        report['memory']=process_memory(provider.worker_pid) if provider.worker_pid else {'available':False}
        report['warm_latency_ms']={'median':statistics.median(latencies),
            'p95':sorted(latencies)[math.ceil(len(latencies)*0.95)-1]}
        report['confusions']=[{'id':r['id'],'query':r['query'],'expected':[r['intent'],r['kind']],
                              'actual':[r['suggestion']['intent'],r['suggestion']['kind']] if r['suggestion'] else None}
                             for r in report['rows'] if not(r['intent_correct'] and r['kind_correct'])]
        report['runtime_pass']=all(r['state']=='suggested' for r in report['rows'])
        report['retrieval']=compare_retrieval(target,service) if report['runtime_pass'] else {'skipped':'Decision runtime failed'}
        print(json.dumps({k:report[k] for k in ('metrics','warm_latency_ms','cold_request_ms','memory','telemetry','confusions','retrieval')},ensure_ascii=False),flush=True)
    finally:
        service.close()
        report['owned_worker_stopped']=provider.process is None
        (target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

    if not report.get('runtime_pass'):raise SystemExit('Laya runtime failed; see result.json')

if __name__=='__main__':main()
