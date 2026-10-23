"""One bounded native shelf workflow, generated media/catalog only; no installed app changes."""
import argparse,ctypes,hashlib,json,os,secrets,subprocess,sys,threading,time,traceback
from ctypes import wintypes
from http.server import ThreadingHTTPServer
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'app'),str(REPO/'tools')]
from production import ProductionCatalog
from production_server import production_handler,DisabledAI
from ai_settings import AIProfileSettings
from wd_tagger import DisabledTagger
from create_preview_fixture import png
from native_ui_tools import nodes

def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace');sys.stderr.reconfigure(encoding='utf-8',errors='replace')
    parser=argparse.ArgumentParser();parser.add_argument('--frontend',type=Path,required=True);parser.add_argument('--attempt',type=int,choices=(1,2,3),required=True);args=parser.parse_args()
    front=args.frontend.resolve();base=REPO/'data/ai-ui/p4-shelves-20261023';target=base/f'run{args.attempt:02}'
    if os.name!='nt' or not front.is_relative_to(REPO/'data/ai-ui') or not (front/'Aredoko.WinUI.exe').is_file() or target.exists():parser.error('New bounded output and dedicated frontend required')
    target.mkdir(parents=True);report={'pass':False,'checks':[],'screenshots':[],'target':'local','visual_review':'pending','source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()}
    report['frontend_sha256']=hashlib.sha256((front/'Aredoko.WinUI.dll').read_bytes()).hexdigest()
    report['diff_sha256']=hashlib.sha256(subprocess.check_output(['git','diff','--','src','app'],cwd=REPO)).hexdigest()
    env={**os.environ,'WINAPP_UI_WORKFLOW_ID':'aredoko-p4-shelves-20261023'}
    user=ctypes.WinDLL('user32',use_last_error=True);user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)];user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    cat=server=thread=proc=None;hwnd=None
    def cli(*arguments):
        result=subprocess.run(['winapp','ui',*map(str,arguments)],cwd=REPO,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
        with (target/'commands.log').open('a',encoding='utf-8') as log:log.write(json.dumps({'args':list(map(str,arguments)),'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr},ensure_ascii=False)+'\n')
        if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        return result.stdout
    def ui(*arguments):
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
        if owner.value!=proc.pid:raise RuntimeError('Owned HWND changed')
        return cli(*arguments,'-w',hwnd)
    def check(name,value):
        report['checks'].append({'name':name,'pass':bool(value)});print(name,bool(value),flush=True)
        if not value:raise AssertionError(name)
    def wait(name,predicate):
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            if predicate():check(name,True);return
            time.sleep(.1)
        check(name,False)
    def shot(name):
        path=target/(name+'.png');ui('screenshot','--output',path);report['screenshots'].append(str(path));(target/(name+'.json')).write_text(ui('inspect','--depth','18','--json'),encoding='utf-8')
    def sources():return {p.name:[hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns] for p in media.iterdir()}
    try:
        media=target/'media';media.mkdir()
        for number in range(8):(media/f'generated-{number:02}.png').write_bytes(png(width=160,height=180,color=(30+number*20,120,170)))
        before=sources();cat=ProductionCatalog(target/'catalog.sqlite');root=cat.add_root(str(media));cat.start_scan(root)
        if cat._worker:cat._worker.join(12)
        first=cat.search()['items'][0]['id'];a=cat.change_shelf('create',name='素材')['id'];b=cat.change_shelf('create',name='資料')['id'];cat.change_shelf('create',name='空の棚')
        cat.change_shelf('assign',entity='item',object_ids=[first],shelf_ids=[a])
        profiles=AIProfileSettings(REPO,target/'ai-settings.json',profile_directory=target/'profiles')
        handler=production_handler(cat,secrets.token_hex(32),ai=DisabledAI(),profiles=profiles,tagger=DisabledTagger());handler.log_message=lambda *args:None
        server=ThreadingHTTPServer(('127.0.0.1',8769),handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        with (target/'app.log').open('w',encoding='utf-8') as log:proc=subprocess.Popen([str(front/'Aredoko.WinUI.exe'),'--ui-theme','dark','--viewer-settings',str(target/'viewer-settings.json')],cwd=front,env=env,stdout=log,stderr=subprocess.STDOUT)
        report['owned_pid']=proc.pid
        for _ in range(30):
            if proc.poll() is not None:raise RuntimeError('Owned app exited: '+str(proc.returncode))
            windows=[w for w in json.loads(cli('list-windows','-a',proc.pid,'--json')) if w.get('title') and w['title']!='PopupHost']
            if len(windows)==1:hwnd=str(windows[0]['hwnd']);break
            time.sleep(.2)
        check('owned window',hwnd is not None)
        ui('wait-for','Item'+str(first),'-t','12000');ui('invoke','Item'+str(first),'--action','select')
        ui('wait-for','TxtTags','-t','5000');ui('set-value','TxtTags','generated-shelf-draft');ui('invoke','BtnChooseShelves');ui('wait-for','ChooseShelf'+str(b),'-t','5000')
        ui('click','ChooseShelf'+str(b));ui('invoke','PrimaryButton');ui('wait-for','ChooseShelfList','--gone','-t','5000')
        ui('wait-for','TxtTags','--value','generated-shelf-draft','-t','5000');ui('invoke','BtnSave')
        wait('atomic tags plus two shelves',lambda:cat.get(first)['shelf_ids']==[a,b] and cat.get(first)['tags']==['generated-shelf-draft'])
        ui('wait-for','BtnChooseShelves','-p','IsEnabled','--value','True','-t','12000');ui('invoke','NavShelf','--action','select');ui('wait-for','ShelfOpen'+str(a),'-t','10000');shot('shelf-hub')
        ui('invoke','BtnCreateShelf');ui('wait-for','TxtShelfName','-t','5000');ui('set-value','TxtShelfName','追加棚');ui('invoke','PrimaryButton')
        wait('create empty named shelf',lambda:'追加棚' in cat.shelves());created=next(r['id'] for r in cat.shelf_descriptors() if r['name']=='追加棚')
        ui('wait-for','ShelfRename'+str(created),'-t','5000');ui('invoke','ShelfRename'+str(created));ui('wait-for','TxtShelfName','-t','5000');ui('set-value','TxtShelfName','変更した棚');ui('invoke','PrimaryButton')
        wait('rename keeps shelf identity',lambda:any(r['id']==created and r['name']=='変更した棚' for r in cat.shelf_descriptors()))
        ui('wait-for','ShelfOpen'+str(a),'-t','5000');ui('invoke','ShelfOpen'+str(a));ui('wait-for','Item'+str(first),'-t','10000');ui('invoke','Item'+str(first),'--action','select');ui('wait-for','BtnChooseShelves','-t','5000');ui('invoke','BtnChooseShelves');ui('wait-for','ChooseShelf'+str(a),'-t','5000')
        ui('click','ChooseShelf'+str(a));ui('invoke','PrimaryButton');ui('wait-for','ChooseShelfList','--gone','-t','5000');ui('invoke','BtnSave')
        wait('remove only one membership',lambda:cat.get(first)['shelf_ids']==[b]);ui('wait-for','TxtCount','--value','0 件','-t','12000');shot('empty-shelf-scope')
        ui('invoke','BtnShelfList');ui('wait-for','ShelfDelete'+str(b),'-t','10000');ui('invoke','ShelfDelete'+str(b));ui('wait-for','CloseButton','-t','5000');ui('invoke','CloseButton')
        check('cancel delete retains shelf',any(r['id']==b for r in cat.shelf_descriptors()))
        ui('invoke','ShelfDelete'+str(b));ui('wait-for','PrimaryButton','-t','5000');ui('invoke','PrimaryButton')
        wait('shelf deletion preserves media row',lambda:cat.get(first)['shelf_ids']==[] and '資料' not in cat.shelves())
        check('all eight media records remain',cat.search()['total']==8);check('generated source hashes and timestamps unchanged',sources()==before)
        shot('shelf-hub-after-delete');report['pass']=True
    except Exception:
        report['error']=traceback.format_exc();print(report['error'],flush=True)
        if hwnd and proc is not None and proc.poll() is None:
            try:shot('failure')
            except Exception:report['capture_error']=traceback.format_exc()
    finally:
        if proc is not None and proc.poll() is None and hwnd:
            try:
                # Only generated test dialogs/drafts may be cancelled/discarded.
                for _ in range(2):
                    visible=list(nodes(json.loads(ui('inspect','--depth','22','--json'))))
                    buttons=[n for n in visible if n.get('automationId')=='CloseButton' and not n.get('isOffscreen',True)]
                    if not buttons:break
                    ui('invoke','CloseButton');ui('wait-for','CloseButton','--gone','-t','3000')
                owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
                if owner.value!=proc.pid:raise RuntimeError('Cleanup HWND changed')
                if not user.PostMessageW(int(hwnd),0x10,0,0):raise ctypes.WinError(ctypes.get_last_error())
                try:
                    ui('wait-for','PrimaryButton','-t','2000')
                    visible=list(nodes(json.loads(ui('inspect','--depth','22','--json'))))
                    if any(n.get('automationId')=='PrimaryButton' and n.get('name')=='変更を破棄' for n in visible):ui('invoke','PrimaryButton')
                except Exception:pass
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
