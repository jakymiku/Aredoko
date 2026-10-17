"""One native Windows tag-review batch, using only generated sandbox media.

Requires an existing Release build and winapp CLI. No downloads.
--wd-runtime-only explicitly uses the already approved local WD CPU model,
on generated images only. --tag-language-only uses existing EG2 CUDA with
predetermined English labels. --page-image-only uses the same EG2 runtime
on fixed generated Japanese page images directly. Other modes never load a model.
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
    parser.add_argument('--check-scroll-gutters',action='store_true',help='User-requested form scroll lanes, compact page inputs and narrow dialog checks')
    parser.add_argument('--check-ui-cleanup',action='store_true')
    parser.add_argument('--check-user-feedback',action='store_true')
    parser.add_argument('--scenario',choices=('indexed','unindexed','text-only'),default='indexed')
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--candidate-search-only',action='store_true')
    modes.add_argument('--wd-runtime-only',action='store_true',help='Existing approved CPU model on generated media only; no downloads')
    modes.add_argument('--tag-language-only',action='store_true',help='Existing EG2 CUDA model with generated sources and predetermined English labels; no downloads')
    modes.add_argument('--pane-boundary-only',action='store_true',help='No-model overlay occlusion, close and resize checks on generated images')
    modes.add_argument('--book-batch-only',action='store_true',help='Generated two-book review, cancel and app-restart resume; no actual models')
    modes.add_argument('--page-coverage-only',action='store_true',help='No-model page counts, gaps, cancellation and restart on generated books')
    modes.add_argument('--page-image-only',action='store_true',help='Existing EG2 CUDA on generated fixed Japanese book pages; no OCR or downloads')
    modes.add_argument('--page-jump-only',action='store_true')
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
    tagger=None;wd_observer=None;wd_processes=[];model_before=None;language_encoder=None;language_process=None
    report={'runtime_pass':False,'visual_review':'pending: inspect every screenshot','actual_model':bool(args.wd_runtime_only or args.tag_language_only or args.page_image_only),'tagging_quality_measured':False,
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
        owned()
        if args.check_scroll_gutters or args.pane_boundary_only or args.book_batch_only:time.sleep(.3) # Let the compositor present the current layout.
        path=target/(name+'.png');ui('screenshot','--output',path)
        check('screenshot '+name,path.is_file() and path.stat().st_size>0);report['screenshots'].append(path.name)
        tree=json.loads(ui('inspect','--json','--depth','12'))
        (target/(name+'-tree.json')).write_text(json.dumps(tree,ensure_ascii=False),encoding='utf-8')
    def context(identifier,source,action="FindSimilar"):
        if identifier.startswith('Item'):ui('scroll-into-view',identifier)
        owned(foreground=True);ui('click',identifier,'--right')
        for _ in range(20):
            windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
            ordered=[w for w in windows if w.get('title')=='PopupHost']+[w for w in windows if str(w.get('hwnd'))==hwnd]
            for window in ordered:
                handle=str(window['hwnd']);owned(handle)
                tree=json.loads(ui('inspect','--json','--depth','14',window=handle))
                matches=[n for n in nodes(tree) if n.get('automationId')==action+str(source)]
                if matches:
                    ui('invoke',action+str(source),window=handle);return
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
    def gutter(viewport_id,control_id):
        tree=json.loads(ui('inspect','--json','--depth','18'))
        viewport=next(n for n in nodes(tree) if n.get('automationId')==viewport_id)
        control=next(n for n in nodes(viewport) if n.get('automationId')==control_id)
        gap=viewport['x']+viewport['width']-control['x']-control['width']
        check(viewport_id+' has scrollbar lane beyond '+control_id,gap>=20)
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
        if args.page_jump_only or args.page_image_only or args.page_coverage_only or args.book_batch_only:
            import zipfile
            from page_index import PageIndex
            from page_text import PageTextIndex
            jump_media=target/'generated-page-jump';jump_media.mkdir()
            jump_file=jump_media/('batch-one.cbz' if args.book_batch_only else 'jump.cbz')
            def write_jump_book(extra=False):
                with zipfile.ZipFile(jump_file,'w') as archive:
                    if extra:archive.writestr('p00.png',png(300,400,(80,80,80)))
                    if args.page_coverage_only or args.book_batch_only:
                        for n in range(35):archive.writestr(f'p{n:03}.png',png(60,80,(n+20,40,70)))
                    elif args.page_image_only:
                        rendered=REPO/'data/ocr-eval/ocr-v1-20261017'
                        receipt=json.loads((rendered/'receipt.json').read_bytes())
                        for filename in ('page-03.png','page-01.png'):
                            entry=next(i for i in receipt['images'] if i['file']==filename)
                            check('fixed generated page digest '+filename,hashlib.sha256((rendered/filename).read_bytes()).hexdigest()==entry['sha256'])
                        archive.writestr('p01.png',png(600,420,(240,240,240)))
                        archive.writestr('p02.png',(rendered/'page-03.png').read_bytes())
                        archive.writestr('p03.png',(rendered/'page-01.png').read_bytes())
                    else:
                        for n,color in enumerate(((180,30,30),(30,180,30),(30,30,180)),1):
                            archive.writestr(f'p{n:02}.png',png(300,400,color))
                if args.book_batch_only:
                    with zipfile.ZipFile(jump_media/'batch-two.cbz','w') as other:
                        for n in range(8):other.writestr(f'p{n:03}.png',png(60,80,(40,n+20,90)))
            jump_root=sandbox.catalog.add_root(str(jump_media))
            page_index=PageIndex(sandbox.catalog)
            class JumpExtractor:
                class info:
                    @staticmethod
                    def record():return {'adapter':'contract-fixture','version':'1','model':'not-real-ocr','model_revision':'1','preprocessing':'page-jump'}
                def extract(self,payload,cancelled):return '夕焼けの教室で約束した'
            page_text=PageTextIndex(sandbox.catalog,page_index,JumpExtractor())
        if args.page_coverage_only or args.book_batch_only:
            class CoverageEncoder:
                available=True
                resident=False
                def __init__(self,ai):self.ai=ai;self.profile=ai.profile;self.calls=0;self.delay=False;self.delay_after=0;self.entered=threading.Event()
                def encode(self,operation,data):
                    self.calls+=1
                    if self.delay and self.calls>self.delay_after:
                        self.entered.set()
                        if not self.ai.cancel.wait(20):raise RuntimeError('Fixture cancel timeout')
                    return [1.0]+[0.0]*(self.profile.dimension-1)
                def close(self):pass
            coverage_encoder=CoverageEncoder(sandbox.ai);sandbox.ai.encoder=coverage_encoder
            sandbox.profiles.set_scope({'root_ids':[jump_root,*sandbox.roots] if args.book_batch_only else [jump_root]});sandbox.settings_before=(sandbox.target/'settings.json').read_bytes()
            report['test_mode']='CPU-page-coverage-and-resume'
        tagger=FixtureTagger()
        if args.tag_language_only or args.page_image_only:
            from ai_process import EncoderProcess
            from ai_profiles import DEFAULT_PROFILE
            from ai_search import AISearch
            language_encoder=EncoderProcess(REPO/'.venv-ai/Scripts/python.exe',DEFAULT_PROFILE.model_path(REPO))
            if not language_encoder.available:raise RuntimeError('Existing approved EG2 runtime required; never downloads')
            sandbox.ai.close();sandbox.ai=AISearch(sandbox.catalog,language_encoder)
            if args.page_image_only:
                sandbox.profiles.set_scope({'root_ids':[jump_root]})
                sandbox.settings_before=(sandbox.target/'settings.json').read_bytes()
                report['test_mode']='direct-page-images-native'
                report['actual_model_role']='Existing EG2 CUDA; generated Japanese text images directly; no OCR'
            else:
                blue_item=sandbox.item('generated-003.png');red_item=sandbox.item('generated-001.png',1)
                language_scope={'root_ids':sandbox.roots,'kind':'image','shelf':'language-fixture'}
                sandbox.catalog.update([blue_item,red_item],{'tags':['manual-language'],'shelf':'language-fixture'})
                report['test_mode']='Japanese-query-English-pending-tags'
                report['actual_model_role']='EmbeddingGemma 2 CUDA; predetermined English labels, not WD image accuracy'
                report['profile']=DEFAULT_PROFILE.identity()
        if args.wd_runtime_only:
            from wd_tagger import create_tagger
            from unittest.mock import patch
            tagger=create_tagger(sandbox.ai)
            if not tagger.status()['available']:raise RuntimeError('Approved local WD installation is unavailable; no download attempted')
            directory=tagger.profile.verify(REPO,hashes=True)
            model_before={name:(directory/name).stat().st_mtime_ns for name in tagger.profile.data()['artifacts']}
            report['test_mode']='wd-cpu-runtime'
            report['profile_key']=tagger.profile.key
            report['device']='cpu'
            real_popen=subprocess.Popen
            def observe(args,**kwargs):
                child=real_popen(args,**kwargs)
                if isinstance(args,list) and any(Path(str(part)).name=='tagger_worker.py' for part in args):wd_processes.append(child)
                return child
            wd_observer=patch('wd_tagger.subprocess.Popen',side_effect=observe);wd_observer.start()
        server.RequestHandlerClass=production_handler(sandbox.catalog,secrets.token_urlsafe(32),ai=sandbox.ai,profiles=sandbox.profiles,tagger=tagger)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        for theme in ('Light','Dark'):
            if args.tag_language_only:
                tagger.info=TaggerInfo('language-fixture',theme,'predetermined-English-labels','fixed','cover-v1')
                for item,tags in ((blue_item,['blue_hair','twintails']),(red_item,['red_hair','long_hair'])):
                    tagger.suggest=lambda source,cancelled,tags=tags:[TagProposal(tag,'Predetermined English runtime fixture; not tagging quality') for tag in tags]
                    TagSuggestions(sandbox.catalog,tagger).generate(item,uuid.uuid4().hex)
            if args.page_jump_only or args.page_image_only or args.page_coverage_only or args.book_batch_only:
                if args.page_jump_only or theme=='Light':write_jump_book()
                sandbox.catalog.index.scan(jump_root);sandbox.catalog.sync_index()
                jump_item=next(r['id'] for r in sandbox.catalog.search(root_id=jump_root)['items'] if r['relative_path']==jump_file.name)
                page_index.refresh(jump_item);snapshot=page_index.list(jump_item)
                if args.page_jump_only:page_text.generate(jump_item,[snapshot['pages'][1]['page_id']],snapshot['source_revision'],uuid.uuid4().hex)
                else:sandbox.catalog.update([jump_item],{'tags':['manual-page'],'shelf':'ページ試験','favorite':True})
                if args.page_coverage_only and theme=='Light':
                    sandbox.ai.pages.start(jump_item,[p['page_id'] for p in snapshot['pages'][16:32]],snapshot['source_revision'],{'root_ids':[jump_root]})
                    sandbox.ai.worker.join(10);check('fixture has a disjoint middle range',sandbox.ai.status()['state']=='complete')
                with sandbox.catalog.connect() as db:db.execute('DELETE FROM reader_progress WHERE item_id=?',(jump_item,))
            launch=json.loads(cli('run','src/Aredoko.WinUI','-c','Release','--arch','x64','-p','Platform=x64','-p','SelfContained=true','--no-build',
                '--output-appx-directory',target/('layout-'+theme.lower()),'--detach','--json','--args','--ui-theme '+theme.lower()+' --viewer-settings '+str(target/'viewer-settings.json')))
            if launch.get('ProcessScope') not in (None,'local'):raise RuntimeError('Unexpected launch scope')
            app_pid=int(launch['ProcessId']);process=kernel32.OpenProcess(0x00100001,False,app_pid)
            if not process:raise ctypes.WinError(ctypes.get_last_error())
            for _ in range(50):
                windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
                matches=[w for w in windows if w.get('hwnd') and 'Aredoko' in w.get('title','') and w.get('title')!='PopupHost']
                if len(matches)==1:break
                time.sleep(.1)
            if len(matches)!=1:raise RuntimeError('Expected one owned main window')
            hwnd=str(matches[0]['hwnd']);user32.SetWindowPos(int(hwnd),None,0,0,1200,820,0x0014);ready();wait('TxtCount','78 件' if args.book_batch_only else '77 件' if args.page_jump_only or args.page_image_only or args.page_coverage_only or args.book_batch_only or args.folder_books_only and theme=='Dark' else '76 件')
            if args.book_batch_only:
                report['test_mode']='bounded-book-page-batch'
                second=next(r['id'] for r in sandbox.catalog.search(root_id=jump_root)['items'] if r['relative_path']=='batch-two.cbz')
                if theme=='Light':
                    originals={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in jump_media.glob('*.cbz')}
                    ui('set-value','TxtQuery','batch');time.sleep(.4);ui('invoke','BtnSearch');ready();wait('TxtCount','2 件')
                    ui('invoke','Item'+str(jump_item),'--action','select');wait('TxtEditStatus','保存済み')
                    ui('set-value','TxtTags','draft-batch');wait('TxtEditStatus','未保存の変更')
                    context('Item'+str(jump_item),jump_item,'IndexBookBatch');ui('wait-for','BatchBooks','-t','12000')
                    ui('invoke','BatchBook'+str(second),'--action','toggle-on');ui('set-value','BatchPageLimit','32')
                    ui('invoke','BatchPreview');enabled('BatchStart',True);contains('BatchSummary','2冊・24ページ')
                    check('preview never infers',coverage_encoder.calls==0);shot('Light-batch-preview')
                    user32.SetWindowPos(int(hwnd),None,0,0,700,620,0x0014);time.sleep(.4)
                    visible('BatchStart');shot('Light-batch-narrow')
                    coverage_encoder.delay=True;coverage_encoder.delay_after=16
                    ui('invoke','BatchStart');check('second book delayed after completed first',coverage_encoder.entered.wait(10))
                    ui('wait-for','BatchSummary','--value','完了: 1/2','--contains','-t','12000');contains('BatchSummary','完了: 1/2');ui('invoke','BatchCancel');enabled('BatchResume',True)
                    contains('BatchSummary','保存済み 16/24');shot('Light-batch-cancelled')
                    coverage_encoder.delay=False;sandbox.ai.worker.join(5)
                    check('cancel keeps completed first book',sandbox.ai.status()['indexed']==16 and sandbox.ai.status()['state']=='cancelled')
                    ui('invoke','CloseButton');ready()
                    tree=json.loads(ui('inspect','--json','--depth','14'))
                    if not any(n.get('automationId')=='TxtTags' and not n.get('isOffscreen',True) for n in nodes(tree)):ui('invoke','BtnDetails')
                    check('batch preserves dirty tags','draft-batch' in ui('get-value','TxtTags'))
                    ui('set-value','TxtTags','manual-page');wait('TxtEditStatus','保存済み')
                else:
                    from native_ui_tools import invoke_tool
                    invoke_tool(cli,app_pid,hwnd,'BtnAIIndex');ui('wait-for','ResumeBookBatch','-t','12000')
                    ui('invoke','AIScopeOptions','--action','expand');enabled('ResumeBookBatch',True)
                    visible('ResumeBookBatch');shot('Dark-persisted-batch')
                    before=coverage_encoder.calls;ui('invoke','ResumeBookBatch')
                    ui('wait-for','AIStatus','--value','保存済み 24/24','--contains','-t','20000')
                    sandbox.ai.worker.join(5);state=sandbox.ai.status()
                    check('resumed exact selected ranges with first book reused',state['state']=='complete' and state['indexed']==24 and state['reused']==16 and coverage_encoder.calls-before==8)
                    shot('Dark-batch-complete')
                    user32.SetWindowPos(int(hwnd),None,0,0,700,620,0x0014);time.sleep(.4);shot('Dark-batch-settings-narrow')
                    ui('invoke','CloseButton');ready()
                    check('generated books unchanged',originals=={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in originals})
                close();continue
            if args.pane_boundary_only:
                report['test_mode']='detail-pane-boundary'
                name='generated-003.png';item=sandbox.item(name)
                original_tags=sandbox.catalog.get(item)['tags']
                ui('set-value','TxtQuery',name);time.sleep(.4);ui('invoke','BtnSearch');ready()
                ui('invoke','Item'+str(item),'--action','select');wait('TxtEditStatus','保存済み')
                visible('BtnSearch')
                tree=json.loads(ui('inspect','--json','--depth','14'))
                tags=next(n for n in nodes(tree) if n.get('automationId')=='TxtTags')
                for identifier in ('BtnSearch','BtnRoots'):
                    control=next(n for n in nodes(tree) if n.get('automationId')==identifier)
                    check(theme+' inline gap separates '+identifier,tags['x']-(control['x']+control['width'])>=32)
                shot(theme+'-inline-pane')
                def ensure_pane():
                    tree=json.loads(ui('inspect','--json','--depth','14'))
                    if not any(n.get('automationId')=='BtnCloseDetails' and not n.get('isOffscreen',True) for n in nodes(tree)):
                        ui('invoke','BtnDetails')
                    ui('wait-for','BtnCloseDetails','-p','IsOffscreen','--value','False','-t','5000')
                ui('set-value','TxtTags','draft-boundary');wait('TxtEditStatus','未保存の変更')
                for width in (700,820):
                    user32.SetWindowPos(int(hwnd),None,0,0,width,620,0x0014);time.sleep(.4)
                    ensure_pane();visible('BtnCloseDetails');visible('TxtTags')
                    tree=json.loads(ui('inspect','--json','--depth','14'))
                    search=next(n for n in nodes(tree) if n.get('automationId')=='BtnSearch')
                    check(theme+f' overlay {width} clips fully occluded Search button',search.get('isOffscreen') is True)
                    check(theme+f' overlay {width} preserves draft','draft-boundary' in ui('get-value','TxtTags'))
                    shot(theme+f'-overlay-{width}')
                user32.SetWindowPos(int(hwnd),None,0,0,1200,820,0x0014);time.sleep(.4)
                ensure_pane();visible('BtnSearch');check(theme+' inline resize preserves draft','draft-boundary' in ui('get-value','TxtTags'))
                ui('set-value','TxtTags',', '.join(original_tags));wait('TxtEditStatus','保存済み')
                user32.SetWindowPos(int(hwnd),None,0,0,700,620,0x0014);time.sleep(.4)
                ensure_pane();ui('invoke','BtnCloseDetails');ready();visible('BtnSearch');shot(theme+'-pane-closed')
                ui('invoke','BtnSearch');ready();wait('TxtCount','1 件')
                check(theme+' closing restores working search',True)
                check(theme+' manual metadata unchanged',sandbox.catalog.get(item)['tags']==original_tags)
                close();continue
            if args.tag_language_only:
                from tag_semantics import semantic_candidates
                choose_combo('CmbSearchMode','ModeTagSemantic');ready()
                ui('set-value','TxtQuery','青髪のツインテール');time.sleep(.4);ui('invoke','BtnSearch');ready();wait('TxtCount','0 件')
                check(theme+' index update warning visible',any('索引の更新が必要' in n.get('name','') and not n.get('isOffscreen',True) for n in nodes(json.loads(ui('inspect','--json','--depth','14')))))
                shot(theme+'-pending-index-needed')
                def prepare_language_index():
                    sandbox.ai.start(scope=language_scope);sandbox.ai.worker.join(180)
                    check(theme+' explicit scoped AI index complete',not sandbox.ai.worker.is_alive() and sandbox.ai.status()['state']=='complete' and sandbox.ai.status()['indexed']==2)
                prepare_language_index()
                ui('invoke','BtnSearch');ready();wait('TxtCount','2 件')
                actual=semantic_candidates(TagSuggestions(sandbox.catalog,tagger),sandbox.ai,'青髪のツインテール')
                check(theme+' actual EG2 ranks English blue_hair/twintails first from Japanese query',actual['items'][0]['id']==blue_item)
                contains('ProposalEvidence'+str(blue_item),'タグ候補の意味一致')
                contains('ProposalEvidence'+str(blue_item),'blue_hair')
                shot(theme+'-Japanese-pending-wide')
                user32.SetWindowPos(int(hwnd),None,0,0,700,620,0x0014);time.sleep(.3)
                shot(theme+'-Japanese-pending-narrow')
                user32.SetWindowPos(int(hwnd),None,0,0,1200,820,0x0014);time.sleep(.3)
                ui('invoke','NavFolders','--action','select');wait('TxtCount','2 フォルダ')
                ui('invoke',f'OpenFolder{sandbox.roots[1]}');ready();wait('TxtCount','1 件')
                check(theme+' Japanese pending semantic search honors selected root',True)
                ui('invoke','NavAll','--action','select');ready()
                # Reset explicit root selection through the existing scope toolbar.
                ui('invoke','ExpandSearchOptions');visible('BtnResetAllFolders');ui('invoke','BtnResetAllFolders');ready();wait('TxtCount','2 件')
                choose_combo('CmbSearchMode','ModeTagCandidates');ui('set-value','TxtQuery','blue_hair');time.sleep(.4);ui('invoke','BtnSearch');ready();wait('TxtCount','1 件')
                check(theme+' original literal pending-tag mode remains available',True)
                if theme=='Light':
                    ui('invoke','Item'+str(blue_item),'--action','select');wait('TxtEditStatus','保存済み');open_review()
                    contains('TagEdited','blue_hair');ui('invoke','TagAccept');enabled('TagRefresh',True)
                    ui('invoke','TagClose');ready()
                    check('English approval preserves raw label and manual metadata',set(sandbox.catalog.get(blue_item)['tags'])=={'manual-language','blue_hair'})
                    choose_combo('CmbSearchMode','ModeTagSemantic');ui('set-value','TxtQuery','青髪');time.sleep(.4);ui('invoke','BtnSearch');ready();wait('TxtCount','1 件')
                    check(theme+' index update warning visible',any('索引の更新が必要' in n.get('name','') and not n.get('isOffscreen',True) for n in nodes(json.loads(ui('inspect','--json','--depth','14')))))
                    prepare_language_index()
                    choose_combo('CmbSearchMode','ModeText');ui('invoke','BtnSearch');ready();wait('TxtCount','1 件')
                    found=sandbox.ai.search('青髪',source='text',scope=language_scope)
                    check('actual EG2 finds approved English blue_hair from Japanese without translating tag',found['items'][0]['id']==blue_item)
                    shot('Light-approved-English-Japanese-search')
                else:
                    check('English approval persists across app restart',set(sandbox.catalog.get(blue_item)['tags'])=={'manual-language','blue_hair'})
                close();continue
            if args.wd_runtime_only:
                name='generated-003.png' if theme=='Light' else 'generated-cover.cbz'
                source=sandbox.item(name)
                sandbox.catalog.update([source],{'tags':['manual-native-wd'],'favorite':True,'shelf':'WD検証'})
                ui('set-value','TxtQuery',name);time.sleep(.4);ui('invoke','BtnSearch');ready();wait('TxtCount','1 件')
                ui('invoke','Item'+str(source),'--action','select');wait('TxtEditStatus','保存済み');open_review()
                enabled('TagGenerate',True);ui('invoke','TagGenerate');enabled('TagRefresh',True)
                history=TagSuggestions(sandbox.catalog,tagger).list(source)
                batch=history['batches'][0];candidates=batch['proposals']
                check(theme+' actual WD generated bounded pending candidates',0<len(candidates)<=30 and all(p['state']=='pending' for p in candidates))
                check(theme+' model and source provenance',batch['producer']==tagger.info.record() and not batch['stale'])
                check(theme+' inference does not write confirmed tags',sandbox.catalog.get(source)['tags']==['manual-native-wd'])
                check(theme+' real WD owned worker launched',len(wd_processes)==(1 if theme=='Light' else 2))
                contains('TagProvenance','本の先頭ページのみ' if theme=='Dark' else '画像')
                contains('TagExplanation','正解確率ではありません')
                visible('TagMetadata');ui('invoke','TagMetadata','--action','expand')
                contains('TagModelDetails',tagger.profile.data()['revision'])
                shot(theme+'-actual-wd-model')
                ui('invoke','TagMetadata','--action','collapse');visible('TagProvenance')
                ui('invoke','TagGenerate');enabled('TagRefresh',True)
                check(theme+' regenerate reuses decisions without another worker',len(wd_processes)==(1 if theme=='Light' else 2))
                approved='検証用日本語タグ'+theme
                ui('set-value','TagEdited',approved);ui('invoke','TagAccept');enabled('TagRefresh',True)
                check(theme+' Japanese approval preserves manual tags',set(sandbox.catalog.get(source)['tags'])=={'manual-native-wd',approved})
                selected=candidates[0]
                history=TagSuggestions(sandbox.catalog,tagger).list(source)
                stored=next(p for p in history['batches'][0]['proposals'] if p['id']==selected['id'])
                check(theme+' original English label and Japanese decision are both retained',stored['tag']==selected['tag'] and stored['state']=='accepted' and stored['accepted_tag']==approved)
                current=sandbox.catalog.get(source)
                check(theme+' shelf and favorite retained',current['shelf']=='WD検証' and current['favorite'])
                user32.SetWindowPos(int(hwnd),None,0,0,700,620,0x0014);time.sleep(.3)
                visible('TagEdited');shot(theme+'-actual-wd-narrow-reviewed')
                ui('invoke','TagClose');ready()
                user32.SetWindowPos(int(hwnd),None,0,0,1200,820,0x0014);time.sleep(.3)
                ui('set-value','TxtQuery',approved);time.sleep(.4);ui('invoke','BtnSearch');ready();wait('TxtCount','1 件')
                shot(theme+'-approved-Japanese-search')
                check(theme+' GUI literal search finds edited Japanese approval',True)
                pending=[p for p in history['batches'][0]['proposals'] if p['state']=='pending']
                check(theme+' raw candidates remain separately reviewable',bool(pending))
                tag=pending[0]['tag']
                ui('set-value','TxtQuery',tag);time.sleep(.4);ui('invoke','BtnSearch');ready()
                wait('TxtCount',str(sandbox.catalog.search(tag)['total'])+' 件')
                check(theme+' pending candidate excluded from confirmed tag search',all(r['id']!=source for r in sandbox.catalog.search(tag)['items']))
                choose_combo('CmbSearchMode','ModeTagCandidates');ready()
                from tag_candidate_search import search_candidates
                expected=search_candidates(TagSuggestions(sandbox.catalog,tagger),tag)['total']
                wait('TxtCount',str(expected)+' 件');contains('ProposalEvidence'+str(source),tag)
                shot(theme+'-raw-English-candidate-search')
                close();continue
            if args.page_coverage_only:
                original=(jump_file.read_bytes(),jump_file.stat().st_mtime_ns);before_calls=coverage_encoder.calls
                ui('set-value','TxtQuery','jump.cbz');time.sleep(.4);ui('invoke','BtnSearch');ready();wait('TxtCount','1 件')
                ui('invoke','Item'+str(jump_item),'--action','select');wait('TxtEditStatus','保存済み')
                ui('set-value','TxtTags','draft-coverage');wait('TxtEditStatus','未保存の変更')
                context('Item'+str(jump_item),jump_item,'IndexBookPages');enabled('PageAIAdd',True)
                contains('PageAICoverage','16 / 35' if theme=='Light' else '35 / 35')
                check(theme+' opening coverage never infers',coverage_encoder.calls==before_calls)
                visible('PageAIRanges');ui('invoke','PageAIRanges','--action','expand');contains('PageAIRangesText','17–32' if theme=='Light' else '1–35')
                if args.check_scroll_gutters:gutter('PageAIFieldsScroll','PageAIRanges')
                shot(theme+'-coverage-wide');ui('invoke','PageAIRanges','--action','collapse')
                user32.SetWindowPos(int(hwnd),None,0,0,700,620,0x0014);time.sleep(.3)
                visible('PageAIAdd')
                if args.check_scroll_gutters:
                    gutter('PageAIFieldsScroll','PageAICount');visible('PageAINextRange')
                shot(theme+'-coverage-narrow')
                if theme=='Light':
                    visible('PageAINextRange');ui('invoke','PageAINextRange');check('selecting the next missing range never infers',coverage_encoder.calls==before_calls)
                    ui('invoke','PageAIAdd');enabled('PageAIAdd',True);contains('PageAICoverage','32 / 35')
                    check('only first missing 16 pages were encoded',coverage_encoder.calls-before_calls==16)
                    tree=json.loads(ui('inspect','--json','--depth','16'))
                    for identifier,expected in [('PageAIStart','33'),('PageAICount','3')]:
                        control=next(n for n in nodes(tree) if n.get('automationId')==identifier)
                        editors=[n for n in nodes(control) if n.get('type')=='Edit']
                        check(identifier+' native edit value '+expected,len(editors)==1 and editors[0].get('value')==expected)
                    shot('Light-next-tail-range')
                    coverage_encoder.delay=True;coverage_encoder.entered.clear()
                    visible('PageAIAdd');ui('invoke','PageAIAdd');check('owned delayed page fixture entered',coverage_encoder.entered.wait(5))
                    visible('PageAICancel');ui('invoke','PageAICancel');enabled('PageAIAdd',True)
                    contains('PageAIStatus','中断しました');contains('PageAICoverage','32 / 35')
                    visible('PageAIStatus');shot('Light-cancel-preserves-coverage');coverage_encoder.delay=False
                    visible('PageAIAdd');ui('invoke','PageAIAdd');enabled('PageAIAdd',True);contains('PageAICoverage','35 / 35');enabled('PageAINextRange',False)
                    visible('PageAIStatus');shot('Light-all-pages-ready')
                else:
                    enabled('PageAINextRange',False);check('restart complete coverage never infers',coverage_encoder.calls==before_calls)
                    visible('PageAIAdd');ui('invoke','PageAIAdd');enabled('PageAIAdd',True)
                    contains('PageAIStatus','再利用 16');check('manual range recheck uses cached vectors',coverage_encoder.calls==before_calls)
                    contains('PageAICoverage','35 / 35');shot('Dark-cached-recheck')
                ui('invoke','CloseButton');ready()
                tree=json.loads(ui('inspect','--json','--depth','14'))
                if not any(n.get('automationId')=='TxtEditStatus' and not n.get('isOffscreen',True) for n in nodes(tree)):ui('invoke','BtnDetails')
                wait('TxtEditStatus','未保存の変更');check(theme+' draft tags preserved','draft-coverage' in ui('get-value','TxtTags'))
                ui('set-value','TxtTags','manual-page');wait('TxtEditStatus','保存済み')
                check(theme+' metadata and source retained',sandbox.catalog.get(jump_item)['tags']==['manual-page'] and original==(jump_file.read_bytes(),jump_file.stat().st_mtime_ns))
                if args.check_scroll_gutters:
                    visible('TxtTags');gutter('DetailScroll','TxtTags');shot(theme+'-detail-scroll-lane')
                    from native_ui_tools import invoke_tool
                    invoke_tool(cli,app_pid,hwnd,'BtnAIIndex');ui('wait-for','AIProfileChoice','-t','12000');visible('AIProfileChoice');gutter('AIOptions','AIProfileChoice');shot(theme+'-ai-options-scroll-lane')
                    ui('invoke','CloseButton');ready()
                    invoke_tool(cli,app_pid,hwnd,'BtnRelatedTerms');ui('wait-for','RelatedTerm','-t','12000');visible('RelatedTerm');gutter('RelatedTermsScroll','RelatedTerm');shot(theme+'-related-terms-scroll-lane')
                    ui('invoke','CloseButton');ready()
                    ui('wait-for','Item'+str(jump_item),'-t','12000');ready()
                    ui('invoke','Item'+str(jump_item),'--action','select');wait('TxtEditStatus','保存済み')
                    open_review();ui('invoke','TagGenerate');enabled('TagRefresh',True)
                    visible('TagEdited');gutter('TagDetail','TagEdited');shot(theme+'-tag-review-scroll-lane')
                    ui('invoke','TagClose');ready()
                close();continue
            if args.page_image_only:
                original=(jump_file.read_bytes(),jump_file.stat().st_mtime_ns)
                ui('set-value','TxtQuery','jump.cbz');time.sleep(.4);ui('invoke','BtnSearch');ready();wait('TxtCount','1 件')
                ui('invoke','Item'+str(jump_item),'--action','select');wait('TxtEditStatus','保存済み')
                ui('set-value','TxtTags','draft-page');wait('TxtEditStatus','未保存の変更')
                context('Item'+str(jump_item),jump_item,'IndexBookPages')
                enabled('PageAIAdd',True);shot(theme+'-page-range-wide')
                user32.SetWindowPos(int(hwnd),None,0,0,700,620,0x0014);time.sleep(.3)
                visible('PageAIAdd');shot(theme+'-page-range-narrow')
                ui('invoke','PageAIAdd');enabled('PageAIAdd',True)
                # Poll the real GPU job through the existing backend, never retry it.
                for _ in range(180):
                    job=sandbox.ai.status()
                    if job['state'] not in ('running','cancelling'):break
                    time.sleep(.25)
                check(theme+' GUI-selected page job completes',job.get('job')=='book-pages' and job['state']=='complete' and job['indexed']==3)
                if theme=='Dark':check('restart same source reuses selected page vectors',job['reused']==3)
                contains('PageAIStatus','追加しました');shot(theme+'-page-index-complete')
                ui('invoke','CloseButton');ready()
                tree=json.loads(ui('inspect','--json','--depth','14'))
                if not any(n.get('automationId')=='TxtEditStatus' and not n.get('isOffscreen',True) for n in nodes(tree)):ui('invoke','BtnDetails')
                wait('TxtEditStatus','未保存の変更')
                check(theme+' pending editor preserved', 'draft-page' in ui('get-value','TxtTags') and sandbox.catalog.get(jump_item)['tags']==['manual-page'])
                ui('set-value','TxtTags','manual-page');wait('TxtEditStatus','保存済み')
                user32.SetWindowPos(int(hwnd),None,0,0,1200,820,0x0014);time.sleep(.3)
                choose_combo('CmbSearchMode','ModeVisual');ready()
                ui('set-value','TxtQuery','教室の机');time.sleep(.4);ui('invoke','BtnSearch');ready();wait('TxtCount','1 件')
                result=sandbox.ai.search('教室の机',source='cover',scope={'root_ids':[jump_root]})
                hit=result['items'][0]['ai_page_match']
                report.setdefault('page_quality',[]).append({'theme':theme,'expected_page':1,'actual_page':hit['page'],'matched_expected':hit['page']==1})
                contains('AIPageEvidence'+str(jump_item),str(hit['page']+1)+'ページ');contains('AIPageEvidence'+str(jump_item),'google/embeddinggemma-2')
                shot(theme+'-page-meaning-search')
                ui('invoke','Item'+str(jump_item),'--action','select');ui('scroll-into-view','BtnOpenBook');ui('invoke','BtnOpenBook')
                viewer=None
                for _ in range(40):
                    windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
                    matches=[str(w['hwnd']) for w in windows if str(w.get('hwnd'))!=hwnd and '読書画面' in w.get('title','')]
                    if len(matches)==1:viewer=matches[0];break
                    time.sleep(.1)
                check(theme+' owned reader',viewer is not None);owned(viewer)
                user32.SetForegroundWindow(int(viewer));time.sleep(.15)
                check(theme+' owned reader foreground',user32.GetForegroundWindow()==int(viewer))
                ui('send-keys','f10',window=viewer)
                ui('wait-for','ReaderPageNumber','--value',str(hit['page']+1)+' / 3','-t','12000',window=viewer)
                ui('wait-for','ReaderStatus','--value','表示しました。拡大すると細部を確認できます。','-t','12000',window=viewer)
                path=target/(theme+'-page-match-reader.png');ui('screenshot','--output',path,window=viewer)
                check(theme+' exact revision AI page jump',path.is_file());report['screenshots'].append(path.name)
                ui('send-keys','escape',window=viewer);ready()
                check(theme+' book bytes and mtime retained',original==(jump_file.read_bytes(),jump_file.stat().st_mtime_ns))
                check(theme+' hand metadata retained',sandbox.catalog.get(jump_item)['tags']==['manual-page'] and sandbox.catalog.get(jump_item)['favorite'])
                close();continue
            if args.page_jump_only:
                report['test_mode']='page-text-revision-jump'
                report['generated_revision_mutation']='Only generated-page-jump/jump.cbz is deliberately repacked; base media remain unchanged.'
                def open_jump(number,label):
                    ui('invoke','Item'+str(jump_item),'--action','select');wait('TxtEditStatus','保存済み')
                    ui('scroll-into-view','BtnOpenBook');ui('invoke','BtnOpenBook')
                    viewer=None
                    for _ in range(40):
                        windows=json.loads(cli('ui','list-windows','-a',app_pid,'--json'))
                        matches=[str(w['hwnd']) for w in windows if str(w.get('hwnd'))!=hwnd and '読書画面' in w.get('title','')]
                        if len(matches)==1:viewer=matches[0];break
                        time.sleep(.1)
                    check(label+' owned reader',viewer is not None);owned(viewer)
                    user32.SetForegroundWindow(int(viewer));time.sleep(.15)
                    check(label+' owned reader foreground',user32.GetForegroundWindow()==int(viewer))
                    ui('send-keys','f10',window=viewer)
                    ui('wait-for','ReaderPageNumber','--value',number,'-t','12000',window=viewer)
                    ui('wait-for','ReaderStatus','--value','表示しました。拡大すると細部を確認できます。','-t','12000',window=viewer)
                    check(label+' page '+number,True)
                    path=target/(theme+'-'+label+'.png');ui('screenshot','--output',path,window=viewer)
                    check('screenshot '+path.name,path.is_file() and path.stat().st_size>0);report['screenshots'].append(path.name)
                    ui('send-keys','escape',window=viewer);ready()
                choose_combo('CmbSearchMode','ModePageText');ready()
                ui('set-value','TxtQuery','夕焼け 約束');time.sleep(.4);ui('invoke','BtnSearch');ready();wait('TxtCount','1 件')
                contains('PageTextEvidence'+str(jump_item),'2ページ');contains('PageTextEvidence'+str(jump_item),'元ファイル一致')
                open_jump('2 / 3','current-match')
                # The GUI still has the old 'current' hit: change only our own
                # generated archive and rescan, without re-running the query.
                write_jump_book(extra=True);sandbox.catalog.index.scan(jump_root);sandbox.catalog.sync_index()
                open_jump('1 / 4','changed-after-search')
                check(theme+' stale page number cannot override normal reader opening',True)
                ui('invoke','BtnSearch');ready();wait('TxtCount','1 件')
                contains('PageTextEvidence'+str(jump_item),'元ファイル変更あり');shot(theme+'-stale-text-evidence')
                open_jump('1 / 4','stale-result')
                close();continue
            if args.check_user_feedback:
                ui('invoke','BtnSettings');ui('wait-for','SettingsWheel','-t','12000')
                choose_combo('SettingsWheel','上に回す（下で戻る）' if theme=='Light' else '下に回す（上で戻る）')
                ui('invoke','SettingsSave');contains('SettingsStatus','保存しました')
                check(theme+' wheel preference persisted in isolated settings',json.loads((target/'viewer-settings.json').read_text(encoding='utf-8'))['wheel_up_advances']==(theme=='Light'))
                shot(theme+'-viewer-settings');ui('invoke','CloseButton');ready()
                ui('invoke','NavHistory','--action','select');ready();wait('TxtCount','0 件' if theme=='Light' else '1 件')
                enabled('CmbSearchMode',False);check(theme+' history navigation disables unsupported AI modes',True)
                ui('invoke','NavAll','--action','select');ready()
                sandbox.catalog.update([sandbox.item('generated-001.png')],{'reviewed':True})
                ui('invoke','ExpandSearchOptions');visible('ChkUnreviewedOnly');ui('invoke','ChkUnreviewedOnly');ready()
                wait('TxtCount','75 件' if theme=='Light' else '76 件');wait('ChkUnreviewedOnly','On')
                check(theme+' unreviewed remains a working search option',True)
                ui('invoke','ChkUnreviewedOnly');ready();wait('TxtCount','76 件' if theme=='Light' else '77 件');ui('invoke','ExpandSearchOptions','--action','collapse');ui('wait-for','TxtSearchMethodHint','--gone','-t','12000')
            if args.check_ui_cleanup:
                from native_ui_tools import invoke_tool
                visible('BtnSettings');visible('BtnLayout');visible('BtnDetails')
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
                ui('invoke','ExpandSearchOptions','--action','collapse');ui('wait-for','TxtSearchMethodHint','--gone','-t','12000')
            if args.folder_books_only:
                if theme=='Light':
                    ui('invoke','BtnRoots');ui('wait-for','BtnToggleAddFolder','-t','12000');ui('invoke','BtnToggleAddFolder')
                    ui('set-value','RootPath',str(book_media));visible('RootFolderBooks')
                    ui('invoke','RootFolderBooks')
                    visible('RootRecursive')
                    shot('Light-folder-book-registration')
                    user32.SetWindowPos(int(hwnd),None,0,0,800,820,0x0014);time.sleep(.3)
                    visible('RootFolderBooks');shot('Light-folder-book-registration-narrow')
                    user32.SetWindowPos(int(hwnd),None,0,0,1200,820,0x0014);time.sleep(.3)
                    ui('invoke','AddRoot');ui('wait-for','ScanRoot','-t','12000');visible('ScanRoot')
                    roots=[r for r in sandbox.catalog.index.roots() if r['path']==str(book_media)]
                    check('GUI opt-in root registered',len(roots)==1 and roots[0]['folder_books'])
                    book_root=roots[0]['id'];ui('invoke','ScanRoot')
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
                # F10 pins controls before wheel/X-button and keyboard tests so ReaderPageNumber/ReaderStatus stay visible across 2.5s auto-hide.
                user32.SetForegroundWindow(int(viewer));time.sleep(.15)
                check('only owned reader is foreground',user32.GetForegroundWindow()==int(viewer))
                ui('send-keys','f10',window=viewer)
                if args.check_user_feedback:
                    user32.SetForegroundWindow(int(viewer));time.sleep(.15)
                    check('owned reader foreground for wheel',user32.GetForegroundWindow()==int(viewer))
                    start='1 / 3' if theme=='Light' else '2 / 3'
                    next_page='2 / 3' if theme=='Light' else '3 / 3'
                    ui('scroll','ReaderViewport','--wheel','1' if theme=='Light' else '-1',window=viewer)
                    ui('wait-for','ReaderPageNumber','--value',next_page,'-t','12000',window=viewer)
                    ui('wait-for','ReaderStatus','--value','表示しました。拡大すると細部を確認できます。','-t','12000',window=viewer)
                    time.sleep(.25)
                    ui('scroll','ReaderViewport','--wheel','-1' if theme=='Light' else '1',window=viewer)
                    ui('wait-for','ReaderPageNumber','--value',start,'-t','12000',window=viewer)
                    check(theme+' actual wheel obeys saved direction and returns page',True)
                    tree=json.loads(ui('inspect','--json','--depth','12',window=viewer))
                    area=next(n for n in nodes(tree) if n.get('automationId')=='ReaderViewport')
                    point=wintypes.POINT(int(area['x']+area['width']/2),int(area['y']+area['height']/2))
                    user32.SetCursorPos.argtypes=[ctypes.c_int,ctypes.c_int];user32.SetCursorPos(point.x,point.y)
                    user32.mouse_event.argtypes=[wintypes.DWORD,wintypes.DWORD,wintypes.DWORD,wintypes.DWORD,ctypes.c_size_t]
                    owned(viewer);check('owned reader foreground before X-button input',user32.GetForegroundWindow()==int(viewer))
                    ui('send-keys','f10',window=viewer)
                    user32.mouse_event(0x0080,0,0,2,0);user32.mouse_event(0x0100,0,0,2,0)
                    ui('wait-for','ReaderPageNumber','--value',next_page,'-t','12000',window=viewer)
                    ui('wait-for','ReaderStatus','--value','表示しました。拡大すると細部を確認できます。','-t','12000',window=viewer)
                    ui('send-keys','f10',window=viewer)
                    user32.mouse_event(0x0080,0,0,1,0);user32.mouse_event(0x0100,0,0,1,0)
                    ui('wait-for','ReaderPageNumber','--value',start,'-t','12000',window=viewer)
                    check(theme+' actual mouse forward/back turns viewer pages',True)
                user32.SetForegroundWindow(int(viewer));time.sleep(.15)
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
                if args.check_user_feedback:
                    for _ in range(60):
                        history=sandbox.catalog.search(view='history')['items']
                        if history and history[0]['id']==book_item:break
                        time.sleep(.1)
                    check(theme+' successful reader records recent item',history and history[0]['id']==book_item)
                    ui('scroll-into-view','FileProperties');ui('invoke','FileProperties');contains('FilePropertyText','画像フォルダ（一冊）');shot(theme+'-file-properties')
                    ui('invoke','NavHistory','--action','select');ready();wait('TxtCount','1 件');enabled('CmbSearchMode',False)
                    ui('invoke','NavAll','--action','select');ready()
                    ui('invoke','Item'+str(book_item),'--action','select');wait('TxtEditStatus','保存済み')
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
                if args.check_user_feedback and theme=='Light':
                    ui('invoke','BtnCloseDetails');ui('invoke','BtnToggleAddFolder')
                    ui('scroll-into-view','FolderItem'+str(book_root));ui('wait-for','FolderTitle'+str(book_root),'-t','12000')
                    owned(foreground=True);ui('click','FolderTitle'+str(book_root))
                    ui('wait-for','ScanRoot','-t','12000');check('single folder click opens settings',True)
                    owned(foreground=True);ui('click','FolderTitle'+str(book_root),'--double');ready();wait('TxtCount','1 件')
                    check('double folder click opens scoped library',True)
                    ui('invoke','BtnRoots');ui('wait-for','ConfigFolder'+str(book_root),'-t','12000');ui('invoke','ConfigFolder'+str(book_root))
                    ui('scroll-into-view','UnregisterConsent');ui('invoke','UnregisterConsent');ui('scroll-into-view','UnregisterRoot');ui('invoke','UnregisterRoot')
                    ui('wait-for','CmbFolderState','-t','12000')
                    choose_combo('CmbFolderState','FolderStateInactive')
                    ui('wait-for','RestoreFolder'+str(book_root),'-t','12000');ui('invoke','RestoreFolder'+str(book_root))
                    for _ in range(60):
                        restored=next(x for x in sandbox.catalog.index.roots(include_inactive=True) if x['id']==book_root)
                        if restored['enabled']:break
                        time.sleep(.1)
                    check('single restore click re-enables root with metadata',restored['enabled'] and restored['folder_books'] and sandbox.catalog.get(book_item)['tags']==['folder-manual'])
                    # F21: Create a disposable generated root, unregister it, test cancel + confirm DB purge
                    purge_media=target/'generated-purge-root';purge_media.mkdir(parents=True,exist_ok=True)
                    (purge_media/'purge-sample.png').write_bytes((book_media/'Generated book'/'p1.png').read_bytes())
                    purge_before=(purge_media/'purge-sample.png').stat().st_mtime_ns
                    purge_root=sandbox.catalog.add_root(str(purge_media))
                    sandbox.catalog.index.scan(purge_root);sandbox.catalog.sync_index()
                    purge_item=sandbox.catalog.search(root_id=purge_root)['items'][0]['id']
                    sandbox.catalog.update([purge_item],{'tags':['purge-test-tag']})
                    sandbox.catalog.unregister_root(purge_root)
                    choose_combo('CmbFolderState','FolderStateActive');choose_combo('CmbFolderState','FolderStateInactive')
                    ui('wait-for','PurgeFolder'+str(purge_root),'-t','12000');visible('PurgeFolder'+str(purge_root))
                    ui('invoke','PurgeFolder'+str(purge_root));ui('wait-for','PrimaryButton','-t','12000');shot('Light-purge-confirm-dialog')
                    ui('invoke','CloseButton');ui('wait-for','PrimaryButton','--gone','-t','12000')
                    check('cancelling purge preserves inactive root and metadata',any(x['id']==purge_root for x in sandbox.catalog.index.roots(include_inactive=True)) and sandbox.catalog.get(purge_item)['tags']==['purge-test-tag'])
                    ui('invoke','PurgeFolder'+str(purge_root));ui('wait-for','PrimaryButton','-t','12000');ui('invoke','PrimaryButton')
                    ui('wait-for','TxtFolderEmpty','-t','12000')
                    check('confirming purge removes inactive root and DB records while preserving source file',not any(x['id']==purge_root for x in sandbox.catalog.index.roots(include_inactive=True)) and (purge_media/'purge-sample.png').is_file() and (purge_media/'purge-sample.png').stat().st_mtime_ns==purge_before)
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
                    # Verify ModePageText: saved page text search displays PageTextEvidence and excludes normal tags
                    from page_index import PageIndex
                    from page_text import PageTextIndex
                    class UiFakeExtractor:
                        class info:
                            @staticmethod
                            def record():return {'adapter':'ui-ocr','version':'1','model':'ocr-fixture','model_revision':'rev1','preprocessing':'page-v1'}
                        def extract(self,payload,cancelled):
                            return '夕焼けの教室で約束した'
                    pages_idx=PageIndex(sandbox.catalog)
                    pages_idx.refresh(book_item)
                    snap=pages_idx.list(book_item)
                    texts_idx=PageTextIndex(sandbox.catalog,pages_idx,UiFakeExtractor())
                    texts_idx.generate(book_item,[snap['pages'][0]['page_id']],snap['source_revision'],uuid.uuid4().hex)
                    choose_combo('CmbSearchMode','ModePageText');ready()
                    ui('set-value','TxtQuery','夕焼け 約束');time.sleep(.4);ui('invoke','BtnSearch');ready();wait('TxtCount','1 件')
                    contains('PageTextEvidence'+str(book_item),'ページ本文一致（1ページ: 1ページ）')
                    contains('PageTextEvidence'+str(book_item),'夕焼けの教室で約束した')
                    contains('PageTextEvidence'+str(book_item),'ocr-fixture')
                    shot('Dark-page-text-search-wide')
                    check('Dark ModePageText searches saved page text and displays excerpt/provenance',True)
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
        if args.tag_language_only or args.page_image_only:
            check('actual existing CUDA model used',language_encoder.device=='cuda')
            language_process=language_encoder.process
        check('fixture encoder never called',sandbox.encoder.calls==0 and not sandbox.encoder.resident)
        if args.wd_runtime_only:
            directory=tagger.profile.verify(REPO,hashes=True)
            check('WD model bytes and mtime unchanged',model_before=={name:(directory/name).stat().st_mtime_ns for name in tagger.profile.data()['artifacts']})
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
            if args.wd_runtime_only and tagger:
                tagger.close()
                report['wd_workers']=len(wd_processes)
                report['wd_workers_stopped']=all(p.poll() is not None and p.stdin.closed and p.stdout.closed for p in wd_processes)
                if not report['wd_workers_stopped']:report['runtime_pass']=False
            if wd_observer:wd_observer.stop()
            if sandbox:
                report['source_unchanged']=sandbox.source_before==sandbox.source_digest()
                if not report['source_unchanged'] or report.get('cleanup_terminated_owned_process'):report['runtime_pass']=False
                if (args.tag_language_only or args.page_image_only) and sandbox.ai is not None:
                    language_process=language_encoder.process
                    sandbox.ai.close();sandbox.ai=None
                sandbox.close()
                if language_process:
                    report['embedding_worker_stopped']=language_process.poll() is not None
                    if not report['embedding_worker_stopped']:report['runtime_pass']=False
            if target.exists():(target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            try:cli('ui','yield')
            except Exception:pass
    print(json.dumps({'runtime_pass':report['runtime_pass'],'checks':len(report['checks']),'visual_review':report['visual_review']}))
    if not report['runtime_pass']:raise RuntimeError('Native checks failed; inspect result.json')

if __name__=='__main__':main()
