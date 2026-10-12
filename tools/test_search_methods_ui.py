"""Native local search-method checks with generated PNGs and contract or CUDA encoders.

Default: CPU contract stub. --cuda explicitly uses existing offline project
weights; --text-only selects a fixed capability variant. These tiny fixtures
verify native integration, not retrieval quality. No downloads or private data.
"""
import argparse
import ctypes
from ctypes import wintypes
from dataclasses import replace
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import uuid

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from ai_profiles import DEFAULT_PROFILE
from ai_process import AIUnavailable
from ai_search import AISearch
from ai_settings import AIProfileSettings
from production import ProductionCatalog
from production_server import production_handler
from create_holdout_fixture import graphic
from test_index_gpu_scaling import MeasuredEncoder
from test_index_gpu_api import vector_digest


class ContractEncoder:
    available=True
    resident=False
    device='CPU-contract-only'
    profile=replace(DEFAULT_PROFILE,dimension=8)
    def __init__(self):self.calls=[];self.fail=False
    def encode(self,operation,value):
        if self.fail:raise AIUnavailable('生成テストの検索エラー')
        self.calls.append(operation)
        return [1.0]+[0.0]*7
    def close(self):pass


class NativeGPUEncoder(MeasuredEncoder):
    def __init__(self,profile):
        super().__init__();self.profile=profile;self.fail=False
    def encode(self,operation,value):
        if self.fail:raise AIUnavailable('生成テストの検索エラー')
        return super().encode(operation,value)


