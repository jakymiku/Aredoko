"""Material continuous-browse acceptance; generated catalog and owned windows only."""
import ctypes,json,re,time
from pathlib import Path
from ctypes import wintypes
from native_ui_tools import nodes

def audit(ui,cli,tree,shot,report,check,pid,hwnd,cat):
    def extent():
        node=tree().get('TxtPageNumber')
        text=(node or {}).get('name','').replace(',','')
        match=re.fullmatch(r'(\d+)–(\d+) / (\d+)',text)
        # Before the first extension the legacy page label is still visible.
        # A missing/recycling peer is also not evidence of any numeric range.
        return tuple(map(int,match.groups())) if match else None
    def wait_range(predicate):
        last=None
        for _ in range(25):
            current=extent()
            if current is not None:
                last=current
                if predicate(current):
                    report.setdefault('result_ranges',[]).append(current)
                    check('native metadata window bounded',current[1]-current[0]+1<=600)
                    return current
            time.sleep(.15)
        raise AssertionError('Incremental viewport did not advance; last stable range: '+str(last))
    ui('scroll','ItemList','--to','bottom')
    wait_range(lambda value:value[1]>=180)
    # Original60th item remains in the viewport after appending the next block.
    row=cat.search(limit=120)['items'][59]
    ui('invoke','Item'+str(row['id']),'--action','select')
    ui('wait-for','BtnOpenImage','-p','IsEnabled','--value','True','-t','10000')
    ui('invoke','BtnOpenImage')
    viewer=None
    for _ in range(25):
        windows=json.loads(cli('list-windows','-a',pid,'--json'))
        matches=[w for w in windows if w.get('title')=='Aredoko — 画像ビューア']
        if len(matches)==1:viewer=str(matches[0]['hwnd']);break
        time.sleep(.2)
    if not viewer:raise RuntimeError('Owned viewer not found')
    user=ctypes.WinDLL('user32',use_last_error=True);user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(viewer),ctypes.byref(owner))
    check('viewer belongs to test process',owner.value==pid)
    def view(*args):return cli(*args,'-w',viewer)
    view('wait-for','ImagePosition','--value','60 / 745','-t','10000')
    view('invoke','ImageNext');view('wait-for','ImagePosition','--value','61 / 745','-t','10000')
    view('invoke','ImagePrevious');view('wait-for','ImagePosition','--value','60 / 745','-t','10000')
    view('invoke','ImageNext');view('wait-for','ImagePosition','--value','61 / 745','-t','10000')
    view('wait-for','ImageFit','-p','IsEnabled','--value','True','-t','10000')
    view('invoke','ImageClose');ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
    ui('wait-for','generated-060.png','-t','5000')
    returned=json.loads(ui('inspect','--depth','18','--json'))
    check('returned item is shown in right detail pane',any(n.get('name')=='generated-060.png' and n.get('type')=='Text' and n.get('x',0)>800 for n in nodes(returned)))
    check('viewer crosses60/61 both directions and returns selected item',True)
    ui('set-value','TxtTags','continuous-unsaved-draft');ui('invoke','BtnCloseDetails')
    current=wait_range(lambda value:True)
    for _ in range(9):
        if current[1]>=745:break
        previous=current;ui('scroll','ItemList','--to','bottom')
        current=wait_range(lambda value:value[1]>previous[1])
    check('continuous forward reaches last generated result and evicts head',current[1]==745 and current[0]>1)
    shot('continuous-tail')
    for _ in range(9):
        if current[0]==1:break
        previous=current;ui('scroll','ItemList','--to','top')
        current=wait_range(lambda value:value[0]<previous[0])
    check('reverse scroll retrieves first results',current[0]==1)
    ui('invoke','BtnDetails');ui('wait-for','TxtTags','--value','continuous-unsaved-draft','-t','5000')
    check('draft survives extension eviction and reverse scrolling',True)
    ui('invoke','BtnSave');ui('wait-for','TxtTags','-p','IsEnabled','--value','True','-t','20000')
    check('draft saved only explicitly',cat.search(query='continuous-unsaved-draft')['total']==1)
    shot('continuous-return')


def audit_boundary120(ui,cli,tree,shot,report,check,pid,hwnd,cat):
    """One125-item case: realizes120th row using normal native keyboard input."""
    ui('scroll','ItemList','--to','bottom')
    ui('wait-for','TxtPageNumber','--value','125','--contains','-t','10000')
    visible=tree()
    row=next((key for key,value in visible.items() if re.fullmatch(r'Item[0-9]+',key) and not value.get('isOffscreen',True)),None)
    if row is None:raise AssertionError('No visible owned row for keyboard focus')
    # ListView delegates keyboard focus to its realized item. Click that owned
    # item rather than require HasKeyboardFocus on the parent ListView peer.
    ui('click',row);ui('send-keys','end up up up up up','--via','send-input')
    ui('wait-for','BtnOpenImage','-p','IsEnabled','--value','True','-t','7000');ui('invoke','BtnOpenImage')
    viewer=None
    for _ in range(25):
        rows=json.loads(cli('list-windows','-a',pid,'--json'))
        matches=[w for w in rows if w.get('title')=='Aredoko — 画像ビューア']
        if len(matches)==1:viewer=str(matches[0]['hwnd']);break
        time.sleep(.2)
    if viewer is None:raise AssertionError('Owned viewer did not open for boundary test')
    user=ctypes.WinDLL('user32',use_last_error=True);user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    def view(*args):
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(viewer),ctypes.byref(owner))
        if owner.value!=pid:raise AssertionError('Viewer ownership changed')
        return cli(*args,'-w',viewer)
    def shown(position,title):
        view('wait-for','ImagePosition','--value',f'{position} / 125','-t','10000')
        view('wait-for','ImageTitle','--value',title,'-t','5000')
        view('wait-for','ImageFit','-p','IsEnabled','--value','True','-t','10000')
    shown(120,'generated-119.png');check('120th image is decoded before movement',True)
    view('focus','ImageViewport');view('send-keys','f10','--via','send-input')
    view('invoke','ImageNext');shown(121,'generated-120.png')
    path=Path(report['screenshots'][0]).parent/'viewer121.png'
    view('screenshot','--focus','--output',path);report['screenshots'].append(str(path))
    check('120th moves to121st beyond the UI page boundary',True)
    view('invoke','ImagePrevious');shown(120,'generated-119.png')
    check('121st moves back to decoded120th',True)
    view('invoke','ImageClose');ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
    ui('wait-for','generated-119.png','-t','5000')
    check('closing120th restores its right detail title',any(n.get('name')=='generated-119.png' and n.get('type')=='Text' and n.get('x',0)>800 for n in nodes(json.loads(ui('inspect','--depth','18','--json')))))
    shot('boundary120-return')
