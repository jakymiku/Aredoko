"""Generated native U5 multi-selection plus U4b corrected callback acceptance."""
import argparse,ctypes,hashlib,json,os,secrets,socket,subprocess,sys,threading,time,traceback
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
    parser=argparse.ArgumentParser();parser.add_argument('--frontend',type=Path,required=True);parser.add_argument('--attempt',type=int,choices=(1,2,3),required=True)
    parser.add_argument('--output',type=Path);parser.add_argument('--theme',choices=('dark','light'),default='dark')
    parser.add_argument('--verification-settings-only',action='store_true');parser.add_argument('--grid-pointer-only',action='store_true')
    parser.add_argument('--cancel-range-only',action='store_true');parser.add_argument('--snapshot-progress-only',action='store_true');args=parser.parse_args()
    if sum((args.verification_settings_only,args.grid_pointer_only,args.cancel_range_only,args.snapshot_progress_only))>1:parser.error('Select one bounded scenario')
    front=args.frontend.resolve();target=args.output.resolve() if args.output else REPO/'data/ai-ui/continuation-20261025b'/f'native-selection{args.attempt:02}'
    if os.name!='nt' or not front.is_relative_to(REPO/'data/ai-ui') or not target.is_relative_to(REPO/'data/ai-ui') or not (front/'Aredoko.WinUI.exe').is_file() or target.exists():parser.error('Dedicated frontend and new bounded output required')
    inspect_portable(front)  # Reject an incorrectly packaged build before launching.
    target.mkdir(parents=True)
    report={'pass':False,'checks':[],'screenshots':[],'visual_review':'pending','authorization':'Current user permits dedicated generated-data native tests; previous attempt reports are preserved; no GPU',
            'theme':args.theme,
            'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
            'frontend_sha256':hashlib.sha256((front/'Aredoko.WinUI.dll').read_bytes()).hexdigest()}
    env={**os.environ,'WINAPP_UI_WORKFLOW_ID':'aredoko-selection-20261025b','LOCALAPPDATA':str(target/'user'),'APPDATA':str(target/'user')}
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
        instance=secrets.token_hex(16);env['AREDOKO_STARTUP_INSTANCE']=instance
        handler=production_handler(cat,secrets.token_hex(32),ai=DisabledAI(),tagger=DisabledTagger(),profiles=profiles,instance_id=instance);handler.log_message=lambda *a:None
        if args.snapshot_progress_only:
            original_provider=handler.results.provider
            def progress_provider(conditions,consume,cancelled):
                def intercept(page):
                    def held(number):
                        if number==1:
                            reached.set();deadline=time.monotonic()+30
                            while not release.wait(.05):
                                if cancelled():raise InterruptedError('Generated progress cancellation')
                                if time.monotonic()>deadline:raise TimeoutError('Bounded progress gate expired')
                        return page(number)
                    return consume(held)
                return original_provider(conditions,intercept,cancelled)
            handler.results.provider=progress_provider
        server=ThreadingHTTPServer(('127.0.0.1',8769),handler,bind_and_activate=False)
        server.allow_reuse_address=False
        server.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        server.server_bind();server.server_activate()
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        with (target/f'app{len(owned)+1}.log').open('w',encoding='utf-8') as log:
            proc=subprocess.Popen([str(front/'Aredoko.WinUI.exe'),'--ui-theme',args.theme,'--viewer-settings',str(target/'viewer-settings.json')],cwd=front,env=env,stdout=log,stderr=subprocess.STDOUT)
        owned.append(proc.pid);hwnd=None
        def find():
            nonlocal hwnd
            if proc.poll() is not None:raise RuntimeError('Frontend exited '+str(proc.returncode))
            windows=[w for w in json.loads(cli('list-windows','-a',proc.pid,'--json')) if w.get('title') and w['title']!='PopupHost']
            if len(windows)==1:hwnd=str(windows[0]['hwnd']);return True
            return False
        wait('owned window available',find)
        if args.snapshot_progress_only:ui('wait-for','TxtCount','--value','準備中 120 / 1,201','-t','10000')
        else:ui('wait-for','Item1','-t','15000')
    def stop():
        nonlocal cat,server,thread,handler,proc,hwnd
        release.set()
        if handler:handler.startup_scans.cancel()
        if cat and cat._worker:cat._worker.join(8)
        if proc is not None and proc.poll() is None and hwnd:
            if 'CloseButton' in tree():
                ui('invoke','CloseButton');ui('wait-for','CloseButton','--gone','-t','10000')
            owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
            if owner.value!=proc.pid:raise RuntimeError('Refusing to close another window')
            user.PostMessageW(int(hwnd),0x10,0,0);proc.wait(15)
            check('owned frontend closes normally',proc.returncode==0)
        if server:server.shutdown();server.server_close();thread.join(5)
        if handler:
            for resource in (handler.startup_scans,handler.thumbnails,handler.results,handler.animations,handler.setup_jobs,handler.download_jobs,handler.backup_jobs,handler.restore_jobs):resource.close()
        if cat:cat.close()
        cat=server=thread=handler=proc=hwnd=None
    def select(ids):
        if ids not in ([1],[1,2]):raise ValueError('This bounded keyboard fixture selects item1 or adjacent items1/2 only')
        ui('invoke','Item1','--action','select')
        if len(ids)==2:
            ui('focus','Item1')
            ui('send-keys','shift+down','--via','send-input')
    try:
        folders=[]
        for i in range(2):
            folder=target/f'media{i}';folder.mkdir();folders.append(folder)
            content=png(width=24,height=24,color=(60+i*60,100,160))
            for number in range(1200 if i==0 else 1):(folder/f'generated-{number:04}.png').write_bytes(content)
        cat=ProductionCatalog(target/'catalog.sqlite');roots=[]
        for folder in folders:
            roots.append(cat.add_root(str(folder)));cat.start_scan(roots[-1]);cat._worker.join(10)
        shelf=cat.change_shelf('create',name='生成テスト棚')['id'];cat.close();cat=None
        before={str(p):[hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns] for f in folders for p in f.iterdir()}
        start();check('existing folders do not start an automatic scan',not handler.startup_scans.requested)
        if args.snapshot_progress_only:
            check('building progress is visible without partial rows',reached.is_set() and 'Item1' not in tree())
            shot('01-snapshot-building');release.set();ui('wait-for','Item1','-t','10000');ui('wait-for','TxtCount','--value','1,201 件','-t','10000')
            shot('02-snapshot-ready');release.clear();reached.clear();ui('set-value','TxtQuery','generated')
            ui('wait-for','TxtCount','--value','準備中 120 / 1,201','-t','10000');ui('invoke','BtnCancelSearch')
            ui('wait-for','TxtCount','--value','中断','--contains','-t','10000');shot('03-snapshot-cancelled')
            ui('set-value','TxtQuery','generated-0003');ui('wait-for','Item4','-t','10000');ui('wait-for','TxtCount','--value','1 件','-t','10000')
            check('new search is not overwritten by cancelled progress','Item1' not in tree());shot('04-new-search-after-progress');stop();report['pass']=True;return 0
        if args.cancel_range_only:
            ui('invoke','BrowseActions');ui('invoke','BtnNext');ui('wait-for','Item61','-t','10000')
            ui('invoke','Item61','--action','select');ui('invoke','BtnDetails');ui('wait-for','TxtTags','-p','IsEnabled','--value','True','-t','10000')
            original_read=handler.results.read;held_once=threading.Event();release.clear()
            def held_range(session_id,offset=0,limit=120):
                if offset==120 and not held_once.is_set():
                    held_once.set();reached.set()
                    if not release.wait(20):raise RuntimeError('Bounded test range gate timed out')
                return original_read(session_id,offset,limit)
            handler.results.read=held_range
            ui('invoke','BrowseActions');ui('invoke','BtnNext');wait('next uncached result range is in progress',reached.is_set)
            ui('invoke','BtnCancelSearch');ui('wait-for','BtnCancelSearch','--gone','-t','10000')
            ui('wait-for','Item61','-t','10000');ui('wait-for','TxtPageNumber','--value','61–120','--contains','-t','10000')
            ui('wait-for','TxtTags','-p','IsEnabled','--value','True','-t','10000');shot('01-cancelled-range-retained')
            ui('set-value','TxtTags','unsaved-cancel-draft');check('cancelled range leaves selected item editable','unsaved-cancel-draft' in ui('get-value','TxtTags'))
            ui('set-value','TxtTags','');check('no draft is written implicitly',cat.get(61)['tags']==[])
            release.set();ui('invoke','BrowseActions');ui('invoke','BtnNext');ui('wait-for','Item121','-t','10000');shot('02-cancelled-range-retried')
            ui('set-value','TxtQuery','generated-0003');ui('wait-for','TxtCount','--value','1 件','-t','15000');ui('wait-for','Item4','-t','10000');shot('03-new-input-after-cancel')
            check('later input can start a new search','Item61' not in tree());stop();report['pass']=True;return 0
        if args.verification_settings_only:
            def settings(expected):
                ui('invoke','BtnSettings');ui('wait-for','SettingsAdvanced','-t','10000');ui('invoke','SettingsAdvanced')
                ui('wait-for','SettingsVerifyAIRuntime','-t','10000')
                check('verification checkbox state '+str(expected),tree()['SettingsVerifyAIRuntime'].get('toggleState')==('on' if expected else 'off'))
            settings(True);shot('01-advanced-default')
            ui('invoke','SettingsVerifyAIRuntime');ui('invoke','SettingsSave')
            ui('wait-for','SettingsStatus','--value','保存しました','--contains','-t','10000')
            path=target/'launch-settings.json'
            check('disabled preference saved',json.loads(path.read_text())['verify_ai_runtime'] is False)
            shot('02-advanced-saved');ui('invoke','CloseButton');ui('wait-for','SettingsDialog','--gone','-t','10000');stop()
            start();settings(False);shot('03-advanced-restarted')
            ui('invoke','CloseButton');ui('wait-for','SettingsDialog','--gone','-t','10000')
            stop();report['pass']=True;return 0
        if args.grid_pointer_only:
            ui('invoke','BtnLayout');ui('wait-for','Item1','-t','10000');ui('click','Item1')
            # Hold Control only while the exact owned window is foreground;
            # always release it, including CLI/provider failures.
            class Mouse(ctypes.Structure):
                _fields_=[('dx',wintypes.LONG),('dy',wintypes.LONG),('data',wintypes.DWORD),('flags',wintypes.DWORD),('time',wintypes.DWORD),('extra',ctypes.c_size_t)]
            class Key(ctypes.Structure):
                _fields_=[('vk',wintypes.WORD),('scan',wintypes.WORD),('flags',wintypes.DWORD),('time',wintypes.DWORD),('extra',ctypes.c_size_t)]
            class Union(ctypes.Union):_fields_=[('mouse',Mouse),('key',Key)]
            class Input(ctypes.Structure):_fields_=[('type',wintypes.DWORD),('value',Union)]
            user.GetForegroundWindow.restype=wintypes.HWND
            user.SendInput.argtypes=[wintypes.UINT,ctypes.POINTER(Input),ctypes.c_int]
            check('owned grid window is foreground',user.GetForegroundWindow()==int(hwnd))
            check('human Control key is not held',not user.GetAsyncKeyState(0x11)&0x8000)
            def control(flags):
                event=Input(type=1,value=Union(key=Key(vk=0x11,flags=flags)))
                if user.SendInput(1,ctypes.byref(event),ctypes.sizeof(event))!=1:raise OSError('Input rejected')
            try:
                control(0);ui('click','Item3')
            finally:control(2)
            ui('wait-for','SelectionCountText','--value','2 件選択','--contains','-t','10000')
            check('grid selection leaves details closed','SelectionSummaryText' not in tree());shot('01-grid-control-selection')
            ui('click','Item3','--right');ui('wait-for','BulkFavoriteAdd','-t','10000');ui('invoke','BulkFavoriteAdd')
            wait('right-click favorite edits exactly the Control-selected pair',lambda:cat.get(1)['favorite'] and cat.get(3)['favorite'] and not cat.get(2)['favorite'])
            ui('wait-for','SelectionInlineStatus','--value','保存しました','--contains','-t','20000');ui('click','Item3','--right');ui('wait-for','BulkShelfAdd','-t','10000');ui('invoke','BulkShelfAdd')
            ui('wait-for','BulkShelfChoice'+str(shelf),'-t','10000');ui('invoke','BulkShelfChoice'+str(shelf),'--action','select');ui('invoke','PrimaryButton')
            wait('right-click shelf edits exactly the selected pair',lambda:cat.get(1)['shelf_ids']==[shelf] and cat.get(3)['shelf_ids']==[shelf] and cat.get(2)['shelf_ids']==[])
            ui('wait-for','PrimaryButton','--gone','-t','10000');ui('wait-for','SelectionInlineStatus','--value','保存しました','--contains','-t','20000');shot('02-grid-context-saved')
            ui('invoke','BtnLayout');ui('wait-for','SelectionCountText','--value','2 件選択','--contains','-t','10000')
            ui('wait-for','Item1','-p','IsOffscreen','--value','False','-t','10000');check('leading tile stays visible after list reflow',True);shot('03-list-keeps-grid-selection')
            ui('invoke','ClearLibrarySelection');ui('wait-for','SelectionCountText','--gone','-t','10000')
            check('generated originals unchanged',all(hashlib.sha256(Path(name).read_bytes()).hexdigest()==value[0] for name,value in before.items()))
            stop();report['pass']=True;return 0
        select([1,2]);ui('wait-for','SelectionCountText','--value','2 件選択','--contains','-t','10000')
        check('single click selection does not open details','SelectionSummaryText' not in tree())
        ui('invoke','BtnDetails');ui('wait-for','SelectionSummaryText','--value','2 件','--contains','-t','10000');shot('01-multiple-selection')
        ui('invoke','SelectionFavoriteAdd');wait('bulk favorite saves both items',lambda:cat.get(1)['favorite'] and cat.get(2)['favorite'])
        ui('wait-for','SelectionSummaryText','--value','2 件','--contains','-t','10000')
        # Backend commit precedes result-session replacement. Wait for the
        # published UI completion state, never infer readiness from a sleep.
        ui('wait-for','SelectionEditStatus','--value','保存しました','--contains','-t','20000')
        ui('invoke','SelectionShelfAdd');ui('wait-for','BulkShelfChoice'+str(shelf),'-t','10000')
        ui('invoke','BulkShelfChoice'+str(shelf),'--action','select');ui('invoke','PrimaryButton')
        wait('bulk shelf add keeps both memberships',lambda:cat.get(1)['shelf_ids']==[shelf] and cat.get(2)['shelf_ids']==[shelf])
        ui('wait-for','PrimaryButton','--gone','-t','10000');ui('wait-for','SelectionEditStatus','--value','保存しました','--contains','-t','20000');ui('invoke','BtnCloseDetails')
        for n in range(10):
            ui('scroll','ItemList','--to','bottom');time.sleep(.5)
            visible=tree()
            if '一覧外 2 件' in visible.get('SelectionCountText',{}).get('name',''):break
        check('selection survives removal from the 600-row window','一覧外 2 件' in tree().get('SelectionCountText',{}).get('name',''))
        shot('02-selection-outside-window')
        ui('invoke','NavFavorites');ui('wait-for','Item1','-t','15000');select([1,2]);ui('invoke','BtnDetails')
        ui('wait-for','SelectionFavoriteRemove','-t','10000');ui('invoke','SelectionFavoriteRemove')
        wait('favorite-only result removes exactly the edited items',lambda:cat.search(view='favorites')['total']==0)
        ui('wait-for','Item1','--gone','-t','15000');shot('03-filtered-removal')
        ui('invoke','NavFolders');ui('wait-for','ConfigFolder'+str(roots[0]),'-t','10000');ui('invoke','ConfigFolder'+str(roots[0]))
        ui('wait-for','RootStartupScan','-t','10000');ui('scroll','FolderDetailScroll','--to','bottom');ui('invoke','RootStartupScan')
        options={n['selector'] for n in nodes(json.loads(ui('inspect','--depth','18','--json'))) if n.get('type')=='ListItem' and n.get('name')=='アイテム一覧だけ更新'}
        check('one exact startup scan option',len(options)==1);ui('invoke',next(iter(options)),'--action','select')
        wait('startup mode saved by the corrected control',lambda:cat.registered_roots()[0]['startup_scan']=='list')
        shot('04-startup-setting');stop()
        cat=ProductionCatalog(target/'catalog.sqlite');cat.set_root_startup_scan([roots[1]],'list');cat.close();cat=None
        (folders[0]/'new-at-next-start.png').write_bytes(png(width=24,height=24,color=(80,180,100)))
        start_scan=ProductionCatalog.start_scan;original_scan=None;release.clear()
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
            start();wait('startup queue begins after a rendered screen',reached.is_set)
            check('first root publishes while second root waits',cat.search()['total']==1202)
            select([1]);ui('invoke','BtnDetails');ui('wait-for','TxtTags','-t','10000');ui('set-value','TxtTags','unsaved-startup-draft')
            ui('wait-for','StartupUpdateAction','--value','停止','-t','10000');ui('invoke','StartupUpdateAction')
            wait('owned startup queue cancelled',lambda:handler.startup_scans.state()['state']=='cancelled')
            ui('wait-for','StartupUpdateAction','--value','一覧を更新','-t','10000')
            check('background completion preserves the editing draft','unsaved-startup-draft' in ui('get-value','TxtTags'))
            check('draft was not saved implicitly',cat.get(1)['tags']==[]);shot('05-cancelled-draft-retained')
            ui('invoke','BtnSave');wait('explicit save retains draft tags',lambda:cat.get(1)['tags']==['unsaved-startup-draft'])
            ui('wait-for','TxtTags','-p','IsEnabled','--value','True','-t','20000');ui('invoke','StartupUpdateAction');ui('wait-for','StartupUpdateAction','--gone','-t','20000');ui('wait-for','Item1','-t','10000');shot('06-refreshed-library')
        check('first root complete and second root cancelled',[r['state'] for r in handler.startup_scans.state()['results']]==['complete','cancelled'])
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
