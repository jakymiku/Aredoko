"""Display-only acquisition acceptance of an explicitly selected basic ZIP.

Never starts downloads, consent, inference, installers, or a user's library.
"""
import argparse,ctypes,hashlib,json,os,socket,subprocess,sys,time,traceback
from ctypes import wintypes
from pathlib import Path
from urllib.request import build_opener,ProxyHandler,Request
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'app'),str(REPO/'tools')]
from production import ProductionCatalog
from create_preview_fixture import png
from release_runtime import verify_release
from native_ui_tools import nodes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();release=args.release.resolve();target=args.output.resolve()
    if os.name!='nt' or target.exists() or not target.is_relative_to(REPO/'data/ai-ui'):
        parser.error('New dedicated Windows output required')
    if not release.is_relative_to(REPO/'dist'):parser.error('Explicit repository candidate required')
    manifest=verify_release(release)
    if manifest.get('models_bundled') is not False or manifest.get('ai_runtime_bundled') is not False:
        parser.error('Basic ZIP only')
    with socket.socket() as probe:probe.bind(('127.0.0.1',8769))  # Never reuse someone else's server.
    target.mkdir(parents=True);local=target/'local';data=local/'Aredoko';data.mkdir(parents=True)
    media=target/'media';media.mkdir();source=media/'catalog-display-fixture.png';source.write_bytes(png())
    before=(hashlib.sha256(source.read_bytes()).hexdigest(),source.stat().st_mtime_ns)
    cat=ProductionCatalog(data/'catalog.sqlite');root=cat.add_root(str(media));cat.start_scan(root)
    if cat._worker:cat._worker.join(15)
    item=cat.search()['items'][0]['id'];cat.close()
    empty_models=target/'empty-models';empty_models.mkdir()
    settings=data/'launch-settings.json';settings.write_text(json.dumps({'database':str(data/'catalog.sqlite'),'models_root':str(empty_models),'ui_theme':'dark'}),encoding='utf-8')
    initial_settings=settings.read_bytes()
    env={**os.environ,'LOCALAPPDATA':str(local),'APPDATA':str(local),'WINAPP_UI_WORKFLOW_ID':'aredoko-model-catalog-display-20261025'}
    report={'pass':False,'checks':[],'screenshots':[],'owned_pids':[],'exits':[],
            'authorization':'2026-10-25 explicit human approval: new basic ZIP display only, one restart',
            'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'app_sha256':hashlib.sha256((release/'bin/Aredoko.WinUI.dll').read_bytes()).hexdigest()}
    user=ctypes.WinDLL('user32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    user.EnumWindows.argtypes=[callback_type,wintypes.LPARAM]
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    bootstrap=None;handle=None;pid=None;hwnd=None;token=None
    expected=os.path.normcase(str(release/'bin/Aredoko.WinUI.exe'))
    opener=build_opener(ProxyHandler({}))
    def check(name,value):
        report['checks'].append({'name':name,'pass':bool(value)});print(name,bool(value),flush=True)
        if not value:raise AssertionError(name)
    def cli(*parts):
        result=subprocess.run(['winapp',*map(str,parts)],cwd=REPO,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=35)
        with (target/'commands.log').open('a',encoding='utf-8') as log:log.write(json.dumps({'args':list(map(str,parts)),'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr},ensure_ascii=False)+'\n')
        if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        return result.stdout
    def ui(*parts):
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
        if owner.value!=pid:raise RuntimeError('Owned HWND changed')
        return cli('ui',*parts,'-w',hwnd)
    def tree():return {n['automationId']:n for n in nodes(json.loads(ui('inspect','--depth','22','--json'))) if n.get('automationId')}
    def shot(name):
        path=target/(name+'.png');ui('screenshot','--focus','--output',path)
        report['screenshots'].append(str(path));path.with_suffix('.json').write_text(json.dumps(tree(),ensure_ascii=False,indent=2),encoding='utf-8')
    def request(path):
        headers={'Origin':'http://127.0.0.1:8769'}
        if token:headers['X-Aredoko-Token']=token
        with opener.open(Request('http://127.0.0.1:8769'+path,headers=headers),timeout=5) as r:return json.load(r)
    def attach():
        nonlocal pid,hwnd,handle,token
        deadline=time.monotonic()+50
        while time.monotonic()<deadline:
            if bootstrap.poll() is not None:raise RuntimeError('Owned bootstrap exited before attach')
            candidates=set()
            def capture(w,_):
                p=wintypes.DWORD();user.GetWindowThreadProcessId(w,ctypes.byref(p))
                if p.value:candidates.add(p.value)
                return True
            user.EnumWindows(callback_type(capture),0)
            for candidate in candidates:
                h=kernel.OpenProcess(0x101000,False,candidate)
                if not h:continue
                size=wintypes.DWORD(4096);buf=ctypes.create_unicode_buffer(4096)
                try:
                    if not kernel.QueryFullProcessImageNameW(h,0,buf,ctypes.byref(size)) or os.path.normcase(buf.value)!=expected:continue
                    wins=[w for w in json.loads(cli('ui','list-windows','-a',candidate,'--json')) if w.get('title') and w['title']!='PopupHost']
                    if len(wins)!=1:continue
                    session=request('/api/session');token=session['token']
                    pid=candidate;hwnd=str(wins[0]['hwnd']);handle=h;h=None
                    report['owned_pids'].append({'bootstrap':bootstrap.pid,'frontend':pid});return
                finally:
                    if h:kernel.CloseHandle(h)
            time.sleep(.2)
        raise RuntimeError('Owned candidate did not expose its native window')
    def close_phase():
        nonlocal handle,pid,hwnd,bootstrap
        if hwnd:
            for _ in range(3):
                visible=tree();button=visible.get('CloseButton')
                if button is None or button.get('isOffscreen',True):break
                ui('invoke','CloseButton')
            owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
            if owner.value!=pid:raise RuntimeError('Owned HWND changed before close')
            if not user.PostMessageW(int(hwnd),0x10,0,0):raise ctypes.WinError(ctypes.get_last_error())
        if handle:
            wait=kernel.WaitForSingleObject(handle,20000);code=wintypes.DWORD()
            if wait!=0 or not kernel.GetExitCodeProcess(handle,ctypes.byref(code)) or code.value!=0:
                raise RuntimeError('Owned frontend did not exit normally')
            report['exits'].append({'frontend':pid,'code':code.value});kernel.CloseHandle(handle);handle=None;hwnd=pid=None
        if bootstrap:
            code=bootstrap.wait(timeout=20);report['exits'].append({'bootstrap':bootstrap.pid,'code':code})
            if code!=0:raise RuntimeError('Owned bootstrap did not exit normally')
            bootstrap=None
    try:
        for phase in range(2):
            bootstrap=subprocess.Popen([str(release/'Aredoko.exe')],cwd=release,env=env)
            attach();ui('wait-for','Item'+str(item),'-t','20000')
            catalogs=request('/api/library/ai/setup/download/catalog')
            check(f'phase {phase}: both production models visible',catalogs['download_supported'] and {x['model_target']['role'] for x in catalogs['catalogs']}=={'embedding','tagger'})
            check(f'phase {phase}: no acquisition started',request('/api/library/ai/setup/download/job')['state']=='idle')
            if phase==0:
                ui('invoke','BtnSettings');ui('wait-for','BtnAIIndex','-t','5000');ui('invoke','BtnAIIndex')
                ui('wait-for','AIEnvironmentOpen','-t','10000');ui('invoke','AIEnvironmentOpen')
                ui('wait-for','AIEnvironmentDownload','-t','10000');ui('invoke','AIEnvironmentDownload')
                ui('wait-for','AIDownloadInformation','--value','EmbeddingGemma 2','--contains','-t','10000')
                info=tree()['AIDownloadInformation']['name']
                check('model-only runtime requirement is visible','対応する実行環境が必要' in info)
                ui('wait-for','PrimaryButton','-p','IsEnabled','--value','False','-t','5000');shot('embedding-catalog')
                ui('focus','AIDownloadCatalog');ui('send-keys','home down enter','--via','send-input')
                ui('wait-for','AIDownloadInformation','--value','627aef95638667ddcaa3ac8ae625e88ea5b02f51','--contains','-t','10000')
                ui('wait-for','PrimaryButton','-p','IsEnabled','--value','False','-t','5000');shot('wd-catalog')
                check('viewing two models does not start transfer',request('/api/library/ai/setup/download/job')['state']=='idle')
            else:shot('restarted-library')
            close_phase();check(f'phase {phase}: settings unchanged',settings.read_bytes()==initial_settings)
        check('generated media unchanged',before==(hashlib.sha256(source.read_bytes()).hexdigest(),source.stat().st_mtime_ns))
        check('all owned exits zero',len(report['exits'])==4 and all(x['code']==0 for x in report['exits']))
        verify_release(release);check('complete packaged inventory unchanged',True)
        report['pass']=True
    except Exception:
        report['error']=traceback.format_exc();print(report['error'],flush=True)
        if hwnd:
            try:shot('failure')
            except Exception:report['capture_error']=traceback.format_exc()
    finally:
        try:close_phase()
        except Exception:report['cleanup_error']=traceback.format_exc();report['pass']=False
        if handle:kernel.CloseHandle(handle)
        report['launcher_still_running']=bootstrap is not None and bootstrap.poll() is None
        report['transfer_requested_by_test']=False  # No start/consent action exists in this script.
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['pass'] and not report['launcher_still_running'] else 1

if __name__=='__main__':raise SystemExit(main())