class RecordedAI(AISearch):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.requests=[];self.record_lock=threading.Lock()
    def search(self,query,kind='',view='all',page=0,**kwargs):
        entry={'query':query,'kind':kind,'view':view,'page':page,**kwargs}
        try:
            result=super().search(query,kind,view,page,**kwargs)
            entry['ids']=[item['id'] for item in result['items']]
            return result
        except Exception:
            entry['failed']=True
            raise
        finally:
            with self.record_lock:self.requests.append(entry)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cuda',action='store_true',help='Use existing project runtime and offline EG2 weights')
    parser.add_argument('--text-only',action='store_true',help='With --cuda, test the fixed text-only EG2 capability profile')
    args=parser.parse_args()
    if args.text_only and not args.cuda:parser.error('--text-only requires --cuda')
    target=args.output.resolve()
    if not target.is_relative_to((REPO/'data/ai-ui').resolve()):parser.error('Evidence must stay in data/ai-ui')
    if os.name!='nt':parser.error('Native Windows only')
    profile=replace(DEFAULT_PROFILE,modalities=('text',)) if args.text_only else DEFAULT_PROFILE
    if args.cuda and not ((REPO/'.venv-ai/Scripts/python.exe').is_file() and profile.model_path(REPO).is_dir()):parser.error('Existing project environment/weights required; no download')
    target.mkdir(parents=True,exist_ok=False)
    env={**os.environ,'WINAPP_UI_WORKFLOW_ID':'aredoko-search-methods-'+uuid.uuid4().hex}
    report={'target':'local','encoder':'actual offline CUDA' if args.cuda else 'CPU contract stub','actual_model':args.cuda,'retrieval_quality':'not evaluated','text_only':args.text_only,'input_verification':'UIA only; physical keyboard not tested','pass':False,'checks':[],'screenshots':[],'requests':[]}
    catalog=None;engine=None;server=None;thread=None;hwnd=None;app_pid=None;process=None
    user32=ctypes.WinDLL('user32',use_last_error=True)
    kernel32=ctypes.WinDLL('kernel32',use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user32.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    user32.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
    kernel32.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel32.OpenProcess.restype=wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel32.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
    kernel32.CloseHandle.argtypes=[wintypes.HANDLE]

    def check(name,value):
        if not value:raise RuntimeError(name)
        report['checks'].append(name);print(json.dumps({'check':name},ensure_ascii=True),flush=True)
    def cli(*args):
        result=subprocess.run(['winapp',*map(str,args)],cwd=REPO,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        if result.returncode:raise RuntimeError('winapp '+str(args)+': '+result.stdout+result.stderr)
        return result.stdout
    def ui(*args,window=None):return cli('ui',*args,'-w',window or hwnd)
    def wait(identifier,value):ui('wait-for',identifier,'--value',value,'-t','40000')
    def ready():ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','40000');time.sleep(.4)
    def choose(combo,option,label):
        # Refresh the peer after result rendering/screenshot layout changes.
        ui('inspect',combo,'--json')
        ui('wait-for',combo,'-p','IsEnabled','--value','True','-t','5000')
        ui('invoke',combo,'--action','expand')
        for _ in range(30):
            windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
            popups=[w for w in windows if w.get('title')=='PopupHost']
            if len(popups)==1:break
            time.sleep(.1)
        if len(popups)!=1:raise RuntimeError('Expected one owned popup')
        popup=str(popups[0]['hwnd'])
        tree=json.loads(ui('inspect','--json','--depth','12',window=popup))
        # Names are substring searches in the CLI; '画像' also matches result
        # labels. Resolve the unique exact observed ListItem peer instead.
        matches={n['selector']:n for n in nodes(tree) if n.get('selector') and
                 (n.get('automationId')==option or (n.get('type')=='ListItem' and n.get('name')==option))}
        if len(matches)!=1:raise RuntimeError('Expected unique exact popup option '+option)
        ui('invoke',next(iter(matches)),'--action','select',window=popup)
        wait(combo,label);ready()
    def shot(name):
        path=target/(name+'.png');ui('screenshot','--output',path)
        check('Delivered '+name,path.is_file() and path.stat().st_size>0)
        report['screenshots'].append(path.name)
    def resize(width,height):
        if not user32.SetWindowPos(int(hwnd),None,0,0,width,height,0x0014):raise ctypes.WinError(ctypes.get_last_error())
        time.sleep(.4)
    def nodes(value):
        if isinstance(value,dict):
            yield value
            for child in value.values():yield from nodes(child)
        elif isinstance(value,list):
            for child in value:yield from nodes(child)
    def fits(phase):
        tree=json.loads(ui('inspect','--json','--depth','8'))
        root=tree['windows'][0]['elements'][0]
        found=list(nodes(tree))
        for identifier in ('TxtQuery','CmbKind','CmbSearchMode','TxtSearchMethodHint','BtnSearch','BtnAIIndex','BtnLayout'):
            matches=[n for n in found if n.get('automationId')==identifier]
            check(phase+' '+identifier+' visible',len(matches)==1 and not matches[0].get('isOffscreen') and matches[0]['width']>0 and matches[0]['height']>0 and matches[0]['x']>=root['x'] and matches[0]['y']>=root['y'] and matches[0]['x']+matches[0]['width']<=root['x']+root['width'] and matches[0]['y']+matches[0]['height']<=root['y']+root['height'])
        (target/(phase+'-tree.json')).write_text(json.dumps(tree,ensure_ascii=False),encoding='utf-8')
    def assert_request(source,kind='',view='all',ids=None):
        for _ in range(100):
            with engine.record_lock:latest=engine.requests[-1] if engine.requests else None
            if latest and latest['source']==source and latest['kind']==kind and latest['view']==view:break
            time.sleep(.05)
        check('GUI request '+source+'/'+kind+'/'+view,latest is not None and latest['query']=='UIモード確認' and latest['source']==source and latest['kind']==kind and latest['view']==view and latest['page']==0 and latest['scope']==scope and not latest.get('failed') and (ids is None or latest['ids']==ids))
    def close():
        nonlocal hwnd,app_pid,process
        if process:
            if kernel32.WaitForSingleObject(process,0)!=0:
                owner=wintypes.DWORD();user32.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
                if owner.value!=app_pid:raise RuntimeError('Owned window changed')
                user32.PostMessageW(int(hwnd),0x0010,0,0)
                if kernel32.WaitForSingleObject(process,7000)==0:
                    report['graceful_closes']=report.get('graceful_closes',0)+1
                else:
                    report.setdefault('cleanup_warnings',[]).append('Owned test process required termination')
                    kernel32.TerminateProcess(process,1);kernel32.WaitForSingleObject(process,5000)
            kernel32.CloseHandle(process);process=None;hwnd=None;app_pid=None
    hashes={}
    try:
        existing=subprocess.run(['powershell','-NoProfile','-Command','if(Get-Process Aredoko.WinUI -ErrorAction SilentlyContinue){exit 1}'],capture_output=True)
        if existing.returncode:raise RuntimeError('Existing app; never attach to its data')
        # Bind before fixture creation; an occupied production port stops this run.
        server=ThreadingHTTPServer(('127.0.0.1',8769),production_handler)
        catalog=ProductionCatalog(target/'catalog.sqlite')
        roots=[]
        for number in (1,2):
            media=target/('media-'+str(number));media.mkdir()
            for item in range(2 if number==1 else 1):
                (media/('generated-'+str(item)+'.png')).write_bytes(graphic({'background':'white','objects':[{'shape':'circle','color':'red','x':90,'y':120,'sx':40,'sy':40}]}))
            root=catalog.add_root(str(media));roots.append(root);catalog.start_scan(root);catalog._worker.join(10)
            check('Generated scan '+str(number),catalog.scan_state()['state']=='complete')
        rows=catalog.search()['items'];first=rows[0]['id']
        for i,row in enumerate(rows):catalog.update([row['id']],{'tags':['テスト素材'],'favorite':i!=1,'shelf':'テスト棚'})
        scope={'root_ids':[roots[0]],'kind':'','shelf':None}
        settings=target/'settings.json';settings.write_text(json.dumps({'version':1,'profile':'default','scope':scope}),encoding='utf-8')
        profile_file=None
        if args.cuda:
            profile_file=target/'profile.json';profile_file.write_text(json.dumps(profile.to_dict()),encoding='utf-8')
        profiles=AIProfileSettings(REPO,settings,profile_file)
        encoder=NativeGPUEncoder(profile) if args.cuda else ContractEncoder()
        report['profile']=encoder.profile.identity()
        report['profile_key']=encoder.profile.key
        engine=RecordedAI(catalog,encoder,ranking='mean-rrf')
        check('Counts before model load',engine.coverage(scope)['target_total']==2 and not encoder.resident)
        engine.start(scope=scope);engine.worker.join(180)
        check('Index ready',not engine.worker.is_alive() and engine.status()['state']=='complete' and engine.status()['indexed']==2)
        if args.cuda:
            check('Actual CUDA index',encoder.device=='cuda' and encoder.calls['document']==2 and encoder.calls['image']==(0 if args.text_only else 2))
            check('Profile capability/store isolation',engine.profile.modalities==profile.modalities and engine.store.path==profile.store_path(catalog.path))
        vector_before=vector_digest(engine)
        hashes={str(p.relative_to(target)):(p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest()) for p in target.glob('media-*/*.png')}
        settings_bytes=settings.read_bytes()
        base=production_handler(catalog,secrets.token_urlsafe(32),engine,profiles=profiles)
        class QuietHandler(base):
            def log_message(self,*args):pass
        server.RequestHandlerClass=QuietHandler
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        for theme in ('Light','Dark'):
            launch=json.loads(cli('run','src/Aredoko.WinUI','-c','Release','--arch','x64','-p','Platform=x64','-p','SelfContained=true','--no-build','--detach','--json','--args','--ui-theme '+theme.lower()))
            if launch.get('ProcessScope') not in (None,'local'):raise RuntimeError('Wrong target')
            app_pid=int(launch['ProcessId']);process=kernel32.OpenProcess(0x00100001,False,app_pid)
            if not process:raise RuntimeError('Cannot observe owned process')
            for _ in range(50):
                windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
                main=[w for w in windows if w.get('hwnd') and 'Aredoko' in w.get('title','') and w.get('title')!='PopupHost']
                if len(main)==1:break
                time.sleep(.1)
            if len(main)!=1:raise RuntimeError('Expected owned main window')
            hwnd=str(main[0]['hwnd']);ready();resize(1200,800)
            user32.GetDpiForWindow.argtypes=[wintypes.HWND];user32.GetDpiForWindow.restype=wintypes.UINT
            class HighContrast(ctypes.Structure):
                _fields_=[('cbSize',wintypes.UINT),('dwFlags',wintypes.DWORD),('lpszDefaultScheme',wintypes.LPWSTR)]
            contrast=HighContrast();contrast.cbSize=ctypes.sizeof(contrast)
            user32.SystemParametersInfoW.argtypes=[wintypes.UINT,wintypes.UINT,ctypes.c_void_p,wintypes.UINT]
            if not user32.SystemParametersInfoW(0x0042,contrast.cbSize,ctypes.byref(contrast),0):raise ctypes.WinError(ctypes.get_last_error())
            report.setdefault('display',[]).append({'theme':theme,'dpi':user32.GetDpiForWindow(int(hwnd)),'high_contrast':bool(contrast.dwFlags&1)})
            wait('CmbSearchMode','名前・タグ');wait('TxtCount','3 件')
            before=len(engine.requests);choose('CmbSearchMode','ModeText','AI文章')
            wait('TxtSearchMethodHint','名前・タグの意味から探します。本の本文や音声は読み取りません。')
            check(theme+' empty query remains literal',len(engine.requests)==before)
            ui('set-value','TxtQuery','UIモード確認');time.sleep(.5);ui('invoke','BtnSearch');ready();wait('TxtCount','2 件');assert_request('text')
            fits(theme+'-text-wide');shot(theme+'-text-wide')
            choose('CmbKind','画像','画像');assert_request('text','image')
            ui('invoke','NavFavorites','--action','select');ready();wait('TxtCount','1 件');assert_request('text','image','favorites',[first])
            choose('CmbSearchMode','ModeSemantic','AI混合');assert_request('all','image','favorites',[first])
            wait('TxtSearchMethodHint','名前・タグと画像・表紙を組み合わせて探します。')
            before_query=dict(encoder.calls) if args.cuda else None
            choose('CmbSearchMode','ModeVisual','AI画像・表紙')
            if args.text_only:
                wait('TxtCount','—');wait('TxtPageNumber','—')
                ui('wait-for','Message','--value','選択中のモデルは画像・表紙検索に対応していません。AI文章を使ってください。','-t','10000')
                check(theme+' unsupported cover rejected before inference',dict(encoder.calls)==before_query and engine.requests[-1]['source']=='cover' and engine.requests[-1].get('failed'))
                for identifier in ('BtnPrevious','BtnNext'):ui('wait-for',identifier,'-p','IsEnabled','--value','False','-t','10000')
            else:assert_request('cover','image','favorites',[first])
            resize(700,620);fits(theme+'-cover-narrow');shot(theme+'-cover-narrow');resize(1200,800)
            choose('CmbSearchMode','ModeText','AI文章');assert_request('text','image','favorites',[first])
            ui('invoke','Item'+str(first),'--action','select');wait('TxtEditStatus','保存済み');ui('set-value','TxtTags','unsaved-mode-test');wait('TxtEditStatus','未保存の変更')
            before=len(engine.requests);choose('CmbSearchMode','ModeLiteral','名前・タグ')
            ui('wait-for','PrimaryButton','-t','5000');ui('invoke','CloseButton');ready()
            wait('CmbSearchMode','AI文章');wait('TxtTags','unsaved-mode-test')
            wait('TxtSearchMethodHint','名前・タグの意味から探します。本の本文や音声は読み取りません。')
            query_name=json.loads(ui('get-property','TxtQuery','--property','Name','--json'))
            check(theme+' cancelled mode restores query accessibility', 'AI検索の文章' in json.dumps(query_name,ensure_ascii=False))
            check(theme+' cancelled mode sends no AI request',len(engine.requests)==before)
            shot(theme+'-dirty-restored')
            choose('CmbSearchMode','ModeSemantic' if args.text_only else 'ModeVisual','AI混合' if args.text_only else 'AI画像・表紙');ui('wait-for','PrimaryButton','-t','5000');ui('invoke','PrimaryButton');ready()
            assert_request('all' if args.text_only else 'cover','image','favorites',[first]);check(theme+' discard does not persist edit',catalog.search()['items'][0]['tags']==['テスト素材'])
            encoder.fail=True
            choose('CmbSearchMode','ModeText','AI文章');ui('invoke','BtnSearch');ready();wait('TxtCount','—')
            ui('wait-for','TxtEmpty','--value','名前・タグ検索に切り替えるか','--contains','-t','5000')
            wait('TxtPageNumber','—')
            for identifier in ('BtnPrevious','BtnNext'):ui('wait-for',identifier,'-p','IsEnabled','--value','False','-t','5000')
            check(theme+' error clears count/pagination and shows guidance',True)
            choose('CmbSearchMode','ModeLiteral','名前・タグ');ui('set-value','TxtQuery','generated');time.sleep(.5);ui('invoke','BtnSearch');ready();wait('TxtCount','2 件')
            check(theme+' literal recovery ignores saved AI scope',True)
            encoder.fail=False
            if args.cuda:
                report.setdefault('telemetry',[]).append({'theme':theme,'device':encoder.device,'peak_allocated_mib':encoder.peak_cuda_allocated_mib})
                check(theme+' queries retain vectors',vector_digest(engine)==vector_before)
                before_calls=dict(encoder.calls);engine.release()
                check(theme+' owned worker released',not encoder.resident)
                engine.start(scope=scope);engine.worker.join(30)
                check(theme+' cached rebuild without model reload',not engine.worker.is_alive() and engine.status()['state']=='complete' and engine.status()['indexed']==2 and not encoder.resident and dict(encoder.calls)==before_calls and vector_digest(engine)==vector_before)
            close()
        check('Saved scope/settings unchanged',settings.read_bytes()==settings_bytes)
        report['requests']=engine.requests;report['encoder_calls']=dict(encoder.calls) if args.cuda else encoder.calls
        check('Vectors unchanged across native sessions',vector_digest(engine)==vector_before)
        check('Worker not resident at end',not encoder.resident)
        report['pass']=True
    except Exception as ex:
        report['error']=str(ex)
        if hwnd:
            try:shot('failure')
            except Exception:pass
        raise
    finally:
        try:close()
        except Exception as cleanup_error:
            report['pass']=False
            report['cleanup_error']=str(cleanup_error)
            raise
        finally:
            try:
                if thread:server.shutdown();thread.join(5)
                if server:server.server_close()
                if engine:
                    report['requests']=engine.requests
                    report['encoder_calls']=dict(engine.encoder.calls) if args.cuda else engine.encoder.calls
                    engine.close()
                    if args.cuda:
                        report['owned_exits']=engine.encoder.observed_exits
                        if not report['owned_exits'] or not all(row['stopped'] for row in report['owned_exits']):raise RuntimeError('Owned worker handle cleanup failed')
            except Exception as cleanup_error:
                report['pass']=False
                report['cleanup_error']=str(cleanup_error)
                raise
            finally:
                try:
                    if catalog:catalog.close()
                    cli('ui','yield')
                except Exception as cleanup_error:
                    report['pass']=False
                    report['cleanup_error']=str(cleanup_error)
                    raise
                finally:
                    actual={str(p.relative_to(target)):(p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest()) for p in target.glob('media-*/*.png')}
                    report['source_hashes_mtime_unchanged']=bool(hashes) and hashes==actual
                    if not report['source_hashes_mtime_unchanged']:report['pass']=False
                    (target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'pass':report['pass'],'checks':len(report['checks']),'screenshots':report['screenshots']},ensure_ascii=True))
    if not report['pass']:raise RuntimeError('Native checks failed; see result.json')


if __name__=='__main__':main()
