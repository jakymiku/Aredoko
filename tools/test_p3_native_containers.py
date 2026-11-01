"""Generated-only Portable native card recycling acceptance. No model or private data."""
import argparse, ctypes, hashlib, json, os, secrets, socket, subprocess, sys,re, threading, time, traceback
from ctypes import wintypes
from http.server import ThreadingHTTPServer
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'app'),str(REPO/'tools')]
from production import ProductionCatalog
from production_server import production_handler, DisabledAI
from ai_settings import AIProfileSettings
from wd_tagger import DisabledTagger
from create_preview_fixture import png
from native_ui_tools import nodes

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--frontend',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--usability-u1',action='store_true')
    parser.add_argument('--favorite-only',action='store_true')
    parser.add_argument('--usability-u2',action='store_true')
    parser.add_argument('--usability-u3',action='store_true')
    parser.add_argument('--uia-only',action='store_true',help='Record input/hover checks as unverified; use UIA only')
    parser.add_argument('--real-fixture',type=Path,help='Global-edge case only: reuse generated real-file fixture with a copied catalog')
    parser.add_argument('--audio-content',action='store_true',help='Generated WAV + supplied CPU encoder; no playback or GPU')
    parser.add_argument('--audio-search-only',action='store_true',help='Prepare generated audio via CPU; native scenario only switches mode and checks result time')
    parser.add_argument('--audio-similarity-only',action='store_true',help='Cached audio origin similarity and navigation only, supplied CPU vectors')
    parser.add_argument('--toolbar-wrap-only',action='store_true',help='UIA-only width/long search label and folder/shelf header transitions')
    parser.add_argument('--compact-toolbar',action='store_true',help='Generated mixed media, toolbar geometry and explicit detail draft preservation')
    parser.add_argument('--video-audio-content',action='store_true',help='Generated video PCM, supplied CPU vectors, no playback or GPU')
    parser.add_argument('--bulk-favorite-patch',action='store_true',help='Generated 745-item library; retained bulk favorites and fallback')
    parser.add_argument('--video-content',action='store_true',help='Generated silent MP4s and supplied CPU encoder; no playback, model or GPU')
    parser.add_argument('--video-history-only',action='store_true',help='Pre-index on CPU, then only cached video similarity and folder navigation')
    parser.add_argument('--viewer-choice',action='store_true',help='Generated media: settings persistence, failed external fallback and internal double-click; no external app launched')
    parser.add_argument('--setup-plan',action='store_true',help='UIA-only feature plan and opt-out; no foreground activation, input, download, model or GPU')
    parser.add_argument('--setup-return',action='store_true',help='UIA-only return from acquisition, placement and index settings; no acquisition or inference')
    parser.add_argument('--setup-recovery',action='store_true',help='Setup return plus safe recovery, diagnostic return and saved-profile restart state')
    parser.add_argument('--setup-skip-download',action='store_true',help='Remaining setup case only: do not repeat an already accepted download return')
    parser.add_argument('--favorite-patch',action='store_true',help='UIA-only favorite edits keep the literal session, selection and unsaved tags without rebuilding')
    parser.add_argument('--favorite-root-removal-only',action='store_true',help='Only remaining last-folder guidance and registration/media retention')
    parser.add_argument('--folder-settings-remaining',action='store_true',help='Only folder draft reopen/switch and batch; prior individual saves remain recorded')
    parser.add_argument('--folder-settings-layout',action='store_true',help='Generated roots: section layout and independent draft saves; UIA only')
    parser.add_argument('--agent-desktop-only',action='store_true',help='Only remaining optional Agent Desktop probe; no repeated folder edits')
    parser.add_argument('--agent-desktop',type=Path,help='Optional development-only agent-desktop headless probe over the owned test window')
    parser.add_argument('--favorite-root-actions',action='store_true',help='UIA-only favorite folder commands, dirty tag guard and last-folder removal')
    parser.add_argument('--shelf-picker-remaining',action='store_true',help='Only remaining shelf save/reopen, then acquisition explanations and recovery-guide footer; no jobs')
    parser.add_argument('--shelf-picker-filter',action='store_true',help='UIA-only shelf filtering retains hidden memberships and unsaved tags')
    parser.add_argument('--empty-ai-recovery',action='store_true',help='UIA-only direct AI setup and literal-search recovery on generated images')
    parser.add_argument('--setup-choice-layout',action='store_true',help='Combine contextual feedback with explained purpose choices; no acquisition or inference')
    parser.add_argument('--empty-guidance-only',action='store_true',help='UIA-only literal/AI-unavailable feedback and browse menu cleanup on navigation')
    parser.add_argument('--footer-actions-only',action='store_true',help='UIA-only range menu, retained selection/draft and refresh over145 generated PNGs')
    parser.add_argument('--folder-toolbar-only',action='store_true',help='UIA-only single folder return action and registration form access')
    parser.add_argument('--diagnostic-footer-only',action='store_true',help='UIA-only diagnostic native close footer, no clipboard access')
    parser.add_argument('--guide-layout-only',action='store_true',help='UIA-only concise guide, preserved details and folder/AI entry points')
    parser.add_argument('--settings-feedback-only',action='store_true',help='UIA-only persistent settings save feedback at either scroll edge')
    parser.add_argument('--settings-layout-only',action='store_true',help='UIA-only settings action grid, footer save and reopen')
    parser.add_argument('--detail-fields-only',action='store_true',help='UIA-only wrapped tags and inline shelf picker without repeating captions')
    parser.add_argument('--detail-polish',action='store_true',help='UIA-only two generated PNGs: deduplicated filenames, bounded long title and draft preservation')
    parser.add_argument('--card-captions',action='store_true',help='UIA-only library/shelf caption slots and 60/180 percent size changes')
    parser.add_argument('--caption-menu-only',action='store_true',help='Remaining caption case only: size menu closes on navigation/layout')
    parser.add_argument("--detail-actions",action="store_true");parser.add_argument("--detail-navigation-only",action="store_true");parser.add_argument("--theme",choices=("light","dark"),default="dark");parser.add_argument("--continuous",action="store_true");parser.add_argument("--library-tail",action="store_true");parser.add_argument("--global-edge",action="store_true");parser.add_argument("--shelf-management",action="store_true");parser.add_argument("--initial-loading",action="store_true");parser.add_argument("--viewer-boundary120",action="store_true");args=parser.parse_args();target=args.output.resolve();front=args.frontend.resolve()
    if os.name!='nt' or not target.is_relative_to(REPO/'data/ai-ui') or target.exists():parser.error('New dedicated output under data/ai-ui required')
    if not (front.is_relative_to(REPO/'data/ai-ui') or front.is_relative_to(REPO/'dist')) or not (front/'Aredoko.WinUI.exe').is_file():parser.error('Dedicated published frontend required')
    if args.real_fixture and not args.global_edge:parser.error('Real fixture requires the bounded global-edge case')
    if args.bulk_favorite_patch:args.continuous=True
    if args.toolbar_wrap_only:args.compact_toolbar=True;args.uia_only=True
    if args.compact_toolbar:args.detail_actions=True
    if args.viewer_choice:args.detail_actions=True
    if args.setup_recovery:args.setup_return=True
    if args.setup_skip_download and not args.setup_return:parser.error('Skipping download requires the bounded setup-return case')
    if args.favorite_patch:args.detail_actions=True;args.uia_only=True
    if args.caption_menu_only:args.card_captions=True
    if args.card_captions:args.detail_polish=True
    if args.favorite_root_removal_only:args.favorite_root_actions=True
    if args.agent_desktop_only:
        if not args.agent_desktop:parser.error('agent-desktop-only requires the explicit executable')
        args.folder_settings_remaining=True
    if args.folder_settings_remaining:args.folder_settings_layout=True
    if args.folder_settings_layout:args.detail_polish=True
    if args.agent_desktop and not (args.folder_settings_layout or args.settings_feedback_only):parser.error('agent-desktop probe requires a bounded folder or settings case')
    if args.favorite_root_actions:args.detail_polish=True
    if args.shelf_picker_remaining:args.shelf_picker_filter=True
    if args.shelf_picker_filter:args.detail_polish=True
    if args.empty_ai_recovery:args.detail_polish=True
    if args.setup_choice_layout:args.empty_guidance_only=True
    if args.empty_guidance_only:args.detail_polish=True
    if args.footer_actions_only:args.uia_only=True
    if args.folder_toolbar_only:args.detail_polish=True
    if args.diagnostic_footer_only:args.detail_polish=True
    if args.guide_layout_only:args.detail_polish=True
    if args.settings_feedback_only:args.detail_polish=True
    if args.settings_layout_only:args.detail_polish=True
    if args.detail_fields_only:args.detail_polish=True
    if args.detail_polish:args.uia_only=True
    if args.setup_plan or args.setup_return:args.detail_actions=True;args.uia_only=True
    if args.video_history_only:args.video_content=True
    if args.audio_similarity_only:args.audio_search_only=True
    if args.audio_search_only:args.audio_content=True
    # Fail before launching any owned app if the app-execution alias cannot run
    # in this process context. A readable PATH entry is not an executable probe.
    subprocess.run(['winapp','--version'],check=True,capture_output=True,timeout=15)
    target.mkdir(parents=True);report={'pass':False,'checks':[],'screenshots':[],'target':'local','visual_review':'pending','authorization':'2026-10-24 current local-test-policy; generated isolated data','source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()}
    if args.video_content:report['authorization']='Explicit per-run permission: generated silent MP4s, dedicated DB, CPU vectors; no playback/GPU/models/normal DB/Alpha'
    if args.detail_actions:report['authorization']='2026-10-24 explicit human approval: contextual detail GUI on dedicated fixtures, Light/Dark; no AI/GPU inference'
    report['theme']=args.theme
    if args.compact_toolbar:report['toolbar_audit_sha256']=hashlib.sha256((REPO/'tools/ui_compact_toolbar_audit.py').read_bytes()).hexdigest()
    report['detail_audit_sha256']=hashlib.sha256((REPO/'tools/ui_detail_actions_audit.py').read_bytes()).hexdigest()
    report['app_assembly_sha256']=hashlib.sha256((front/'Aredoko.WinUI.dll').read_bytes()).hexdigest()
    report['source_worktree_diff_sha256']=hashlib.sha256(subprocess.check_output(['git','diff','--','src'],cwd=REPO)).hexdigest()
    tracked=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','--','app','src'],cwd=REPO,text=True).splitlines()
    report['source_files']={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in tracked}
    report['audit_script_sha256']=hashlib.sha256((REPO/'tools/ui_continuous_browse_audit.py').read_bytes()).hexdigest()
    env={**os.environ,'WINAPP_UI_WORKFLOW_ID':'aredoko-p3-native-content-ready-20261024','LOCALAPPDATA':str(target/'user'),'APPDATA':str(target/'user')}
    cat=server=thread=proc=None;hwnd=None
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    user.SetForegroundWindow.argtypes=[wintypes.HWND];user.SetForegroundWindow.restype=wintypes.BOOL
    user.GetForegroundWindow.restype=wintypes.HWND
    def check(name,value):
        report['checks'].append({'name':name,'pass':bool(value)});print(name, bool(value),flush=True)
        if not value:raise AssertionError(name)
    command_timeout=70 if args.global_edge else 35
    def cli(*args):
        result=subprocess.run(['winapp','ui',*map(str,args)],cwd=REPO,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=command_timeout)
        with (target/'commands.log').open('a',encoding='utf-8') as log:log.write(json.dumps({'args':list(map(str,args)),'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr},ensure_ascii=False)+'\n')
        if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        return result.stdout
    def ui(*args):
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
        if owner.value!=proc.pid:raise RuntimeError('Owned HWND changed')
        return cli(*args,'-w',hwnd)
    def resize(width,height):
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
        if owner.value!=proc.pid:raise RuntimeError('Owned resize target changed')
        user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
        user.GetDpiForWindow.argtypes=[wintypes.HWND];user.GetDpiForWindow.restype=wintypes.UINT
        scale=user.GetDpiForWindow(int(hwnd))/96
        if not user.SetWindowPos(int(hwnd),None,0,0,round(width*scale),round(height*scale),0x16):raise ctypes.WinError(ctypes.get_last_error())
        time.sleep(.3)
    def tree():return {n['automationId']:n for n in nodes(json.loads(ui('inspect','--depth','18','--json'))) if n.get('automationId')}
    def shot(name):
        path=target/(name+'.png');ui('screenshot',*(() if args.uia_only else ('--focus',)),'--output',path);report['screenshots'].append(str(path));path.with_suffix('.json').write_text(json.dumps(tree(),ensure_ascii=False,indent=2),encoding='utf-8')
    def ready():ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','60000' if args.global_edge else '10000')
    def sources():
        if not args.detail_polish:return {p.name:[hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns] for p in media.iterdir()}
        from storage_lease import plain_path
        value={}
        for path in media.rglob('*'):
            path=plain_path(path,directory=path.is_dir())
            if path.is_file():value[path.relative_to(media).as_posix()]=[hashlib.sha256(path.read_bytes()).hexdigest(),path.stat().st_mtime_ns]
        return value
    try:
        media=target/'media';media.mkdir()
        for i in range(0 if args.detail_polish or args.detail_actions or args.global_edge or args.audio_content or args.video_content or args.video_audio_content else 745 if args.continuous or args.library_tail else 125 if args.viewer_boundary120 else 145):(media/f'generated-{i:03}.png').write_bytes(png(width=120,height=160,color=(40+i%180,80,160)))
        if args.detail_polish:
            from ui_detail_polish_audit import create_media
            create_media(media)
        if args.video_audio_content:
            from ui_video_audio_audit import create_media
            create_media(media)
        if args.video_content:
            from ui_video_content_audit import create_media
            create_media(media)
        if args.audio_content:
            from ui_audio_content_audit import create_media
            create_media(media)
        if args.usability_u1:
            (media/'generated-000.png').rename(media/('generated-000-Test1145141919810364364-'+('LongName'*10)+'.png'))
        if args.usability_u2:
            import zipfile
            (media/'generated-144.png').unlink()
            with zipfile.ZipFile(media/'zz-usability.cbz','w') as book:
                for page in range(5):book.writestr(f'{page}.png',png(width=300,height=500,color=(40+page*30,80,160)))
            (target/'viewer-settings.json').write_text(json.dumps({'version':1,'wheel_up_advances':False,'always_show_controls':True}),encoding='utf-8')
        if args.usability_u3:
            from PIL import Image
            for old,name,kind,count in [('generated-144.png','zz-clock.webp','WEBP',12),('generated-143.png','zz-clock.png','PNG',72)]:
                (media/old).unlink()
                frames=[Image.new('RGBA',(64,48),(50+i%150,80,150,128 if kind=='PNG' else 255)) for i in range(count)]
                try:frames[0].save(media/name,format=kind,save_all=True,append_images=frames[1:],duration=[40+i%3*20 for i in range(count)],loop=0)
                finally:
                    for frame in frames:frame.close()
            (target/'viewer-settings.json').write_text(json.dumps({'version':1,'wheel_up_advances':False,'always_show_controls':True}),encoding='utf-8')
        if args.detail_actions:
            from ui_detail_actions_audit import create_media
            create_media(media)
        if args.real_fixture:
            from ui_real_library_audit import copy_fixture
            fixture,source_digest=copy_fixture(args.real_fixture,target/'catalog.sqlite')
            report['real_fixture']=fixture
            def sources():return source_digest()
        cat=ProductionCatalog(target/'catalog.sqlite')
        if args.global_edge and not args.real_fixture:
            from ui_global_edge_audit import create_metadata
            create_metadata(cat,media)
        elif not args.real_fixture:
            root=cat.add_root(str(media));cat.start_scan(root)
            if cat._worker:cat._worker.join(15)
        before=sources()
        if args.viewer_choice and args.uia_only:
            (target/'viewer-settings.json').write_text(json.dumps({'version':1,'wheel_up_advances':False,'theme':args.theme,'double_click_viewer':'internal'}),encoding='utf-8')
        first=cat.search()['items'][0];check('generated catalog ready',cat.search()['total']==(3 if args.video_audio_content else 2 if args.detail_polish or args.audio_content or args.video_content else 50000 if args.global_edge else 6 if args.detail_actions else 745 if args.continuous or args.library_tail else 125 if args.viewer_boundary120 else 145))
        if args.detail_actions:
            shelf=cat.change_shelf('create',name='確認用の棚')['id']
            cat.change_shelf('assign',entity='item',object_ids=[row['id'] for row in cat.search()['items']],shelf_ids=[shelf])
        if args.shelf_management:
            a=cat.change_shelf('create',name='素材')['id'];b=cat.change_shelf('create',name='資料')['id'];cat.change_shelf('create',name='空の棚')
            cat.change_shelf('assign',entity='item',object_ids=[first['id']],shelf_ids=[a,b])
        profiles=AIProfileSettings(REPO,target/'ai-settings.json',profile_directory=target/'profiles',ai_python=str(target/'missing-python'),models_root=target/'missing-models')
        instance=secrets.token_hex(16);env['AREDOKO_STARTUP_INSTANCE']=instance
        extras={}
        if args.folder_settings_layout:
            from ui_folder_settings_audit import prepare
            report['folder_settings_fixture']=prepare(cat,target,remaining=args.folder_settings_remaining)
        if args.favorite_root_actions:
            from ui_favorite_root_actions_audit import prepare
            report['favorite_root_fixture']=prepare(cat,target,file_favorite=not args.favorite_root_removal_only)
        if args.shelf_picker_filter:
            from ui_shelf_filter_audit import prepare
            report['shelf_filter_fixture']=prepare(cat)
        if args.setup_plan or args.setup_return or args.setup_choice_layout or args.shelf_picker_remaining:
            from ai_acquisition_registry import load_trusted_specs
            extras['acquisition_specs']=load_trusted_specs(REPO)
        if args.video_content:
            from ui_video_content_audit import create_feature
            video_feature,video_gate,video_reached=create_feature(cat)
            if args.video_history_only:
                video_gate.set();video_feature.start({'consent':True});video_feature.owner.thread.join(20)
                if video_feature.status()['state']!='completed':raise RuntimeError('Generated CPU video setup failed')
            extras['video_feature']=video_feature
        if args.video_audio_content:
            from ui_video_audio_audit import create_feature
            audio_feature,audio_gate,audio_reached=create_feature(cat)
            extras['audio_feature']=audio_feature
        if args.audio_content:
            from ui_audio_content_audit import create_feature
            audio_feature,audio_gate,audio_reached=create_feature(cat)
            if args.audio_search_only:
                audio_gate.set();audio_feature.start({'consent':True})
                audio_feature.owner.thread.join(10)
                if audio_feature.status()['state']!='completed':raise RuntimeError('Generated CPU audio setup failed')
            extras['audio_feature']=audio_feature
        if args.setup_return:
            # The supplied missing-model directory is also the saved directory;
            # otherwise the deliberate command-line fixture override correctly
            # appears as a restart-only location change before any UI action.
            (target/'launch-settings.json').write_text(json.dumps({'models_root':str(target/'missing-models')}),encoding='utf-8')
        handler=production_handler(cat,secrets.token_hex(32),ai=DisabledAI(),profiles=profiles,tagger=DisabledTagger(),instance_id=instance,**extras);handler.log_message=lambda *args:None
        if args.real_fixture:
            from ui_real_library_audit import install_cancel_gate
            real_gate=install_cancel_gate(handler)
        if args.initial_loading or args.usability_u1:
            empty_shelf=cat.change_shelf('create',name='案内確認用の空棚')['id']
            gate=threading.Event();original_provider=handler.results.provider
            def held(conditions,consume,cancelled):
                deadline=time.monotonic()+40
                while not gate.wait(.05):
                    if cancelled():raise InterruptedError('Generated test cancellation')
                    if time.monotonic()>deadline:raise TimeoutError('Generated test hold exceeded')
                return original_provider(conditions,consume,cancelled)
            handler.results.provider=held
            if args.usability_u1:gate.set()
        server=ThreadingHTTPServer(('127.0.0.1',8769),handler,bind_and_activate=False)
        server.allow_reuse_address=False
        server.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        server.server_bind();server.server_activate()
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        with (target/'app.log').open('w',encoding='utf-8') as log:
            proc=subprocess.Popen([str(front/'Aredoko.WinUI.exe'),'--ui-theme',args.theme,'--viewer-settings',str(target/'viewer-settings.json')],cwd=front,env=env,stdout=log,stderr=subprocess.STDOUT)
        report['owned_pid']=proc.pid
        for _ in range(30):
            if proc.poll() is not None:raise RuntimeError('Owned app exited: '+str(proc.returncode))
            windows=json.loads(cli('list-windows','-a',proc.pid,'--json'));windows=[w for w in windows if w.get('title') and w['title']!='PopupHost']
            if len(windows)==1:hwnd=str(windows[0]['hwnd']);break
            time.sleep(.2)
        check('owned native window available',hwnd is not None)
        if (args.usability_u1 and not args.uia_only) or args.global_edge or args.audio_content or (args.compact_toolbar and not args.uia_only) or args.video_content or args.video_audio_content or args.bulk_favorite_patch or (args.viewer_choice and not args.uia_only):
            if args.video_content or args.video_audio_content or args.bulk_favorite_patch or args.viewer_choice:ready()
            # The owner launches this one test process; use normal Windows
            # activation, never input attachment, security bypass or other apps.
            report['foreground_activation_requested']=bool(user.SetForegroundWindow(int(hwnd)))
            report['foreground_confirmed']=user.GetForegroundWindow()==int(hwnd)
            check('owned test window foreground confirmed',report['foreground_confirmed'])
        if args.initial_loading:
            ui('wait-for','TxtEmpty','--value','検索結果を準備しています…','-t','10000');shot('loading')
            ui('invoke','BtnCancelSearch');ui('wait-for','TxtEmpty','--value','検索を中断しました。もう一度「検索」を押してください。','-t','10000');shot('cancelled')
            gate.set();ui('invoke','BtnSearch')
        if args.real_fixture:
            from ui_real_library_audit import cancel_then_prepare
            cancel_then_prepare(ui,tree,shot,check,report,real_gate)
        key='Item'+str(first['id']);ready();ui('wait-for',key,'-t','60000' if args.global_edge else '10000');shot('list-initial')
        visible=tree();count=sum(re.fullmatch(r'Item\d+',k) is not None for k in visible)
        check('panel realizes fewer cards than sixty-result page',0<count<60)
        if args.usability_u1:
            from ui_usability_u1_audit import audit
            audit(ui,tree,shot,check,first['id'],gate,cat,interactive=not args.uia_only,favorite=args.favorite_only)
            if args.uia_only:report['unverified']=['pointer hover/tooltip','small-size slider and name ellipsis','context-menu invocation','Ctrl Home/End physical input']
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.usability_u2 or args.usability_u3:
            from ui_usability_u2_audit import audit
            audit(ui,cli,tree,shot,check,report,proc.pid,hwnd,first['id'],cat,user,animations=args.usability_u3)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.initial_loading:
            for nav,expected,name in (("NavHistory","閲覧履歴はありません。作品を開くと、ここに表示されます。","empty-history"),("NavFavorites","お気に入りはまだありません。作品の右クリックメニューや詳細から登録できます。","empty-favorites")):
                ui("invoke",nav);ui("wait-for","TxtEmpty","--value",expected,"-t","10000");shot(name);check(name+" context guidance",True)
            ui("invoke","NavShelf");ui("wait-for","ShelfOpen"+str(empty_shelf),"-t","10000");ui("invoke","ShelfOpen"+str(empty_shelf))
            ui("wait-for","TxtEmpty","--value","この棚には作品がありません。作品の詳細で所属する棚を選択できます。","-t","10000");shot("empty-shelf");check("empty shelf context guidance",True)
            check("generated sources unchanged",before==sources());report["pass"]=True
        elif args.shelf_management:
            from ui_shelf_management_audit import audit
            audit(ui,tree,shot,check,cat,first["id"],a,b)
            check("generated sources unchanged",before==sources());report["pass"]=True
        elif args.compact_toolbar:
            if args.toolbar_wrap_only:
                subprocess.run(['pwsh','-NoProfile','-File',str(REPO/'tools/inspect_frontend_modules.ps1'),'-OwnedPid',str(proc.pid),'-Executable',str(front/'Aredoko.WinUI.exe'),'-Output',str(target/'frontend-modules.json')],check=True,timeout=15,capture_output=True,text=True)
                report['frontend_modules_report']='frontend-modules.json'
            from ui_compact_toolbar_audit import audit
            audit(ui,tree,shot,report,check,cat,first['id'],input_guard=lambda:user.GetForegroundWindow()==int(hwnd),uia_only=args.uia_only,resize=resize,wrap_only=args.toolbar_wrap_only)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.bulk_favorite_patch:
            from ui_favorite_patch_audit import audit_bulk
            audit_bulk(ui,tree,shot,report,check,handler,cat,input_guard=lambda:user.GetForegroundWindow()==int(hwnd))
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.favorite_patch:
            from ui_favorite_patch_audit import audit
            audit(ui,tree,shot,report,check,handler,cat,first['id'])
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.setup_return:
            from ui_setup_return_audit import audit
            audit(ui,tree,shot,report,check,handler,target,profiles=profiles,recovery=args.setup_recovery,skip_download=args.setup_skip_download)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.setup_plan:
            from ui_setup_plan_audit import audit
            audit(ui,tree,shot,report,check,handler,target)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.viewer_choice:
            from ui_viewer_choice_audit import audit
            removed=audit(ui,cli,tree,shot,report,check,cat,media,target,proc.pid,hwnd,input_guard=lambda:user.GetForegroundWindow()==int(hwnd),uia_only=args.uia_only)
            check('generated sources match the declared scope',{key:value for key,value in before.items() if key!=removed}==sources())
            report['pass']=True
        elif args.folder_settings_layout:
            from ui_folder_settings_audit import audit
            report['folder_settings_audit_sha256']=hashlib.sha256((REPO/'tools/ui_folder_settings_audit.py').read_bytes()).hexdigest()
            if args.agent_desktop_only:
                ui('invoke','BtnRoots');ui('wait-for','LibraryHeading','--value','登録フォルダ','-t','10000')
                ui('wait-for','FolderList','-p','IsOffscreen','--value','False','-t','10000')
                ui('invoke','ConfigFolder'+str(report['folder_settings_fixture']['roots'][0]));ui('wait-for','ScanRoot','-t','10000')
            else:audit(ui,tree,shot,report,check,cat,remaining=args.folder_settings_remaining)
            if args.agent_desktop:
                from agent_desktop_probe import audit as audit_agent_desktop
                audit_agent_desktop(args.agent_desktop,hwnd,proc.pid,ui,target,report,check)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.favorite_root_actions:
            from ui_favorite_root_actions_audit import audit
            report['favorite_root_audit_sha256']=hashlib.sha256((REPO/'tools/ui_favorite_root_actions_audit.py').read_bytes()).hexdigest()
            audit(ui,tree,shot,report,check,cat,remaining=args.favorite_root_removal_only)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.shelf_picker_filter:
            from ui_shelf_filter_audit import audit
            report['shelf_audit_sha256']=hashlib.sha256((REPO/'tools/ui_shelf_filter_audit.py').read_bytes()).hexdigest()
            audit(ui,tree,shot,report,check,cat,remaining=args.shelf_picker_remaining)
            if args.shelf_picker_remaining:
                from ui_acquisition_guidance_audit import audit as audit_guidance
                report['acquisition_guidance_sha256']=hashlib.sha256((REPO/'tools/ui_acquisition_guidance_audit.py').read_bytes()).hexdigest()
                audit_guidance(ui,tree,shot,report,check,handler)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.empty_ai_recovery:
            from ui_empty_ai_recovery_audit import audit
            report['recovery_audit_sha256']=hashlib.sha256((REPO/'tools/ui_empty_ai_recovery_audit.py').read_bytes()).hexdigest()
            audit(ui,tree,shot,report,check,handler)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.empty_guidance_only:
            from ui_empty_guidance_audit import audit
            report['empty_audit_sha256']=hashlib.sha256((REPO/'tools/ui_empty_guidance_audit.py').read_bytes()).hexdigest()
            audit(ui,tree,shot,report,check)
            if args.setup_choice_layout:
                from ui_setup_plan_audit import audit as audit_setup
                report['setup_audit_sha256']=hashlib.sha256((REPO/'tools/ui_setup_plan_audit.py').read_bytes()).hexdigest()
                audit_setup(ui,tree,shot,report,check,handler,target,check_layout=True)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.footer_actions_only:
            from ui_footer_actions_audit import audit
            report['footer_audit_sha256']=hashlib.sha256((REPO/'tools/ui_footer_actions_audit.py').read_bytes()).hexdigest()
            audit(ui,tree,shot,report,check,cat)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.folder_toolbar_only:
            from ui_settings_layout_audit import audit_folder_toolbar
            report['folder_audit_sha256']=hashlib.sha256((REPO/'tools/ui_settings_layout_audit.py').read_bytes()).hexdigest()
            audit_folder_toolbar(ui,shot,report,check)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.diagnostic_footer_only:
            from ui_settings_layout_audit import audit_diagnostics
            report['diagnostics_audit_sha256']=hashlib.sha256((REPO/'tools/ui_settings_layout_audit.py').read_bytes()).hexdigest()
            audit_diagnostics(ui,shot,report,check)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.guide_layout_only:
            from ui_settings_layout_audit import audit_guide
            report['guide_audit_sha256']=hashlib.sha256((REPO/'tools/ui_settings_layout_audit.py').read_bytes()).hexdigest()
            audit_guide(ui,shot,report,check,cat,handler,target)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.settings_feedback_only:
            from ui_settings_feedback_audit import audit
            audit(ui,shot,report,check)
            if args.agent_desktop:
                from agent_desktop_probe import audit as audit_agent_desktop
                ui('invoke','BtnRoots');ui('wait-for','LibraryHeading','--value','登録フォルダ','-t','10000')
                ui('wait-for','FolderList','-p','IsOffscreen','--value','False','-t','10000')
                ui('invoke','ConfigFolder'+str(cat.registered_roots()[0]['id']));ui('wait-for','ScanRoot','-t','10000')
                audit_agent_desktop(args.agent_desktop,hwnd,proc.pid,ui,target,report,check)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.settings_layout_only:
            from ui_settings_layout_audit import audit
            report['settings_audit_sha256']=hashlib.sha256((REPO/'tools/ui_settings_layout_audit.py').read_bytes()).hexdigest()
            audit(ui,shot,report,check,target)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.detail_fields_only:
            from ui_detail_polish_audit import audit_fields
            report['fields_audit_sha256']=hashlib.sha256((REPO/'tools/ui_detail_polish_audit.py').read_bytes()).hexdigest()
            audit_fields(ui,tree,shot,report,check,cat)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.detail_polish:
            if args.caption_menu_only:from ui_card_caption_audit import audit_menu as audit
            elif args.card_captions:from ui_card_caption_audit import audit
            else:from ui_detail_polish_audit import audit
            audit(ui,tree,shot,report,check,cat)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.detail_actions:
            from ui_detail_actions_audit import audit
            audit(ui,tree,shot,check,cat,navigation_only=args.detail_navigation_only)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.viewer_boundary120:
            from ui_continuous_browse_audit import audit_boundary120
            audit_boundary120(ui,cli,tree,shot,report,check,proc.pid,hwnd,cat)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.real_fixture:
            from ui_real_library_audit import audit
            audit(ui,tree,shot,report,check,proc.pid,cat,handler.thumbnails,input_guard=lambda:user.GetForegroundWindow()==int(hwnd))
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.video_audio_content:
            from ui_video_audio_audit import audit
            audit(ui,tree,shot,report,check,cat,audio_feature,audio_gate,audio_reached,input_guard=lambda:user.GetForegroundWindow()==int(hwnd))
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.video_content:
            from ui_video_content_audit import audit
            def input_owned():
                foreground=user.GetForegroundWindow();owner=wintypes.DWORD()
                user.GetWindowThreadProcessId(foreground,ctypes.byref(owner))
                return owner.value==proc.pid
            audit(ui,tree,shot,report,check,cat,video_feature,video_gate,video_reached,input_guard=input_owned,history_only=args.video_history_only)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.audio_content:
            from ui_audio_content_audit import audit,audit_similarity
            def input_owned():
                foreground=user.GetForegroundWindow();owner=wintypes.DWORD()
                user.GetWindowThreadProcessId(foreground,ctypes.byref(owner))
                return owner.value==proc.pid
            if args.audio_similarity_only:
                audit_similarity(ui,tree,shot,report,check,cat,audio_feature,input_guard=input_owned)
            else:audit(ui,tree,shot,report,check,cat,audio_feature,audio_gate,audio_reached,input_guard=input_owned,search_only=args.audio_search_only)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.global_edge:
            from ui_global_edge_audit import audit
            audit(ui,tree,shot,report,check,proc.pid,cat,input_guard=lambda:user.GetForegroundWindow()==int(hwnd))
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.library_tail:
            from ui_continuous_browse_audit import audit_tail
            audit_tail(ui,cli,tree,shot,report,check,proc.pid,hwnd,cat)
            check('generated sources unchanged',before==sources());report['pass']=True
        elif args.continuous:
            from ui_continuous_browse_audit import audit
            audit(ui,cli,tree,shot,report,check,proc.pid,hwnd,cat)
            check('generated sources unchanged',before==sources());report['pass']=True
        else:
            ui('invoke',key,'--action','select');ui('wait-for','TxtTags','-t','5000');ui('set-value','TxtTags','p3-generated-draft')
            ui('invoke','BtnLayout');ui('wait-for','TxtTags','--value','p3-generated-draft','-t','5000');shot('grid-draft')
            ui('invoke','BtnSave');ui('wait-for','BtnSave','-p','IsEnabled','--value','False','-t','5000')
            ui('wait-for','TxtTags','-p','IsEnabled','--value','True','-t','15000')
            check('tag saved to generated catalog',cat.search(query='p3-generated-draft')['total']==1)
            ui('invoke','BtnCloseDetails');ui('scroll','ItemList','--to','bottom');time.sleep(.3);shot('grid-bottom')
            ui('invoke','BrowseActions');ui('invoke','BtnNext');ready();shot('page-two');ui('wait-for','TxtPageNumber','--value','2 / 3','-t','5000')
            ui('invoke','BrowseActions');ui('invoke','BtnPrevious');ready();ui('scroll','ItemList','--to','top');ui('wait-for',key,'-t','5000')
            check('previous page restores keyed card',True);check('generated sources unchanged',before==sources());report['pass']=True
    except Exception:
        report['error']=traceback.format_exc();print(report['error'],flush=True)
        if hwnd and proc is not None and proc.poll() is None:
            try:shot('failure')
            except Exception:report['capture_error']=traceback.format_exc()
    finally:
        if 'real_gate' in locals():real_gate.set()
        if 'audio_gate' in locals():audio_gate.set()
        if 'video_gate' in locals():video_gate.set()
        if (args.initial_loading or args.usability_u1) and "gate" in locals():gate.set()
        if proc is not None and proc.poll() is None and not hwnd:
            try:
                owned=[w for w in json.loads(cli('list-windows','-a',proc.pid,'--json')) if w.get('title')=='Aredoko — あれどこ']
                if len(owned)==1:hwnd=str(owned[0]['hwnd'])
            except Exception:report['cleanup_discovery_error']=traceback.format_exc()
        if proc is not None and proc.poll() is None and hwnd:
            try:
                visible=tree()
                if visible.get('CloseButton',{}).get('name')=='キャンセル':
                    ui('invoke','CloseButton');ui('wait-for','CloseButton','--gone','-t','5000')
            except Exception:report['dialog_cleanup_error']=traceback.format_exc()
            try:
                for child in json.loads(cli('list-windows','-a',proc.pid,'--json')):
                    if str(child.get('hwnd'))!=hwnd and 'ビューア' in child.get('title',''):
                        child_owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(child['hwnd']),ctypes.byref(child_owner))
                        if child_owner.value!=proc.pid:raise RuntimeError('Child owner changed')
                        if not user.PostMessageW(int(child['hwnd']),0x10,0,0):raise ctypes.WinError(ctypes.get_last_error())
            except Exception:report['child_cleanup_error']=traceback.format_exc()
            try:
                owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
                if owner.value!=proc.pid:raise RuntimeError('Cleanup HWND changed')
                # Only discard this flow's generated draft, never force-close.
                for _ in range(8):
                    if proc.poll() is not None:break
                    visible=tree();primary=visible.get('PrimaryButton',{})
                    modal=next((name for name in ('AISetupPlanDialog','AIEnvironmentDialog','AIDownloadDialog','AISettingsDialog','DiagnosticsDialog','SettingsDialog','GettingStartedGuideDialog') if name in visible),None)
                    if modal is not None:
                        combo=visible.get('SettingsDoubleClickViewer',{})
                        if combo.get('expandState')=='expanded':ui('invoke',combo.get('selector','SettingsDoubleClickViewer'),'--action','collapse')
                        ui('invoke','CloseButton','--action','invoke')
                        ui('wait-for',modal,'--gone','-t','5000')
                        continue
                    if primary.get('name')=='変更を破棄':
                        ui('invoke','PrimaryButton')
                        if proc.poll() is not None:break
                        try:ui('wait-for','PrimaryButton','--gone','-t','5000')
                        except RuntimeError:
                            # Window destruction can precede process-handle signaling.
                            try:proc.wait(timeout=8);break
                            except subprocess.TimeoutExpired:raise
                    user.IsWindow.argtypes=[wintypes.HWND];user.IsWindow.restype=wintypes.BOOL
                    if not user.IsWindow(int(hwnd)):
                        proc.wait(timeout=8);break
                    if not user.PostMessageW(int(hwnd),0x10,0,0):raise ctypes.WinError(ctypes.get_last_error())
                    try:proc.wait(timeout=5);break
                    except subprocess.TimeoutExpired:pass
                if proc.poll() is None:raise RuntimeError('Owned app did not close normally')
                report['graceful_exit']=proc.returncode
            except Exception:report['cleanup_error']=traceback.format_exc()
        if server:
            if thread:server.shutdown()
            server.server_close()
        if thread:thread.join(5)
        if server:
            for resource in (handler.startup_scans,handler.thumbnails,handler.results,handler.audio_content,handler.video_content,handler.animations,handler.setup_jobs,handler.download_jobs,handler.backup_jobs,handler.restore_jobs):resource.close()
        if cat:cat.close()
        report['process_still_running']=proc is not None and proc.poll() is None
        report['test_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        if report.get('source_files')!={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in tracked}:report['pass']=False;report['source_changed']=True
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['pass'] and not report.get('process_still_running') else 1
if __name__=='__main__':raise SystemExit(main())

