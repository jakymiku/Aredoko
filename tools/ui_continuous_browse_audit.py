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


def audit_tail(ui,cli,tree,shot,report,check,pid,hwnd,cat):
    """Outstanding P3 case: physical final row, resizing and bounded native cards."""
    def extent():
        text=tree().get('TxtPageNumber',{}).get('name','').replace(',','')
        match=re.fullmatch(r'(\d+)–(\d+) / (\d+)',text)
        return tuple(map(int,match.groups())) if match else None
    def wait_range(predicate):
        last=None
        for _ in range(40):
            current=extent()
            if current is not None:
                last=current
                if predicate(current):
                    report.setdefault('tail_ranges',[]).append(current)
                    check('tail case metadata retention at most600',current[1]-current[0]+1<=600)
                    return current
            time.sleep(.1)
        raise AssertionError('Tail range did not settle: '+str(last))
    def sample(label):
        class Counters(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD),*[(name,ctypes.c_size_t) for name in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]]
        kernel=ctypes.WinDLL('kernel32',use_last_error=True);api=ctypes.WinDLL('psapi',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        api.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
        h=kernel.OpenProcess(0x410,False,pid)
        if not h:raise ctypes.WinError(ctypes.get_last_error())
        try:
            values=Counters();values.cb=ctypes.sizeof(values)
            if not api.GetProcessMemoryInfo(h,ctypes.byref(values),values.cb):raise ctypes.WinError(ctypes.get_last_error())
            visible=tree();realized=sum(re.fullmatch(r'Item\d+',name) is not None for name in visible)
            report.setdefault('memory_samples',[]).append({'label':label,'working_set_bytes':values.WorkingSetSize,'private_bytes':values.PrivateUsage,'native_keyed_cards':realized})
            check(label+' native keyed cards bounded',0<realized<100)
        finally:kernel.CloseHandle(h)
    def shown(key,label):
        ui('wait-for',key,'-p','IsOffscreen','--value','False','-t','10000')
        visible=tree();row=visible[key];viewport=visible['ItemList']
        check(label+' physical row intersects library viewport',row['y']<viewport['y']+viewport['height'] and row['y']+row['height']>viewport['y'])
    sample('initial')
    current=None
    for _ in range(12):
        previous=current;ui('scroll','ItemList','--to','bottom')
        current=wait_range(lambda value:value[1]==745 or previous is None or value[1]>previous[1])
        if current[1]==745:break
    check('final range available with head eviction',current is not None and current[1]==745 and current[0]>1)
    last=cat.search(query='generated-744.png')['items'][0];key='Item'+str(last['id'])
    ui('scroll','ItemList','--to','bottom');shown(key,'list final')
    ui('invoke',key,'--action','select');ui('wait-for','TxtTags','-p','IsEnabled','--value','True','-t','10000')
    ui('set-value','TxtTags','tail-unsaved-draft');shot('physical-last-list');sample('list-tail')
    ui('invoke','BtnLayout');shown(key,'grid final');ui('wait-for','TxtTags','--value','tail-unsaved-draft','-t','5000')
    for size in (180,60,100):
        ui('invoke','BtnItemSize');ui('set-value','ItemSizeSlider',str(size));ui('wait-for','ItemSizeLabel','--value',str(size)+'%','-t','5000')
        ui('send-keys','escape','--via','send-input');shown(key,'grid '+str(size)+' final')
        ui('wait-for','TxtTags','--value','tail-unsaved-draft','-t','5000')
    shot('physical-last-grid');sample('grid-resized-tail')
    check('tail draft has not autosaved',cat.get(last['id'])['tags']==[])
    ui('set-value','TxtTags','');ui('invoke','BtnCloseDetails')
    for _ in range(12):
        if current[0]==1:break
        previous=current;ui('scroll','ItemList','--to','top')
        current=wait_range(lambda value:value[0]<previous[0])
    ui('scroll','ItemList','--to','top');first=cat.search(limit=1)['items'][0]
    shown('Item'+str(first['id']),'reverse first');sample('returned-first');shot('tail-returned-first')
