"""Generated-only WD CPU runtime/API smoke; never a tagging quality benchmark."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import zipfile

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from production import ProductionCatalog
from production_server import production_handler,DisabledAI
from wd_tagger import create_tagger
from create_preview_fixture import png


def digest(directory):
    return {p.name:(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns)
            for p in directory.iterdir() if p.is_file()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    output=args.output.resolve()
    allowed=(REPO/'data/ai-ui').resolve()
    if os.name!='nt' or not output.is_relative_to(allowed) or output==allowed:
        parser.error('Fresh generated output below project data/ai-ui required')
    tagger=create_tagger()
    if not tagger.status()['available']:parser.error('Approved local model/runtime setup required; this tool never downloads')
    output.mkdir(parents=True,exist_ok=False)
    media=output/'generated';media.mkdir()
    (media/'red-shapes.png').write_bytes(png(180,240,(180,40,30)))
    (media/'blue-shapes.png').write_bytes(png(240,180,(30,60,180)))
    with zipfile.ZipFile(media/'fiction.cbz','w') as archive:
        archive.writestr('10.png',png(color=(140,40,40)))
        archive.writestr('2.png',png(color=(40,140,40)))
    (media/'broken.png').write_bytes(b'not an image; generated corruption test')
    before=digest(media)
    profile=tagger.profile
    model_dir=profile.verify(REPO,hashes=True)
    model_before={name:(model_dir/name).stat().st_mtime_ns for name in profile.data()['artifacts']}
    catalog=server=thread=None
    checks=[];processes=[]
    report={'runtime_pass':False,'generated_only':True,'quality_measured':False,
            'device':'cpu','profile_key':profile.key,'cases':[]}
    def check(value,label):
        if not value:raise RuntimeError(label)
        checks.append(label)
    real_popen=subprocess.Popen
    def observe(*args,**kwargs):
        process=real_popen(*args,**kwargs);processes.append(process);return process
    try:
        catalog=ProductionCatalog(output/'catalog.sqlite')
        root=catalog.add_root(str(media));catalog.index.scan(root);catalog.sync_index()
        rows={r['title']:r for r in catalog.search()['items']}
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(catalog,'generated-token',ai=DisabledAI(),tagger=tagger))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def request(path,body=None):
            data=json.dumps(body).encode() if body is not None else None
            req=urllib.request.Request(url+path,data=data,headers={'Origin':url,'X-Aredoko-Token':'generated-token'})
            try:
                with opener.open(req,timeout=100) as response:return response.status,json.load(response)
            except urllib.error.HTTPError as error:
                with error:return error.code,json.load(error)
        route='/api/library/tag-suggestions'
        with patch('wd_tagger.subprocess.Popen',side_effect=observe):
            for name in ('red-shapes.png','blue-shapes.png','fiction.cbz'):
                item=rows[name]['id'];catalog.update([item],{'tags':['manual-fixture'],'shelf':'fixture-shelf','favorite':True})
                started=time.perf_counter()
                status,result=request(route+'/generate',{'item_id':item,'request_id':uuid.uuid4().hex})
                elapsed=round((time.perf_counter()-started)*1000,3)
                check(status==200,name+' generation HTTP200')
                batch=result['batch'];proposals=batch['proposals']
                check(not result['reused'] and batch['producer']['model_revision']==profile.data()['revision'],name+' provenance')
                check(len(proposals)<=30 and all(p['state']=='pending' and p['page']==0 for p in proposals),name+' pending bound')
                check(catalog.get(item)['tags']==['manual-fixture'],name+' no automatic tags')
                previous=len(processes)
                status,reused=request(route+'/generate',{'item_id':item,'request_id':uuid.uuid4().hex})
                check(status==200 and reused['reused'] and reused['batch']['id']==batch['id'] and len(processes)==previous,name+' idempotent no worker')
                if proposals:
                    payload={'item_id':item,'proposal_id':proposals[0]['id'],'version':0,'decision':'accept','tag':'runtime-approved-fixture'}
                    check(request(route+'/review',payload)[0]==200,name+' approval')
                    check(request(route+'/review',payload)[0]==409,name+' duplicate approval rejected')
                    check(catalog.get(item)['tags']==['manual-fixture','runtime-approved-fixture'],name+' manual union')
                    if len(proposals)>1:
                        payload={'item_id':item,'proposal_id':proposals[1]['id'],'version':0,'decision':'reject'}
                        check(request(route+'/review',payload)[0]==200,name+' reject after first approval')
                status,history=request(route+'/'+str(item))
                check(status==200 and not history['batches'][0]['stale'],name+' physical revision stable after tags')
                current=catalog.get(item)
                check(current['shelf']=='fixture-shelf' and current['favorite'],name+' metadata preserved')
                report['cases'].append({'fixture':name,'elapsed_ms':elapsed,'candidate_count':len(proposals),
                                        'sample_labels':[p['tag'] for p in proposals[:5]]})
            item=rows['broken.png']['id']
            check(request(route+'/generate',{'item_id':item,'request_id':uuid.uuid4().hex})[0]==503,'corrupt image explicit failure')
            check(request(route+'/'+str(item))[1]['batches']==[],'corrupt image no partial batch')
        report['runtime_pass']=True
    except Exception as error:
        report['error']=type(error).__name__+': '+str(error)
    finally:
        if server:server.shutdown();server.server_close()
        if thread:thread.join(5)
        tagger.close()
        if catalog:catalog.close()
        report['source_unchanged']=digest(media)==before
        profile.verify(REPO,hashes=True)
        report['model_unchanged']=model_before=={name:(model_dir/name).stat().st_mtime_ns for name in profile.data()['artifacts']}
        report['owned_workers']=len(processes)
        report['all_workers_stopped']=all(p.poll() is not None and p.stdin.closed and p.stdout.closed for p in processes)
        report['checks']=checks
        report['runtime_pass']=bool(report['runtime_pass'] and report['source_unchanged'] and report['model_unchanged'] and report['all_workers_stopped'])
        (output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('runtime_pass','quality_measured','source_unchanged','model_unchanged','owned_workers','all_workers_stopped')},ensure_ascii=False))
    return 0 if report['runtime_pass'] else 1


if __name__=='__main__':raise SystemExit(main())
