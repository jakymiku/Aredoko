"""Production-only loopback endpoint. No demo data or source-media writes."""
import argparse
import json
import secrets
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import re
from production import ProductionCatalog, ScanBusyError
from term_relations import MAX_IMPORT_BYTES
from previews import VideoRangeUnsatisfiable, PreviewReader, PreviewUnavailable, PreviewBusyError, ReaderChanged
import zipfile
import sqlite3
from ai_process import EncoderProcess, AIUnavailable
from ai_search import AISearch, AIBusy, MAX_ITEMS
from ai_profiles import load_profile
from ai_settings import AIProfileSettings,validate_resource,RESOURCE_DEFAULT
from ai_ranking import POLICIES
from ai_scope import validate_scope
from search_intent import SearchIntent
from intent_questions import QUESTION_SETS
from laya_process import LayaProcess
from laya_config import model_path as laya_model_path
from server import handler_for
from tag_suggestions import TagSuggestions

class DisabledAI:
    def __init__(self,error=None):
        self.error=error or 'モデル設定またはAI索引を開けません。文字検索は引き続き利用できます。'
    def status(self):
        return {'available':False,'state':'failed','processed':0,'total':0,'indexed':0,
                'skipped':0,'error':self.error}
    def start(self,*args,**kwargs): raise AIUnavailable(self.status()['error'])
    def search(self,*args,**kwargs): raise AIUnavailable(self.status()['error'])
    def similar(self,*args,**kwargs): raise AIUnavailable(self.status()['error'])
    def coverage(self,*args,**kwargs): raise AIUnavailable(self.status()['error'])
    def cancel_build(self): return {'cancel_requested':False}
    def release(self): raise AIUnavailable(self.status()['error'])
    def close(self): pass

def create_ai(catalog,profile_path=None,ranking='mean-rrf'):
    repo=Path(__file__).resolve().parents[1]
    try:
        profile=load_profile(profile_path)
        return AISearch(catalog,EncoderProcess(repo/'.venv-ai/Scripts/python.exe',profile.model_path(repo),profile),ranking=ranking)
    except (AIUnavailable,sqlite3.DatabaseError,OSError,ValueError): return DisabledAI()

def create_intent(enabled=False,question_set='v2-hybrid',check_order=True):
    repo=Path(__file__).resolve().parents[1]
    try:
        return SearchIntent(LayaProcess(repo/'.venv-ai/Scripts/python.exe',laya_model_path(repo),question_set=question_set,check_order=check_order)) if enabled else SearchIntent()
    except (ValueError,OSError):return SearchIntent()

