"""Generated books and deterministic vectors: lifecycle, not model accuracy."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))

from test_page_index import PageFixture
from ai_profiles import DEFAULT_PROFILE
from ai_process import AIUnavailable
from ai_search import AISearch, AIBusy
from production_server import production_handler
from previews import ReaderChanged, PreviewUnavailable
from create_preview_fixture import png


class Encoder:
    available=True
    def __init__(self, dimension=8):
        self.profile=replace(DEFAULT_PROFILE,dimension=dimension)
        self.calls=[];self.hook=None
    def encode(self,operation,value):
        self.calls.append((operation,value))
        if self.hook:self.hook(operation,value)
        axis=1 if operation=='query' or value==png(color=(90,80,70)) else 0
        return [float(i==axis) for i in range(self.profile.dimension)]
    def close(self):pass


class PageSemanticTests(PageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.encoder=Encoder();self.ai=AISearch(self.catalog,self.encoder);self.addCleanup(self.ai.close)
        self.item=self.ids['comic.cbz'];self.scope={'root_ids':[self.root]}
        self.pages.refresh(self.item);self.snapshot=self.pages.list(self.item)
        self.revision=self.snapshot['source_revision']
        self.page_ids=[p['page_id'] for p in self.snapshot['pages']]
    def build(self, page_ids=None, expected='complete'):
        self.ai.pages.start(self.item,self.page_ids if page_ids is None else page_ids,self.revision,self.scope)
        self.ai.worker.join(10);self.assertFalse(self.ai.worker.is_alive())
        self.assertEqual(self.ai.status()['state'],expected,self.ai.status())
    def records(self):
        with self.ai.store.connect() as db:return db.execute('SELECT * FROM ai_page_vectors ORDER BY item_id,page').fetchall()
    def search(self,**kwargs):return self.ai.search('内側の青いページ',source='cover',scope=self.scope,**kwargs)

    def test_no_automatic_page_inference_and_explicit_range_reuse_aggregation(self):
        self.ai.start(scope=self.scope);self.ai.worker.join(10)
        self.assertEqual(self.records(),[])
        before=(self.archive.read_bytes(),self.archive.stat().st_mtime_ns)
        self.catalog.update([self.item],{'tags':['手動'],'shelf':'保存','favorite':True})
        self.build([self.page_ids[1]])
        self.assertEqual(len(self.records()),1)
        result=self.search();match=result['items'][0]['ai_page_match']
        self.assertEqual(result['items'][0]['id'],self.item);self.assertEqual(match['page'],1)
        self.assertEqual((match['page_id'],match['source_revision'],match['model_revision']),
            (self.page_ids[1],self.revision,self.encoder.profile.revision))
        calls=len(self.encoder.calls);self.build([self.page_ids[1]])
        self.assertEqual(len(self.encoder.calls),calls);self.assertEqual(self.ai.status()['reused'],1)
        self.build([self.page_ids[0]]);self.assertEqual(len(self.records()),2)
        self.assertEqual(sum(r['id']==self.item for r in self.search()['items']),1)
        self.assertEqual(before,(self.archive.read_bytes(),self.archive.stat().st_mtime_ns))
        self.assertEqual(self.catalog.get(self.item)['tags'],['手動'])
        self.assertEqual(self.catalog.get(self.item)['shelf'],'保存')
        self.assertTrue(self.catalog.get(self.item)['favorite'])

    def test_page_vectors_work_without_cover_and_never_enter_text_search(self):
        self.build()
        self.assertEqual(self.search()['total'],1)
        self.assertEqual(self.search()['items'][0]['ai_page_match']['page'],1)
        self.assertEqual(self.ai.search('内側',source='text',scope=self.scope)['total'],0)
        self.assertEqual(self.ai.search('内側',source='all',scope=self.scope)['items'][0]['ai_page_match']['page'],1)

    def test_cancel_and_failed_range_keep_previous_complete_pages(self):
        self.build([self.page_ids[0]]);old=self.records()
        self.encoder.hook=lambda *args:self.ai.cancel.set()
        self.build(expected='cancelled');self.assertEqual(self.records(),old)
        self.encoder.hook=None
        with patch.object(self.ai.pages.index,'input',side_effect=PreviewUnavailable('fixture')):
            self.build(expected='failed')
        self.assertEqual(self.records(),old)
        self.build();self.assertEqual(len(self.records()),2);self.assertEqual(self.ai.status()['reused'],1)

    def test_source_change_during_inference_and_stale_query_are_suppressed(self):
        self.build([self.page_ids[0]]);old=self.records()
        self.encoder.hook=lambda *args:self.write_archive([('1.png',self.first),('2.png',png(color=(1,2,3)))])
        self.build(expected='failed');self.assertEqual(self.records(),old)
        self.encoder.hook=None
        self.assertEqual(self.search()['total'],0)
        with self.assertRaises(ReaderChanged):self.ai.pages.start(self.item,self.page_ids,self.revision,self.scope)
        self.scan();self.pages.refresh(self.item);self.snapshot=self.pages.list(self.item)
        self.revision=self.snapshot['source_revision'];self.page_ids=[p['page_id'] for p in self.snapshot['pages']]
        self.build();self.assertTrue(all(r[1]==self.revision for r in self.records()))

    def test_scope_change_during_inference_preserves_old_vectors(self):
        self.build([self.page_ids[0]]);old=self.records()
        self.encoder.hook=lambda *args:self.catalog.set_excludes(self.root,['*.cbz'])
        self.build(expected='failed');self.assertEqual(self.records(),old)
        self.assertEqual(self.search()['total'],0)

    def test_folder_book_and_metadata_change_keep_physical_revision(self):
        self.item=self.ids['comic/'];self.scope={'root_ids':[self.bookroot]}
        self.pages.refresh(self.item);snapshot=self.pages.list(self.item)
        self.revision=snapshot['source_revision'];self.page_ids=[p['page_id'] for p in snapshot['pages']]
        self.build();calls=len(self.encoder.calls)
        self.catalog.update([self.item],{'tags':['changed'],'favorite':True})
        self.build();self.assertEqual(len(self.encoder.calls),calls)
        self.assertEqual(self.search(view='favorites')['items'][0]['ai_page_match']['source_revision'],self.revision)
        self.assertEqual(self.ai.search('内側',source='cover',scope={'root_ids':[self.root]})['total'],0)

    def test_strict_ids_selection_scope_and_profile_namespace(self):
        for ids in ([],[True],['bad'],self.page_ids*2,['a'*64]*17):
            with self.subTest(ids=ids),self.assertRaises(ValueError):self.ai.pages.start(self.item,ids,self.revision,self.scope)
        for scope in (None,{'root_ids':[]},{'root_ids':[self.bookroot]}):
            with self.subTest(scope=scope),self.assertRaises((ValueError,KeyError)):
                self.ai.pages.start(self.item,self.page_ids,self.revision,scope)
        with self.assertRaises(KeyError):self.ai.pages.start(self.item,['a'*64],self.revision,self.scope)
        self.build()
        other=AISearch(self.catalog,Encoder(16));self.addCleanup(other.close)
        self.assertNotEqual(other.store.path,self.ai.store.path)
        self.assertEqual(other.search('内側',source='cover',scope=self.scope)['total'],0)
        self.encoder.profile=replace(self.encoder.profile,modalities=('text',))
        self.ai.profile=self.encoder.profile
        with self.assertRaises(AIUnavailable):self.ai.pages.start(self.item,self.page_ids,self.revision,self.scope)

    def test_corrupt_cache_is_rebuilt_and_busy_query_rejected(self):
        self.build()
        with self.ai.store.connect() as db:db.execute('UPDATE ai_page_vectors SET vector=?',(b'bad',))
        self.assertEqual(self.search()['total'],0)
        calls=len(self.encoder.calls);self.build();self.assertEqual(len(self.encoder.calls)-calls,2)
        self.ai.inference.acquire()
        try:
            with self.assertRaises(AIBusy):self.search()
        finally:self.ai.inference.release()

    def test_purge_clears_all_page_vectors_only_for_inactive_root(self):
        self.build();other=AISearch(self.catalog,Encoder(16));self.addCleanup(other.close)
        other.pages.start(self.item,self.page_ids,self.revision,self.scope);other.worker.join(10)
        self.catalog.unregister_root(self.root);self.catalog.purge_inactive_root(self.root,True)
        for ai in (self.ai,other):
            with ai.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM ai_page_vectors').fetchone()[0],0)
        self.assertIsNotNone(self.catalog.get(self.ids['comic/']))

    def test_http_cancel_only_targets_the_owned_page_job(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'test',ai=self.ai))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        origin=f'http://127.0.0.1:{server.server_port}'
        entered=threading.Event();proceed=threading.Event()
        self.addCleanup(proceed.set)
        self.encoder.hook=lambda *args:(entered.set(),proceed.wait(5))
        state=self.ai.pages.start(self.item,self.page_ids,self.revision,self.scope)
        self.assertTrue(entered.wait(3))
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def cancel(job_id):
            request=urllib.request.Request(origin+'/api/library/ai/pages/cancel',json.dumps({'job_id':job_id}).encode(),
                headers={'Origin':origin,'X-Aredoko-Token':'test','Content-Type':'application/json'})
            with opener.open(request,timeout=5) as response:return json.loads(response.read())
        self.assertFalse(cancel('0'*32)['cancel_requested']);self.assertFalse(self.ai.cancel.is_set())
        self.assertTrue(cancel(state['job_id'])['cancel_requested']);self.assertTrue(self.ai.cancel.is_set())
        proceed.set();self.ai.worker.join(10)
        self.assertEqual(self.ai.status()['state'],'cancelled');self.assertEqual(self.records(),[])
        self.assertFalse(cancel(state['job_id'])['cancel_requested'])

    def test_http_auth_strict_body_and_revision_bound_build(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'test',ai=self.ai))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        origin=f'http://127.0.0.1:{server.server_port}'
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        body={'item_id':self.item,'page_ids':self.page_ids,'revision':self.revision,'scope':self.scope}
        def call(value,token='test',site=origin):
            request=urllib.request.Request(origin+'/api/library/ai/pages',json.dumps(value).encode(),
                headers={'Origin':site,'X-Aredoko-Token':token,'Content-Type':'application/json'})
            try:response=opener.open(request,timeout=5)
            except urllib.error.HTTPError as ex:response=ex
            with response:return response.code,json.loads(response.read())
        self.assertEqual(call(body,'wrong')[0],403)
        self.assertEqual(call(body,site='https://example.invalid')[0],403)
        for changed in ({**body,'path':'escape'},{k:v for k,v in body.items() if k!='scope'},{**body,'page_ids':[False]}):
            self.assertEqual(call(changed)[0],400)
        self.assertEqual(call({**body,'revision':'a'*64})[0],409)
        self.assertEqual(call(body)[0],200);self.ai.worker.join(10)
        self.assertEqual(len(self.records()),2)

    def test_rank_batch_source_check_preserves_stale_exclusion_and_no_zipinfo_on_tag_source(self):
        import zipfile
        self.build()
        folder_item=self.ids['comic/']
        self.pages.refresh(folder_item);folder_snap=self.pages.list(folder_item)
        self.ai.pages.start(folder_item,[p['page_id'] for p in folder_snap['pages']],
                            folder_snap['source_revision'],{'root_ids':[self.bookroot]})
        self.ai.worker.join(10)
        both_scope={'root_ids':[self.root,self.bookroot]}
        with patch.object(zipfile,'ZipInfo',side_effect=AssertionError('tag_source must not allocate ZipInfo')):
            res=self.ai.search('内側の青いページ',source='cover',scope=both_scope)
        self.assertEqual({r['id'] for r in res['items']},{self.item,folder_item})
        states=self.pages.states({self.item:self.revision,folder_item:folder_snap['source_revision']})
        self.assertEqual(states,{self.item:'current',folder_item:'current'})
        self.assertEqual(self.pages.states({self.item:'a'*64})[self.item],'stale')
        # Exclude the archive root pattern without rescanning: immediately omitted.
        self.catalog.set_excludes(self.root,['*.cbz'])
        self.assertEqual([r['id'] for r in self.ai.search('内側の青いページ',source='cover',scope=both_scope)['items']],
                         [folder_item])
        self.catalog.set_excludes(self.root,[])
        # Concurrent exclusion or root unregistration between candidate books in the
        # same rank() call must immediately omit the second book rather than serving
        # a cached location row from the start of the 256-book batch.
        orig_guard = self.catalog._guard
        releases = 0
        class InterleaveGuard:
            def __enter__(_self):
                orig_guard.acquire()
                return _self
            def __exit__(_self, *args):
                nonlocal releases
                orig_guard.release()
                releases += 1
                if releases == 1:
                    self.catalog.set_excludes(self.bookroot, ['comic/*'])
            def __getattr__(_self, name):
                return getattr(orig_guard, name)
        self.catalog._guard = InterleaveGuard()
        try:
            mid_res = self.ai.search('内側の青いページ', source='cover', scope=both_scope)
        finally:
            self.catalog._guard = orig_guard
        self.assertEqual([r['id'] for r in mid_res['items']], [self.item])
        self.catalog.set_excludes(self.bookroot, [])
        # Also test concurrent root unregistration mid-batch
        releases = 0
        def unregister_on_release(_self, *args):
            nonlocal releases
            orig_guard.release()
            releases += 1
            if releases == 1:
                self.catalog.unregister_root(self.bookroot)
        InterleaveGuard.__exit__ = unregister_on_release
        self.catalog._guard = InterleaveGuard()
        try:
            mid_res_unreg = self.ai.search('内側の青いページ', source='cover', scope=both_scope)
        finally:
            self.catalog._guard = orig_guard
        self.assertEqual([r['id'] for r in mid_res_unreg['items']], [self.item])
        self.catalog.add_root(str(self.books), folder_books=True)
        # Mutate the folder book on disk without rescanning: immediately omitted.
        (self.folder/'2.png').write_bytes(png(color=(1,2,3)))
        self.assertEqual([r['id'] for r in self.ai.search('内側の青いページ',source='cover',scope=both_scope)['items']],
                         [self.item])

    def test_next_gaps_calculation(self):
        # Comic has 2 pages
        gaps = self.ai.pages.next_gaps(self.item, self.revision, self.scope, max_pages=10, chunk_size=1)
        self.assertEqual(gaps['total_gap_pages'], 2)
        self.assertEqual(gaps['chunks'], [{'start': 0, 'count': 1}, {'start': 1, 'count': 1}])

        # Error checks
        with self.assertRaises(ValueError):
            self.ai.pages.next_gaps(self.item, self.revision, self.scope, max_pages=0)
        with self.assertRaises(ValueError):
            self.ai.pages.next_gaps(self.item, self.revision, self.scope, chunk_size=17)

    def test_bounded_multi_chunk_indexing_and_gap_continuation(self):
        # Index comic (2 pages) with chunk_size=1 to exercise multi-chunk publishing
        self.ai.pages.start_chunked(self.item, self.page_ids, self.revision, self.scope, chunk_size=1)
        self.ai.worker.join(10)
        self.assertFalse(self.ai.worker.is_alive())
        status = self.ai.status()
        self.assertEqual(status['state'], 'complete')
        self.assertEqual(status['chunks_completed'], 2)
        self.assertEqual(status['indexed'], 2)
        self.assertEqual(len(self.records()), 2)

        # Gaps should now be empty
        gaps_after = self.ai.pages.next_gaps(self.item, self.revision, self.scope)
        self.assertEqual(gaps_after['total_gap_pages'], 0)
        self.assertEqual(gaps_after['chunks'], [])

        # Chunked indexing with cancellation
        other = self.ids['comic/']
        self.pages.refresh(other)
        folder_snap = self.pages.list(other)
        other_rev = folder_snap['source_revision']
        other_ids = [p['page_id'] for p in folder_snap['pages']]
        other_scope = {'root_ids': [self.bookroot]}

        # Cancel on 4th encode call (during 2nd chunk of 'other')
        self.encoder.hook = lambda *args: self.ai.cancel.set() if len(self.encoder.calls) == 4 else None
        self.ai.pages.start_chunked(other, other_ids, other_rev, other_scope, chunk_size=1)
        self.ai.worker.join(10)
        self.assertEqual(self.ai.status()['state'], 'cancelled')
        # First chunk was published and retained
        with self.ai.store.connect() as db:
            folder_recs = db.execute('SELECT page FROM ai_page_vectors WHERE item_id=?', (other,)).fetchall()
        self.assertEqual(len(folder_recs), 1)
        self.assertEqual(folder_recs[0][0], 0)

        # Resume / finish remaining chunks
        self.encoder.hook = None
        self.ai.pages.start_chunked(other, other_ids, other_rev, other_scope, chunk_size=1)
        self.ai.worker.join(10)
        self.assertEqual(self.ai.status()['state'], 'complete')
        self.assertEqual(self.ai.status()['reused'], 1)
        with self.ai.store.connect() as db:
            folder_recs = db.execute('SELECT page FROM ai_page_vectors WHERE item_id=?', (other,)).fetchall()
        self.assertEqual(len(folder_recs), 2)


if __name__=='__main__':unittest.main()
