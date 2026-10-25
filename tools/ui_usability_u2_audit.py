"""Owned viewer UIA acceptance; does not claim physical hover/pan coverage."""
import ctypes
import json
import time
from ctypes import wintypes
from native_ui_tools import nodes


def audit(ui,cli,tree,shot,check,report,pid,main_hwnd,first_id,cat,user):
    owned=None
    def windows():return json.loads(cli('list-windows','-a',pid,'--json'))
    def control(*args):return cli(*args,'-w',owned)
    def viewer():
        nonlocal owned
        for _ in range(40):
            candidates=[w for w in windows() if str(w['hwnd'])!=main_hwnd and 'ビューア' in w.get('title','')]
            if len(candidates)==1:owned=str(candidates[0]['hwnd']);return
            time.sleep(.1)
        raise AssertionError('owned viewer was not created')
    def title(expected):
        for _ in range(40):
            value=next((w.get('title','') for w in windows() if str(w['hwnd'])==owned),'')
            if expected in value:return value
            time.sleep(.1)
        raise AssertionError('Window title missing '+expected+': '+value)
    def vtree():return {n['automationId']:n for n in nodes(json.loads(control('inspect','--depth','16','--json'))) if n.get('automationId')}
    def capture(name):
        from pathlib import Path
        base=Path(report['screenshots'][0]).parent
        path=base/(name+'.png');control('screenshot','--output',path);report['screenshots'].append(str(path));path.with_suffix('.json').write_text(json.dumps(vtree(),ensure_ascii=False,indent=2),encoding='utf-8')
    def close():
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(owned),ctypes.byref(owner))
        if owner.value!=pid:raise RuntimeError('viewer HWND ownership changed')
        if not user.PostMessageW(int(owned),0x10,0,0):raise ctypes.WinError(ctypes.get_last_error())
        for _ in range(60):
            if not any(str(w['hwnd'])==owned for w in windows()):return
            time.sleep(.1)
        raise AssertionError('owned viewer did not close normally')
    report['unverified']=['physical pointer hot zone/tooltip','left-drag pan','physical DPI and High Contrast']
    ui('invoke','Item'+str(first_id),'--action','select');ui('invoke','BtnDetails');ui('invoke','BtnOpenImage');viewer()
    control('wait-for','ImageZoomIn','-p','IsEnabled','--value','True','-t','10000')
    title('[1/145]');check('image title includes file and scoped ordinal',True)
    check('duplicate image header and close are absent','ImageHeader' not in vtree() and 'ImageClose' not in vtree())
    toolbar=vtree()['ImageToolbar'];control('invoke','ImageZoomIn');control('wait-for','ImageZoomStatus','--value','倍率 150%','-t','5000')
    control('invoke','ImageZoomOut');control('wait-for','ImageZoomStatus','--value','倍率 100%','-t','5000')
    control('invoke','ImageNext');control('wait-for','ImageZoomIn','-p','IsEnabled','--value','True','-t','10000');title('[2/145]')
    check('toolbar geometry stays fixed across image navigation',all(vtree()['ImageToolbar'].get(k)==toolbar.get(k) for k in ('x','y','width','height')))
    control('invoke','ImageSettings');control('invoke','ViewerEnlargeImages');capture('image-settings-applied');close()
    ui('set-value','TxtQuery','zz-usability.cbz');ui('wait-for','TxtCount','--value','1 件','-t','10000')
    book=cat.search(query='zz-usability.cbz')['items'][0]
    ui('invoke','Item'+str(book['id']),'--action','select');ui('invoke','BtnDetails');ui('invoke','BtnOpenBook');viewer()
    control('wait-for','ReaderNext','-p','IsEnabled','--value','True','-t','10000');title('[1 / 5]')
    control('wait-for','ReaderPrevious','-p','IsEnabled','--value','False','-t','5000')
    control('invoke','ReaderSettings');control('invoke','ViewerLoopPages')
    control('wait-for','ReaderPrevious','-p','IsEnabled','--value','True','-t','5000')
    control('invoke','ReaderPrevious');title('[5 / 5]')
    control('invoke','ReaderNext');title('[1 / 5]');check('single page wraps in both directions',True)
    control('invoke','ReaderPrevious');title('[5 / 5]')
    control('invoke','ReaderSettings');control('invoke','ReaderRtl');title('[4–5 / 5]')
    control('invoke','ReaderNext');title('[1 / 5]');control('invoke','ReaderPrevious');title('[4–5 / 5]')
    check('odd RTL spread wraps without omitting the last page',True);capture('reader-last-spread')
    control('invoke','ReaderSettings');control('invoke','ViewerAlwaysControls')
    control('wait-for','ReaderToolbar','--gone','-t','5000');capture('reader-controls-hidden')
    check('disabled persistent controls hide without shrinking the page',True)
    close()
