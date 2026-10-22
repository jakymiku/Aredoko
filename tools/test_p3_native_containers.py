"""Generated-only Portable native card recycling acceptance. No model or private data."""
import argparse, ctypes, hashlib, json, os, secrets, subprocess, sys, threading, time, traceback
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
    args=parser.parse_args();target=args.output.resolve();front=args.frontend.resolve()
    if os.name!='nt' or not target.is_relative_to(REPO/'data/ai-ui') or target.exists():parser.error('New dedicated output under data/ai-ui required')
    if not front.is_relative_to(REPO/'data/ai-ui') or not (front/'Aredoko.WinUI.exe').is_file():parser.error('Dedicated published frontend required')
    target.mkdir(parents=True);report={'pass':False,'checks':[],'screenshots':[],'target':'local','visual_review':'pending','authorization':'2026-10-23 renewed overnight GUI/GPU permission','source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()}
    report['app_assembly_sha256']=hashlib.sha256((front/'Aredoko.WinUI.dll').read_bytes()).hexdigest()
    report['source_worktree_diff_sha256']=hashlib.sha256(subprocess.check_output(['git','diff','--','src'],cwd=REPO)).hexdigest()
    report['app_assembly_sha256']=hashlib.sha256((front/'Aredoko.WinUI.dll').read_bytes()).hexdigest()
    report['source_worktree_diff_sha256']=hashlib.sha256(subprocess.check_output(['git','diff','--','src'],cwd=REPO)).hexdigest()
    env={**os.environ,'WINAPP_UI_WORKFLOW_ID':'aredoko-p3-native-20261023'}
    cat=server=thread=proc=None;hwnd=None
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    def check(name,value):
        report['checks'].append({'name':name,'pass':bool(value)});print(name, bool(value),flush=True)
        if not value:raise AssertionError(name)
    def cli(*args):
        result=subprocess.run(['winapp','ui',*map(str,args)],cwd=REPO,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=35)
        with (target/'commands.log').open('a',encoding='utf-8') as log:log.write(json.dumps({'args':list(map(str,args)),'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr},ensure_ascii=False)+'\n')
        if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        return result.stdout
    def ui(*args):
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
        if owner.value!=proc.pid:raise RuntimeError('Owned HWND changed')
        return cli(*args,'-w',hwnd)
    def tree():return {n['automationId']:n for n in nodes(json.loads(ui('inspect','--depth','18','--json'))) if n.get('automationId')}
    def shot(name):
        path=target/(name+'.png');ui('screenshot','--output',path);report['screenshots'].append(str(path));path.with_suffix('.json').write_text(json.dumps(tree(),ensure_ascii=False,indent=2),encoding='utf-8')
    def ready():ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
    def sources():return {p.name:[hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns] for p in media.iterdir()}
    try:
        media=target/'media';media.mkdir()
        for i in range(145):(media/f'generated-{i:03}.png').write_bytes(png(width=120,height=160,color=(40+i%180,80,160)))
        before=sources();cat=ProductionCatalog(target/'catalog.sqlite');root=cat.add_root(str(media));cat.start_scan(root)
        if cat._worker:cat._worker.join(15)
        first=cat.search()['items'][0];check('generated catalog ready',cat.search()['total']==145)
        profiles=AIProfileSettings(REPO,target/'ai-settings.json',profile_directory=target/'profiles')
        handler=production_handler(cat,secrets.token_hex(32),ai=DisabledAI(),profiles=profiles,tagger=DisabledTagger());handler.log_message=lambda *args:None
        server=ThreadingHTTPServer(('127.0.0.1',8769),handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        with (target/'app.log').open('w',encoding='utf-8') as log:
            proc=subprocess.Popen([str(front/'Aredoko.WinUI.exe'),'--ui-theme','dark','--viewer-settings',str(target/'viewer-settings.json')],cwd=front,env=env,stdout=log,stderr=subprocess.STDOUT)
        report['owned_pid']=proc.pid
        for _ in range(30):
            if proc.poll() is not None:raise RuntimeError('Owned app exited: '+str(proc.returncode))
            windows=json.loads(cli('list-windows','-a',proc.pid,'--json'));windows=[w for w in windows if w.get('title') and w['title']!='PopupHost']
            if len(windows)==1:hwnd=str(windows[0]['hwnd']);break
            time.sleep(.2)
        check('owned native window available',hwnd is not None)
        key='Item'+str(first['id']);ready();ui('wait-for',key,'-t','10000');shot('list-initial')
        visible=tree();count=sum(k.startswith('PreviewStatus') for k in visible)
        check('panel realizes fewer cards than sixty-result page',0<count<60)
        ui('invoke',key,'--action','select');ui('wait-for','TxtTags','-t','5000');ui('set-value','TxtTags','p3-generated-draft')
        ui('invoke','BtnLayout');ui('wait-for','TxtTags','--value','p3-generated-draft','-t','5000');shot('grid-draft')
        ui('invoke','BtnSave');ui('wait-for','BtnSave','-p','IsEnabled','--value','False','-t','5000')
        ui('wait-for','TxtTags','-p','IsEnabled','--value','True','-t','15000')
        check('tag saved to generated catalog',cat.search(query='p3-generated-draft')['total']==1)
        ui('invoke','BtnCloseDetails');ui('scroll','ItemList','--to','bottom');time.sleep(.3);shot('grid-bottom')
        ui('invoke','BtnNext');ready();shot('page-two');ui('wait-for','TxtPageNumber','--value','2 / 3','-t','5000')
        ui('invoke','BtnPrevious');ready();ui('scroll','ItemList','--to','top');ui('wait-for',key,'-t','5000')
        check('previous page restores keyed card',True);check('generated sources unchanged',before==sources());report['pass']=True
    except Exception:
        report['error']=traceback.format_exc();print(report['error'],flush=True)
    finally:
        if proc is not None and proc.poll() is None and hwnd:
            try:
                owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
                if owner.value!=proc.pid:raise RuntimeError('Cleanup HWND changed')
                if not user.PostMessageW(int(hwnd),0x10,0,0):raise ctypes.WinError(ctypes.get_last_error())
                proc.wait(timeout=12);report['graceful_exit']=proc.returncode
            except Exception:report['cleanup_error']=traceback.format_exc()
        if server:server.shutdown();server.server_close()
        if thread:thread.join(5)
        if server:
            for resource in (handler.thumbnails,handler.results,handler.animations,handler.setup_jobs):resource.close()
        if cat:cat.close()
        report['process_still_running']=proc is not None and proc.poll() is None
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['pass'] and not report.get('process_still_running') else 1
if __name__=='__main__':raise SystemExit(main())

