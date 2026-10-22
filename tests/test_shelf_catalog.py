"""Product shelf adapters on generated catalog/media only."""
import sys,tempfile,unittest
from pathlib import Path
from dataclasses import replace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from production import ProductionCatalog
from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch
class Encoder:
    profile=replace(DEFAULT_PROFILE,dimension=3)
    available=True
    def encode(self,*args):return [1.,0.,0.]
    def close(self):pass
class ShelfCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name);self.media=self.base/'media';self.media.mkdir()
        for name in ('a.png','b.png'):(self.media/name).write_bytes(b'generated-only fixture')
        self.catalog=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.catalog.close);self.root=self.catalog.add_root(str(self.media))
        self.catalog.index.scan(self.root);self.catalog.sync_index();self.ids=[row['id'] for row in self.catalog.search()['items']]
        self.a=self.catalog.change_shelf('create',name='A')['id'];self.b=self.catalog.change_shelf('create',name='B')['id']
        self.catalog.change_shelf('assign',entity='item',object_ids=[self.ids[0]],shelf_ids=[self.a,self.b])
        self.catalog.change_shelf('assign',entity='item',object_ids=[self.ids[1]],shelf_ids=[self.b])
    def test_scope_or_other_conditions_and_no_duplicate_items(self):
        self.assertEqual(self.catalog.search(shelf_ids=[self.a,self.b])['total'],2)
        self.assertEqual(self.catalog.search(shelf='B')['total'],2)
        self.assertEqual(self.catalog.search(shelf_ids=[])['total'],0)
        self.catalog.update([self.ids[0]],{'favorite':True})
        result=self.catalog.search(shelf_ids=[self.b],view='favorites',root_ids=[self.root])
        self.assertEqual([row['id'] for row in result['items']],[self.ids[0]])
        self.assertEqual(result['items'][0]['shelf_ids'],[self.a,self.b])
    def test_ai_scope_selects_secondary_memberships(self):
        ai=AISearch(self.catalog,Encoder());self.addCleanup(ai.close)
        rows=list(ai._iter_rows(scope={'root_ids':[self.root],'shelf_ids':[self.b]}))
        self.assertEqual({row['id'] for row in rows},set(self.ids))
        self.assertEqual({row['id'] for row in ai._iter_rows(scope={'shelf':'B'})},set(self.ids))
    def test_legacy_batch_cannot_drop_membership_or_commit_tags(self):
        with self.assertRaisesRegex(ValueError,'lose multiple'):self.catalog.update(self.ids,{'shelf':'C','tags':['must-not-save']})
        self.assertEqual(self.catalog.get(self.ids[0])['tags'],[])
        self.assertEqual(self.catalog.get(self.ids[1])['shelf'],'B')
        self.catalog.update([self.ids[1]],{'shelf':'C'});self.assertIn('C',self.catalog.shelves())
        self.assertEqual(self.catalog.search(shelf='C')['total'],1)
    def test_scan_inherits_all_root_shelves_and_restart_preserves(self):
        self.catalog.change_shelf('assign',entity='root',object_ids=[self.root],shelf_ids=[self.a,self.b])
        (self.media/'c.png').write_bytes(b'generated-only fixture');self.catalog.index.scan(self.root);self.catalog.sync_index()
        row=next(r for r in self.catalog.search()['items'] if r['title']=='c.png');self.assertEqual(row['shelf_ids'],[self.a,self.b])
        reopened=ProductionCatalog(self.catalog.path);self.addCleanup(reopened.close);self.assertEqual(reopened.get(row['id'])['shelf_ids'],[self.a,self.b])
        with self.assertRaisesRegex(ValueError,'lose multiple'):reopened.set_root_shelf(self.root,'C')
    def test_purge_cleans_junctions_but_keeps_empty_named_shelves(self):
        self.catalog.unregister_root(self.root);self.catalog.purge_inactive_root(self.root,consent=True)
        with self.catalog.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM item_shelves').fetchone()[0],0)
            self.assertIsNone(db.execute('PRAGMA foreign_key_check').fetchone())
        self.assertEqual(set(self.catalog.shelves()),{'A','B'})

    def test_http_shelf_ids_results_and_mutation_contract(self):
        import json,secrets,threading,urllib.request,urllib.error
        from http.server import ThreadingHTTPServer
        from production_server import production_handler
        handler=production_handler(self.catalog,'fixture');handler.log_message=lambda *args:None
        server=ThreadingHTTPServer(('127.0.0.1',0),handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def close():
            server.shutdown();server.server_close();thread.join(5)
            for obj in (handler.setup_jobs,handler.results,handler.animations,handler.thumbnails):obj.close()
        self.addCleanup(close);origin=f'http://127.0.0.1:{server.server_port}'
        def request(path,data=None,token='fixture',raw=False):
            payload=None if data is None else data.encode() if raw else json.dumps(data).encode()
            req=urllib.request.Request(origin+path,data=payload,headers={'Origin':origin,'X-Aredoko-Token':token,'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(req,timeout=5) as response:return response.status,json.load(response)
            except urllib.error.HTTPError as ex:return ex.code,json.load(ex)
        route='/api/library/shelves'
        self.assertEqual(request(route,token='wrong')[0],403)
        self.assertEqual(request('/api/items?shelf_ids='+str(self.b))[1]['total'],2)
        self.assertEqual(request('/api/items?shelf_ids=')[1]['total'],0)
        sid=secrets.token_hex(16)
        response=request('/api/library/results/create',{'session_id':sid,'conditions':{'mode':'literal','shelf_ids':[self.b]}})
        self.assertEqual(response[0],200);self.assertEqual(response[1]['total'],2)
        self.assertEqual(request(route+'/create',{'name':'A'})[0],409)
        created=request(route+'/create',{'name':'empty'});self.assertEqual(created[0],200)
        new_id=created[1]['id']
        self.assertEqual(request(route+'/assign',{'entity':'item','object_ids':[self.ids[1]],'shelf_ids':[self.b,new_id]})[0],200)
        self.assertEqual(request('/api/items?shelf_ids='+str(new_id))[1]['total'],1)
        self.assertEqual(request(route+'/delete',{'shelf_id':new_id,'consent':False})[0],400)
        self.assertEqual(request(route+'/delete','{"shelf_id":'+str(new_id)+',"consent":false,"consent":true}',raw=True)[0],400)
        self.assertEqual(request(route+'/delete',{'shelf_id':new_id,'consent':True})[0],200)
        self.assertEqual(self.catalog.search(shelf_ids=[self.b])['total'],2)
