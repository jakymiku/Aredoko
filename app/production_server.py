"""Production-only loopback endpoint. No demo data or source-media writes."""
import argparse
import sys
import json
import secrets
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import re
import select
import socket
from production import ProductionCatalog, ScanBusyError, HistoryChanged
from term_relations import MAX_IMPORT_BYTES
from previews import VideoRangeUnsatisfiable, PreviewReader, PreviewUnavailable, PreviewBusyError, ReaderChanged
import zipfile
import sqlite3
from ai_process import EncoderProcess, AIUnavailable
from ai_search import AISearch, AIBusy, MAX_ITEMS
from ai_score_spool import SearchCancelled
from search_requests import SearchRequestConflict,SearchRequests
from ai_profiles import load_profile, ModelProfile
from ai_settings import AIProfileSettings,validate_resource,RESOURCE_DEFAULT
from ai_ranking import POLICIES
from ai_scope import validate_scope
from search_intent import SearchIntent
from intent_questions import QUESTION_SETS
from laya_process import LayaProcess
from laya_config import model_path as laya_model_path
from server import handler_for
from tag_suggestions import TagSuggestions
from tag_candidate_search import search_candidates
from tag_semantics import semantic_candidates
from page_index import PageIndex
from page_text import PageTextIndex
from page_batch import start_batch, resume_batch
from page_chunks import plan_chunked, start_chunked, resume_chunked
from wd_tagger import create_tagger
from tagger_profile import load_profile as load_tagger_profile
from model_locations import FIELD as LOCATIONS, ModelTarget
from storage_lease import storage_lease,storage_parent
from runtime_paths import worker_python, bind_runtime
from ai_runtime_preferences import AIRuntimePreferences, read_preferences, model_root, MODEL_ROOT_FIELDS
from ai_setup_jobs import AISetupJobs, SetupBusy
from backup_jobs import BackupJobs,BackupBusy
from ai_download_jobs import AIDownloadJobs,DownloadBusy
from ai_acquisition_registry import load_trusted_specs
from restore_jobs import RestoreStagingJobs,RestoreBusy
from ai_runtime import object_pairs
from animation_sessions import AnimationSessions, AnimationBusy, AnimationGone, MIME as ANIMATION_MIME
from image_animations import AnimationUnavailable
from result_sessions import ResultSessions, ResultUnavailable, ResultCapacity, IndexStamp
from thumbnail_cache import ThumbnailCache, ThumbnailCancelled
from contextlib import ExitStack
import sys

class DisabledAI:
    def __init__(self,error=None,status_code='model_missing'):
        self.error=error or 'AI環境（モデル・Python）が未導入です。名前・タグの文字検索、棚・整理、閲覧はそのまま利用できます。'
        self.status_code=status_code
    def status(self):
        return {'available':False,'state':'failed','processed':0,'total':0,'indexed':0,
                'skipped':0,'error':self.error,'status_code':self.status_code,
                'model':'未導入','model_id':'none','profile':'none','modalities':[],
                'resident':False,'worker_state':'unloaded','limit':MAX_ITEMS}
    def start(self,*args,**kwargs): raise AIUnavailable(self.status()['error'])
    def search(self,*args,**kwargs): raise AIUnavailable(self.status()['error'])
    def similar(self,*args,**kwargs): raise AIUnavailable(self.status()['error'])
    def coverage(self,*args,**kwargs): raise AIUnavailable(self.status()['error'])
    def cancel_build(self): return {'cancel_requested':False}
    def release(self): raise AIUnavailable(self.status()['error'])
    def close(self): pass

# Fixed, path-free folder validation messages the GUI can explain (in
# Japanese via ErrorText); any other ValueError stays generic.
PUBLIC_FOLDER_ERRORS = frozenset({
    'Explicit folder consent required',
    'Choose an absolute folder path',
    'The library must not contain the application database',
    'Shelf must be 80 characters or less',
    'Include subfolders must be true or false',
    'Symlink roots are not supported',
    'Root must exist and be accessible',
    'Reparse-point roots are not supported',
    'Root must be an existing ordinary directory',
    'Overlapping roots are not supported',
    'This root is already registered',
    'Exclusion patterns must be a list (max 64)',
    'Invalid exclusion pattern',
    'Use relative POSIX-style exclusion patterns',
    'folder_books must be true or false',
    'Folder book mode cannot change after scanning',
    'Explicit folder purge consent required',
    'AI index cleanup failed; library records were kept',
    'Unregister the root before purging database records',
    'Invalid scan mode',
})


def create_ai(catalog,profile_path=None,ranking='mean-rrf',*,ai_python=None,models_root=None,profile_definition=None):
    repo=Path(__file__).resolve().parents[1]
    try:
        profile=load_profile(profile_path) if profile_definition is None else profile_definition
        if not isinstance(profile,ModelProfile):raise ValueError('Invalid model definition')
        return AISearch(catalog,EncoderProcess(worker_python(repo,ai_python),profile.model_path(repo,models_root=models_root),profile),ranking=ranking)
    except (ValueError, KeyError, json.JSONDecodeError):
        return DisabledAI(error='モデル設定が無効または破損しています。「設定」からプロファイルを選び直してください。', status_code='corrupt_profile')
    except (AIUnavailable,sqlite3.DatabaseError,OSError):
        return DisabledAI(error='AI環境（モデル・Python）が未導入です。名前・タグの文字検索、棚・整理、閲覧はそのまま利用できます。', status_code='model_missing')

def create_intent(enabled=False,question_set='v2-hybrid',check_order=True,*,ai_python=None,models_root=None):
    repo=Path(__file__).resolve().parents[1]
    try:
        return SearchIntent(LayaProcess(worker_python(repo,ai_python),laya_model_path(repo,models_root=models_root),question_set=question_set,check_order=check_order)) if enabled else SearchIntent()
    except (ValueError,OSError):return SearchIntent()

