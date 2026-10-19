"""Common daily WinUI flows, using the verified process/fixtures of the detail harness."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import time

from native_ui_tools import nodes


def audit(cli, main, pid, theme, rows, catalog, output, report, check):
    user32=ctypes.WinDLL('user32',use_last_error=True)
    user32.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
    user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    user32.SetForegroundWindow.argtypes=[wintypes.HWND]

    def ui(*args,window=main):return cli('ui',*args,'-w',window)
    def tree(window=main):
        raw=json.loads(ui('inspect','--depth','18','--json',window=window))
        return {n['automationId']:n for n in nodes(raw) if n.get('automationId')}
    def owned(window):
        owner=wintypes.DWORD();user32.GetWindowThreadProcessId(int(window),ctypes.byref(owner))
        if owner.value!=pid:raise RuntimeError('UI action target is outside the owned process')
    def resize(width,height,window=main):
        owned(window)
        if not user32.SetWindowPos(int(window),None,0,0,width,height,0x2|0x4|0x10):raise ctypes.WinError(ctypes.get_last_error())
        time.sleep(.4)
    def shot(name,window=main,selector=None):
        path=Path(output)/(theme+'-'+name+'.png')
        if path.exists():raise FileExistsError(path)
        ui('screenshot',*([selector] if selector else []),'--output',path,window=window)
        check(theme+'/'+name+' screenshot delivered',path.is_file() and path.stat().st_size>0)
        report['screenshots'].append(str(path))
        (Path(output)/(theme+'-'+name+'-tree.json')).write_text(
            json.dumps(tree(window),ensure_ascii=False,indent=2),encoding='utf-8')
    def fits(name,identifiers,window=main,minimum_width=32):
        current=tree(window);rect=wintypes.RECT();owned(window)
        if not user32.GetWindowRect(int(window),ctypes.byref(rect)):raise ctypes.WinError(ctypes.get_last_error())
        failed=[]
        for identifier in identifiers:
            node=current.get(identifier)
            width=minimum_width.get(identifier,32) if isinstance(minimum_width,dict) else minimum_width
            if not node or node.get('isOffscreen',True) or node['width']<width or node['height']<30 or not (
                node['x']>=rect.left and node['y']>=rect.top and
                node['x']+node['width']<=rect.right and node['y']+node['height']<=rect.bottom):failed.append(identifier)
        good=not failed
        report['checks'].append({'name':theme+'/'+name+' controls fit','pass':good})
        report.setdefault('layout_observations',[]).append({'theme':theme,'name':name,'failed':failed,
            'controls':{identifier:current.get(identifier) for identifier in identifiers}})
        print(json.dumps({'layout':theme+'/'+name,'pass':good,'failed':failed}),flush=True)
        return good
    def ready():ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','15000')
    def close_details():
        current=tree()
        if current.get('BtnCloseDetails') and not current['BtnCloseDetails'].get('isOffscreen',True):ui('invoke','BtnCloseDetails')
    def all_items():
        close_details();ui('invoke','NavAll');ready();ui('set-value','TxtQuery','');time.sleep(.65);ui('invoke','BtnSearch');ready()
        ui('wait-for','Item'+str(rows['image.png']['id']),'-t','10000')
    def selected(name):
        close_details();ui('invoke','Item'+str(rows[name]['id']),'--action','select');ui('invoke','BtnDetails')
        ui('wait-for','DetailScroll','-t','5000');ui('scroll','DetailScroll','--to','top')
    def settings():
        close_details();ui('invoke','BtnSettings');ui('wait-for','SettingsWheel','-t','5000')
    def child_with(identifier):
        for _ in range(50):
            windows=json.loads(cli('ui','list-windows','-a',pid,'--json'))
            # A child native viewer is independent from PopupHost tooltips.
            for candidate in windows:
                handle=str(candidate.get('hwnd',''))
                if not handle or handle=='0' or handle==str(main):continue
                if candidate.get('title')=='PopupHost':continue
                current=tree(handle)
                if identifier in current:
                    owned(handle);return handle
            time.sleep(.1)
        raise RuntimeError('No owned child window containing '+identifier)
    def pin_chrome(window,viewport):
        owned(window)
        # Physical keyboard input is confined to the verified foreground viewer.
        if not user32.SetForegroundWindow(int(window)):raise RuntimeError('Owned viewer foreground activation refused')
        ui('focus',viewport,window=window)
        ui('send-keys','tab','--target',viewport,'--via','send-input',window=window)
    def open_viewer(item,opener,viewport):
        all_items();selected(item)
        for _ in range(10):
            n=tree().get(opener)
            if n and not n.get('isOffscreen',True) and n['height']>=32:break
            ui('scroll','DetailScroll','--direction','down')
        ui('wait-for',opener,'-p','IsEnabled','--value','True','-t','5000');ui('invoke',opener)
        handle=child_with(viewport);pin_chrome(handle,viewport)
        return handle
    def close_viewer(handle,identifier):
        ui('invoke',identifier,window=handle)
        ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
        check(theme+'/'+identifier+' restores main window',True)

    all_items();resize(1200,820)
    ui('wait-for','BtnLayout','-t','5000')
    check(theme+' wide navigation expanded',tree()['NavAll']['width']>=140)
    fits('wide-list',('TxtQuery','BtnSearch','CmbKind','CmbSearchMode','BtnLayout','BtnRoots'),minimum_width={'TxtQuery':180})
    shot('wide-list',selector='Nav')
    ui('invoke','BtnLayout');ready()
    fits('wide-grid',('Item'+str(rows['image.png']['id']),'Item'+str(rows['second.png']['id'])) )
    shot('wide-grid',selector='Nav')
    selected('image.png');ui('scroll','DetailScroll','--to','bottom')
    ui('wait-for','TxtTags','-t','5000');ui('set-value','TxtTags','画面検証-'+theme)
    ui('wait-for','BtnSave','-p','IsEnabled','--value','True','-t','5000');ui('invoke','BtnSave')
    ui('wait-for','TxtEditStatus','--value','保存しました','-t','10000')
    check(theme+' edit/save reaches isolated catalog',catalog.get(rows['image.png']['id'])['tags']==['画面検証-'+theme])
    fits('wide-details',('TxtTags','BtnSave','BtnCloseDetails'))
    shot('wide-details',selector='Nav')
    close_details();resize(700,620)
    check(theme+' resize returns compact navigation',tree()['NavAll']['width']<=48)
    fits('narrow-grid',('TxtQuery','BtnSearch','CmbKind','CmbSearchMode','BtnLayout','BtnRoots'),minimum_width={'TxtQuery':120})
    shot('narrow-grid',selector='Nav')

    settings()
    fits('narrow-settings',('SettingsWheel','SettingsSave','BtnAIIndex','BtnRelatedTerms','BtnBackupGuide','BtnDiagnostics','CloseButton'))
    shot('narrow-settings')
    ui('invoke','CloseButton');ready()
    ui('invoke','NavFolders');ui('wait-for','FolderList','-t','10000')
    header=('TxtFolderFilter','CmbFolderState','BtnFolderLayout','BtnToggleAddFolder','BtnBackToLibrary')
    header_ok=fits('narrow-folders',header,minimum_width={'TxtFolderFilter':120})
    fits('narrow-folder-actions',('BtnSearchSelectedFolders','BtnEditSelectedFolders','BtnUnregisterSelectedFolders','BtnSearchAllFolders'))
    shot('narrow-folders',selector='Nav')
    if header_ok:
        ui('invoke','BtnToggleAddFolder');ui('wait-for','RootPath','-t','5000')
        ui('scroll','FolderAddScroll','--to','top')
        fits('narrow-folder-add-top',('RootPath','ChooseFolder'))
        shot('narrow-folder-add-top',selector='Nav')
        for identifier in ('AddRootExcludes','AddRootInitialShelf','AddRootNewShelf','RootRecursive','RootFolderBooks','AddRoot'):
            ui('scroll-into-view',identifier)
            fits('narrow-folder-add-'+identifier,(identifier,))
        shot('narrow-folder-add-bottom',selector='Nav');ui('invoke','BtnToggleAddFolder')
    else:report.setdefault('unverified_cases',[]).append(theme+' narrow folder add skipped because header was clipped')
    resize(1200,820)
    fits('wide-folders',header,minimum_width={'TxtFolderFilter':120})
    shot('wide-folders',selector='Nav')
    all_items();resize(700,620)

    image=open_viewer('image.png','BtnOpenImage','ImageViewport')
    ui('wait-for','ImageNext','-p','IsEnabled','--value','True','-t','5000',window=image)
    ui('invoke','ImageNext',window=image)
    ui('wait-for','ImagePosition','--value','2 / 2','-t','10000',window=image)
    check(theme+' image viewer navigates search results',True)
    fits('image-viewer',('ImageClose','ImageNext','ImageZoomIn','ImageFit'),window=image)
    shot('image-viewer',window=image,selector='ImageViewerDialog');close_viewer(image,'ImageClose')

    book=open_viewer('book.cbz','BtnOpenBook','ReaderViewport')
    ui('invoke','ReaderSettings',window=book)
    ui('wait-for','ReaderRtl','-t','5000',window=book);ui('invoke','ReaderRtl',window=book)
    pin_chrome(book,'ReaderViewport')
    ui('wait-for','ReaderPageNumber','--value','3','--contains','-t','10000',window=book)
    check(theme+' reader display settings reachable',True)
    fits('book-viewer',('ReaderClose','ReaderSettings','ReaderNext','ReaderFit'),window=book)
    shot('book-viewer',window=book,selector='ArchiveReaderDialog');close_viewer(book,'ReaderClose')

    audio=open_viewer('audio.wav','BtnOpenAudio','VideoViewport')
    ui('wait-for','VideoSeek','-p','IsEnabled','--value','True','-t','10000',window=audio)
    fits('audio-player',('VideoClose','VideoPlayPause','VideoSeek','VideoVolume'),window=audio)
    shot('audio-player',window=audio,selector='AudioPlayerDialog');close_viewer(audio,'VideoClose')
