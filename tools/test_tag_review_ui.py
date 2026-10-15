"""One native Windows tag-review batch, using only generated sandbox media.

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
from production_server import production_handler
from tag_suggestions import TagSuggestions,TaggerInfo,TagProposal
import secrets

class FixtureTagger:
    info=TaggerInfo('ui-fixture','1','not-a-real-model','fixed','cover-v1')
    available=True
    delay=False
    entered=threading.Event()
    def status(self):return {'available':self.available,'reason':'' if self.available else '生成fixtureのモデル未接続テストです。'}
    def suggest(self,source,cancelled):
        self.entered.set()
        if self.delay:
            if not cancelled.wait(30):raise RuntimeError('fixture cancel timeout')
        return [TagProposal('candidate-one','生成fixtureの先頭画像。AI精度の測定ではありません。'),TagProposal('candidate-two','生成fixtureの2つ目の候補。')]



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
    env={**os.environ,'WINAPP_UI_WORKFLOW_ID':'aredoko-tag-review-'+uuid.uuid4().hex}
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
    def enabled(identifier,value):ui('wait-for',identifier,'-p','IsEnabled','--value',str(value),'-t','12000')
    def contains(identifier,text):
        value=ui('get-value',identifier)
        check(identifier+' contains '+text,text in value)
    def visible(identifier):
        ui('scroll-into-view',identifier)
        ui('wait-for',identifier,'-p','IsOffscreen','--value','False','-t','5000')
        tree=json.loads(ui('inspect','--json','--depth','16'))
        matches=[n for n in nodes(tree) if n.get('automationId')==identifier]
        check(identifier+' has visible nonzero bounds',len(matches)==1 and matches[0].get('width',0)>0 and matches[0].get('height',0)>0 and not matches[0].get('isOffscreen',True))
    def open_review():
        ui('scroll-into-view','BtnTagSuggestions');ui('invoke','BtnTagSuggestions');ui('wait-for','TagStatus','-t','12000');enabled('TagRefresh',True)
    def proposal(state='pending'):
        with sandbox.catalog.connect() as db:
            return db.execute('SELECT p.id FROM tag_proposals p JOIN tag_proposal_batches b ON b.id=p.batch_id WHERE b.item_id=? AND p.state=? ORDER BY p.id LIMIT 1',(source,state)).fetchone()[0]
    try:
        sandbox=SimilaritySandbox(target/'fixture',args.scenario);target.mkdir(parents=True,exist_ok=True)
        tagger=FixtureTagger()
        server.RequestHandlerClass=production_handler(sandbox.catalog,secrets.token_urlsafe(32),ai=sandbox.ai,profiles=sandbox.profiles,tagger=tagger)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
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
            name='generated-003.png' if theme=='Light' else 'generated-004.png';source=sandbox.item(name)
            ui('set-value','TxtQuery',name);time.sleep(.4);ui('invoke','BtnSearch');ready();wait('TxtCount','1 件')
            ui('invoke','Item'+str(source),'--action','select');wait('TxtEditStatus','保存済み')
            ui('set-value','TxtTags','unsaved-review');wait('TxtEditStatus','未保存の変更');open_review()
            contains('TagProvenance','まだ候補がありません');contains('TagStatus','未保存の編集')
            ui('invoke','TagGenerate');enabled('TagRefresh',True);ui('wait-for','TagCandidate'+str(proposal()),'-t','12000')
            enabled('TagAccept',False);enabled('TagReject',True);contains('TagExplanation','生成fixture')
            ui('wait-for','TagEvidence','-p','IsOffscreen','--value','False','-t','5000');time.sleep(.3);shot(theme+'-dirty-review')
            ui('invoke','TagClose');wait('TxtTags','unsaved-review');wait('TxtQuery',name);wait('TxtCount','1 件');check(theme+' unsaved metadata and query preserved',True)
            ui('invoke','BtnSave');wait('TxtEditStatus','保存しました');open_review();enabled('TagAccept',True)
            ui('set-value','TagEdited','approved-edit');ui('invoke','TagAccept');enabled('TagRefresh',True)
            ui('invoke','TagCandidate'+str(proposal()),'--action','select');ui('invoke','TagReject');enabled('TagRefresh',True)
            contains('TagProvenance','not-a-real-model');shot(theme+'-reviewed')
            owned(foreground=True);ui('send-keys','tab');ui('send-keys','escape');ready();wait('TxtTags','unsaved-review, approved-edit');wait('TxtQuery',name)
            report['keyboard_tested']=True
            check(theme+' approval unions saved manual tag and exact edit',sandbox.catalog.get(source)['tags']==['unsaved-review','approved-edit'])
            # Distinct fixture producer versions create bounded history pages.
            service=TagSuggestions(sandbox.catalog,tagger)
            for version in range(12):
                tagger.info=TaggerInfo('ui-fixture',theme+str(version),'not-a-real-model','fixed','cover-v1');service.generate(source,uuid.uuid4().hex)
            open_review();enabled('TagOlder',True);ui('invoke','TagOlder');enabled('TagRefresh',True);enabled('TagOlder',False)
            check(theme+' older history page loaded',True);ui('invoke','TagRefresh');enabled('TagRefresh',True)
            tagger.available=False;ui('invoke','TagRefresh');enabled('TagRefresh',True);enabled('TagGenerate',False);contains('TagStatus','未接続');enabled('TagAccept',True)
            tagger.available=True
            user32.SetWindowPos(int(hwnd),None,0,0,700,620,0x0014);time.sleep(.3)
            visible('TagProvenance');shot(theme+'-narrow-provenance')
            visible('TagEdited');ui('set-value','TagEdited','narrow-edit');visible('TagAccept');shot(theme+'-narrow-edit')
            ui('invoke','TagAccept');enabled('TagRefresh',True)
            check(theme+' approval works after live resize','narrow-edit' in sandbox.catalog.get(source)['tags'])
            user32.SetWindowPos(int(hwnd),None,0,0,1200,820,0x0014);time.sleep(.3)
            visible('TagProvenance');shot(theme+'-resize-restored')
            # Fault injection changes only the synthetic proposal DB, never media.
            with sandbox.catalog.connect() as db:db.execute('UPDATE tag_proposal_batches SET source_revision=? WHERE id=(SELECT max(id) FROM tag_proposal_batches WHERE item_id=?)',('0'*64,source));db.execute('UPDATE tag_proposal_batches SET evidence_json=json_set(evidence_json,\'$.revision\',?) WHERE item_id=? AND source_revision=?',('0'*64,source,'0'*64))
            ui('invoke','TagRefresh');enabled('TagRefresh',True);enabled('TagAccept',False);enabled('TagReject',False);contains('TagProvenance','元ファイルが変わっています')
            user32.SetWindowPos(int(hwnd),None,0,0,700,620,0x0014);time.sleep(.3);visible('TagProvenance');shot(theme+'-narrow-stale');ui('invoke','TagClose');ready()
            open_review();visible('TagProvenance');shot(theme+'-narrow-fresh-open');visible('TagReject');enabled('TagReject',False);ui('invoke','TagClose');ready()
            tagger.info=TaggerInfo('ui-fixture','cancel-'+theme,'not-a-real-model','fixed','cover-v1');tagger.delay=True;tagger.entered.clear()
            open_review();ui('invoke','TagGenerate');check(theme+' delayed tagger entered',tagger.entered.wait(5))
            ui('invoke','TagClose');ready();ui('wait-for','BtnTagSuggestions','-p','IsEnabled','--value','True','-t','12000');tagger.delay=False
            with sandbox.catalog.connect() as db:check(theme+' close cancels without publishing',db.execute('SELECT count(*) FROM tag_proposal_batches WHERE producer_json LIKE ?',('%cancel-'+theme+'%',)).fetchone()[0]==0)
            check(theme+' original search preserved after cancel',name in ui('get-value','TxtQuery'))
            if theme=='Light':
                user32.SetWindowPos(int(hwnd),None,0,0,1200,820,0x0014)
                book=sandbox.item('generated-cover.cbz');ui('set-value','TxtQuery','generated-cover.cbz');time.sleep(.4);ui('invoke','BtnSearch');ready()
                ui('invoke','Item'+str(book),'--action','select');open_review();ui('invoke','TagGenerate');enabled('TagRefresh',True)
                contains('TagProvenance','本の先頭ページのみ');time.sleep(.3);shot('Light-cbz-cover');ui('invoke','TagClose');ready()
            close()
        check('source bytes/mtime unchanged',sandbox.source_before==sandbox.source_digest())
        check('saved AI settings unchanged',sandbox.settings_before==(sandbox.target/'settings.json').read_bytes())
        check('no inference or model loaded',sandbox.encoder.calls==0 and not sandbox.encoder.resident)
        report['runtime_pass']=True
    except Exception as ex:
        report['error']=str(ex)
        if hwnd:
            try:shot('failure')
            except Exception:pass
        raise
    finally:
        try:close()
        finally:
            if thread:server.shutdown();thread.join(5)
            server.server_close()
            if sandbox:
                report['source_unchanged']=sandbox.source_before==sandbox.source_digest()
                if not report['source_unchanged'] or report.get('cleanup_terminated_owned_process'):report['runtime_pass']=False
                sandbox.close()
            if target.exists():(target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            try:cli('ui','yield')
            except Exception:pass
    print(json.dumps({'runtime_pass':report['runtime_pass'],'checks':len(report['checks']),'visual_review':report['visual_review']}))
    if not report['runtime_pass']:raise RuntimeError('Native checks failed; inspect result.json')

if __name__=='__main__':main()
