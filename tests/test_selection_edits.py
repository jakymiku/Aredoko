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
        def provider(conditions,consume,cancelled):return consume(lambda page:self.cat.search(page=page,**{k:v for k,v in conditions.items() if k!='mode'}))
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

    def test_literal_favorite_patch_keeps_frozen_order_and_only_checks_selected_sources(self):
        sid=self.session(mode='literal');old=self.owner.read(sid)['items']
        original=self.owner.sessions[sid]._currents;checked=[]
        def capture(items,**kw):checked.extend(item['id'] for item in items);return original(items,**kw)
        with patch.object(self.owner.sessions[sid],'_currents',side_effect=capture):
            result=self.owner.edit(sid,self.ids[:1],'favorite_add',[],keep_session=True)
        self.assertTrue(result['kept_session']);self.assertEqual(checked,self.ids[:1])
        current=self.owner.read(sid)['items'];self.assertEqual([r['id'] for r in old],[r['id'] for r in current])
        self.assertEqual([r['favorite'] for r in current],[True,False,False,False])
        self.assertTrue(self.owner.edit(sid,self.ids[:1],'favorite_remove',[],keep_session=True)['kept_session'])
        self.assertFalse(self.owner.read(sid)['items'][0]['favorite'])
        self.cat.update(self.ids[1:2],{'tags':['unrelated change']})
        with self.assertRaises(ResultUnavailable):self.owner.read(sid)

    def test_favorite_filtered_and_ranked_results_still_require_refresh(self):
        for conditions in ({'mode':'literal','view':'favorites'},{'mode':'semantic','view':'favorites'}):
            self.cat.update(self.ids,{'favorite':True})
            sid=self.session(**conditions)
            result=self.owner.edit(sid,self.ids[:1],'favorite_remove',[],keep_session=True)
            self.assertFalse(result['kept_session'])
            with self.assertRaises(ResultUnavailable):self.owner.read(sid)
            self.owner.cancel(sid)

    def test_ai_similar_and_shelf_sessions_keep_frozen_order_on_favorite_patch(self):
        shelf=self.cat.change_shelf('create',name='shelf-keep')['id']
        self.cat.update(self.ids,{'shelf_ids':[shelf]})
        origin=self.ids[-1]
        original_provider=self.owner.provider
        def sim_provider(conditions,consume,cancelled):
            if conditions.get('mode')=='similar':
                return consume(lambda page:{**self.cat.search(page=page),'origin_id':origin} if page==0 else {'total':len(self.ids),'page':page,'limit':60,'items':[]})
            return original_provider(conditions,consume,cancelled)
        with patch.object(self.owner,'provider',side_effect=sim_provider):
            for conditions in ({'mode':'semantic','view':'all'},{'mode':'literal','view':'shelf'},{'mode':'similar','view':'all'}):
                sid=self.session(**conditions)
                old=self.owner.read(sid)['items']
                result=self.owner.edit(sid,self.ids[:1],'favorite_add',[],keep_session=True)
                self.assertTrue(result['kept_session'],conditions)
                current=self.owner.read(sid)['items']
                self.assertEqual([r['id'] for r in old],[r['id'] for r in current])
                self.assertTrue(current[0]['favorite'])
                self.assertTrue(self.owner.edit(sid,self.ids[:1],'favorite_remove',[],keep_session=True)['kept_session'])
                self.assertFalse(self.owner.read(sid)['items'][0]['favorite'])
                self.cat.update(self.ids[1:2],{'tags':['unrelated-change']})
                with self.assertRaises(ResultUnavailable):self.owner.read(sid)
                self.owner.cancel(sid)

    def test_maximum_favorite_selection_keeps_order_without_recapturing_unselected_sources(self):
        for n in range(4,724):(self.media/f'{n:04}.png').write_bytes(b'generated-only')
        self.cat.start_scan(self.root);self.cat._worker.join(5)
        self.assertFalse(self.cat._worker.is_alive())
        with patch.object(self.owner,'provider',wraps=self.owner.provider) as provider:
            sid=self.session(mode='literal',view='all');session=self.owner.sessions[sid]
            def snapshot():
                return [row for offset in range(0,session.total,120) for row in self.owner.read(sid,offset,120)['items']]
            old=snapshot();self.assertEqual(len(old),724)
            ids=[row['id'] for row in old[:255]]+[old[-1]['id']];checked=[]
            original=session._currents
            def capture(items,**kw):checked.extend(item['id'] for item in items);return original(items,**kw)
            with patch.object(session,'_currents',side_effect=capture):
                result=self.owner.edit(sid,ids,'favorite_add',[],keep_session=True)
            self.assertTrue(result['kept_session']);self.assertEqual(result['updated'],256)
            self.assertCountEqual(checked,ids);self.assertEqual(len(checked),256)
            current=snapshot();self.assertEqual(provider.call_count,1)
            self.assertEqual([r['id'] for r in current],[r['id'] for r in old])
            for before,after in zip(old,current):
                self.assertEqual(after,{**before,'favorite':True} if after['id'] in ids else before)

    def test_later_private_patch_failure_invalidates_the_batch_after_saved_metadata(self):
        sid=self.session(mode='literal');session=self.owner.sessions[sid]
        session.db.execute('CREATE TRIGGER fail_patch BEFORE UPDATE ON results WHEN OLD.item_id='+str(self.ids[1])+" BEGIN SELECT RAISE(ABORT,'generated failure'); END")
        result=self.owner.edit(sid,self.ids[:2],'favorite_add',[],keep_session=True)
        self.assertFalse(result['kept_session'])
        self.assertTrue(all(self.cat.get(i)['favorite'] for i in self.ids[:2]))
        self.assertTrue(session.stop.is_set());self.assertFalse(session.path.exists())
        with self.assertRaises(ResultUnavailable):self.owner.read(sid)

    def test_retention_never_absorbs_an_extra_generation_or_index_change(self):
        sid=self.session(mode='literal');original=apply
        def extra(db,*args):
            original(db,*args)
            with self.cat._result_generation_lock:self.cat._result_generation+=1
        with patch('selection_edits.apply',side_effect=extra):
            # The existing pre-commit check rejects the extra generation and
            # rolls back instead of rebasing over an unrelated metadata edit.
            with self.assertRaises(ResultUnavailable):self.owner.edit(sid,self.ids[:1],'favorite_add',[],keep_session=True)
        self.assertFalse(self.cat.get(self.ids[0])['favorite'])

    def test_private_patch_failure_reports_saved_but_requires_refresh(self):
        import sqlite3
        sid=self.session(mode='literal');db=self.owner.sessions[sid].db
        db.set_authorizer(lambda action,table,*_:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_UPDATE and table=='results' else sqlite3.SQLITE_OK)
        result=self.owner.edit(sid,self.ids[:1],'favorite_add',[],keep_session=True)
        self.assertFalse(result['kept_session']);self.assertTrue(self.cat.get(self.ids[0])['favorite'])
        with self.assertRaises(ResultUnavailable):self.owner.read(sid)

    def test_after_commit_stamp_failure_or_extra_write_never_reports_a_failed_save(self):
        original=self.cat.edit_result_selection
        for changes in ('exception','generation'):
            sid=self.session(mode='literal')
            def wrapped(*args,after_commit=None):
                def committed():
                    if changes=='exception':
                        self.owner.sessions[sid].stamp=lambda:(_ for _ in ()).throw(OSError('generated missing sidecar'))
                    else:
                        with self.cat._result_generation_lock:self.cat._result_generation+=1
                    return after_commit()
                return original(*args,after_commit=committed)
            with patch.object(self.cat,'edit_result_selection',side_effect=wrapped):
                result=self.owner.edit(sid,self.ids[:1],'favorite_add',[],keep_session=True)
            self.assertFalse(result['kept_session']);self.assertTrue(self.cat.get(self.ids[0])['favorite'])
            self.owner.cancel(sid)
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
        sid=self.session();(self.media/self.cat.get(self.ids[0])['relative_path']).write_bytes(b'changed-size')
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
        self.assertEqual(request('edit',{**body,'keep_session':'true'})[0],400)
        self.assertEqual(request('edit',json.dumps(body)[:-1]+',"operation":"favorite_remove"}')[0],400)
        self.assertEqual(request('locate',{'session_id':sid,'item_ids':self.ids})[0],200)
        code,reply=request('edit',{**body,'keep_session':True});self.assertEqual(code,200);self.assertTrue(reply['kept_session'])
        self.assertEqual(request('locate',{'session_id':sid,'item_ids':self.ids})[0],200)
        # Legacy requests still commit and invalidate the owner as before.
        self.assertEqual(request('edit',body)[0],200)
        self.assertEqual(request('edit',body)[0],409)
        self.assertTrue(all(self.cat.get(i)['favorite'] for i in self.ids[:2]))

if __name__=='__main__':unittest.main()
