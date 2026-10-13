"""Owned related-term and archive-reader checks on generated media only.

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
    report={'pass':False,'target':'local','actual_model':False,'checks':[],'screenshots':[],'keyboard_actions':[],'keyboard_skipped':[],'display':[],'audit_scope':'related-term dialog/search and modal archive reader; not whole-app audit'}
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
    def source_digest():return {p.name:(p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest()) for p in (target/'media').glob('*') if p.is_file()}
    try:
        existing=subprocess.run(['powershell','-NoProfile','-Command','if(Get-Process Aredoko.WinUI -ErrorAction SilentlyContinue){exit 1}'],capture_output=True)
        if existing.returncode:raise RuntimeError('Existing app; never attach to its data')
        server=ThreadingHTTPServer(('127.0.0.1',8769),production_handler)
        media=target/'media';media.mkdir()
        colors={name:graphic({'background':'white','objects':[{'shape':'circle','color':name,'x':90,'y':120,'sx':40,'sy':40}]}) for name in ('red','blue','green')}
        def book(name,extra=False,broken=False):
            with zipfile.ZipFile(media/name,'w') as archive:
                for filename,data in [('page10.png',b'not an image' if broken else colors['blue']),('page2.png',colors['red']),('page20.png',colors['green'])]+([('page30.png',colors['red'])] if extra else []):
                    entry=zipfile.ZipInfo(filename,date_time=(2000,1,1,0,0,0));archive.writestr(entry,data)
        book('book.cbz');book('broken.zip',broken=True)
        (media/'neutral-1.png').write_bytes(colors['red']);(media/'neutral-2.png').write_bytes(colors['blue'])
        original=source_digest();expected_source=dict(original)
        catalog=ProductionCatalog(target/'catalog.sqlite');root=catalog.add_root(str(media));catalog.start_scan(root);catalog._worker.join(20)
        check('Generated scan complete',catalog.scan_state()['state']=='complete' and catalog.search()['total']==4)
        ids={x['title']:x['id'] for x in catalog.search()['items']}
        catalog.update([ids['neutral-1.png']],{'tags':['東方','巫女']});catalog.update([ids['neutral-2.png']],{'tags':['博麗霊夢']})
        settings=target/'settings.json';settings.write_text(json.dumps({'version':1,'profile':'default','scope':{'root_ids':[root],'kind':'','shelf':None}}),encoding='utf-8');settings_before=settings.read_bytes()
        encoder=ContractEncoder();engine=RecordedAI(catalog,encoder);profiles=AIProfileSettings(REPO,settings)
        token=secrets.token_urlsafe(32);handler=production_handler(catalog,token,engine,profiles=profiles)
        faults={'code':None,'delay':False,'term_delay':False};entered=threading.Event();released=threading.Event()
        class Quiet(handler):
            def log_message(self,*args):pass
            def do_POST(self):
                origin='http://127.0.0.1:'+str(self.server.server_port)
                valid=self.valid_host() and self.headers.get('Origin')==origin and self.headers.get('X-Aredoko-Token')==token
                if valid and self.path=='/api/library/terms' and faults['term_delay']:
                    faults['term_delay']=False;entered.set()
                    if not released.wait(25):return self.send(503,{'error':'Generated delay timeout'})
                return super().do_POST()
            def do_GET(self):
                path=urlparse(self.path).path
                valid=self.valid_host() and self.headers.get('X-Aredoko-Token')==token
                if valid and '/reader/' in path and '/pages/' in path:
                    report.setdefault('reader_requests',[]).append(path)
                    if faults['code']:
                        code=faults['code'];faults['code']=None
                        report.setdefault('injected_codes',[]).append(code);return self.send(code,{'error':'Generated reader failure'})
                    if faults['delay']:
                        faults['delay']=False;entered.set()
                        if not released.wait(25):return self.send(503,{'error':'Generated delay timeout'})
                try:return super().do_GET()
                except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
                    report['cancelled_response_writes']=report.get('cancelled_response_writes',0)+1
        server.RequestHandlerClass=Quiet;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def prop(identifier,name,value):ui('wait-for',identifier,'-p',name,'--value',str(value),'-t','10000')
        def tree_names():return [str(n.get('name','')) for n in nodes(json.loads(ui('inspect','--json','--depth','18')))]
        def query(value,count):
            ui('set-value','TxtQuery',value);ui('invoke','BtnSearch');ready();wait('TxtCount',count)
        def select(item):
            ui('invoke','Item'+str(item),'--action','select');wait('TxtEditStatus','保存済み')
        def open_reader():
            ui('focus','BtnOpenBook');ui('invoke','BtnOpenBook');wait('ReaderStatus','表示しました。拡大すると細部を確認できます。')
        def close_reader():
            physical=keys('esc','CloseButton')
            if not physical:ui('invoke','CloseButton')
            ui('wait-for','ArchiveReaderDialog','--gone','-t','5000')
            return physical
        for theme in ('Light','Dark'):
            if theme=='Dark':
                check('Dictionary persisted between app launches',len(catalog.terms.entries())==2)
                book('book.cbz');expected_source=source_digest();catalog.start_scan(root);catalog._worker.join(20)
                report.setdefault('intentional_fixture_changes',[]).append('Reset generated book to three pages before Dark launch')
            launch=json.loads(cli('run','src/Aredoko.WinUI','-c','Release','--arch','x64','-p','Platform=x64','-p','SelfContained=true','--no-build','--output-appx-directory',str(target/('layout-'+theme.lower())),'--detach','--json','--args','--ui-theme '+theme.lower()))
            if launch.get('ProcessScope') not in (None,'local'):raise RuntimeError('Wrong target')
            app_pid=int(launch['ProcessId']);process=kernel32.OpenProcess(0x00100001,False,app_pid)
            if not process:raise RuntimeError('Owned process handle unavailable')
            for _ in range(50):
                windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'));main=[w for w in windows if 'Aredoko' in w.get('title','') and w.get('title')!='PopupHost']
                if len(main)==1:break
                time.sleep(.1)
            if len(main)!=1:raise RuntimeError('Expected one owned main window')
            hwnd=str(main[0]['hwnd']);ready();resize(1200,820);wait('TxtCount','4 件')
            class Contrast(ctypes.Structure):_fields_=[('cbSize',wintypes.UINT),('flags',wintypes.DWORD),('scheme',wintypes.LPWSTR)]
            contrast=Contrast();contrast.cbSize=ctypes.sizeof(contrast)
            if not user32.SystemParametersInfoW(0x0042,contrast.cbSize,ctypes.byref(contrast),0):raise ctypes.WinError(ctypes.get_last_error())
            report['display'].append({'theme':theme,'dpi':user32.GetDpiForWindow(int(hwnd)),'high_contrast':bool(contrast.flags&1)})
            audit(theme+'-main',('TxtQuery','BtnSearch','BtnRelatedTerms','BtnLayout','ItemList'))
            query('東方 巫女','1 件' if theme=='Light' else '2 件')
            ui('invoke','BtnRelatedTerms');ui('wait-for','RelatedTerm','-t','5000')
            audit(theme+'-terms',('RelatedTerm','RelatedAliases','RelatedWords','SaveRelatedTerm','DeleteRelatedTerm','RelatedTermList','ExportRelatedTerms','ImportRelatedTerms'))
            ui('set-value','RelatedTerm','博麗霊夢');ui('set-value','RelatedAliases','霊夢、reimu');ui('set-value','RelatedWords','東方、巫女')
            ui('scroll-into-view','SaveRelatedTerm');ui('invoke','SaveRelatedTerm');wait('RelatedTermStatus','保存しました。次の名前・タグ検索から使われます。')
            # Add a second term while testing the actual editor, not the API alone.
            ui('set-value','RelatedTerm','雨の背景');ui('set-value','RelatedAliases','rain');ui('set-value','RelatedWords','雨、背景')
            entered.clear();released.clear();faults['term_delay']=True
            ui('invoke','SaveRelatedTerm');check(theme+' delayed dictionary save started',entered.wait(5))
            prop('RelatedTerm','IsEnabled','False');prop('RelatedAliases','IsEnabled','False');prop('RelatedWords','IsEnabled','False')
            check(theme+' busy dictionary fields disabled',True)
            ui('invoke','CloseButton');ui('wait-for','RelatedTerm','-t','5000');check(theme+' busy dictionary close deferred',True)
            released.set();wait('RelatedTermStatus','保存しました。次の名前・タグ検索から使われます。')
            prop('SaveRelatedTerm','IsEnabled','True')
            for _ in range(50):
                if len(catalog.terms.entries())==2:break
                time.sleep(.1)
            check(theme+' dictionary writes persisted',len(catalog.terms.entries())==2)
            shot(theme+'-terms-wide');resize(700,620);shot(theme+'-terms-narrow')
            ui('invoke','CloseButton');ready();wait('TxtCount','2 件')
            names=tree_names();check(theme+' related candidate reason shown',any('関連語の候補' in n for n in names))
            observed=catalog.search('東方 巫女')['items'];check(theme+' direct hit before related',[(x['id'],x['match']) for x in observed]==[(ids['neutral-1.png'],'direct'),(ids['neutral-2.png'],'related')])
            shot(theme+'-related-narrow')
            query('東方 宇宙','2 件');names=tree_names();check(theme+' partial results disclosed',any('一部の語のみ一致' in n for n in names) and any('2語すべてに一致' in n for n in names));shot(theme+'-partial-narrow')
            query(' '.join('w'+str(i) for i in range(17)),'—');names=tree_names();check(theme+' Japanese word-limit error',any('検索語は16語まで' in n for n in names));shot(theme+'-error-narrow')
            query('','4 件');resize(1200,820);select(ids['book.cbz']);ui('set-value','TxtTags','unsaved-reader');wait('TxtEditStatus','未保存の変更')
            before=catalog.get(ids['book.cbz'])['tags'];open_reader();wait('ReaderPageNumber','1 / 3');prop('ReaderPrevious','IsEnabled','False')
            audit(theme+'-reader',('ReaderViewport','ReaderPrevious','ReaderNext','ReaderRetry','ReaderReopen','CloseButton'))
            physical=keys('ctrl+s','CloseButton');check(theme+(' reader blocks background save' if physical else ' reader metadata unchanged; save input skipped'),catalog.get(ids['book.cbz'])['tags']==before)
            if physical:focus_assert('CloseButton');check(theme+' save shortcut stays within modal',True)
            if keys('ctrl+f','CloseButton'):focus_assert('CloseButton');check(theme+' search shortcut stays within modal',True)
            shot(theme+'-reader-first-wide')
            ui('invoke','ReaderNext');wait('ReaderPageNumber','2 / 3');wait('ReaderStatus','表示しました。拡大すると細部を確認できます。');shot(theme+'-reader-second-wide')
            resize(700,620);ui('invoke','ReaderNext');wait('ReaderPageNumber','3 / 3');wait('ReaderStatus','表示しました。拡大すると細部を確認できます。');prop('ReaderNext','IsEnabled','False');shot(theme+'-reader-last-narrow')
            physical=close_reader();wait('TxtTags','unsaved-reader');wait('TxtEditStatus','未保存の変更')
            check(theme+' reader close retains metadata draft',catalog.get(ids['book.cbz'])['tags']==before)
            if physical:focus_assert('BtnOpenBook');check(theme+' reader Escape restores opener focus',True)
            ui('invoke','BtnCloseDetails');ui('wait-for','PrimaryButton','-t','5000');ui('invoke','PrimaryButton');prop('BtnDetails','IsEnabled','False')
            select(ids['broken.zip']);open_reader();ui('invoke','ReaderNext');wait('ReaderStatus','このページを表示できません。未対応形式・破損・画像サイズを確認してください。');wait('ReaderPageNumber','2 / 3');shot(theme+'-reader-corrupt-narrow')
            ui('invoke','ReaderNext');wait('ReaderPageNumber','3 / 3');wait('ReaderStatus','表示しました。拡大すると細部を確認できます。');check(theme+' corrupt page can be skipped',True);close_reader()
            select(ids['book.cbz']);open_reader();faults['code']=503;ui('invoke','ReaderNext');wait('ReaderStatus','ほかの画像を読み込み中です。少し待って再試行してください。');prop('ReaderRetry','IsEnabled','True');shot(theme+'-reader-busy-narrow')
            ui('invoke','ReaderRetry');wait('ReaderPageNumber','2 / 3');wait('ReaderStatus','表示しました。拡大すると細部を確認できます。');check(theme+' manual busy retry succeeds',True)
            book('book.cbz',extra=True);expected_source=source_digest();report.setdefault('intentional_fixture_changes',[]).append(theme+' added a fourth generated book page for real409')
            ui('invoke','ReaderNext');wait('ReaderStatus','ファイルが更新されました。閉じて再スキャンしてから、開き直してください。');wait('ReaderPageNumber','—');prop('ReaderNext','IsEnabled','False');prop('ReaderPrevious','IsEnabled','False');shot(theme+'-reader-stale-narrow');close_reader()
            catalog.start_scan(root);catalog._worker.join(20);check(theme+' generated rescan complete',catalog.scan_state()['state']=='complete')
            open_reader();wait('ReaderPageNumber','1 / 4');check(theme+' explicit reopen uses new manifest',True)
            entered.clear();released.clear();faults['delay']=True;ui('invoke','ReaderNext');check(theme+' delayed page started',entered.wait(5))
            close_reader();select(ids['broken.zip']);open_reader();released.set();time.sleep(1)
            wait('ReaderPageNumber','1 / 3');wait('ReaderImage','1ページ');check(theme+' late cancelled response cannot replace new book',True);shot(theme+'-reader-after-cancel-narrow');close_reader()
            resize(1200,820)
            close()
        check('No AI inference or worker',not engine.encoder.resident and not engine.encoder.calls and not engine.requests)
        check('Settings bytes unchanged',settings.read_bytes()==settings_before)
        check('Only declared generated archive changes',source_digest()==expected_source and all(source_digest()[name]==original[name] for name in original if name!='book.cbz'))
        report['keyboard_verification']='partial' if report['keyboard_skipped'] else 'tested shortcuts passed'
        report['high_dpi_verification']='not tested; actual DPI recorded';report['contrast_verification']='not tested; actual contrast recorded'
        report['pass']=True
    except Exception as error:
        report['error']=str(error)
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
                report['source_boundary_verified']=bool(original) and source_digest()==expected_source and all(source_digest()[name]==original[name] for name in original if name!='book.cbz')
                if not report['source_boundary_verified']:report['pass']=False
                (target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'pass':report['pass'],'checks':len(report['checks']),'keys':len(report['keyboard_actions']),'skipped':len(report['keyboard_skipped'])}))
    if not report['pass']:raise RuntimeError('Native checks failed')

if __name__=='__main__':main()
