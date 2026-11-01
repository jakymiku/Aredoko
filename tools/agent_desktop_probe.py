"""Optional pinned development CLI probe, scoped to the harness-owned window."""
import ctypes
import hashlib
import json
import subprocess
from ctypes import wintypes


def audit(executable, hwnd, pid, ui, target, report, check):
    executable=executable.resolve()
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.GetForegroundWindow.restype=wintypes.HWND
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    def run(*args):
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(hwnd),ctypes.byref(owner))
        if owner.value!=pid:raise RuntimeError('Agent Desktop target ownership changed')
        result=subprocess.run([str(executable),*map(str,args)],capture_output=True,text=True,encoding='utf-8',timeout=25)
        value=json.loads(result.stdout)
        with (target/'agent-desktop.jsonl').open('a',encoding='utf-8') as log:
            log.write(json.dumps({'args':args,'exit':result.returncode,'result':value},ensure_ascii=False)+'\n')
        if result.returncode or not value.get('ok'):raise RuntimeError('Agent Desktop: '+result.stdout+result.stderr)
        return value
    report['agent_desktop']={'sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),'headed':False,'window_id':hwnd,'pid':pid}
    run('version')
    ui('scroll-into-view','RootShelfSettings')
    ui('invoke','RootShelfSettings','--action','expand')
    before=user.GetForegroundWindow()
    snapshot=run('snapshot','--window-id',hwnd,'--max-depth','18','--include-bounds')
    check('agent-desktop reads only the owned folder settings window','初期棚' in json.dumps(snapshot,ensure_ascii=False))
    found=run('find','--window-id',hwnd,'--native-id','RootShelfSettings','--exact')
    def refs(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key=='ref' and isinstance(item,str) and item.startswith('@'):yield item
                else:yield from refs(item)
        elif isinstance(value,list):
            for item in value:yield from refs(item)
    matches=set(refs(found))
    check('agent-desktop resolves one native settings ref',len(matches)==1)
    run('collapse',matches.pop())
    from native_ui_tools import inspect_element
    check('agent-desktop semantic collapse is observed by the existing harness',inspect_element(ui,'RootShelfSettings').get('expandState')=='collapsed')
    check('agent-desktop probe did not change the foreground window',user.GetForegroundWindow()==before)
