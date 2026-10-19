"""Native follow-up: original image/page resolution, quiet chrome and real notices."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import time
from native_ui_tools import nodes

def audit(cli,main,pid,theme,rows,catalog,output,report,check):
    user32=ctypes.WinDLL('user32',use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user32.SetForegroundWindow.argtypes=[wintypes.HWND]
    def ui(*args,window=main):
        owner=wintypes.DWORD();user32.GetWindowThreadProcessId(int(window),ctypes.byref(owner))
        if owner.value!=pid:raise RuntimeError('Window outside owned test process')
        return cli('ui',*args,'-w',window)
    def tree(window=main):return {n['automationId']:n for n in nodes(json.loads(ui('inspect','--depth','18','--json',window=window))) if n.get('automationId')}
    def shot(name,window=main,selector=None):
        path=Path(output)/(theme+'-'+name+'.png')
        if path.exists():raise FileExistsError(path)
        ui('screenshot',*([selector] if selector else []),'--output',path,window=window)
        check(theme+'/'+name+' screenshot delivered',path.is_file() and path.stat().st_size>0)
        report['screenshots'].append(str(path))
        path.with_suffix('.json').write_text(json.dumps(tree(window),ensure_ascii=False,indent=2),encoding='utf-8')
    def child(viewport):
        for _ in range(40):
            for window in json.loads(cli('ui','list-windows','-a',pid,'--json')):
                handle=str(window.get('hwnd',''))
                if not handle or handle=='0' or handle==str(main) or window.get('title')=='PopupHost':continue
                if viewport in tree(handle):return handle
            time.sleep(.1)
        raise RuntimeError('Owned viewer not available')
    def select(name):
        current=tree()
        if 'BtnCloseDetails' in current and not current['BtnCloseDetails'].get('isOffscreen',True):ui('invoke','BtnCloseDetails')
        ui('set-value','TxtQuery',name);time.sleep(.7);ui('invoke','BtnSearch')
        ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','15000')
        ui('wait-for','Item'+str(rows[name]['id']),'-t','10000')
        ui('invoke','Item'+str(rows[name]['id']),'--action','select');ui('invoke','BtnDetails')
        ui('wait-for','DetailScroll','-t','5000');ui('scroll','DetailScroll','--to','top')
    def open_viewer(name,button,viewport,delay=False):
        select(name)
        for _ in range(10):
            node=tree().get(button)
            if node and not node.get('isOffscreen',True) and node['height']>=32:break
            ui('scroll','DetailScroll','--direction','down')
        if delay:catalog._ui_test_preview_gate.clear()
        ui('invoke',button);return child(viewport)
    def pin(window,viewport):
        user32.SetForegroundWindow(int(window));ui('focus',viewport,window=window)
        ui('send-keys','tab','--target',viewport,'--via','send-input',window=window)
    def close(window,identifier):
        ui('invoke',identifier,window=window);ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
    def quiet(window,identifiers,toolbar,maxheight):
        current=tree(window)
        check(theme+' '+toolbar+' normal notices absent',all(i not in current or current[i].get('isOffscreen',True) for i in identifiers))
        check(theme+' '+toolbar+' compact height',current[toolbar]['height']<=maxheight)
    def actual(window,button,zoom,image,dimensions,fit):
        raw=ui('get-property',image,'-p','HelpText','--json',window=window)
        check(theme+' '+image+' decoded original dimensions',dimensions in raw)
        report.setdefault('decoded_dimensions',[]).append({'theme':theme,'image':image,'uia':raw})
        ui('invoke',button,window=window);ui('wait-for',zoom,'--value','倍率 100%','-t','5000',window=window)
        check(theme+' '+button+' reports 100 percent',True)
        bounds=tree(window)[image];expected=[int(part.strip()) for part in dimensions.split('x')]
        exact=abs(bounds['width']-expected[0])<2 and abs(bounds['height']-expected[1])<2
        report.setdefault('actual_size_geometry',[]).append({'theme':theme,'image':image,'bounds':bounds,'matches_source_pixels':exact})
        if exact:check(theme+' '+image+' physical bounds match source pixels',True)
        else:report.setdefault('unverified_cases',[]).append(theme+' '+image+' UIA bounds clipped; physical pixel geometry not asserted')
        ui('invoke',fit,window=window)

    image=open_viewer('image.png','BtnOpenImage','ImageViewport',delay=True)
    try:
        ui('wait-for','ImageStatus','--value','画像を読み込んでいます…','-t','5000',window=image)
        check(theme+' loading zoom is not NaN','NaN' not in tree(image)['ImageZoomStatus']['name'])
        shot('image-loading',image,'ImageViewerDialog')
    finally:catalog._ui_test_preview_gate.set()
    ui('wait-for','ImageActualSize','-p','IsEnabled','--value','True','-t','15000',window=image);pin(image,'ImageViewport')
    actual(image,'ImageActualSize','ImageZoomStatus','ViewerImage','6144 x 4096','ImageFit')
    quiet(image,('ImageStatus',),'ImageToolbar',64);shot('image-original-fit',image,'ImageViewerDialog');close(image,'ImageClose')

    broken=open_viewer('broken.jpg','BtnOpenImage','ImageViewport');pin(broken,'ImageViewport')
    ui('wait-for','ImageRetry','-p','IsEnabled','--value','True','-t','10000',window=broken)
    check(theme+' image failure remains visible',not tree(broken)['ImageStatus']['isOffscreen'])
    shot('image-error',broken,'ImageViewerDialog');close(broken,'ImageClose')

    book=open_viewer('book.cbz','BtnOpenBook','ReaderViewport');pin(book,'ReaderViewport')
    ui('wait-for','ReaderReopen','-p','IsEnabled','--value','True','-t','15000',window=book)
    ui('invoke','ReaderReopen',window=book)
    ui('wait-for','ReaderActualSize','-p','IsEnabled','--value','True','-t','15000',window=book)
    actual(book,'ReaderActualSize','ReaderZoomStatus','ReaderImage','4096 x 3072','ReaderFit')
    check(theme+' reader position still saved',catalog.reader_progress(rows['book.cbz']['id'])['progress']['page']==0)
    quiet(book,('ReaderStatus','ReaderProgressStatus'),'ReaderToolbar',64);shot('book-original-fit',book,'ArchiveReaderDialog')
    save=catalog.save_reader_progress
    def unavailable(*args,**kwargs):raise ValueError('Generated save failure')
    catalog.save_reader_progress=unavailable
    try:
        ui('invoke','ReaderNext',window=book)
        ui('wait-for','ReaderProgressStatus','--value','保存できません','--contains','-t','10000',window=book)
        check(theme+' failed reading position keeps previous record',catalog.reader_progress(rows['book.cbz']['id'])['progress']['page']==0)
        shot('book-save-warning',book,'ArchiveReaderDialog')
    finally:catalog.save_reader_progress=save
    ui('invoke','ReaderSettings',window=book);ui('wait-for','ReaderSaveProgress','-t','5000',window=book);ui('invoke','ReaderSaveProgress',window=book)
    ui('wait-for','ReaderSettings','-p','IsEnabled','--value','True','-t','10000',window=book)
    check(theme+' manual save retry succeeds',catalog.reader_progress(rows['book.cbz']['id'])['progress']['page']==1)
    quiet(book,('ReaderStatus','ReaderProgressStatus'),'ReaderToolbar',64);close(book,'ReaderClose')

    for name,is_audio in (('audio.wav',True),('clip.mp4',False)):
        handle=open_viewer(name,'BtnOpenAudio' if is_audio else 'BtnOpenVideo','VideoViewport');pin(handle,'VideoViewport')
        ui('wait-for','VideoSeek','-p','IsEnabled','--value','True','-t','15000',window=handle)
        quiet(handle,('VideoStatus',),'VideoToolbar',110)
        if not is_audio:
            ui('invoke','VideoPlayPause',window=handle)
            ui('wait-for','VideoPlayPause','--value','一時停止','-t','5000',window=handle)
            quiet(handle,('VideoStatus',),'VideoToolbar',110)
            ui('invoke','VideoPlayPause',window=handle)
        shot('audio-quiet' if is_audio else 'video-quiet',handle,'AudioPlayerDialog' if is_audio else 'VideoPlayerDialog');close(handle,'VideoClose')
    ui('invoke','BtnCloseDetails');ui('invoke','NavFolders');ui('wait-for','TxtFolderSelectionSummary','-t','10000')
    check(theme+' folder guidance uses plain Japanese',tree()['TxtFolderSelectionSummary']['name']=='フォルダを選ぶと、まとめて検索や設定ができます。')
    shot('folders-plain-copy',selector='Nav')
