"""Owned image viewer/navigation and archive regression checks on generated media only.

Built x64 Release required. No models, downloads, OS settings or private media.
Physical input is guarded by owned HWND/PID and verified foreground; denied
activation is recorded as skipped, never claimed as keyboard coverage.
"""
import zipfile,struct
from urllib.parse import urlparse
import argparse,ctypes,hashlib,json,os,secrets,shutil,subprocess,sys,threading,time,uuid
from native_ui_tools import viewer_wait_args
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
    parser.add_argument('--animation-only',action='store_true');parser.add_argument('--feedback-input-only',action='store_true');parser.add_argument('--double-click-only',action='store_true');parser.add_argument('--reader-spread-only',action='store_true');parser.add_argument('--reader-progress-only',action='store_true');parser.add_argument('--video-and-evidence-only',action='store_true');parser.add_argument('--evidence-only',action='store_true');parser.add_argument('--video-player-only',action='store_true');parser.add_argument('--video-range-only',action='store_true');parser.add_argument('--video-seek-only',action='store_true');args=parser.parse_args();args.video_player_only=args.video_player_only or args.video_range_only or args.video_seek_only;target=args.output.resolve()
    if os.name!='nt':parser.error('Native Windows required')
    if not target.is_relative_to((REPO/'data/ai-ui').resolve()):parser.error('Evidence must stay in data/ai-ui')
    target.mkdir(parents=True,exist_ok=False)
    env={**os.environ,'WINAPP_UI_WORKFLOW_ID':'aredoko-image-'+uuid.uuid4().hex}
    report={'pass':False,'target':'local','actual_model':False,'checks':[],'screenshots':[],'keyboard_actions':[],'keyboard_skipped':[],'display':[],'audit_scope':'image modal/auto-hide overlays/navigation/current-page scope/zoom/draft/errors and archive regression; not whole-app audit'}
    catalog=engine=server=thread=None;hwnd=main_hwnd=app_pid=process=None;original={}
    expected_source={}
    selected_item_id=None
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
        if args and args[0]=='wait-for' and len(args)>1 and args[1] in ('ImageViewerDialog','ArchiveReaderDialog','VideoPlayerDialog') and '--gone' in args:
            title='画像ビューア' if args[1]=='ImageViewerDialog' else ('動画再生' if args[1]=='VideoPlayerDialog' else '読書画面')
            for _ in range(50):
                windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
                if not any(title in w.get('title','') for w in windows):break
                time.sleep(.1)
            else:raise RuntimeError('Owned viewer window did not close')
            hwnd=main_hwnd
        if args and args[0]=='wait-for' and len(args)>1 and args[1] in ('ImageViewerDialog','ArchiveReaderDialog','VideoPlayerDialog') and '--gone' not in args:
            title='画像ビューア' if args[1]=='ImageViewerDialog' else ('動画再生' if args[1]=='VideoPlayerDialog' else '読書画面')
            for _ in range(50):
                windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
                matches=[w for w in windows if title in w.get('title','')]
                if len(matches)==1:
                    hwnd=str(matches[0]['hwnd']);break
                time.sleep(.1)
            else:raise RuntimeError('Owned viewer window unavailable')
        return cli('ui',*viewer_wait_args(args),'-w',hwnd)
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
        if phase.endswith('-viewer') or phase.endswith('-reader') or phase.endswith('-video'):
            prefix='Image' if phase.endswith('-viewer') else ('Video' if phase.endswith('-video') else 'Reader')
            outer=next(n for n in all_nodes if n.get('automationId')==prefix+'Viewport')
            toolbar=next(n for n in all_nodes if n.get('automationId')==prefix+'Toolbar')
            if prefix=='Video':
                check(phase+' duplicate client header removed',not any(n.get('automationId') in ('VideoHeader','VideoClose') for n in all_nodes))
            else:
                close_node=next(n for n in all_nodes if n.get('automationId')==prefix+'Close')
                check(phase+' header is flush to image canvas top',0<=close_node['y']-outer['y']<=12)
            check(phase+' toolbar docks flush without side or bottom gaps',abs(toolbar['x']-outer['x'])<=2 and abs(toolbar['width']-outer['width'])<=2 and abs(toolbar['y']+toolbar['height']-outer['y']-outer['height'])<=2)
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
        if args.reader_spread_only or args.reader_progress_only:
            colors=['red','blue','green','yellow','purple']
            contents=[graphic({'background':'white','objects':[{'shape':'circle','color':color,'x':90,'y':120,'sx':40,'sy':40}]}) for color in colors]
            with zipfile.ZipFile(media/'book.cbz','w') as archive:
                for name,data in zip(['page1.png','page2.png','page10.png','page20.png','page30.png'],contents):archive.writestr(name,data)
            with zipfile.ZipFile(media/'broken.zip','w') as archive:
                for name,data in zip(['page1.png','page2.png','page3.png','page4.png'],[contents[0],b'broken page',contents[2],contents[3]]):archive.writestr(name,data)
        if args.video_and_evidence_only:
            ffmpeg=shutil.which('ffmpeg')
            if not ffmpeg or not shutil.which('ffprobe'):raise RuntimeError('Native FFmpeg tools required for video GUI gate')
            (media/'broken.png').unlink();(media/'book.cbz').unlink()
            for name,size,sar,codec,extra in [
                ('clip.mp4','320x180','1/1','mpeg4',['-movflags','+faststart']),
                ('clip.mkv','320x180','1/1','ffv1',[]),
                ('clip.webm','320x180','1/1','libvpx',[]),
                ('anamorphic.mp4','720x480','8/9','mpeg4',['-movflags','+faststart'])]:
                subprocess.run([ffmpeg,'-nostdin','-v','error','-f','lavfi','-i',f'color=c=red:s={size}:d=0.2','-vf','setsar='+sar,'-threads','1','-c:v',codec,*extra,str(media/name)],check=True,timeout=15)
            (media/'broken.mp4').write_bytes(b'not a valid video')
        if args.evidence_only:
            (media/'broken.png').unlink();(media/'book.cbz').unlink()
            (media/'c.png').write_bytes(graphic({'background':'white','objects':[{'shape':'circle','color':'green','x':90,'y':120,'sx':40,'sy':40}]}))
        if args.video_player_only:
            ffmpeg=shutil.which('ffmpeg')
            if not ffmpeg or not shutil.which('ffprobe'):raise RuntimeError('Native FFmpeg tools required for video player gate')
            (media/'b.png').unlink();(media/'broken.png').unlink();(media/'book.cbz').unlink()
            for name,color,codec,extra in [
                ('clip.mp4','red','libx264',['-pix_fmt','yuv420p','-movflags','+faststart']),
                ('clip.wmv','blue','wmv2',[]),
                ('unsupported.mkv','green','ffv1',[])]:
                subprocess.run([ffmpeg,'-nostdin','-v','error','-f','lavfi','-i',('color=c=red:s=320x180:d=1[r];color=c=blue:s=320x180:d=1[b];[r][b]concat=n=2:v=1:a=0' if args.video_seek_only and name=='clip.mp4' else f'color=c={color}:s=320x180:d=2.0'),'-threads','1','-c:v',codec,*([] if args.video_range_only and name=='clip.mp4' else extra),str(media/name)],check=True,timeout=15)
            (media/'broken.mp4').write_bytes(b'not a valid video')
        if args.video_range_only:
            # Place moov after a valid free atom; mdat offsets stay unchanged.
            # This requires actual native cursor seeking beyond its initial buffer.
            clip=media/'clip.mp4';raw=clip.read_bytes();offset=0
            while offset<len(raw):
                size,kind=struct.unpack_from('>I4s',raw,offset)
                if kind==b'moov':break
                if size<8:raise RuntimeError('Invalid generated MP4 atom')
                offset+=size
            if offset>=len(raw):raise RuntimeError('Generated MP4 has no moov')
            padding=70*1024*1024
            with clip.open('wb') as out:
                out.write(raw[:offset]);out.write(struct.pack('>I4s',padding,b'free'))
                remaining=padding-8
                while remaining:
                    count=min(1024*1024,remaining);out.write(bytes(count));remaining-=count
                out.write(raw[offset:])
            report['large_video_size']=(media/'clip.mp4').stat().st_size
        if args.animation_only:
            import zlib
            from PIL import Image
            (media/'b.png').unlink();(media/'broken.png').unlink();(media/'book.cbz').unlink()
            f0=Image.new('RGBA',(160,120),(220,30,30,255))
            f1=Image.new('RGBA',(160,120),(30,190,40,255))
            f2=Image.new('RGBA',(160,120),(30,50,220,255))
            for name,fmt in [('anim.gif','GIF'),('anim.webp','WEBP'),('anim.png','PNG')]:
                f0.save(media/name,format=fmt,save_all=True,append_images=[f1,f2],duration=[140,140,140],loop=0)
            apng_raw=(media/'anim.png').read_bytes()
            iend=apng_raw.rfind(b'\x00\x00\x00\x00IEND')
            pad_len=54802*1024-len(apng_raw)
            pad_payload=b'A'*pad_len
            chunk=struct.pack('>I4s',len(pad_payload),b'prIv')+pad_payload+struct.pack('>I',zlib.crc32(b'prIv'+pad_payload))
            (media/'large-54mb.apng').write_bytes(apng_raw[:iend]+chunk+apng_raw[iend:])
            report['large_apng_size']=(media/'large-54mb.apng').stat().st_size
        original=source_digest();expected_source=dict(original)
        catalog=ProductionCatalog(target/'catalog.sqlite');root=catalog.add_root(str(media));catalog.start_scan(root);catalog._worker.join(20)
        expected_total=5 if (args.video_player_only or args.animation_only) else (3 if args.evidence_only else (7 if args.video_and_evidence_only else (5 if (args.reader_spread_only or args.reader_progress_only) else 4)))
        check('Generated scan complete',catalog.scan_state()['state']=='complete' and catalog.search()['total']==expected_total)
        ids={x['title']:x['id'] for x in catalog.search()['items']}
        if args.evidence_only:
            catalog.update([ids['a.png']],{'tags':['東方','巫女','魔法"少女']})
            catalog.update([ids['b.png']],{'tags':['東方','博麗霊夢']})
            catalog.update([ids['c.png']],{'tags':['博麗霊夢',r'C:\textures']})
            catalog.terms.upsert({'term':'博麗霊夢','aliases':['霊夢'],'related':['東方','巫女']})
        if args.video_and_evidence_only:
            catalog.update([ids['a.png']],{'tags':['東方','巫女','魔法"少女']})
            catalog.update([ids['clip.mp4']],{'tags':['東方','博麗霊夢']})
            catalog.update([ids['b.png']],{'tags':['博麗霊夢',r'C:\textures']})
            catalog.terms.upsert({'term':'博麗霊夢','aliases':['霊夢'],'related':['東方','巫女']})
        settings=target/'settings.json';settings.write_text(json.dumps({'version':1,'profile':'default','scope':{'root_ids':[root],'kind':'','shelf':None}}),encoding='utf-8');settings_before=settings.read_bytes()
        encoder=ContractEncoder();engine=RecordedAI(catalog,encoder);profiles=AIProfileSettings(REPO,settings)
        token=secrets.token_urlsafe(32);handler=production_handler(catalog,token,engine,profiles=profiles)
        faults={'code':None,'delay':False};entered=threading.Event();released=threading.Event()
        class Quiet(handler):
            def log_message(self,*args):pass
            def do_POST(self):
                if self.headers.get('X-Aredoko-Token')==token and self.headers.get('Origin')=='http://127.0.0.1:8769' and self.path.endswith('/progress'):
                    report.setdefault('progress_posts',[]).append(self.path)
                    if faults.get('progress_save_code'):
                        code=faults.pop('progress_save_code');return self.reject_post(code,{'error':'Generated progress save failure'})
                return super().do_POST()
            def do_GET(self):
                if self.headers.get('X-Aredoko-Token')==token and self.path.endswith('/progress') and faults.get('progress_get_code'):
                    code=faults.pop('progress_get_code');return self.send(code,{'error':'Generated progress read failure'})
                if self.headers.get('X-Aredoko-Token')==token and self.path.startswith('/api/library/preview/'):
                    report.setdefault('image_requests',[]).append(self.path)
                if self.headers.get('X-Aredoko-Token')==token and self.path.startswith('/api/library/reader/'):
                    report.setdefault('reader_requests',[]).append(self.path)
                    if urlparse(self.path).path=='/api/library/reader/'+str(ids['book.cbz'])+'/original/1':
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
                if args.video_and_evidence_only and self.headers.get('X-Aredoko-Token')==token and self.path=='/api/library/preview/'+str(ids['clip.mp4']):
                    if faults.get('video_code'):
                        code=faults.pop('video_code');return self.send(code,{'error':'Generated video failure'})
                    if faults.get('video_delay'):
                        faults['video_delay']=False;entered.set()
                        if not released.wait(25):return self.send(503,{'error':'Generated video delay timeout'})
                if args.video_player_only and self.headers.get('X-Aredoko-Token')==token and self.path.startswith('/api/library/video/'):
                    report.setdefault('video_requests',[]).append(self.path)
                    report.setdefault('video_ranges',[]).append({'route':urlparse(self.path).path,'span':self.headers.get('Range')})
                    if args.video_seek_only and urlparse(self.path).path=='/api/library/video/'+str(ids['clip.mp4'])+'/frame':
                        if faults.get('frame_code'):
                            code=faults.pop('frame_code');return self.send(code,{'error':'Generated frame failure'})
                        if faults.get('frame_delay'):
                            faults['frame_delay']=False;entered.set()
                            if not released.wait(25):return self.send(503,{'error':'Generated frame delay timeout'})
                    if self.path=='/api/library/video/'+str(ids['clip.mp4'])+'/manifest' and faults.get('video_play_code'):
                        code=faults.pop('video_play_code');return self.send(code,{'error':'Generated video playback failure'})
                try:return super().do_GET()
                except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):report['cancelled_response_writes']=report.get('cancelled_response_writes',0)+1
        server.RequestHandlerClass=Quiet;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def prop(identifier,name,value):ui('wait-for',identifier,'-p',name,'--value',str(value),'-t','10000')
        def select(name):
            nonlocal selected_item_id
            selected_item_id=ids[name]
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
            if not args.reader_progress_only:
                with catalog.connect() as db:db.execute('DELETE FROM reader_progress')
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
        def revealed_reader():
            ui('wait-for','ArchiveReaderDialog','-t','5000')
            if not keys('f10','ReaderViewport'):raise RuntimeError('Cannot reveal double-click reader with owned keyboard')
            ui('wait-for','ReaderClose','-t','5000')
        def close_image():
            physical=keys('esc','ImageClose')
            if not physical:ui('invoke','ImageClose')
            ui('wait-for','ImageViewerDialog','--gone','-t','5000')
            return physical
        shown='← → で画像送り · 表示画像は長辺2048pxまで'
        for theme in ('Light','Dark'):
            launch=json.loads(cli('run','src/Aredoko.WinUI','-c','Release','--arch','x64','-p','Platform=x64','-p','SelfContained=true','--no-build','--output-appx-directory',str(target/('layout-'+theme.lower())),'--detach','--json','--args','--ui-theme '+theme.lower()+' --viewer-settings '+str(target/'viewer-settings.json')))
            if launch.get('ProcessScope') not in (None,'local'):raise RuntimeError('Wrong target')
            app_pid=int(launch['ProcessId']);process=kernel32.OpenProcess(0x00100001,False,app_pid)
            if not process:raise RuntimeError('Owned process unavailable')
            for _ in range(60):
                windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'));main=[w for w in windows if 'Aredoko' in w.get('title','') and w.get('title')!='PopupHost']
                if len(main)==1:break
                time.sleep(.1)
            if len(main)!=1:raise RuntimeError('Unique owned main unavailable')
            hwnd=main_hwnd=str(main[0]['hwnd']);ready();resize(1200,820);wait('TxtCount',f'{expected_total} 件')
            if args.animation_only:
                report['audit_scope']='F07/F08/F11 animated GIF/WebP/APNG playback, 54,802KB large APNG bounded handling, and frame cycling across Light/Dark and wide/narrow'
                for aname in ('anim.gif','anim.webp','anim.png','large-54mb.apng'):
                    wait('PreviewStatus'+str(ids[aname]),'画像プレビュー')
                check(theme+' animated GIF/WebP/APNG and 54.8MB APNG list thumbnails loaded',True)
                select('anim.gif');open_image()
                wait('ImageTitle','anim.gif')
                wait('ImageStatus','アニメーション再生中（3フレーム） · ← → で画像送り · 表示画像は長辺2048pxまで')
                wait('ViewerImage','anim.gifの画像（アニメーション 1 / 3）')
                wait('ViewerImage','anim.gifの画像（アニメーション 2 / 3）')
                check(theme+' animated GIF advances frames in native viewer',True)
                shot(theme+'-anim-gif-wide')
                ui('invoke','ImageNext');wait('ImageTitle','anim.png');wait('ImageStatus','アニメーション再生中（3フレーム） · ← → で画像送り · 表示画像は長辺2048pxまで')
                ui('invoke','ImageNext');wait('ImageTitle','anim.webp');wait('ImageStatus','アニメーション再生中（3フレーム） · ← → で画像送り · 表示画像は長辺2048pxまで')
                wait('ViewerImage','anim.webpの画像（アニメーション 2 / 3）')
                check(theme+' animated WebP advances frames in native viewer',True)
                ui('invoke','ImageNext');wait('ImageTitle','large-54mb.apng')
                wait('ImageStatus','アニメーション再生中（3フレーム） · ← → で画像送り · 表示画像は長辺2048pxまで')
                wait('ViewerImage','large-54mb.apngの画像（アニメーション 2 / 3）')
                check(theme+' 54,802KB APNG plays frames smoothly under bounded transfer',report.get('large_apng_size',0)>=54802*1024)
                resize(700,620);shot(theme+'-anim-large-apng-narrow');resize(1200,820)
                close_image()
                close();continue
            if args.feedback_input_only:
                report['audit_scope']='first-run image wheel and mouse X input; settings isolated; no failed folder-batch rerun'
                select('a.png');open_image();wait('ImageTitle','a.png');wait('ImageStatus',shown)
                if not keys('tab','ImageViewport'):raise RuntimeError('Owned image foreground unavailable')
                ui('scroll','ImageViewport','--wheel','-1');wait('ImageTitle','b.png');wait('ImageStatus',shown);time.sleep(.25)
                ui('scroll','ImageViewport','--wheel','1');wait('ImageTitle','a.png');wait('ImageStatus',shown);check(theme+' image actual wheel advances and returns',True)
                tree=json.loads(ui('inspect','--json','--depth','12'));area=next(n for n in nodes(tree) if n.get('automationId')=='ImageViewport')
                x=int(area['x']+area['width']/2);y=int(area['y']+area['height']/2)
                at_point=user32.WindowFromPoint(wintypes.POINT(x,y));point_owner=wintypes.DWORD();user32.GetWindowThreadProcessId(at_point,ctypes.byref(point_owner))
                check('image pointer belongs to owned foreground',point_owner.value==app_pid and user32.GetForegroundWindow()==int(hwnd))
                user32.SetCursorPos(x,y);user32.mouse_event.argtypes=[wintypes.DWORD,wintypes.DWORD,wintypes.DWORD,wintypes.DWORD,ctypes.c_size_t]
                user32.mouse_event(0x0080,0,0,2,0);user32.mouse_event(0x0100,0,0,2,0);wait('ImageTitle','b.png');wait('ImageStatus',shown)
                user32.mouse_event(0x0080,0,0,1,0);user32.mouse_event(0x0100,0,0,1,0);wait('ImageTitle','a.png');wait('ImageStatus',shown);check(theme+' image actual mouse forward/back works',True)
                resize(700,620);shot(theme+'-feedback-image-input');close_image()
                for _ in range(40):
                    history=catalog.search(view='history')['items']
                    if len(history)==2:break
                    time.sleep(.1)
                check(theme+' real image opens persist viewing history',len(history)==2 and history[0]['id']==ids['a.png'])
                ui('invoke','NavHistory','--action','select');ready();wait('TxtCount','2 件');prop('CmbSearchMode','IsEnabled','False');shot(theme+'-history-wide')
                close();continue
            if args.reader_progress_only:
                report['audit_scope']='reading progress: page/direction across reopen and app restart, explicit cover, save/read failure preservation, corrupt page, real generated revision/rescan, cancelled load and drafts'
                shown_book='表示しました。拡大すると細部を確認できます。';saved_text='読書位置を保存しました'
                def reader_saved(number):
                    wait('ReaderPageNumber',number);wait('ReaderStatus',shown_book);prop('ReaderSettings','IsEnabled','True')
                    expected_page=int(number.split(' / ')[0].split('–')[0])-1
                    for _ in range(50):
                        progress=catalog.reader_progress(selected_item_id)['progress']
                        if progress and progress['page']==expected_page:break
                        time.sleep(.1)
                    check(theme+' bookmark persisted without a permanent success caption',progress is not None and progress['page']==expected_page)
                select('book.cbz');ui('set-value','TxtTags','progress-draft');wait('TxtEditStatus','未保存の変更');open_reader()
                if theme=='Light':
                    reader_saved('1 / 5');reader_mode('ReaderRtl');reader_saved('1 / 5');ui('invoke','ReaderNext');reader_saved('2–3 / 5');ui('invoke','ReaderNext');reader_saved('4–5 / 5')
                else:
                    reader_saved('4–5 / 5');check('Dark app restart restores saved page and RTL',catalog.reader_progress(ids['book.cbz'])['progress']['mode']=='rtl');wait('ReaderImage','5ページ');wait('ReaderImageSecond','4ページ')
                audit(theme+'-reader',('ReaderViewport','ReaderSettings','ReaderClose'));resize(700,620);shot(theme+'-progress-spread')
                close_reader();wait('TxtTags','progress-draft');wait('TxtEditStatus','未保存の変更');focus_assert('BtnOpenBook');check(theme+' progress does not save metadata draft',catalog.get(ids['book.cbz'])['tags']==[])
                open_reader();reader_saved('4–5 / 5');wait('ReaderImage','5ページ');check(theme+' reopen restores RTL and page',True)
                if keys('right','ReaderViewport'):reader_saved('2–3 / 5');check(theme+' restored RTL right key returns previous spread',True)
                else:raise RuntimeError('Owned reader direction input unavailable')
                ui('invoke','ReaderReopen');reader_saved('1 / 5');check(theme+' explicit beginning replaces bookmark with cover',catalog.reader_progress(ids['book.cbz'])['progress']['page']==0)
                faults['progress_save_code']=503;ui('invoke','ReaderNext');wait('ReaderPageNumber','2–3 / 5');wait('ReaderStatus',shown_book);wait('ReaderProgressStatus','読書位置を保存できませんでした。設定から保存し直せます。');prop('ReaderSettings','IsEnabled','True');shot(theme+'-progress-save-error');check(theme+' failed save keeps prior bookmark and readable image',catalog.reader_progress(ids['book.cbz'])['progress']['page']==0)
                ui('invoke','ReaderSettings');ui('wait-for','ReaderSaveProgress','-t','5000');ui('invoke','ReaderSaveProgress');reader_saved('2–3 / 5');check(theme+' manual save retry stores current position',catalog.reader_progress(ids['book.cbz'])['progress']['page']==1);close_reader()
                faults['progress_get_code']=503;open_reader();wait('ReaderPageNumber','1 / 5');wait('ReaderStatus',shown_book);wait('ReaderProgressStatus','読書位置を取得できませんでした。先頭から表示します。保存済み位置は移動するまで保持します。');prop('ReaderSettings','IsEnabled','True');shot(theme+'-progress-read-error');check(theme+' failed progress GET cannot overwrite prior position',catalog.reader_progress(ids['book.cbz'])['progress']['page']==1);close_reader();open_reader();reader_saved('2–3 / 5');check(theme+' successful reopen recovers prior position after read failure',True)
                ui('invoke','ReaderReopen');reader_saved('1 / 5');entered.clear();released.clear();faults['reader_delay']=True;ui('invoke','ReaderNext');check(theme+' progress delayed page started',entered.wait(5));close_reader();released.set();time.sleep(.4);check(theme+' cancelled unread page cannot overwrite cover',catalog.reader_progress(ids['book.cbz'])['progress']['page']==0)
                ui('invoke','BtnCloseDetails');ui('wait-for','PrimaryButton','-t','5000');ui('invoke','PrimaryButton');select('broken.zip');open_reader();reader_saved('1 / 4');reader_mode('ReaderLtr');reader_saved('1 / 4');ui('invoke','ReaderNext');wait('ReaderStatus','このページを表示できません。未対応形式・破損・画像サイズを確認してください。');wait('ReaderProgressStatus','前に読めたページの位置を保持しています');shot(theme+'-progress-corrupt');check(theme+' corrupt spread leaves previous successful bookmark',catalog.reader_progress(ids['broken.zip'])['progress']['page']==0);close_reader();open_reader();reader_saved('1 / 4');check(theme+' corrupt book reopens at last readable cover',True);close_reader()
                select('book.cbz');open_reader();reader_saved('1 / 5');reader_mode('ReaderRtl');reader_saved('1 / 5');ui('invoke','ReaderNext');reader_saved('2–3 / 5');old_revision=catalog.reader_progress(ids['book.cbz'])['progress']['revision'];close_reader()
                # Explicit mutation of this generated fixture ONLY, after closing its viewer.
                with zipfile.ZipFile(media/'book.cbz','a') as archive:archive.writestr('revision-'+theme+'.txt','Generated revision reset fixture')
                expected_source=source_digest();catalog.index.scan(root);catalog.sync_index();report.setdefault('controlled_fixture_changes',[]).append({'file':'book.cbz','purpose':'revision reset after real rescan','theme':theme})
                open_reader();reader_saved('1 / 5');shot(theme+'-progress-revision');progress=catalog.reader_progress(ids['book.cbz'])['progress'];check(theme+' changed revision resets page and preserves RTL',progress['revision']!=old_revision and progress['page']==0 and progress['mode']=='rtl')
                ui('invoke','ReaderNext');reader_saved('2–3 / 5');ui('invoke','ReaderNext');reader_saved('4–5 / 5');close_reader();ui('invoke','BtnCloseDetails');close();continue
            if args.video_player_only:
                report['audit_scope']='dedicated native video player window: play/pause/seek/volume/mute, MP4/WMV playback, unsupported MKV(FFV1) and corrupt MP4 guidance, 503 retry, 409 conflict, auto-hide/F10/Escape, and unsaved draft retention across Light/Dark and wide/narrow'
                shown_video='動画を開きました。再生ボタンまたはスペースキーで再生できます。'
                unsupported_video='この動画はWindowsの標準機能では再生できません。未対応の形式・コーデック、破損、または容量制限（2TBまで）を確認してください。'
                def open_video():
                    ui('inspect','BtnOpenVideo','--json');ui('invoke','BtnOpenVideo');ui('wait-for','VideoPlayerDialog','-t','5000')
                    if not keys('f10','VideoViewport'):raise RuntimeError('Cannot reveal video controls with owned keyboard')
                    ui('wait-for','VideoPlayPause','-t','5000')
                def video_title(name):
                    windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
                    matches=[w for w in windows if str(w.get('hwnd'))==str(hwnd)]
                    check(theme+' native video title identifies '+name,len(matches)==1 and matches[0].get('title','').endswith(name))
                def close_video():
                    physical=keys('esc','VideoViewport')
                    if not physical:
                        owner=wintypes.DWORD();user32.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
                        if owner.value!=app_pid:raise RuntimeError('Owned video close target changed')
                        user32.PostMessageW(int(hwnd),0x10,0,0)
                    ui('wait-for','VideoPlayerDialog','--gone','-t','5000')
                    return physical
                select('a.png');prop('BtnOpenImage','IsEnabled','True');prop('BtnOpenVideo','IsEnabled','False');prop('BtnOpenBook','IsEnabled','False')
                select('clip.mp4')
                if not args.video_range_only:ui('wait-for','DetailPreview','-t','10000')
                prop('BtnOpenVideo','IsEnabled','True');prop('BtnOpenImage','IsEnabled','False');prop('BtnOpenBook','IsEnabled','False')
                ui('set-value','TxtTags','video-draft');wait('TxtEditStatus','未保存の変更')
                open_video();wait('VideoStatus',shown_video);video_title('clip.mp4');wait('VideoPosition','0:00 / 0:02')
                audit(theme+'-video',('VideoViewport','VideoPlayPause','VideoSeekBack','VideoSeekForward','VideoMute','VideoVolumeDown','VideoVolumeUp','VideoRetry'))
                shot(theme+'-video-opened-wide')
                ui('invoke','VideoPlayPause');wait('VideoStatus','再生中');wait('VideoPlayPause','一時停止');check(theme+' video play starts playback',True)
                ui('invoke','VideoPlayPause');wait('VideoStatus','一時停止中');wait('VideoPlayPause','再生');check(theme+' video pause stops playback',True)
                if args.video_seek_only:
                    prop('VideoSeek','IsEnabled','True');ui('set-value','VideoSeek','1');wait('VideoPosition','0:01 / 0:02');check(theme+' seek slider changes actual player position',True)
                    if keys('right','VideoSeek'):wait('VideoPosition','0:02 / 0:02');check(theme+' seek slider keyboard moves position',True)
                    ui('set-value','VideoSeek','0');wait('VideoPosition','0:00 / 0:02')
                    ui('hover','VideoSeek','--dwell-time','0');wait('VideoSeekImage','0:01のサムネイル');wait('VideoSeekTime','0:01');wait('VideoPosition','0:00 / 0:02');shot(theme+'-seek-preview-wide');check(theme+' hover preview is independent of playback position',True)
                    ui('hover','VideoViewport','--dwell-time','0');ui('wait-for','VideoSeekPreview','--gone','-t','5000')
                    resize(700,620);ui('hover','VideoSeek','--dwell-time','0');wait('VideoSeekImage','0:01のサムネイル');shot(theme+'-seek-preview-narrow');ui('hover','VideoViewport','--dwell-time','0');resize(1200,820)
                if args.video_seek_only:
                    close_video();open_video();wait('VideoStatus',shown_video);faults['frame_code']=503;ui('hover','VideoSeek','--dwell-time','0');wait('VideoSeekImage','サムネイルを取得できません。シークは利用できます');shot(theme+'-seek-preview-unavailable');prop('VideoPlayPause','IsEnabled','True');ui('set-value','VideoSeek','1');wait('VideoPosition','0:01 / 0:02');check(theme+' unavailable preview leaves seeking enabled',True)
                    ui('hover','VideoViewport','--dwell-time','0');ui('set-value','VideoSeek','0');wait('VideoPosition','0:00 / 0:02')
                ui('invoke','VideoSeekForward');wait('VideoPosition','0:01 / 0:02');prop('VideoSeekBack','IsEnabled','True');check(theme+' video seek forward advances position',True)
                ui('invoke','VideoSeekBack');wait('VideoPosition','0:00 / 0:02');check(theme+' video seek back returns to start',True)
                ui('set-value','VideoVolume','35');wait('VideoVolumeStatus','音量 35%');ui('set-value','VideoVolume','80')
                check(theme+' volume slider synchronizes actual player and buttons',True)
                ui('click','VideoViewport');wait('VideoPlayPause','一時停止');ui('click','VideoViewport');wait('VideoPlayPause','再生')
                check(theme+' canvas click toggles playback and pause',True)
                wait('VideoVolumeStatus','音量 80%')
                ui('invoke','VideoVolumeDown');wait('VideoVolumeStatus','音量 60%')
                ui('invoke','VideoVolumeUp');wait('VideoVolumeStatus','音量 80%')
                ui('invoke','VideoMute');wait('VideoVolumeStatus','消音中（80%）');wait('VideoMute','消音解除')
                ui('invoke','VideoMute');wait('VideoVolumeStatus','音量 80%');wait('VideoMute','消音')
                check(theme+' video volume and mute controls update state',True)
                if keys('ctrl+s','VideoPlayPause'):check(theme+' video player blocks background save',catalog.get(ids['clip.mp4'])['tags']==[])
                resize(700,620);shot(theme+'-video-narrow')
                physical=close_video();wait('TxtTags','video-draft');wait('TxtEditStatus','未保存の変更')
                check(theme+' video player retains unsaved tags',catalog.get(ids['clip.mp4'])['tags']==[])
                if physical:focus_assert('BtnOpenVideo');check(theme+' video Escape restores opener focus',True)
                ui('invoke','BtnCloseDetails');ui('wait-for','PrimaryButton','-t','5000');ui('invoke','PrimaryButton');ready();resize(1200,820)
                select('clip.wmv');open_video();wait('VideoStatus',shown_video);video_title('clip.wmv');wait('VideoPosition','0:00 / 0:02');check(theme+' WMV format opens natively',True);close_video()
                wait('PreviewStatus'+str(ids['unsupported.mkv']),'動画の先頭フレーム')
                select('unsupported.mkv');open_video();wait('VideoStatus',unsupported_video);wait('VideoPosition','—');prop('VideoPlayPause','IsEnabled','False');prop('VideoRetry','IsEnabled','True');shot(theme+'-video-unsupported');check(theme+' unsupported codec shows guidance while thumbnail works',True);close_video()
                select('broken.mp4');open_video();wait('VideoStatus',unsupported_video);prop('VideoRetry','IsEnabled','True');check(theme+' corrupt video shows guidance',True);close_video()
                select('clip.mp4');faults['video_play_code']=503;open_video();wait('VideoStatus','ほかのメディアを読み込み中です。少し待って再試行してください。');shot(theme+'-video-busy')
                ui('invoke','VideoRetry');wait('VideoStatus',shown_video);wait('VideoPosition','0:00 / 0:02');check(theme+' video 503 manual retry succeeds',True);close_video()
                faults['video_play_code']=409;open_video();wait('VideoStatus','ファイルが更新されました。閉じて再スキャンしてから、開き直してください。');wait('VideoPosition','—');check(theme+' video 409 conflict guidance',True);close_video()
                if args.video_seek_only:
                    entered.clear();released.clear();faults['frame_delay']=True;open_video();wait('VideoStatus',shown_video);ui('hover','VideoSeek','--dwell-time','0');check(theme+' delayed seek thumbnail started',entered.wait(5));close_video();select('clip.wmv');open_video();wait('VideoStatus',shown_video);released.set();time.sleep(.3);video_title('clip.wmv');check(theme+' late seek thumbnail cannot replace next player',True);close_video()
                select('clip.mp4');open_video();wait('VideoStatus',shown_video)
                tree=json.loads(ui('inspect','--json','--depth','16'));outer=next(n for n in nodes(tree) if n.get('automationId')=='VideoViewport')
                move_owned(outer,.15,'VideoViewport');ui('wait-for','VideoPlayPause','--gone','-t','10000');shot(theme+'-video-controls-hidden')
                move_owned(outer,.99,'VideoViewport');ui('wait-for','VideoPlayPause','-t','5000');shot(theme+'-video-controls-revealed');check(theme+' video chrome hides and reappears with mouse motion',True)
                move_owned(outer,.15,'VideoViewport');ui('wait-for','VideoPlayPause','--gone','-t','10000')
                if keys('esc','VideoViewport'):
                    ui('wait-for','VideoPlayerDialog','--gone','-t','5000');focus_assert('BtnOpenVideo');check(theme+' video Escape closes while chrome is hidden',True)
                else:raise RuntimeError('Hidden video Escape unavailable')
                if args.video_seek_only:
                    ui('invoke','BtnCloseDetails');ready()
                    wait('PreviewStatus'+str(ids['clip.mp4']),'動画の先頭フレーム')
                    double_click_owned('Preview'+str(ids['clip.mp4']));ui('wait-for','VideoPlayerDialog','-t','5000')
                    if not keys('f10','VideoViewport'):raise RuntimeError('Cannot reveal double-click video controls')
                    video_title('clip.mp4');wait('VideoStatus',shown_video);shot(theme+'-video-double-click')
                    close_video();wait('TxtEditStatus','保存済み');check(theme+' video list thumbnail double click opens native video player',True)
                    ui('set-value','TxtTags','video-dc-draft');wait('TxtEditStatus','未保存の変更')
                    ui('wait-for','DetailPreview','-t','5000');double_click_owned('DetailPreview');ui('wait-for','VideoPlayerDialog','-t','5000')
                    if not keys('f10','VideoViewport'):raise RuntimeError('Cannot reveal detail double-click video controls')
                    video_title('clip.mp4');close_video();wait('TxtTags','video-dc-draft');wait('TxtEditStatus','未保存の変更')
                    check(theme+' video detail thumbnail double click preserves unsaved draft',catalog.get(ids['clip.mp4'])['tags']==[])
                    ui('invoke','BtnCloseDetails');ui('wait-for','PrimaryButton','-t','5000');ui('invoke','PrimaryButton');ready()
                    owner=wintypes.DWORD();user32.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
                    if owner.value!=app_pid:raise RuntimeError('Owned context target changed')
                    if user32.GetForegroundWindow()!=int(hwnd):user32.SetForegroundWindow(int(hwnd));time.sleep(.1)
                    ui('click','Item'+str(ids['clip.mp4']),'--right');time.sleep(.25)
                    windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
                    popup_nodes=[]
                    for w in [w for w in windows if w.get('title')=='PopupHost']+[w for w in windows if str(w.get('hwnd'))==hwnd]:
                        try:popup_nodes.extend(nodes(json.loads(cli('ui','inspect','--json','--depth','14','-w',str(w['hwnd'])))))
                        except RuntimeError:pass
                    has_explorer=any(n.get('automationId')=='ShowInExplorer'+str(ids['clip.mp4']) for n in popup_nodes)
                    has_default=any(n.get('automationId')=='OpenDefault'+str(ids['clip.mp4']) for n in popup_nodes)
                    has_similar=any(n.get('automationId')=='FindSimilar'+str(ids['clip.mp4']) for n in popup_nodes)
                    check(theme+' video context menu exposes common shell actions and video similarity',has_explorer and has_default and has_similar)
                    shot(theme+'-video-context-menu')
                    # F12: Verify time-coded video AI indexing, visual search evidence ('動画フレーム一致（0:01）'), and opening video at the matched timestamp
                    if theme=='Light':
                        from ai_search import revision as ai_rev
                        clip_row=next(r for r in catalog.search()['items'] if r['id']==ids['clip.mp4'])
                        rev_val=ai_rev(clip_row)
                        engine.store.put(ids['clip.mp4'],rev_val,
                            {'text':[0.0,1.0]+[0.0]*(engine.store.dimension-2),'cover':[0.0,1.0]+[0.0]*(engine.store.dimension-2)},
                            [(0,[0.0,1.0]+[0.0]*(engine.store.dimension-2)),(1000,[1.0,0.0]+[0.0]*(engine.store.dimension-2))])
                    ui('click','TxtCount');time.sleep(.2)
                    ui('invoke','CmbSearchMode');time.sleep(.25)
                    for w in [w for w in json.loads(cli('ui','list-windows','-a',app_pid,'--json')) if w.get('title')=='PopupHost']:
                        try:
                            for n in nodes(json.loads(cli('ui','inspect','--json','--depth','12','-w',str(w['hwnd'])))):
                                if n.get('automationId')=='ModeVisual':
                                    cli('ui','invoke','ModeVisual','-w',str(w['hwnd']));break
                        except RuntimeError:pass
                    time.sleep(.2);ui('set-value','TxtQuery','青い場面');time.sleep(.4);ui('invoke','BtnSearch');ready()
                    ui('wait-for','AIEvidence'+str(ids['clip.mp4']),'--value','動画フレーム一致（0:01）','--contains','-t','10000')
                    shot(theme+'-video-ai-timecoded-match')
                    select('clip.mp4');open_video();wait('VideoStatus',shown_video);wait('VideoPosition','0:01 / 0:02')
                    check(theme+' opening video from time-coded AI search starts at matched timestamp 0:01',True)
                    close_video()
                    # Restore ModeLiteral for clean exit
                    ui('invoke','CmbSearchMode');time.sleep(.25)
                    for w in [w for w in json.loads(cli('ui','list-windows','-a',app_pid,'--json')) if w.get('title')=='PopupHost']:
                        try:
                            for n in nodes(json.loads(cli('ui','inspect','--json','--depth','12','-w',str(w['hwnd'])))):
                                if n.get('automationId')=='ModeLiteral':
                                    cli('ui','invoke','ModeLiteral','-w',str(w['hwnd']));break
                        except RuntimeError:pass
                    ui('set-value','TxtQuery','');time.sleep(.4);ui('invoke','BtnSearch');ready()
                    encoder.calls.clear();engine.requests.clear()
                close();continue
            if args.evidence_only:
                report['audit_scope']='per-row SearchEvidence (direct/related/missing), direct-only omission, dirty rollback, and quote/backslash/[ tag search across Light/Dark and wide/narrow'
                def run_query(value,count):
                    ui('set-value','TxtQuery',value);time.sleep(.45);ready();wait('TxtCount',count);ready()
                run_query('東方 巫女','3 件')
                tree=json.loads(ui('inspect','--json','--depth','18'));all_nodes=list(nodes(tree))
                check(theme+' direct-only hit hides redundant SearchEvidence',not any(n.get('automationId')=='SearchEvidence'+str(ids['a.png']) for n in all_nodes))
                ev_b=next((n for n in all_nodes if n.get('automationId')=='SearchEvidence'+str(ids['b.png'])),None)
                ev_c=next((n for n in all_nodes if n.get('automationId')=='SearchEvidence'+str(ids['c.png'])),None)
                check(theme+' mixed direct/related SearchEvidence shown',ev_b is not None and ev_b.get('name')=='入力語で一致：東方 / 関連語で一致：巫女')
                check(theme+' related-only SearchEvidence shown',ev_c is not None and ev_c.get('name')=='関連語で一致：東方、巫女')
                item_a=next(n for n in all_nodes if n.get('automationId')=='Item'+str(ids['a.png']))
                item_b=next(n for n in all_nodes if n.get('automationId')=='Item'+str(ids['b.png']))
                item_c=next(n for n in all_nodes if n.get('automationId')=='Item'+str(ids['c.png']))
                check(theme+' direct hits ordered before related hit',item_a['y']<item_b['y']<item_c['y'])
                shot(theme+'-evidence-related-wide')
                resize(700,620);run_query('東方 未知','3 件')
                tree=json.loads(ui('inspect','--json','--depth','18'));all_nodes=list(nodes(tree))
                ev_a_partial=next((n for n in all_nodes if n.get('automationId')=='SearchEvidence'+str(ids['a.png'])),None)
                ev_c_partial=next((n for n in all_nodes if n.get('automationId')=='SearchEvidence'+str(ids['c.png'])),None)
                check(theme+' partial direct+missing SearchEvidence shown',ev_a_partial is not None and ev_a_partial.get('name')=='入力語で一致：東方 / 一致なし：未知')
                check(theme+' partial related+missing SearchEvidence shown',ev_c_partial is not None and ev_c_partial.get('name')=='関連語で一致：東方 / 一致なし：未知')
                shot(theme+'-evidence-partial-narrow')
                ui('invoke','Item'+str(ids['c.png']),'--action','select');wait('TxtEditStatus','保存済み');ui('set-value','TxtTags','evidence-draft');wait('TxtEditStatus','未保存の変更')
                ui('set-value','TxtQuery','魔法"少女');ui('wait-for','CloseButton','--value','編集を続ける','-t','5000');ui('invoke','CloseButton');ready()
                wait('TxtQuery','東方 未知');wait('TxtTags','evidence-draft');wait('TxtEditStatus','未保存の変更')
                check(theme+' cancelling search keeps unsaved draft and SearchEvidence',catalog.get(ids['c.png'])['tags']==['博麗霊夢',r'C:\textures'])
                ui('invoke','BtnCloseDetails');ui('wait-for','PrimaryButton','-t','5000');ui('invoke','PrimaryButton');ready()
                run_query('魔法"少女','1 件');ui('wait-for','Item'+str(ids['a.png']),'-t','5000');check(theme+' quote tag search finds decoded tag',True)
                run_query(r'C:\textures','1 件');ui('wait-for','Item'+str(ids['c.png']),'-t','5000');check(theme+' backslash tag search finds decoded tag',True)
                run_query('[','0 件');ui('wait-for','TxtEmpty','-t','5000');shot(theme+'-tag-syntax-narrow');check(theme+' JSON bracket syntax does not false-match tags',True)
                close();continue
            if args.video_and_evidence_only:
                report['audit_scope']='native video thumbnails (MP4/MKV/WebM/SAR 8:9/corrupt/503/cancel), per-row SearchEvidence (direct/related/missing), and quote/backslash/[ tag search across Light/Dark and wide/narrow'
                def run_query(value,count):
                    ui('set-value','TxtQuery',value);time.sleep(.45);ready();wait('TxtCount',count);ready()
                wait('PreviewStatus'+str(ids['anamorphic.mp4']),'動画の先頭フレーム')
                wait('PreviewStatus'+str(ids['broken.mp4']),'プレビューなし')
                ui('invoke','Item'+str(ids['anamorphic.mp4']),'--action','select');wait('TxtEditStatus','保存済み');ui('wait-for','DetailPreview','-t','10000')
                prop('BtnOpenImage','IsEnabled','False');prop('BtnOpenBook','IsEnabled','False')
                tree=json.loads(ui('inspect','--json','--depth','18'));all_nodes=list(nodes(tree))
                dp=next(n for n in all_nodes if n.get('automationId')=='DetailPreview')
                check(theme+' SAR 8:9 video preserves 4:3 display aspect in DetailPreview',dp['height']>0 and abs((dp['width']/dp['height'])-(4/3))<=0.06)
                shot(theme+'-video-list-detail')
                double_click_owned('Preview'+str(ids['anamorphic.mp4']));wait('TxtEditStatus','保存済み');ui('wait-for','ImageViewerDialog','--gone','-t','3000');ui('wait-for','ArchiveReaderDialog','--gone','-t','3000')
                check(theme+' video thumbnail double click does not open image or book viewer',True)
                run_query('clip','3 件')
                for vname in ('clip.mp4','clip.mkv','clip.webm'):
                    wait('PreviewStatus'+str(ids[vname]),'動画の先頭フレーム')
                check(theme+' list MP4/MKV/WebM video first-frame statuses',True)
                ui('invoke','BtnLayout');ready()
                for vname in ('clip.mp4','clip.mkv','clip.webm'):wait('PreviewStatus'+str(ids[vname]),'動画の先頭フレーム')
                shot(theme+'-video-grid');check(theme+' grid video thumbnails',True)
                ui('invoke','BtnLayout');ready()
                run_query('broken.mp4','1 件');faults['video_code']=503;ui('invoke','BtnReconnect');ready()
                run_query('clip.mp4','1 件');wait('PreviewStatus'+str(ids['clip.mp4']),'プレビューなし');check(theme+' video 503 falls back cleanly',True)
                ui('invoke','BtnReconnect');ready();wait('PreviewStatus'+str(ids['clip.mp4']),'動画の先頭フレーム');check(theme+' video retry after 503 succeeds',True)
                run_query('broken.mp4','1 件');ui('invoke','BtnReconnect');ready()
                entered.clear();released.clear();faults['video_delay']=True
                run_query('clip','3 件')
                check(theme+' delayed video preview started',entered.wait(5))
                run_query('b.png','1 件');released.set();time.sleep(.4);wait('PreviewStatus'+str(ids['b.png']),'画像プレビュー')
                check(theme+' delayed video preview cancelled on navigation',True)
                run_query('東方 巫女','3 件')
                tree=json.loads(ui('inspect','--json','--depth','18'));all_nodes=list(nodes(tree))
                check(theme+' direct-only hit hides redundant SearchEvidence',not any(n.get('automationId')=='SearchEvidence'+str(ids['a.png']) for n in all_nodes))
                ev_clip=next((n for n in all_nodes if n.get('automationId')=='SearchEvidence'+str(ids['clip.mp4'])),None)
                ev_b=next((n for n in all_nodes if n.get('automationId')=='SearchEvidence'+str(ids['b.png'])),None)
                check(theme+' mixed direct/related SearchEvidence shown',ev_clip is not None and ev_clip.get('name')=='入力語で一致：東方 / 関連語で一致：巫女')
                check(theme+' related-only SearchEvidence shown',ev_b is not None and ev_b.get('name')=='関連語で一致：東方、巫女')
                item_a=next(n for n in all_nodes if n.get('automationId')=='Item'+str(ids['a.png']))
                item_b=next(n for n in all_nodes if n.get('automationId')=='Item'+str(ids['b.png']))
                check(theme+' direct hit ordered before related hit',item_a['y']<item_b['y'])
                shot(theme+'-evidence-related-wide')
                resize(700,620);run_query('東方 未知','3 件')
                tree=json.loads(ui('inspect','--json','--depth','18'));all_nodes=list(nodes(tree))
                ev_a_partial=next((n for n in all_nodes if n.get('automationId')=='SearchEvidence'+str(ids['a.png'])),None)
                ev_b_partial=next((n for n in all_nodes if n.get('automationId')=='SearchEvidence'+str(ids['b.png'])),None)
                check(theme+' partial direct+missing SearchEvidence shown',ev_a_partial is not None and ev_a_partial.get('name')=='入力語で一致：東方 / 一致なし：未知')
                check(theme+' partial related+missing SearchEvidence shown',ev_b_partial is not None and ev_b_partial.get('name')=='関連語で一致：東方 / 一致なし：未知')
                shot(theme+'-evidence-partial-narrow')
                ui('invoke','Item'+str(ids['b.png']),'--action','select');wait('TxtEditStatus','保存済み');ui('set-value','TxtTags','evidence-draft');wait('TxtEditStatus','未保存の変更')
                ui('set-value','TxtQuery','魔法"少女');ui('wait-for','CloseButton','--value','編集を続ける','-t','5000');ui('invoke','CloseButton');ready()
                wait('TxtQuery','東方 未知');wait('TxtTags','evidence-draft');wait('TxtEditStatus','未保存の変更')
                check(theme+' cancelling search keeps unsaved draft and SearchEvidence',catalog.get(ids['b.png'])['tags']==['博麗霊夢',r'C:\textures'])
                ui('invoke','BtnCloseDetails');ui('wait-for','PrimaryButton','-t','5000');ui('invoke','PrimaryButton');ready()
                run_query('魔法"少女','1 件');ui('wait-for','Item'+str(ids['a.png']),'-t','5000');check(theme+' quote tag search finds decoded tag',True)
                run_query(r'C:\textures','1 件');ui('wait-for','Item'+str(ids['b.png']),'-t','5000');check(theme+' backslash tag search finds decoded tag',True)
                run_query('[','0 件');ui('wait-for','TxtEmpty','-t','5000');shot(theme+'-tag-syntax-narrow');check(theme+' JSON bracket syntax does not false-match tags',True)
                close();continue
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
                double_click_owned('Preview'+str(ids['book.cbz']));revealed_reader();wait('ReaderPageNumber','1 / 1');wait('ReaderStatus','表示しました。拡大すると細部を確認できます。');shot(theme+'-double-book');close_reader();check(theme+' CBZ thumbnail opens existing reader',True)
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
        if args.video_range_only:
            spans=[r['span'] for r in report.get('video_ranges',[]) if r['span']]
            widths=[int(r.split('-')[1])-int(r.split('=')[1].split('-')[0])+1 for r in spans]
            offsets=[int(r.split('=')[1].split('-')[0]) for r in spans]
            check('Native video exceeds legacy 64MiB limit',report['large_video_size']>64*1024*1024)
            check('Native codec reads bounded ranges and seeks beyond first byte',bool(widths) and max(widths)<=1024*1024 and max(offsets)>0)
            check('Native player never calls legacy full-file route',all(r['route'].endswith(('/range','/manifest')) for r in report.get('video_ranges',[])))
            report['range_summary']={'requests':len(widths),'max_bytes':max(widths,default=0),'max_offset':max(offsets,default=0)}
        check('No AI inference',not engine.encoder.calls and not engine.requests and not engine.encoder.resident)
        check('Settings unchanged',settings.read_bytes()==settings_before);check('Only explicit generated-book revision changes' if args.reader_progress_only else 'Source bytes and mtimes unchanged',source_digest()==(expected_source if args.reader_progress_only else original));report['pass']=True
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
