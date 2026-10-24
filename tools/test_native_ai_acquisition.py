"""Bounded native acquisition workflow. Generated loopback bytes only; never model/runtime execution."""
import argparse,ctypes,hashlib,json,os,secrets,subprocess,sys,threading,time,traceback,urllib.request,struct
from ctypes import wintypes
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'app'),str(REPO/'tools'),str(REPO/'tests')]
from production import ProductionCatalog
from production_server import production_handler,DisabledAI
from ai_settings import AIProfileSettings
from wd_tagger import DisabledTagger
from create_preview_fixture import png
from native_ui_tools import nodes
from ai_acquisition import Catalog

def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace');sys.stderr.reconfigure(encoding='utf-8',errors='replace')
    parser=argparse.ArgumentParser();parser.add_argument('--frontend',type=Path,required=True);parser.add_argument('--attempt',type=int,choices=(1,2),required=True);parser.add_argument('--theme',choices=('light','dark'),default='dark');parser.add_argument('--published-selection',action='store_true',help='New feature: apply a generated valid published runtime without executing it');args=parser.parse_args()
    front=args.frontend.resolve();base=REPO/('data/ai-ui/ai-acquired-selection-20261024' if args.published_selection else 'data/ai-ui/ai-acquisition-20261024');target=base/f'run{args.attempt:02}'
    if os.name!='nt' or not (front.is_relative_to(REPO/'data/ai-ui') or front.is_relative_to(REPO/'dist')) or not (front/'Aredoko.WinUI.exe').is_file() or target.exists():parser.error('New bounded output and dedicated frontend required')
    target.mkdir(parents=True);report={'pass':False,'checks':[],'screenshots':[],'target':'local','visual_review':'pending','source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()}
    report['frontend_sha256']=hashlib.sha256((front/'Aredoko.WinUI.dll').read_bytes()).hexdigest()
    report['diff_sha256']=hashlib.sha256(subprocess.check_output(['git','diff','--','src','app'],cwd=REPO)).hexdigest()
    tracked=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','--','src','app'],cwd=REPO,text=True).splitlines()
    report['source_files']={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in tracked}
    report['frontend_sha256']=hashlib.sha256((front/'Aredoko.WinUI.dll').read_bytes()).hexdigest()
    env={**os.environ,'WINAPP_UI_WORKFLOW_ID':'aredoko-ai-acquired-selection-20261024' if args.published_selection else 'aredoko-ai-acquisition-20261024','LOCALAPPDATA':str(target/'user'),'APPDATA':str(target/'user')}
    user=ctypes.WinDLL('user32',use_last_error=True);user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)];user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    cat=server=thread=proc=artifact_server=artifact_thread=None;hwnd=None;original_popen=None;release=threading.Event();reached=threading.Event()
    def cli(*arguments):
        result=subprocess.run(['winapp','ui',*map(str,arguments)],cwd=REPO,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
        with (target/'commands.log').open('a',encoding='utf-8') as log:log.write(json.dumps({'args':list(map(str,arguments)),'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr},ensure_ascii=False)+'\n')
        if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        return result.stdout
    def ui(*arguments):
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
        if owner.value!=proc.pid:raise RuntimeError('Owned HWND changed')
        return cli(*arguments,'-w',hwnd)
    def check(name,value):
        report['checks'].append({'name':name,'pass':bool(value)});print(name,bool(value),flush=True)
        if not value:raise AssertionError(name)
    def wait(name,predicate):
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if predicate():check(name,True);return
            time.sleep(.1)
        check(name,False)
    def shot(name):
        path=target/(name+'.png');ui('screenshot','--focus','--output',path);report['screenshots'].append(str(path))
        payload=path.read_bytes()
        if payload[:8]!=b'\x89PNG\r\n\x1a\n' or len(payload)<24 or min(struct.unpack('>II',payload[16:24]))<100:raise RuntimeError('Screenshot is empty or too small; not visual acceptance')
        (target/(name+'.json')).write_text(ui('inspect','--depth','18','--json'),encoding='utf-8')
    def sources():return {str(p.relative_to(target)):[hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns] for directory in (media,generated) for p in directory.rglob('*') if p.is_file()}
    try:
        media=target/'media';media.mkdir();(media/'generated.png').write_bytes(png(width=160,height=180,color=(50,120,170)))
        generated=target/'generated-source';generated.mkdir();payload=b'aredoko-generated-byte-stream-'*50000;(generated/'fixture.bin').write_bytes(payload)
        models=target/'empty-models';models.mkdir();settings=target/'launch-settings.json';settings.write_text(json.dumps({'models_root':str(models),'ui_theme':'dark'}),encoding='utf-8');initial=settings.read_bytes()
        before=sources();cat=ProductionCatalog(target/'catalog.sqlite');root=cat.add_root(str(media));cat.start_scan(root)
        if cat._worker:cat._worker.join(12)
        requested=[]
        class Artifacts(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                if self.path!='/fixture':self.send_error(404);return
                value=self.headers.get('Range');requested.append(value);offset=int(value[6:-1]) if value else 0
                self.send_response(206 if value else 200);self.send_header('Content-Length',str(len(payload)-offset))
                if value:self.send_header('Content-Range',f'bytes {offset}-{len(payload)-1}/{len(payload)}')
                self.end_headers()
                try:self.wfile.write(payload[offset:])
                except (BrokenPipeError,ConnectionResetError):pass
        if args.published_selection:
            from test_ai_runtime import fixture
            from build_ai_runtime_catalog import build_catalog
            from ai_acquisition import validate_runtime
            from urllib.parse import quote,unquote
            pack=fixture(generated/'runtime')
            document,_=build_catalog(pack,key='generated-runtime-selection',revision='e'*40,base_url='https://example.org/immutable/'+('e'*40),license='MIT',license_url='https://example.org/NOTICE',allowed_hosts=['example.org'])
            payloads={'/artifact/'+p.relative_to(pack).as_posix():p.read_bytes() for p in pack.rglob('*') if p.is_file()}
            class ExactArtifacts(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_GET(self):
                    value=payloads.get(unquote(self.path))
                    if value is None:self.send_error(404);return
                    requested.append(self.path);self.send_response(200);self.send_header('Content-Length',str(len(value)));self.end_headers()
                    try:self.wfile.write(value)
                    except (BrokenPipeError,ConnectionResetError):pass
            Artifacts=ExactArtifacts
            before=sources()
        artifact_server=ThreadingHTTPServer(('127.0.0.1',0),Artifacts);artifact_thread=threading.Thread(target=artifact_server.serve_forever,daemon=True);artifact_thread.start()
        raw={'format':'aredoko-acquisition-v1','id':'generated-runtime','revision':'e'*40,'kind':'runtime','license':'MIT','license_url':'https://example.org/LICENSE','allowed_hosts':['127.0.0.1'],'entries':[{'path':'generated.bin','url':f'http://127.0.0.1:{artifact_server.server_port}/fixture','bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),'role':'runtime'}]}
        catalog=Catalog.parse(json.dumps(raw).encode(),test_loopback=True)
        def validate(directory,cancel):
            if cancel():raise InterruptedError('cancelled')
            if (directory/'generated.bin').read_bytes()!=payload:raise ValueError('Generated content mismatch')
        if args.published_selection:
            value=json.loads(document);value['allowed_hosts']=['127.0.0.1']
            for entry in value['entries']:entry['url']=f'http://127.0.0.1:{artifact_server.server_port}/artifact/'+quote(entry['path'],safe='/')
            catalog=Catalog.parse(json.dumps(value).encode(),test_loopback=True);validate=validate_runtime
        token=secrets.token_hex(32);profiles=AIProfileSettings(target,target/'ai-settings.json',profile_directory=target/'profiles',ai_python=str(target/'no-interpreter.exe'),models_root=str(models))
        instance=secrets.token_hex(16) if args.published_selection else None
        if instance is not None:env.update(AREDOKO_STARTUP_NONCE=secrets.token_hex(16),AREDOKO_STARTUP_INSTANCE=instance)
        handler=production_handler(cat,token,ai=DisabledAI(),profiles=profiles,tagger=DisabledTagger(),instance_id=instance,runtime_preferences=settings,acquisition_specs=((catalog,validate),));handler.log_message=lambda *args:None
        server=ThreadingHTTPServer(('127.0.0.1',8769),handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        if args.published_selection:
            original_popen=subprocess.Popen
            report['unexpected_process_attempts']=[]
            def guarded_popen(command,*position,**options):
                first=str(command[0]) if isinstance(command,(list,tuple)) else str(command)
                if first.casefold() not in ('winapp','git',str(front/'Aredoko.WinUI.exe').casefold()):
                    report['unexpected_process_attempts'].append(Path(first).name)
                    raise AssertionError('The selected runtime must never execute in this fixture')
                return original_popen(command,*position,**options)
            subprocess.Popen=guarded_popen
        with (target/'app.log').open('w',encoding='utf-8') as log:proc=subprocess.Popen([str(front/'Aredoko.WinUI.exe'),'--ui-theme',args.theme,'--viewer-settings',str(target/'viewer-settings.json')],cwd=front,env=env,stdout=log,stderr=subprocess.STDOUT)
        report['owned_pid']=proc.pid
        for _ in range(30):
            if proc.poll() is not None:raise RuntimeError('Owned app exited: '+str(proc.returncode))
            windows=[w for w in json.loads(cli('list-windows','-a',proc.pid,'--json')) if w.get('title') and w['title']!='PopupHost']
            if len(windows)==1:hwnd=str(windows[0]['hwnd']);break
            time.sleep(.2)
        check('owned window',hwnd is not None)
        def open_acquisition():
            ui('invoke','BtnSettings');ui('wait-for','BtnAIIndex','-t','5000');ui('invoke','BtnAIIndex')
            ui('wait-for','AIEnvironmentOpen','-t','7000');ui('invoke','AIEnvironmentOpen');ui('wait-for','AIEnvironmentDownload','-t','7000')
            ui('invoke','AIEnvironmentDownload');ui('wait-for','AIDownloadDialog','-t','7000')
        ui('wait-for','Item'+str(cat.search()['items'][0]['id']),'-t','12000');open_acquisition()
        ui('wait-for','AIDownloadInformation','--value','MIT','--contains','-t','5000')
        ui('wait-for','PrimaryButton','-p','IsEnabled','--value','False','-t','3000');shot('acquisition-idle')
        check('idle makes no artifact request',requested==[] and settings.read_bytes()==initial)
        if args.published_selection:
            ui('invoke','AIDownloadConsent');ui('wait-for','PrimaryButton','-p','IsEnabled','--value','True','-t','3000');ui('invoke','PrimaryButton')
            wait('generated valid runtime is published',lambda:handler.download_jobs.snapshot()['state']=='complete' and handler.download_jobs.snapshot()['published'])
            ui('wait-for','AIDownloadSelect','-p','IsEnabled','--value','True','-t','7000');shot('published-selection')
            result=handler.download_jobs.snapshot()['result'];check('publication alone preserves preferences',settings.read_bytes()==initial)
            ui('invoke','AIDownloadSelect');ui('wait-for','AIEnvironmentAcquiredLocation','--value',result['root'],'-t','7000')
            ui('wait-for','AIEnvironmentUseAcquired','-p','IsEnabled','--value','True','-t','7000');shot('explicit-selection')
            check('opening selection does not save',settings.read_bytes()==initial and handler.setup_jobs.snapshot()['state']=='idle')
            ui('invoke','AIEnvironmentUseAcquired')
            wait('explicit use validates and saves next restart',lambda:handler.setup_jobs.snapshot()['state']=='complete' and handler.setup_jobs.snapshot()['saved'])
            ui('wait-for','AIEnvironmentUseAcquired','--value','次回起動に設定済み','-t','7000')
            ui('wait-for','AIEnvironmentUseAcquired','-p','IsEnabled','--value','False','-t','3000');shot('selection-saved')
            selected=json.loads(settings.read_text(encoding='utf-8'))
            check('exact acquired runtime root is saved',selected['ai_runtime_root']==result['root'])
            check('model root and unrelated theme are preserved',selected['models_root']==str(models) and selected['ui_theme']=='dark')
            check('selected runtime inventory is pinned',len(selected['ai_runtime_manifest_sha256'])==64)
            check('generated source and media unchanged',sources()==before)
            check('frontend startup log is isolated',(target/'user/Aredoko/logs'/('frontend-startup-'+env['AREDOKO_STARTUP_NONCE']+'.log')).is_file())
            report.update(feature='published runtime explicit use',selected_runtime_executed=False,settings=selected,artifact_requests=requested)
            ui('invoke','CloseButton');ui('wait-for','AIEnvironmentDialog','--gone','-t','5000');report['pass']=True
        else:
            progress=handler.download_jobs._progress
            def controlled(value):
                progress(value)
                if not reached.is_set() and value['stage']=='downloading' and value['bytes_received']>=65536:reached.set();release.wait(90)
            handler.download_jobs._progress=controlled
            ui('invoke','AIDownloadConsent');ui('wait-for','PrimaryButton','-p','IsEnabled','--value','True','-t','3000');ui('invoke','PrimaryButton')
            check('native Start reaches real generated transfer',reached.wait(5))
            ui('wait-for','SecondaryButton','-p','IsEnabled','--value','True','-t','5000');shot('acquisition-active')
            ui('invoke','CloseButton');ui('wait-for','AIDownloadDialog','--gone','-t','5000');open_acquisition()
            ui('wait-for','SecondaryButton','-p','IsEnabled','--value','True','-t','5000');check('download reattaches to owned transfer',handler.download_jobs.snapshot()['state']=='downloading')
            ui('invoke','SecondaryButton');wait('native transfer cancellation accepted',lambda:handler.download_jobs.snapshot()['state']=='cancelling')
            release.set();wait('transfer cancelled before publication',lambda:handler.download_jobs.snapshot()['state']=='cancelled')
            ui('wait-for','AIDownloadStatus','--value','途中から再開できます','--contains','-t','7000');shot('acquisition-cancelled')
            check('cancel retains original launch preferences',settings.read_bytes()==initial)
            ui('invoke','AIDownloadConsent');ui('wait-for','PrimaryButton','-p','IsEnabled','--value','True','-t','3000');ui('invoke','PrimaryButton')
            wait('native resume publishes verified generated artifact',lambda:handler.download_jobs.snapshot()['state']=='complete' and handler.download_jobs.snapshot()['published'])
            ui('wait-for','AIDownloadDestination','-t','7000');ui('wait-for','PrimaryButton','-p','IsEnabled','--value','False','-t','3000');shot('acquisition-complete')
            result=handler.download_jobs.snapshot()['result'];check('published bytes match generated source',(Path(result['root'])/'generated.bin').read_bytes()==payload)
            check('same catalog resumes using HTTP Range',len(requested)==2 and requested[0] is None and requested[1] is not None and requested[1].startswith('bytes='))
            check('publication does not activate AI or change settings',settings.read_bytes()==initial)
            check('generated source and media unchanged',sources()==before)
            report['artifact_requests']=requested;report['final_acquisition_job']=handler.download_jobs.snapshot()
            ui('invoke','CloseButton');ui('wait-for','AIDownloadDialog','--gone','-t','5000');report['pass']=True
    except Exception:
        report['error']=traceback.format_exc();print(report['error'],flush=True)
        if hwnd and proc is not None and proc.poll() is None:
            try:shot('failure')
            except Exception:report['capture_error']=traceback.format_exc()
    finally:
        release.set()
        if proc is not None and proc.poll() is None and hwnd:
            try:
                # Wait for dialog finalizers before ordinary main-window close.
                for _ in range(3):
                    visible=list(nodes(json.loads(ui('inspect','--depth','22','--json'))))
                    dialogs=[n.get('automationId') for n in visible if n.get('automationId') in ('AIDownloadDialog','AIEnvironmentDialog','AIEnvironmentOpen') and not n.get('isOffscreen',True)]
                    if not dialogs:break
                    ui('invoke','CloseButton')
                    for identifier in dialogs:ui('wait-for',identifier,'--gone','-t','5000')
                owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
                if owner.value!=proc.pid:raise RuntimeError('Cleanup HWND changed')
                if not user.PostMessageW(int(hwnd),0x10,0,0):raise ctypes.WinError(ctypes.get_last_error())
                try:
                    ui('wait-for','PrimaryButton','-t','2000')
                    visible=list(nodes(json.loads(ui('inspect','--depth','22','--json'))))
                    if any(n.get('automationId')=='PrimaryButton' and n.get('name')=='変更を破棄' for n in visible):ui('invoke','PrimaryButton')
                except Exception:pass
                proc.wait(timeout=12);report['graceful_exit']=proc.returncode
            except Exception:report['cleanup_error']=traceback.format_exc()
        if server:server.shutdown();server.server_close()
        if thread:thread.join(5)
        if server:
            for resource in (handler.download_jobs,handler.restore_jobs,handler.backup_jobs,handler.thumbnails,handler.results,handler.animations,handler.setup_jobs):resource.close()
        if cat:cat.close()
        if artifact_server:artifact_server.shutdown();artifact_server.server_close()
        if artifact_thread:artifact_thread.join(5)
        try:cli('yield')
        except Exception:report['yield_error']=traceback.format_exc()
        if report['source_files']!={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in tracked}:report['pass']=False;report['source_changed']=True
        report['frontend_exit_code']=None if proc is None else proc.poll()
        if server:report['final_setup_job']=handler.setup_jobs.snapshot();report['final_acquisition_job']=handler.download_jobs.snapshot()
        report['process_still_running']=proc is not None and proc.poll() is None
        if original_popen is not None:subprocess.Popen=original_popen
        report['test_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['pass'] and report.get('frontend_exit_code')==0 and not report.get('process_still_running') else 1
if __name__=='__main__':raise SystemExit(main())
