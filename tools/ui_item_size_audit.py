"""Generated-only native acceptance of Explorer-style library display sizing."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import time

from native_ui_tools import nodes


def audit(cli,main,pid,theme,rows,catalog,output,report,check):
    user32=ctypes.WinDLL('user32',use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user32.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
    user32.SetForegroundWindow.argtypes=[wintypes.HWND]
    user32.GetForegroundWindow.restype=wintypes.HWND
    user32.keybd_event.argtypes=[wintypes.BYTE,wintypes.BYTE,wintypes.DWORD,ctypes.c_size_t]
    settings=Path(output)/'viewer-settings.json'
    def owned():
        owner=wintypes.DWORD();user32.GetWindowThreadProcessId(int(main),ctypes.byref(owner))
        if owner.value!=pid:raise RuntimeError('Outside owned test process')
    def owned_foreground():
        handle=user32.GetForegroundWindow();owner=wintypes.DWORD()
        user32.GetWindowThreadProcessId(handle,ctypes.byref(owner))
        return owner.value==pid
    def foreground():
        owned();user32.SetForegroundWindow(int(main))
        # A WinUI flyout can own the foreground PopupHost HWND of this same PID.
        if not owned_foreground():raise RuntimeError('Foreground is outside the owned process')
    def ui(*args):owned();return cli('ui',*args,'-w',main)
    def tree():return {n['automationId']:n for n in nodes(json.loads(ui('inspect','--depth','18','--json'))) if n.get('automationId')}
    def resize(width,height):
        owned()
        if not user32.SetWindowPos(int(main),None,0,0,width,height,0x2|0x4|0x10):raise ctypes.WinError(ctypes.get_last_error())
        time.sleep(.4)
    def shot(name,full=False):
        path=Path(output)/(theme+'-'+name+'.png')
        if path.exists():raise FileExistsError(path)
        ui('screenshot',*(() if full else ('Nav',)),'--output',path)
        check(theme+'/'+name+' screenshot delivered',path.is_file() and path.stat().st_size>0)
        report['screenshots'].append(str(path))
        path.with_suffix('.json').write_text(json.dumps(tree(),ensure_ascii=False,indent=2),encoding='utf-8')
    def dismiss():foreground();ui('send-keys','esc','--via','send-input');time.sleep(.2)
    def slider(value,photo=False):
        ui('invoke','BtnItemSize');ui('wait-for','ItemSizeSlider','-t','5000')
        ui('set-value','ItemSizeSlider',value)
        ui('wait-for','ItemSizeLabel','--value',str(value)+'%','-t','5000')
        if photo:shot('size-control',True)
        dismiss();time.sleep(.2)
    def preview():return tree()['Preview'+str(rows['image.png']['id'])]
    def show_image():ui('scroll-into-view','Item'+str(rows['image.png']['id']));time.sleep(.25)
    def saved(value):
        for _ in range(35):
            if settings.is_file():
                current=json.loads(settings.read_text(encoding='utf-8'))
                if current.get('library_item_scale')==value:
                    check(theme+' size persisted with wheel preference',current['wheel_up_advances'] is True)
                    return
            time.sleep(.1)
        raise AssertionError('Display size not persisted')

    resize(1200,820)
    ui('invoke','BtnItemSize');ui('wait-for','ItemSizeSlider','-t','5000')
    ui('wait-for','ItemSizeLabel','--value',('100%' if theme=='Light' else '160%'),'-t','5000')
    check(theme+' restart loads saved display size',True);dismiss()
    ui('invoke','Item'+str(rows['image.png']['id']),'--action','select')
    slider(60,True);show_image();small=preview();shot('list-small')
    slider(180);show_image();large=preview();shot('list-large')
    check(theme+' list thumbnail dimensions change',large['width']>small['width']*2 and large['height']>small['height']*2)
    ui('invoke','BtnLayout');time.sleep(.3)
    slider(60);show_image();small=tree()['Item'+str(rows['image.png']['id'])];shot('grid-small')
    slider(180);show_image();large=tree()['Item'+str(rows['image.png']['id'])];shot('grid-large')
    check(theme+' grid card width changes',large['width']>small['width']*2)
    resize(700,620);ui('scroll','ItemList','--to','top');time.sleep(.3)
    current=tree();viewport=current['ItemList'];title=current['ItemTitle'+str(rows['audio.wav']['id'])]
    check(theme+' narrow grid first filename fully visible',not title['isOffscreen'] and title['height']>=18 and title['y']>=viewport['y'] and title['y']+title['height']<=viewport['y']+viewport['height'])
    shot('narrow-grid')
    resize(1200,820);slider(100)
    show_image();ui('invoke','BtnDetails');ui('scroll','DetailScroll','--to','bottom')
    draft='サイズ検証-'+theme
    ui('set-value','TxtTags',draft)
    ui('wait-for','BtnSave','-p','IsEnabled','--value','True','-t','5000')
    slider(120)
    ui('wait-for','TxtTags','--value',draft,'-t','5000')
    # Mouse wheel uses the CLI's physical injection at the owned element. Keep
    # Control down only inside this try/finally and refuse another foreground.
    foreground();before=preview()
    user32.keybd_event(0x11,0,0,0)
    try:
        if not owned_foreground():raise RuntimeError('Lost owned foreground before wheel')
        ui('scroll','ItemList','--wheel','1')
    finally:user32.keybd_event(0x11,0,2,0)
    time.sleep(.3)
    ui('invoke','BtnItemSize');ui('wait-for','ItemSizeLabel','--value','140%','-t','5000');dismiss()
    check(theme+' actual Ctrl+wheel increases size',True)
    foreground();ui('scroll','ItemList','--wheel','-1');time.sleep(.2)
    ui('invoke','BtnItemSize');ui('wait-for','ItemSizeLabel','--value','140%','-t','5000');dismiss()
    check(theme+' normal wheel leaves size unchanged',True)
    ui('wait-for','TxtTags','--value',draft,'-t','5000')
    ui('invoke','BtnSave');ui('wait-for','TxtEditStatus','--value','保存しました','-t','10000')
    check(theme+' resizing keeps selected item and dirty metadata',catalog.get(rows['image.png']['id'])['tags']==[draft])
    shot('selection-and-edit')
    ui('invoke','BtnCloseDetails');ui('invoke','BtnItemSize');ui('wait-for','BtnResetItemSize','-t','5000')
    ui('invoke','BtnResetItemSize');ui('wait-for','ItemSizeLabel','--value','100%','-t','5000');dismiss();saved(100)
    check(theme+' reset restores standard size',True)
    if theme=='Light':slider(160);saved(160)
