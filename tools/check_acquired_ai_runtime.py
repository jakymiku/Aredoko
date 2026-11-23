"""Explicit acquired-model smoke: two generated images, one call per model.

Requires human-approved GPU/CPU use. No network, normal settings, or GUI.
"""
import argparse,hashlib,json,math,os,sqlite3,subprocess,sys,time,traceback
from pathlib import Path
from unittest.mock import patch
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'app'),str(REPO/'tools')]
from ai_process import EncoderProcess
from ai_profiles import DEFAULT_PROFILE
from wd_tagger import create_tagger
from tagger_profile import load_profile
from runtime_paths import bind_runtime,verify_runtime_pack,runtime_verification_status
from ai_runtime import MARKER
from production import ProductionCatalog
from create_preview_fixture import png


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('runtime','embedding-root','tagger-root','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--consent-gpu-cpu',action='store_true')
    p.add_argument('--existing-repository-models',action='store_true',help='Also allow the exact repository models root; never scan other model directories')
    a=p.parse_args()
    if not a.consent_gpu_cpu:p.error('Explicit GPU/CPU authorization required')
    roots=[x.resolve() for x in (a.runtime,a.embedding_root,a.tagger_root,a.output)]
    runtime,embedding,tagger_root,out=roots
    allowed=(REPO/'data/ai-ui').resolve()
    model_base=(REPO/'models').resolve()
    if (any(not x.is_relative_to(allowed) or x==allowed for x in (runtime,out))
        or any(not x.is_relative_to(allowed) and not (a.existing_repository_models and x==model_base) for x in (embedding,tagger_root))
        or out.exists()):p.error('Dedicated runtime/output and explicit existing model roots required')
    if any(out.is_relative_to(x) or x.is_relative_to(out) for x in roots[:3]):p.error('Output overlaps inputs')
    out.mkdir(parents=True);media=out/'generated';media.mkdir()
    for name,color in [('red.png',(185,35,35)),('blue.png',(35,55,185))]:(media/name).write_bytes(png(160,180,color))
    stamp=lambda path:(path.stat().st_size,path.stat().st_mtime_ns)
    selected=[runtime,DEFAULT_PROFILE.model_path(REPO,models_root=embedding),load_profile(REPO).directory(REPO,models_root=tagger_root)]
    input_files=[x for root in selected for x in root.rglob('*') if x.is_file()]
    before={str(x):stamp(x) for x in input_files}
    source={x.name:(hashlib.sha256(x.read_bytes()).hexdigest(),stamp(x)) for x in media.iterdir()}
    report={'pass':False,'generated_only':True,'gui':False,'network_requested':False,'normal_settings_used':False,'quality_measured':False,'checks':[]}
    encoder=None;tagger=None;workers=[];cat=None
    def check(name,value):
        report['checks'].append({'name':name,'pass':bool(value)});print(name,bool(value),flush=True)
        if not value:raise AssertionError(name)
    try:
        free=subprocess.run(['nvidia-smi','--id=0','--query-gpu=memory.free','--format=csv,noheader,nounits'],capture_output=True,text=True,check=True,timeout=15)
        if int(free.stdout.strip())<3072:raise RuntimeError('Less than 3 GiB free; defer before loading')
        os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',
            HF_HOME=str(out/'cache/hf'),HF_MODULES_CACHE=str(out/'cache/modules'),TORCH_HOME=str(out/'cache/torch'),CUDA_CACHE_PATH=str(out/'cache/cuda'))
        for name in ('TEMP','TMP','LOCALAPPDATA','APPDATA'):
            folder=out/('isolated-'+name.lower());folder.mkdir();os.environ[name]=str(folder)
        marker=hashlib.sha256((runtime/MARKER).read_bytes()).hexdigest();bind_runtime(runtime,marker)
        report['runtime_manifest_sha256']=marker
        deadline=time.monotonic()+600;start=time.monotonic()
        verify_runtime_pack(runtime/'python.exe',cancelled=lambda:time.monotonic()>deadline)
        report['runtime_verification_seconds']=round(time.monotonic()-start,3)
        report['runtime_verification']=runtime_verification_status(runtime/'python.exe')
        cat=ProductionCatalog(out/'catalog.sqlite');root=cat.add_root(str(media));cat.index.scan(root);cat.sync_index()
        check('dedicated DB contains only two generated images',len(cat.search()['items'])==2)
        encoder=EncoderProcess(runtime/'python.exe',DEFAULT_PROFILE.model_path(REPO,models_root=embedding),gpu_budget_mib=3072)
        start=time.monotonic();vector=encoder.encode('image',(media/'red.png').read_bytes())
        if encoder.process:workers.append(encoder.process)
        report['embedding']={'device':encoder.device,'dimension':len(vector) if vector else 0,'elapsed_seconds':round(time.monotonic()-start,3),'telemetry':encoder.telemetry,'profile':encoder.profile.key,'allocator_budget_mib':encoder.gpu_budget_mib}
        check('acquired embedding runs on CUDA with finite normalized 768D',encoder.device=='cuda' and vector is not None and len(vector)==768 and all(math.isfinite(x) for x in vector) and abs(sum(x*x for x in vector)-1)<1e-4)
        encoder.close();encoder=None
        tagger=create_tagger(repo=REPO,ai_python=runtime/'python.exe',models_root=tagger_root)
        check('acquired WD model and sealed runtime report prepared',tagger.status()['available'])
        original=subprocess.Popen
        def observe(*args,**kwargs):
            child=original(*args,**kwargs);workers.append(child);return child
        start=time.monotonic()
        with patch('wd_tagger.subprocess.Popen',side_effect=observe):proposals=tagger.suggest({'data':(media/'blue.png').read_bytes()},lambda:False)
        report['tagger']={'device':'cpu','candidate_count':len(proposals),'elapsed_seconds':round(time.monotonic()-start,3)}
        check('acquired WD returns bounded candidates',len(proposals)<=30)
        report['pass']=True
    except Exception:report['error']=traceback.format_exc();print(report['error'],flush=True)
    finally:
        if encoder:encoder.close()
        if tagger:tagger.close()
        if cat:cat.close()
        report['owned_workers_stopped']=all(x.poll() is not None for x in workers)
        report['owned_worker_exits']=[x.poll() for x in workers]
        report['input_metadata_unchanged']=before=={str(x):stamp(x) for x in input_files}
        report['generated_sources_unchanged']=source=={x.name:(hashlib.sha256(x.read_bytes()).hexdigest(),stamp(x)) for x in media.iterdir()}
        with sqlite3.connect(out/'catalog.sqlite') as db:report['db_integrity']=db.execute('PRAGMA integrity_check').fetchone()[0]
        report['pass']=report['pass'] and report['owned_workers_stopped'] and report['input_metadata_unchanged'] and report['generated_sources_unchanged'] and report['db_integrity']=='ok'
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['pass'] else 1


if __name__=='__main__':raise SystemExit(main())
