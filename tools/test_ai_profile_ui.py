"""Native restart/profile regression using generated sources and isolated settings.

Requires built x64 SelfContained Release, existing local weights, unlocked Windows.
Never touches the default AppData settings or private library. No setup/download.
Search modes use real keyboard input and assert the resulting selected value.
PopupHost can be a child UIA pane rather than a separately enumerated window.
Each run reports its checked scope; editor-only does not load models unless
--coverage-checks explicitly adds the generated 17-item CUDA coverage slice.
See docs/model-profiles.md and docs/ui-polish.md for the latest native evidence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from ui_geometry import resource_control_visible

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from ai_profiles import DEFAULT_PROFILE
from create_preview_fixture import create

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--editor-only',action='store_true',help='Run literal editor/dirty/restart checks without loading AI');parser.add_argument('--layout-checks',action='store_true',help='Also capture wide/narrow list/tile and missing-model dialog');parser.add_argument('--appearance-checks',action='store_true',help='Also check Light/Dark error guidance and literal recovery without GPU loading')
    parser.add_argument('--coverage-checks',action='store_true',help='With editor-only/appearance checks, index the 17 generated items on existing CUDA weights and verify semantic coverage text')
    parser.add_argument('--resource-checks',action='store_true',help='Also save resource policy, release/reload CUDA and verify saved GUI values after restart')
    args=parser.parse_args()
    if args.resource_checks and not args.coverage_checks:parser.error('--resource-checks requires --coverage-checks')
    if args.coverage_checks and not (args.editor_only and args.appearance_checks):parser.error('--coverage-checks requires --editor-only --appearance-checks')
    if (args.layout_checks or args.appearance_checks) and not args.editor_only:parser.error("--layout-checks/--appearance-checks require --editor-only")
    if os.name!='nt':raise RuntimeError('Native Windows only')
    target=args.output.resolve();target.mkdir(parents=True,exist_ok=False)
    media=create(target/'media')
    for name in ('雨の夜の街並み.wav','晴れた昼の公園.wav'):(media/name).write_bytes(b'fictional audio metadata fixture')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in media.iterdir()}
    (target/'source-hashes.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2),encoding='utf-8')
    folder=REPO/'data/ai-profiles';folder.mkdir(parents=True,exist_ok=True)
    nonce='ui-'+uuid.uuid4().hex[:10]
    names={key:nonce+'-'+key+'.json' for key in ('text','missing','invalid')}
    profile_files=[];logs=[];backend=None;app_pid=None;hwnd=None;headers={}
    origin='http://127.0.0.1:8769';settings=target/'settings.json'
    ui_theme='System'
    env=os.environ.copy();env['WINAPP_UI_WORKFLOW_ID']='aredoko-profile-'+nonce
    report={'target':'local','actual_model':not args.editor_only or args.coverage_checks,'profile_verification':'not_run','coverage_verification':'not_run','resource_verification':'not_run','pass':False,'checks':[],'screenshots':[]}
    def cli(*arguments):
        result=subprocess.run(['winapp',*map(str,arguments)],cwd=REPO,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
        if result.returncode:raise RuntimeError('winapp '+str(arguments)+': '+result.stderr+result.stdout)
        return result.stdout
    def ui(*arguments,window=None):return cli('ui',*arguments,'-w',window or hwnd)
    def api(route,body=None,expected=200):
        request=urllib.request.Request(origin+route,None if body is None else json.dumps(body,ensure_ascii=False).encode('utf-8'),headers={**headers,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=180) as response:data=json.load(response);code=response.status
        except urllib.error.HTTPError as ex:
            with ex:data=json.load(ex);code=ex.code
        if code!=expected:raise RuntimeError(f'{route} returned {code}: {data}')
        return data
    def check(name,condition):
        if not condition:raise RuntimeError(name)
        report['checks'].append(name)
        print(json.dumps({'check':name},ensure_ascii=True),flush=True)
    def screenshot(name):
        path=target/(name+'.png')
        ui('screenshot','--output',path)
        check('Screenshot '+name,path.is_file() and path.stat().st_size>0)
        report['screenshots'].append(path.name)
    def resize(width,height):
        import ctypes
        from ctypes import wintypes
        user32=ctypes.WinDLL('user32',use_last_error=True)
        user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
        owner=wintypes.DWORD();user32.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
        if owner.value!=app_pid:raise RuntimeError('Resize target is not the owned app')
        user32.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
        if not user32.SetWindowPos(int(hwnd),None,0,0,width,height,0x2|0x4|0x10):raise ctypes.WinError(ctypes.get_last_error())
        time.sleep(.5);ready()
    def visible_controls(name,ids):
        tree=json.loads(ui('inspect','--json','--depth','12'))
        (target/(name+'-tree.json')).write_text(json.dumps(tree,ensure_ascii=False,indent=2),encoding='utf-8')
        stack=[tree];nodes=[]
        while stack:
            node=stack.pop()
            if isinstance(node,dict):
                if node.get('automationId') in ids:nodes.append(node)
                stack.extend(node.values())
            elif isinstance(node,list):stack.extend(node)
        root=tree['windows'][0]['elements'][0]
        for id in ids:
            matches=[n for n in nodes if n.get('automationId')==id]
            check(name+' '+id+' fits',len(matches)==1 and not matches[0].get('isOffscreen') and matches[0]['x']>=root['x'] and matches[0]['y']>=root['y'] and matches[0]['x']+matches[0]['width']<=root['x']+root['width'] and matches[0]['y']+matches[0]['height']<=root['y']+root['height'])
    def record_display(phase):
        import ctypes
        from ctypes import wintypes
        user32=ctypes.WinDLL('user32',use_last_error=True)
        user32.GetDpiForWindow.argtypes=[wintypes.HWND];user32.GetDpiForWindow.restype=wintypes.UINT
        class HighContrast(ctypes.Structure):
            _fields_=[('cbSize',wintypes.UINT),('dwFlags',wintypes.DWORD),('lpszDefaultScheme',wintypes.LPWSTR)]
        contrast=HighContrast();contrast.cbSize=ctypes.sizeof(contrast)
        user32.SystemParametersInfoW.argtypes=[wintypes.UINT,wintypes.UINT,ctypes.c_void_p,wintypes.UINT]
        if not user32.SystemParametersInfoW(0x0042,contrast.cbSize,ctypes.byref(contrast),0):raise ctypes.WinError(ctypes.get_last_error())
        dpi=user32.GetDpiForWindow(int(hwnd))
        if not dpi:raise RuntimeError('Cannot read owned window DPI')
        report.setdefault('display',[]).append({'phase':phase,'requested_theme':ui_theme,'dpi':dpi,'high_contrast':bool(contrast.dwFlags&1)})
    def recovery_mode(option,label):
        # A popup can also appear under main, duplicating its UIA items. Scope
        # the operation to the unique observed popup HWND owned by this app.
        ui('invoke','CmbSearchMode','--action','expand')
        popup=[]
        for _ in range(30):
            windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
            popup=[w for w in windows if w.get('title')=='PopupHost']
            if len(popup)==1:break
            time.sleep(.1)
        if len(popup)!=1:raise RuntimeError('Expected one owned recovery popup')
        ui('wait-for',option,'-t','3000',window=str(popup[0]['hwnd']))
        ui('invoke',option,'--action','select',window=str(popup[0]['hwnd']))
        ui('wait-for','CmbSearchMode','--value',label,'-t','3000')
        check('Recovery mode '+label,True)
    def unavailable_search(option,label,name):
        recovery_mode(option,label)
        ui('set-value','TxtQuery','青い画像');time.sleep(.6);ui('invoke','BtnSearch')
        ui('wait-for','TxtEmpty','--value','名前・タグ検索に切り替えるか','--contains','-t','5000');ready()
        ui('wait-for','TxtCount','--value','—','-t','3000')
        ui('wait-for','TxtPageNumber','--value','—','-t','3000')
        ui('wait-for','BtnPrevious','-p','IsEnabled','--value','False','-t','3000')
        ui('wait-for','BtnNext','-p','IsEnabled','--value','False','-t','3000')
        check(name+' guidance and cleared pagination',True)
        visible_controls(name,{'TxtEmpty','TxtQuery','CmbSearchMode','BtnSearch','TxtCount','TxtPageNumber','StatusBar'})
        screenshot(name)
        recovery_mode('ModeLiteral','名前・タグ')
        literal();ui('wait-for','TxtCount','--value','1 件','-t','3000')
        ui('wait-for','Title','--value','読込完了','-t','3000');ui('wait-for','Message','--value','名前・タグの文字検索。','-t','3000')
        check(name+' literal recovery',True)
    def status():return api('/api/library/ai/status')
    def profiles():return api('/api/library/ai/profiles')
    def ready():
        ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','30000')
        time.sleep(.3)
    def dialog():
        ready();ui('invoke','BtnAIIndex');ui('wait-for','AIProfileChoice','-t','5000');ui('wait-for','AIProfileChoice','-p','IsEnabled','--value','True','-t','5000');time.sleep(.5)
    def close_dialog():ui('invoke','CloseButton');ready()
    def select(combo,option):
        if combo=='CmbSearchMode':
            modes={'ModeLiteral':(0,'名前・タグ'),'ModeSemantic':(1,'AI意味検索'),'ModeVisual':(2,'AI画像・表紙')}
            index,label=modes[option]
            # Literal is already selected on each editor-only startup; no input
            # or foreground activation is needed to verify that unchanged state.
            if args.editor_only and option=='ModeLiteral':
                ui('wait-for',combo,'--value',label,'-t','3000')
                check('GUI mode '+label,True)
                return
            ui('focus',combo)
            ui('send-keys','home '+('down '*index)+'esc','--target',combo,'--via','send-input')
            ui('wait-for',combo,'--value',label,'-t','3000')
            check('GUI mode '+label,True)
            return
        ui('invoke',combo,'--action','expand')
        for _ in range(30):
            windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
            popup=[w for w in windows if w.get('title')=='PopupHost']
            if len(popup)==1:break
            time.sleep(.1)
        if len(popup)!=1:raise RuntimeError('Expected one observed popup')
        ui('invoke',option,'--action','select',window=str(popup[0]['hwnd']))
    def choose(profile_id):
        select('AIProfileChoice','AIProfile_'+profile_id.replace(':','_'))
        ui('wait-for','AIProfileApply','-p','IsEnabled','--value','True','-t','3000')
        ui('invoke','AIProfileApply')
        for _ in range(50):
            if profiles()['selected']==profile_id:break
            time.sleep(.1)
        check('GUI saved '+profile_id,profiles()['selected']==profile_id)
        ui('wait-for','AIProfileApply','-p','IsEnabled','--value','False','-t','3000')
    def build(expect_inference=True):
        ui('wait-for','StartAIIndex','-p','IsEnabled','--value','True','-t','5000')
        # Invoke the real button's UIA pattern on the owned HWND. This runs
        # its Click handler without requiring foreground keyboard/mouse input.
        ui('invoke','StartAIIndex','--action','invoke')
        for _ in range(240):
            state=status()
            if state['state'] in ('complete','failed'):break
            if state['state']=='idle' and _>=20:raise RuntimeError('GUI did not start index within 10 seconds')
            time.sleep(.5)
        report.setdefault('index_states',[]).append({key:state[key] for key in ('state','processed','total','indexed','device','profile')})
        check('GUI index complete',state['state']=='complete' and state['indexed']==17 and (not expect_inference or state['device']=='cuda'))
        ui('wait-for','AIStatus','--value','準備完了','--contains','-t','5000')
    def show_resource_control(identifier):
        # UIA Focus alone does not scroll this nested WinUI ScrollViewer.
        # Scroll the actual owned settings viewport and check observed bounds.
        ui('scroll','AIOptions','--to','top')
        for _ in range(35):
            tree=json.loads(ui('inspect','--json','--depth','12'));stack=[tree];nodes={}
            while stack:
                node=stack.pop()
                if isinstance(node,dict):
                    if node.get('automationId')==identifier:nodes[identifier]=node
                    if node.get('type')=='Text' and node.get('name') in ('AI検索の準備','現在のAI索引'):
                        nodes[node['name']]=node
                    stack.extend(node.values())
                elif isinstance(node,list):stack.extend(node)
            title=nodes.get('AI検索の準備');summary=nodes.get('現在のAI索引');item=nodes.get(identifier)
            report.setdefault('resource_scroll_observations',[]).append({'control':identifier,'step':_,
                'title':title,'summary':summary,'item':item})
            # ScrollViewer reports content extent. Grid/StackPanel do not expose
            # UIA peers just because they have an ID. These observed TextBlock
            # peers bound the settings viewport (title gap / fixed row spacing).
            if resource_control_visible(title,summary,item):
                time.sleep(.4)
                check(identifier+' visible in scrolled settings',True);return
            ui('scroll','AIOptions','--direction','down');time.sleep(.1)
        raise RuntimeError(identifier+' cannot be brought into settings viewport')
    def resource_checks(theme):
        policy={'idle_release_seconds':60,'index_pause_ms':50}
        dialog()
        show_resource_control('AIIdleRelease')
        select('AIIdleRelease','AIIdleRelease_60')
        ui('wait-for','AIIdleRelease','--value','1分','-t','3000')
        show_resource_control('AIIndexPause')
        select('AIIndexPause','AIIndexPause_50')
        ui('wait-for','AIIndexPause','--value','50ms','-t','3000')
        show_resource_control('AISaveResource');ui('invoke','AISaveResource')
        ui('wait-for','AIResourceStatus','--value','保存しました','--contains','-t','5000')
        check(theme+' GUI policy saved and applied',api('/api/library/ai/resource')['policy']==policy and status()['resource_policy']==policy)
        ui('scroll','AIOptions','--to','bottom');time.sleep(.3)
        visible_controls('22-'+theme+'-resource',{'CloseButton','AISaveResource','AIResourceStatus','StartAIIndex','CancelAIIndex'})
        screenshot('22-'+theme+'-resource-settings')
        show_resource_control('AIRelease')
        # UIA settings traversal may exceed the saved 60-second idle policy.
        # Warm the isolated generated fixture immediately before manual release,
        # so this assertion tests the button rather than racing idle eviction.
        api('/api/library/ai/search',{'query':'傘が必要な暗い都会の景色','source':'text'})
        check(theme+' worker ready for manual GUI release',status()['resident'] and status()['device']=='cuda')
        ui('wait-for','AIRelease','-p','IsEnabled','--value','True','-t','10000')
        ui('invoke','AIRelease')
        ui('wait-for','AIReleaseResult','--value','解放しました','--contains','-t','10000')
        state=status()
        check(theme+' GUI release clears resident and telemetry',not state['resident'] and state['device']=='' and state['telemetry']=={})
        ui('wait-for','AIRelease','-p','IsEnabled','--value','False','-t','3000')
        show_resource_control('AIReleaseResult');screenshot('23-'+theme+'-resource-released');close_dialog()
        recovery_mode('ModeSemantic','AI意味検索')
        ui('set-value','TxtQuery','傘が必要な暗い都会の景色');time.sleep(.6);ui('invoke','BtnSearch');ready()
        ui('wait-for','Message','--value','最大10,000件','--contains','-t','60000')
        check(theme+' GUI search reloads CUDA',status()['resident'] and status()['device']=='cuda')
        ui('wait-for','TxtCount','--value','17 件','-t','5000')
        recovery_mode('ModeLiteral','名前・タグ');literal();stop()
        start('resource-restart-'+theme);resize(700,620);dialog()
        show_resource_control('AIIndexPause')
        ui('wait-for','AIIdleRelease','--value','1分','-t','3000')
        ui('wait-for','AIIndexPause','--value','50ms','-t','3000')
        check(theme+' saved resource policy survives restart',api('/api/library/ai/resource')['policy']==policy and status()['resource_policy']==policy and not status()['resident'])
        screenshot('24-'+theme+'-resource-restart');close_dialog();literal()
    def stop():
        nonlocal app_pid,backend,hwnd
        try:
            if app_pid:
                try:
                    try:ui('invoke','CloseButton')
                    except RuntimeError:pass
                    # WM_CLOSE is confined to the verified owned HWND and invokes
                    # the app's normal Closing guard, without foreground/global keys.
                    import ctypes
                    from ctypes import wintypes
                    user32=ctypes.WinDLL('user32',use_last_error=True)
                    kernel32=ctypes.WinDLL('kernel32',use_last_error=True)
                    user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
                    owner=wintypes.DWORD();user32.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
                    if owner.value!=app_pid:raise RuntimeError('Close target is not the owned app')
                    kernel32.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel32.OpenProcess.restype=wintypes.HANDLE
                    kernel32.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
                    kernel32.CloseHandle.argtypes=[wintypes.HANDLE]
                    process=kernel32.OpenProcess(0x100000,False,app_pid)
                    if not process:raise RuntimeError('Cannot observe owned app exit')
                    try:
                        user32.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
                        if not user32.PostMessageW(int(hwnd),0x0010,0,0):raise RuntimeError('Owned window close failed')
                        if kernel32.WaitForSingleObject(process,5000)!=0:raise RuntimeError('Owned app did not close normally')
                        report['graceful_close_count']=report.get('graceful_close_count',0)+1
                    finally:kernel32.CloseHandle(process)
                except RuntimeError:
                    report.setdefault('cleanup_warnings',[]).append('Graceful UI close unavailable; stopped owned test PID')
                finally:
                    subprocess.run(['powershell','-NoProfile','-Command',f'if(Get-Process -Id {app_pid} -ErrorAction SilentlyContinue){{Stop-Process -Id {app_pid}}}'],capture_output=True,check=True)
                    app_pid=None;hwnd=None
        finally:
            try:
                if backend:
                    backend.terminate();backend.wait(timeout=10);backend=None
            finally:
                for log in logs:log.close()
                logs.clear();time.sleep(.6)
    def start(phase,override=None):
        nonlocal backend,app_pid,hwnd,headers
        # Refuse another API or native Aredoko instance; never attach to unknown data.
        try:
            urllib.request.urlopen(origin+'/api/session',timeout=.5).close()
        except urllib.error.HTTPError:raise RuntimeError('Port is already occupied')
        except urllib.error.URLError:pass
        else:raise RuntimeError('Port is already occupied')
        existing=subprocess.run(['powershell','-NoProfile','-Command','if(Get-Process Aredoko.WinUI -ErrorAction SilentlyContinue){exit 1}'],capture_output=True)
        if existing.returncode:raise RuntimeError('Existing native app; stop your own app first')
        for suffix in ('out','err'):logs.append((target/(phase+'-api.'+suffix)).open('w',encoding='utf-8'))
        command=[sys.executable,'app/production_server.py','--db',str(target/'catalog.sqlite'),'--ai-settings',str(settings)]
        if override:command+=['--ai-profile',str(override)]
        backend=subprocess.Popen(command,cwd=REPO,stdout=logs[0],stderr=logs[1],creationflags=subprocess.CREATE_NO_WINDOW,env={**env,'PYTHONIOENCODING':'utf-8'})
        for _ in range(100):
            if backend.poll() is not None:raise RuntimeError('Owned API failed')
            try:
                session=api('/api/session');headers={'X-Aredoko-Token':session['token'],'Origin':origin};break
            except urllib.error.URLError:time.sleep(.1)
        launch=json.loads(cli('run','src/Aredoko.WinUI','-c','Release','--arch','x64','-p','Platform=x64','-p','SelfContained=true','--no-build','--detach','--json','--args','--ui-theme '+ui_theme.lower()))
        app_pid=int(launch['ProcessId'])
        for _ in range(50):
            windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
            main=[w for w in windows if w.get('hwnd') and 'Aredoko' in w.get('title','') and w.get('title')!='PopupHost']
            if len(main)==1:break
            time.sleep(.1)
        if len(main)!=1:raise RuntimeError('Expected owned main window')
        (target/(phase+'-launch.json')).write_text(json.dumps(launch),encoding='utf-8')
        hwnd=str(main[0]['hwnd']);ready()
    def semantic():
        select('CmbSearchMode','ModeSemantic');ui('set-value','TxtQuery','傘が必要な暗い都会の景色');time.sleep(.6);ui('invoke','BtnSearch');ready()
        result=api('/api/library/ai/search',{'query':'傘が必要な暗い都会の景色','source':'text'})
        check('CUDA Japanese query',status()['device']=='cuda' and result['items'][0]['title']=='雨の夜の街並み.wav')
        ui('wait-for','Item'+str(result['items'][0]['id']),'-t','5000')
    def literal():
        select('CmbSearchMode','ModeLiteral');ui('set-value','TxtQuery','雨の夜');time.sleep(.6);ui('invoke','BtnSearch');ready()
        result=api('/api/items?q='+urllib.parse.quote('雨の夜'))
        check('Literal independent of model',result['total']==1)
        ui('wait-for','Item'+str(result['items'][0]['id']),'-t','5000')
    try:
        for key in ('text','missing','invalid'):
            path=folder/names[key]
            if path.exists():raise RuntimeError('Test config collision')
            data=DEFAULT_PROFILE.to_dict();data.update(label='GUI test '+key,modalities=['text'],precision='float32')
            if key=='missing':data['directory']=nonce+'-missing-weights'
            path.write_text('{invalid' if key=='invalid' else json.dumps(data),encoding='utf-8');profile_files.append(path)
        start('default');api('/api/library/roots',{'path':str(media),'consent':True});api('/api/library/scan',{'root_id':1})
        for _ in range(100):
            if api('/api/library/scan')['state']=='complete':break
            time.sleep(.1)
        # Refresh native catalog after API registration; actual index is started in GUI.
        ui('invoke','BtnSearch');ready()
        if args.layout_checks:
            visible_controls('10-wide',{'TxtQuery','CmbKind','CmbSearchMode','BtnAIIndex','BtnLayout','BtnSearch','TxtCount'})
            screenshot('10-wide-library');ui('invoke','BtnLayout');ready();screenshot('11-wide-tiles');ui('invoke','BtnLayout')
            resize(700,620);visible_controls('12-narrow',{'TxtQuery','CmbKind','CmbSearchMode','BtnAIIndex','BtnLayout','BtnSearch','TxtCount'});screenshot('12-narrow-library')
            resize(1200,820)
        if not args.editor_only:
            dialog();build()
            default_profile=status()['profile'];check('Default active',profiles()['active']=='default')
            choose('local:'+names['text']);check('No hot swap',status()['profile']==default_profile and profiles()['active']=='default')
            screenshot('01-next-launch');close_dialog();semantic();stop()
            start('text');check('Saved text profile active',profiles()['active']=='local:'+names['text'] and status()['modalities']==['text'] and status()['profile']!=default_profile and status()['indexed']==0)
            dialog();build();screenshot('02-text-only');close_dialog();semantic()
            result=api('/api/library/ai/search',{'query':'青い画像','source':'cover'},expected=503);check('Text-only cover refused with guidance','画像' in result['error'])
            select('CmbSearchMode','ModeVisual');ui('set-value','TxtQuery','青い画像');time.sleep(.6);ui('invoke','BtnSearch');ready();screenshot('03-cover-unavailable');literal()
            dialog();choose('default');check('Text stays active until restart',profiles()['active']=='local:'+names['text']);close_dialog();stop()
            start('restored');check('Original index reused',status()['profile']==default_profile and status()['indexed']==17 and status()['state']=='complete')
            semantic();screenshot('04-restored-index');dialog();choose('local:'+names['missing']);close_dialog();stop()
            start('missing');check('Missing model unavailable',not status()['available']);literal();dialog();ui('wait-for','StartAIIndex','-p','IsEnabled','--value','False','-t','3000');screenshot('05-missing');close_dialog();stop()
            settings.write_text(json.dumps({'version':1,'profile':'local:'+names['invalid']}),encoding='utf-8')
            start('invalid');check('Invalid saved config fallback',not status()['available'] and bool(profiles()['error']));literal();dialog();screenshot('06-invalid');choose('default');close_dialog();stop()
            settings.write_text('{broken',encoding='utf-8')
            start('override',REPO/'config/ai-profiles/embeddinggemma-2.json');check('Explicit override beats corrupt settings',profiles()['command_line_override'] and status()['profile']==default_profile);semantic();dialog();screenshot('07-override');choose('default');close_dialog();stop()
            report['profile_verification']='pass'
        else:stop()
        start('editor');literal()
        row=api('/api/items?q='+urllib.parse.quote('雨の夜'))['items'][0]
        ui('invoke','Item'+str(row['id']),'--action','select');ui('wait-for','TxtTags','-p','IsEnabled','--value','True','-t','3000')
        original=', '.join(row['tags'])
        ui('invoke','ChkFavorite','--action','toggle-on');ui('wait-for','BtnSave','-p','IsEnabled','--value','True','-t','3000');ui('invoke','BtnSave')
        # A disabled parent editor can make BtnSave appear disabled before POST completes.
        ui('wait-for','TxtEditStatus','--value','保存しました','-t','5000')
        for _ in range(50):
            if api('/api/items?q='+urllib.parse.quote('雨の夜'))['items'][0]['favorite']:break
            time.sleep(.1)
        check('GUI favorite persisted',api('/api/items?q='+urllib.parse.quote('雨の夜'))['items'][0]['favorite'])
        ui('set-value','TxtTags','unsaved-profile-dialog-proof');ui('invoke','BtnAIIndex');ui('wait-for','PrimaryButton','-t','3000');screenshot('08-dirty-guard')
        ui('invoke','CloseButton');ui('wait-for','TxtTags','--value','unsaved-profile-dialog-proof','-t','3000')
        check('Dirty keep preserves editor and database',api('/api/items?q='+urllib.parse.quote('雨の夜'))['items'][0]['tags']==row['tags'])
        ui('set-value','TxtTags',original);dialog();close_dialog();stop()
        start('editor-restart');literal()
        check('GUI favorite survives restart',api('/api/items?q='+urllib.parse.quote('雨の夜'))['items'][0]['favorite'])
        ui('invoke','Item'+str(row['id']),'--action','select')
        ui('wait-for','ChkFavorite','-p','IsEnabled','--value','True','-t','3000')
        tree=json.loads(ui('inspect','--json','--depth','12'))
        (target/'editor-restart-tree.json').write_text(json.dumps(tree,ensure_ascii=False,indent=2),encoding='utf-8')
        stack=[tree];favorites=[]
        while stack:
            node=stack.pop()
            if isinstance(node,dict):
                if node.get('automationId')=='ChkFavorite':favorites.append(node)
                stack.extend(node.values())
            elif isinstance(node,list):stack.extend(node)
        check('GUI restored favorite toggle',len(favorites)==1 and favorites[0].get('isEnabled') and favorites[0].get('toggleState')=='on')
        screenshot('09-editor-restart');stop()
        if args.layout_checks:
            settings.write_text(json.dumps({'version':1,'profile':'local:'+names['missing']}),encoding='utf-8')
            start('layout-missing');resize(700,620);dialog()
            ui('wait-for','StartAIIndex','-p','IsEnabled','--value','False','-t','3000')
            visible_controls('13-small-dialog',{'CloseButton','AIProfileChoice','AIProfileWarning'});screenshot('13-small-missing-dialog');close_dialog();stop()
        if args.appearance_checks:
            for theme in ('Light','Dark'):
                ui_theme=theme
                settings.write_text(json.dumps({'version':1,'profile':'local:'+names['text']}),encoding='utf-8')
                start('appearance-'+theme);record_display('appearance-'+theme);resize(700,620)
                check(theme+' text-only available',status()['available'] and status()['modalities']==['text'])
                # The production API rejects unsupported covers before encoder loading.
                error=api('/api/library/ai/search',{'query':'青い画像','source':'cover'},expected=503)
                check(theme+' real cover capability error','画像' in error['error'])
                unavailable_search('ModeVisual','AI画像・表紙','14-'+theme+'-cover-error')
                row=api('/api/items?q='+urllib.parse.quote('雨の夜'))['items'][0]
                ui('invoke','Item'+str(row['id']),'--action','select');ui('wait-for','TxtTags','-p','IsEnabled','--value','True','-t','3000')
                screenshot('15-'+theme+'-details');dialog()
                visible_controls('16-'+theme+'-dialog',{'CloseButton','AIProfileChoice','AIProfileWarning','AIStatus','StartAIIndex','CancelAIIndex'})
                ui('wait-for','AIStatus','--value','最大10,000件','--contains','-t','5000')
                check(theme+' API and dialog coverage',status()['limit']==10000)
                screenshot('16-'+theme+'-dialog')
                if args.coverage_checks:
                    if theme=='Dark':check('Dark saved index available before reuse',status()['state']=='complete' and status()['indexed']==17)
                    # A fully fresh restart intentionally leaves the lazy encoder
                    # unloaded. The later real semantic query asserts CUDA.
                    build(expect_inference=(theme=='Light'))
                    state=status()
                    report.setdefault('coverage_gpu_states',[]).append({key:state[key] for key in ('device','processed','total','indexed','dimension','modalities','telemetry')})
                    screenshot('18-'+theme+'-indexed-dialog')
                close_dialog()
                if args.coverage_checks:
                    recovery_mode('ModeSemantic','AI意味検索')
                    ui('set-value','TxtQuery','傘が必要な暗い都会の景色');time.sleep(.6);ui('invoke','BtnSearch');ready()
                    # Do not race a direct API query against the GUI's first
                    # lazy-load search: AISearch intentionally rejects overlap.
                    ui('wait-for','Message','--value','最大10,000件','--contains','-t','60000')
                    ui('wait-for','Item'+str(row['id']),'-t','5000')
                    ui('wait-for','TxtCount','--value','17 件','-t','5000');ready()
                    result=api('/api/library/ai/search',{'query':'傘が必要な暗い都会の景色','source':'text'})
                    check(theme+' real CUDA search and coverage',status()['device']=='cuda' and result['coverage_limit']==10000 and result['total']==17 and result['items'][0]['title']=='雨の夜の街並み.wav')
                    screenshot('19-'+theme+'-semantic-coverage')
                    recovery_mode('ModeLiteral','名前・タグ');literal()
                if args.resource_checks:resource_checks(theme)
                ui('invoke','Item'+str(row['id']),'--action','select');ui('wait-for','TxtTags','-p','IsEnabled','--value','True','-t','3000')
                ui('set-value','TxtTags','unsaved-'+theme+'-theme-proof');ui('invoke','BtnAIIndex')
                ui('wait-for','PrimaryButton','-t','3000');screenshot('20-'+theme+'-dirty-dialog')
                ui('invoke','CloseButton');ui('wait-for','TxtTags','--value','unsaved-'+theme+'-theme-proof','-t','3000')
                check(theme+' dirty keep leaves saved tags unchanged',api('/api/items?q='+urllib.parse.quote('雨の夜'))['items'][0]['tags']==row['tags'])
                ui('set-value','TxtTags',', '.join(row['tags']))
                ui('invoke','BtnRoots');ui('wait-for','RootPath','-t','5000')
                visible_controls('21-'+theme+'-roots',{'CloseButton','RootPath','RootList'})
                screenshot('21-'+theme+'-roots-dialog');close_dialog();stop()
            ui_theme='Light'
            settings.write_text(json.dumps({'version':1,'profile':'local:'+names['missing']}),encoding='utf-8')
            start('appearance-missing');record_display('appearance-missing');resize(700,620)
            check('Missing profile unavailable for semantic search',not status()['available'])
            unavailable_search('ModeSemantic','AI意味検索','17-Light-missing-error');stop()
        if args.coverage_checks:report['coverage_verification']='pass'
        if args.resource_checks:report['resource_verification']='pass'
        check('Generated source hashes unchanged',hashes=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in media.iterdir()})
        report['pass']=True
    except Exception as ex:
        report['error']=str(ex)
        if app_pid and hwnd:
            try:
                screenshot('failure')
                (target/'failure-tree.json').write_text(ui('inspect','--json','--depth','12'),encoding='utf-8')
            except Exception:pass
        raise
    finally:
        try:stop()
        finally:
            try:cli('ui','yield')
            finally:
                # Delete only the exact generated profile files, never the directory.
                for path in profile_files:
                    if path.resolve().parent!=folder.resolve():raise RuntimeError('Unsafe cleanup target')
                    path.unlink(missing_ok=True)
                try:
                    report['source_hashes_unchanged']=hashes=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in media.iterdir()}
                except OSError:
                    report['source_hashes_unchanged']=False
                if not report['source_hashes_unchanged']:report['pass']=False
                (target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                if not report['source_hashes_unchanged']:raise RuntimeError('Generated source hashes changed')
    print(json.dumps(report,ensure_ascii=True))

if __name__=='__main__':main()
