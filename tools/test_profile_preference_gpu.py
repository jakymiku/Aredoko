"""Actual HTTP/CUDA restart from a GUI-saved test preference; no UI assertions."""
import argparse,hashlib,json,os,sqlite3,subprocess,sys,time,urllib.error,urllib.request,uuid
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from ai_profiles import DEFAULT_PROFILE

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--gui-evidence',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();source=args.gui_evidence.resolve();target=args.output.resolve()
    if not source.is_relative_to(REPO/'data/ai-ui'):raise RuntimeError('Generated GUI evidence only')
    target.mkdir(parents=True,exist_ok=False)
    pref=json.loads((source/'settings.json').read_text(encoding='utf-8'));selected=pref['profile']
    if not selected.startswith('local:ui-') or '/' in selected or '\\' in selected:raise RuntimeError('Expected test-generated GUI preference')
    folder=REPO/'data/ai-profiles';name=selected.removeprefix('local:')
    paths=[folder/name,folder/('gpu-'+uuid.uuid4().hex[:8]+'-missing.json'),folder/('gpu-'+uuid.uuid4().hex[:8]+'-invalid.json')]
    if any(p.exists() for p in paths):raise RuntimeError('Do not overwrite configs')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source/'media').iterdir()}
    for filename in ('catalog.sqlite','catalog.sqlite.ai.sqlite'):
        with sqlite3.connect((source/filename).as_uri()+'?mode=ro',uri=True) as old,sqlite3.connect(target/filename) as new:old.backup(new)
    settings=target/'settings.json';settings.write_text(json.dumps(pref),encoding='utf-8')
    base='http://127.0.0.1:8769';headers={};process=None;logs=[];report={'pass':False,'checks':[],'starts':[],'gui_preference':pref}
    def api(route,body=None,expected=200):
        request=urllib.request.Request(base+route,None if body is None else json.dumps(body).encode(),headers={**headers,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=180) as response:result=json.load(response);code=response.status
        except urllib.error.HTTPError as ex:
            with ex:result=json.load(ex);code=ex.code
        if code!=expected:raise RuntimeError(f'{route} HTTP {code}')
        return result
    def check(name,value):
        if not value:raise RuntimeError(name)
        report['checks'].append(name)
    def stop():
        nonlocal process
        if process:process.terminate();process.wait(timeout=10);process=None
        for f in logs:f.close()
        logs.clear();time.sleep(1)
    def start(label,override=None):
        nonlocal process,headers
        try:urllib.request.urlopen(base+'/api/session',timeout=.5).close()
        except urllib.error.HTTPError:raise RuntimeError('Port occupied')
        except urllib.error.URLError:pass
        else:raise RuntimeError('Port occupied')
        cmd=[sys.executable,'app/production_server.py','--db',str(target/'catalog.sqlite'),'--ai-settings',str(settings)]
        if override:cmd+=['--ai-profile',str(override)]
        logs.extend((target/(label+'.'+suffix)).open('w',encoding='utf-8') for suffix in ('out','err'))
        process=subprocess.Popen(cmd,cwd=REPO,stdout=logs[0],stderr=logs[1],creationflags=subprocess.CREATE_NO_WINDOW,env={**os.environ,'PYTHONIOENCODING':'utf-8'})
        for _ in range(100):
            if process.poll() is not None:raise RuntimeError('Owned API failed')
            try:session=api('/api/session');headers={'X-Aredoko-Token':session['token'],'Origin':base};break
            except urllib.error.URLError:time.sleep(.1)
        report['starts'].append({'phase':label,'pid':process.pid,'profiles':api('/api/library/ai/profiles'),'status':api('/api/library/ai/status')})
    def status():return api('/api/library/ai/status')
    def query():
        result=api('/api/library/ai/search',{'query':'傘が必要な暗い都会の景色','source':'text'})
        check('CUDA Japanese hit',status()['device']=='cuda' and result['items'][0]['title']=='雨の夜の街並み.wav')
    try:
        profile=DEFAULT_PROFILE.to_dict();profile.update(label='GUI test text',modalities=['text'],precision='float32')
        paths[0].write_text(json.dumps(profile),encoding='utf-8')
        missing={**profile,'label':'GPU missing test','directory':paths[1].stem+'-weights'};paths[1].write_text(json.dumps(missing),encoding='utf-8')
        paths[2].write_text('{invalid',encoding='utf-8')
        start('gui-text');text_key=status()['profile'];check('GUI saved preference applied on restart',api('/api/library/ai/profiles')['active']==selected and status()['modalities']==['text'] and status()['indexed']==0)
        api('/api/library/ai/index',{})
        for _ in range(480):
            if status()['state'] in ('complete','failed'):break
            time.sleep(.5)
        check('Separate text index built',status()['state']=='complete' and status()['indexed']==17);query()
        check('Text-only cover fallback',bool(api('/api/library/ai/search',{'query':'青い画像','source':'cover'},503)['error']))
        chosen=api('/api/library/ai/profile',{'id':'default'});check('No hot swap on selection',chosen['active']==selected and status()['profile']==text_key and chosen['restart_required']);stop()
        start('default');check('Original index reused without rebuild',status()['profile']==DEFAULT_PROFILE.key and status()['state']=='complete' and status()['indexed']==17);query()
        result=api('/api/library/ai/search',{'query':'青い画像','source':'cover'});check('Cover vectors reused',result['items'][0]['title'] in ('book-01.cbz','image-01.png'))
        api('/api/library/ai/profile',{'id':'local:'+paths[1].name});stop();start('missing');check('Missing optional AI disabled',not status()['available']);check('Literal with missing weights',api('/api/items')['total']==17);stop()
        settings.write_text(json.dumps({'version':1,'profile':'local:'+paths[2].name}),encoding='utf-8');start('invalid');check('Invalid selected optional AI disabled',not status()['available'] and bool(api('/api/library/ai/profiles')['error']));check('Literal with invalid config',api('/api/items')['total']==17);stop()
        settings.write_text('{corrupt',encoding='utf-8');start('override',REPO/'config/ai-profiles/embeddinggemma-2.json');check('Explicit override beats corrupt settings',api('/api/library/ai/profiles')['command_line_override'] and status()['profile']==DEFAULT_PROFILE.key);query();api('/api/library/ai/profile',{'id':'default'});stop()
        check('Source hashes unchanged',hashes=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source/'media').iterdir()});report['pass']=True
    except Exception as ex:report['error']=str(ex);raise
    finally:
        stop()
        for p in paths:
            if p.resolve().parent!=folder.resolve():raise RuntimeError('Unsafe cleanup')
            p.unlink(missing_ok=True)
        (target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'pass':report['pass'],'checks':report['checks']},ensure_ascii=True))

if __name__=='__main__':main()
