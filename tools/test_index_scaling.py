"""CPU-only, generated-source index plumbing measurement. No model quality claim."""
import argparse
import ctypes
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch, MAX_ITEMS, PROGRESS_INTERVAL, ROW_BATCH_SIZE
from production import ProductionCatalog

class SyntheticEncoder:
    available=True
    device='synthetic-cpu-only'
    profile=replace(DEFAULT_PROFILE,model_id='aredoko/synthetic-scaling-fixture',
                    label='Synthetic scaling fixture',modalities=('text',))
    def __init__(self):self.documents=0;self.on_document=None
    def encode(self,operation,value):
        if operation=='document':
            self.documents+=1
            if self.on_document:self.on_document(self.documents)
        axis=0 if operation=='query' or 'scale-target' in str(value) else 1
        vector=[0.0]*self.profile.dimension;vector[axis]=1.0
        return vector
    def close(self):pass

def source_digest(media):
    digest=hashlib.sha256()
    for path in sorted(media.glob('*.wav')):
        digest.update(path.name.encode());digest.update(path.read_bytes())
        stat=path.stat();digest.update(f'{stat.st_size}:{stat.st_mtime_ns}'.encode())
    return digest.hexdigest()

def peak_working_set():
    if sys.platform!='win32':return None
    class Counters(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong),
                  *[(name,ctypes.c_size_t) for name in ('PeakWorkingSetSize','WorkingSetSize',
                  'QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage',
                  'QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]]
    data=Counters();data.cb=ctypes.sizeof(data)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype=ctypes.c_void_p
    psapi=ctypes.WinDLL('psapi',use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.POINTER(Counters),ctypes.c_ulong]
    return data.PeakWorkingSetSize if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(data),data.cb) else None

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True,help='New evidence folder; existing folders are refused')
    args=parser.parse_args()
    if args.output.exists():parser.error('Use a fresh output folder')
    args.output.mkdir(parents=True)
    media=args.output/'generated';media.mkdir()
    checks=[];timings={};catalog=None;ai=None
    def check(name,condition):
        checks.append({'name':name,'pass':bool(condition)})
        if not condition:raise AssertionError(name)
    result={'actual_model':False,'gpu_used':False,'native_gui_run':False,
            'vector_dimension':SyntheticEncoder.profile.dimension,'modalities':['text'],
            'coverage_limit':MAX_ITEMS,'row_batch_size':ROW_BATCH_SIZE,'progress_interval':PROGRESS_INTERVAL,
            'source_count':MAX_ITEMS+10,'checks':checks,'seconds':timings,'pass':False}
    def build(name):
        started=time.perf_counter();ai.start();timings[name+'_start']=time.perf_counter()-started
        ai.worker.join(300)
        check(name+'_worker_stopped',not ai.worker.is_alive())
        timings[name+'_total']=time.perf_counter()-started
        return ai.status()
    try:
        started=time.perf_counter()
        for i in range(MAX_ITEMS+10):
            (media/f'{i:05d}.wav').write_bytes(b'Generated metadata fixture; not playable audio.')
        original=source_digest(media);timings['generate_and_hash']=time.perf_counter()-started
        catalog=ProductionCatalog(args.output/'catalog.sqlite')
        root=catalog.add_root(str(media.resolve()))
        started=time.perf_counter();catalog.start_scan(root);catalog._worker.join(120)
        timings['scan']=time.perf_counter()-started
        check('scan_complete',not catalog._worker.is_alive() and catalog.scan_state()['state']=='complete')
        check('literal_includes_all_generated_sources',catalog.search()['total']==MAX_ITEMS+10)
        encoder=SyntheticEncoder();ai=AISearch(catalog,encoder)
        rows=ai._rows();check('eligible_cap',len(rows)==MAX_ITEMS)
        target=rows[-1]['id'];del rows
        catalog.update([target],{'tags':['scale-target'],'favorite':True})
        encoder.on_document=lambda count:ai.cancel_build() if count==2300 else None
        state=build('cancelled_build')
        check('cancel_after_legacy_limit',state['state']=='cancelled' and state['processed']==2300 and state['indexed']==2300)
        result['cancelled_state']={key:state[key] for key in ('state','processed','total','indexed','skipped')}
        ai.close();encoder=SyntheticEncoder();ai=AISearch(catalog,encoder)
        state=build('resume_build')
        check('resumed_all_10000',state['state']=='complete' and state['indexed']==MAX_ITEMS and state['skipped']==0)
        check('resume_encodes_only_remaining',encoder.documents==MAX_ITEMS-2300)
        result['resume_document_calls']=encoder.documents
        started=time.perf_counter();found=ai.search('scale-target');timings['search']=time.perf_counter()-started
        check('last_eligible_target_ranks_first',found['total']==MAX_ITEMS and found['items'][0]['id']==target)
        check('search_contract_and_paging',found['coverage_limit']==MAX_ITEMS and len(found['items'])==60 and len(ai.search('scale-target',page=166)['items'])==40)
        check('favorite_filter',ai.search('scale-target',view='favorites')['total']==1)
        ai.close();encoder=SyntheticEncoder();ai=AISearch(catalog,encoder)
        state=build('cache_reuse')
        check('reopened_cache_no_document_inference',state['state']=='complete' and state['indexed']==MAX_ITEMS and encoder.documents==0)
        check('source_bytes_size_mtime_unchanged',source_digest(media)==original)
        result['final_state']={key:state[key] for key in ('state','processed','total','indexed','skipped')}
        result['pass']=True
    except Exception as ex:
        result['error']=type(ex).__name__+': '+str(ex)
    finally:
        if ai:ai.close()
        if catalog:catalog.close()
        result['peak_process_working_set_bytes']=peak_working_set()
        (args.output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=True))
    return 0 if result['pass'] else 1

if __name__=='__main__':raise SystemExit(main())