def production_handler(catalog,token,ai=None,intent=None,profiles=None,tagger=None):
    ai=ai or create_ai(catalog)
    intent=intent or SearchIntent()
    profiles=profiles or AIProfileSettings(Path(__file__).resolve().parents[1])
    base=handler_for(catalog,token)
    previews=PreviewReader(catalog)
    resource_updates=threading.Lock()
    suggestions=TagSuggestions(catalog,adapter=tagger,previews=previews)
    class Handler(base):
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
                    return self.send(200,catalog.search(param('q'),param('kind'),param('view','all'),int(page),root_id=root,root_ids=roots))
                except ValueError as ex:return self.send(400,{'error':str(ex)})
            if path=='/api/session':
                return self.send(200,{'mode':'production','token':token,'stats':catalog.stats()})
            # Native client supplies the session token for library-specific reads.
            if path.startswith('/api/library'):
                if self.headers.get('X-Aredoko-Token')!=token:
                    return self.send(403,{'error':'Invalid session'})
                if path.startswith('/api/library/tag-suggestions/'):
                    try:
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
                        match=re.fullmatch(r'/api/library/reader/([1-9][0-9]{0,18})(?:/pages/(0|[1-9][0-9]{0,3}))?',path)
                        if match is None: raise ValueError('Invalid reader route')
                        item=int(match[1])
                        if item > 9223372036854775807: raise ValueError('Invalid item')
                        query=parse_qs(urlparse(self.path).query,keep_blank_values=True,strict_parsing=True,max_num_fields=2)
                        if match[2] is None:
                            if query: raise ValueError('Unexpected reader query')
                            return self.send(200,previews.manifest(item))
                        if set(query)!={'revision'} or len(query['revision'])!=1:
                            raise ValueError('One revision is required')
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
                if path.startswith('/api/library/preview/'):
                    try:
                        match=re.fullmatch(r'/api/library/preview/([1-9][0-9]{0,18})',path)
                        if match is None or urlparse(self.path).query:
                            raise ValueError('Invalid item')
                        item=int(match[1])
                        if item > 9223372036854775807: raise ValueError('Invalid item')
                        data,mime=previews.read(item)
                        return self.send(200,data,mime)
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
                if path=='/api/library/intent/status':return self.send(200,intent.status())
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
                if path=='/api/library/shelves': return self.send(200,{'items':catalog.shelves()})
                if path=='/api/library/roots':
                    inactive=parse_qs(urlparse(self.path).query).get('include_inactive',['0'])
                    if inactive not in (['0'],['1']):return self.send(400,{'error':'Invalid root filter'})
                    return self.send(200,{'items':catalog.index.roots(include_inactive=inactive==['1'])})
                if path=='/api/library/scan': return self.send(200,catalog.scan_state())
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
                body=json.loads(self.rfile.read(length))
                if not isinstance(body,dict): raise ValueError('Expected an object')
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
                if self.path=='/api/library/ai/similar':
                    if set(body)-{'item_id','kind','view','page','limit','scope'}:raise ValueError('Invalid similarity request')
                    scope=validate_scope(body['scope']) if 'scope' in body else profiles.scope()
                    try:
                        return self.send(200,ai.similar(body.get('item_id'),body.get('kind',''),body.get('view','all'),
                            body.get('page',0),body.get('limit',60),scope=scope))
                    except KeyError:return self.send(404,{'error':'Similarity source unavailable'})
                if self.path=='/api/library/ai/search':
                    scope_args={'scope':validate_scope(body['scope'])} if 'scope' in body else {}
                    if 'literal_only' in body:scope_args['literal_only']=body['literal_only']
                    if 'group_threshold' in body:scope_args['group_threshold']=body['group_threshold']
                    if 'result_group' in body:scope_args['result_group']=body['result_group']
                    return self.send(200,ai.search(body.get('query'),body.get('kind',''),body.get('view','all'),body.get('page',0),source=body.get('source','all'),ranking=body.get('ranking'),**scope_args))
                if self.path=='/api/library/terms':
                    try: return self.send(200,{'entry':catalog.terms.upsert(body)})
                    except ValueError as ex: return self.send(400,{'error':str(ex)})
                if self.path=='/api/library/terms/delete':
                    if set(body)!={'term'}: raise ValueError('Only term is accepted')
                    try: return self.send(200,catalog.terms.delete(body['term']))
                    except KeyError: return self.send(404,{'error':'Related-term entry not found'})
                if self.path=='/api/library/roots':
                    if body.get('consent') is not True: raise ValueError('Explicit folder consent required')
                    return self.send(200,{'root_id':catalog.add_root(body.get('path'),body.get('excludes'),body.get('default_shelf',''))})
                if self.path=='/api/library/roots/shelf':
                    if set(body)-{'root_id','shelf','fill_unset'}:raise ValueError('Invalid root filter')
                    return self.send(200,catalog.set_root_shelf(body.get('root_id'),body.get('shelf'),body.get('fill_unset',False)))
                if self.path=='/api/library/roots/unregister':
                    if set(body)!={'root_id'}:raise ValueError('Invalid root filter')
                    return self.send(200,catalog.unregister_root(body['root_id']))
                if self.path=='/api/library/excludes':
                    # Avoid racing the index transaction while scanning.
                    return self.send(200,{'excludes':catalog.set_excludes(body.get('root_id'),body.get('patterns'))})
                if self.path=='/api/library/scan': return self.send(200,catalog.start_scan(body.get('root_id')))
                if self.path=='/api/library/cancel': return self.send(200,catalog.cancel_scan())
                return self.send(404,{'error':'Not found'})
            except (ScanBusyError,AIBusy) as ex: return self.send(409,{'error':str(ex)})
            except AIUnavailable as ex: return self.send(503,{'error':str(ex)})
            except (ValueError,TypeError): return self.send(400,{'error':'Invalid request: check folder, exclusions or scan state'})
            except KeyError: return self.send(404,{'error':'Root not found'})
            except OSError: return self.send(409,{'error':'Folder unavailable; records preserved'})
    return Handler

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8769)
    parser.add_argument('--ai-profile',type=Path)
    parser.add_argument('--ai-settings',type=Path,help='Optional local settings file for developer tests')
    parser.add_argument('--laya-intent',action='store_true',help='Experimental suggestions only; no auto-routing')
    parser.add_argument('--ai-ranking',choices=POLICIES,default='mean-rrf')
    parser.add_argument('--intent-questions',choices=QUESTION_SETS,default='v2-hybrid')
    parser.add_argument('--intent-no-order-check',action='store_true',help='Developer comparison only')
    args=parser.parse_args()
    catalog=ProductionCatalog(args.db)
    profiles=AIProfileSettings(Path(__file__).resolve().parents[1],args.ai_settings,args.ai_profile)
    ai=DisabledAI(profiles.startup_error) if profiles.startup_error else create_ai(catalog,profiles.startup_path,args.ai_ranking)
    if isinstance(ai,AISearch):
        try: ai.configure(**profiles.resource())
        except (ValueError,OSError,json.JSONDecodeError): ai.configure(**RESOURCE_DEFAULT)
    intent=create_intent(args.laya_intent,args.intent_questions,not args.intent_no_order_check)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),production_handler(catalog,secrets.token_urlsafe(32),ai,intent,profiles))
    print(f'Aredoko production: http://127.0.0.1:{server.server_port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: intent.close(); ai.close(); catalog.close(); server.server_close()

if __name__=='__main__': main()

