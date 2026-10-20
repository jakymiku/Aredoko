"""Fixed local MSIX/shortcut lifecycle acceptance on generated media only.

Run only after explicit certificate trust/install and GUI permission. No model
inference, downloads, development registration, package removal, or private scan.
"""
import argparse
from contextlib import closing
import ctypes
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
import uuid

sys.dont_write_bytecode=True
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
import packaged_frontend as native


class LauncherHandle:
    """Retain the fresh, exact copied-pythonw process returned by ShellExecute."""
    def __init__(self,pid,expected,started):
        self.k=ctypes.WinDLL('kernel32',use_last_error=True)
        self.k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];self.k.OpenProcess.restype=W.HANDLE
        self.k.GetProcessTimes.argtypes=[W.HANDLE,*([ctypes.POINTER(W.FILETIME)]*4)]
        self.k.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)]
        self.k.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD]
        self.k.GetExitCodeProcess.argtypes=[W.HANDLE,ctypes.POINTER(W.DWORD)]
        self.k.TerminateProcess.argtypes=[W.HANDLE,W.UINT]
        self.k.CloseHandle.argtypes=[W.HANDLE]
        self.h=self.k.OpenProcess(0x100000|0x1000|1,False,pid)
        if not self.h:raise ctypes.WinError(ctypes.get_last_error())
        try:
            times=[W.FILETIME() for _ in range(4)]
            if not self.k.GetProcessTimes(self.h,*(ctypes.byref(t) for t in times)):raise ctypes.WinError(ctypes.get_last_error())
            created=(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime
            buffer=ctypes.create_unicode_buffer(32768);length=W.DWORD(len(buffer))
            if not self.k.QueryFullProcessImageNameW(self.h,0,buffer,ctypes.byref(length)):raise ctypes.WinError(ctypes.get_last_error())
            if created<started or os.path.normcase(buffer.value)!=os.path.normcase(str(expected)):
                raise RuntimeError('Shortcut launcher ownership not proven')
        except BaseException:
            self.k.CloseHandle(self.h);self.h=None;raise

    def running(self):return self.k.WaitForSingleObject(self.h,0)==258
    def stop(self):
        if self.running():self.k.TerminateProcess(self.h,1);self.k.WaitForSingleObject(self.h,5000)
    def wait(self,seconds=15):
        if self.k.WaitForSingleObject(self.h,int(seconds*1000))!=0:raise TimeoutError('Owned launcher did not exit')
        code=W.DWORD()
        if not self.k.GetExitCodeProcess(self.h,ctypes.byref(code)):raise ctypes.WinError(ctypes.get_last_error())
        return code.value
    def close(self):
        if self.h:self.k.CloseHandle(self.h);self.h=None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--attempt',type=int,choices=(1,2,3),required=True)
    args=parser.parse_args()
    root=args.release.resolve();base=args.fixture.resolve()
    if os.name!='nt' or not root.is_relative_to(REPO/'dist') or not base.is_relative_to(REPO/'data/ai-ui'):
        parser.error('Use the Windows repository release and prepared generated fixture only')
    media=base/'generated media'
    original={p.name:(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in media.iterdir() if p.is_file()}
    if set(original)!={'alpha-blue-card.png'}:raise RuntimeError('Expected the fixed generated fixture')
    out=base/f'attempt-{args.attempt:02d}';out.mkdir(exist_ok=False)
    user=out/'isolated-user';data=user/'Aredoko';data.mkdir(parents=True)
    settings={key:str(data/value) for key,value in {'database':'catalog.sqlite','models_root':'absent-models',
              'ai_settings':'settings.json','ai_profiles_dir':'ai-profiles','viewer_settings':'viewer settings 日本語.json'}.items()}
    settings['ui_theme']='light'
    config=out/'launch settings 日本語.json';config.write_text(json.dumps(settings,ensure_ascii=False),encoding='utf-8')
    env={**os.environ,'LOCALAPPDATA':str(user),'PYTHONDONTWRITEBYTECODE':'1',
         'WINAPP_UI_WORKFLOW_ID':'aredoko-alpha-'+uuid.uuid4().hex}
    report={'flow':'alpha-msix-owned-lifecycle-v1','attempt':args.attempt,'pass':False,'checks':[],
            'screenshots':[],'gpu_operations':0,'actual_shortcut':True,'release':str(root)}
    launcher=frontend=None;hwnd=pid=None;token=None
    def check(name,condition):
        report['checks'].append({'name':name,'pass':bool(condition)})
        print(json.dumps({'check':name,'pass':bool(condition)}),flush=True)
        if not condition:raise AssertionError(name)
    def cli(*items):
        result=subprocess.run(['winapp','ui',*map(str,items)],cwd=REPO,env=env,capture_output=True,
                              text=True,encoding='utf-8',errors='replace',timeout=35)
        with (out/'ui.log').open('a',encoding='utf-8') as log:
            log.write(json.dumps(list(map(str,items)),ensure_ascii=False)+'\n'+result.stdout+result.stderr+'\n')
        if result.returncode:raise RuntimeError('UI command failed: '+str(items)+'\n'+result.stdout+result.stderr)
        return result.stdout
    def ui(*items):return cli(*items,'-w',hwnd)
    def wait(name,**kwargs):
        values=['wait-for',name,'-t','15000']
        for key,value in kwargs.items():values+=['-p' if key=='property' else '--'+key,str(value)]
        return ui(*values)
    def shot(name):
        path=out/(name+'.png')
        if path.exists():raise FileExistsError('Preserve screenshot evidence')
        ui('screenshot','--output',path,'--focus')
        report['screenshots'].append(str(path))
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def api(path):
        request=urllib.request.Request('http://127.0.0.1:8769'+path,headers={'X-Aredoko-Token':token} if token else {})
        with opener.open(request,timeout=2) as response:return json.loads(response.read(1048576))
    link=out/'Aredoko Alpha Test.lnk'
    starter=out/'start-shortcut.ps1'
    starter.write_text('''param($Link,$Data,$Output)
$ErrorActionPreference='Stop'
$env:LOCALAPPDATA=$Data
$child=Start-Process -FilePath $Link -WindowStyle Hidden -PassThru
@{pid=$child.Id} | ConvertTo-Json | Set-Content -LiteralPath $Output -Encoding UTF8
''',encoding='utf-8-sig')
    def start(number):
        nonlocal launcher,frontend,pid,hwnd,token
        with socket.socket() as port:
            if port.connect_ex(('127.0.0.1',8769))==0:raise RuntimeError('Backend port in use; no launch')
        began=time.monotonic();stamp=time.time_ns()//100+116444736000000000
        receipt=out/f'launcher-{number}.json'
        result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                '-File',str(starter),str(link),str(user),str(receipt)],env=env,capture_output=True,text=True,timeout=25)
        if result.returncode:raise RuntimeError('Shortcut launch failed: '+result.stdout+result.stderr)
        launch_pid=json.loads(receipt.read_text(encoding='utf-8-sig'))['pid']
        launcher=LauncherHandle(launch_pid,root/'runtime/python/pythonw.exe',stamp)
        deadline=time.monotonic()+240
        record=None;log_directory=None
        while time.monotonic()<deadline:
            for folder in (data/'logs').glob('*'):
                if (folder/'launcher.log').is_file():raise RuntimeError((folder/'launcher.log').read_text(encoding='utf-8'))
                app=folder/'app.log'
                if app.exists() and app.stat().st_size:
                    candidate=json.loads(app.read_text(encoding='utf-8').splitlines()[0])
                    if candidate.get('pid')!=report.get('first_frontend_pid'):
                        record=candidate;log_directory=folder;break
            if record:break
            if not launcher.running():raise RuntimeError('Launcher exited before GUI activation')
            time.sleep(.3)
        if not record:raise TimeoutError('No owned activation receipt in isolated data')
        expected=native.inspect_msix(root/native.PACKAGE_PATH)
        registration=native.discover_package(expected)
        executable=native.verify_installed(expected,registration)
        pid=record['pid'];frontend=native.WindowsProcess(pid,executable,registration['full_name'],stamp)
        check(f'launch{number} exact fresh installed process',record['package']==registration['full_name'])
        session=api('/api/session');token=session['token']
        check(f'launch{number} backend belongs to launcher',session.get('mode')=='production' and
              session.get('instance_id')==log_directory.name.rsplit('-',1)[-1])
        report[f'launch{number}_seconds_to_receipt']=time.monotonic()-began
        if number==1:report['first_frontend_pid']=pid
        windows=json.loads(cli('list-windows','-a',pid,'--json'))
        matches=[w for w in windows if 'Aredoko' in w.get('title','') and w.get('title')!='PopupHost']
        if len(matches)!=1:raise RuntimeError('Expected one owned main window')
        hwnd=str(matches[0]['hwnd'])
        wait('ItemList',property='IsEnabled',value='True')
    def stop():
        nonlocal launcher,frontend,token
        ui('send-keys','alt+f4')
        check('GUI exits normally',frontend.wait(timeout=20)==0)
        check('shortcut launcher exits normally',launcher.wait()==0)
        frontend.close();frontend=None;launcher.close();launcher=None;token=None
        with socket.socket() as port:check('owned backend releases listening port',port.connect_ex(('127.0.0.1',8769))!=0)
        with closing(sqlite3.connect(data/'catalog.sqlite')) as db:check('generated catalog integrity',db.execute('PRAGMA integrity_check').fetchone()[0]=='ok')
    try:
        result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
            '-File',str(root/'install-release-shortcut.ps1'),'-Destination',str(link),'-Settings',str(config),'-NoErrorDialog'],
            env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=240)
        (out/'shortcut-creation.log').write_text(result.stdout+result.stderr,encoding='utf-8')
        check('product shortcut installer passes full activation check',result.returncode==0 and link.is_file())
        start(1)
        check('fresh generated catalog starts empty',api('/api/items')['total']==0)
        wait('TxtCount',value='0 件')
        ui('invoke','NavFolders','--action','select');wait('TxtCount',value='0 フォルダ')
        wait('BtnToggleAddFolder');ui('invoke','BtnToggleAddFolder')
        wait('RootPath');ui('set-value','RootPath',str(media));ui('invoke','AddRoot')
        wait('ScanRoot',property='IsEnabled',value='True');ui('invoke','ScanRoot')
        deadline=time.monotonic()+20
        while time.monotonic()<deadline and api('/api/items')['total']!=1:time.sleep(.3)
        items=api('/api/items');check('GUI registers and scans only generated source',items['total']==1)
        root_id=api('/api/library/roots')['items'][0]['id']
        report['generated_root_id']=root_id
        item=items['items'][0];item_id=item['id']
        ui('invoke','BtnBackToLibrary');wait('TxtCount',value='1 件')
        ui('set-value','TxtQuery','alpha-blue-card');ui('invoke','BtnSearch');time.sleep(.6)
        wait('Item'+str(item_id));ui('invoke','Item'+str(item_id),'--action','select')
        wait('TxtTags');ui('set-value','TxtTags','alpha-native-saved');ui('invoke','BtnSave')
        wait('TxtEditStatus',value='保存しました')
        check('GUI saves generated item tag',api('/api/items')['items'][0]['tags']==['alpha-native-saved'])
        shot('01-library')
        ui('invoke','BtnOpenImage')
        viewers=[]
        for _ in range(40):
            windows=json.loads(cli('list-windows','-a',pid,'--json'))
            viewers=[w for w in windows if '画像ビューア' in w.get('title','')]
            if len(viewers)==1:break
            time.sleep(.2)
        if len(viewers)!=1:raise RuntimeError('Expected owned viewer')
        main_hwnd=hwnd;hwnd=str(viewers[0]['hwnd'])
        wait('ImageZoomIn',property='IsEnabled',value='True');shot('02-viewer')
        # Use targeted HWND input; chrome can be auto-hidden.
        ui('send-keys','esc');hwnd=main_hwnd
        script = ("[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); "
                  "(Get-CimInstance Win32_Process -Filter 'ProcessId="+str(pid)+"').CommandLine | ConvertTo-Json -Compress")
        command_result=subprocess.run(['powershell','-NoProfile','-Command',script],capture_output=True,
                                      text=True,encoding='utf-8-sig',timeout=15)
        if command_result.returncode:raise RuntimeError('Cannot read the owned frontend command line')
        command=json.loads(command_result.stdout)
        check('WinUI receives explicit Japanese settings path and theme',settings['viewer_settings'] in command and '--viewer-settings' in command and '--ui-theme light' in command)
        stop();start(2)
        items=api('/api/items')
        check('second shortcut launch preserves generated tag',items['total']==1 and items['items'][0]['tags']==['alpha-native-saved'])
        check('second launch preserves root identity',api('/api/library/roots')['items'][0]['id']==root_id)
        wait('TxtCount',value='1 件');wait('Item'+str(item_id))
        shot('03-restarted');stop()
        current={p.name:(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in media.iterdir() if p.is_file()}
        check('generated source bytes and mtimes unchanged',current==original)
        from release_runtime import verify_release
        check('full release inventory remains unchanged after native workflow',verify_release(root)['frontend_activation']=='msix')
        report['pass']=True
    except BaseException as error:
        report['error']=type(error).__name__+': '+str(error)
        if frontend is not None and frontend.poll() is None and hwnd:
            try:
                (out/'failure-tree.json').write_text(ui('inspect','--json','--depth','12'),encoding='utf-8')
                shot('failure')
            except Exception as capture_error:report['capture_error']=str(capture_error)
        raise
    finally:
        if frontend is not None:
            try:
                if frontend.poll() is None:frontend.terminate();frontend.wait(timeout=5)
            finally:frontend.close()
        if launcher is not None:
            try:
                try:launcher.wait(seconds=10)
                except TimeoutError:launcher.stop()
            finally:launcher.close()
        (out/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        try:cli('yield')
        except Exception:pass
    print(json.dumps({'pass':True,'checks':len(report['checks']),'screenshots':report['screenshots']}))


if __name__=='__main__':main()
