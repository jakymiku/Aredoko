"""Generated-only frozen-selection editing; no UI, model or GPU."""
import json,sys,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from production import ProductionCatalog
from result_sessions import ResultSessions,ResultUnavailable
from selection_edits import apply

class SelectionEditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.media=self.base/'media';self.media.mkdir()
        for n in range(4):(self.media/f'{n}.png').write_bytes(b'generated-only')
        self.cat=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.cat.close)
        self.root=self.cat.add_root(str(self.media));self.cat.start_scan(self.root);self.cat._worker.join(3)
        self.ids=[r['id'] for r in self.cat.search()['items']];self.number=0
        def provider(conditions,consume,cancelled):return consume(lambda page:self.cat.search(page=page,**conditions))
        self.owner=ResultSessions(self.cat,provider,parent=self.base);self.addCleanup(self.owner.close)
    def session(self,**conditions):
        self.number+=1;sid=f'{self.number:032x}';self.owner.create(sid,conditions);return sid
    def edit(self,ids,operation,shelves=None,**conditions):
        sid=self.session(**conditions)
        try:return self.owner.edit(sid,ids,operation,shelves or [])
        finally:self.owner.cancel(sid)
    def test_favorites_are_explicit_and_do_not_save_other_drafts(self):
        self.cat.update([self.ids[0]],{'tags':['keep'],'favorite':True})
        result=self.edit(self.ids[:2],'favorite_add')
        self.assertEqual(result['updated'],2)
        self.assertTrue(all(self.cat.get(i)['favorite'] for i in self.ids[:2]));self.assertEqual(self.cat.get(self.ids[0])['tags'],['keep'])
        self.edit(self.ids[:2],'favorite_remove');self.assertFalse(any(self.cat.get(i)['favorite'] for i in self.ids[:2]))
    def test_shelf_add_and_remove_preserve_other_memberships(self):
        a=self.cat.change_shelf('create',name='a')['id'];b=self.cat.change_shelf('create',name='b')['id'];c=self.cat.change_shelf('create',name='c')['id']
        self.cat.update([self.ids[0]],{'shelf_ids':[a]});self.cat.update([self.ids[1]],{'shelf_ids':[b]})
        self.edit(self.ids[:2],'shelves_add',[c]);self.assertEqual(self.cat.get(self.ids[0])['shelf_ids'],[a,c]);self.assertEqual(self.cat.get(self.ids[1])['shelf_ids'],[b,c])
        self.edit(self.ids[:2],'shelves_remove',[c]);self.assertEqual(self.cat.get(self.ids[0])['shelf_ids'],[a]);self.assertEqual(self.cat.get(self.ids[1])['shelf_ids'],[b])
    def test_outside_frozen_scope_rejects_the_entire_edit(self):
        self.cat.update([self.ids[0]],{'favorite':True});sid=self.session(view='favorites')
        with self.assertRaises(ResultUnavailable):self.owner.edit(sid,self.ids[:2],'favorite_remove',[])
        self.assertTrue(self.cat.get(self.ids[0])['favorite'])
    def test_source_change_and_unregister_reject_without_partial_write(self):
        sid=self.session();(self.media/'1.png').write_bytes(b'changed-size')
        with self.assertRaises(ResultUnavailable):self.owner.edit(sid,self.ids[:2],'favorite_add',[])
        self.assertFalse(any(self.cat.get(i)['favorite'] for i in self.ids[:2]));self.owner.cancel(sid)
        sid=self.session();self.cat.unregister_root(self.root)
        with self.assertRaises(ResultUnavailable):self.owner.edit(sid,self.ids[:2],'favorite_add',[])
        self.assertFalse(any(self.cat.get(i)['favorite'] for i in self.ids[:2]))
    def test_cancel_at_publication_rolls_back_all_metadata(self):
        sid=self.session();session=self.owner.sessions[sid]
        def cancelled(db,ids,operation,shelves):apply(db,ids,operation,shelves);session.stop.set()
        with patch('selection_edits.apply',side_effect=cancelled),self.assertRaises(ResultUnavailable):self.owner.edit(sid,self.ids[:2],'favorite_add',[])
        self.assertFalse(any(self.cat.get(i)['favorite'] for i in self.ids[:2]))
    def test_invalid_ids_operations_and_shelves_are_atomic(self):
        sid=self.session()
        for ids,op,shelves in [([], 'favorite_add',[]),([True],'favorite_add',[]),([self.ids[0]]*2,'favorite_add',[]),([self.ids[0]]*257,'favorite_add',[]),(self.ids[:1],'toggle',[]),(self.ids[:1],'favorite_add',[1]),(self.ids[:1],'shelves_add',[])]:
            with self.assertRaises(ValueError):self.owner.edit(sid,ids,op,shelves)
        with self.assertRaises(KeyError):self.owner.edit(sid,self.ids[:2],'shelves_add',[999])
        self.assertFalse(any(self.cat.get(i)['favorite'] for i in self.ids))
    def test_union_shelf_limit_rejects_without_touching_any_item(self):
        shelves=[self.cat.change_shelf('create',name=f's{n}')['id'] for n in range(65)]
        self.cat.update([self.ids[1]],{'shelf_ids':shelves[:64]})
        with self.assertRaises(ValueError):self.edit(self.ids[:2],'shelves_add',shelves[64:])
        self.assertEqual(self.cat.get(self.ids[0])['shelf_ids'],[]);self.assertEqual(len(self.cat.get(self.ids[1])['shelf_ids']),64)
    def test_locate_returns_only_current_scope_in_server_order(self):
        self.cat.update(self.ids[:2],{'favorite':True});sid=self.session(view='favorites')
        positions=self.owner.locate(sid,list(reversed(self.ids)))['positions']
        self.assertEqual(positions,[{'id':self.ids[0],'ordinal':0},{'id':self.ids[1],'ordinal':1}])
        self.owner.edit(sid,self.ids[:1],'favorite_remove',[])
        with self.assertRaises(ResultUnavailable):self.owner.locate(sid,self.ids[:1])
    def test_http_edit_and_locate_require_authentication_and_strict_fields(self):
        from production_server import production_handler,DisabledAI
        from ai_settings import AIProfileSettings
        from wd_tagger import DisabledTagger
        profiles=AIProfileSettings(Path(__file__).resolve().parents[1],self.base/'settings.json',profile_directory=self.base/'profiles')
        handler=production_handler(self.cat,'fixture',ai=DisabledAI(),tagger=DisabledTagger(),profiles=profiles);handler.log_message=lambda *a:None
        server=ThreadingHTTPServer(('127.0.0.1',0),handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def close():
            server.shutdown();server.server_close();thread.join(5)
            for resource in (handler.startup_scans,handler.results,handler.animations,handler.thumbnails,handler.setup_jobs):resource.close()
        self.addCleanup(close);origin=f'http://127.0.0.1:{server.server_port}'
        def request(route,body,token='fixture'):
            value=body if isinstance(body,str) else json.dumps(body)
            req=urllib.request.Request(origin+'/api/library/results/'+route,data=value.encode(),headers={'Origin':origin,'X-Aredoko-Token':token,'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(req,timeout=5) as reply:return reply.status,json.load(reply)
            except urllib.error.HTTPError as ex:
                with ex:return ex.code,json.load(ex)
        sid='a'*32
        self.assertEqual(request('create',{'session_id':sid,'conditions':{'mode':'literal','query':'','kind':'','view':'all'}})[0],200)
        body={'session_id':sid,'item_ids':self.ids[:2],'operation':'favorite_add','shelf_ids':[]}
        self.assertEqual(request('edit',body,'wrong')[0],403)
        self.assertEqual(request('edit',{**body,'unknown':True})[0],400)
        self.assertEqual(request('edit',json.dumps(body)[:-1]+',"operation":"favorite_remove"}')[0],400)
        self.assertEqual(request('locate',{'session_id':sid,'item_ids':self.ids})[0],200)
        self.assertEqual(request('edit',body)[0],200)
        self.assertEqual(request('edit',body)[0],409)
        self.assertTrue(all(self.cat.get(i)['favorite'] for i in self.ids[:2]))

if __name__=='__main__':unittest.main()
