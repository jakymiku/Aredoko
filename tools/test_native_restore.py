"""Bounded native restore consent/restart test, generated DB/media only."""
import argparse,ctypes,hashlib,json,os,secrets,struct,subprocess,sys,threading,time,traceback
from ctypes import wintypes
from dataclasses import replace
from pathlib import Path
from urllib.request import ProxyHandler,Request,build_opener
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'app'),str(REPO/'tools')]
from production import ProductionCatalog
from storage_backup import backup,create_backup
from restore_handoff import RestoreHandoff
from restore_switch import check_pending_restore
from launch_release import run_session
from portable_frontend import ReadyProcess
from create_preview_fixture import png
from native_ui_tools import nodes


def run_format2(args):
    release=args.release.resolve()
    expected_app=(release/'bin/Aredoko.WinUI.exe').resolve()
    target=REPO/'data/ai-ui/restore-v2-native-20261024'/f'run{args.attempt:02}'
    if (os.name!='nt' or not (release.is_relative_to(REPO/'dist') or release.is_relative_to(REPO/'data/ai-ui'))
            or not (release/'Aredoko.exe').is_file() or not expected_app.is_file() or target.exists()):
        raise SystemExit('New dedicated release candidate and output directory required')
    from ai_profiles import DEFAULT_PROFILE
    from ai_settings import AIProfileSettings
    from tagger_profile import WDProfile
    from model_locations import ModelTarget

    target.mkdir(parents=True)
    local_root=target/'local';data=local_root/'Aredoko';data.mkdir(parents=True)
    media=target/'media';media.mkdir()
    (media/'generated.png').write_bytes(png(width=180,height=160,color=(50,120,170)))
    media_before={p.name:(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in media.iterdir()}

    # 1. Build Format 2 backup source with distinct active (running-v2) and pending (pending-v2) profiles
    source_lib=target/'source-lib';source_lib.mkdir()
    source_profiles=source_lib/'profiles';source_profiles.mkdir()
    running_profile=replace(DEFAULT_PROFILE,label='Restored Active V2',dimension=8,modalities=('text',),directory='generated-running-v2')
    pending_profile=replace(DEFAULT_PROFILE,label='Restored Pending V2',dimension=16,modalities=('text',),directory='generated-pending-v2')
    (source_profiles/'running.json').write_text(json.dumps(running_profile.to_dict()),encoding='utf-8')
    (source_profiles/'pending.json').write_text(json.dumps(pending_profile.to_dict()),encoding='utf-8')
    source_settings=source_lib/'ai-settings.json'
    source_settings.write_text('{"version":1,"profile":"local:running.json"}',encoding='utf-8')
    profiles_mgr=AIProfileSettings(source_lib,source_settings,profile_directory=source_profiles)
    profiles_mgr.choose('local:pending.json')

    tag_base=json.loads((REPO/'config/tagger-profiles/wd-swinv2-v3.json').read_text(encoding='utf-8'))
    tagger_a=source_lib/'a-tagger.json';tagger_a.write_text(json.dumps({**tag_base,'general_threshold':0.25}),encoding='utf-8')
    tagger_z=source_lib/'z-tagger.json';tagger_z.write_text(json.dumps({**tag_base,'general_threshold':0.65}),encoding='utf-8')
    loaded_tagger=WDProfile.from_dict(json.loads(tagger_z.read_text(encoding='utf-8')))

    src_cat=ProductionCatalog(source_lib/'catalog.sqlite');src_root=src_cat.add_root(str(media));src_cat.start_scan(src_root)
    if src_cat._worker:src_cat._worker.join(10)
    with src_cat.connect() as db:db.execute("UPDATE items SET tags='[\"restored-v2-fixture\"]'");db.commit()
    src_cat.close()

    create_backup(
        source_lib/'catalog.sqlite',
        target/'bundle.zip',
        settings=source_settings,
        profiles=source_profiles,
        tagger_profiles=(tagger_a,tagger_z),
        active_tagger_profile='z-tagger.json',
        active_profile_data=profiles_mgr.active_definition,
        active_tagger_data=loaded_tagger.document.encode('utf-8'),
        active_profile_override=False,
        include_vectors=False,
    )

    # 2. Prepare current library and local model placement preferences in LOCALAPPDATA/Aredoko
    cur_cat=ProductionCatalog(data/'catalog.sqlite');cur_root=cur_cat.add_root(str(media));cur_cat.start_scan(cur_root)
    if cur_cat._worker:cur_cat._worker.join(10)
    with cur_cat.connect() as db:db.execute("UPDATE items SET tags='[\"current-fixture\"]'");db.commit()
    cur_cat.close()

    local_models=target/'local-models';local_models.mkdir()
    local_embedding=target/'local-embedding-models';local_embedding.mkdir()
    local_tagger=target/'local-tagger-models';local_tagger.mkdir()
    local_intent=target/'local-intent-models';local_intent.mkdir()
    placed_running=target/'placed-running-v2';placed_running.mkdir()
    placed_pending=target/'placed-pending-v2';placed_pending.mkdir()
    placed_tagger=target/'placed-tagger-v2';placed_tagger.mkdir()

    expected_locations=[
        ModelTarget.for_profile('embedding',running_profile).to_dict()|{'root':str(placed_running)},
        ModelTarget.for_profile('embedding',pending_profile).to_dict()|{'root':str(placed_pending)},
        ModelTarget.for_profile('tagger',loaded_tagger).to_dict()|{'root':str(placed_tagger)},
    ]
    initial_launch_settings={
        'ui_theme':'dark',
        'models_root':str(local_models),
        'embedding_models_root':str(local_embedding),
        'tagger_models_root':str(local_tagger),
        'intent_models_root':str(local_intent),
        'model_locations':expected_locations,
    }
    (data/'launch-settings.json').write_text(json.dumps(initial_launch_settings,indent=2),encoding='utf-8')

    report={
        'pass':False,'format':2,'checks':[],'screenshots':[],'visual_review':'pending',
        'attempt':args.attempt,'release':str(release),
        'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'owned_bootstrap_pids':[],'owned_app_pids':[],'exits':[],
    }
    files=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','--','src','app'],cwd=REPO,text=True).splitlines()
    report['source_files']={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in files}
    report['frontend_sha256']=hashlib.sha256((release/'bin/Aredoko.WinUI.dll').read_bytes()).hexdigest()

    env={**os.environ,'LOCALAPPDATA':str(local_root),'APPDATA':str(local_root),'WINAPP_UI_WORKFLOW_ID':'aredoko-native-restore-v2-20261024'}
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    WNDENUMPROC=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    user.EnumWindows.argtypes=[WNDENUMPROC,wintypes.LPARAM]

    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype=wintypes.BOOL
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype=wintypes.BOOL
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.CloseHandle.restype=wintypes.BOOL

    def cli(*parts):
        result=subprocess.run(['winapp','ui',*map(str,parts)],cwd=REPO,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=25)
        with (target/'commands.log').open('a',encoding='utf-8') as log:
            log.write(json.dumps({'args':parts,'code':result.returncode,'out':result.stdout,'err':result.stderr},ensure_ascii=False,default=str)+'\n')
        if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        return result.stdout

    def wait(name,predicate,timeout=25):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if predicate():report['checks'].append(name);return
            time.sleep(.1)
        raise AssertionError(name)

    seen_pids=set();seen_instances=set()
    hwnd=None;pid=None;proc_handle=None;picker_hwnd=None;bootstrap=None
    opener=build_opener(ProxyHandler({}))

    def session_info():
        try:
            with opener.open('http://127.0.0.1:8769/api/session',timeout=1.5) as response:
                return json.load(response)
        except Exception:
            return None

    def request(path,body=None):
        info=session_info()
        if not info or 'token' not in info:raise RuntimeError('Backend session unavailable')
        req=Request('http://127.0.0.1:8769'+path,data=None if body is None else json.dumps(body).encode(),
                    headers={'X-Aredoko-Token':info['token'],'Origin':'http://127.0.0.1:8769','Content-Type':'application/json'})
        with opener.open(req,timeout=4) as response:return json.load(response)

    def candidate_app_pids(include_seen=False):
        pids=set()
        def callback(w,lparam):
            owner=wintypes.DWORD()
            user.GetWindowThreadProcessId(w,ctypes.byref(owner))
            if owner.value and (include_seen or owner.value not in seen_pids):pids.add(owner.value)
            return True
        user.EnumWindows(WNDENUMPROC(callback),0)
        matches=[]
        for cand_pid in sorted(pids):
            h=kernel.OpenProcess(0x101000,False,cand_pid)
            if not h:continue
            try:
                size=wintypes.DWORD(4096);buf=ctypes.create_unicode_buffer(4096)
                code=wintypes.DWORD()
                if (kernel.QueryFullProcessImageNameW(h,0,buf,ctypes.byref(size))
                        and os.path.normcase(str(Path(buf.value).resolve()))==os.path.normcase(str(expected_app))
                        and kernel.GetExitCodeProcess(h,ctypes.byref(code)) and code.value==259):
                    matches.append((cand_pid,h));h=None
            finally:
                if h:kernel.CloseHandle(h)
        return matches

    def attach_phase(phase):
        nonlocal hwnd,pid,proc_handle
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            if bootstrap is not None and bootstrap.poll() is not None:
                raise RuntimeError(f'Owned launcher exited early during phase {phase} with code {bootstrap.returncode}')
            matches=candidate_app_pids()
            for cand_pid,h in matches:
                try:
                    windows=json.loads(cli('list-windows','-a',cand_pid,'--json'))
                    main_wins=[w for w in windows if w.get('title') and w['title']!='PopupHost']
                    info=session_info()
                    if len(main_wins)==1 and isinstance(info,dict) and info.get('instance_id') not in seen_instances:
                        pid=cand_pid;proc_handle=h;hwnd=str(main_wins[0]['hwnd'])
                        seen_pids.add(cand_pid);seen_instances.add(info['instance_id'])
                        report['owned_app_pids'].append(cand_pid)
                        report['checks'].append(f'phase {phase} ready (pid={cand_pid})')
                        for other_pid,other_h in matches:
                            if other_pid!=cand_pid:kernel.CloseHandle(other_h)
                        return
                except Exception:
                    pass
                kernel.CloseHandle(h)
            time.sleep(.2)
        raise AssertionError(f'Timed out waiting for phase {phase} owned window')

    def wait_app_exit(phase):
        nonlocal proc_handle,hwnd,pid
        if not proc_handle:return
        wait_res=kernel.WaitForSingleObject(proc_handle,20000)
        code=wintypes.DWORD()
        ok=kernel.GetExitCodeProcess(proc_handle,ctypes.byref(code))
        kernel.CloseHandle(proc_handle);proc_handle=None;hwnd=None;pid=None
        if wait_res!=0 or not ok or code.value!=0:
            raise AssertionError(f'Phase {phase} WinUI did not exit cleanly (wait={wait_res}, exit={code.value})')
        report['exits'].append({'phase':phase,'frontend_exit':int(code.value)})
        report['checks'].append(f'phase {phase} WinUI exited 0')

    def ui(*parts):
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
        if owner.value!=pid:raise RuntimeError('Owned window changed')
        return cli(*parts,'-w',hwnd)

    def shot(name):
        path=target/(name+'.png');ui('screenshot','--focus','--output',path);report['screenshots'].append(str(path))
        payload=path.read_bytes()
        if payload[:8]!=b'\x89PNG\r\n\x1a\n' or len(payload)<24 or min(struct.unpack('>II',payload[16:24]))<100:
            raise RuntimeError('Screenshot is empty or too small')
        (target/(name+'.json')).write_text(ui('inspect','--depth','22','--json'),encoding='utf-8')

    try:
        # Launch 1: Normal entrypoint Aredoko.exe (covers Phase 0 -> automatic restore handoff -> Phase 1)
        bootstrap=subprocess.Popen([str(release/'Aredoko.exe')],cwd=release,env=env)
        report['owned_bootstrap_pids'].append(bootstrap.pid)
        attach_phase(0)
        ui('wait-for','generated.png','-t','15000')
        ui('invoke','BtnSettings');ui('wait-for','BtnBackupGuide','-t','5000');ui('invoke','BtnBackupGuide')
        ui('wait-for','BackupDialog','-t','5000');ui('invoke','BackupRestoreGuide');ui('wait-for','RestoreDialog','-t','5000')
        shot('01-restore-v2-idle')

        ui('invoke','RestoreChooseZip')
        def find_picker():
            nonlocal picker_hwnd
            windows=json.loads(cli('list-windows','-a',pid,'--json'))
            matches=[w for w in windows if str(w.get('hwnd'))!=hwnd and (str(w.get('ownerHwnd'))==hwnd or w.get('className')=='#32770')]
            if len(matches)==1:picker_hwnd=str(matches[0]['hwnd']);return True
            return False
        wait('owned ZIP picker',find_picker)
        def select_zip_in_picker():
            tree=json.loads(cli('inspect','--depth','3','--json','-w',picker_hwnd));all_nodes=list(nodes(tree))
            edits=[n for n in all_nodes if not n.get('isOffscreen',True) and n.get('type')=='Edit' and (n.get('automationId') in ('1148','FileNameControlHost') or n.get('name','').startswith(('ファイル名','File name')))]
            combos=[n for n in all_nodes if not n.get('isOffscreen',True) and n.get('automationId') in ('FileNameControlHost','1148')]
            names=edits or combos
            buttons=[n for n in all_nodes if n.get('type') in ('Button','SplitButton') and n.get('isEnabled') and not n.get('isOffscreen',True) and n.get('automationId')=='1']
            if not names or len(buttons)!=1:return False
            cli('set-value',names[0].get('selector') or names[0].get('automationId'),str(target/'bundle.zip'),'-w',picker_hwnd)
            cli('invoke',buttons[0].get('selector') or buttons[0].get('automationId'),'--action','invoke','-w',picker_hwnd)
            return True
        wait('ZIP path selected in owned picker',select_zip_in_picker,timeout=10)
        picker_hwnd=None

        ui('wait-for','RestoreSource','--value',str(target/'bundle.zip'),'-t','5000');shot('02-restore-v2-selected')
        ui('wait-for','PrimaryButton','-p','IsEnabled','--value','True','-t','3000');ui('invoke','PrimaryButton')
        wait('prepared format2 bundle',lambda:request('/api/library/restore')['state']=='completed')
        ui('invoke','RestoreRefresh');ui('wait-for','RestoreConsent','-t','5000')
        ui('wait-for','PrimaryButton','-p','IsEnabled','--value','False','-t','3000');shot('03-restore-v2-prepared')
        ui('invoke','RestoreConsent');ui('wait-for','PrimaryButton','-p','IsEnabled','--value','True','-t','3000')
        ui('invoke','PrimaryButton')

        # Phase 0 exits and same Aredoko.exe owned launcher automatically restarts into Phase 1
        wait_app_exit(0)
        attach_phase(1)
        ui('wait-for','BtnSettings','-t','10000')
        wait('ready committed restore switch and cleared pending sentinel',lambda:not (data/'restore-pending.json').exists())
        shot('04-restore-v2-phase1-relaunched')

        # Verify Phase 1 uses restored active profile ('Restored Active V2') transiently while releasing ai_profile on disk
        prof_state1=request('/api/library/ai/profiles')
        if prof_state1.get('active')!='restored' or not prof_state1.get('restored_active') or prof_state1.get('command_line_override') or prof_state1.get('selected')!='local:pending.json' or not prof_state1.get('restart_required'):
            raise AssertionError(f'Unexpected Phase 1 AI profile state: {prof_state1}')
        setup_state1=request('/api/library/ai/setup')
        if (setup_state1.get('models_root')!=str(placed_running)
                or setup_state1.get('model_locations')!=expected_locations
                or setup_state1.get('model_roots')!={'embedding':str(local_embedding),'tagger':str(local_tagger),'intent':str(local_intent)}):
            raise AssertionError(f'Unexpected Phase 1 AI setup state: {setup_state1}')
        disk_settings1=json.loads((data/'launch-settings.json').read_text(encoding='utf-8'))
        if 'ai_profile' in disk_settings1:
            raise AssertionError('Transient ai_profile was not released from launch-settings.json after ready')
        if disk_settings1.get('model_locations')!=expected_locations:
            raise AssertionError('Local model_locations were not preserved across restore')
        if json.loads(Path(disk_settings1['tagger_profile']).read_text(encoding='utf-8')).get('general_threshold')!=0.65:
            raise AssertionError('Active tagger profile snapshot was not restored')
        report['checks'].extend([
            'phase 1 started with restored active profile and resolved its model placement',
            'phase 1 ready released transient ai_profile while preserving model_locations and role roots',
            'phase 1 restored active tagger profile definition',
        ])

        ui('invoke','BtnSettings');ui('wait-for','SettingsDialog','-t','5000');ui('invoke','BtnAIIndex')
        ui('wait-for','AIEnvironmentOpen','-t','5000');shot('05-restore-v2-phase1-ai-settings')
        ui('invoke','CloseButton');ui('wait-for','AIEnvironmentOpen','--gone','-t','5000')
        user.PostMessageW(int(hwnd),0x10,0,0)
        wait_app_exit(1)
        boot1_code=bootstrap.wait(timeout=20);bootstrap=None
        if boot1_code!=0:raise AssertionError(f'First Aredoko.exe exited with {boot1_code}')
        report['exits'].append({'bootstrap':1,'exit':boot1_code})
        report['checks'].append('first owned Aredoko.exe launcher exited 0')

        # Launch 2: Next normal restart via Aredoko.exe -> verifies pending profile ('local:pending.json') is now active
        bootstrap=subprocess.Popen([str(release/'Aredoko.exe')],cwd=release,env=env)
        report['owned_bootstrap_pids'].append(bootstrap.pid)
        attach_phase(2)
        ui('wait-for','BtnSettings','-t','10000')
        prof_state2=request('/api/library/ai/profiles')
        pending_candidates=[p for p in prof_state2.get('profiles',[]) if p.get('id')=='local:pending.json']
        if (prof_state2.get('active')!='local:pending.json' or prof_state2.get('restored_active')
                or prof_state2.get('command_line_override') or prof_state2.get('selected')!='local:pending.json'
                or prof_state2.get('restart_required') or len(pending_candidates)!=1
                or pending_candidates[0].get('label')!='Restored Pending V2' or pending_candidates[0].get('dimension')!=16):
            raise AssertionError(f'Unexpected Phase 2 AI profile state: {prof_state2}')
        setup_state2=request('/api/library/ai/setup')
        if (setup_state2.get('models_root')!=str(placed_pending)
                or setup_state2.get('model_locations')!=expected_locations
                or setup_state2.get('model_roots')!={'embedding':str(local_embedding),'tagger':str(local_tagger),'intent':str(local_intent)}):
            raise AssertionError(f'Unexpected Phase 2 AI setup state: {setup_state2}')
        report['checks'].extend([
            'phase 2 normal restart activated pending profile (local:pending.json)',
            'phase 2 resolved model placement for pending profile and retained all model_locations',
        ])

        ui('invoke','BtnSettings');ui('wait-for','SettingsDialog','-t','5000');ui('invoke','BtnAIIndex')
        ui('wait-for','AIEnvironmentOpen','-t','5000');shot('06-restore-v2-phase2-pending-active')
        ui('invoke','CloseButton');ui('wait-for','AIEnvironmentOpen','--gone','-t','5000')
        user.PostMessageW(int(hwnd),0x10,0,0)
        wait_app_exit(2)
        boot2_code=bootstrap.wait(timeout=20);bootstrap=None
        if boot2_code!=0:raise AssertionError(f'Second Aredoko.exe exited with {boot2_code}')
        report['exits'].append({'bootstrap':2,'exit':boot2_code})
        report['checks'].append('second owned Aredoko.exe launcher exited 0')

        # Verify restored catalog and untouched original catalog
        restored=ProductionCatalog(disk_settings1['database'])
        try:
            with restored.connect() as db:tags=db.execute('SELECT tags FROM items LIMIT 1').fetchone()[0]
        finally:restored.close()
        if 'restored-v2-fixture' not in tags:raise AssertionError('Restored v2 tags missing')
        old=ProductionCatalog(data/'catalog.sqlite')
        try:
            with old.connect() as db:old_tags=db.execute('SELECT tags FROM items LIMIT 1').fetchone()[0]
        finally:old.close()
        if 'current-fixture' not in old_tags:raise AssertionError('Old library changed')
        report['checks'].extend(['restored v2 catalog verified','old catalog retained untouched'])
        report['pass']=True
    except Exception:
        report['error']=traceback.format_exc()
        if hwnd and proc_handle:
            try:shot('failure')
            except Exception:report['capture_error']=traceback.format_exc()
    finally:
        try:
            if picker_hwnd:user.PostMessageW(int(picker_hwnd),0x10,0,0)
            if hwnd:
                try:
                    ui('invoke','CloseButton')
                    time.sleep(.3)
                except Exception:pass
                user.PostMessageW(int(hwnd),0x10,0,0)
            if proc_handle:
                kernel.WaitForSingleObject(proc_handle,10000)
                kernel.CloseHandle(proc_handle);proc_handle=None
            if bootstrap is not None and bootstrap.poll() is None:
                bootstrap.wait(timeout=15)
        except Exception:
            report['cleanup_error']=traceback.format_exc()
        remaining=candidate_app_pids(include_seen=True)
        for _,rem_h in remaining:kernel.CloseHandle(rem_h)
        report['source_files_unchanged']=report['source_files']=={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in files}
        report['process_still_running']=bool(remaining) or (bootstrap is not None and bootstrap.poll() is None)
        report['owner_finished']=not report['process_still_running']
        report['source_media_unchanged']=media_before=={p.name:(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in media.iterdir()}
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['pass'] and report['owner_finished'] and not report['process_still_running'] and report['source_media_unchanged'] and report['source_files_unchanged'] else 1


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--frontend',type=Path)
    parser.add_argument('--release',type=Path,help='Portable release directory containing Aredoko.exe for --format2')
    parser.add_argument('--format2',action='store_true',help='Verify Format 2 active/pending restore and model_locations across normal launcher restarts')
    parser.add_argument('--attempt',type=int,choices=(1,2,3,4,5),required=True)
    args=parser.parse_args()
    if args.format2:
        if args.release is None:parser.error('--format2 requires --release')
        return run_format2(args)
    if args.frontend is None:parser.error('--frontend is required')
    front=args.frontend.resolve();target=REPO/'data/ai-ui/restore-native-20261024'/f'run{args.attempt:02}'
    if os.name!='nt' or not front.is_relative_to(REPO/'data/ai-ui') or not (front/'Aredoko.WinUI.exe').is_file() or target.exists():parser.error('New dedicated candidate/output required')
    target.mkdir(parents=True);data=target/'user';data.mkdir();media=target/'media';media.mkdir()
    (media/'generated.png').write_bytes(png(width=180,height=160,color=(50,120,170)))
    media_before={p.name:(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in media.iterdir()}
    cat=ProductionCatalog(data/'catalog.sqlite');root=cat.add_root(str(media));cat.start_scan(root)
    if cat._worker:cat._worker.join(10)
    with cat.connect() as db:db.execute("UPDATE items SET tags='[\"restored-fixture\"]'");db.commit()
    cat.close();backup(data/'catalog.sqlite',target/'bundle',include_vectors=False)
    if args.attempt==3:create_backup(data/'catalog.sqlite',target/'bundle.zip',include_vectors=False)
    cat=ProductionCatalog(data/'catalog.sqlite')
    with cat.connect() as db:db.execute("UPDATE items SET tags='[\"current-fixture\"]'");db.commit()
    cat.close()
    report={'pass':False,'checks':[],'screenshots':[],'visual_review':'pending','attempt':args.attempt,'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()}
    files=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','--','src','app'],cwd=REPO,text=True).splitlines()
    report['source_files']={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in files}
    report['frontend_sha256']=hashlib.sha256((front/'Aredoko.WinUI.dll').read_bytes()).hexdigest()
    state={};lock=threading.Lock();done=threading.Event();env={**os.environ,'LOCALAPPDATA':str(target/'local'),'WINAPP_UI_WORKFLOW_ID':'aredoko-native-restore-20261024'}
    user=ctypes.WinDLL('user32',use_last_error=True);user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM];user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    def owned_loop():
        try:
            for phase in range(2):
                current=json.loads((data/'launch-settings.json').read_text()) if (data/'launch-settings.json').exists() else {}
                catalog=Path(current.get('database',str(data/'catalog.sqlite')));instance=secrets.token_hex(16);logs=target/f'session{phase}';logs.mkdir()
                handoff=RestoreHandoff(logs,instance,catalog)
                command=[sys.executable,'-B',str(REPO/'app/production_server.py'),'--db',str(catalog),'--instance-id',instance,'--exit-on-stdin-close','--restore-session-dir',str(logs),'--ai-python',str(target/'absent-python'),'--models-root',str(target/'absent-models'),'--ai-settings',str(target/'ai-settings.json'),'--runtime-preferences',str(data/'launch-settings.json')]
                def factory(arguments,log):
                    nonce=secrets.token_hex(16);child_env={**env,'AREDOKO_STARTUP_NONCE':nonce,'AREDOKO_STARTUP_INSTANCE':instance}
                    process=subprocess.Popen([str(front/'Aredoko.WinUI.exe'),*arguments],cwd=front,env=child_env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=log,bufsize=0)
                    owned=ReadyProcess(process,nonce,instance,log)
                    with lock:state.update(phase=phase,process=process,owned=owned)
                    return owned
                result=run_session(command,['--ui-theme','dark','--viewer-settings',str(data/'viewer-settings.json')],port=8769,instance=instance,logs=logs,cwd=REPO,env=env,app_factory=factory,require_ready=True,data=data,restore_handoff=handoff)
                report.setdefault('exits',[]).append({'phase':phase,'frontend':state['process'].returncode})
                if phase==0:
                    if not result or not result.get('restart'):raise AssertionError('No restore handoff')
                    check_pending_restore(data)
                else:
                    if result is not None:raise AssertionError('Unexpected second handoff')
        except Exception:report['owner_error']=traceback.format_exc()
        finally:done.set()
    def cli(*parts):
        result=subprocess.run(['winapp','ui',*map(str,parts)],cwd=REPO,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=25)
        with (target/'commands.log').open('a',encoding='utf-8') as log:log.write(json.dumps({'args':parts,'code':result.returncode,'out':result.stdout,'err':result.stderr},ensure_ascii=False,default=str)+'\n')
        if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        return result.stdout
    def wait(name,predicate,timeout=20):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if predicate():report['checks'].append(name);return
            if done.is_set():raise RuntimeError(report.get('owner_error','Owner stopped early'))
            time.sleep(.1)
        raise AssertionError(name)
    hwnd=None;pid=None;picker_hwnd=None
    def select(phase):
        nonlocal hwnd,pid
        wait('phase ready '+str(phase),lambda:state.get('phase')==phase and state.get('owned') is not None and state['owned'].ready.is_set())
        pid=state['process'].pid
        windows=json.loads(cli('list-windows','-a',pid,'--json'));windows=[w for w in windows if w.get('title') and w['title']!='PopupHost']
        if len(windows)!=1:raise AssertionError('Expected one owned window')
        hwnd=str(windows[0]['hwnd'])
    def ui(*parts):
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
        if owner.value!=pid:raise RuntimeError('Owned window changed')
        return cli(*parts,'-w',hwnd)
    def shot(name):
        path=target/(name+'.png');ui('screenshot','--output',path);report['screenshots'].append(str(path));(target/(name+'.json')).write_text(ui('inspect','--depth','22','--json'),encoding='utf-8')
    opener=build_opener(ProxyHandler({}))
    def request(path,body=None):
        with opener.open('http://127.0.0.1:8769/api/session',timeout=2) as response:token=json.load(response)['token']
        req=Request('http://127.0.0.1:8769'+path,data=None if body is None else json.dumps(body).encode(),headers={'X-Aredoko-Token':token,'Origin':'http://127.0.0.1:8769','Content-Type':'application/json'})
        with opener.open(req,timeout=3) as response:return json.load(response)
    worker=threading.Thread(target=owned_loop,daemon=True);worker.start()
    try:
        select(0)
        ui('invoke','BtnSettings');ui('wait-for','BtnBackupGuide','-t','5000');ui('invoke','BtnBackupGuide');ui('wait-for','BackupDialog','-t','5000');ui('invoke','BackupRestoreGuide');ui('wait-for','RestoreDialog','-t','5000');shot('restore-idle')
        if args.attempt==3:
            ui('invoke','RestoreChooseZip')
            def find_picker():
                nonlocal picker_hwnd
                windows=json.loads(cli('list-windows','-a',pid,'--json'))
                matches=[w for w in windows if str(w.get('hwnd'))!=hwnd and (str(w.get('ownerHwnd'))==hwnd or w.get('className')=='#32770')]
                if len(matches)==1:picker_hwnd=str(matches[0]['hwnd']);return True
                return False
            wait('owned ZIP picker',find_picker)
            tree=json.loads(cli('inspect','--depth','20','--json','-w',picker_hwnd));all_nodes=list(nodes(tree))
            names=[n for n in all_nodes if n.get('automationId')=='FileNameControlHost' and not n.get('isOffscreen',True)]
            if len(names)!=1:raise AssertionError('File name control not found in actual picker tree')
            cli('set-value',names[0].get('selector','FileNameControlHost'),str(target/'bundle.zip'),'-w',picker_hwnd)
            buttons=[n for n in all_nodes if n.get('type')=='Button' and n.get('isEnabled') and not n.get('isOffscreen',True) and (n.get('automationId')=='1' or n.get('name','').startswith(('開く','Open')))]
            if len(buttons)!=1:raise AssertionError('Open button not uniquely identified in actual picker tree')
            cli('invoke',buttons[0]['selector'],'-w',picker_hwnd);picker_hwnd=None
            ui('wait-for','RestoreSource','--value',str(target/'bundle.zip'),'-t','5000');shot('restore-selected')
            ui('wait-for','PrimaryButton','-p','IsEnabled','--value','True','-t','3000');ui('invoke','PrimaryButton')
            report['checks'].append('native ZIP picker and preparation start')
        else:
            # Earlier scopes start through API; not claimed as native picker coverage.
            request('/api/library/restore/start',{'consent':True,'source':str(target/'bundle'),'without_vectors':True})
        wait('prepared owned bundle',lambda:request('/api/library/restore')['state']=='completed')
        ui('invoke','RestoreRefresh');ui('wait-for','RestoreConsent','-t','5000')
        if args.attempt==2:
            ui('wait-for','RestoreSource','--value',str(target/'bundle'),'-t','5000')
            ui('invoke','CloseButton');ui('wait-for','RestoreDialog','--gone','-t','5000')
            ui('invoke','BtnSettings');ui('wait-for','BtnBackupGuide','-t','5000');ui('invoke','BtnBackupGuide');ui('wait-for','BackupDialog','-t','5000');ui('invoke','BackupRestoreGuide');ui('wait-for','RestoreDialog','-t','5000')
            ui('wait-for','RestoreSource','--value',str(target/'bundle'),'-t','5000');shot('restore-reattached')
            ui('invoke','SecondaryButton');ui('wait-for','RestoreStatus','--value','バックアップを選んで復元の準備を始めてください。','-t','5000');shot('restore-discarded')
            request('/api/library/restore/start',{'consent':True,'source':str(target/'bundle'),'without_vectors':True})
            wait('prepared replacement bundle',lambda:request('/api/library/restore')['state']=='completed')
            ui('invoke','RestoreRefresh');ui('wait-for','RestoreConsent','-t','5000')
            report['checks'].extend(['native reattach preserves selected source','native discard permits replacement'])
        ui('wait-for','PrimaryButton','-p','IsEnabled','--value','False','-t','3000');shot('restore-prepared')
        ui('invoke','RestoreConsent');ui('wait-for','PrimaryButton','-p','IsEnabled','--value','True','-t','3000');ui('invoke','PrimaryButton')
        select(1);ui('wait-for','BtnSettings','-t','6000');shot('restore-relaunched')
        current=json.loads((data/'launch-settings.json').read_text());restored=ProductionCatalog(current['database'])
        try:
            with restored.connect() as db:tags=db.execute('SELECT tags FROM items LIMIT 1').fetchone()[0]
        finally:restored.close()
        if 'restored-fixture' not in tags:raise AssertionError('Restored tags missing')
        if (data/'restore-pending.json').exists():raise AssertionError('Ready did not confirm restore')
        old=ProductionCatalog(data/'catalog.sqlite')
        try:
            with old.connect() as db:tags=db.execute('SELECT tags FROM items LIMIT 1').fetchone()[0]
        finally:old.close()
        if 'current-fixture' not in tags:raise AssertionError('Old library changed')
        report['checks'].extend(['native consent gated restart','new frontend ready confirmed restore','old catalog retained'])
        report['pass']=True
    except Exception:
        report['error']=traceback.format_exc()
        if hwnd and state.get('process') and state['process'].poll() is None:
            try:shot('failure')
            except Exception:report['capture_error']=traceback.format_exc()
    finally:
        if state.get('process') and state['process'].poll() is None:
            try:
                if picker_hwnd:user.PostMessageW(int(picker_hwnd),0x10,0,0)
                if hwnd:
                    # Only owned generated dialogs; no forced process exit.
                    try:
                        ui('invoke','CloseButton')
                        ui('wait-for','RestoreDialog','--gone','-t','5000')
                        ui('wait-for','BackupDialog','--gone','-t','5000')
                    except Exception:pass
                    user.PostMessageW(int(hwnd),0x10,0,0)
                worker.join(18)
            except Exception:report['cleanup_error']=traceback.format_exc()
        report['source_files_unchanged']=report['source_files']=={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in files}
        report['process_still_running']=state.get('process') is not None and state['process'].poll() is None
        report['owner_finished']=done.is_set()
        report['source_media_unchanged']=media_before=={p.name:(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in media.iterdir()}
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['pass'] and report['owner_finished'] and not report.get('owner_error') and not report['process_still_running'] and report['source_media_unchanged'] and report['source_files_unchanged'] else 1
if __name__=='__main__':raise SystemExit(main())