def production_handler(catalog,token,ai=None,intent=None,profiles=None,tagger=None,text_extractor=None,*,instance_id=None,runtime_preferences=None,tagger_profile_paths=(),active_tagger_profile=None,restore_handoff=None,acquisition_specs=(),thumbnail_disk_path=None):
    ai=ai or create_ai(catalog)
    intent=intent or SearchIntent()
    profiles=profiles or AIProfileSettings(Path(__file__).resolve().parents[1])
    profiles.writer_fence=catalog.writer_fence
    base=handler_for(catalog,token)
    previews=PreviewReader(catalog)
    page_index=PageIndex(catalog,previews)
    page_text=PageTextIndex(catalog,page_index,text_extractor)
    try:setup_profile=(ModelProfile.from_dict(json.loads(profiles.active_definition)) if profiles.active_definition is not None else load_profile(profiles.startup_path)) if not profiles.startup_error else None
    except (ValueError,OSError):setup_profile=None
    setup=AIRuntimePreferences(runtime_preferences if runtime_preferences is not None else catalog.path.parent/'launch-settings.json',
        profiles.repo,setup_profile,active_python=profiles.python,active_models_root=getattr(profiles,'active_models_root',profiles.models_root))
    if profiles.model_preferences is None:profiles.model_preferences=setup.path
    setup.writer_fence=catalog.writer_fence
    setup_jobs=AISetupJobs(setup)
    download_jobs=AIDownloadJobs(setup.path.parent/'ai-downloads',specifications=acquisition_specs)
    def backup_configuration():
        # Only explicitly configured app-owned profile/settings paths. No media
        # discovery and no arbitrary path supplied by the HTTP caller.
        folder=profiles.folder if profiles.folder.exists() else None
        extra=() if profiles.active_definition is not None or profiles.startup_path is None or folder is not None and profiles.startup_path.parent.resolve()==folder.resolve() else (profiles.startup_path,)
        tagger_paths=tuple(Path(p) for p in tagger_profile_paths)
        active_tagger=active_tagger_profile.name if isinstance(active_tagger_profile,Path) else active_tagger_profile
        definition=getattr(getattr(tagger,'profile',None),'document',None)
        return {'settings':profiles.path if profiles.path.exists() else None,'profiles':folder,
                'extra_profiles':extra,'tagger_profiles':tagger_paths,
                'active_profile':profiles.startup_path.name if profiles.active_definition is None and profiles.startup_path is not None else None,
                'active_profile_override':profiles.override is not None and not profiles.transient_override,
                'active_tagger_profile':active_tagger,
                'active_profile_data':profiles.active_definition,
                'active_tagger_data':definition.encode('utf-8') if isinstance(definition,str) else None}
    backup_jobs=BackupJobs(catalog,quiesce=catalog.writer_fence.pause,configuration=backup_configuration)
    restore_jobs=RestoreStagingJobs(catalog.path.parent/'restore-staging',handoff=restore_handoff)
    animations=AnimationSessions(previews)
    thumbnails=ThumbnailCache(previews,disk_path=thumbnail_disk_path)
    def result_provider(conditions, consume, cancelled):
        values = dict(conditions)
        mode = values.pop('mode', None)
        def require(allowed):
            if set(values) - set(allowed):raise ValueError('Invalid result conditions')
        if mode in ('literal','history'):
            require(('query','kind','view','root_ids','shelf','shelf_ids'))
            if mode=='history':
                if values.get('view','history')!='history':raise ValueError('Invalid history filter')
                values['view']='history'
            return catalog.search(limit=120,**values,result_sink=consume,cancelled=cancelled)
        if mode=='semantic':
            require(('query','kind','view','source','scope','literal_only','group_threshold','result_group'))
            return ai.search(page=0,limit=120,**values,cancelled=cancelled,result_sink=consume)
        if mode=='similar':
            require(('item_id','kind','view','scope'))
            return ai.similar(page=0,limit=120,**values,cancelled=cancelled,result_sink=consume)
        if mode in ('page-text','pending-proposals','pending-proposals-semantic'):
            require(('query','kind','view','root_ids','shelf','shelf_ids','model'))
            if mode=='page-text':return consume(lambda page:page_text.search(page=page,**values))
            if mode=='pending-proposals':return consume(lambda page:search_candidates(suggestions,page=page,**values))
            return semantic_candidates(suggestions,ai,page=0,**values,cancelled=cancelled,result_sink=consume)
        raise ValueError('Invalid result search mode')
    results=ResultSessions(catalog,result_provider,index_stamp=IndexStamp(ai) if isinstance(ai,AISearch) else None)
    resource_updates=threading.Lock()
    suggestions=TagSuggestions(catalog,adapter=tagger if tagger is not None else create_tagger(ai),previews=previews)
    def ai_scan_hook(target_roots, discovered, cancelled):
        from scan_ai_followup import run_scan_ai
        if not ai.status().get('available',False):
            raise AIUnavailable('AI環境が未準備です。AI検索の準備を確認してください。')
        return run_scan_ai(ai,profiles,catalog,target_roots,cancelled,catalog._scan_ai_progress)
    catalog.ai_scan_hook = ai_scan_hook
    from startup_scans import StartupScans
    startup_scans=StartupScans(catalog)
    class Handler(base):
        def _search_reply(self,body,operation):
            supplied='request_id' in body
            request_id=body.pop('request_id',None)
            if supplied:
                SearchRequests.validate(request_id)
            def disconnected():
                # No socket mode changes: HTTP body is consumed, requests close after one reply.
                try:
                    readable,_,_=select.select([self.connection],[],[],0)
                    return bool(readable) and self.connection.recv(1,socket.MSG_PEEK)==b''
                except OSError:return True
            def execute(cancelled):
                if cancelled():raise SearchCancelled('Search cancelled')
                result=operation(cancelled)
                if cancelled():raise SearchCancelled('Search cancelled')
                return result
            if request_id is None:
                # Legacy callers still stop on disconnect; no global cancel operation.
                result=execute(disconnected)
            else:
                if not isinstance(ai,AISearch):raise AIUnavailable(ai.status()['error'])
                with ai.search_requests.claim(request_id) as cancelled:
                    result=execute(lambda:cancelled() or disconnected())
                    result={**result,'request_id':request_id}
            return self.send(200,result)

        def do_GET(self):
            if not self.valid_host(): return self.send(403,{'error':'Invalid host'})
            path=urlparse(self.path).path
            if path=='/api/items':
                args=parse_qs(urlparse(self.path).query,keep_blank_values=True)
                def param(name,default=''):return args.get(name,[default])[0]
                try:
                    page=param('page','0')
                    if not page.isascii() or not page.isdigit() or len(page)>9:
                        raise ValueError('Invalid paging')
                    root=None
                    roots=None
                    if 'root_id' in args and 'root_ids' in args:
                        raise ValueError('Invalid root filter')
                    if 'root_id' in args:
                        value=param('root_id')
                        if len(args['root_id'])!=1 or not value.isascii() or not value.isdigit() or len(value)>19:
                            raise ValueError('Invalid root filter')
                        root=int(value)
                    if 'root_ids' in args:
                        raw_values=args['root_ids']
                        if len(raw_values)!=1 or not raw_values[0]:
                            raise ValueError('Invalid root filter')
                        parts=raw_values[0].split(',')
                        if not 1<=len(parts)<=256 or any(not p.isascii() or not p.isdigit() or len(p)>19 for p in parts):
                            raise ValueError('Invalid root filter')
                        roots=[int(p) for p in parts]
                    shelf_ids=None
                    if 'shelf_ids' in args:
                        if len(args['shelf_ids'])!=1:raise ValueError('Invalid shelf selection')
                        parts=args['shelf_ids'][0].split(',') if args['shelf_ids'][0] else []
                        if len(parts)>64 or any(not part.isascii() or not part.isdigit() or len(part)>19 for part in parts):raise ValueError('Invalid shelf selection')
                        shelf_ids=[int(part) for part in parts]
                    if 'shelf' in args and len(args['shelf'])!=1:raise ValueError('Invalid shelf selection')
                    return self.send(200,catalog.search(param('q'),param('kind'),param('view','all'),int(page),root_id=root,root_ids=roots,shelf=param('shelf',None),shelf_ids=shelf_ids))
                except ValueError as ex:return self.send(400,{'error':str(ex)})
            if path=='/api/session':
                session={'mode':'production','token':token,'stats':catalog.stats()}
                if instance_id is not None:session['instance_id']=instance_id
                return self.send(200,session)
            # Native client supplies the session token for library-specific reads.
            if path.startswith('/api/library'):
                if self.headers.get('X-Aredoko-Token')!=token:
                    return self.send(403,{'error':'Invalid session'})
                if path=='/api/library/shelves':
                    if urlparse(self.path).query:return self.send(400,{'error':'Invalid shelf query'})
                    return self.send(200,{'shelves':catalog.shelf_descriptors(),'items':catalog.shelves()})
                if path=='/api/library/history':
                    if urlparse(self.path).query:return self.send(400,{'error':'Invalid history query'})
                    return self.send(200,catalog.history_status())
                if path.startswith('/api/library/page-text/'):
                    try:
                        if path=='/api/library/page-text/status':
                            if urlparse(self.path).query:raise ValueError('Unexpected status query')
                            return self.send(200,page_text.status())
                        match=re.fullmatch(r'/api/library/page-text/([1-9][0-9]{0,18})',path)
                        if match is None:raise ValueError('Invalid page text route')
                        args=parse_qs(urlparse(self.path).query,keep_blank_values=True,strict_parsing=True,max_num_fields=3)
                        if set(args)-{'offset','limit','revision'} or any(len(v)!=1 for v in args.values()):
                            raise ValueError('Invalid text query')
                        values={}
                        for key in ('offset','limit'):
                            if key in args:
                                if re.fullmatch(r'0|[1-9][0-9]{0,4}',args[key][0]) is None:raise ValueError('Invalid paging')
                                values[key]=int(args[key][0])
                        if 'revision' in args:values['revision']=args['revision'][0]
                        return self.send(200,page_text.list(int(match[1]),**values))
                    except ReaderChanged:return self.send(409,{'error':'Page source changed; rescan and refresh page index'})
                    except (PreviewUnavailable,OSError,KeyError):return self.send(404,{'error':'Page source unavailable'})
                    except ValueError:return self.send(400,{'error':'Invalid page text request'})
                if path.startswith('/api/library/page-index/'):
                    try:
                        match=re.fullmatch(r'/api/library/page-index/([1-9][0-9]{0,18})(?:/pages/([0-9a-f]{64}))?',path)
                        if match is None:raise ValueError('Invalid page index route')
                        item=int(match[1])
                        args=parse_qs(urlparse(self.path).query,keep_blank_values=True,strict_parsing=True,max_num_fields=3)
                        if any(len(v)!=1 for v in args.values()):raise ValueError('Repeated query')
                        if match[2] is not None:
                            if set(args)!={'revision'}:raise ValueError('One revision is required')
                            payload=page_index.input(item,match[2],args['revision'][0])
                            return self.send(200,payload['data'],payload['mime'])
                        if set(args)-{'offset','limit','revision'}:raise ValueError('Invalid page query')
                        values={}
                        for key in ('offset','limit'):
                            if key in args:
                                if re.fullmatch(r'0|[1-9][0-9]{0,4}',args[key][0]) is None:raise ValueError('Invalid paging')
                                values[key]=int(args[key][0])
                        if 'revision' in args:values['revision']=args['revision'][0]
                        return self.send(200,page_index.list(item,**values))
                    except ReaderChanged:return self.send(409,{'error':'Page source changed; rescan and refresh page index'})
                    except PreviewBusyError:return self.send(503,{'error':'Preview workers busy'})
                    except (PreviewUnavailable,OSError,KeyError):return self.send(404,{'error':'Page source unavailable'})
                    except ValueError:return self.send(400,{'error':'Invalid page index request'})
                if path.startswith('/api/library/tag-suggestions/'):
                    try:
                        evidence=re.fullmatch(r'/api/library/tag-suggestions/([1-9][0-9]{0,18})/evidence',path)
                        if evidence is not None:
                            item=int(evidence[1])
                            if item>9223372036854775807:raise ValueError('Invalid item')
                            query=parse_qs(urlparse(self.path).query,keep_blank_values=True,strict_parsing=True,max_num_fields=2)
                            if set(query)!={'revision'} or len(query['revision'])!=1 or re.fullmatch('[0-9a-f]{64}',query['revision'][0]) is None:
                                raise ValueError('Invalid evidence revision')
                            try:
                                payload=previews.tag_input(item)
                            except (ReaderChanged,PreviewBusyError) as ex:
                                raise AIBusy('根拠画像を確認できません。再走査して開き直してください。') from ex
                            except PreviewUnavailable as ex:raise KeyError('Tag source unavailable') from ex
                            if payload['source']['revision']!=query['revision'][0]:
                                raise AIBusy('元ファイルが変更されました。候補を生成し直してください。')
                            return self.send(200,payload['data'],payload['mime'])
                        match=re.fullmatch(r'/api/library/tag-suggestions/([1-9][0-9]{0,18})',path)
                        if match is None:raise ValueError('Invalid proposal route')
                        args=parse_qs(urlparse(self.path).query,keep_blank_values=True,strict_parsing=True,max_num_fields=2)
                        if set(args)-{'before','limit'}:raise ValueError('Invalid history query')
                        values={}
                        for key,entries in args.items():
                            value=entries[0]
                            if len(entries)!=1 or not value.isascii() or not value.isdigit() or len(value)>19:
                                raise ValueError('Invalid history query')
                            values[key]=int(value)
                        return self.send(200,suggestions.list(int(match[1]),**values))
                    except AIBusy as ex:return self.send(409,{'error':str(ex)})
                    except ValueError:return self.send(400,{'error':'Invalid proposal history request'})
                    except KeyError:return self.send(404,{'error':'Tag source unavailable'})
                    except OSError:return self.send(409,{'error':'Tag source unavailable; records preserved'})
                if path.endswith('/progress') and path.startswith('/api/library/reader/'):
                    try:
                        match=re.fullmatch(r'/api/library/reader/([1-9][0-9]{0,18})/progress',path)
                        if match is None or urlparse(self.path).query:raise ValueError('Invalid progress route')
                        return self.send(200,catalog.reader_progress(int(match[1])))
                    except ValueError:return self.send(400,{'error':'Invalid reading progress request'})
                    except KeyError:return self.send(404,{'error':'Book unavailable'})
                if path.startswith('/api/library/reader/'):
                    try:
                        match=re.fullmatch(r'/api/library/reader/([1-9][0-9]{0,18})(?:/(?:pages|original)/(0|[1-9][0-9]{0,3}))?',path)
                        if match is None: raise ValueError('Invalid reader route')
                        item=int(match[1])
                        if item > 9223372036854775807: raise ValueError('Invalid item')
                        query=parse_qs(urlparse(self.path).query,keep_blank_values=True,strict_parsing=True,max_num_fields=2)
                        if match[2] is None:
                            if query: raise ValueError('Unexpected reader query')
                            return self.send(200,previews.manifest(item))
                        if set(query)!={'revision'} or len(query['revision'])!=1:
                            raise ValueError('One revision is required')
                        if '/original/' in path:
                            data,mime,etag=previews.page_source(item,int(match[2]),query['revision'][0],self.headers.get('If-None-Match'))
                            return self.send(304 if data is None else 200,b'' if data is None else data,mime,{'ETag':etag})
                        data,mime=previews.read_page(item,int(match[2]),query['revision'][0])
                        return self.send(200,data,mime)
                    except ReaderChanged:
                        return self.send(409,{'error':'Archive changed; rescan and reopen the reader'})
                    except PreviewBusyError:
                        return self.send(503,{'error':'Preview workers busy'})
                    except (PreviewUnavailable,OSError,zipfile.BadZipFile,RuntimeError,NotImplementedError):
                        return self.send(404,{'error':'Reader page unavailable'})
                    except ValueError:
                        return self.send(400,{'error':'Invalid reader request'})
                if path.startswith('/api/library/thumbnail/'):
                    try:
                        match=re.fullmatch(r'/api/library/thumbnail/([1-9][0-9]{0,18})',path)
                        if match is None or int(match[1])>9223372036854775807:raise ValueError('Invalid item')
                        query=parse_qs(urlparse(self.path).query,keep_blank_values=True,strict_parsing=True,max_num_fields=2)
                        if 'edge' not in query or set(query)-{'edge','priority'} or len(query['edge'])!=1 or query['edge'][0] not in ('128','256','512','1024'):
                            raise ValueError('Invalid thumbnail size')
                        priority=query.get('priority',['visible'])
                        if len(priority)!=1 or priority[0] not in ('visible','nearby'):raise ValueError('Invalid thumbnail priority')
                        def disconnected():
                            try:
                                readable,_,_=select.select([self.connection],[],[],0)
                                return bool(readable) and self.connection.recv(1,socket.MSG_PEEK)==b''
                            except OSError:return True
                        data=thumbnails.read(int(match[1]),int(query['edge'][0]),priority=priority[0],cancelled=disconnected)
                        return self.send(200,data,'image/png')
                    except ThumbnailCancelled:
                        return self.send(409,{'error':'Thumbnail cancelled'})
                    except ReaderChanged:
                        return self.send(409,{'error':'Thumbnail source changed; rescan'})
                    except PreviewBusyError:
                        return self.send(503,{'error':'Preview workers busy'})
                    except (PreviewUnavailable,OSError,KeyError,zipfile.BadZipFile,RuntimeError,NotImplementedError,ImportError):
                        return self.send(404,{'error':'Thumbnail unavailable'})
                    except ValueError:
                        return self.send(400,{'error':'Invalid thumbnail request'})
                if path.startswith('/api/library/preview/'):
                    try:
                        match=re.fullmatch(r'/api/library/preview/([1-9][0-9]{0,18})(?:/(info|manifest|original|frames/(0|[1-9][0-9]?)))?',path)
                        if match is None:
                            raise ValueError('Invalid item')
                        item=int(match[1])
                        if item > 9223372036854775807: raise ValueError('Invalid item')
                        query=parse_qs(urlparse(self.path).query,keep_blank_values=True,strict_parsing=True,max_num_fields=2)
                        if match[2]=='original':
                            if query:raise ValueError('Invalid item')
                            data,mime,etag=previews.original_source(item,self.headers.get('If-None-Match'))
                            return self.send(304 if data is None else 200,b'' if data is None else data,mime,{'ETag':etag})
                        if match[2]=='info':
                            if query: raise ValueError('Invalid item')
                            return self.send(200,previews.image_info(item))
                        if match[2]=='manifest':
                            if query: raise ValueError('Invalid item')
                            return self.send(200,previews.image_manifest(item))
                        if match[2] and match[2].startswith('frames/'):
                            if set(query)!={'revision'} or len(query['revision'])!=1:
                                raise ValueError('Invalid item')
                            data,mime=previews.image_frame(item,int(match[3]),query['revision'][0])
                            return self.send(200,data,mime)
                        if query:
                            raise ValueError('Invalid item')
                        data,mime=previews.read(item)
                        return self.send(200,data,mime)
                    except ReaderChanged:
                        return self.send(409,{'error':'Archive changed; rescan and reopen the reader'})
                    except PreviewBusyError:
                        return self.send(503,{'error':'Preview workers busy'})
                    except (PreviewUnavailable,OSError,zipfile.BadZipFile,RuntimeError,NotImplementedError):
                        return self.send(404,{'error':'Preview unavailable'})
                    except ValueError:
                        return self.send(400,{'error':'Invalid item'})
                if path.startswith('/api/library/video/'):
                    try:
                        match=re.fullmatch(r'/api/library/video/([1-9][0-9]{0,18})(?:/(manifest|range|frame))?',path)
                        if match is None:raise ValueError('Invalid video route')
                        item=int(match[1])
                        if item>9223372036854775807:raise ValueError('Invalid item')
                        query=parse_qs(urlparse(self.path).query,keep_blank_values=True,strict_parsing=True,max_num_fields=2)
                        if match[2]=='frame':
                            if set(query)!={'revision','at_ms'} or any(len(x)!=1 for x in query.values()) or re.fullmatch(r'0|[1-9][0-9]{0,7}',query['at_ms'][0]) is None:
                                raise ValueError('Invalid frame query')
                            data,mime=previews.video_frame(item,int(query['at_ms'][0]),query['revision'][0])
                            return self.send(200,data,mime)
                        if match[2]=='range':
                            if set(query)!={'revision'} or len(query['revision'])!=1:raise ValueError('One revision is required')
                            values=self.headers.get_all('Range',[])
                            value=re.fullmatch(r'bytes=(0|[1-9][0-9]{0,12})-(0|[1-9][0-9]{0,12})',values[0]) if len(values)==1 else None
                            if value is None:raise ValueError('One explicit bounded range is required')
                            start,end=map(int,value.groups())
                            data,mime,size=previews.video_range(item,start,end,query['revision'][0])
                            return self.send(206,data,mime,{'Content-Range':f'bytes {start}-{end}/{size}','Accept-Ranges':'bytes','ETag':'"'+query['revision'][0]+'"'})
                        if query:raise ValueError('Unexpected video query')
                        if match[2]=='manifest':return self.send(200,previews.video_manifest(item))
                        data,mime=previews.read_video(item)
                        return self.send(200,data,mime)
                    except VideoRangeUnsatisfiable as error:
                        return self.send(416,{'error':'Video range outside source'},extra_headers={'Content-Range':f'bytes */{error.size}'})
                    except ReaderChanged:
                        return self.send(409,{'error':'Archive changed; rescan and reopen the reader'})
                    except PreviewBusyError:
                        return self.send(503,{'error':'Preview workers busy'})
                    except (PreviewUnavailable,OSError,RuntimeError,NotImplementedError):
                        return self.send(404,{'error':'Preview unavailable'})
                    except ValueError:
                        return self.send(400,{'error':'Invalid video range request'})
                if path.startswith('/api/library/audio/'):
                    try:
                        match=re.fullmatch(r'/api/library/audio/([1-9][0-9]{0,18})(?:/(manifest|range))?',path)
                        if match is None:raise ValueError('Invalid audio route')
                        item=int(match[1])
                        if item>9223372036854775807:raise ValueError('Invalid item')
                        query=parse_qs(urlparse(self.path).query,keep_blank_values=True,strict_parsing=True,max_num_fields=2)
                        if match[2]=='range':
                            if set(query)!={'revision'} or len(query['revision'])!=1:raise ValueError('One revision is required')
                            values=self.headers.get_all('Range',[])
                            value=re.fullmatch(r'bytes=(0|[1-9][0-9]{0,12})-(0|[1-9][0-9]{0,12})',values[0]) if len(values)==1 else None
                            if value is None:raise ValueError('One explicit bounded range is required')
                            start,end=map(int,value.groups())
                            data,mime,size=previews.audio_range(item,start,end,query['revision'][0])
                            return self.send(206,data,mime,{'Content-Range':f'bytes {start}-{end}/{size}','Accept-Ranges':'bytes','ETag':'"'+query['revision'][0]+'"'})
                        if query:raise ValueError('Unexpected audio query')
                        if match[2]=='manifest':return self.send(200,previews.audio_manifest(item))
                        data,mime=previews.read_audio(item)
                        return self.send(200,data,mime)
                    except VideoRangeUnsatisfiable as error:
                        return self.send(416,{'error':'Audio range outside source'},extra_headers={'Content-Range':f'bytes */{error.size}'})
                    except ReaderChanged:
                        return self.send(409,{'error':'Archive changed; rescan and reopen the reader'})
                    except PreviewBusyError:
                        return self.send(503,{'error':'Preview workers busy'})
                    except (PreviewUnavailable,OSError,RuntimeError,NotImplementedError):
                        return self.send(404,{'error':'Preview unavailable'})
                    except ValueError:
                        return self.send(400,{'error':'Invalid audio range request'})
                if path=='/api/library/restore':
                    if urlparse(self.path).query:return self.send(400,{'error':'Invalid restore query'})
                    return self.send(200,restore_jobs.snapshot())
                if path=='/api/library/backup':
                    if urlparse(self.path).query:return self.send(400,{'error':'Invalid backup query'})
                    return self.send(200,{**backup_jobs.snapshot(),'backup_supported':True,'restore_supported':restore_handoff is not None,
                        'default_selection':{'settings':True,'history':True,'reader_progress':True,'vectors':False}})
                if path=='/api/library/intent/status':return self.send(200,intent.status())
                if path=='/api/library/ai/setup':return self.send(200,{**setup.snapshot(),'selection_api_supported':True,'downloads_supported':download_jobs.supported,'job':setup_jobs.snapshot()})
                if path in ('/api/library/ai/setup/download/catalog','/api/library/ai/setup/download/job'):
                    if urlparse(self.path).query:return self.send(400,{'error':'Invalid acquisition query'})
                    return self.send(200,download_jobs.catalogs() if path.endswith('/catalog') else download_jobs.snapshot())
                if path=='/api/library/ai/setup/job':return self.send(200,setup_jobs.snapshot())
                if path=='/api/library/ai/status': return self.send(200,ai.status())
                if path=='/api/library/ai/profiles': return self.send(200,profiles.snapshot())
                if path=='/api/library/ai/resource':
                    try: return self.send(200,{'policy':profiles.resource()})
                    except (ValueError,OSError,json.JSONDecodeError):
                        return self.send(409,{'error':'AIリソース設定が無効です。設定ファイルを修正するか、モデル選択を保存し直してください。'})
                if path=='/api/library/ai/scope':
                    try:
                        scope=profiles.scope()
                        registered={root['id'] for root in catalog.index.roots()}
                        missing=[root for root in scope['root_ids'] or [] if root not in registered]
                        return self.send(200,{'scope':scope,'valid':not missing,'missing_root_ids':missing,
                            'error':'登録が見つからないフォルダがあります。対象を選び直してください。' if missing else ''})
                    except (ValueError,OSError,json.JSONDecodeError):
                        return self.send(409,{'error':'AI対象設定を読み込めません。対象を選び直して保存してください。文字検索は利用できます。'})
                if path=='/api/library/terms': return self.send(200,{'items':catalog.terms.entries()})
                if path=='/api/library/terms/export': return self.send(200,catalog.terms.export())
                if path=='/api/library/roots':
                    inactive=parse_qs(urlparse(self.path).query).get('include_inactive',['0'])
                    if inactive not in (['0'],['1']):return self.send(400,{'error':'Invalid root filter'})
                    return self.send(200,{'items':catalog.registered_roots(include_inactive=inactive==['1'])})
                if path=='/api/library/scan':
                    return self.send(200,catalog.scan_state())
                if path=='/api/library/startup-scan':return self.send(200,startup_scans.state())
                return self.send(404,{'error':'Not found'})
            return super().do_GET()

        def do_POST(self):
            if self.path=='/api/items/update':
                origin=f'http://127.0.0.1:{self.server.server_port}'
                if not self.valid_host() or self.headers.get('Origin')!=origin or self.headers.get('X-Aredoko-Token')!=token:
                    return self.reject_post(403,{'error':'Invalid session'})
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=32768: return self.reject_post(413,{'error':'Invalid body size'})
                    body=json.loads(self.rfile.read(length))
                    if not isinstance(body,dict): raise ValueError('Expected object')
                    return self.send(200,catalog.update(body.get('ids'),body.get('changes')))
                except ScanBusyError: return self.send(409,{'error':'スキャン中です。完了後に保存し直してください。編集内容は保持されます。'})
                except (ValueError,TypeError): return self.send(400,{'error':'Invalid update'})
                except KeyError: return self.send(404,{'error':'Item not found'})
            if not self.path.startswith('/api/library/'):
                return super().do_POST()
            origin=f'http://127.0.0.1:{self.server.server_port}'
            if not self.valid_host() or self.headers.get('Origin')!=origin or self.headers.get('X-Aredoko-Token')!=token:
                return self.reject_post(403,{'error':'Invalid session'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                # Only an explicit dictionary import may carry a larger document.
                limit=MAX_IMPORT_BYTES if self.path=='/api/library/terms/import' else 32768
                if not 0<length<=limit: return self.reject_post(413,{'error':'Invalid body size'})
                strict=self.path.startswith(('/api/library/animation/','/api/library/results/','/api/library/shelves/','/api/library/backup/','/api/library/startup-scan/')) or self.path in ('/api/library/ai/setup/select','/api/library/ai/setup/cancel','/api/library/history/delete','/api/library/roots/favorite','/api/library/roots/shelves','/api/library/roots/startup-scan')
                body=json.loads(self.rfile.read(length),**({'object_pairs_hook':object_pairs} if strict else {}))
                if not isinstance(body,dict): raise ValueError('Expected an object')
                if self.path.startswith('/api/library/results/'):
                    try:
                        if self.path=='/api/library/results/create':
                            if set(body)!={'session_id','conditions'}:raise ValueError('Invalid result fields')
                            return self.send(200,results.create(**body))
                        if self.path=='/api/library/results/status':
                            if set(body)!={'session_id'}:raise ValueError('Invalid result fields')
                            return self.send(200,results.status(**body))
                        if self.path=='/api/library/results/range':
                            if set(body)!={'session_id','offset','limit'}:raise ValueError('Invalid result fields')
                            return self.send(200,results.read(**body))
                        if self.path=='/api/library/results/neighbor':
                            if set(body)!={'session_id','item_id','direction'}:raise ValueError('Invalid result fields')
                            return self.send(200,results.neighbor(**body))
                        if self.path=='/api/library/results/close':
                            if set(body)!={'session_id'}:raise ValueError('Invalid result fields')
                            return self.send(200,results.cancel(**body))
                        return self.send(404,{'error':'Not found'})
                    except ResultUnavailable as error:
                        return self.send(410 if error.expired else 409,{'error':'Results expired or changed; refresh search',
                            'error_code':'result_session_expired' if error.expired else 'result_session_changed',
                            'conditions':error.conditions,'current_id':body.get('item_id')})
                    except (PreviewUnavailable,ReaderChanged,OSError):
                        return self.send(409,{'error':'Result source unavailable; refresh search','error_code':'result_session_changed',
                            'conditions':body.get('conditions'),'current_id':body.get('item_id')})
                    except ResultCapacity:return self.send(503,{'error':'Result workspace busy or full; close another search', 'error_code':'result_session_capacity'})
                if self.path.startswith('/api/library/animation/'):
                    try:
                        if self.path=='/api/library/animation/open-first':
                            if set(body)!={'item_id','revision','session_id'}:raise ValueError('Invalid animation fields')
                            return self.send(200,animations.open_first(**body),ANIMATION_MIME)
                        if self.path=='/api/library/animation/open':
                            if set(body)!={'item_id','revision','session_id'}:raise ValueError('Invalid animation fields')
                            return self.send(200,animations.open(**body))
                        if self.path=='/api/library/animation/next':
                            if set(body)!={'session_id','count'}:raise ValueError('Invalid animation fields')
                            return self.send(200,animations.pull(**body),ANIMATION_MIME)
                        if self.path=='/api/library/animation/close':
                            if set(body)!={'session_id'}:raise ValueError('Invalid animation fields')
                            return self.send(200,animations.cancel(**body))
                        return self.send(404,{'error':'Not found'})
                    except (ReaderChanged,AnimationGone):return self.send(409,{'error':'Animation source changed or session closed'})
                    except (PreviewBusyError,AnimationBusy):return self.send(503,{'error':'Animation decoder busy'})
                    except (PreviewUnavailable,AnimationUnavailable,OSError,EOFError):return self.send(404,{'error':'Animation unavailable'})
                    except (ValueError,TypeError):return self.send(400,{'error':'Invalid animation request'})
                if self.path.startswith('/api/library/restore/'):
                    try:
                        if self.path=='/api/library/restore/start':return self.send(202,restore_jobs.start(body))
                        if self.path=='/api/library/restore/cancel':return self.send(200,restore_jobs.cancel(body))
                        if self.path=='/api/library/restore/restart':return self.send(202,restore_jobs.request_restart(body))
                        if self.path=='/api/library/restore/discard':return self.send(200,restore_jobs.discard(body))
                        return self.send(404,{'error':'Not found'})
                    except (RestoreBusy,KeyError):return self.send(409,{'error':'復元準備の状態が変わりました。状態を確認してください。'})
                    except (ValueError,TypeError):return self.send(400,{'error':'復元元と選択内容を確認してください。'})
                if self.path.startswith('/api/library/backup/'):
                    try:
                        if self.path=='/api/library/backup/start':return self.send(202,backup_jobs.start(body))
                        if self.path=='/api/library/backup/cancel':
                            if set(body)!={'job_id'}:raise ValueError('Invalid backup cancel fields')
                            return self.send(200,backup_jobs.cancel(body['job_id']))
                        return self.send(404,{'error':'Not found'})
                    except BackupBusy:return self.send(409,{'error':'バックアップを開始できません。現在の処理を確認してください。','job':backup_jobs.snapshot()})
                    except KeyError:return self.send(409,{'error':'現在のバックアップと一致しません。'})
                    except (ValueError,TypeError):return self.send(400,{'error':'バックアップの保存先と選択内容を確認してください。'})
                if self.path.startswith('/api/library/ai/setup/download/'):
                    try:
                        if self.path=='/api/library/ai/setup/download/start':return self.send(202,download_jobs.start(body))
                        if self.path=='/api/library/ai/setup/download/cancel':
                            if set(body)!={'job_id'}:raise ValueError('Invalid acquisition cancel fields')
                            return self.send(200,download_jobs.cancel(body['job_id']))
                        return self.send(404,{'error':'Not found'})
                    except (DownloadBusy,KeyError):return self.send(409,{'error':'AI環境取得の状態が変わりました。状態を確認してください。'})
                    except (ValueError,TypeError):return self.send(400,{'error':'取得するAI環境と速度設定を確認してください。'})
                if self.path=='/api/library/ai/setup/select':
                    try:return self.send(202,setup_jobs.start(body))
                    except SetupBusy:return self.send(409,{'error':'AI環境の確認を開始できません。現在の状態を確認してください。','job':setup_jobs.snapshot()})
                if self.path=='/api/library/ai/setup/cancel':
                    if set(body)!={'job_id'}:raise ValueError('Invalid setup cancel request')
                    try:return self.send(200,setup_jobs.cancel(body['job_id']))
                    except KeyError:return self.send(409,{'error':'現在の確認処理と一致しません。'})
                if self.path.startswith('/api/library/page-text/'):
                    try:
                        if self.path=='/api/library/page-text/generate':
                            if set(body)!={'item_id','page_ids','revision','request_id'}:raise ValueError('Invalid extraction fields')
                            return self.send(200,page_text.generate(**body))
                        if self.path=='/api/library/page-text/cancel':
                            if set(body)!={'request_id'}:raise ValueError('Invalid cancellation fields')
                            return self.send(200,page_text.cancel(body['request_id']))
                        if self.path=='/api/library/page-text/search':
                            if 'query' not in body or set(body)-{'query','kind','view','page','root_ids','shelf','shelf_ids','model'}:
                                raise ValueError('Invalid text search fields')
                            return self.send(200,page_text.search(**body))
                        return self.send(404,{'error':'Not found'})
                    except ReaderChanged:return self.send(409,{'error':'Page source changed; rescan and refresh page index'})
                    except PreviewBusyError:return self.send(503,{'error':'Preview workers busy'})
                    except (PreviewUnavailable,OSError,KeyError):return self.send(404,{'error':'Page source unavailable'})
                    except ScanBusyError:raise
                    except (ValueError,TypeError):return self.send(400,{'error':'Invalid page text request'})
                if self.path=='/api/library/page-index':
                    if set(body)!={'item_id'}:raise ValueError('Invalid page index request')
                    try:return self.send(200,page_index.refresh(body['item_id']))
                    except ReaderChanged:return self.send(409,{'error':'Page source changed; rescan and refresh page index'})
                    except PreviewBusyError:return self.send(503,{'error':'Preview workers busy'})
                    except (PreviewUnavailable,OSError,KeyError):return self.send(404,{'error':'Page source unavailable'})
                if self.path=='/api/library/tag-suggestions/search':
                    if set(body)-{'query','kind','view','page','root_ids','shelf','shelf_ids','model','semantic','request_id'}:raise ValueError('Invalid candidate search fields')
                    semantic=body.pop('semantic',False)
                    if type(semantic) is not bool:raise ValueError('Invalid candidate search mode')
                    if semantic:return self._search_reply(body,lambda cancelled:semantic_candidates(suggestions,ai,**body,cancelled=cancelled))
                    if 'request_id' in body:raise ValueError('Search IDs require semantic search')
                    return self.send(200,search_candidates(suggestions,**body))
                if self.path=='/api/library/tag-suggestions/generate':
                    if set(body)!={'item_id','request_id'}:raise ValueError('Invalid generation request')
                    return self.send(200,suggestions.generate(body['item_id'],body['request_id']))
                if self.path=='/api/library/tag-suggestions/cancel':
                    if set(body)!={'request_id'}:raise ValueError('Invalid cancellation request')
                    return self.send(200,suggestions.cancel(body['request_id']))
                if self.path=='/api/library/tag-suggestions/review':
                    if set(body)-{'item_id','proposal_id','version','decision','tag'} or not {'item_id','proposal_id','version','decision'}<=set(body):
                        raise ValueError('Invalid review request')
                    return self.send(200,suggestions.review(**body))
                if self.path.startswith('/api/library/reader/'):
                    try:
                        match=re.fullmatch(r'/api/library/reader/([1-9][0-9]{0,18})/progress',self.path)
                        if match is None:raise ValueError('Invalid progress route')
                        return self.send(200,catalog.save_reader_progress(int(match[1]),body,previews))
                    except ReaderChanged:return self.send(409,{'error':'Archive changed; reopen before saving progress'})
                    except PreviewBusyError:return self.send(503,{'error':'Preview workers busy'})
                    except (PreviewUnavailable,OSError,zipfile.BadZipFile,RuntimeError,NotImplementedError):return self.send(404,{'error':'Book unavailable'})
                if self.path=='/api/library/terms/import':
                    try: return self.send(200,catalog.terms.import_entries(body))
                    except ValueError as ex: return self.send(400,{'error':str(ex)})
                if self.path=='/api/library/intent/suggest':
                    return self.send(200,intent.suggest(body.get('query'),body.get('source','all'),body.get('kind','')))
                if self.path=='/api/library/ai/profile':
                    if set(body) != {'id'} or type(body['id']) is not str:
                        raise ValueError('Only a profile identifier is accepted')
                    return self.send(200,profiles.choose(body['id']))
                if self.path=='/api/library/ai/scope':
                    if set(body)!={'scope'}:raise ValueError('Only scope is accepted')
                    scope=validate_scope(body['scope'])
                    registered={root['id'] for root in catalog.index.roots()}
                    if any(root not in registered for root in scope['root_ids'] or []):
                        raise ValueError('Unknown registered root')
                    if catalog.scan_state()['state'] in ('running','cancelling') or ai.status()['state'] in ('running','cancelling'):
                        raise AIBusy('スキャンまたはAI索引の完了後に対象を保存してください。')
                    try: saved=profiles.set_scope(scope)
                    except (ValueError,OSError,json.JSONDecodeError):
                        return self.send(409,{'error':'AI対象を保存できません。保存済みの条件を維持します。'})
                    return self.send(200,{'scope':saved,'valid':True,'missing_root_ids':[],'error':''})
                if self.path=='/api/library/ai/coverage':
                    if set(body)-{'scope','limit'}:raise ValueError('Invalid coverage request')
                    scope=validate_scope(body['scope']) if 'scope' in body else None
                    return self.send(200,ai.coverage(scope=scope,limit=body.get('limit',MAX_ITEMS)))
                if self.path=='/api/library/ai/pages/coverage':
                    if set(body)!={'item_id','revision','scope'}:raise ValueError('Invalid page coverage fields')
                    if not isinstance(ai,AISearch):raise AIUnavailable(ai.status()['error'])
                    try:return self.send(200,ai.pages.coverage(body['item_id'],body['revision'],validate_scope(body['scope'])))
                    except ReaderChanged:return self.send(409,{'error':'Page source changed; rescan and refresh page index'})
                    except (PreviewUnavailable,OSError,KeyError):return self.send(404,{'error':'Page source unavailable'})
                if self.path in ('/api/library/ai/pages/chunked/plan',
                                 '/api/library/ai/pages/chunked', '/api/library/ai/pages/chunked/resume'):
                    plan=self.path.endswith('/plan');resume=self.path.endswith('/resume')
                    fields=({'job_id','scope','profile'} if resume else
                            {'item_id','revision','scope','profile','max_pages' if plan else 'page_ids'})
                    if set(body)!=fields:return self.send(400,{'error':'Invalid chunked page request'})
                    if not isinstance(ai,AISearch):raise AIUnavailable(ai.status()['error'])
                    try:
                        scope=validate_scope(body['scope'])
                        if resume:return self.send(200,resume_chunked(ai,body['job_id'],scope,body['profile']))
                        if plan:return self.send(200,plan_chunked(ai,body['item_id'],body['revision'],scope,body['max_pages'],body['profile']))
                        return self.send(200,start_chunked(ai,body['item_id'],body['page_ids'],body['revision'],scope,body['profile']))
                    except ReaderChanged:return self.send(409,{'error':'Page source changed; review a new range'})
                    except (PreviewUnavailable,OSError,KeyError):return self.send(404,{'error':'Page source or saved chunked job unavailable'})
                    except (ValueError,TypeError):return self.send(400,{'error':'Invalid chunked page request'})
                if self.path in ('/api/library/ai/pages/batch','/api/library/ai/pages/batch/resume'):
                    resume=self.path.endswith('/resume')
                    if set(body)!=({'job_id','scope','profile'} if resume else {'items','scope','page_limit','profile'}):raise ValueError('Invalid batch fields')
                    if not isinstance(ai,AISearch):raise AIUnavailable(ai.status()['error'])
                    try:
                        if resume:return self.send(200,resume_batch(ai,body['job_id'],validate_scope(body['scope']),body['profile']))
                        return self.send(200,start_batch(ai,body['items'],validate_scope(body['scope']),body['page_limit'],body['profile']))
                    except ReaderChanged:return self.send(409,{'error':'Page source changed; review a new range'})
                    except (PreviewUnavailable,OSError,KeyError):return self.send(404,{'error':'Page source or saved batch unavailable'})
                if self.path=='/api/library/ai/pages/cancel':
                    if set(body)!={'job_id'} or type(body['job_id']) is not str or not re.fullmatch(r'[0-9a-f]{32}',body['job_id']):raise ValueError('Invalid job ID')
                    accepted=False
                    if isinstance(ai,AISearch):
                        with ai.guard:
                            state=ai.store.state()
                            if state.get('job_id')==body['job_id'] and state.get('state') in ('running','cancelling'):
                                ai.cancel.set();ai.store.save_state({**state,'state':'cancelling'});accepted=True
                    return self.send(200,{'cancel_requested':accepted})
                if self.path=='/api/library/ai/pages':
                    if set(body)!={'item_id','page_ids','revision','scope'}:raise ValueError('Invalid page index fields')
                    if not isinstance(ai,AISearch):raise AIUnavailable(ai.status()['error'])
                    try:return self.send(200,ai.pages.start(body['item_id'],body['page_ids'],body['revision'],validate_scope(body['scope'])))
                    except ReaderChanged:return self.send(409,{'error':'Page source changed; rescan and refresh page index'})
                    except (PreviewUnavailable,OSError,KeyError):return self.send(404,{'error':'Page source unavailable'})
                if self.path in ('/api/library/ai/index/plan','/api/library/ai/index/start','/api/library/ai/index/resume','/api/library/ai/index/cancel'):
                    operation=self.path.rsplit('/',1)[-1]
                    if operation=='cancel':
                        if set(body)!={'job_id'}:raise ValueError('Invalid continuation fields')
                        if not isinstance(ai,AISearch):
                            if type(body['job_id']) is not str or not re.fullmatch(r'[0-9a-f]{32}',body['job_id']):
                                raise ValueError('Invalid job ID')
                            return self.send(200,{'cancel_requested':False,'job_id':body['job_id']})
                        return self.send(200,ai.continuation.cancel(body['job_id']))
                    if not isinstance(ai,AISearch):raise AIUnavailable(ai.status()['error'])
                    fields={'scope','profile'} | ({'limit','after_id'} if operation=='plan' else {'plan_id' if operation=='start' else 'job_id'})
                    if set(body)!=fields:raise ValueError('Invalid continuation fields')
                    scope=validate_scope(body['scope'])
                    if operation=='plan':return self.send(200,ai.continuation.prepare(scope,body['profile'],body['limit'],body['after_id']))
                    if operation=='start':return self.send(200,ai.continuation.start(body['plan_id'],scope,body['profile']))
                    return self.send(200,ai.continuation.resume(body['job_id'],scope,body['profile']))
                if self.path=='/api/library/ai/index':
                    if 'scope' in body:
                        return self.send(200,ai.start(body.get('limit',MAX_ITEMS),scope=validate_scope(body['scope'])))
                    return self.send(200,ai.start(body.get('limit',MAX_ITEMS)))
                if self.path=='/api/library/ai/cancel': return self.send(200,ai.cancel_build())
                if self.path=='/api/library/ai/release':
                    if body: raise ValueError('Release takes no arguments')
                    return self.send(200,ai.release())
                if self.path=='/api/library/ai/resource':
                    policy=validate_resource(body)
                    # No model-space change; the active encoder is never reloaded.
                    # Serialize resource posts; failed persistence must not
                    # change the running policy or start an idle timer.
                    with resource_updates:
                        try:
                            profiles.set_resource(policy)
                        except (ValueError,OSError,json.JSONDecodeError):
                            return self.send(409,{'error':'AIリソース設定を保存できません。設定ファイルを確認してください。動作中の設定は保持されます。'})
                        if isinstance(ai,AISearch): ai.configure(**policy)
                    return self.send(200,{'saved':True,'policy':policy})
                if self.path=='/api/library/ai/searches/prepare':
                    if body:raise ValueError('Expected empty preparation request')
                    if not isinstance(ai,AISearch):raise AIUnavailable(ai.status()['error'])
                    return self.send(200,ai.search_requests.prepare())
                if self.path=='/api/library/ai/searches/cancel':
                    if set(body)!={'request_id'}:raise ValueError('Invalid search cancellation')
                    if not isinstance(ai,AISearch):raise AIUnavailable(ai.status()['error'])
                    return self.send(200,ai.search_requests.cancel(body['request_id']))
                if self.path=='/api/library/ai/similar':
                    if set(body)-{'item_id','kind','view','page','limit','scope','request_id'}:raise ValueError('Invalid similarity request')
                    scope=validate_scope(body['scope']) if 'scope' in body else profiles.scope()
                    try:
                        return self._search_reply(body,lambda cancelled:ai.similar(body.get('item_id'),body.get('kind',''),body.get('view','all'),
                            body.get('page',0),body.get('limit',60),scope=scope,cancelled=cancelled))
                    except KeyError:return self.send(404,{'error':'Similarity source unavailable'})
                if self.path=='/api/library/ai/search':
                    if set(body)-{'query','kind','view','page','source','ranking','scope','literal_only','group_threshold','result_group','request_id'}:raise ValueError('Invalid AI search request')
                    scope_args={'scope':validate_scope(body['scope'])} if 'scope' in body else {}
                    if 'literal_only' in body:scope_args['literal_only']=body['literal_only']
                    if 'group_threshold' in body:scope_args['group_threshold']=body['group_threshold']
                    if 'result_group' in body:scope_args['result_group']=body['result_group']
                    return self._search_reply(body,lambda cancelled:ai.search(body.get('query'),body.get('kind',''),body.get('view','all'),body.get('page',0),source=body.get('source','all'),ranking=body.get('ranking'),cancelled=cancelled,**scope_args))
                if self.path=='/api/library/terms':
                    try: return self.send(200,{'entry':catalog.terms.upsert(body)})
                    except ValueError as ex: return self.send(400,{'error':str(ex)})
                if self.path=='/api/library/terms/delete':
                    if set(body)!={'term'}: raise ValueError('Only term is accepted')
                    try: return self.send(200,catalog.terms.delete(body['term']))
                    except KeyError: return self.send(404,{'error':'Related-term entry not found'})
                if self.path.startswith('/api/library/shelves/'):
                    operation=self.path.rsplit('/',1)[-1]
                    fields={'create':{'name'},'rename':{'shelf_id','name'},'delete':{'shelf_id','consent'},'assign':{'entity','object_ids','shelf_ids'}}
                    if operation not in fields or set(body)!=fields[operation]:raise ValueError('Invalid shelf request')
                    if operation=='delete':
                        if body.pop('consent') is not True:raise ValueError('Explicit shelf deletion consent required')
                    try:return self.send(200,catalog.change_shelf(operation,**body))
                    except ScanBusyError:raise
                    except sqlite3.IntegrityError:return self.send(409,{'error':'Shelf name already exists'})
                    except KeyError:return self.send(404,{'error':'Shelf or item not found'})
                    except ValueError:return self.send(400,{'error':'Invalid shelf request'})
                if self.path=='/api/library/history':
                    if set(body) not in ({'item_id'},{'item_id','generation'}):raise ValueError('Invalid history request')
                    if 'generation' in body and type(body['generation']) is not str:raise ValueError('Invalid history request')
                    try:return self.send(200,catalog.record_view(body['item_id'],body.get('generation')))
                    except HistoryChanged:return self.send(409,{'error':'History generation changed','error_code':'history_changed'})
                if self.path=='/api/library/history/delete':
                    if set(body) not in ({'generation','consent'},{'generation','consent','item_ids'}):raise ValueError('Invalid history request')
                    if 'item_ids' in body and body['item_ids'] is None:raise ValueError('Invalid history item IDs')
                    try:return self.send(200,catalog.delete_history(generation=body['generation'],consent=body['consent'],**({'item_ids':body['item_ids']} if 'item_ids' in body else {})))
                    except HistoryChanged:return self.send(409,{'error':'History generation changed','error_code':'history_changed'})
                if self.path=='/api/library/roots':
                    if body.get('consent') is not True: raise ValueError('Explicit folder consent required')
                    return self.send(200,{'root_id':catalog.add_root(body.get('path'),body.get('excludes'),body.get('default_shelf',''),body.get('folder_books'),body.get('recursive'))})
                if self.path=='/api/library/roots/favorite':
                    if set(body)!={'root_id','favorite'}:raise ValueError('Invalid root favorite request')
                    return self.send(200,catalog.set_root_favorite(body['root_id'],body['favorite']))
                if self.path=='/api/library/roots/startup-scan':
                    if set(body)!={'root_ids','mode'}:raise ValueError('Invalid startup scan request')
                    return self.send(200,catalog.set_root_startup_scan(body['root_ids'],body['mode']))
                if self.path=='/api/library/startup-scan/start':
                    if body!={'frontend_ready':True} or type(body['frontend_ready']) is not bool:raise ValueError('Frontend readiness required')
                    return self.send(200,startup_scans.start())
                if self.path=='/api/library/startup-scan/cancel':
                    if body:raise ValueError('Invalid startup scan cancellation')
                    return self.send(200,startup_scans.cancel())
                if self.path=='/api/library/roots/shelves':
                    if set(body)!={'root_ids','shelf_ids','fill_unset'}:raise ValueError('Invalid root shelf request')
                    return self.send(200,catalog.set_root_shelves(body['root_ids'],body['shelf_ids'],body['fill_unset']))
                if self.path=='/api/library/roots/shelf':
                    if set(body)-{'root_id','shelf','fill_unset'}:raise ValueError('Invalid root filter')
                    return self.send(200,catalog.set_root_shelf(body.get('root_id'),body.get('shelf'),body.get('fill_unset',False)))
                if self.path=='/api/library/roots/unregister':
                    if set(body)!={'root_id'}:raise ValueError('Invalid root filter')
                    return self.send(200,catalog.unregister_root(body['root_id']))
                if self.path=='/api/library/roots/purge':
                    if set(body)!={'root_id','consent'}:raise ValueError('Invalid root filter')
                    if ai.status().get('state') in ('running','cancelling') or suggestions._active is not None or page_text._active is not None:
                        raise AIBusy('AI処理や候補生成の完了後に削除してください。')
                    return self.send(200,catalog.purge_inactive_root(body['root_id'],body['consent']))
                if self.path=='/api/library/excludes':
                    # Avoid racing the index transaction while scanning.
                    return self.send(200,{'excludes':catalog.set_excludes(body.get('root_id'),body.get('patterns'))})
                if self.path=='/api/library/scan':
                    if set(body) - {'root_id', 'root_ids', 'mode'}:
                        raise ValueError('Invalid scan request')
                    return self.send(200, catalog.start_scan(body.get('root_id'), mode=body.get('mode', 'list'), root_ids=body.get('root_ids')))
                if self.path=='/api/library/cancel':
                    res = catalog.cancel_scan()
                    if catalog._scan_mode == 'list_and_ai' and catalog._scan_stage == 'ai':res['ai_cancel_requested']=True
                    return self.send(200, res)
                return self.send(404,{'error':'Not found'})
            except SearchCancelled:return self.send(409,{'error':'検索を中断しました。','error_code':'search_cancelled'})
            except SearchRequestConflict:return self.send(409,{'error':'検索の受付が無効か終了しています。再検索してください。','error_code':'search_request_unavailable'})
            except (ScanBusyError,AIBusy) as ex: return self.send(409,{'error':str(ex)})
            except AIUnavailable as ex: return self.send(503,{'error':str(ex),'error_code':'ai_unavailable'})
            except (ValueError,TypeError) as ex: return self.send(400,{'error':str(ex) if str(ex) in PUBLIC_FOLDER_ERRORS else 'Invalid request: check folder, exclusions or scan state'})
            except KeyError: return self.send(404,{'error':'Root not found'})
            except OSError: return self.send(409,{'error':'Folder unavailable; records preserved'})
    Handler.thumbnails=thumbnails
    Handler.results=results
    Handler.animations=animations
    Handler.backup_jobs=backup_jobs
    Handler.restore_jobs=restore_jobs
    Handler.setup_jobs=setup_jobs
    Handler.startup_scans=startup_scans
    Handler.download_jobs=download_jobs
    return Handler

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8769)
    parser.add_argument('--ai-profile',type=Path)
    parser.add_argument('--ai-python',type=Path,help='Explicit local AI worker interpreter; no PATH fallback or download')
    parser.add_argument('--models-root',type=Path,help='Explicit directory containing local model subdirectories')
    for field in MODEL_ROOT_FIELDS.values():parser.add_argument('--'+field.replace('_','-'),type=Path,help='Restart-only explicit model folder for this role')
    parser.add_argument('--instance-id',help='Launcher-owned session identifier')
    parser.add_argument('--restore-session-dir',type=Path,help='Owned launcher restore handoff directory')
    parser.add_argument('--exit-on-stdin-close',action='store_true',help='Gracefully stop when the owning launcher closes its pipe')
    parser.add_argument('--tagger-profile',type=Path,help='Optional local WD-compatible tagger profile; never downloads')
    parser.add_argument('--ai-settings',type=Path,help='Optional local settings file for developer tests')
    parser.add_argument('--ai-profiles-dir',type=Path,help='Explicit local profile directory, including a restored bundle')
    parser.add_argument('--ai-profile-transient',action='store_true',help='Owned restore session: use frozen active profile until next restart')
    parser.add_argument('--laya-intent',action='store_true',help='Experimental suggestions only; no auto-routing')
    parser.add_argument('--runtime-preferences',type=Path,help='Explicit restart-only launch settings for setup diagnostics')
    parser.add_argument('--ai-ranking',choices=POLICIES,default='mean-rrf')
    parser.add_argument('--intent-questions',choices=QUESTION_SETS,default='v2-hybrid')
    parser.add_argument('--intent-no-order-check',action='store_true',help='Developer comparison only')
    args=parser.parse_args()
    if args.instance_id is not None and (len(args.instance_id)!=32 or any(c not in '0123456789abcdef' for c in args.instance_id)):
        parser.error('--instance-id must be 32 lowercase hex characters')
    if args.restore_session_dir is not None and (not args.exit_on_stdin_close or args.instance_id is None):parser.error('Restore handoff requires an owned instance')
    if args.ai_profile_transient and args.ai_profile is None:parser.error('Transient AI selection requires --ai-profile')
    if any(getattr(args,field) is not None and not getattr(args,field).is_absolute() for field in MODEL_ROOT_FIELDS.values()):parser.error('Role-specific model roots must be absolute')
    storage_parent(args.db)
    with storage_lease(args.db):
        _serve(args)

def _serve(args):
    overrides={field:getattr(args,field) for field in MODEL_ROOT_FIELDS.values() if getattr(args,field,None) is not None}
    runtime={'ai_python':args.ai_python,'models_root':model_root(overrides,'embedding',args.models_root)}
    preferences=getattr(args,'runtime_preferences',None)
    selected={}
    if preferences is not None:
        try:
            selected=read_preferences(preferences)
            if selected.get('ai_runtime_root') and args.ai_python is not None:
                expected=Path(selected['ai_runtime_root'])/'python.exe'
                if expected.absolute()==Path(args.ai_python).absolute():bind_runtime(expected.parent,selected['ai_runtime_manifest_sha256'])
        except (ValueError,OSError,KeyError):pass
    from restore_handoff import RestoreHandoff
    handoff=RestoreHandoff(args.restore_session_dir,args.instance_id,args.db) if args.restore_session_dir is not None else None
    def close_job(job):
        if job.close() is False:raise RuntimeError('Owned job did not stop; restore cannot proceed')
    # Register each owned resource immediately, including startup/bind failures.
    with ExitStack() as resources:
        catalog=ProductionCatalog(args.db);resources.callback(catalog.close)
        profiles=AIProfileSettings(Path(__file__).resolve().parents[1],args.ai_settings,args.ai_profile,args.ai_profiles_dir,transient_override=getattr(args,'ai_profile_transient',False),model_preferences=getattr(args,'runtime_preferences',None),**runtime)
        definition=ModelProfile.from_dict(json.loads(profiles.active_definition)) if profiles.active_definition is not None else None
        placements={LOCATIONS:selected.get(LOCATIONS,[])}
        if definition is not None:
            try:runtime['models_root']=model_root(placements,'embedding',runtime['models_root'],target=ModelTarget.for_profile('embedding',definition))
            except ValueError:pass  # Invalid optional model layout stays AI-unavailable.
            profiles.active_models_root=runtime['models_root']
        ai=DisabledAI(profiles.startup_error, status_code='corrupt_profile') if profiles.startup_error else create_ai(catalog,profiles.startup_path,args.ai_ranking,profile_definition=definition,**runtime)
        resources.callback(ai.close)
        if isinstance(ai,AISearch):
            try: ai.configure(**profiles.resource())
            except (ValueError,OSError,json.JSONDecodeError): ai.configure(**RESOURCE_DEFAULT)
        intent=create_intent(args.laya_intent,args.intent_questions,not args.intent_no_order_check,**{**runtime,'models_root':model_root(overrides,'intent',args.models_root)})
        resources.callback(intent.close)
        try:tag_definition=load_tagger_profile(Path(__file__).resolve().parents[1],args.tagger_profile)
        except (ValueError,OSError):tag_definition=None
        tag_root=model_root(overrides,'tagger',args.models_root)
        if tag_definition is not None:
            try:tag_root=model_root(placements,'tagger',tag_root,target=ModelTarget.for_profile('tagger',tag_definition))
            except ValueError:pass
        tagger=create_tagger(ai,args.tagger_profile,profile_definition=tag_definition,**{**runtime,'models_root':tag_root});resources.callback(tagger.close)
        try:
            acquisition_specs=load_trusted_specs(Path(__file__).resolve().parents[1])
        except (OSError,ValueError,UnicodeError) as error:
            # Broken optional acquisition metadata must not disable the library.
            print('AI acquisition registry unavailable ('+type(error).__name__+')',file=sys.stderr,flush=True)
            acquisition_specs=()
        handler=production_handler(catalog,secrets.token_urlsafe(32),ai,intent,profiles,tagger,instance_id=args.instance_id,runtime_preferences=preferences,tagger_profile_paths=(args.tagger_profile,) if args.tagger_profile else (),restore_handoff=handoff,acquisition_specs=acquisition_specs,thumbnail_disk_path=catalog.path.parent/(catalog.path.name+'.thumbs.sqlite'))
        resources.callback(handler.startup_scans.close)
        resources.callback(close_job,handler.setup_jobs)
        resources.callback(close_job,handler.download_jobs)
        resources.callback(handler.animations.close)
        resources.callback(handler.results.close)
        resources.callback(handler.thumbnails.close)
        resources.callback(close_job,handler.backup_jobs)
        resources.callback(close_job,handler.restore_jobs)
        server=ThreadingHTTPServer(('127.0.0.1',args.port),handler)
        resources.callback(server.server_close)
        if args.exit_on_stdin_close:
            def watch_owner():
                try:
                    while sys.stdin.buffer.read(1):pass
                finally:server.shutdown()
            threading.Thread(target=watch_owner,daemon=True,name='launcher-owner').start()
        print(f'Aredoko production: http://127.0.0.1:{server.server_port}',flush=True)
        try: server.serve_forever(poll_interval=0.1)
        except KeyboardInterrupt: pass
    if handoff is not None:handoff.mark_closed()

if __name__=='__main__': main()

