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
import hashlib
from create_preview_fixture import png
from previews import PreviewReader, ReaderChanged

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
    parser.add_argument('--check-ui-cleanup',action='store_true')
    parser.add_argument('--scenario',choices=('indexed','unindexed','text-only'),default='indexed')
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--candidate-search-only',action='store_true')
    modes.add_argument('--folder-books-only',action='store_true')
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
        'scenario':args.scenario,'test_mode':'folder-books' if args.folder_books_only else 'candidate-search' if args.candidate_search_only else 'tag-review','checks':[],'screenshots':[],'requests':[],'keyboard_tested':False}
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
    def choose_combo(combo_id,option_id_or_name):
        ui('invoke',combo_id);time.sleep(.25)
        windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
        ordered=[w for w in windows if w.get('title')=='PopupHost']+[w for w in windows if str(w.get('hwnd'))==hwnd]
        for window in ordered:
            handle=str(window['hwnd']);owned(handle)
            tree=json.loads(ui('inspect','--json','--depth','14',window=handle))
            for n in nodes(tree):
                if n.get('type')=='ListItem' and (n.get('automationId')==option_id_or_name or n.get('name')==option_id_or_name):
                    ui('invoke',n.get('automationId') or n.get('selector') or option_id_or_name,window=handle);time.sleep(.15);return
        raise RuntimeError(f'Combo option {option_id_or_name} not found in {combo_id}')
    def open_review():
        ui('scroll-into-view','BtnTagSuggestions');ui('invoke','BtnTagSuggestions');ui('wait-for','TagStatus','-t','12000');enabled('TagRefresh',True)
    def proposal(state='pending'):
        with sandbox.catalog.connect() as db:
            return db.execute('SELECT p.id FROM tag_proposals p JOIN tag_proposal_batches b ON b.id=p.batch_id WHERE b.item_id=? AND p.state=? ORDER BY p.id LIMIT 1',(source,state)).fetchone()[0]
    try:
        sandbox=SimilaritySandbox(target/'fixture',args.scenario);target.mkdir(parents=True,exist_ok=True)
        book_root=None;book_item=None
        if args.folder_books_only:
            book_media=target/'generated-folder-books'
            (book_media/'Generated book').mkdir(parents=True)
            (book_media/'Generated book'/'p10.png').write_bytes(png(300,400,(20,40,200)))
            (book_media/'Generated book'/'p2.png').write_bytes(png(300,400,(20,180,40)))
            (book_media/'Generated book'/'p1.png').write_bytes(png(300,400,(200,40,20)))
            def book_digest():
                return {p.relative_to(book_media).as_posix():(p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest()) for p in book_media.rglob('*') if p.is_file()}
            book_before=book_digest()
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
            hwnd=str(matches[0]['hwnd']);user32.SetWindowPos(int(hwnd),None,0,0,1200,820,0x0014);ready();wait('TxtCount','77 件' if args.folder_books_only and theme=='Dark' else '76 件')
            if args.check_ui_cleanup:
                from native_ui_tools import invoke_tool
                visible('BtnTools');visible('BtnLayout');visible('BtnDetails')
                tree=json.loads(ui('inspect','--json','--depth','14'))
                check(theme+' management tools and long hints are absent from default canvas',not any(n.get('automationId') in ('BtnAIIndex','BtnRelatedTerms','TxtSearchMethodHint') and not n.get('isOffscreen',True) for n in nodes(tree)))
                shot(theme+'-library-compact')
                invoke_tool(cli,app_pid,hwnd,'BtnAIIndex')
                ui('wait-for','AIProfileChoice','-t','12000');ui('invoke','CloseButton')
                ui('wait-for','AIProfileChoice','--gone','-t','12000');ready()
                check(theme+' AI preparation remains reachable through Tools',True)
                invoke_tool(cli,app_pid,hwnd,'BtnRelatedTerms')
                ui('wait-for','RelatedTermsDialog','-t','12000');ui('invoke','CloseButton')
                ui('wait-for','RelatedTermsDialog','--gone','-t','12000');ready()
                check(theme+' related-term editing remains reachable through Tools',True)
                ui('invoke','BtnStatusDetails')
                detail=None
                for _ in range(20):
                    windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
                    ordered=[w for w in windows if str(w.get('hwnd'))==hwnd]+[w for w in windows if w.get('title')=='PopupHost']
                    for w in ordered:
                        handle=str(w['hwnd'])
                        try:tree=json.loads(ui('inspect','--json','--depth','14',window=handle))
                        except RuntimeError as ex:
                            # A dismissed menu host can disappear between list and inspect.
                            if 'AppNotFoundException' in str(ex):continue
                            raise
                        found=[n for n in nodes(tree) if n.get('automationId')=='TxtStatusDetails' and not n.get('isOffscreen',True)]
                        if found:detail=found[0];break
                    if detail:break
                    time.sleep(.1)
                check(theme+' full search explanation is readable on demand',detail is not None and '名前・タグ' in detail.get('name',''))
                owned(foreground=True);ui('send-keys','escape')
                ui('invoke','ExpandSearchOptions');ui('wait-for','TxtSearchMethodHint','-p','IsOffscreen','--value','False','-t','12000')
                check(theme+' search method help remains under search options',True)
                ui('invoke','ExpandSearchOptions');ready()
            if args.folder_books_only:
                if theme=='Light':
                    ui('invoke','BtnRoots');ui('wait-for','BtnToggleAddFolder','-t','12000');ui('invoke','BtnToggleAddFolder')
                    ui('set-value','RootPath',str(book_media));visible('RootFolderBooks')
                    ui('invoke','RootFolderBooks');ui('invoke','RootConsent')
                    shot('Light-folder-book-registration')
                    user32.SetWindowPos(int(hwnd),None,0,0,800,820,0x0014);time.sleep(.3)
                    visible('RootFolderBooks');shot('Light-folder-book-registration-narrow')
                    user32.SetWindowPos(int(hwnd),None,0,0,1200,820,0x0014);time.sleep(.3)
                    ui('invoke','AddRoot');enabled('AddRoot',True)
                    roots=[r for r in sandbox.catalog.index.roots() if r['path']==str(book_media)]
                    check('GUI opt-in root registered',len(roots)==1 and roots[0]['folder_books'])
                    book_root=roots[0]['id'];ui('wait-for','ScanRoot','-t','12000');visible('ScanRoot');ui('invoke','ScanRoot')
                    for _ in range(100):
                        if sandbox.catalog.scan_state()['state']=='complete':break
                        time.sleep(.1)
                    check('GUI folder-book scan complete',sandbox.catalog.scan_state()['state']=='complete')
                    time.sleep(1.2)
                    found=sandbox.catalog.search(root_id=book_root)['items']
                    check('folder contains one book instead of three loose pages',len(found)==1 and found[0]['kind']=='book' and found[0]['relative_path']=='Generated book/')
                    book_item=found[0]['id']
                    reader=PreviewReader(sandbox.catalog);manifest=reader.manifest(book_item)
                    actual=[reader.read_page(book_item,i,manifest['revision'])[0] for i in range(3)]
                    check('natural page order p1 p2 p10',actual==[(book_media/'Generated book'/n).read_bytes() for n in ('p1.png','p2.png','p10.png')])
                    ui('invoke','BtnBackToLibrary');ready()
                ui('set-value','TxtQuery','Generated book');time.sleep(.4);ui('invoke','BtnSearch');ready();wait('TxtCount','1 件')
                ui('invoke','Item'+str(book_item),'--action','select');wait('TxtEditStatus','保存済み')
                enabled('BtnOpenBook',True);enabled('BtnTagSuggestions',True)
                if theme=='Light':
                    ui('set-value','TxtTags','folder-manual');ui('set-value','TxtShelf','folder-shelf');ui('invoke','ChkFavorite')
                    ui('invoke','BtnSave');wait('TxtEditStatus','保存しました')
                else:
                    wait('TxtTags','folder-manual');wait('TxtShelf','folder-shelf')
                    check('metadata and favorite survive process restart',sandbox.catalog.get(book_item)['favorite'])
                shot(theme+'-folder-book-details')
                ui('scroll-into-view','BtnOpenBook');ui('invoke','BtnOpenBook')
                viewer=None
                for _ in range(40):
                    windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
                    matches=[str(w['hwnd']) for w in windows if str(w.get('hwnd'))!=hwnd and 'Aredoko' in w.get('title','') and w.get('title')!='PopupHost']
                    if len(matches)==1:viewer=matches[0];break
                    time.sleep(.1)
                check(theme+' owned reader window opened',viewer is not None);owned(viewer)
                ui('wait-for','ReaderPageNumber','--value','1 / 3' if theme=='Light' else '2 / 3','-t','12000',window=viewer)
                ui('wait-for','ReaderStatus','--value','表示しました。拡大すると細部を確認できます。','-t','12000',window=viewer)
                check(theme+' reader loaded expected page',True)
                # F10 pins controls for repeatable screenshots and keyboard navigation.
                user32.SetForegroundWindow(int(viewer));time.sleep(.15)
                check('only owned reader is foreground',user32.GetForegroundWindow()==int(viewer))
                ui('send-keys','f10',window=viewer)
                if theme=='Light':
                    ui('send-keys','right',window=viewer)
                    ui('wait-for','ReaderPageNumber','--value','2 / 3','-t','12000',window=viewer)
                    for _ in range(80):
                        saved=sandbox.catalog.reader_progress(book_item)['progress']
                        if saved and saved['page']==1:break
                        time.sleep(.1)
                    check('right key advances and persists folder-book position',saved is not None and saved['page']==1)
                    report['keyboard_tested']=True
                user32.SetWindowPos(int(viewer),None,0,0,700,620,0x0014);time.sleep(.4)
                path=target/(theme+'-folder-book-reader-narrow.png')
                ui('screenshot','--output',path,window=viewer);check('screenshot '+path.stem,path.is_file() and path.stat().st_size>0);report['screenshots'].append(path.name)
                ui('send-keys','escape',window=viewer);ready()
                # Tag review uses the same folder-book first-page evidence contract.
                open_review()
                if args.check_ui_cleanup:
                    if theme=='Light':
                        ui('invoke','TagGenerate')
                    ui('wait-for','TagProvenance','--value','not-a-real-model','--contains','-t','12000');enabled('TagRefresh',True)
                    ui('wait-for','TagEvidence','-p','IsOffscreen','--value','False','-t','12000')
                    shot(theme+'-tag-review-compact')
                    ui('scroll-into-view','TagMetadata');ui('invoke','TagMetadata')
                    ui('wait-for','TagModelDetails','-p','IsOffscreen','--value','False','-t','12000')
                    contains('TagModelDetails','モデル版: fixed');contains('TagModelDetails','ui-fixture');contains('TagModelDetails','cover-v1')
                    shot(theme+'-tag-review-model-details')
                    ui('invoke','TagMetadata')
                    user32.SetWindowPos(int(hwnd),None,0,0,700,620,0x0014);time.sleep(.4)
                    visible('TagEdited');visible('TagAccept');shot(theme+'-tag-review-compact-narrow')
                    user32.SetWindowPos(int(hwnd),None,0,0,1200,820,0x0014);time.sleep(.3)
                else:
                    contains('TagProvenance','まだ候補がありません');shot(theme+'-folder-book-tag-entry')
                ui('invoke','TagClose');ready()
                if theme=='Light':
                    # Emulate the old v1 scan token only in this generated DB.
                    from previews import folder_pages
                    pages=sorted(folder_pages(book_media/'Generated book','Generated book/',()))
                    legacy=int.from_bytes(hashlib.sha256(json.dumps(pages,ensure_ascii=False).encode()).digest()[:8],'big')>>1
                    with sandbox.catalog.index.connect() as db:
                        db.execute('UPDATE library_locations SET mtime_ns=? WHERE root_id=? AND relative_path=?',(legacy,book_root,'Generated book/'))
                    try:PreviewReader(sandbox.catalog).manifest(book_item)
                    except ReaderChanged:check('old token requires rescan',True)
                    else:raise RuntimeError('Old token was reused')
                    ui('invoke','BtnRoots');ui('wait-for','ConfigFolder'+str(book_root),'-t','12000')
                    ui('invoke','ConfigFolder'+str(book_root));ui('wait-for','ScanRoot','-t','12000');visible('ScanRoot');ui('invoke','ScanRoot')
                    for _ in range(100):
                        if sandbox.catalog.get(book_item)['mtime_ns']!=legacy and sandbox.catalog.scan_state()['state']=='complete':break
                        time.sleep(.1)
                    fresh=sandbox.catalog.get(book_item)
                    check('GUI rescan upgrades old token and preserves ID metadata',fresh['mtime_ns']!=legacy and fresh['tags']==['folder-manual'] and fresh['shelf']=='folder-shelf' and fresh['favorite'])
                    check('reader reopens after old-token rescan',PreviewReader(sandbox.catalog).manifest(book_item)['page_count']==3)
                check(theme+' generated book source unchanged',book_before==book_digest())
                close();continue
            if args.candidate_search_only:
                service=TagSuggestions(sandbox.catalog,tagger)
                img_item=sandbox.item('generated-003.png')
                book_item=sandbox.item('generated-cover.cbz')
                root2_item=sandbox.item('generated-001.png',1)
                if theme=='Light':
                    sandbox.catalog.update([img_item],{'tags':['confirmed-only-tag']})
                    tagger.info=TaggerInfo('ui-fixture','cand-1','wd-fixture-model','rev1','cover-v1')
                    service.generate(img_item,uuid.uuid4().hex)
                    service.generate(book_item,uuid.uuid4().hex)
                    service.generate(root2_item,uuid.uuid4().hex)
                    # Mark book_item batch stale in synthetic DB to verify stale display in candidate search
                    with sandbox.catalog.connect() as db:
                        db.execute('UPDATE tag_proposal_batches SET source_revision=? WHERE item_id=?',('0'*64,book_item))
                        db.execute("UPDATE tag_proposal_batches SET evidence_json=json_set(evidence_json,'$.revision',?) WHERE item_id=?",('0'*64,book_item))
                # 1. Literal search does not match unapproved candidate tags
                ui('set-value','TxtQuery','candidate-one');time.sleep(.4);ui('invoke','BtnSearch');ready();wait('TxtCount','0 件')
                check(theme+' literal search excludes unapproved candidates',True)
                # 2. Switch to ModeTagCandidates: matches pending candidates across active roots
                choose_combo('CmbSearchMode','ModeTagCandidates');ready();wait('TxtCount','3 件')
                contains('ProposalEvidence'+str(img_item),'未承認タグ候補: candidate-one')
                contains('ProposalEvidence'+str(img_item),'wd-fixture-model')
                contains('ProposalEvidence'+str(img_item),'元ファイル一致')
                contains('ProposalEvidence'+str(book_item),'本の先頭ページのみ')
                contains('ProposalEvidence'+str(book_item),'元ファイル変更あり')
                shot(theme+'-candidate-search-wide')
                # 3. Confirmed tags do not match in ModeTagCandidates
                ui('set-value','TxtQuery','confirmed-only-tag');time.sleep(.4);ui('invoke','BtnSearch');ready();wait('TxtCount','0 件')
                check(theme+' candidate search excludes confirmed tags',True)
                # 4. Empty query in ModeTagCandidates lists all items with pending proposals, and shares folder scope
                ui('set-value','TxtQuery','');time.sleep(.4);ui('invoke','BtnSearch');ready();wait('TxtCount','3 件')
                ui('invoke','NavFolders','--action','select');wait('TxtCount','2 フォルダ')
                ui('invoke',f'OpenFolder{sandbox.roots[0]}');ready();wait('TxtCount','2 件')
                check(theme+' candidate search honors selected folder scope',True)
                user32.SetWindowPos(int(hwnd),None,0,0,700,620,0x0014);time.sleep(.3)
                shot(theme+'-candidate-search-narrow')
                user32.SetWindowPos(int(hwnd),None,0,0,1200,820,0x0014);time.sleep(.3)
                if theme=='Dark':
                    # Approve and reject all pending candidates on Dark img_item (generated-003.png from Light), verify it leaves pending search
                    target_item=sandbox.item('generated-003.png')
                    ui('invoke','Item'+str(target_item),'--action','select');wait('TxtEditStatus','保存済み')
                    open_review();ui('set-value','TagEdited','cand-approved');ui('invoke','TagAccept');enabled('TagRefresh',True)
                    with sandbox.catalog.connect() as db:
                        rem=db.execute("SELECT p.id FROM tag_proposals p JOIN tag_proposal_batches b ON b.id=p.batch_id WHERE b.item_id=? AND p.state='pending'",(target_item,)).fetchone()[0]
                    ui('invoke','TagCandidate'+str(rem),'--action','select');ui('invoke','TagReject');enabled('TagRefresh',True)
                    ui('invoke','TagClose');ready();ui('invoke','BtnSearch');ready();wait('TxtCount','1 件')
                    choose_combo('CmbSearchMode','ModeLiteral');ui('set-value','TxtQuery','cand-approved');time.sleep(.4);ui('invoke','BtnSearch');ready();wait('TxtCount','1 件')
                    check('Dark reviewing all pending proposals removes item from candidate search and exposes approved tag in literal search',True)
                close();continue
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
