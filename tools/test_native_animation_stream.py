"""Native streaming acceptance on generated fixtures or the explicitly attached sample.

The provided sample is read/copied to isolated media; its parent is never scanned.
No models, downloads, OS registration or system settings. Exact owned PID/HWND.
"""
import argparse,ctypes,hashlib,json,os,secrets,shutil,socket,struct,subprocess,sys,threading,time,traceback
from ctypes import wintypes
from http.server import ThreadingHTTPServer
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'app'),str(REPO/'tools')]
from PIL import Image
from production import ProductionCatalog
from production_server import production_handler,DisabledAI
from ai_settings import AIProfileSettings
from wd_tagger import DisabledTagger
from animation_sessions import MIME
from native_ui_tools import process_memory


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--frontend',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--provided-sample',type=Path,help='Only the explicitly attached E:/picture/!gif/10.gif, read/copy only');parser.add_argument('--large-generated',action='store_true')
    parser.add_argument('--original-generated',action='store_true',help='Three 2560x1440 frames; verify original-size viewer transport')
    args=parser.parse_args()
    if sum((args.large_generated,args.original_generated,bool(args.provided_sample)))>1:parser.error('Choose one generated or explicitly provided media flow')
    front=args.frontend.resolve();target=args.output.resolve()
    if os.name!='nt' or not front.is_relative_to(REPO/'data/ai-ui') or not (front/'Aredoko.WinUI.exe').is_file() or not target.is_relative_to(REPO/'data/ai-ui') or target.exists():parser.error('Dedicated frontend and new isolated output required')
    target.mkdir(parents=True);media=target/'media';media.mkdir()
    report={'pass':False,'checks':[],'screenshots':[],'visual_review':'pending','source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),'frontend_sha256':hashlib.sha256((front/'Aredoko.WinUI.dll').read_bytes()).hexdigest()}
    tracked=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','--','app','src'],cwd=REPO,text=True).splitlines()
    report['source_files']={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in tracked}
    report['diff_sha256']=hashlib.sha256(subprocess.check_output(['git','diff','--','app','src'],cwd=REPO)).hexdigest()
    env={**os.environ,'LOCALAPPDATA':str(target/'user'),'APPDATA':str(target/'user'),'AREDOKO_VIEWER_TIMINGS':'1','WINAPP_UI_WORKFLOW_ID':'aredoko-stream-native-'+target.name}
    user=ctypes.WinDLL('user32',use_last_error=True);user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)];user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    proc=cat=server=thread=None;main_hwnd=viewer_hwnd=None;observed=[];closes=[]
    viewer_prefix='Aredoko — 画像ビューア';frame_count=3 if args.original_generated else 18 if args.large_generated else 70
    def check(name,value):
        report['checks'].append({'name':name,'pass':bool(value)});print(name,bool(value),flush=True)
        if not value:raise AssertionError(name)
    def cli(*args):
        r=subprocess.run(['winapp','ui',*map(str,args)],cwd=REPO,env=env,text=True,encoding='utf-8',errors='replace',capture_output=True,timeout=30)
        with (target/'commands.log').open('a',encoding='utf-8') as f:f.write(json.dumps({'args':list(map(str,args)),'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr},ensure_ascii=False)+'\n')
        if r.returncode:raise RuntimeError(r.stdout+r.stderr)
        return r.stdout
    def ui(hwnd,*args):
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
        if proc is None or proc.poll() is not None or owner.value!=proc.pid:raise RuntimeError('Owned window/process changed')
        return cli(*args,'-w',hwnd)
    def wait(name,predicate,seconds=18):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if predicate():check(name,True);return
            time.sleep(.1)
        check(name,False)
    def windows():return json.loads(cli('list-windows','-a',proc.pid,'--json'))
    def find_viewer():
        nonlocal viewer_hwnd
        rows=[w for w in windows() if w.get('title','').startswith(viewer_prefix)]
        if len(rows)!=1:return False
        viewer_hwnd=str(rows[0]['hwnd']);return True
    def shot(name):
        path=target/(name+'.png');ui(viewer_hwnd,'screenshot','--focus','--output',path)
        raw=path.read_bytes();check('nonempty screenshot '+name,raw[:8]==b'\x89PNG\r\n\x1a\n' and min(struct.unpack('>II',raw[16:24]))>=100)
        report['screenshots'].append(str(path));(target/(name+'.json')).write_text(ui(viewer_hwnd,'inspect','--depth','18','--json'),encoding='utf-8')
        report.setdefault('memory_samples',[]).append({'stage':name,'frontend':process_memory(proc.pid),'backend':process_memory(os.getpid())})
    def show_chrome(viewport):
        user.SetForegroundWindow.argtypes=[wintypes.HWND];user.GetForegroundWindow.restype=wintypes.HWND
        if user.GetForegroundWindow()!=int(viewer_hwnd):user.SetForegroundWindow(int(viewer_hwnd))
        if user.GetForegroundWindow()!=int(viewer_hwnd):raise RuntimeError('Owned viewer must be foreground before keyboard input')
        ui(viewer_hwnd,'focus',viewport);ui(viewer_hwnd,'send-keys','f10','--via','send-input')
    try:
        supplied_before=None
        if args.provided_sample:
            sample=args.provided_sample.resolve()
            if sample!=Path('E:/picture/!gif/10.gif').resolve():raise ValueError('Only the explicitly attached sample is authorized')
            supplied_before=(hashlib.sha256(sample.read_bytes()).hexdigest(),sample.stat().st_mtime_ns)
            shutil.copyfile(sample,media/'provided-10.gif')
            with Image.open(media/'provided-10.gif') as image:
                report['provided_sample']={'format':image.format,'size':list(image.size),'frames':image.n_frames,'copied_to_isolated_media':True,'original_modified':False}
        else:
            dimensions=(2560,1440) if args.original_generated else (2560,1920) if args.large_generated else (180,160)
            frames=[Image.new('RGBA',dimensions,(40+(i*7)%190,70+(i*3)%170,100+(i*11)%150,255)) for i in range(frame_count)]
            poster=Image.new('RGBA',dimensions,(210,210,210,255))
            durations=[80 if args.large_generated else 30]*frame_count;durations[0]=700;durations[min(64,frame_count-1)]=500;durations[-1]=800
            poster.save(media/'a-long.png',format='PNG',save_all=True,append_images=frames,default_image=True,duration=durations,loop=2,disposal=[0]*frame_count,blend=[0]*frame_count)
            frames[0].save(media/'b-native.gif',format='GIF',save_all=True,append_images=frames[1:4],duration=180,loop=1)
            frames[0].save(media/'c-disguised.gif',format='WEBP',save_all=True,append_images=frames[1:8],duration=140,loop=2,lossless=True)
            poster.close()
            for frame in frames:frame.close()
            if args.large_generated:
                import random,zipfile,io
                rng=random.Random(20261026);frames=[]
                for _ in range(80):
                    frame=Image.frombytes('P',(1024,768),rng.randbytes(1024*768));frame.putpalette([v for i in range(256) for v in (i,i,i)]);frames.append(frame)
                frames[0].save(media/'d-large.gif',save_all=True,append_images=frames[1:],duration=80,loop=0,optimize=False)
                for frame in frames:frame.close()
                check('generated GIF crosses old 64MiB source cap',64*1024**2<(media/'d-large.gif').stat().st_size<256*1024**2)
                with zipfile.ZipFile(media/'z-large.cbz','w',compression=zipfile.ZIP_STORED) as book:
                    for page in range(8):
                        with Image.new('RGB',(3072,2048),(40+page*20,80,160)) as image,io.BytesIO() as buffer:
                            image.save(buffer,format='PNG');book.writestr(f'{page:02}.png',buffer.getvalue())
                report['large_generated']={'apng_source_dimensions':list(dimensions),'apng_frames':frame_count,'gif_bytes':(media/'d-large.gif').stat().st_size,'cbz_pages':8,'cbz_page_dimensions':[3072,2048]}
        sources={p.name:[hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns] for p in media.iterdir()}
        cat=ProductionCatalog(target/'catalog.sqlite');root=cat.add_root(str(media));cat.start_scan(root)
        if cat._worker:cat._worker.join(10)
        ids={row['title']:row['id'] for row in cat.search()['items']}
        check('all isolated test images registered',all(name in ids for name in sources))
        profiles=AIProfileSettings(target,target/'settings.json',ai_python=str(target/'missing-python'),models_root=target/'missing-models')
        instance=secrets.token_hex(16);env['AREDOKO_STARTUP_INSTANCE']=instance
        handler=production_handler(cat,secrets.token_hex(32),DisabledAI(),profiles=profiles,tagger=DisabledTagger(),runtime_preferences=target/'launch-settings.json',instance_id=instance)
        class Recorded(handler):
            def log_message(self,*args):pass
            def send(self,status,body,mime='application/json; charset=utf-8',extra_headers=None):
                if mime==MIME and status==200:
                    size=struct.unpack_from('<I',body)[0];metadata=json.loads(body[4:4+size])
                    observed.append({'action':self.path.rsplit('/',1)[-1],'item_id':metadata['item_id'],'width':metadata['width'],'height':metadata['height'],'frames':metadata['frames'],'done':metadata['done']})
                elif self.path=='/api/library/animation/close' and status==200:closes.append(True)
                return super().send(status,body,mime,extra_headers)
        server=ThreadingHTTPServer(('127.0.0.1',8769),Recorded,bind_and_activate=False);server.allow_reuse_address=False
        server.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1);server.server_bind();server.server_activate()
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        with (target/'app.log').open('w',encoding='utf-8') as log:proc=subprocess.Popen([str(front/'Aredoko.WinUI.exe'),'--ui-theme','dark','--viewer-settings',str(target/'viewer-settings.json')],cwd=front,env=env,stdout=log,stderr=subprocess.STDOUT)
        report['owned_pid']=proc.pid
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            rows=[w for w in windows() if w.get('title') and w['title']!='PopupHost']
            if len(rows)==1:main_hwnd=str(rows[0]['hwnd']);break
            if proc.poll() is not None:raise RuntimeError('Frontend exited before window')
            time.sleep(.2)
        check('owned main window',main_hwnd is not None)
        first_name='provided-10.gif' if args.provided_sample else 'a-long.png'
        if args.original_generated:
            ui(main_hwnd,'wait-for','TxtPageNumber','--value','1–3 / 3','-t','10000')
            check('initial library range uses the same notation as navigation',True)
        ui(main_hwnd,'wait-for','Item'+str(ids[first_name]),'-t','10000');ui(main_hwnd,'invoke','Item'+str(ids[first_name]),'--action','select')
        ui(main_hwnd,'invoke','BtnDetails');ui(main_hwnd,'wait-for','BtnOpenImage','-p','IsEnabled','--value','True','-t','7000');ui(main_hwnd,'invoke','BtnOpenImage')
        wait('owned viewer window',find_viewer)
        if args.provided_sample:
            show_chrome('ImageViewport')
            ui(viewer_hwnd,'wait-for','ViewerImage','--value','provided-10.gifの画像（アニメーション','--contains','-t','10000');shot('provided-sample-playing')
            wait('provided sample reaches its second decode cycle',lambda:any(f['cycle']>=1 for batch in observed for f in batch['frames']),seconds=35)
            shot('provided-sample-second-cycle')
            delivered=[f for batch in observed for f in batch['frames']]
            check('all 55 first-cycle frames decoded',[(f['index'],f['cycle']) for f in delivered[:55]]==[(i,0) for i in range(55)])
            check('actual WebP container used despite gif extension',report['provided_sample']['format']=='WEBP' and len(observed)>0)
        else:
            ui(viewer_hwnd,'wait-for','ViewerImage','--value','a-long.pngの画像（アニメーション','--contains','-t','10000')
            show_chrome('ImageViewport')
            shot('apng-playing')
            ui(viewer_hwnd,'wait-for','ViewerImage','--value',f'a-long.pngの画像（アニメーション {frame_count}）','-t','30000')
            wait('finite APNG completes and releases its session',lambda:bool(closes))
            ui(viewer_hwnd,'wait-for','ViewerImage','--value',f'a-long.pngの画像（アニメーション {frame_count}）','-t','3000');shot('apng-final-retained')
            batches=[x for x in observed if x['item_id']==ids['a-long.png']]
            check('first APNG batch contains only its first frame',len(batches[0]['frames'])==1 and batches[0]['frames'][0]['index']==0)
            check('open and first frame share one request',batches[0]['action']=='open-first')
            delivered=[f for x in batches for f in x['frames']]
            check('all frames and both cycles delivered without poster',[(f['index'],f['cycle']) for f in delivered]==[(i,c) for c in range(2) for i in range(frame_count)])
            if args.original_generated:
                check('APNG viewer receives original pixels beyond the old edge cap',all((x['width'],x['height'])==(2560,1440) for x in batches))
                check('APNG batches remain within the byte budget',all(sum(f['byte_length'] for f in x['frames'])<=128*1024*1024 for x in batches))
            ui(viewer_hwnd,'invoke','ImageNext');ui(viewer_hwnd,'wait-for','ViewerImage','--value','b-native.gifの画像','-t','10000');ui(viewer_hwnd,'wait-for','ImageZoomIn','-p','IsEnabled','--value','True','-t','10000');shot('native-gif')
            check('true GIF uses native path without a streaming decode session',not any(x['item_id']==ids['b-native.gif'] for x in observed))
            ui(viewer_hwnd,'invoke','ImageNext');ui(viewer_hwnd,'wait-for','ViewerImage','--value',f'c-disguised.gifの画像（アニメーション {min(8,frame_count)}）','-t','30000')
            wait('disguised WebP completes and releases session',lambda:len(closes)>=2);shot('disguised-webp-final')
            check('WebP with gif extension streams actual decoded frames',any(x['item_id']==ids['c-disguised.gif'] for x in observed))
            if args.original_generated:
                webp=[x for x in observed if x['item_id']==ids['c-disguised.gif']]
                check('WebP viewer receives original pixels beyond the old edge cap',all((x['width'],x['height'])==(2560,1440) for x in webp))
            if args.large_generated:
                ui(viewer_hwnd,'invoke','ImageNext');wait('large GIF streams beyond its first frame',lambda:any(x['item_id']==ids['d-large.gif'] and any(f['index']>=2 for f in x['frames']) for x in observed),seconds=30)
                shot('large-gif-streaming')
        user.PostMessageW(int(viewer_hwnd),0x10,0,0);wait('viewer closes normally',lambda:not any(str(w['hwnd'])==viewer_hwnd for w in windows()))
        if args.provided_sample:wait('async decoder close acknowledged',lambda:bool(closes),seconds=7)
        def decoders_closed():
            with handler.animations.lock:return not handler.animations.sessions
        # Window close schedules an independently owned HTTP decoder close.
        # An infinite large GIF is still active here, unlike the finite cases.
        wait('no owned decoder sessions remain',decoders_closed,seconds=8)
        if args.large_generated:
            ui(main_hwnd,'invoke','Item'+str(ids['z-large.cbz']),'--action','select');ui(main_hwnd,'invoke','BtnDetails');ui(main_hwnd,'wait-for','BtnOpenBook','-p','IsEnabled','--value','True','-t','10000');ui(main_hwnd,'invoke','BtnOpenBook')
            viewer_prefix='Aredoko — 本ビューア';wait('owned book viewer opens',find_viewer)
            ui(viewer_hwnd,'wait-for','ReaderImage','--value','1ページ','-t','15000');show_chrome('ReaderViewport');shot('cbz-first')
            for action,page in [('ReaderNext',2),('ReaderNext',3),('ReaderPrevious',2),('ReaderPrevious',1)]:
                ui(viewer_hwnd,'invoke',action);ui(viewer_hwnd,'wait-for','ReaderImage','--value',f'{page}ページ','-t','15000');ui(viewer_hwnd,'wait-for','ReaderFit','-p','IsEnabled','--value','True','-t','10000')
            shot('cbz-cached-return');user.PostMessageW(int(viewer_hwnd),0x10,0,0);wait('book viewer closes normally',lambda:not any(str(w['hwnd'])==viewer_hwnd for w in windows()))
        traces=target/'user/Aredoko/logs/viewer-load.jsonl';check('viewer trace stays in dedicated LOCALAPPDATA',traces.is_file())
        report['timings']=[json.loads(line) for line in traces.read_text(encoding='utf-8').splitlines()]
        check('first animation-frame assignment was measured',any(x['stage']=='first-frame-assigned' for x in report['timings']))
        check('generated source hashes and mtimes unchanged',sources=={p.name:[hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns] for p in media.iterdir()})
        if args.provided_sample:check('attached original SHA and mtime unchanged',supplied_before==(hashlib.sha256(sample.read_bytes()).hexdigest(),sample.stat().st_mtime_ns))
        report['pass']=True
    except Exception:
        report['error']=traceback.format_exc();print(report['error'],flush=True)
        if viewer_hwnd and proc is not None and proc.poll() is None:
            try:shot('failure')
            except Exception:report['capture_error']=traceback.format_exc()
    finally:
        if proc is not None and proc.poll() is None:
            try:
                if viewer_hwnd and any(str(w['hwnd'])==viewer_hwnd for w in windows()):
                    owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(viewer_hwnd),ctypes.byref(owner))
                    if owner.value!=proc.pid:raise RuntimeError('Cleanup viewer owner changed')
                    user.PostMessageW(int(viewer_hwnd),0x10,0,0);time.sleep(.2)
                if main_hwnd:user.PostMessageW(int(main_hwnd),0x10,0,0)
                proc.wait(timeout=12)
            except Exception:report['cleanup_error']=traceback.format_exc()
        if server:
            if thread:server.shutdown()
            server.server_close()
        if thread:thread.join(5)
        if server:
            for resource in (handler.download_jobs,handler.restore_jobs,handler.backup_jobs,handler.thumbnails,handler.results,handler.animations,handler.setup_jobs):resource.close()
        if cat:cat.close()
        report.update(frontend_exit_code=None if proc is None else proc.poll(),process_still_running=proc is not None and proc.poll() is None,delivered_batches=observed,closed_sessions=len(closes))
        if report['source_files']!={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in tracked}:report['pass']=False;report['source_changed']=True
        report['test_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        try:cli('yield')
        except Exception:pass
    return 0 if report['pass'] and report.get('frontend_exit_code')==0 and not report.get('process_still_running') else 1
if __name__=='__main__':raise SystemExit(main())
