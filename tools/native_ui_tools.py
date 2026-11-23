"""Open a named production tool through the owned app's Settings dialog."""
import json
import time

TOOL_IDS = frozenset(('BtnAIIndex', 'BtnRelatedTerms'))

def nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def inspect_element(ui,identifier):
    """Read one stable peer without walking changing virtualized containers."""
    value=json.loads(ui('inspect',identifier,'--depth','0','--json'))
    peers=[node for node in nodes(value) if node.get('automationId')==identifier]
    if len(peers)!=1:raise RuntimeError('Expected one exact UIA peer: '+identifier)
    return peers[0]

def invoke_tool(cli, app_pid, hwnd, identifier):
    if identifier not in TOOL_IDS:
        raise ValueError('Unknown production tool')
    cli('ui', 'invoke', 'BtnSettings', '-w', hwnd)
    for _ in range(20):
        windows = json.loads(cli('ui', 'list-windows', '-a', app_pid, '--json'))
        for window in windows:
            handle = str(window.get('hwnd', ''))
            if not handle or handle == '0':
                continue
            try:
                tree = json.loads(cli('ui', 'inspect', '--json', '--depth', '12', '-w', handle))
            except RuntimeError as ex:
                if 'AppNotFoundException' in str(ex):
                    continue
                raise
            if any(n.get('automationId') == identifier and not n.get('isOffscreen', True) for n in nodes(tree)):
                return cli('ui', 'invoke', identifier, '-w', handle)
        time.sleep(.1)
    raise RuntimeError('Production tool was not visible in the owned menu: ' + identifier)


def viewer_wait_args(arguments):
    """Legacy success captions moved off canvas; assert the real control state.

    Error/warning assertions stay unchanged. Frame count is still checked through
    the displayed image's accessible name, not through removed explanatory copy.
    """
    args=tuple(arguments)
    if len(args)<4 or args[0]!='wait-for' or '--value' not in args:return args
    target=args[1];value=str(args[args.index('--value')+1])
    timeout=args[args.index('-t')+1] if '-t' in args else '10000'
    if target=='ImageStatus' and value.startswith('アニメーション再生中（'):
        count=value.split('（',1)[1].split('フレーム',1)[0]
        return ('wait-for','ViewerImage','--value','/ '+count+'）','--contains','-t',timeout)
    ready=(target=='ImageStatus' and value.startswith('← → で画像送り') or
           target=='ReaderStatus' and value.startswith('表示しました。') or
           target=='VideoStatus' and value.startswith(('動画を開きました。','音声を開きました。','該当時刻（')))
    if ready:
        control={'ImageStatus':'ImageZoomIn','ReaderStatus':'ReaderFit','VideoStatus':'VideoSeek'}[target]
        return ('wait-for',control,'-p','IsEnabled','--value','True','-t',timeout)
    if target=='VideoStatus' and value in ('再生中','一時停止中'):
        return ('wait-for','VideoPlayPause','--value','一時停止' if value=='再生中' else '再生','-t',timeout)
    return args


def process_memory(pid):
    """Read working/private bytes of one explicit Windows process; no enumeration."""
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD),*[(name,ctypes.c_size_t) for name in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);api=ctypes.WinDLL('psapi',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE];api.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    handle=kernel.OpenProcess(0x410,False,pid)
    if not handle:raise ctypes.WinError(ctypes.get_last_error())
    try:
        value=Counters();value.cb=ctypes.sizeof(value)
        if not api.GetProcessMemoryInfo(handle,ctypes.byref(value),value.cb):raise ctypes.WinError(ctypes.get_last_error())
        return {'working_set_bytes':value.WorkingSetSize,'private_bytes':value.PrivateUsage}
    finally:kernel.CloseHandle(handle)



def select_combo_item(ui,combo_id,item_id):
    """Select one live visible native item by stable AutomationId, never End.

    The supplied UI helper must remain bound to its owned PID/window. WinUI may
    expose the same peer twice, plus separate child text or hidden stale peers.
    Resolve again after selection; prior popup selectors can become stale.
    """
    ui('invoke',combo_id,'--action','expand')
    inspected=json.loads(ui('inspect','--depth','18','--json'))
    choices={node['selector'] for node in nodes(inspected)
        if node.get('type') in ('ListItem','ComboBoxItem') and node.get('automationId')==item_id
        and node.get('selector') and not node.get('isOffscreen',True)}
    if len(choices)!=1:raise RuntimeError('Expected one visible exact ComboBox item: '+item_id)
    ui('invoke',choices.pop(),'--action','select')
    current=json.loads(ui('inspect','--depth','18','--json'))
    controls={node['selector'] for node in nodes(current)
        if node.get('type')=='ComboBox' and node.get('automationId')==combo_id
        and node.get('selector') and not node.get('isOffscreen',True)}
    if len(controls)!=1:raise RuntimeError('Expected one visible ComboBox after selection: '+combo_id)
    ui('invoke',controls.pop(),'--action','collapse')
