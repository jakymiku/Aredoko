"""CPU-only smoke of an explicitly staged basic release, generated DB/media only.

Does not launch WinUI, bootstrap GUI, models, GPU, installers or normal user DB.
Full payload/ZIP verification belongs to the preparation step.
"""
import argparse,hashlib,json,os,queue,secrets,sqlite3,subprocess,sys,threading,time,traceback,urllib.request,zipfile
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
from create_preview_fixture import png
from release_runtime import runtime_environment
from storage_lease import plain_path,storage_parent


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--release',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--polish',action='store_true',help='Also check U4-U6 contracts on a current candidate');args=parser.parse_args()
    release=plain_path(args.release,directory=True);output=Path(os.path.abspath(args.output))
    if not (release.is_relative_to(REPO/'dist') or release.is_relative_to(REPO/'data/ai-ui')) or not output.is_relative_to(REPO/'data/ai-ui') or output.exists():parser.error('Explicit staged repository release and new dedicated evidence required')
    manifest=json.loads((release/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('ai_runtime_bundled') is not False or manifest.get('models_bundled') is not False:parser.error('Basic release only; never run an AI-bundled interpreter here')
    storage_parent(output);output.mkdir();report={'pass':False,'gui':False,'gpu':False,'normal_db_used':False,'checks':[]};proc=None
    def check(name,value):
        report['checks'].append({'name':name,'pass':bool(value)})
        if not value:raise AssertionError(name)
    env=runtime_environment(release/'runtime/media');env['LOCALAPPDATA']=str(output/'user');env['APPDATA']=str(output/'user')
    try:
        python=plain_path(release/'runtime/python/python.exe');server=plain_path(release/'backend/app/production_server.py')
        probe=subprocess.run([str(python),'-I','-B','-c',"import importlib.util,json,sys;print(json.dumps({'torch':importlib.util.find_spec('torch') is not None,'prefix':sys.prefix}))"],env=env,cwd=output,capture_output=True,text=True,encoding='utf-8',timeout=15,check=True)
        check('bundled isolated Python has no torch',json.loads(probe.stdout)['torch'] is False)
        media=output/'generated';media.mkdir();source=media/'generated.png';source.write_bytes(png(width=160,height=180,color=(45,130,160)))
        before=hashlib.sha256(source.read_bytes()).hexdigest(),source.stat().st_mtime_ns
        models=output/'models';models.mkdir();instance=secrets.token_hex(16)
        command=[str(python),'-I','-B','-c','import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_path(sys.argv.pop(1),run_name="__main__")',str(server.parent),str(server),'--db',str(output/'catalog.sqlite'),'--port','0','--instance-id',instance,'--exit-on-stdin-close','--ai-python',str(python),'--models-root',str(models),'--ai-settings',str(output/'ai-settings.json'),'--runtime-preferences',str(output/'launch-settings.json')]
        with (output/'backend.log').open('w',encoding='utf-8') as log:
            proc=subprocess.Popen(command,cwd=output,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,encoding='utf-8');report['owned_pid']=proc.pid
            lines=queue.Queue()
            def read():
                for line in proc.stdout:lines.put(line)
            reader=threading.Thread(target=read,daemon=True);reader.start();line=lines.get(timeout=20)
            if not line.startswith('Aredoko production: http://127.0.0.1:'):raise RuntimeError('Unexpected owned startup')
            origin=line.split('production: ',1)[1].strip();opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));token=None
            def request(path,body=None,binary=False):
                headers={'Origin':origin,'Content-Type':'application/json'}
                if token:headers['X-Aredoko-Token']=token
                req=urllib.request.Request(origin+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
                with opener.open(req,timeout=5) as response:return response.read() if binary else json.load(response)
            session=request('/api/session');token=session['token'];check('actual bundled backend production instance',session['mode']=='production' and session['instance_id']==instance)
            setup=request('/api/library/ai/setup');check('AI missing stays distinct from inference',not setup['inference_verified'])
            # Read only the staged source-owned registry with the sealed basic
            # interpreter. Listing metadata never starts acquisition/inference.
            registry_code = "import json,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from ai_acquisition_registry import load_trusted_specs;from ai_download_jobs import AIDownloadJobs;j=AIDownloadJobs(Path(sys.argv[3]),specifications=load_trusted_specs(Path(sys.argv[2])));print(json.dumps(j.catalogs()));j.close()"
            registry=subprocess.run([str(python),'-I','-B','-c',registry_code,str(server.parent),str(server.parent.parent),str(output/'unused-acquisition')],
                                    env=env,cwd=output,capture_output=True,text=True,encoding='utf-8',timeout=15,check=True)
            expected_catalogs=json.loads(registry.stdout)
            catalogs=request('/api/library/ai/setup/download/catalog')
            check('production catalog matches staged pinned registry',catalogs==expected_catalogs and setup['downloads_supported']==expected_catalogs['download_supported'])
            report['catalog_count']=len(catalogs['catalogs'])
            report['catalog_fingerprints']=[entry['catalog_id'] for entry in catalogs['catalogs']]
            check('setup and acquisition owners idle',request('/api/library/ai/setup/job')['state']=='idle' and request('/api/library/ai/setup/download/job')['state']=='idle')
            root=request('/api/library/roots',{'consent':True,'path':str(media),'recursive':True})['root_id'];request('/api/library/scan',{'root_id':root})
            deadline=time.monotonic()+12
            while request('/api/library/scan')['state']=='running' and time.monotonic()<deadline:time.sleep(.05)
            check('generated-only scan completes',request('/api/library/scan')['state']=='complete')
            items=request('/api/items?q=generated.png')['items'];check('filename search returns generated image',len(items)==1)
            preview=request('/api/library/preview/'+str(items[0]['id']),binary=True);check('actual bundled preview produces PNG',preview.startswith(b'\x89PNG\r\n\x1a\n'))
            if args.polish:
                report['polish']=True
                check('runtime verification defaults on without AI assets',setup['verify_ai_runtime'] is True)
                saved=request('/api/library/ai/runtime-verification',{'enabled':False})
                check('bundled advanced preference saves for next startup',saved['verify_ai_runtime'] is False and saved['active_verify_ai_runtime'] is True and saved['restart_required'])
                request('/api/library/roots/startup-scan',{'root_ids':[root],'mode':'list'})
                check('startup preference saves without implicit scanning',request('/api/library/roots')['items'][0]['startup_scan']=='list' and request('/api/library/startup-scan')['state']=='idle')
                for name in ('generated.zip','generated.CBZ'):
                    with zipfile.ZipFile(media/name,'w') as archive:archive.writestr('1.png',source.read_bytes())
                def scan():
                    request('/api/library/scan',{'root_id':root,'mode':'list'});deadline=time.monotonic()+12
                    while request('/api/library/scan')['state']=='running' and time.monotonic()<deadline:time.sleep(.05)
                    check('explicit list scan completes without AI',request('/api/library/scan')['state']=='complete' and request('/api/library/scan')['ai_state']=='none')
                scan();compressed=request('/api/items?kind=compressed')['items'];ids=[item['id'] for item in compressed]
                check('bundled compressed filter finds ZIP and uppercase CBZ',len(ids)==2 and {item['kind'] for item in compressed}=={'book','archive'})
                check('legacy ZIP and book filters remain distinct',request('/api/items?kind=archive')['total']==1 and request('/api/items?kind=book')['total']==1)
                def create():
                    sid=secrets.token_hex(16);request('/api/library/results/create',{'session_id':sid,'conditions':{'mode':'literal','query':'','kind':'compressed','view':'all','root_ids':[root]}});return sid
                sid=create();result=request('/api/library/results/edit',{'session_id':sid,'item_ids':ids,'operation':'favorite_add','shelf_ids':[]})
                check('bundled atomic favorite edit covers the frozen selection',result['updated']==2 and request('/api/items?kind=compressed&view=favorites')['total']==2)
                request('/api/library/results/close',{'session_id':sid})
                shelf=request('/api/library/shelves/create',{'name':'生成テスト棚'})['id']
                sid=create()
                result=request('/api/library/results/edit',{'session_id':sid,'item_ids':ids,'operation':'shelves_add','shelf_ids':[shelf]})
                check('bundled shelf edit preserves confirmed memberships',result['updated']==2 and all(item['shelf_ids']==[shelf] for item in request('/api/items?kind=compressed')['items']))
                request('/api/library/results/close',{'session_id':sid})
                (media/'generated.zip').unlink();scan()
                check('confirmed missing item leaves ordinary and favorite results',request('/api/items?kind=compressed')['total']==1 and request('/api/items?kind=compressed&view=favorites')['total']==1)
            check('generated source SHA and mtime preserved',before==(hashlib.sha256(source.read_bytes()).hexdigest(),source.stat().st_mtime_ns))
            proc.stdin.close();proc.wait(timeout=15);reader.join(3);check('owned EOF shutdown exits zero',proc.returncode==0)
        with sqlite3.connect(output/'catalog.sqlite') as db:
            check('generated DB integrity',db.execute('PRAGMA integrity_check').fetchone()[0]=='ok')
            if args.polish:
                check('catalog v3 startup preference survives normal EOF shutdown',db.execute('PRAGMA user_version').fetchone()[0]==3 and db.execute('SELECT startup_scan FROM registered_root_preferences WHERE root_id=?',(root,)).fetchone()[0]=='list')
                check('missing metadata is retained for recovery',db.execute("SELECT count(*) FROM item_locations m JOIN library_locations l ON l.id=m.location_id JOIN items i ON i.id=m.item_id JOIN item_shelves s ON s.item_id=i.id WHERE l.status='missing' AND i.favorite=1 AND s.shelf_id=?",(shelf,)).fetchone()[0]==1)
        report['pass']=True
    except Exception:report['error']=traceback.format_exc()
    finally:
        if proc is not None and proc.poll() is None:
            if proc.stdin and not proc.stdin.closed:proc.stdin.close()
            try:proc.wait(timeout=15)
            except subprocess.TimeoutExpired:report['cleanup_pending']=True
        if proc is not None:
            report['exit_code']=proc.poll()
            if proc.stdout:proc.stdout.close()
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));return 0 if report['pass'] and not report.get('cleanup_pending') else 1

if __name__=='__main__':raise SystemExit(main())
