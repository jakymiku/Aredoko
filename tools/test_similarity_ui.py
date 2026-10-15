"""One native Windows similarity batch, using only generated sandbox media.

Requires an existing Release build and winapp CLI. No downloads or model.
Screenshots need human review; runtime_pass never means visual review passed.
"""
import argparse
import ctypes
from ctypes import wintypes
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid
from similarity_sandbox import SimilaritySandbox,REPO


def nodes(value):
    if isinstance(value,dict):
        yield value
        for child in value.values():yield from nodes(child)
    elif isinstance(value,list):
        for child in value:yield from nodes(child)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--scenario',choices=('indexed','unindexed','text-only'),default='indexed')
    args=parser.parse_args()
    if os.name!='nt':parser.error('Native Windows required; no test was run')
    target=args.output.resolve()
    if not target.is_relative_to((REPO/'data/ai-ui').resolve()):parser.error('Output must be a new folder inside data/ai-ui')
    if target.exists():parser.error('Output already exists; choose a new evidence folder')
    # Refuse existing app/service instead of attaching to user data or killing it.
    existing=subprocess.run(['powershell','-NoProfile','-Command','if(Get-Process Aredoko.WinUI -ErrorAction SilentlyContinue){exit 1}'],capture_output=True,timeout=15)
    if existing.returncode:parser.error('Close the existing Aredoko app before this isolated test')
    server=ThreadingHTTPServer(('127.0.0.1',8769),BaseHTTPRequestHandler)
    sandbox=thread=process=hwnd=app_pid=None
    report={'runtime_pass':False,'visual_review':'pending: inspect every screenshot','actual_model':False,
        'scenario':args.scenario,'checks':[],'screenshots':[],'requests':[],'keyboard_tested':False}
    env={**os.environ,'WINAPP_UI_WORKFLOW_ID':'aredoko-similarity-'+uuid.uuid4().hex}
    user32=ctypes.WinDLL('user32',use_last_error=True);kernel32=ctypes.WinDLL('kernel32',use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user32.GetForegroundWindow.restype=wintypes.HWND
    user32.SetForegroundWindow.argtypes=[wintypes.HWND]
    user32.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    user32.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
    kernel32.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel32.OpenProcess.restype=wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel32.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
    kernel32.CloseHandle.argtypes=[wintypes.HANDLE]

    def check(name,value):
        if not value:raise RuntimeError(name)
        report['checks'].append(name);print(json.dumps({'check':name},ensure_ascii=True),flush=True)
    def cli(*parts):
        result=subprocess.run(['winapp',*map(str,parts)],cwd=REPO,env=env,text=True,encoding='utf-8',errors='replace',capture_output=True,timeout=45)
        if result.returncode:raise RuntimeError('winapp '+str(parts)+': '+result.stdout+result.stderr)
        return result.stdout
    def ui(*parts,window=None):return cli('ui',*parts,'-w',window or hwnd)
    def wait(identifier,value):ui('wait-for',identifier,'--value',value,'-t','12000')
    def ready():
        ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','12000');time.sleep(.2)
    def owned(handle=None,foreground=False):
        handle=handle or hwnd
        owner=wintypes.DWORD();user32.GetWindowThreadProcessId(int(handle),ctypes.byref(owner))
        if owner.value!=app_pid or kernel32.WaitForSingleObject(process,0)==0:raise RuntimeError('Owned window/process changed')
        if foreground:
            if user32.GetForegroundWindow()!=int(hwnd):user32.SetForegroundWindow(int(hwnd));time.sleep(.1)
            if user32.GetForegroundWindow()!=int(hwnd):raise RuntimeError('Windows denied owned-window activation; no input sent')
    def shot(name):
        owned();path=target/(name+'.png');ui('screenshot','--output',path)
        check('screenshot '+name,path.is_file() and path.stat().st_size>0);report['screenshots'].append(path.name)
        tree=json.loads(ui('inspect','--json','--depth','12'))
        (target/(name+'-tree.json')).write_text(json.dumps(tree,ensure_ascii=False),encoding='utf-8')
    def context(identifier,source):
        if identifier.startswith('Item'):ui('scroll-into-view',identifier)
        owned(foreground=True);ui('click',identifier,'--right')
        for _ in range(20):
            windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
            ordered=[w for w in windows if w.get('title')=='PopupHost']+[w for w in windows if str(w.get('hwnd'))==hwnd]
            for window in ordered:
                handle=str(window['hwnd']);owned(handle)
                tree=json.loads(ui('inspect','--json','--depth','14',window=handle))
                matches=[n for n in nodes(tree) if n.get('automationId')=='FindSimilar'+str(source)]
                if matches:
                    ui('invoke','FindSimilar'+str(source),window=handle);return
            time.sleep(.1)
        raise RuntimeError('No context action for clicked item '+str(source))
    def latest(source):
        with sandbox.ai.request_lock:entry=dict(sandbox.ai.requests[-1]) if sandbox.ai.requests else {}
        check('clicked origin '+str(source),entry.get('item_id')==source)
        return entry
    def close():
        nonlocal process,hwnd,app_pid
        if process:
            try:
                if kernel32.WaitForSingleObject(process,0)!=0:
                    owned();user32.PostMessageW(int(hwnd),0x0010,0,0)
                    if kernel32.WaitForSingleObject(process,7000)!=0:
                        report['cleanup_terminated_owned_process']=True
                        kernel32.TerminateProcess(process,1)
                        if kernel32.WaitForSingleObject(process,5000)!=0:raise RuntimeError('Owned process cleanup failed')
                    else:report['graceful_closes']=report.get('graceful_closes',0)+1
            finally:kernel32.CloseHandle(process);process=hwnd=app_pid=None
    try:
        sandbox=SimilaritySandbox(target/'fixture',args.scenario)
        target.mkdir(parents=True,exist_ok=True)
        server.RequestHandlerClass=sandbox.handler();thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        for theme in ('Light','Dark'):
            launch=json.loads(cli('run','src/Aredoko.WinUI','-c','Release','--arch','x64','-p','Platform=x64','-p','SelfContained=true','--no-build',
                '--output-appx-directory',target/('layout-'+theme.lower()),'--detach','--json','--args','--ui-theme '+theme.lower()))
            if launch.get('ProcessScope') not in (None,'local'):raise RuntimeError('Unexpected launch scope')
            app_pid=int(launch['ProcessId']);process=kernel32.OpenProcess(0x00100001,False,app_pid)
            if not process:raise ctypes.WinError(ctypes.get_last_error())
            for _ in range(50):
                windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
                matches=[w for w in windows if w.get('hwnd') and 'Aredoko' in w.get('title','') and w.get('title')!='PopupHost']
                if len(matches)==1:break
                time.sleep(.1)
            if len(matches)!=1:raise RuntimeError('Expected one owned main window')
            hwnd=str(matches[0]['hwnd']);user32.SetWindowPos(int(hwnd),None,0,0,1200,820,0x0014);ready();wait('TxtCount','76 件')
            origin=sandbox.item('generated-065.png')
            ui('invoke','BtnNext');ready();wait('TxtPageNumber','2 / 2')
            context('Item'+str(origin),origin);ready();wait('TxtSimilarityOrigin','類似検索の起点: generated-065.png')
            if args.scenario!='indexed':
                wait('TxtCount','0 件');expected='unindexed' if args.scenario=='unindexed' else 'unsupported_profile'
                check(theme+' explicit fallback',latest(origin).get('status')==expected)
                shot(theme+'-'+expected);ui('invoke','BtnSimilarityBack');ready();wait('TxtPageNumber','2 / 2');close();continue
            wait('TxtCount','72 件');entry=latest(origin)
            check(theme+' profile scope and self exclusion',entry.get('scope')==sandbox.scope and origin not in entry['ids'] and sandbox.item('generated-001.png',1) not in entry['ids'])
            shot(theme+'-list');owned(foreground=True);ui('invoke','BtnSimilarityBack');ready();wait('TxtPageNumber','2 / 2')
            ui('wait-for','Item'+str(origin),'-p','HasKeyboardFocus','--value','True','-t','5000')
            check(theme+' original page and focus restored',True)
            ui('invoke','BtnPrevious');ready();ui('invoke','BtnLayout')
            source=sandbox.item('generated-001.png');context('Item'+str(source),source);ready();wait('TxtCount','72 件')
            shot(theme+'-grid');ui('invoke','BtnSimilarityBack');ready();ui('invoke','BtnLayout')
            ui('invoke','Item'+str(source),'--action','select');wait('TxtEditStatus','保存済み')
            ui('wait-for','DetailPreview','-p','IsOffscreen','--value','False','-t','5000')
            ui('set-value','TxtTags','unsaved-similarity-test');wait('TxtEditStatus','未保存の変更')
            before=len(sandbox.ai.requests);context('DetailPreview',source)
            ui('wait-for','PrimaryButton','-t','5000');ui('invoke','CloseButton')
            wait('TxtTags','unsaved-similarity-test');check(theme+' dirty cancel sends no request',len(sandbox.ai.requests)==before)
            # Accept discard, then cancel the delayed request. No second dirty
            # prompt may strand the loading view with ItemList disabled.
            sandbox.ai.delay=True;sandbox.ai.entered.clear();sandbox.ai.proceed.clear()
            context('DetailPreview',source);ui('wait-for','PrimaryButton','-t','5000');ui('invoke','PrimaryButton')
            check(theme+' delayed request entered',sandbox.ai.entered.wait(3))
            ui('invoke','BtnSimilarityBack');ready();wait('TxtCount','76 件')
            sandbox.ai.proceed.set();sandbox.ai.delay=False;time.sleep(.4)
            wait('TxtCount','76 件');check(theme+' cancel restores enabled library without second discard prompt',True)
            shot(theme+'-cancel-return')
            # Current scope includes the source and the generated favorite;
            # the result-only view must not filter out the nonfavorite source.
            ui('invoke','NavFavorites','--action','select');ready()
            favorite=sandbox.item('generated-002.png');context('Item'+str(favorite),favorite);ready();wait('TxtCount','0 件')
            check(theme+' favorite scope and self exclusion',latest(favorite).get('view')=='favorites')
            ui('invoke','BtnSimilarityBack');ready();ui('invoke','NavAll','--action','select');ready()
            ui('set-value','TxtQuery','generated-unindexed.png');time.sleep(.4);ui('invoke','BtnSearch');ready()
            unindexed=sandbox.item('generated-unindexed.png');context('Item'+str(unindexed),unindexed);ready();wait('TxtCount','0 件')
            check(theme+' unindexed fallback',latest(unindexed).get('status')=='unindexed')
            shot(theme+'-unindexed');ui('invoke','BtnSimilarityBack');ready()
            ui('set-value','TxtQuery','generated-001.png');time.sleep(.4);ui('invoke','BtnSearch');ready()
            for fault in ('busy','unavailable'):
                sandbox.ai.fail=fault;context('Item'+str(source),source);ready();wait('TxtCount','—')
                check(theme+' '+fault+' error recovery offered',latest(source).get('failed') is not None)
                ui('invoke','BtnSimilarityBack');ready();sandbox.ai.fail=None
            # The pane's extra origin/back controls must also fit a narrow window.
            context('Item'+str(source),source);ready()
            user32.SetWindowPos(int(hwnd),None,0,0,700,620,0x0014);time.sleep(.3);shot(theme+'-narrow')
            ui('invoke','BtnSimilarityBack');ready();close()
        check('source bytes/mtime unchanged',sandbox.source_before==sandbox.source_digest())
        check('saved settings unchanged',sandbox.settings_before==(sandbox.target/'settings.json').read_bytes())
        check('no inference or model loaded',sandbox.encoder.calls==0 and not sandbox.encoder.resident)
        report['runtime_pass']=True
    except Exception as ex:
        report['error']=str(ex)
        if hwnd:
            try:shot('failure')
            except Exception:pass
        raise
    finally:
        if sandbox:sandbox.ai.proceed.set()
        try:close()
        finally:
            if thread:server.shutdown();thread.join(5)
            server.server_close()
            if sandbox:
                report['requests']=sandbox.ai.requests
                report['source_unchanged']=sandbox.source_before==sandbox.source_digest()
                if not report['source_unchanged'] or report.get('cleanup_terminated_owned_process'):report['runtime_pass']=False
                sandbox.close()
            if target.exists():(target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            try:cli('ui','yield')
            except Exception:pass
    print(json.dumps({'runtime_pass':report['runtime_pass'],'checks':len(report['checks']),'visual_review':report['visual_review']}))
    if not report['runtime_pass']:raise RuntimeError('Native checks failed; inspect result.json')

if __name__=='__main__':main()
