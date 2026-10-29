"""Bounded P7 viewer input acceptance; generated media and an owned HWND only.

Requires explicit permission for local foreground/input. No GPU inference,
models, downloads, installed Alpha, ordinary DB, or OS settings are used.
"""
import argparse,ctypes,hashlib,io,json,os,secrets,socket,subprocess,sys,threading,time,traceback,zipfile
from ctypes import wintypes
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'app'),str(REPO/'tools')]
from production import ProductionCatalog
from production_server import production_handler,DisabledAI
from owned_http_server import OwnedHTTPServer
from ai_settings import AIProfileSettings
from wd_tagger import DisabledTagger
from native_ui_tools import nodes
from portable_frontend import inspect_portable


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--keyboard-controls',action='store_true',help='Only generated silent audio controls and image menu keyboard routing')
    parser.add_argument('--inspect-controls',action='store_true',help='With --keyboard-controls, inspect generated player UIA state only; never verify real keys')
    parser.add_argument('--inspect-notices',action='store_true',help='Only compare a generated audio player temporary failure and successful retry, UIA only')
    parser.add_argument('--inspect-autohide',choices=('automatic','always'),help='UIA-only timer behavior after a generated temporary failure/retry')
    args=parser.parse_args();front=args.frontend.resolve();target=args.output.resolve()
    if args.inspect_autohide and not args.inspect_notices:parser.error('--inspect-autohide requires --inspect-notices')
    if args.inspect_notices and not (args.inspect_controls and args.keyboard_controls):parser.error('--inspect-notices requires both control inspection flags')
    if args.inspect_controls and not args.keyboard_controls:parser.error('--inspect-controls requires --keyboard-controls')
    if (os.name!='nt' or target.exists() or not target.is_relative_to(REPO/'data/ai-ui') or
        not (front.is_relative_to(REPO/'dist') or front.is_relative_to(REPO/'data/ai-ui'))):parser.error('Dedicated Windows candidate and new evidence directory required')
    inspect_portable(front);target.mkdir(parents=True);media=target/'media';media.mkdir()
    from PIL import Image,ImageDraw
    report={'pass':False,'checks':[],'screenshots':[],'visual_review':'pending','gpu_inference':False,
            'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
            'frontend_sha256':hashlib.sha256((front/'Aredoko.WinUI.dll').read_bytes()).hexdigest(),'keyboard_controls':args.keyboard_controls,'control_state_only':args.inspect_controls,'physical_keyboard_attempted':False,'keyboard_control_pass':False,'notices_only':args.inspect_notices,'autohide_mode':args.inspect_autohide}
    env={**os.environ,'LOCALAPPDATA':str(target/'user'),'APPDATA':str(target/'user'),
         'WINAPP_UI_WORKFLOW_ID':'aredoko-viewer-input-'+secrets.token_hex(8)}
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.GetForegroundWindow.restype=wintypes.HWND;user.SetForegroundWindow.argtypes=[wintypes.HWND]
    user.WindowFromPoint.argtypes=[wintypes.POINT];user.WindowFromPoint.restype=wintypes.HWND
    user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    proc=cat=server=thread=handler=None;main_hwnd=viewer=None;app_log=None
    def check(name,value):
        report['checks'].append({'name':name,'pass':bool(value)});print(name,bool(value),flush=True)
        if not value:raise AssertionError(name)
    def cli(*arguments):
        result=subprocess.run(['winapp','ui',*map(str,arguments)],cwd=REPO,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=25)
        with (target/'commands.log').open('a',encoding='utf-8') as stream:stream.write(json.dumps({'args':arguments,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr},ensure_ascii=False)+'\n')
        if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        return result.stdout
    def owned(hwnd):
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
        if proc is None or proc.poll() is not None or owner.value!=proc.pid:raise RuntimeError('Owned HWND/PID changed')
    def ui(hwnd,*arguments):owned(hwnd);return cli(*arguments,'-w',str(hwnd))
    def tree(hwnd):return {n['automationId']:n for n in nodes(json.loads(ui(hwnd,'inspect','--depth','18','--json'))) if n.get('automationId')}
    def visible(hwnd,identifier):
        value=tree(hwnd).get(identifier);return value is not None and not value.get('isOffscreen',True)
    def wait(name,predicate,seconds=12):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if predicate():return
            time.sleep(.12)
        raise AssertionError(name)
    def windows():return json.loads(cli('list-windows','-a',proc.pid,'--json'))
    def foreground(hwnd):
        owned(hwnd)
        if user.GetForegroundWindow()!=int(hwnd):user.SetForegroundWindow(int(hwnd))
        if user.GetForegroundWindow()!=int(hwnd) and args.keyboard_controls:
            current=tree(hwnd)
            identifier=next((key for key in ('VideoViewport','ImageViewport') if key in current),None)
            if identifier is not None:
                area=current[identifier];location=wintypes.POINT(round(area['x']+area['width']/2),round(area['y']+area['height']/2))
                owner=wintypes.DWORD();user.GetWindowThreadProcessId(user.WindowFromPoint(location),ctypes.byref(owner))
                # An ordinary click may activate this visible test viewport.
                # Refuse if any other process covers that exact point.
                if owner.value==proc.pid:
                    ui(hwnd,'click',identifier);time.sleep(.15)
        if user.GetForegroundWindow()!=int(hwnd):raise RuntimeError('Owned foreground input unavailable; no fallback to another app')
    def point(hwnd,x,y):
        foreground(hwnd);owner=wintypes.DWORD();user.GetWindowThreadProcessId(user.WindowFromPoint(wintypes.POINT(x,y)),ctypes.byref(owner))
        if owner.value!=proc.pid:raise RuntimeError('Input coordinate outside owned window')
        return f'{x},{y}'
    def bar(hwnd,viewport):
        area=tree(hwnd)[viewport];x=round(area['x']+20);y=round(area['y']+area['height']-8)
        coordinate=point(hwnd,x,y)
        # A documented real pointer gesture in the empty left side of the
        # bottom hotzone. No toolbar button, image action or foreign app hit.
        ui(hwnd,'drag',coordinate,coordinate)
    def shot(name):
        current=tree(viewer);viewport='VideoViewport' if 'VideoViewport' in current else 'ImageViewport' if 'ImageViewport' in current else 'ReaderViewport'
        # Window capture can compose a tooltip with per-window headings. Crop
        # the selected viewport so a tooltip cannot shift the pixel origin.
        path=target/(name+'.png');ui(viewer,'screenshot',viewport,'--output',str(path))
        if not path.is_file():raise RuntimeError('Screenshot not delivered')
        with Image.open(path) as captured:
            expected=current[viewport]
            if abs(captured.width-expected['width'])>2 or abs(captured.height-expected['height'])>2:raise AssertionError('Viewport capture changed scale or origin')
        report['screenshots'].append(str(path));path.with_suffix('.json').write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8')
        return path
    def marker(path):
        with Image.open(path) as image:
            rgb=image.convert('RGB');points=[]
            for y in range(60,rgb.height-65):
                for x in range(20,rgb.width-20):
                    r,g,b=rgb.getpixel((x,y))
                    if r>235 and b>235 and g<30:points.append((x,y))
            if len(points)<9:raise AssertionError('Generated center marker is not visible')
            return [sum(p[axis] for p in points)/len(points) for axis in (0,1)]
    def open_viewer(name,button,prefix):
        nonlocal viewer
        ui(main_hwnd,'invoke','Item'+str(ids[name]),'--action','select')
        if not visible(main_hwnd,'BtnCloseDetails'):ui(main_hwnd,'invoke','BtnDetails')
        ui(main_hwnd,'wait-for',button,'-p','IsEnabled','--value','True','-t','10000');ui(main_hwnd,'invoke',button)
        def locate():
            nonlocal viewer
            rows=[w for w in windows() if w.get('title','').startswith(prefix)]
            if len(rows)!=1:return False
            viewer=str(rows[0]['hwnd']);report.setdefault('viewer_windows',[]).append({'title':rows[0].get('title',''),'hwnd':viewer});return True
        wait('owned viewer opens',locate)
        if not args.inspect_controls:foreground(viewer)
    def close_viewer():
        owned(viewer);user.PostMessageW(int(viewer),0x10,0,0)
        wait('owned viewer closes',lambda:not any(str(w['hwnd'])==viewer for w in windows()))
    try:
        for name,color in [('a-center.png',(35,70,105)),('b-next.png',(55,100,135))]:
            with Image.new('RGB',(2000,1400),color) as image:
                draw=ImageDraw.Draw(image);draw.rectangle((980,680,1020,720),fill=(255,0,255));image.save(media/name)
        with zipfile.ZipFile(media/'book.cbz','w',compression=zipfile.ZIP_STORED) as archive:
            for number in range(5):
                with Image.new('RGB',(1000,700),(35+number*30,80,140)) as image,io.BytesIO() as buffer:
                    image.save(buffer,format='PNG');archive.writestr(f'{number}.png',buffer.getvalue())
        if args.keyboard_controls:
            import wave
            with wave.open(str(media/'silent-controls.wav'),'wb') as audio:
                audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(16000);audio.writeframes(b'\0\0'*16000*20)
        before={p.name:[hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns] for p in media.iterdir()}
        cat=ProductionCatalog(target/'catalog.sqlite');root=cat.add_root(str(media));cat.start_scan(root)
        if cat._worker:cat._worker.join(10)
        ids={item['title']:item['id'] for item in cat.search()['items']}
        profiles=AIProfileSettings(target,target/'ai-settings.json',ai_python=str(target/'missing-python'),models_root=target/'missing-models')
        instance=secrets.token_hex(16);env['AREDOKO_STARTUP_INSTANCE']=instance
        test_token=secrets.token_hex(32)
        handler=production_handler(cat,test_token,DisabledAI(),profiles=profiles,tagger=DisabledTagger(),instance_id=instance,runtime_preferences=target/'launch-settings.json')
        manifest_faults={'fail_next':args.inspect_notices,'injected':0}
        if args.inspect_notices:
            get=handler.do_GET
            route='/api/library/audio/'+str(ids['silent-controls.wav'])+'/manifest'
            def temporary_manifest_failure(self):
                if (self.path==route and self.valid_host() and self.headers.get('X-Aredoko-Token')==test_token and manifest_faults['fail_next']):
                    manifest_faults['fail_next']=False;manifest_faults['injected']+=1
                    return self.send(503,{'error':'Preview workers busy'})
                return get(self)
            handler.do_GET=temporary_manifest_failure
        handler.log_message=lambda *args:None
        server=OwnedHTTPServer(('127.0.0.1',8769),handler,bind_and_activate=False);server.allow_reuse_address=False
        server.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1);server.server_bind();server.server_activate()
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        app_log=(target/'app.log').open('w',encoding='utf-8')
        if args.inspect_controls:(target/'viewer-settings.json').write_text(json.dumps({'version':1,'wheel_up_advances':False,'always_show_controls':args.inspect_autohide!='automatic'}))
        proc=subprocess.Popen([str(front/'Aredoko.WinUI.exe'),'--ui-theme','dark','--viewer-settings',str(target/'viewer-settings.json')],cwd=front,env=env,stdout=app_log,stderr=subprocess.STDOUT)
        report['owned_pid']=proc.pid
        def main_window():
            nonlocal main_hwnd
            rows=[w for w in windows() if w.get('title') and w['title']!='PopupHost']
            if len(rows)!=1:return False
            main_hwnd=str(rows[0]['hwnd']);return True
        wait('owned main window',main_window)
        ui(main_hwnd,'wait-for','Item'+str(ids['a-center.png']),'-t','15000')
        if args.inspect_notices:
            from ui_player_keyboard_audit import audit_notices,audit_autohide
            inspection=audit_autohide if args.inspect_autohide else audit_notices
            observations=inspection(ui,tree,open_viewer,close_viewer,shot,report,lambda:viewer)
            for name,value in observations:check(name,value)
            check('one temporary authenticated manifest failure only',manifest_faults['injected']==1)
        elif args.keyboard_controls:
            from ui_player_keyboard_audit import audit
            observations=audit(ui,tree,open_viewer,close_viewer,foreground,shot,wait,report,lambda:viewer)
            for name,value in observations:check(name,value)
        else:
            open_viewer('a-center.png','BtnOpenImage','Aredoko — 画像ビューア')
            bar(viewer,'ImageViewport')
            ui(viewer,'wait-for','ImageActualSize','-p','IsEnabled','--value','True','-t','15000')
            ui(viewer,'hover','ImageViewport','--dwell-time','0')
            wait('image toolbar hides while pointer remains over image',lambda:not visible(viewer,'ImageToolbar'),seconds=5)
            check('image toolbar hides over the canvas',True);before_zoom=marker(shot('01-fit'))
            bar(viewer,'ImageViewport');wait('bottom hotzone reveals controls',lambda:visible(viewer,'ImageToolbar'))
            check('bottom hotzone reveals image controls',True)
            ui(viewer,'invoke','ImageZoomIn');time.sleep(.3);after_zoom=marker(shot('02-centered-zoom'))
            report['marker_before_zoom']=before_zoom;report['marker_after_zoom']=after_zoom
            check('button zoom preserves the image center',max(abs(a-b) for a,b in zip(before_zoom,after_zoom))<=5)
            area=tree(viewer)['ImageViewport'];x=round(area['x']+area['width']/2+50);y=round(area['y']+area['height']/2+30)
            start=point(viewer,x,y);end=point(viewer,x-80,y-50);ui(viewer,'drag',start,end,'--dwell-ms','100');time.sleep(.25)
            after_pan=marker(shot('03-left-drag'));report['marker_after_pan']=after_pan
            check('left drag moves zoomed image by the pointer displacement',abs(after_pan[0]-after_zoom[0]+80)<=15 and abs(after_pan[1]-after_zoom[1]+50)<=15)
            bar(viewer,'ImageViewport');ui(viewer,'invoke','ImageFit');ui(viewer,'hover','ImageViewport','--dwell-time','0')
            foreground(viewer);ui(viewer,'scroll','ImageViewport','--wheel','-1');ui(viewer,'wait-for','ViewerImage','--value','b-next.pngの画像','-t','10000')
            time.sleep(.25);ui(viewer,'scroll','ImageViewport','--wheel','1');ui(viewer,'wait-for','ViewerImage','--value','a-center.pngの画像','-t','10000')
            check('real wheel advances and returns between images',True);close_viewer()
            open_viewer('book.cbz','BtnOpenBook','Aredoko — 本ビューア');ui(viewer,'wait-for','ReaderImage','--value','1ページ','-t','10000')
            bar(viewer,'ReaderViewport');ui(viewer,'invoke','ReaderSettings');ui(viewer,'wait-for','ViewerLoopPages','-t','5000');ui(viewer,'invoke','ViewerLoopPages')
            ui(viewer,'hover','ReaderViewport','--dwell-time','0');foreground(viewer)
            ui(viewer,'scroll','ReaderViewport','--wheel','1');ui(viewer,'wait-for','ReaderImage','--value','5ページ','-t','10000')
            time.sleep(.25);ui(viewer,'scroll','ReaderViewport','--wheel','-1');ui(viewer,'wait-for','ReaderImage','--value','1ページ','-t','10000')
            check('real wheel wraps both book boundaries with loop enabled',True)
            wait('reader toolbar hides over image',lambda:not visible(viewer,'ReaderToolbar'),seconds=5);check('reader toolbar hides over image',True);shot('04-book-loop-hidden')
            close_viewer();settings=json.loads((target/'viewer-settings.json').read_text(encoding='utf-8'))
            check('loop preference saved only in dedicated settings',settings['loop_book_pages'] is True and settings['always_show_controls'] is False)
        check('generated source hashes and mtimes unchanged',before=={p.name:[hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns] for p in media.iterdir()})
        report['pass']=True
    except Exception:
        report['error']=traceback.format_exc();print(report['error'],flush=True)
        if viewer and proc is not None and proc.poll() is None:
            try:shot('failure')
            except Exception:report['capture_error']=traceback.format_exc()
    finally:
        if proc is not None and proc.poll() is None:
            try:
                if viewer and any(str(w['hwnd'])==viewer for w in windows()):owned(viewer);user.PostMessageW(int(viewer),0x10,0,0);time.sleep(.2)
                if main_hwnd:owned(main_hwnd);user.PostMessageW(int(main_hwnd),0x10,0,0)
                proc.wait(timeout=15)
            except Exception:report['cleanup_error']=traceback.format_exc()
        if server:
            if thread:server.shutdown()
            server.server_close()
        if thread:thread.join(5)
        if handler:
            for resource in (handler.startup_scans,handler.download_jobs,handler.restore_jobs,handler.backup_jobs,handler.thumbnails,handler.results,handler.animations,handler.setup_jobs):resource.close()
        if cat:cat.close()
        if app_log:app_log.close()
        report.update(frontend_exit_code=None if proc is None else proc.poll(),process_still_running=proc is not None and proc.poll() is None)
        report['test_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        try:cli('yield')
        except Exception:pass
    return 0 if report['pass'] and report['frontend_exit_code']==0 and not report['process_still_running'] else 1


if __name__=='__main__':raise SystemExit(main())
