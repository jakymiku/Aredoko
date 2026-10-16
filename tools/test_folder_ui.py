"""Owned folder/shelf/unregister and AI candidate grouping checks on generated media only.

Built x64 Release required. No models, downloads, OS settings or private media.
Physical input is guarded by owned HWND/PID and verified foreground; denied
activation is recorded as skipped, never claimed as keyboard coverage.
"""
import zipfile
from urllib.parse import urlparse
import argparse,ctypes,hashlib,json,os,secrets,subprocess,sys,threading,time,uuid
from ctypes import wintypes
from http.server import ThreadingHTTPServer
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from production import ProductionCatalog,ScanBusyError
from production_server import production_handler
from ai_settings import AIProfileSettings
from test_search_methods_ui import ContractEncoder,RecordedAI
from create_holdout_fixture import graphic

def nodes(value):
    if isinstance(value,dict):
        yield value
        for child in value.values():yield from nodes(child)
    elif isinstance(value,list):
        for child in value:yield from nodes(child)

def focused_property(value):
    def true(v):return v is True or isinstance(v,str) and v.casefold()=='true'
    for row in nodes(value):
        for key,v in row.items():
            if key.casefold()=='haskeyboardfocus' and (true(v) or isinstance(v,dict) and true(v.get('value'))):return True
        if str(row.get('property','')).casefold()=='haskeyboardfocus' and true(row.get('value')):return True
    return False

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();target=args.output.resolve()
    if os.name!='nt':parser.error('Native Windows required')
    if not target.is_relative_to((REPO/'data/ai-ui').resolve()):parser.error('Evidence must stay in data/ai-ui')
    target.mkdir(parents=True,exist_ok=False)
    env={**os.environ,'WINAPP_UI_WORKFLOW_ID':'aredoko-hark-'+uuid.uuid4().hex}
    report={'pass':False,'target':'local','actual_model':False,'checks':[],'screenshots':[],'keyboard_actions':[],'keyboard_skipped':[],'display':[],'audit_scope':'folder sidebar/settings and AI candidate groups; not whole-app audit'}
    catalog=engine=server=thread=None;hwnd=app_pid=process=None;original={}
    expected_source={}
    user32=ctypes.WinDLL('user32',use_last_error=True);kernel32=ctypes.WinDLL('kernel32',use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user32.GetForegroundWindow.restype=wintypes.HWND
    user32.SetForegroundWindow.argtypes=[wintypes.HWND]
    user32.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    user32.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
    user32.GetDpiForWindow.argtypes=[wintypes.HWND];user32.GetDpiForWindow.restype=wintypes.UINT
    kernel32.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel32.OpenProcess.restype=wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel32.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
    kernel32.CloseHandle.argtypes=[wintypes.HANDLE]
    def check(name,condition):
        if not condition:raise RuntimeError(name)
        report['checks'].append(name);print(json.dumps({'check':name}),flush=True)
    def cli(*args):
        r=subprocess.run(['winapp',*map(str,args)],cwd=REPO,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        if r.returncode:raise RuntimeError('winapp '+str(args)+': '+r.stdout+r.stderr)
        return r.stdout
    def ui(*args):return cli('ui',*args,'-w',hwnd)
    def wait(identifier,value):ui('wait-for',identifier,'--value',value,'-t','10000')
    def ready():ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000');time.sleep(.4)
    def keys(sequence,identifier=None):
        if kernel32.WaitForSingleObject(process,0)==0:raise RuntimeError('Owned process exited before input')
        owner=wintypes.DWORD();user32.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
        if owner.value!=app_pid:raise RuntimeError('Owned window changed before input')
        if user32.GetForegroundWindow()!=int(hwnd):user32.SetForegroundWindow(int(hwnd));time.sleep(.1)
        if user32.GetForegroundWindow()!=int(hwnd):
            report['keyboard_skipped'].append({'target':identifier,'keys':sequence,'reason':'Windows denied owned-window activation'})
            return False
        if identifier:
            ui('inspect',identifier,'--json')
            ui('focus',identifier)
        # Check again after CLI focus, before requesting OS-wide input.
        if user32.GetForegroundWindow()!=int(hwnd):
            report['keyboard_skipped'].append({'target':identifier,'keys':sequence,'reason':'Foreground changed after focus'})
            return False
        if identifier:
            observed=json.loads(ui('get-property',identifier,'--property','HasKeyboardFocus','--json'))
            if not focused_property(observed):raise RuntimeError('Keyboard focus changed before input: '+identifier)
        owner=wintypes.DWORD();user32.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
        if owner.value!=app_pid or kernel32.WaitForSingleObject(process,0)==0:raise RuntimeError('Owned input target changed')
        if user32.GetForegroundWindow()!=int(hwnd):
            report['keyboard_skipped'].append({'target':identifier,'keys':sequence,'reason':'Foreground changed before dispatch'})
            return False
        # focus already verified the exact peer. Do not refocus it with --target:
        # rendering can replace that peer between the two separate CLI commands.
        ui('send-keys',sequence,'--via','send-input')
        report['keyboard_actions'].append({'target':identifier,'keys':sequence,'dispatch':'verified focus; owned HWND only'})
        return True
    def focus_assert(identifier):ui('wait-for',identifier,'-p','HasKeyboardFocus','--value','True','-t','5000')
    def shot(name):
        # Capture only the verified owned window, including its modal state.
        time.sleep(.6)
        p=target/(name+'.png');ui('screenshot','--output',p)
        check('Delivered '+name,p.is_file() and p.stat().st_size>0);report['screenshots'].append(p.name)
    def resize(width,height):
        dpi=user32.GetDpiForWindow(int(hwnd));scale=dpi/96
        if not user32.SetWindowPos(int(hwnd),None,0,0,round(width*scale),round(height*scale),0x0014):raise ctypes.WinError(ctypes.get_last_error())
        time.sleep(.4)
    def audit(phase,ids):
        tree=json.loads(ui('inspect','--json','--depth','16'));all_nodes=list(nodes(tree))
        result=[]
        for identifier in ids:
            matches=[n for n in all_nodes if n.get('automationId')==identifier]
            check(phase+' accessible '+identifier,len(matches)==1 and bool(matches[0].get('name')))
            result.append({'id':identifier,'name':matches[0]['name'],'type':matches[0]['type']})
        report.setdefault('accessible_controls',{})[phase]=result
        (target/(phase+'-tree.json')).write_text(json.dumps(tree,ensure_ascii=False),encoding='utf-8')
    def close():
        nonlocal process,hwnd,app_pid
        if not process:return
        try:
            if kernel32.WaitForSingleObject(process,0)!=0:
                owner=wintypes.DWORD();user32.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
                if owner.value!=app_pid:raise RuntimeError('Owned close window changed')
                user32.PostMessageW(int(hwnd),0x0010,0,0)
                if kernel32.WaitForSingleObject(process,7000)==0:report['graceful_closes']=report.get('graceful_closes',0)+1
                else:
                    report.setdefault('cleanup_warnings',[]).append('Owned test process required termination')
                    if not kernel32.TerminateProcess(process,1) or kernel32.WaitForSingleObject(process,5000)!=0:raise RuntimeError('Owned process cleanup failed')
        finally:kernel32.CloseHandle(process);process=hwnd=app_pid=None
    def source_digest():return {str(p.relative_to(target/'media')):(p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest()) for p in (target/'media').rglob('*') if p.is_file()}
    def expand_options():
        ui('inspect','ExpandSearchOptions','--json');ui('invoke','ExpandSearchOptions','--action','expand')
        ui('wait-for','CmbSearchRoot','-t','5000')
    def choose(combo,option):
        ui('inspect',combo,'--json');ui('scroll-into-view',combo);ui('invoke',combo,'--action','expand')
        for _ in range(30):
            windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
            popups=[w for w in windows if w.get('title')=='PopupHost']
            if len(popups)==1:break
            time.sleep(.1)
        if len(popups)!=1:raise RuntimeError('Expected one owned popup')
        popup=str(popups[0]['hwnd']);tree=json.loads(cli('ui','inspect','--json','--depth','12','-w',popup))
        matches={n['selector']:n for n in nodes(tree) if n.get('selector') and (n.get('automationId')==option or n.get('type')=='ListItem' and n.get('name')==option)}
        if len(matches)!=1:raise RuntimeError('Expected exact popup option '+option)
        cli('ui','invoke',next(iter(matches)),'--action','select','-w',popup)
        time.sleep(.6)
    def root_settings(root):
        identifier='NavRoot'+str(root);ui('inspect',identifier,'--json')
        ui('scroll-into-view',identifier);ui('click',identifier,'--right')
        # MenuFlyout may be on the main XAML surface or an owned PopupHost.
        # Inspect only windows from the captured test PID, never another app.
        candidates=[]
        windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
        (target/'root-menu-windows.json').write_text(json.dumps(windows,ensure_ascii=False,indent=2),encoding='utf-8')
        # Main-window UIA trees can also contain the owned popup. Prefer the
        # popup's own HWND so the same menu is not counted twice.
        ordered=[w for w in windows if w.get('title')=='PopupHost']+[w for w in windows if str(w.get('hwnd'))==hwnd]
        for window in ordered:
            handle=str(window['hwnd'])
            try:
                tree=json.loads(cli('ui','inspect','--json','--depth','16','-w',handle))
            except RuntimeError as error:
                # A tooltip can be listed as PopupHost, then expire before UIA
                # inspection. Only skip that specific missing auxiliary HWND;
                # main-window errors and every other CLI failure still fail.
                if handle!=hwnd and 'AppNotFoundException' in str(error):
                    report.setdefault('expired_auxiliary_windows',[]).append(handle)
                    continue
                raise
            (target/('root-menu-'+handle+'.json')).write_text(json.dumps(tree,ensure_ascii=False,indent=2),encoding='utf-8')
            if any(n.get('automationId')=='ManageRoot'+str(root) for n in nodes(tree)):
                candidates.append(handle)
                report['root_menu_window']={'hwnd':handle,'title':window.get('title')}
                break
        if len(candidates)!=1:raise RuntimeError('Expected one owned root settings menu')
        cli('ui','invoke','ManageRoot'+str(root),'-w',candidates[0])
        wait('RootList',str(folders['characters']))
        check('Sidebar context menu selects intended folder',True)
    def query(value,count):
        ui('set-value','TxtQuery',value)
        # TextChanged starts a 300ms search. Let that render settle before the
        # explicit button check, then refresh UIA's peer rather than reusing it.
        time.sleep(.45);ready();ui('inspect','BtnSearch','--json')
        ui('invoke','BtnSearch');ready();wait('TxtCount',count)
    def tree_names():return [str(n.get('name','')) for n in nodes(json.loads(ui('inspect','--json','--depth','18')))]
    try:
        existing=subprocess.run(['powershell','-NoProfile','-Command','if(Get-Process Aredoko.WinUI -ErrorAction SilentlyContinue){exit 1}'],capture_output=True)
        if existing.returncode:raise RuntimeError('Existing user app; never attach or stop it')
        server=ThreadingHTTPServer(('127.0.0.1',8769),production_handler)
        media=target/'media';media.mkdir()
        folders={name:media/name for name in ('characters','outside','existing-shelf','new-shelf')}
        png=graphic({'background':'white','objects':[{'shape':'circle','color':'blue','x':90,'y':120,'sx':40,'sy':40}]})
        for folder in folders.values():folder.mkdir()
        for i in range(6):(folders['characters']/f'neutral-{i}.png').write_bytes(png)
        for name in ('outside','existing-shelf','new-shelf'):(folders[name]/'generated.png').write_bytes(png)
        original=source_digest();expected_source=dict(original)
        catalog=ProductionCatalog(target/'catalog.sqlite');a=catalog.add_root(str(folders['characters']),excludes=['*.ignore-a']);b=catalog.add_root(str(folders['outside']),excludes=['*.ignore-b'],default_shelf='AI画像')
        root_exclusions=next(root for root in catalog.index.roots() if root['id']==a)['excludes']
        for root in (a,b):catalog.start_scan(root);catalog._worker.join(20);check('Generated root scan '+str(root),catalog.scan_state()['state']=='complete')
        rows=catalog.search(root_id=a)['items'];catalog.update([rows[0]['id']],{'tags':['初音ミク']})
        rows=catalog.search(root_id=a)['items'];encoder=ContractEncoder();engine=RecordedAI(catalog,encoder)
        import math
        from ai_search import revision
        for row,score in zip(rows,[.9,.89,.88,.2,.19,.18]):
            vec=[score,math.sqrt(1-score*score)]+[0.0]*6;engine.store.put(row['id'],revision(row),{'text':vec,'cover':vec})
        outside=catalog.search(root_id=b)['items'][0];engine.store.put(outside['id'],revision(outside),{'text':[.6,.8]+[0.0]*6,'cover':[.6,.8]+[0.0]*6})
        settings=target/'settings.json';settings.write_text(json.dumps({'version':1,'profile':'default','scope':{'root_ids':None,'kind':'','shelf':None}}),encoding='utf-8');settings_before=settings.read_bytes()
        profiles=AIProfileSettings(REPO,settings);handler=production_handler(catalog,secrets.token_urlsafe(32),engine,profiles=profiles)
        class Quiet(handler):
            def log_message(self,*args):pass
        server.RequestHandlerClass=Quiet;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        for theme in ('Light','Dark'):
            launch=json.loads(cli('run','src/Aredoko.WinUI','-c','Release','--arch','x64','-p','Platform=x64','-p','SelfContained=true','--no-build','--output-appx-directory',str(target/('layout-'+theme.lower())),'--detach','--json','--args','--ui-theme '+theme.lower()))
            if launch.get('ProcessScope') not in (None,'local'):raise RuntimeError('Wrong target')
            app_pid=int(launch['ProcessId']);process=kernel32.OpenProcess(0x00100001,False,app_pid)
            if not process:raise RuntimeError('Owned process unavailable')
            for _ in range(60):
                windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'));main=[w for w in windows if w.get('hwnd') and w.get('title')!='PopupHost']
                if len(main)==1:break
                time.sleep(.2)
            if len(main)!=1:raise RuntimeError('Unique owned main window unavailable')
            hwnd=str(main[0]['hwnd']);ready();query('', '7 件' if theme=='Light' else '9 件')
            audit(theme+'-initial',('TxtQuery','BtnSearch','BtnRoots','ItemList'))
            ui('invoke','NavRoot'+str(a));ready();wait('TxtCount','6 件');check(theme+' sidebar folder filter',True)
            query('初音ミク','1 件');choose('CmbSearchMode','ModeVisual');ui('invoke','BtnSearch');ready();wait('TxtCount','3 件')
            check(theme+' automatic upper candidates only',set(r['id'] for r in catalog.search(root_id=a)['items'][:3])==set(r['id'] for r in engine.search('初音ミク',source='cover',scope={'root_ids':[a]},result_group='leading')['items']))
            check(theme+' AI evidence shown',any('類似度' in n and '0.900' in n for n in tree_names()));shot(theme+'-leading-wide')
            expand_options();choose('CmbAIResultGroup','その他の参考候補');ui('invoke','BtnSearch');ready();wait('TxtCount','3 件');check(theme+' reference candidates separated',not any('0.900' in n for n in tree_names()));shot(theme+'-other-wide')
            expand_options();choose('CmbAIResultGroup','すべてのAI候補');ui('invoke','BtnSearch');ready();wait('TxtCount','6 件');check(theme+' all AI candidates available',True)
            ui('invoke','BtnLayout');shot(theme+'-all-grid-wide')
            expand_options();ui('set-value','NumSimilarityBoundary','0.85');ui('focus','BtnSearch');ui('invoke','BtnSearch');ready();wait('TxtCount','6 件')
            expand_options();choose('CmbAIResultGroup','上位の類似候補');ui('invoke','BtnSearch');ready();wait('TxtCount','3 件');check(theme+' manual similarity boundary',math.isclose(engine.requests[-1].get('group_threshold',-2),.85,abs_tol=1e-6))
            ui('invoke','Item'+str(rows[0]['id']),'--action','select');wait('TxtEditStatus','保存済み');ui('set-value','TxtTags','unsaved-folder');wait('TxtEditStatus','未保存の変更')
            ui('invoke','NavRoot'+str(b));ui('wait-for','PrimaryButton','-t','5000');ui('invoke','CloseButton');ready();wait('TxtTags','unsaved-folder');check(theme+' cancelled folder navigation preserves draft',True)
            ui('invoke','NavRoot'+str(b));ui('wait-for','PrimaryButton','-t','5000');ui('invoke','PrimaryButton');ready();wait('TxtCount','0 件');check(theme+' manual boundary honors selected root',True)
            choose('CmbSearchMode','ModeLiteral');query('','1 件');ui('invoke','NavAll');ready();wait('TxtCount','7 件' if theme=='Light' else '9 件');check(theme+' all-folder search restored',True)
            resize(700,620);shot(theme+'-literal-narrow');resize(1200,820)
            if theme=='Light':
                ui('invoke','BtnRoots');ui('wait-for','RootPath','-t','5000');ui('set-value','RootPath',str(folders['existing-shelf']));choose('RootInitialShelf','AI画像');ui('scroll-into-view','AddRoot');ui('invoke','AddRoot')
                wait('ScanStatus','登録しました。スキャンすると一覧に反映されます。');ui('scroll-into-view','ScanRoot');ui('invoke','ScanRoot')
                for _ in range(100):
                    if catalog.scan_state()['state']=='complete' and catalog.search()['total']==8:break
                    time.sleep(.1)
                check('GUI registration to existing shelf',catalog.search()['total']==8 and next(r for r in catalog.search()['items'] if r['root_id'] not in (a,b))['shelf']=='AI画像')
                ui('set-value','RootPath',str(folders['new-shelf']));choose('RootInitialShelf','新しい棚を作成');ui('set-value','RootNewShelf','背景');ui('scroll-into-view','AddRoot');ui('invoke','AddRoot');wait('ScanStatus','登録しました。スキャンすると一覧に反映されます。');ui('scroll-into-view','ScanRoot');ui('invoke','ScanRoot')
                for _ in range(100):
                    if catalog.scan_state()['state']=='complete' and catalog.search()['total']==9:break
                    time.sleep(.1)
                check('GUI registration creates new shelf',catalog.search()['total']==9 and '背景' in catalog.shelves());wait('RootInitialShelf','背景');check('Newly registered shelf matches visible settings',True);shot('Light-root-settings-wide')
                ui('invoke','CloseButton');ready();wait('TxtCount','9 件')
                # Use the same folder settings surface reached from the sidebar.
                ui('invoke','NavRoot'+str(a));ready();wait('TxtCount','6 件');root_settings(a)
                ui('invoke','FillUnsetShelf');choose('RootList',str(folders['outside']));wait('FillUnsetShelf','Off');check('Folder change resets bulk-fill consent',True)
                choose('RootList',str(folders['characters']));choose('RootInitialShelf','AI画像');ui('invoke','FillUnsetShelf');ui('scroll-into-view','SaveRootShelf');ui('invoke','SaveRootShelf')
                for _ in range(50):
                    if all(r['shelf']=='AI画像' for r in catalog.search(root_id=a)['items']):break
                    time.sleep(.1)
                check('Explicit empty-shelf fill',all(r['shelf']=='AI画像' for r in catalog.search(root_id=a)['items']))
                ui('scroll-into-view','UnregisterConsent');ui('invoke','UnregisterConsent');ui('scroll-into-view','UnregisterRoot');ui('invoke','UnregisterRoot')
                for _ in range(50):
                    if not any(root['id']==a for root in catalog.index.roots()):break
                    time.sleep(.1)
                check('GUI unregister hides root and retains annotations',not any(root['id']==a for root in catalog.index.roots()) and catalog.get(rows[0]['id'])['tags']==['初音ミク'])
                shot('Light-unregister-wide');ui('invoke','CloseButton');ready();wait('TxtCount','3 件')
                ui('invoke','NavRestoreRoot'+str(a));ui('wait-for','RootPath','--value',str(folders['characters']),'-t','5000');wait('RootExcludes',', '.join(root_exclusions));wait('RootInitialShelf','AI画像');check('Sidebar restore prefills own path, exclusions and shelf',True)
                ui('scroll-into-view','AddRoot');ui('invoke','AddRoot');wait('ScanStatus','登録しました。スキャンすると一覧に反映されます。');ui('invoke','CloseButton');ready();wait('TxtCount','9 件');check('Same root restored with tags and shelf',catalog.get(rows[0]['id'])['shelf']=='AI画像' and catalog.get(rows[0]['id'])['tags']==['初音ミク']);check('Restored root keeps its own exclusions',next(root for root in catalog.index.roots() if root['id']==a)['excludes']==root_exclusions)
            close()
        check('Settings bytes unchanged',settings.read_bytes()==settings_before)
        check('Generated source bytes and mtimes unchanged',source_digest()==original)
        report['requests']=engine.requests;report['pass']=True
    except Exception as error:
        report['error']=str(error)
        if engine:report['requests']=engine.requests
        if hwnd:
            try:shot('failure')
            except Exception:pass
        raise
    finally:
        try:
            released.set() if 'released' in locals() else None
            if hwnd:
                try:ui('invoke','CloseButton')
                except RuntimeError:pass
            close()
            if thread:server.shutdown();thread.join(5)
            if server:server.server_close()
            if engine:engine.close()
        except Exception as error:report['pass']=False;report['cleanup_error']=str(error);raise
        finally:
            try:
                if catalog:catalog.close()
                cli('ui','yield')
            except Exception as error:report['pass']=False;report['cleanup_error']=str(error);raise
            finally:
                report['source_boundary_verified']=bool(original) and source_digest()==original
                if not report['source_boundary_verified']:report['pass']=False
                (target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'pass':report['pass'],'checks':len(report['checks']),'keys':len(report['keyboard_actions']),'skipped':len(report['keyboard_skipped'])}))
    if not report['pass']:raise RuntimeError('Native checks failed')

if __name__=='__main__':main()
