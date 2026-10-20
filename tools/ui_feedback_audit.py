"""Generated-media overnight feedback acceptance; scoped owned HWNDs only."""
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
    user32.GetForegroundWindow.restype=wintypes.HWND
    def ui(*args,window=main):
        owner=wintypes.DWORD();user32.GetWindowThreadProcessId(int(window),ctypes.byref(owner))
        if owner.value!=pid:raise RuntimeError('UI target is not the owned process')
        return cli('ui',*args,'-w',window)
    def tree(window=main):return {n['automationId']:n for n in nodes(json.loads(ui('inspect','--depth','18','--json',window=window))) if n.get('automationId')}
    def shot(name,window=main):
        path=Path(output)/(theme+'-'+name+'.png')
        if path.exists():raise FileExistsError(path)
        ui('screenshot','--output',path,window=window);report['screenshots'].append(str(path))
        check(theme+'/'+name+' screenshot',path.is_file())
        path.with_suffix('.json').write_text(json.dumps(tree(window),ensure_ascii=False,indent=2),encoding='utf-8')
        return path
    def visible(t,identifier):return identifier in t and not t[identifier].get('isOffscreen',True)
    def close_details():
        if visible(tree(),'BtnCloseDetails'):ui('invoke','BtnCloseDetails')
    def select(name):
        close_details();ui('set-value','TxtQuery',name);time.sleep(.45);ui('invoke','BtnSearch')
        ui('wait-for','Item'+str(rows[name]['id']),'-t','10000')
        ui('invoke','Item'+str(rows[name]['id']),'--action','select');ui('invoke','BtnDetails')
        ui('wait-for','TxtTags','-t','5000');ui('scroll','DetailScroll','--to','top')
    def child(identifier):
        for _ in range(40):
            for w in json.loads(cli('ui','list-windows','-a',pid,'--json')):
                hwnd=str(w.get('hwnd',''))
                if hwnd and hwnd!=str(main) and w.get('title')!='PopupHost' and identifier in tree(hwnd):return hwnd
            time.sleep(.1)
        raise RuntimeError('No owned viewer '+identifier)
    def keys(sequence,identifier):
        user32.SetForegroundWindow(int(main));ui('focus',identifier)
        if user32.GetForegroundWindow()!=int(main):raise RuntimeError('Foreground permission refused for owned window')
        ui('send-keys',sequence,'--via','send-input')

    initial=tree()
    check(theme+' no idle result footer',not visible(initial,'StatusBar'))
    check(theme+' no all-folders dropdown',not visible(initial,'CmbSearchRoot'))
    check(theme+' no inactive scope badge',not visible(initial,'TxtActiveSearchScope'))
    select('image.png')
    check(theme+' reviewed control retired',not visible(tree(),'ChkReviewed'))
    original=catalog.get(rows['image.png']['id']);desired=not original['favorite']
    ui('set-value','TxtTags','unsaved-draft');ui('invoke','ChkFavorite','--action','toggle')
    for _ in range(40):
        current=catalog.get(rows['image.png']['id'])
        if current['favorite']==desired:break
        time.sleep(.1)
    check(theme+' favorite immediately saved',current['favorite']==desired)
    check(theme+' favorite does not save tag draft',current['tags']==original['tags'])
    ui('wait-for','TxtTags','--value','unsaved-draft','-t','3000')
    ui('set-value','TxtTags',', '.join(original['tags']))
    close_details();ui('set-value','TxtQuery','');time.sleep(.45);ui('invoke','BtnSearch')
    ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
    ui('invoke','BtnLayout');ui('invoke','BtnItemSize');ui('set-value','ItemSizeSlider','60')
    # Close the flyout with targeted physical input, after owned focus proof.
    keys('esc','ItemSizeSlider');time.sleep(.6)
    small=tree();first=[n for k,n in small.items() if k.startswith('ItemTitle') and not n.get('isOffscreen',True)]
    check(theme+' small tile layout visible',len(first)>=4)
    def columns(t):
        titles=[n for k,n in t.items() if k.startswith('ItemTitle') and not n.get('isOffscreen',True)]
        top=min(n['y'] for n in titles)
        return sum(abs(n['y']-top)<2 for n in titles)
    small_columns=columns(small)
    shot('tiles')
    ui('invoke','BtnItemSize');ui('set-value','ItemSizeSlider','180');keys('esc','ItemSizeSlider');time.sleep(.5)
    check(theme+' resizing changes visible column count',columns(tree())<small_columns)
    shot('large-tiles')
    ui('invoke','BtnItemSize');ui('set-value','ItemSizeSlider','60');keys('esc','ItemSizeSlider');time.sleep(.5)
    ui('invoke','BtnSettings');ui('wait-for','SettingsTheme','-t','5000')
    keys('home','SettingsTheme')
    keys('down','SettingsTheme')
    if theme=='Light':keys('down','SettingsTheme')
    preferences=Path(output)/'viewer-settings.json'
    enlarged=preferences.exists() and json.loads(preferences.read_text(encoding='utf-8')).get('enlarge_small_images',False)
    if not enlarged:ui('invoke','SettingsEnlargeImages','--action','toggle')
    ui('invoke','SettingsSave');ui('wait-for','SettingsStatus','--contains','--value','保存しました','-t','3000')
    shot('settings')
    ui('send-keys','esc')
    for name in ('moving.gif','moving.apng','book.cbz'):
        select(name);started=time.monotonic();ui('invoke','BtnOpenBook' if name.endswith('.cbz') else 'BtnOpenImage')
        viewport='ReaderViewport' if name.endswith('.cbz') else 'ImageViewport'
        viewer=child(viewport)
        ui('wait-for','ReaderZoomIn' if name.endswith('.cbz') else 'ImageZoomIn','-p','IsEnabled','--value','True','-t','15000',window=viewer)
        report.setdefault('viewer_timings',[]).append({'theme':theme,'item':name,'uia_ready_seconds':time.monotonic()-started,'includes_cli_overhead':True})
        if name.endswith('.cbz'):
            # Both themes share the catalog: a saved position may already be page 2.
            current_label=tree(viewer)['ReaderPageNumber']['name']
            current_page,total_pages=(int(part.strip()) for part in current_label.split('/'))
            step=1 if current_page<total_pages else -1
            ui('invoke','ReaderNext' if step>0 else 'ReaderPrevious',window=viewer)
            ui('wait-for','ReaderPageNumber','--value',f'{current_page+step} / {total_pages}','-t','5000',window=viewer)
        else:
            time.sleep(1.5)
        path=shot(name.replace('.','-'),window=viewer)
        if not name.endswith('.cbz'):
            from PIL import Image
            with Image.open(path) as snap:
                color=snap.convert('RGB').getpixel((snap.width//2,snap.height//2))
                check(theme+'/'+name+' center is a visible animation frame',max(color)>70)
        ui('send-keys','esc',window=viewer)
    close_details();ui('invoke','NavFolders');ui('wait-for','FolderItem1','-t','5000')
    ui('click','FolderItem1');ui('wait-for','TxtFolderTargetTitle','-t','5000')
    check(theme+' folder click opens visible settings',visible(tree(),'TxtFolderTargetTitle'))
    shot('folder-selection')
    ui('invoke','BtnCloseFolderDetails') if visible(tree(),'BtnCloseFolderDetails') else None
    ui('invoke','OpenFolder1');ui('wait-for','TxtActiveSearchScope','-t','5000')
    check(theme+' folder filter has adjacent clear',visible(tree(),'BtnResetAllFolders'))
    ui('invoke','BtnResetAllFolders');time.sleep(.4)
    check(theme+' clearing folder filter hides badge',not visible(tree(),'TxtActiveSearchScope'))
