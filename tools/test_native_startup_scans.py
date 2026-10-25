"""Bounded, generated-only U4b native settings/restart/cancellation acceptance."""
import argparse,ctypes,hashlib,json,os,secrets,subprocess,sys,threading,time,traceback
from ctypes import wintypes
from pathlib import Path
from http.server import ThreadingHTTPServer
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'app'),str(REPO/'tools')]
from production import ProductionCatalog
from production_server import production_handler,DisabledAI
from ai_settings import AIProfileSettings
from wd_tagger import DisabledTagger
from native_ui_tools import nodes
from create_preview_fixture import png
from portable_frontend import inspect_portable

def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    parser=argparse.ArgumentParser();parser.add_argument('--frontend',type=Path,required=True);parser.add_argument('--attempt',type=int,choices=(1,2,3),required=True);args=parser.parse_args()
    front=args.frontend.resolve();target=REPO/'data/ai-ui/continuation-20261025b'/f'native-startup{args.attempt:02}'
    if os.name!='nt' or not front.is_relative_to(REPO/'data/ai-ui') or not (front/'Aredoko.WinUI.exe').is_file() or target.exists():parser.error('Dedicated frontend and new bounded output required')
    inspect_portable(front)  # Reject an incorrectly packaged build before launching.
    target.mkdir(parents=True)
    report={'pass':False,'checks':[],'screenshots':[],'visual_review':'pending','authorization':'User approved generated-only U4b GUI: 2 initial attempts plus 1 explicit additional attempt; no GPU',
            'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
            'frontend_sha256':hashlib.sha256((front/'Aredoko.WinUI.dll').read_bytes()).hexdigest()}
    env={**os.environ,'WINAPP_UI_WORKFLOW_ID':'aredoko-startup-20261025b','LOCALAPPDATA':str(target/'user'),'APPDATA':str(target/'user')}
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    cat=server=thread=handler=proc=None;hwnd=None;release=threading.Event();reached=threading.Event();owned=[]
    def check(name,value):
        report['checks'].append({'name':name,'pass':bool(value)});print(name,bool(value),flush=True)
        if not value:raise AssertionError(name)
    def wait(name,condition):
        deadline=time.monotonic()+18
        while time.monotonic()<deadline:
            if condition():check(name,True);return
            time.sleep(.1)
        check(name,False)
    def cli(*arguments):
        result=subprocess.run(['winapp','ui',*map(str,arguments)],cwd=REPO,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
        with (target/'commands.jsonl').open('a',encoding='utf-8') as log:log.write(json.dumps({'args':list(map(str,arguments)),'exit':result.returncode,'out':result.stdout,'error':result.stderr},ensure_ascii=False)+'\n')
        if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        return result.stdout
    def ui(*arguments):
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
        if owner.value!=proc.pid:raise RuntimeError('Owned window changed')
        return cli(*arguments,'-w',hwnd)
    def tree():return {n['automationId']:n for n in nodes(json.loads(ui('inspect','--depth','18','--json'))) if n.get('automationId')}
    def shot(name):
        path=target/(name+'.png');ui('screenshot','--output',path)
        if not path.is_file() or path.stat().st_size<1000:raise RuntimeError('Missing screenshot')
        report['screenshots'].append(str(path));path.with_suffix('.json').write_text(json.dumps(tree(),ensure_ascii=False,indent=2),encoding='utf-8')
    def start():
        nonlocal cat,handler,server,thread,proc,hwnd
        cat=ProductionCatalog(target/'catalog.sqlite')
        profiles=AIProfileSettings(REPO,target/'ai-settings.json',profile_directory=target/'profiles',ai_python=str(target/'not-installed'),models_root=target/'no-models')
        handler=production_handler(cat,secrets.token_hex(32),ai=DisabledAI(),tagger=DisabledTagger(),profiles=profiles);handler.log_message=lambda *a:None
        server=ThreadingHTTPServer(('127.0.0.1',8769),handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        with (target/f'app{len(owned)+1}.log').open('w',encoding='utf-8') as log:
            proc=subprocess.Popen([str(front/'Aredoko.WinUI.exe'),'--ui-theme','dark','--viewer-settings',str(target/'viewer-settings.json')],cwd=front,env=env,stdout=log,stderr=subprocess.STDOUT)
        owned.append(proc.pid);hwnd=None
        def find():
            nonlocal hwnd
            if proc.poll() is not None:raise RuntimeError('Frontend exited '+str(proc.returncode))
            windows=[w for w in json.loads(cli('list-windows','-a',proc.pid,'--json')) if w.get('title') and w['title']!='PopupHost']
            if len(windows)==1:hwnd=str(windows[0]['hwnd']);return True
            return False
        wait('owned window available',find);ui('wait-for','Item1','-t','15000')
    def stop():
        nonlocal cat,server,thread,handler,proc,hwnd
        release.set()
        if handler:handler.startup_scans.cancel()
        if cat and cat._worker:cat._worker.join(8)
        if proc is not None and proc.poll() is None and hwnd:
            owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
            if owner.value!=proc.pid:raise RuntimeError('Refusing to close another window')
            user.PostMessageW(int(hwnd),0x10,0,0);proc.wait(15)
            check('owned frontend closes normally',proc.returncode==0)
        if server:server.shutdown();server.server_close();thread.join(5)
        if handler:
            for resource in (handler.startup_scans,handler.thumbnails,handler.results,handler.animations,handler.setup_jobs,handler.download_jobs,handler.backup_jobs,handler.restore_jobs):resource.close()
        if cat:cat.close()
        cat=server=thread=handler=proc=hwnd=None
    try:
        folders=[]
        for i in range(2):
            folder=target/f'media{i}';folder.mkdir();(folder/f'generated{i}.png').write_bytes(png(width=160,height=180,color=(60+i*60,100,160)));folders.append(folder)
        cat=ProductionCatalog(target/'catalog.sqlite');roots=[]
        for folder in folders:
            roots.append(cat.add_root(str(folder)));cat.start_scan(roots[-1]);cat._worker.join(5)
        cat.close();cat=None;before={str(p):[hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns] for f in folders for p in f.iterdir()}
        start();check('existing folders do not start an automatic scan',not handler.startup_scans.requested)
        ui('invoke','NavFolders');ui('wait-for','ConfigFolder'+str(roots[0]),'-t','10000');ui('invoke','ConfigFolder'+str(roots[0]))
        ui('wait-for','RootStartupScan','-t','10000');ui('scroll','FolderDetailScroll','--to','bottom');ui('invoke','RootStartupScan')
        options={n['selector'] for n in nodes(json.loads(ui('inspect','--depth','18','--json'))) if n.get('type')=='ListItem' and n.get('name')=='アイテム一覧だけ更新'}
        check('one exact startup scan option',len(options)==1)
        ui('invoke',next(iter(options)),'--action','select')
        wait('startup mode saved by the real settings control',lambda:cat.registered_roots()[0]['startup_scan']=='list')
        shot('01-startup-setting');stop()
        cat=ProductionCatalog(target/'catalog.sqlite');cat.set_root_startup_scan([roots[1]],'list');cat.close();cat=None
        extra=folders[0]/'new-at-next-start.png';extra.write_bytes(png(width=160,height=180,color=(80,180,100)))
        # Hold only root2 through a fixture hook: root1 must publish successfully,
        # while root2 provides a deterministic interval to edit and cancel.
        start_scan=ProductionCatalog.start_scan
        original_scan=None
        release.clear()
        def held(self,*a,**kw):
            nonlocal original_scan
            if original_scan is None:
                original_scan=self.index.scan
                def scan(root,**options):
                    if root==roots[1]:
                        reached.set()
                        while not release.wait(.05):
                            if options['cancelled']():raise InterruptedError()
                    return original_scan(root,**options)
                self.index.scan=scan
            return start_scan(self,*a,**kw)
        from unittest.mock import patch
        with patch.object(ProductionCatalog,'start_scan',held):
            start();wait('startup queue begins after a real first frame',reached.is_set)
            check('first root is already searchable during second scan',cat.search()['total']==3)
            ui('invoke','Item1');ui('invoke','BtnDetails');ui('wait-for','TxtTags','-t','10000');ui('set-value','TxtTags','unsaved-startup-draft')
            ui('wait-for','StartupUpdateAction','--value','停止','-t','10000');ui('invoke','StartupUpdateAction')
            wait('owned startup queue cancelled',lambda:handler.startup_scans.state()['state']=='cancelled')
            ui('wait-for','StartupUpdateAction','--value','一覧を更新','-t','10000')
            check('background cancellation preserves the editing draft','unsaved-startup-draft' in ui('get-value','TxtTags'))
            check('draft was not saved implicitly',cat.get(1)['tags']==[])
            shot('02-cancelled-draft-retained')
            ui('invoke','BtnSave');wait('explicit save retains the draft tags',lambda:cat.get(1)['tags']==['unsaved-startup-draft'])
            ui('invoke','StartupUpdateAction');ui('wait-for','Item3','-t','10000');shot('03-refreshed-library')
        state=handler.startup_scans.state();check('root1 complete and root2 cancelled',[r['state'] for r in state['results']]==['complete','cancelled'])
        check('original generated media unchanged',all(p.is_file() and [hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns]==value for name,value in before.items() for p in [Path(name)]))
        stop();report['pass']=True
    except Exception:
        report['error']=traceback.format_exc();print(report['error'],flush=True)
        if proc and proc.poll() is None and hwnd:
            try:shot('failure')
            except Exception:report['capture_error']=traceback.format_exc()
    finally:
        try:stop()
        except Exception:report['cleanup_error']=traceback.format_exc()
        try:cli('yield')
        except Exception:report['yield_error']=traceback.format_exc()
        report['owned_pids']=owned
        report['script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['pass'] and 'cleanup_error' not in report else 1

if __name__=='__main__':raise SystemExit(main())
