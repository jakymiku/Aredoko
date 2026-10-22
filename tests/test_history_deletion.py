"""Generated-only history deletion, stale delivery and authenticated HTTP."""
import json,secrets,sys,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from production import ProductionCatalog,HistoryChanged
from production_server import production_handler
from result_sessions import ResultSessions,ResultUnavailable

class HistoryDeletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.media=self.base/'media';self.media.mkdir()
        for name in ('one.png','two.png'):(self.media/name).write_bytes(b'generated index-only fixture')
        self.before={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.media.iterdir()}
        self.db=self.base/'catalog.sqlite';self.catalog=ProductionCatalog(self.db);self.addCleanup(self.catalog.close)
        root=self.catalog.add_root(str(self.media));self.catalog.index.scan(root);self.catalog.sync_index()
        self.ids=[row['id'] for row in self.catalog.search()['items']]
        self.generation=self.catalog.history_status()['generation']
        for item in self.ids:self.catalog.record_view(item,self.generation)
    def clear(self,**kwargs):return self.catalog.delete_history(generation=self.generation,consent=True,**kwargs)
    def test_individual_preserves_progress_annotations_and_sources(self):
        self.catalog.update([self.ids[0]],{'tags':['keep'],'shelf':'kept','favorite':True})
        with self.catalog.connect() as db:db.execute("INSERT INTO reader_progress VALUES(?,?,?,?)",(self.ids[0],'generated-revision',3,'rtl'))
        self.assertEqual(self.clear(item_ids=[self.ids[0]])['removed'],1)
        self.assertEqual([r['id'] for r in self.catalog.search(view='history')['items']],[self.ids[1]])
        self.assertEqual(self.catalog.get(self.ids[0])['tags'],['keep'])
        with self.catalog.connect() as db:self.assertEqual(tuple(db.execute('SELECT page,mode FROM reader_progress').fetchone()),(3,'rtl'))
        self.assertEqual(self.before,{p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.media.iterdir()})
    def test_clear_rejects_stale_and_legacy_events_but_new_open_works(self):
        result=self.clear();self.assertEqual(result['removed'],2)
        for old in (self.generation,None):
            with self.assertRaises(HistoryChanged):self.catalog.record_view(self.ids[0],old)
        self.assertEqual(self.catalog.history_status()['count'],0)
        self.catalog.record_view(self.ids[0],result['generation']);self.assertEqual(self.catalog.history_status()['count'],1)
    def test_delayed_thread_cannot_resurrect_deleted_history(self):
        gate=threading.Event();done=[]
        def late():
            gate.wait(5)
            try:self.catalog.record_view(self.ids[0],self.generation)
            except HistoryChanged:done.append('rejected')
        thread=threading.Thread(target=late);thread.start();self.clear();gate.set();thread.join(5)
        self.assertFalse(thread.is_alive());self.assertEqual(done,['rejected']);self.assertEqual(self.catalog.history_status()['count'],0)
    def test_invalid_request_leaves_history_and_generation_unchanged(self):
        for ids in ([],[True],[0],[self.ids[0]]*2,list(range(1,258))):
            with self.subTest(ids=ids),self.assertRaises(ValueError):self.clear(item_ids=ids)
        with self.assertRaises(ValueError):self.catalog.delete_history(generation=self.generation,consent=1)
        with self.assertRaises(HistoryChanged):self.catalog.delete_history(generation='wrong',consent=True)
        self.assertEqual(self.catalog.history_status(),{'generation':self.generation,'count':2})
    def test_deletion_persists_and_old_process_generation_is_rejected(self):
        self.clear();reopened=ProductionCatalog(self.db);self.addCleanup(reopened.close)
        self.assertEqual(reopened.history_status()['count'],0)
        with self.assertRaises(HistoryChanged):reopened.record_view(self.ids[0],self.generation)
    def test_clear_invalidates_frozen_history_results(self):
        def provider(conditions,consume,cancelled):consume(lambda page:self.catalog.search(view='history',page=page,limit=120))
        sessions=ResultSessions(self.catalog,provider);self.addCleanup(sessions.close)
        sid=secrets.token_hex(16);sessions.create(sid,{'mode':'history'});self.clear()
        with self.assertRaises(ResultUnavailable):sessions.read(sid,0,120)
    def test_http_auth_shape_and_stale_record(self):
        handler=production_handler(self.catalog,'test-token');handler.log_message=lambda *args:None
        server=ThreadingHTTPServer(('127.0.0.1',0),handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def cleanup():
            server.shutdown();server.server_close();thread.join(5)
            for obj in (handler.setup_jobs,handler.results,handler.animations,handler.thumbnails):obj.close()
        self.addCleanup(cleanup)
        origin=f'http://127.0.0.1:{server.server_port}'
        def request(path,body=None,token='test-token'):
            req=urllib.request.Request(origin+path,data=None if body is None else json.dumps(body).encode(),headers={'Origin':origin,'X-Aredoko-Token':token,'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(req,timeout=5) as response:return response.status,json.load(response)
            except urllib.error.HTTPError as ex:return ex.code,json.load(ex)
        route='/api/library/history';self.assertEqual(request(route,token='bad')[0],403)
        status=request(route);self.assertEqual(status[0],200);self.assertEqual(status[1]['count'],2)
        self.assertEqual(request(route+'/delete',{'generation':self.generation,'consent':True,'item_ids':None})[0],400)
        result=request(route+'/delete',{'generation':self.generation,'consent':True});self.assertEqual(result[0],200)
        self.assertEqual(request(route,{'item_id':self.ids[0],'generation':self.generation})[0],409)
        self.assertEqual(request(route,{'item_id':self.ids[0]})[0],409)
        self.assertEqual(request(route,{'item_id':self.ids[0],'generation':None})[0],400)
        self.assertEqual(request(route,{'item_id':self.ids[0],'generation':result[1]['generation']})[0],200)
