"""Native restart/profile regression using generated sources and isolated settings.

Requires built x64 SelfContained Release, existing local weights, unlocked Windows.
Never touches the default AppData settings or private library. No setup/download.
Known local limitation: search-mode popup discovery remains failing after the
initial profile save. See docs/model-profiles.md; this batch is not a passed test.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from ai_profiles import DEFAULT_PROFILE
from create_preview_fixture import create

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if os.name!='nt':raise RuntimeError('Native Windows only')
    target=args.output.resolve();target.mkdir(parents=True,exist_ok=False)
    media=create(target/'media')
    for name in ('雨の夜の街並み.wav','晴れた昼の公園.wav'):(media/name).write_bytes(b'fictional audio metadata fixture')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in media.iterdir()}
    folder=REPO/'data/ai-profiles';folder.mkdir(parents=True,exist_ok=True)
    nonce='ui-'+uuid.uuid4().hex[:10]
    names={key:nonce+'-'+key+'.json' for key in ('text','missing','invalid')}
    profile_files=[];logs=[];backend=None;app_pid=None;hwnd=None;headers={}
    origin='http://127.0.0.1:8769';settings=target/'settings.json'
    env=os.environ.copy();env['WINAPP_UI_WORKFLOW_ID']='aredoko-profile-'+nonce
    report={'target':'local','actual_model':True,'pass':False,'checks':[],'screenshots':[]}
    def cli(*arguments):
        result=subprocess.run(['winapp',*map(str,arguments)],cwd=REPO,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
        if result.returncode:raise RuntimeError('winapp '+str(arguments)+': '+result.stderr+result.stdout)
        return result.stdout
    def ui(*arguments,window=None):return cli('ui',*arguments,'-w',window or hwnd)
    def api(route,body=None,expected=200):
        request=urllib.request.Request(origin+route,None if body is None else json.dumps(body,ensure_ascii=False).encode('utf-8'),headers={**headers,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=180) as response:data=json.load(response);code=response.status
        except urllib.error.HTTPError as ex:
            with ex:data=json.load(ex);code=ex.code
        if code!=expected:raise RuntimeError(f'{route} returned {code}: {data}')
        return data
    def check(name,condition):
        if not condition:raise RuntimeError(name)
        report['checks'].append(name)
    def screenshot(name):
        path=target/(name+'.png')
        ui('screenshot','--output',path)
        check('Screenshot '+name,path.is_file() and path.stat().st_size>0)
        report['screenshots'].append(path.name)
    def status():return api('/api/library/ai/status')
    def profiles():return api('/api/library/ai/profiles')
    def ready():
        ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','30000')
        time.sleep(.3)
    def dialog():
        ready();ui('invoke','BtnAIIndex');ui('wait-for','AIProfileChoice','-t','5000')
    def close_dialog():ui('invoke','CloseButton');ready()
    def select(combo,option):
        ui('invoke',combo,'--action','expand')
        for _ in range(30):
            windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
            popup=[w for w in windows if w.get('title')=='PopupHost']
            if len(popup)==1:break
            time.sleep(.1)
        if len(popup)!=1:raise RuntimeError('Expected one observed popup')
        ui('invoke',option,'--action','select',window=str(popup[0]['hwnd']))
    def choose(profile_id):
        select('AIProfileChoice','AIProfile_'+profile_id.replace(':','_'))
        ui('wait-for','AIProfileApply','-p','IsEnabled','--value','True','-t','3000')
        ui('invoke','AIProfileApply')
        for _ in range(50):
            if profiles()['selected']==profile_id:break
            time.sleep(.1)
        check('GUI saved '+profile_id,profiles()['selected']==profile_id)
        ui('wait-for','AIProfileApply','-p','IsEnabled','--value','False','-t','3000')
    def build():
        ui('invoke','StartAIIndex')
        for _ in range(240):
            state=status()
            if state['state'] in ('complete','failed'):break
            time.sleep(.5)
        check('GUI index complete',state['state']=='complete' and state['indexed']==17 and state['device']=='cuda')
    def stop():
        nonlocal app_pid,backend,hwnd
        if app_pid:
            try:
                try:ui('invoke','CloseButton')
                except RuntimeError:pass
                cli('ui','send-keys','alt+f4','-a',app_pid,'--via','send-input','--allow-system-keys')
                time.sleep(.6)
            finally:
                subprocess.run(['powershell','-NoProfile','-Command',f'if(Get-Process -Id {app_pid} -ErrorAction SilentlyContinue){{Stop-Process -Id {app_pid}}}'],capture_output=True)
                app_pid=None;hwnd=None
        if backend:
            backend.terminate();backend.wait(timeout=10);backend=None
        for log in logs:log.close()
        logs.clear();time.sleep(.6)
    def start(phase,override=None):
        nonlocal backend,app_pid,hwnd,headers
        # Refuse another API or native Aredoko instance; never attach to unknown data.
        try:
            urllib.request.urlopen(origin+'/api/session',timeout=.5).close()
        except urllib.error.URLError:pass
        else:raise RuntimeError('Port is already occupied')
        existing=subprocess.run(['powershell','-NoProfile','-Command','if(Get-Process Aredoko.WinUI -ErrorAction SilentlyContinue){exit 1}'],capture_output=True)
        if existing.returncode:raise RuntimeError('Existing native app; stop your own app first')
        for suffix in ('out','err'):logs.append((target/(phase+'-api.'+suffix)).open('w',encoding='utf-8'))
        command=[sys.executable,'app/production_server.py','--db',str(target/'catalog.sqlite'),'--ai-settings',str(settings)]
        if override:command+=['--ai-profile',str(override)]
        backend=subprocess.Popen(command,cwd=REPO,stdout=logs[0],stderr=logs[1],creationflags=subprocess.CREATE_NO_WINDOW,env={**env,'PYTHONIOENCODING':'utf-8'})
        for _ in range(100):
            if backend.poll() is not None:raise RuntimeError('Owned API failed')
            try:
                session=api('/api/session');headers={'X-Aredoko-Token':session['token'],'Origin':origin};break
            except urllib.error.URLError:time.sleep(.1)
        launch=json.loads(cli('run','src/Aredoko.WinUI','-c','Release','--arch','x64','-p','Platform=x64','-p','SelfContained=true','--no-build','--detach','--json'))
        app_pid=int(launch['ProcessId'])
        for _ in range(50):
            windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
            main=[w for w in windows if w.get('hwnd') and 'Aredoko' in w.get('title','') and w.get('title')!='PopupHost']
            if len(main)==1:break
            time.sleep(.1)
        if len(main)!=1:raise RuntimeError('Expected owned main window')
        (target/(phase+'-launch.json')).write_text(json.dumps(launch),encoding='utf-8')
        hwnd=str(main[0]['hwnd']);ready()
    def semantic():
        select('CmbSearchMode','ModeSemantic');ui('set-value','TxtQuery','傘が必要な暗い都会の景色');time.sleep(.6);ui('invoke','BtnSearch');ready()
        result=api('/api/library/ai/search',{'query':'傘が必要な暗い都会の景色','source':'text'})
        check('CUDA Japanese query',status()['device']=='cuda' and result['items'][0]['title']=='雨の夜の街並み.wav')
        ui('wait-for','Item'+str(result['items'][0]['id']),'-t','5000')
    def literal():
        select('CmbSearchMode','ModeLiteral');ui('set-value','TxtQuery','雨の夜');time.sleep(.6);ui('invoke','BtnSearch');ready()
        result=api('/api/items?q='+urllib.parse.quote('雨の夜'))
        check('Literal independent of model',result['total']==1)
        ui('wait-for','Item'+str(result['items'][0]['id']),'-t','5000')
    try:
        for key in ('text','missing','invalid'):
            path=folder/names[key]
            if path.exists():raise RuntimeError('Test config collision')
            data=DEFAULT_PROFILE.to_dict();data.update(label='GUI test '+key,modalities=['text'],precision='float32')
            if key=='missing':data['directory']=nonce+'-missing-weights'
            path.write_text('{invalid' if key=='invalid' else json.dumps(data),encoding='utf-8');profile_files.append(path)
        start('default');api('/api/library/roots',{'path':str(media),'consent':True});api('/api/library/scan',{'root_id':1})
        for _ in range(100):
            if api('/api/library/scan')['state']=='complete':break
            time.sleep(.1)
        # Refresh native catalog after API registration; actual index is started in GUI.
        ui('invoke','BtnSearch');ready();dialog();build()
        default_profile=status()['profile'];check('Default active',profiles()['active']=='default')
        choose('local:'+names['text']);check('No hot swap',status()['profile']==default_profile and profiles()['active']=='default')
        screenshot('01-next-launch');close_dialog();semantic();stop()
        start('text');check('Saved text profile active',profiles()['active']=='local:'+names['text'] and status()['modalities']==['text'] and status()['profile']!=default_profile and status()['indexed']==0)
        dialog();build();screenshot('02-text-only');close_dialog();semantic()
        result=api('/api/library/ai/search',{'query':'青い画像','source':'cover'},expected=503);check('Text-only cover refused with guidance','画像' in result['error'])
        select('CmbSearchMode','ModeVisual');ui('set-value','TxtQuery','青い画像');time.sleep(.6);ui('invoke','BtnSearch');ready();screenshot('03-cover-unavailable');literal()
        dialog();choose('default');check('Text stays active until restart',profiles()['active']=='local:'+names['text']);close_dialog();stop()
        start('restored');check('Original index reused',status()['profile']==default_profile and status()['indexed']==17 and status()['state']=='complete')
        semantic();screenshot('04-restored-index');dialog();choose('local:'+names['missing']);close_dialog();stop()
        start('missing');check('Missing model unavailable',not status()['available']);literal();dialog();ui('wait-for','StartAIIndex','-p','IsEnabled','--value','False','-t','3000');screenshot('05-missing');close_dialog();stop()
        settings.write_text(json.dumps({'version':1,'profile':'local:'+names['invalid']}),encoding='utf-8')
        start('invalid');check('Invalid saved config fallback',not status()['available'] and bool(profiles()['error']));literal();dialog();screenshot('06-invalid');choose('default');close_dialog();stop()
        settings.write_text('{broken',encoding='utf-8')
        start('override',REPO/'config/ai-profiles/embeddinggemma-2.json');check('Explicit override beats corrupt settings',profiles()['command_line_override'] and status()['profile']==default_profile);semantic();dialog();screenshot('07-override');choose('default');close_dialog();stop()
        check('Generated source hashes unchanged',hashes=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in media.iterdir()})
        report['pass']=True
    except Exception as ex:
        report['error']=str(ex)
        if app_pid and hwnd:
            try:
                screenshot('failure')
                (target/'failure-tree.json').write_text(ui('inspect','--json','--depth','12'),encoding='utf-8')
            except Exception:pass
        raise
    finally:
        try:stop()
        finally:
            try:cli('ui','yield')
            finally:
                # Delete only the exact generated profile files, never the directory.
                for path in profile_files:
                    if path.resolve().parent!=folder.resolve():raise RuntimeError('Unsafe cleanup target')
                    path.unlink(missing_ok=True)
                (target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))

if __name__=='__main__':main()
