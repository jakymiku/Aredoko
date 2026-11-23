"""One bounded native backup progress/cancel workflow, generated media/catalog only; no installed app changes."""
import argparse,ctypes,hashlib,json,os,secrets,subprocess,sys,threading,time,traceback,urllib.request,struct
from ctypes import wintypes
from http.server import ThreadingHTTPServer
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'app'),str(REPO/'tools')]
from production import ProductionCatalog
from production_server import production_handler,DisabledAI
from ai_settings import AIProfileSettings
from wd_tagger import DisabledTagger
from create_preview_fixture import png
from native_ui_tools import nodes

def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace');sys.stderr.reconfigure(encoding='utf-8',errors='replace')
    parser=argparse.ArgumentParser();parser.add_argument('--frontend',type=Path,required=True);parser.add_argument('--attempt',type=int,choices=(1,2,3),required=True);parser.add_argument('--theme',choices=('light','dark'),default='dark');args=parser.parse_args()
    front=args.frontend.resolve();base=REPO/'data/ai-ui/p5-backup-20261023';target=base/f'run{args.attempt:02}'
    if os.name!='nt' or not front.is_relative_to(REPO/'data/ai-ui') or not (front/'Aredoko.WinUI.exe').is_file() or target.exists():parser.error('New bounded output and dedicated frontend required')
    target.mkdir(parents=True);report={'pass':False,'checks':[],'screenshots':[],'target':'local','visual_review':'pending','source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()}
    report['frontend_sha256']=hashlib.sha256((front/'Aredoko.WinUI.dll').read_bytes()).hexdigest()
    report['diff_sha256']=hashlib.sha256(subprocess.check_output(['git','diff','--','src','app'],cwd=REPO)).hexdigest()
    tracked=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','--','src','app'],cwd=REPO,text=True).splitlines()
    report['source_files']={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in tracked}
    report['frontend_sha256']=hashlib.sha256((front/'Aredoko.WinUI.dll').read_bytes()).hexdigest()
    env={**os.environ,'WINAPP_UI_WORKFLOW_ID':'aredoko-p5-backup-20261023'}
    user=ctypes.WinDLL('user32',use_last_error=True);user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)];user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    cat=server=thread=proc=None;hwnd=None;release=threading.Event();reached=threading.Event()
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
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            if predicate():check(name,True);return
            time.sleep(.1)
        check(name,False)
    def shot(name):
        path=target/(name+'.png');ui('screenshot','--output',path);report['screenshots'].append(str(path))
        payload=path.read_bytes()
        if payload[:8]!=b'\x89PNG\r\n\x1a\n' or len(payload)<24 or min(struct.unpack('>II',payload[16:24]))<100:raise RuntimeError('Screenshot is empty or too small; not visual acceptance')
        (target/(name+'.json')).write_text(ui('inspect','--depth','18','--json'),encoding='utf-8')
    def sources():return {p.name:[hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns] for p in media.iterdir()}
    try:
        media=target/'media';media.mkdir();(media/'generated.png').write_bytes(png(width=160,height=180,color=(50,120,170)))
        before=sources();cat=ProductionCatalog(target/'catalog.sqlite');root=cat.add_root(str(media));cat.start_scan(root)
        if cat._worker:cat._worker.join(12)
        token=secrets.token_hex(32);profiles=AIProfileSettings(REPO,target/'ai-settings.json',profile_directory=target/'profiles')
        handler=production_handler(cat,token,ai=DisabledAI(),profiles=profiles,tagger=DisabledTagger());handler.log_message=lambda *args:None
        server=ThreadingHTTPServer(('127.0.0.1',8769),handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        with (target/'app.log').open('w',encoding='utf-8') as log:proc=subprocess.Popen([str(front/'Aredoko.WinUI.exe'),'--ui-theme',args.theme,'--viewer-settings',str(target/'viewer-settings.json')],cwd=front,env=env,stdout=log,stderr=subprocess.STDOUT)
        report['owned_pid']=proc.pid
        for _ in range(30):
            if proc.poll() is not None:raise RuntimeError('Owned app exited: '+str(proc.returncode))
            windows=[w for w in json.loads(cli('list-windows','-a',proc.pid,'--json')) if w.get('title') and w['title']!='PopupHost']
            if len(windows)==1:hwnd=str(windows[0]['hwnd']);break
            time.sleep(.2)
        check('owned window',hwnd is not None)
        def open_backup():
            ui('invoke','BtnSettings');ui('wait-for','BtnBackupGuide','-t','5000');ui('invoke','BtnBackupGuide');ui('wait-for','BackupDialog','-t','7000')
        ui('wait-for','Item'+str(cat.search()['items'][0]['id']),'-t','12000');open_backup()
        ui('wait-for','BackupStatus','--value','保存先と対象を選んで作成してください。ライブラリ情報は必ず含まれます。','-t','5000')
        ui('wait-for','PrimaryButton','-p','IsEnabled','--value','False','-t','3000');shot('backup-idle')
        check('no backup published in idle',not handler.backup_jobs.snapshot()['published'])
        progress=handler.backup_jobs._progress
        def controlled(value):
            progress(value)
            if value['stage']=='capturing' and value['bytes_total'] is None:reached.set();release.wait(55)
        handler.backup_jobs._progress=controlled
        # This flow verifies native reattach/cancel, not the system folder picker
        # or native Start. Start through the real authenticated endpoint only.
        origin='http://127.0.0.1:8769';opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        body={'consent':True,'output':str(target/'bundle-cancelled'),'selection':{'settings':False,'history':True,'reader_progress':True,'vectors':False}}
        request=urllib.request.Request(origin+'/api/library/backup/start',data=json.dumps(body).encode(),headers={'Origin':origin,'X-Aredoko-Token':token,'Content-Type':'application/json'})
        with opener.open(request,timeout=3) as reply:check('owned authenticated backend start',reply.status==202)
        check('capture reached real pause',reached.wait(3) and cat.writer_fence.paused)
        ui('invoke','BackupRefresh');ui('wait-for','SecondaryButton','-p','IsEnabled','--value','True','-t','5000');shot('backup-active')
        ui('invoke','CloseButton');ui('wait-for','BackupDialog','--gone','-t','5000');open_backup()
        ui('wait-for','SecondaryButton','-p','IsEnabled','--value','True','-t','5000');check('dialog reattaches to active owned job',handler.backup_jobs.snapshot()['state']=='capturing')
        ui('invoke','SecondaryButton');wait('native cancel accepted',lambda:handler.backup_jobs.snapshot()['cancel_requested'])
        release.set();wait('cancel completes without publication',lambda:handler.backup_jobs.snapshot()['state']=='cancelled')
        ui('wait-for','BackupStatus','--value','バックアップを中止しました。','-t','7000');shot('backup-cancelled')
        check('source hashes and timestamps preserved',sources()==before);check('no completed cancelled bundle',(not (target/'bundle-cancelled').exists()) and not cat.writer_fence.paused)
        ui('invoke','CloseButton');ui('wait-for','BackupDialog','--gone','-t','5000');report['pass']=True
    except Exception:
        report['error']=traceback.format_exc();print(report['error'],flush=True)
        if hwnd and proc is not None and proc.poll() is None:
            try:shot('failure')
            except Exception:report['capture_error']=traceback.format_exc()
    finally:
        release.set()
        if proc is not None and proc.poll() is None and hwnd:
            try:
                # Only generated test dialogs/drafts may be cancelled/discarded.
                for _ in range(2):
                    visible=list(nodes(json.loads(ui('inspect','--depth','22','--json'))))
                    buttons=[n for n in visible if n.get('automationId') =='CloseButton' and not n.get('isOffscreen',True)]
                    if not buttons:break
                    selector=buttons[0]['automationId'];ui('invoke',selector);ui('wait-for',selector,'--gone','-t','3000')
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
            for resource in (handler.backup_jobs,handler.thumbnails,handler.results,handler.animations,handler.setup_jobs):resource.close()
        if cat:cat.close()
        report['process_still_running']=proc is not None and proc.poll() is None
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['pass'] and not report.get('process_still_running') else 1
if __name__=='__main__':raise SystemExit(main())
