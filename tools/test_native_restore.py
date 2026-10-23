"""Bounded native restore consent/restart test, generated DB/media only."""
import argparse,ctypes,hashlib,json,os,secrets,subprocess,sys,threading,time,traceback
from ctypes import wintypes
from pathlib import Path
from urllib.request import ProxyHandler,Request,build_opener
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'app'),str(REPO/'tools')]
from production import ProductionCatalog
from storage_backup import backup
from restore_handoff import RestoreHandoff
from restore_switch import check_pending_restore
from launch_release import run_session
from portable_frontend import ReadyProcess
from create_preview_fixture import png


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--frontend',type=Path,required=True);parser.add_argument('--attempt',type=int,choices=(1,2,3),required=True);args=parser.parse_args()
    front=args.frontend.resolve();target=REPO/'data/ai-ui/restore-native-20261024'/f'run{args.attempt:02}'
    if os.name!='nt' or not front.is_relative_to(REPO/'data/ai-ui') or not (front/'Aredoko.WinUI.exe').is_file() or target.exists():parser.error('New dedicated candidate/output required')
    target.mkdir(parents=True);data=target/'user';data.mkdir();media=target/'media';media.mkdir()
    (media/'generated.png').write_bytes(png(width=180,height=160,color=(50,120,170)))
    media_before={p.name:(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in media.iterdir()}
    cat=ProductionCatalog(data/'catalog.sqlite');root=cat.add_root(str(media));cat.start_scan(root)
    if cat._worker:cat._worker.join(10)
    with cat.connect() as db:db.execute("UPDATE items SET tags='[\"restored-fixture\"]'");db.commit()
    cat.close();backup(data/'catalog.sqlite',target/'bundle',include_vectors=False)
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
    hwnd=None;pid=None
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
        # Source system pickers/native Start are intentionally not claimed here.
        value=request('/api/library/restore/start',{'consent':True,'source':str(target/'bundle'),'without_vectors':True})
        wait('prepared owned bundle',lambda:request('/api/library/restore')['state']=='completed')
        ui('invoke','RestoreRefresh');ui('wait-for','RestoreConsent','-t','5000')
        if args.attempt>=2:
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
                if hwnd:
                    # Only owned generated dialogs; no forced process exit.
                    try:ui('invoke','CloseButton')
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
