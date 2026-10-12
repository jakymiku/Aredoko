"""Owned native keyboard/accessibility checks on generated media only.

Built x64 Release required. No models, downloads, OS settings or private media.
Physical input is guarded by owned HWND/PID and verified foreground; denied
activation is recorded as skipped, never claimed as keyboard coverage.
"""
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
    env={**os.environ,'WINAPP_UI_WORKFLOW_ID':'aredoko-keyboard-'+uuid.uuid4().hex}
    report={'pass':False,'target':'local','actual_model':False,'checks':[],'screenshots':[],'keyboard_actions':[],'keyboard_skipped':[],'display':[],'audit_scope':'main toolbar, selected editor and discard dialog; not whole-app/screen-reader audit'}
    catalog=engine=server=thread=None;hwnd=app_pid=process=None;original={}
    save_fault={'fail':False,'delay':False};save_entered=threading.Event();save_release=threading.Event()
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
        # Move only over this owned app's harmless reconnect button so the
        # close-button tooltip cannot obscure/extend the window capture.
        ui('hover','BtnReconnect');time.sleep(.8)
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
    def source_digest():return {p.name:(p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest()) for p in (target/'media').glob('*.png')}
    try:
        existing=subprocess.run(['powershell','-NoProfile','-Command','if(Get-Process Aredoko.WinUI -ErrorAction SilentlyContinue){exit 1}'],capture_output=True)
        if existing.returncode:raise RuntimeError('Existing app; never attach to its data')
        server=ThreadingHTTPServer(('127.0.0.1',8769),production_handler)
        media=target/'media';media.mkdir()
        png=graphic({'background':'white','objects':[{'shape':'circle','color':'red','x':90,'y':120,'sx':40,'sy':40}]})
        for i in range(65):(media/f'generated-{i:02}.png').write_bytes(png)
        original=source_digest();catalog=ProductionCatalog(target/'catalog.sqlite')
        root=catalog.add_root(str(media));catalog.start_scan(root);catalog._worker.join(20)
        check('Generated scan complete',catalog.scan_state()['state']=='complete' and catalog.search()['total']==65)
        first=catalog.search()['items'][0]['id']
        settings=target/'settings.json';settings.write_text(json.dumps({'version':1,'profile':'default','scope':{'root_ids':[root],'kind':'','shelf':None}}),encoding='utf-8');settings_before=settings.read_bytes()
        encoder=ContractEncoder();engine=RecordedAI(catalog,encoder);profiles=AIProfileSettings(REPO,settings)
        # Test-only catalog faults retain the real handler's token/Origin/body
        # validation and production response handling. Never affect user data.
        original_update=catalog.update
        def controlled_update(ids,changes):
            if save_fault['fail']:
                save_fault['fail']=False
                report['injected_save_failures']=report.get('injected_save_failures',0)+1
                raise ScanBusyError('Generated test save failure')
            if save_fault['delay']:
                save_fault['delay']=False;save_entered.set()
                if not save_release.wait(30):raise ScanBusyError('Generated delay timed out')
                report['delayed_saves']=report.get('delayed_saves',0)+1
            return original_update(ids,changes)
        catalog.update=controlled_update
        handler=production_handler(catalog,secrets.token_urlsafe(32),engine,profiles=profiles)
        class Quiet(handler):
            def log_message(self,*args):pass
        server.RequestHandlerClass=Quiet;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        for theme in ('Light','Dark'):
            launch=json.loads(cli('run','src/Aredoko.WinUI','-c','Release','--arch','x64','-p','Platform=x64','-p','SelfContained=true','--no-build','--detach','--json','--args','--ui-theme '+theme.lower()))
            if launch.get('ProcessScope') not in (None,'local'):raise RuntimeError('Wrong target')
            app_pid=int(launch['ProcessId']);process=kernel32.OpenProcess(0x00100001,False,app_pid)
            if not process:raise RuntimeError('Owned process handle unavailable')
            for _ in range(50):
                windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
                main=[w for w in windows if 'Aredoko' in w.get('title','') and w.get('title')!='PopupHost']
                if len(main)==1:break
                time.sleep(.1)
            if len(main)!=1:raise RuntimeError('Expected one owned main window')
            hwnd=str(main[0]['hwnd']);ready();resize(1200,820);wait('TxtCount','65 件')
            class Contrast(ctypes.Structure):_fields_=[('cbSize',wintypes.UINT),('flags',wintypes.DWORD),('scheme',wintypes.LPWSTR)]
            contrast=Contrast();contrast.cbSize=ctypes.sizeof(contrast)
            if not user32.SystemParametersInfoW(0x0042,contrast.cbSize,ctypes.byref(contrast),0):raise ctypes.WinError(ctypes.get_last_error())
            report['display'].append({'theme':theme,'dpi':user32.GetDpiForWindow(int(hwnd)),'high_contrast':bool(contrast.flags&1)})
            audit(theme+'-main',('TxtQuery','BtnSearch','CmbKind','CmbSearchMode','BtnRoots','BtnAIIndex','BtnLayout','ItemList','BtnNext','BtnReconnect'))
            if keys('ctrl+f','BtnSearch'):focus_assert('TxtQuery');check(theme+' physical Ctrl+F focuses query',True)
            if keys('tab','TxtQuery'):focus_assert('BtnSearch');check(theme+' physical Tab query to search',True)
            if keys('shift+tab','BtnSearch'):focus_assert('TxtQuery');check(theme+' physical Shift+Tab restores query',True)
            physical=keys('ctrl+a text=generated-64','TxtQuery')
            if not physical:ui('set-value','TxtQuery','generated-64')
            ready();wait('TxtCount','1 件');check(theme+(' physical' if physical else ' UIA')+' literal search',True)
            physical=keys('ctrl+a backspace','TxtQuery')
            if not physical:ui('set-value','TxtQuery','')
            ready();wait('TxtCount','65 件');wait('TxtPageNumber','1 / 2')
            physical=keys('enter','BtnNext')
            if not physical:ui('invoke','BtnNext')
            ready();wait('TxtPageNumber','2 / 2');check(theme+(' physical' if physical else ' UIA')+' next page',True)
            physical=keys('enter','BtnPrevious')
            if not physical:ui('invoke','BtnPrevious')
            ready();wait('TxtPageNumber','1 / 2')
            physical=keys('space','Item'+str(first))
            if not physical:ui('invoke','Item'+str(first),'--action','select')
            wait('TxtEditStatus','保存済み');check(theme+(' physical' if physical else ' UIA')+' list selection opens editor',True)
            audit(theme+'-editor',('TxtTags','TxtShelf','ChkFavorite','ChkReviewed','BtnSave','BtnCloseDetails'))
            favorite_before=catalog.search()['items'][0]['favorite']
            tags='keyboard-'+theme.lower();physical=keys('ctrl+a text='+tags,'TxtTags')
            if not physical:ui('set-value','TxtTags',tags)
            wait('TxtEditStatus','未保存の変更')
            if keys('tab','TxtTags'):focus_assert('TxtShelf');check(theme+' physical Tab tags to shelf',True)
            physical=keys('space','ChkFavorite')
            if not physical:ui('invoke','ChkFavorite','--action','toggle')
            physical=keys('ctrl+s','TxtShelf')
            if not physical:ui('invoke','BtnSave')
            wait('TxtEditStatus','保存しました');check(theme+(' physical' if physical else ' UIA')+' save persisted',catalog.search()['items'][0]['tags']==[tags] and catalog.search()['items'][0]['favorite']==(not favorite_before))
            if physical:
                focus_assert('TxtShelf');check(theme+' save retains shelf keyboard focus',True)
            # Failed save retains edits/focus and leaves persisted metadata alone.
            before=catalog.search()['items'][0]['tags'];failed_tags=tags+'-retry'
            physical=keys('ctrl+a text='+failed_tags,'TxtTags')
            if not physical:ui('set-value','TxtTags',failed_tags)
            save_fault['fail']=True;physical=keys('ctrl+s','TxtTags')
            if not physical:ui('invoke','BtnSave')
            wait('TxtEditStatus','保存できませんでした。変更内容は残っています。')
            wait('TxtTags',failed_tags)
            check(theme+' failed save leaves DB and edits intact',catalog.search()['items'][0]['tags']==before)
            if physical:focus_assert('TxtTags');check(theme+' failed save retains tag keyboard focus',True)
            shot(theme+'-save-error-wide')
            physical=keys('enter','BtnSave')
            if not physical:ui('invoke','BtnSave')
            wait('TxtEditStatus','保存しました');tags=failed_tags
            check(theme+' retry saves retained edits',catalog.search()['items'][0]['tags']==[tags])
            if physical:focus_assert('TxtTags');check(theme+' disabled save button falls back to tags',True)
            # While an authenticated save is pending, explicitly choosing the
            # query control via UIA must not be undone by save completion.
            tags+='-delayed';physical=keys('ctrl+a text='+tags,'TxtTags')
            if not physical:ui('set-value','TxtTags',tags)
            save_entered.clear();save_release.clear();save_fault['delay']=True
            physical=keys('ctrl+s','TxtTags')
            if not physical:ui('invoke','BtnSave')
            check(theme+' delayed save started',save_entered.wait(5))
            ui('focus','TxtQuery');focus_assert('TxtQuery');save_release.set()
            wait('TxtEditStatus','保存しました');focus_assert('TxtQuery')
            check(theme+' UIA focus chosen during save is preserved',catalog.search()['items'][0]['tags']==[tags])
            shot(theme+'-saved-wide')
            # Mode changes can close the pane. Reopen explicitly; this does
            # not verify automatic open-state retention across resize.
            resize(700,620);ui('invoke','BtnDetails');wait('TxtTags',tags)
            tree=json.loads(ui('inspect','--json','--depth','16'))
            footer=[n for n in nodes(tree) if n.get('automationId')=='BtnSave']
            check(theme+' narrow fixed save footer is onscreen',len(footer)==1 and footer[0].get('isOffscreen') is False)
            shot(theme+'-saved-list-narrow')
            resize(1200,820);ui('invoke','BtnDetails');wait('TxtTags',tags)
            physical=keys('esc','TxtTags')
            if not physical:ui('invoke','BtnCloseDetails')
            ui('wait-for','BtnDetails','-p','IsEnabled','--value','False','-t','5000')
            if physical:
                focused=[json.loads(ui('get-property',identifier,'--property','HasKeyboardFocus','--json')) for identifier in ('ItemList','Item'+str(first))]
                report.setdefault('focus_return',[]).append({'theme':theme,'properties':focused})
                check(theme+' physical Escape returns focus to list',any(focused_property(x) for x in focused))
            resize(700,620)
            physical=keys('enter','BtnLayout')
            if not physical:ui('invoke','BtnLayout')
            wait('BtnLayout','リスト表示')
            physical=keys('space','Item'+str(first))
            if not physical:ui('invoke','Item'+str(first),'--action','select')
            wait('TxtEditStatus','保存済み');check(theme+(' physical' if physical else ' UIA')+' grid selection opens editor',True)
            shot(theme+'-selected-grid-narrow')
            physical=keys('ctrl+a text=unsaved-keyboard','TxtTags')
            if not physical:ui('set-value','TxtTags','unsaved-keyboard')
            wait('TxtEditStatus','未保存の変更')
            physical=keys('esc','TxtTags')
            if not physical:ui('invoke','BtnCloseDetails')
            ui('wait-for','CloseButton','-t','5000');audit(theme+'-discard',('PrimaryButton','CloseButton'));shot(theme+'-discard-narrow')
            physical=keys('esc','CloseButton')
            if not physical:ui('invoke','CloseButton')
            wait('TxtTags','unsaved-keyboard');wait('TxtEditStatus','未保存の変更')
            check(theme+(' physical' if physical else ' UIA')+' dialog cancel preserves edit',catalog.search()['items'][0]['tags']==[tags])
            physical=keys('esc','TxtTags')
            if not physical:ui('invoke','BtnCloseDetails')
            ui('wait-for','CloseButton','-t','5000')
            physical=keys('shift+tab enter','CloseButton')
            if not physical:ui('invoke','PrimaryButton')
            ui('wait-for','BtnDetails','-p','IsEnabled','--value','False','-t','5000')
            check(theme+(' physical' if physical else ' UIA')+' discard leaves saved tags',catalog.search()['items'][0]['tags']==[tags]);shot(theme+'-closed-narrow')
            close()
        check('Failure and delayed save fixtures exercised',report.get('injected_save_failures')==2 and report.get('delayed_saves')==2)
        check('No AI inference or worker',not engine.encoder.resident and not engine.encoder.calls and not engine.requests)
        check('Settings bytes unchanged',settings.read_bytes()==settings_before)
        check('Source bytes and mtime unchanged',original==source_digest())
        report['keyboard_verification']='partial' if report['keyboard_skipped'] else 'tested paths passed'
        report['high_dpi_verification']='observed' if any(x['dpi']>96 for x in report['display']) else 'not tested; actual windows stayed at DPI96'
        report['contrast_verification']='observed' if any(x['high_contrast'] for x in report['display']) else 'not tested; actual system contrast off'
        report['pass']=True
    except Exception as error:
        report['error']=str(error)
        if hwnd:
            try:shot('failure')
            except Exception:pass
        raise
    finally:
        try:
            save_release.set()
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
                report['source_hashes_mtime_unchanged']=bool(original) and original==source_digest()
                if not report['source_hashes_mtime_unchanged']:report['pass']=False
                (target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'pass':report['pass'],'checks':len(report['checks']),'keyboard_actions':len(report['keyboard_actions']),'skipped':len(report['keyboard_skipped'])}))
    if not report['pass']:raise RuntimeError('Native checks failed')

if __name__=='__main__':main()
