"""Owned image viewer/navigation and archive regression checks on generated media only.

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
    parser.add_argument('--double-click-only',action='store_true');parser.add_argument('--reader-spread-only',action='store_true');args=parser.parse_args();target=args.output.resolve()
    if os.name!='nt':parser.error('Native Windows required')
    if not target.is_relative_to((REPO/'data/ai-ui').resolve()):parser.error('Evidence must stay in data/ai-ui')
    target.mkdir(parents=True,exist_ok=False)
    env={**os.environ,'WINAPP_UI_WORKFLOW_ID':'aredoko-image-'+uuid.uuid4().hex}
    report={'pass':False,'target':'local','actual_model':False,'checks':[],'screenshots':[],'keyboard_actions':[],'keyboard_skipped':[],'display':[],'audit_scope':'image modal/auto-hide overlays/navigation/current-page scope/zoom/draft/errors and archive regression; not whole-app audit'}
    catalog=engine=server=thread=None;hwnd=main_hwnd=app_pid=process=None;original={}
    expected_source={}
    user32=ctypes.WinDLL('user32',use_last_error=True);kernel32=ctypes.WinDLL('kernel32',use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user32.GetForegroundWindow.restype=wintypes.HWND
    user32.SetForegroundWindow.argtypes=[wintypes.HWND]
    user32.IsWindowEnabled.argtypes=[wintypes.HWND]
    user32.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    user32.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
    user32.GetDpiForWindow.argtypes=[wintypes.HWND];user32.GetDpiForWindow.restype=wintypes.UINT
    user32.SetCursorPos.argtypes=[ctypes.c_int,ctypes.c_int]
    user32.WindowFromPoint.argtypes=[wintypes.POINT];user32.WindowFromPoint.restype=wintypes.HWND
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
    def ui(*args):
        nonlocal hwnd
        owner=wintypes.DWORD()
        if hwnd:user32.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
        if hwnd and owner.value!=app_pid:
            hwnd=main_hwnd
        if args and args[0]=='wait-for' and len(args)>1 and args[1] in ('ImageViewerDialog','ArchiveReaderDialog') and '--gone' in args:
            title='画像ビューア' if args[1]=='ImageViewerDialog' else '読書画面'
            for _ in range(50):
                windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
                if not any(title in w.get('title','') for w in windows):break
                time.sleep(.1)
            else:raise RuntimeError('Owned viewer window did not close')
            hwnd=main_hwnd
        if args and args[0]=='wait-for' and len(args)>1 and args[1] in ('ImageViewerDialog','ArchiveReaderDialog') and '--gone' not in args:
            title='画像ビューア' if args[1]=='ImageViewerDialog' else '読書画面'
            for _ in range(50):
                windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
                matches=[w for w in windows if title in w.get('title','')]
                if len(matches)==1:
                    hwnd=str(matches[0]['hwnd']);break
                time.sleep(.1)
            else:raise RuntimeError('Owned viewer window unavailable')
        return cli('ui',*args,'-w',hwnd)
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
        if phase.endswith('-viewer') or phase.endswith('-reader'):
            prefix='Image' if phase.endswith('-viewer') else 'Reader'
            outer=next(n for n in all_nodes if n.get('automationId')==prefix+'Viewport')
            close_node=next(n for n in all_nodes if n.get('automationId')==prefix+'Close')
            check(phase+' header is flush to image canvas top',0<=close_node['y']-outer['y']<=12)
            header=next(n for n in all_nodes if n.get('automationId')==prefix+'Header')
            toolbar=next(n for n in all_nodes if n.get('automationId')==prefix+'Toolbar')
            check(phase+' bands dock flush without side or bottom gaps',abs(header['x']-outer['x'])<=2 and abs(header['width']-outer['width'])<=2 and abs(toolbar['x']-outer['x'])<=2 and abs(toolbar['width']-outer['width'])<=2 and abs(toolbar['y']+toolbar['height']-outer['y']-outer['height'])<=2)
            check(phase+' dedicated window keeps library disabled',hwnd!=main_hwnd and not user32.IsWindowEnabled(int(main_hwnd)))
        if phase.endswith('-viewer'):
            bounds={n['automationId']:n for n in all_nodes if n.get('automationId') in ('ImageViewport','ViewerImage')}
            outer,inner=bounds['ImageViewport'],bounds['ViewerImage']
            check(phase+' fitted image is centered',abs((outer['x']+outer['width']/2)-(inner['x']+inner['width']/2))<=2 and abs((outer['y']+outer['height']/2)-(inner['y']+inner['height']/2))<=2)
        report.setdefault('accessible_controls',{})[phase]=result
        (target/(phase+'-tree.json')).write_text(json.dumps(tree,ensure_ascii=False),encoding='utf-8')
    def close():
        nonlocal process,hwnd,main_hwnd,app_pid
        if not process:return
        try:
            if kernel32.WaitForSingleObject(process,0)!=0:
                if hwnd!=main_hwnd:
                    owner=wintypes.DWORD();user32.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
                    if owner.value==app_pid:user32.PostMessageW(int(hwnd),0x0010,0,0);time.sleep(.5)
                    hwnd=main_hwnd
                owner=wintypes.DWORD();user32.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
                if owner.value!=app_pid:raise RuntimeError('Owned close window changed')
                user32.PostMessageW(int(hwnd),0x0010,0,0)
                if kernel32.WaitForSingleObject(process,7000)==0:report['graceful_closes']=report.get('graceful_closes',0)+1
                else:
                    report.setdefault('cleanup_warnings',[]).append('Owned test process required termination')
                    if not kernel32.TerminateProcess(process,1) or kernel32.WaitForSingleObject(process,5000)!=0:raise RuntimeError('Owned process cleanup failed')
        finally:kernel32.CloseHandle(process);process=hwnd=main_hwnd=app_pid=None
    def source_digest():return {p.name:(p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest()) for p in (target/'media').glob('*') if p.is_file()}
    try:
        existing=subprocess.run(['powershell','-NoProfile','-Command','if(Get-Process Aredoko.WinUI -ErrorAction SilentlyContinue){exit 1}'],capture_output=True)
        if existing.returncode:raise RuntimeError('Existing user app; never attach or stop it')
        server=ThreadingHTTPServer(('127.0.0.1',8769),production_handler)
        media=target/'media';media.mkdir()
        for name,color in [('a.png','red'),('b.png','blue')]:
            (media/name).write_bytes(graphic({'background':'white','objects':[{'shape':'circle','color':color,'x':90,'y':120,'sx':40,'sy':40}]}))
        (media/'broken.png').write_bytes(b'not an image')
        with zipfile.ZipFile(media/'book.cbz','w') as archive:archive.writestr('page1.png',(media/'a.png').read_bytes())
        if args.reader_spread_only:
            colors=['red','blue','green','yellow','purple']
            contents=[graphic({'background':'white','objects':[{'shape':'circle','color':color,'x':90,'y':120,'sx':40,'sy':40}]}) for color in colors]
            with zipfile.ZipFile(media/'book.cbz','w') as archive:
                for name,data in zip(['page1.png','page2.png','page10.png','page20.png','page30.png'],contents):archive.writestr(name,data)
            with zipfile.ZipFile(media/'broken.zip','w') as archive:
                for name,data in zip(['page1.png','page2.png','page3.png','page4.png'],[contents[0],b'broken page',contents[2],contents[3]]):archive.writestr(name,data)
        original=source_digest();expected_source=dict(original)
        catalog=ProductionCatalog(target/'catalog.sqlite');root=catalog.add_root(str(media));catalog.start_scan(root);catalog._worker.join(20)
        check('Generated scan complete',catalog.scan_state()['state']=='complete' and catalog.search()['total']==(5 if args.reader_spread_only else 4))
        ids={x['title']:x['id'] for x in catalog.search()['items']}
        settings=target/'settings.json';settings.write_text(json.dumps({'version':1,'profile':'default','scope':{'root_ids':[root],'kind':'','shelf':None}}),encoding='utf-8');settings_before=settings.read_bytes()
        encoder=ContractEncoder();engine=RecordedAI(catalog,encoder);profiles=AIProfileSettings(REPO,settings)
        token=secrets.token_urlsafe(32);handler=production_handler(catalog,token,engine,profiles=profiles)
        faults={'code':None,'delay':False};entered=threading.Event();released=threading.Event()
        class Quiet(handler):
            def log_message(self,*args):pass
            def do_GET(self):
                if self.headers.get('X-Aredoko-Token')==token and self.path.startswith('/api/library/preview/'):
                    report.setdefault('image_requests',[]).append(self.path)
                if self.headers.get('X-Aredoko-Token')==token and self.path.startswith('/api/library/reader/'):
                    report.setdefault('reader_requests',[]).append(self.path)
                    if urlparse(self.path).path=='/api/library/reader/'+str(ids['book.cbz'])+'/pages/1':
                        if faults.get('reader_code'):
                            code=faults.pop('reader_code');return self.send(code,{'error':'Generated reader failure'})
                        if faults.get('reader_delay'):
                            faults['reader_delay']=False;entered.set()
                            if not released.wait(25):return self.send(503,{'error':'Generated reader delay timeout'})
                if self.headers.get('X-Aredoko-Token')==token and self.path=='/api/library/preview/'+str(ids['a.png']):
                    if faults['code']:
                        code=faults['code'];faults['code']=None;return self.send(code,{'error':'Generated failure'})
                    if faults['delay']:
                        faults['delay']=False;entered.set()
                        if not released.wait(25):return self.send(503,{'error':'Generated delay timeout'})
                try:return super().do_GET()
                except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):report['cancelled_response_writes']=report.get('cancelled_response_writes',0)+1
        server.RequestHandlerClass=Quiet;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def prop(identifier,name,value):ui('wait-for',identifier,'-p',name,'--value',str(value),'-t','10000')
        def select(name):
            ui('invoke','Item'+str(ids[name]),'--action','select');wait('TxtEditStatus','保存済み')
            if name in ('a.png','b.png'):ui('wait-for','DetailPreview','-t','10000')
        def open_image():
            ui('inspect','BtnOpenImage','--json');ui('invoke','BtnOpenImage');ui('wait-for','ImageViewerDialog','-t','5000')
            if not keys('f10','ImageViewport'):raise RuntimeError('Cannot safely reveal viewer controls: owned keyboard activation denied')
            ui('wait-for','ImageClose','-t','5000')
        def move_owned(bounds,fraction,viewport_id='ImageViewport'):
            if kernel32.WaitForSingleObject(process,0)==0:raise RuntimeError('Owned pointer process exited')
            owner=wintypes.DWORD();user32.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
            if owner.value!=app_pid or user32.GetForegroundWindow()!=int(hwnd):raise RuntimeError('Owned foreground pointer target changed')
            x=round(bounds['x']+bounds['width']*fraction);y=round(bounds['y']+bounds['height']*.5)
            at_point=user32.WindowFromPoint(wintypes.POINT(x,y));point_owner=wintypes.DWORD();user32.GetWindowThreadProcessId(at_point,ctypes.byref(point_owner))
            if point_owner.value!=app_pid:raise RuntimeError('Pointer coordinate is outside owned app')
            if not user32.SetCursorPos(x,y):raise ctypes.WinError(ctypes.get_last_error())
            # Cursor placement is not itself a WinUI pointer input. Use the
            # documented CLI SendInput hover after moving off the center.
            ui('hover',viewport_id,'--dwell-time','0')
            time.sleep(.1)
            report.setdefault('pointer_actions',[]).append({'target':viewport_id,'fraction':fraction,'dispatch':'verified point/window/process/foreground; CLI SendInput hover to owned canvas only'})
        def open_reader():
            ui('invoke','BtnOpenBook');ui('wait-for','ArchiveReaderDialog','-t','5000')
            if not keys('f10','ReaderViewport'):raise RuntimeError('Cannot reveal reader controls with owned keyboard')
            ui('wait-for','ReaderClose','-t','5000')
        def close_reader():
            if not keys('esc','ReaderClose'):ui('invoke','ReaderClose')
            ui('wait-for','ArchiveReaderDialog','--gone','-t','5000')
        def reader_mode(identifier):
            ui('invoke','ReaderSettings');ui('wait-for',identifier,'-t','5000');ui('invoke',identifier)
        def double_click_owned(identifier):
            owner=wintypes.DWORD();user32.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
            if kernel32.WaitForSingleObject(process,0)==0 or owner.value!=app_pid:raise RuntimeError('Owned double-click target changed before activation')
            if user32.GetForegroundWindow()!=int(hwnd):user32.SetForegroundWindow(int(hwnd));time.sleep(.1)
            owner=wintypes.DWORD();user32.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
            if kernel32.WaitForSingleObject(process,0)==0 or owner.value!=app_pid or user32.GetForegroundWindow()!=int(hwnd):raise RuntimeError('Owned double-click target changed')
            ui('inspect',identifier,'--json');ui('click',identifier,'--double')
            report.setdefault('double_click_actions',[]).append({'target':identifier,'dispatch':'verified owned foreground; CLI double click'})
        def revealed_image():
            ui('wait-for','ImageViewerDialog','-t','5000')
            if not keys('f10','ImageViewport'):raise RuntimeError('Cannot reveal double-click viewer with owned keyboard')
            wait('ImageStatus',shown)
        def close_image():
            physical=keys('esc','ImageClose')
            if not physical:ui('invoke','ImageClose')
            ui('wait-for','ImageViewerDialog','--gone','-t','5000')
            return physical
        shown='← → で画像送り · 表示画像は長辺2048pxまで'
        for theme in ('Light','Dark'):
            launch=json.loads(cli('run','src/Aredoko.WinUI','-c','Release','--arch','x64','-p','Platform=x64','-p','SelfContained=true','--no-build','--output-appx-directory',str(target/('layout-'+theme.lower())),'--detach','--json','--args','--ui-theme '+theme.lower()))
            if launch.get('ProcessScope') not in (None,'local'):raise RuntimeError('Wrong target')
            app_pid=int(launch['ProcessId']);process=kernel32.OpenProcess(0x00100001,False,app_pid)
            if not process:raise RuntimeError('Owned process unavailable')
            for _ in range(60):
                windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'));main=[w for w in windows if 'Aredoko' in w.get('title','') and w.get('title')!='PopupHost']
                if len(main)==1:break
                time.sleep(.1)
            if len(main)!=1:raise RuntimeError('Unique owned main unavailable')
            hwnd=main_hwnd=str(main[0]['hwnd']);ready();resize(1200,820);wait('TxtCount','5 件' if args.reader_spread_only else '4 件')
            if args.reader_spread_only:
                report['audit_scope']='reader single/RTL/LTR spreads/settings/context/overlay/zoom/errors/cancel/draft; no double-click rerun'
                shown_book='表示しました。拡大すると細部を確認できます。'
                select('book.cbz');ui('set-value','TxtTags','spread-draft');wait('TxtEditStatus','未保存の変更');open_reader();wait('ReaderPageNumber','1 / 5');wait('ReaderStatus',shown_book);wait('ReaderImage','1ページ');prop('ReaderPrevious','IsEnabled','False')
                audit(theme+'-reader',('ReaderViewport','ReaderPrevious','ReaderNext','ReaderSettings','ReaderRetry','ReaderReopen','ReaderClose','ReaderZoomIn','ReaderFit'));shot(theme+'-reader-cover')
                ui('invoke','ReaderNext');wait('ReaderPageNumber','2 / 5');wait('ReaderStatus',shown_book);wait('ReaderImage','2ページ');check(theme+' single page navigation preserved',True)
                reader_mode('ReaderRtl');wait('ReaderPageNumber','2–3 / 5');wait('ReaderStatus',shown_book);wait('ReaderImage','3ページ');wait('ReaderImageSecond','2ページ')
                tree=json.loads(ui('inspect','--json','--depth','16'));bounds={n['automationId']:n for n in nodes(tree) if n.get('automationId') in ('ReaderImage','ReaderImageSecond')};check(theme+' RTL physical left is page 3 and right page 2',bounds['ReaderImage']['x']<bounds['ReaderImageSecond']['x']);shot(theme+'-reader-rtl')
                reader_mode('ReaderLtr');wait('ReaderStatus',shown_book);wait('ReaderPageNumber','2–3 / 5');wait('ReaderImage','2ページ');wait('ReaderImageSecond','3ページ');shot(theme+'-reader-ltr');check(theme+' LTR swaps physical page order',True)
                ui('invoke','ReaderZoomIn');wait('ReaderZoomStatus','倍率 150%');ui('scroll','ReaderViewport','--to','bottom','--json');ui('invoke','ReaderFit');wait('ReaderZoomStatus','倍率 100%');check(theme+' spread zoom/scroll/reset',True)
                resize(700,620);ui('invoke','ReaderNext');wait('ReaderPageNumber','4–5 / 5');wait('ReaderStatus',shown_book);prop('ReaderNext','IsEnabled','False');shot(theme+'-reader-last-narrow')
                if keys('left','ReaderViewport'):wait('ReaderPageNumber','2–3 / 5');wait('ReaderStatus',shown_book);check(theme+' LTR left goes to previous spread',True)
                reader_mode('ReaderRtl');wait('ReaderStatus',shown_book)
                if keys('left','ReaderViewport'):wait('ReaderPageNumber','4–5 / 5');wait('ReaderStatus',shown_book);check(theme+' RTL left goes to next spread',True)
                ui('invoke','ReaderPrevious');wait('ReaderPageNumber','2–3 / 5');wait('ReaderStatus',shown_book);ui('invoke','ReaderPrevious');wait('ReaderPageNumber','1 / 5');wait('ReaderStatus',shown_book);prop('ReaderPrevious','IsEnabled','False');check(theme+' spread returns to solitary cover',True)
                # Menu is also available from an actual right click on the owned viewport.
                owner=wintypes.DWORD();user32.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
                if kernel32.WaitForSingleObject(process,0)==0 or owner.value!=app_pid:raise RuntimeError('Owned context target changed before activation')
                if user32.GetForegroundWindow()!=int(hwnd):user32.SetForegroundWindow(int(hwnd));time.sleep(.1)
                owner=wintypes.DWORD();user32.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
                if owner.value!=app_pid or user32.GetForegroundWindow()!=int(hwnd):raise RuntimeError('Owned context target changed')
                ui('click','ReaderViewport','--right');ui('wait-for','ReaderSingle','-t','5000');shot(theme+'-reader-context');ui('invoke','ReaderSingle');wait('ReaderStatus',shown_book);check(theme+' context menu selects single page',True)
                if keys('ctrl+s','ReaderClose'):check(theme+' reader modal does not save background draft',catalog.get(ids['book.cbz'])['tags']==[])
                close_reader();wait('TxtTags','spread-draft');wait('TxtEditStatus','未保存の変更');focus_assert('BtnOpenBook');check(theme+' reader preserves draft/opener',True)
                ui('invoke','BtnCloseDetails');ui('wait-for','PrimaryButton','-t','5000');ui('invoke','PrimaryButton');select('broken.zip');open_reader();wait('ReaderPageNumber','1 / 4');wait('ReaderStatus',shown_book);reader_mode('ReaderLtr');wait('ReaderStatus',shown_book);ui('invoke','ReaderNext');wait('ReaderPageNumber','2–3 / 4');wait('ReaderStatus','このページを表示できません。未対応形式・破損・画像サイズを確認してください。');prop('ReaderRetry','IsEnabled','True');shot(theme+'-reader-broken-spread')
                ui('invoke','ReaderNext');wait('ReaderPageNumber','4 / 4');wait('ReaderStatus',shown_book);wait('ReaderImage','4ページ');prop('ReaderNext','IsEnabled','False');shot(theme+'-reader-unpaired-last');check(theme+' broken spread can be skipped and last page stays single',True);close_reader()
                select('book.cbz');open_reader();wait('ReaderStatus',shown_book);faults['reader_code']=503;ui('invoke','ReaderNext');wait('ReaderStatus','ほかの画像を読み込み中です。少し待って再試行してください。');shot(theme+'-reader-busy');ui('invoke','ReaderRetry');wait('ReaderStatus',shown_book);wait('ReaderPageNumber','2 / 5');check(theme+' reader manual retry preserves page',True)
                ui('invoke','ReaderPrevious');wait('ReaderStatus',shown_book);faults['reader_code']=409;ui('invoke','ReaderNext');wait('ReaderStatus','ファイルが更新されました。閉じて再スキャンしてから、開き直してください。');wait('ReaderPageNumber','—');prop('ReaderNext','IsEnabled','False');shot(theme+'-reader-conflict');ui('invoke','ReaderReopen');wait('ReaderPageNumber','1 / 5');wait('ReaderStatus',shown_book);check(theme+' injected 409 blocks stale pages and explicit reopen',True)
                entered.clear();released.clear();faults['reader_delay']=True;ui('invoke','ReaderNext');check(theme+' delayed reader page started',entered.wait(5));close_reader();select('broken.zip');open_reader();wait('ReaderPageNumber','1 / 4');wait('ReaderStatus',shown_book);released.set();time.sleep(.6);wait('ReaderImage','1ページ');wait('ReaderPageNumber','1 / 4');shot(theme+'-reader-after-cancel');check(theme+' late page cannot replace new book',True)
                tree=json.loads(ui('inspect','--json','--depth','16'));outer=next(n for n in nodes(tree) if n.get('automationId')=='ReaderViewport')
                # move_owned uses an argument selecting which owned viewport to hover.
                move_owned(outer,.15,'ReaderViewport');ui('wait-for','ReaderClose','--gone','-t','10000');shot(theme+'-reader-controls-hidden');move_owned(outer,.85,'ReaderViewport');ui('wait-for','ReaderClose','-t','5000');shot(theme+'-reader-controls-revealed');check(theme+' reader chrome hides and reappears with mouse motion',True)
                if not keys('f10','ReaderViewport'):raise RuntimeError('Reader keyboard controls unavailable')
                time.sleep(3);ui('wait-for','ReaderClose','-t','5000');check(theme+' reader F10 keeps controls visible',True);move_owned(outer,.15,'ReaderViewport');ui('wait-for','ReaderClose','--gone','-t','10000')
                if keys('esc','ReaderViewport'):ui('wait-for','ArchiveReaderDialog','--gone','-t','5000');check(theme+' reader Escape works with controls hidden',True)
                else:raise RuntimeError('Hidden reader Escape input unavailable')
                close();continue
            if args.double_click_only:
                report['audit_scope']='targeted list/grid/detail thumbnail double click, dirty selection cancellation and CBZ entry; not full overlay rerun'
                wait('PreviewStatus'+str(ids['a.png']),'画像プレビュー')
                double_click_owned('Preview'+str(ids['a.png']));revealed_image();wait('ImageTitle','a.png');check(theme+' list thumbnail opens correct image without preselection',True);shot(theme+'-double-list');close_image()
                ui('set-value','TxtTags','double-click-draft');wait('TxtEditStatus','未保存の変更');ui('invoke','BtnLayout');ready();wait('PreviewStatus'+str(ids['a.png']),'画像プレビュー')
                double_click_owned('Preview'+str(ids['a.png']));revealed_image();wait('ImageTitle','a.png');shot(theme+'-double-grid');close_image();wait('TxtTags','double-click-draft');wait('TxtEditStatus','未保存の変更');check(theme+' grid same-image double click retains draft',catalog.get(ids['a.png'])['tags']==[])
                double_click_owned('Preview'+str(ids['b.png']));ui('wait-for','CloseButton','--value','編集を続ける','-t','5000');ui('invoke','CloseButton');ready();wait('TxtTags','double-click-draft');wait('TxtEditStatus','未保存の変更');ui('wait-for','ImageViewerDialog','--gone','-t','3000');check(theme+' cancelling dirty selection cannot open wrong image',catalog.get(ids['a.png'])['tags']==[])
                ui('wait-for','DetailPreview','-t','5000');double_click_owned('DetailPreview');revealed_image();wait('ImageTitle','a.png');shot(theme+'-double-detail');close_image();wait('TxtTags','double-click-draft');check(theme+' detail thumbnail keeps original image/draft',True)
                ui('invoke','BtnCloseDetails');ui('wait-for','PrimaryButton','-t','5000');ui('invoke','PrimaryButton');ready();wait('PreviewStatus'+str(ids['book.cbz']),'先頭画像')
                double_click_owned('Preview'+str(ids['book.cbz']));ui('wait-for','ReaderPageNumber','--value','1 / 1','-t','10000');wait('ReaderStatus','表示しました。拡大すると細部を確認できます。');shot(theme+'-double-book');ui('invoke','CloseButton');check(theme+' CBZ thumbnail opens existing reader',True)
                close();continue
            select('a.png');prop('BtnOpenImage','IsEnabled','True');prop('BtnOpenBook','IsEnabled','False')
            ui('set-value','TxtTags','image-draft');wait('TxtEditStatus','未保存の変更');open_image();wait('ImageStatus',shown)
            audit(theme+'-viewer',('ImageViewport','ViewerImage','ImagePrevious','ImageNext','ImageZoomIn','ImageZoomOut','ImageFit','ImageRetry','ImageClose'))
            wait('ImageZoomStatus','倍率 100%');ui('invoke','ImageZoomIn');wait('ImageZoomStatus','倍率 150%');check(theme+' image zoom changes',True);ui('invoke','ImageZoomOut');wait('ImageZoomStatus','倍率 100%');check(theme+' image zoom out',True);ui('invoke','ImageZoomIn');wait('ImageZoomStatus','倍率 150%')
            scroll=ui('scroll','ImageViewport','--to','bottom','--json')
            report.setdefault('scroll_operations',[]).append({'theme':theme,'result':scroll})
            observed=ui('get-property','ImageViewport','--json')
            (target/(theme+'-scroll-properties.json')).write_text(observed,encoding='utf-8')
            check(theme+' vertical scroll reaches bottom',float(json.loads(observed)['properties']['ScrollVerticalPercent'])==100)
            check(theme+' zoomed image scroll operation',True);shot(theme+'-image-zoom-wide')
            ui('invoke','ImageFit');wait('ImageZoomStatus','倍率 100%');check(theme+' image reset',True)
            wait('ImagePosition','1 / 3');prop('ImagePrevious','IsEnabled','False');prop('ImageNext','IsEnabled','True')
            if not keys('right','ImageViewport'):ui('invoke','ImageNext')
            wait('ImageStatus',shown);wait('ViewerImage','b.pngの画像');wait('ImageTitle','b.png');wait('ImagePosition','2 / 3');wait('ImageZoomStatus','倍率 100%')
            check(theme+' right opens next result image',True);shot(theme+'-image-next')
            if not keys('left','ImageClose'):ui('invoke','ImagePrevious')
            wait('ImageStatus',shown);wait('ViewerImage','a.pngの画像');wait('ImagePosition','1 / 3');check(theme+' left from Close returns to previous image',True)
            ui('invoke','ImageNext');wait('ImageStatus',shown);ui('invoke','ImageNext')
            wait('ImagePosition','3 / 3');wait('ImageTitle','broken.png');wait('ImageStatus','画像を表示できません。未対応形式・破損・画像サイズを確認してください。');prop('ImageNext','IsEnabled','False');prop('ImagePrevious','IsEnabled','True')
            if keys('right','ImageClose'):wait('ImagePosition','3 / 3');check(theme+' last image does not wrap',True)
            shot(theme+'-image-last-error')
            if not keys('left','ImageViewport'):ui('invoke','ImagePrevious')
            wait('ImageStatus',shown);wait('ViewerImage','b.pngの画像');check(theme+' left escapes failed image',True)
            ui('invoke','ImagePrevious');wait('ImageStatus',shown);wait('ImagePosition','1 / 3')
            if keys('ctrl+s','ImageClose'):focus_assert('ImageClose');check(theme+' viewer blocks background save',catalog.get(ids['a.png'])['tags']==[])
            if keys('ctrl+f','ImageClose'):focus_assert('ImageClose');check(theme+' viewer blocks background search',True)
            resize(700,620);shot(theme+'-image-narrow');physical=close_image();wait('TxtTags','image-draft');wait('TxtEditStatus','未保存の変更')
            check(theme+' viewer retains unsaved tags',catalog.get(ids['a.png'])['tags']==[])
            if physical:focus_assert('BtnOpenImage');check(theme+' Escape restores opener focus',True)
            ui('invoke','BtnCloseDetails');ui('wait-for','PrimaryButton','-t','5000');ui('invoke','PrimaryButton')
            select('broken.png');open_image();wait('ImageStatus','画像を表示できません。未対応形式・破損・画像サイズを確認してください。');prop('ImageRetry','IsEnabled','True');shot(theme+'-image-corrupt');close_image()
            select('a.png');faults['code']=503;open_image();wait('ImageStatus','ほかの画像を読み込み中です。少し待って再試行してください。');shot(theme+'-image-busy');ui('invoke','ImageRetry');wait('ImageStatus',shown);check(theme+' image manual retry',True);close_image()
            entered.clear();released.clear();faults['delay']=True;open_image();check(theme+' navigation delayed image started',entered.wait(5))
            prop('ImageNext','IsEnabled','True');ui('invoke','ImageNext');wait('ImageStatus',shown);wait('ViewerImage','b.pngの画像');wait('ImagePosition','2 / 3')
            released.set();time.sleep(.6);wait('ViewerImage','b.pngの画像');wait('ImageStatus',shown);shot(theme+'-image-navigation-cancel');check(theme+' delayed previous image cannot replace navigation target',True);close_image()
            entered.clear();released.clear();faults['delay']=True;open_image();check(theme+' delayed image started',entered.wait(5));close_image();select('b.png');open_image();wait('ImageStatus',shown);released.set();time.sleep(.6);wait('ImageStatus',shown);wait('ViewerImage','b.pngの画像');shot(theme+'-image-after-cancel');check(theme+' cancelled image cannot replace new viewer',True);close_image()
            select('book.cbz');prop('BtnOpenImage','IsEnabled','False');prop('BtnOpenBook','IsEnabled','True');open_reader();wait('ReaderPageNumber','1 / 1');wait('ReaderStatus','表示しました。拡大すると細部を確認できます。');shot(theme+'-archive-regression');close_reader();check(theme+' archive entry preserved',True)
            ui('invoke','BtnCloseDetails');ui('set-value','TxtQuery','b.png');wait('TxtCount','1 件');ready();select('b.png');open_image();wait('ImageStatus',shown)
            wait('ImagePosition','1 / 1');prop('ImagePrevious','IsEnabled','False');prop('ImageNext','IsEnabled','False')
            if keys('left','ImageClose'):wait('ImagePosition','1 / 1');wait('ImageTitle','b.png');check(theme+' scoped first arrow stays in filtered results',True)
            if keys('right','ImageViewport'):wait('ImagePosition','1 / 1');check(theme+' scoped last arrow stays in filtered results',True)
            shot(theme+'-image-filtered');check(theme+' viewer contains only current filtered result page',True);close_image()
            select('b.png');open_image();wait('ImageStatus',shown)
            tree=json.loads(ui('inspect','--json','--depth','16'));outer=next(n for n in nodes(tree) if n.get('automationId')=='ImageViewport')
            check(theme+' image canvas expands beyond prior fixed-footer layout',outer['width']>=600 and outer['height']>=400)
            # Move only within verified UIA canvas bounds and the owned process,
            # then verify Collapse removes invisible controls from hit testing.
            move_owned(outer,.15);ui('wait-for','ImageClose','--gone','-t','10000');ui('wait-for','ImageToolbar','--gone','-t','5000');shot(theme+'-image-controls-hidden')
            tree=json.loads(ui('inspect','--json','--depth','16'));now=next(n for n in nodes(tree) if n.get('automationId')=='ImageViewport')
            check(theme+' hiding chrome does not resize image canvas',all(abs(outer[k]-now[k])<=2 for k in ('x','y','width','height')))
            if keys('left','ImageViewport'):
                # This page is a singleton: arrows remain in scope even while hidden.
                ui('wait-for','ImageClose','--gone','-t','3000');check(theme+' hidden chrome arrow does not reveal or escape scope',True)
            # A different verified canvas coordinate reveals PointerMoved controls.
            move_owned(outer,.85);ui('wait-for','ImageClose','-t','5000');shot(theme+'-image-controls-revealed');check(theme+' mouse motion restores overlay controls',True)
            if not keys('f10','ImageViewport'):raise RuntimeError('Owned input unavailable for keyboard chrome check')
            time.sleep(3);ui('wait-for','ImageClose','-t','5000');check(theme+' keyboard controls remain available while idle',True)
            # Return to mouse-driven idle, then Escape must close with no button.
            move_owned(outer,.15);ui('wait-for','ImageClose','--gone','-t','10000')
            if keys('esc','ImageViewport'):
                ui('wait-for','ImageViewerDialog','--gone','-t','5000');focus_assert('BtnOpenImage');check(theme+' Escape closes while chrome is hidden',True)
            else:raise RuntimeError('Hidden Escape unavailable; keyboard readiness denied')
            close()
        check('No AI inference',not engine.encoder.calls and not engine.requests and not engine.encoder.resident)
        check('Settings unchanged',settings.read_bytes()==settings_before);check('Source bytes and mtimes unchanged',source_digest()==original);report['pass']=True
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
