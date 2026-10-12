"""Production-only loopback endpoint. No demo data or source-media writes."""
import argparse
import json
import secrets
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse
from production import ProductionCatalog, ScanBusyError
from previews import PreviewReader, PreviewUnavailable, PreviewBusyError
import zipfile
import sqlite3
from ai_process import EncoderProcess, AIUnavailable
from ai_search import AISearch, AIBusy, MAX_ITEMS
from ai_profiles import load_profile
from ai_settings import AIProfileSettings
from ai_ranking import POLICIES
from search_intent import SearchIntent
from intent_questions import QUESTION_SETS
from laya_process import LayaProcess
from laya_config import model_path as laya_model_path
from server import handler_for

class DisabledAI:
    def __init__(self,error=None):
        self.error=error or 'モデル設定またはAI索引を開けません。文字検索は引き続き利用できます。'
    def status(self):
        return {'available':False,'state':'failed','processed':0,'total':0,'indexed':0,
                'skipped':0,'error':self.error}
    def start(self,*args): raise AIUnavailable(self.status()['error'])
    def search(self,*args,**kwargs): raise AIUnavailable(self.status()['error'])
    def cancel_build(self): return {'cancel_requested':False}
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

def production_handler(catalog,token,ai=None,intent=None,profiles=None):
    ai=ai or create_ai(catalog)
    intent=intent or SearchIntent()
    profiles=profiles or AIProfileSettings(Path(__file__).resolve().parents[1])
    base=handler_for(catalog,token)
    previews=PreviewReader(catalog)
    class Handler(base):
        def do_GET(self):
            if not self.valid_host(): return self.send(403,{'error':'Invalid host'})
            path=urlparse(self.path).path
            if path=='/api/session':
                return self.send(200,{'mode':'production','token':token,'stats':catalog.stats()})
            # Native client supplies the session token for library-specific reads.
            if path.startswith('/api/library'):
                if self.headers.get('X-Aredoko-Token')!=token:
                    return self.send(403,{'error':'Invalid session'})
                if path.startswith('/api/library/preview/'):
                    try:
                        data,mime=previews.read(int(path.rsplit('/',1)[1]))
                        return self.send(200,data,mime)
                    except PreviewBusyError:
                        return self.send(503,{'error':'Preview workers busy'})
                    except (PreviewUnavailable,OSError,zipfile.BadZipFile,RuntimeError,NotImplementedError):
                        return self.send(404,{'error':'Preview unavailable'})
                    except ValueError:
                        return self.send(400,{'error':'Invalid item'})
                if path=='/api/library/intent/status':return self.send(200,intent.status())
                if path=='/api/library/ai/status': return self.send(200,ai.status())
                if path=='/api/library/ai/profiles': return self.send(200,profiles.snapshot())
                if path=='/api/library/roots': return self.send(200,{'items':catalog.index.roots()})
                if path=='/api/library/scan': return self.send(200,catalog.scan_state())
                return self.send(404,{'error':'Not found'})
            return super().do_GET()

        def do_POST(self):
            if self.path=='/api/items/update':
                origin=f'http://127.0.0.1:{self.server.server_port}'
                if not self.valid_host() or self.headers.get('Origin')!=origin or self.headers.get('X-Aredoko-Token')!=token:
                    return self.send(403,{'error':'Invalid session'})
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=32768: return self.send(413,{'error':'Invalid body size'})
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
                return self.send(403,{'error':'Invalid session'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=32768: return self.send(413,{'error':'Invalid body size'})
                body=json.loads(self.rfile.read(length))
                if not isinstance(body,dict): raise ValueError('Expected an object')
                if self.path=='/api/library/intent/suggest':
                    return self.send(200,intent.suggest(body.get('query'),body.get('source','all'),body.get('kind','')))
                if self.path=='/api/library/ai/profile':
                    if set(body) != {'id'} or type(body['id']) is not str:
                        raise ValueError('Only a profile identifier is accepted')
                    return self.send(200,profiles.choose(body['id']))
                if self.path=='/api/library/ai/index': return self.send(200,ai.start(body.get('limit',MAX_ITEMS)))
                if self.path=='/api/library/ai/cancel': return self.send(200,ai.cancel_build())
                if self.path=='/api/library/ai/search':
                    return self.send(200,ai.search(body.get('query'),body.get('kind',''),body.get('view','all'),body.get('page',0),source=body.get('source','all'),ranking=body.get('ranking')))
                if self.path=='/api/library/roots':
                    if body.get('consent') is not True: raise ValueError('Explicit folder consent required')
                    return self.send(200,{'root_id':catalog.add_root(body.get('path'),body.get('excludes'))})
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
    intent=create_intent(args.laya_intent,args.intent_questions,not args.intent_no_order_check)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),production_handler(catalog,secrets.token_urlsafe(32),ai,intent,profiles))
    print(f'Aredoko production: http://127.0.0.1:{server.server_port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: intent.close(); ai.close(); catalog.close(); server.server_close()

if __name__=='__main__': main()
