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
        before_vec=self.records()[0][4]
        calls=len(self.encoder.calls);self.build([self.page_ids[1]])
        self.assertEqual(len(self.encoder.calls),calls);self.assertEqual(self.ai.status()['reused'],1)
        self.assertEqual(self.records()[0][4],before_vec)
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
        self.encoder.hook=None  # The build-only mutation must not fire again in the query.
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
        import previews
        safe_path_calls = 0
        orig_safe_path = previews._safe_path
        def counted_safe_path(*args, **kwargs):
            nonlocal safe_path_calls
            safe_path_calls += 1
            return orig_safe_path(*args, **kwargs)
        with patch('previews._safe_path', side_effect=counted_safe_path):
            single_rows=list(self.ai._iter_rows(scope={'root_ids':[self.root]},all_candidates=True))
            single_res=self.ai.pages.rank(single_rows,[0.,1.]+[0.]*6)
        self.assertEqual(set(single_res),{self.item})
        self.assertEqual(safe_path_calls,1)  # One physical read per book inside PageVectors.rank.
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
        rank_rows=list(self.ai._iter_rows(scope=both_scope,all_candidates=True))
        self.catalog._guard = InterleaveGuard()
        try:
            # Verify the ranker's epoch cache itself. The outer streaming API
            # now rejects a changed catalog instead of returning partial ranks.
            mid_res=self.ai.pages.rank(rank_rows,[0.,1.]+[0.]*6)
        finally:
            self.catalog._guard = orig_guard
        self.assertEqual(set(mid_res),{self.item})
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
            mid_res_unreg=self.ai.pages.rank(rank_rows,[0.,1.]+[0.]*6)
        finally:
            self.catalog._guard = orig_guard
        self.assertEqual(set(mid_res_unreg),{self.item})
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

        # Mismatched revision raises ReaderChanged
        with self.assertRaises(ReaderChanged):
            self.ai.pages.next_gaps(self.item, '0' * 64, self.scope)

        # Unsupported modality returns empty gaps
        orig_modalities = self.ai.profile.modalities
        try:
            self.ai.profile = replace(self.ai.profile, modalities=('text',))
            unsupported_gaps = self.ai.pages.next_gaps(self.item, self.revision, self.scope)
            self.assertFalse(unsupported_gaps['supported'])
            self.assertEqual(unsupported_gaps['chunks'], [])
            self.assertEqual(unsupported_gaps['total_gap_pages'], 0)
        finally:
            self.ai.profile = replace(self.ai.profile, modalities=orig_modalities)

        # Error checks
        with self.assertRaises(ValueError):
            self.ai.pages.next_gaps(self.item, self.revision, self.scope, max_pages=0)
        with self.assertRaises(ValueError):
            self.ai.pages.next_gaps(self.item, self.revision, self.scope, max_pages=129)
        with self.assertRaises(ValueError):
            self.ai.pages.next_gaps(self.item, self.revision, self.scope, chunk_size=0)
        with self.assertRaises(ValueError):
            self.ai.pages.next_gaps(self.item, self.revision, self.scope, chunk_size=17)
        with self.assertRaises(ValueError):
            self.ai.pages.next_gaps(self.item, self.revision, None)

    def test_start_chunked_validation_bounds(self):
        with self.assertRaises(ValueError):
            self.ai.pages.start_chunked(self.item, [], self.revision, self.scope)
        with self.assertRaises(ValueError):
            self.ai.pages.start_chunked(self.item, [self.page_ids[0], self.page_ids[0]], self.revision, self.scope)
        with self.assertRaises(ValueError):
            self.ai.pages.start_chunked(self.item, self.page_ids, self.revision, self.scope, chunk_size=0)
        with self.assertRaises(ValueError):
            self.ai.pages.start_chunked(self.item, self.page_ids, self.revision, self.scope, chunk_size=17)
        with self.assertRaises(ValueError):
            self.ai.pages.start_chunked(self.item, self.page_ids, 'invalid_rev', self.scope)
        with self.assertRaises(ValueError):
            self.ai.pages.start_chunked(self.item, self.page_ids, self.revision, None)

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

    def test_all_pages_scope_indexes_and_controls_search_plus_origin_page_similarity(self):
        # Empty ai_page_vectors initially; indexing with book_pages='all_pages' populates pages automatically.
        all_scope = {'root_ids': [self.root], 'book_pages': 'all_pages'}
        cover_only_scope = {'root_ids': [self.root], 'book_pages': 'cover_only'}
        (self.loose / 'match.png').write_bytes(png(color=(90, 80, 70)))
        self.scan()
        match_id = self.ids['match.png']

        # Before indexing internal pages, origin_page=1 encodes on the fly if encoder is available.
        self.ai.start(scope=cover_only_scope)
        self.ai.worker.join(10)
        self.assertEqual(self.records(), [])
        sim_live = self.ai.similar(self.item, scope=all_scope, origin_page=1)
        self.assertEqual(sim_live['origin_page'], 1)
        self.assertEqual(sim_live['similarity_status'], 'ready')
        self.assertEqual(sim_live['items'][0]['id'], match_id)

        # Indexing with book_pages='all_pages' builds ai_page_vectors for already-fresh books too.
        self.ai.start(scope=all_scope)
        self.ai.worker.join(10)
        self.assertEqual(self.ai.status()['state'], 'complete')
        self.assertEqual(len(self.records()), 2)

        # Cached page vector works even with image encoding blocked.
        with patch.object(self.encoder, 'encode', side_effect=AssertionError('should reuse page vector')):
            sim_cached = self.ai.similar(self.item, scope=all_scope, origin_page=1)
        self.assertEqual(sim_cached['items'][0]['id'], match_id)

        # Search obeys book_pages scope setting ('cover_only' omits internal page matches).
        all_hits = {i['id']: i for i in self.ai.search('内側', source='cover', scope=all_scope)['items']}
        cover_hits = {i['id']: i for i in self.ai.search('内側', source='cover', scope=cover_only_scope)['items']}
        self.assertIn('ai_page_match', all_hits[self.item])
        self.assertNotIn('ai_page_match', cover_hits[self.item])

        for bad_page in (-1, 10000, '1', True):
            with self.assertRaises(ValueError):
                self.ai.similar(self.item, scope=all_scope, origin_page=bad_page)
        with self.assertRaises(ValueError):
            self.ai.similar(match_id, scope=all_scope, origin_page=0)

    def test_start_all_pages_http_and_cancellation(self):
        import zipfile
        big_cbz = self.loose / 'big_18.cbz'
        with zipfile.ZipFile(big_cbz, 'w') as zf:
            for idx in range(18):
                zf.writestr(f'{idx:03d}.png', png(color=(90, 80, 70) if idx == 17 else (10 + idx, 20, 30)))
        self.scan()
        big_id = self.ids['big_18.cbz']
        self.pages.refresh(big_id)
        big_rev = self.pages.list(big_id)['source_revision']
        big_scope = {'root_ids': [self.root]}

        server = ThreadingHTTPServer(('127.0.0.1', 0), production_handler(self.catalog, 'test', ai=self.ai))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        origin = f'http://127.0.0.1:{server.server_port}'
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def post(path, payload):
            req = urllib.request.Request(origin + path, json.dumps(payload).encode(),
                headers={'Origin': origin, 'X-Aredoko-Token': 'test', 'Content-Type': 'application/json'})
            try:
                resp = opener.open(req, timeout=5)
            except urllib.error.HTTPError as ex:
                resp = ex
            with resp:
                return resp.code, json.loads(resp.read())

        code, bad = post('/api/library/ai/pages/all', {'item_id': big_id, 'revision': big_rev, 'scope': big_scope, 'profile': 'wrong'})
        self.assertEqual(code, 400)
        code, stale = post('/api/library/ai/pages/all', {'item_id': big_id, 'revision': '0'*64, 'scope': big_scope, 'profile': self.ai.profile.key})
        self.assertEqual(code, 409)

        entered = threading.Event(); proceed = threading.Event(); self.addCleanup(proceed.set)
        calls = 0
        def cancel_hook(*_):
            nonlocal calls
            calls += 1
            if calls == 18:
                entered.set()
                proceed.wait(5)
        self.encoder.hook = cancel_hook
        code, body = post('/api/library/ai/pages/all', {'item_id': big_id, 'revision': big_rev, 'scope': big_scope, 'profile': self.ai.profile.key})
        self.assertEqual(code, 200)
        self.assertEqual((body['job'], body['page_count'], body['chunks_total']), ('book-pages-all', 18, 2))
        self.assertTrue(entered.wait(5))
        c_code, c_body = post('/api/library/ai/pages/cancel', {'job_id': body['job_id']})
        self.assertEqual(c_code, 200)
        self.assertTrue(c_body['cancel_requested'])
        proceed.set()
        self.ai.worker.join(10)
        self.assertEqual(self.ai.status()['state'], 'cancelled')
        with self.ai.store.connect() as db:
            partial_count = db.execute('SELECT count(*) FROM ai_page_vectors WHERE item_id=?', (big_id,)).fetchone()[0]
        self.assertEqual(partial_count, 16)

        self.encoder.hook = None
        code, body2 = post('/api/library/ai/pages/all', {'item_id': big_id, 'revision': big_rev, 'scope': big_scope, 'profile': self.ai.profile.key})
        self.assertEqual(code, 200)
        self.assertEqual((body2['already_indexed'], body2['total'], body2['chunks_total']), (16, 2, 1))
        self.ai.worker.join(10)
        self.assertEqual(self.ai.status()['state'], 'complete')
        with self.ai.store.connect() as db:
            full_count = db.execute('SELECT count(*) FROM ai_page_vectors WHERE item_id=?', (big_id,)).fetchone()[0]
        self.assertEqual(full_count, 18)

        code, body3 = post('/api/library/ai/pages/all', {'item_id': big_id, 'revision': big_rev, 'scope': big_scope, 'profile': self.ai.profile.key})
        self.assertEqual(code, 200)
        self.assertEqual((body3['state'], body3['total'], body3['already_indexed']), ('complete', 0, 18))

    def test_video_frame_origin_ms_similarity_and_cross_media_kind_filter(self):
        from ai_search import revision
        match_img = self.loose / 'near_frame.png'
        match_img.write_bytes(png(color=(90, 80, 70)))
        vid_origin = self.loose / 'origin_clip.mp4'
        vid_cand = self.loose / 'cand_clip.mp4'
        vid_origin.write_bytes(b'ftypmp42' + b'\0' * 128)
        vid_cand.write_bytes(b'ftypmp42' + b'\1' * 128)
        self.scan()
        img_id = self.ids['near_frame.png']
        vo_id = self.ids['origin_clip.mp4']
        vc_id = self.ids['cand_clip.mp4']

        all_scope = {'root_ids': [self.root], 'book_pages': 'all_pages'}
        # Index images + book pages on axis 1 where appropriate
        self.ai.start(scope=all_scope)
        self.ai.worker.join(10)
        # Ensure video candidate has representative frame matching axis 1
        vc_row = self.catalog.get(vc_id)
        vo_row = self.catalog.get(vo_id)
        axis1 = [float(i == 1) for i in range(self.ai.profile.dimension)]
        axis0 = [float(i == 0) for i in range(self.ai.profile.dimension)]
        self.ai.store.put(vc_id, revision(vc_row), {'text': axis0, 'cover': axis1}, video_frames=[(3000, axis1)])
        self.ai.store.put(vo_id, revision(vo_row), {'text': axis0, 'cover': axis0}, video_frames=[(0, axis0)])
        # Ensure book page 1 matches axis 1 (comic page 1 color != (90,80,70), so set page 1 vector directly)
        with self.ai.store.connect() as db:
            from array import array
            blob = array('f', axis1).tobytes()
            db.execute('INSERT OR REPLACE INTO ai_page_vectors VALUES(?,?,?,?,?,?)',
                       (self.item, self.revision, self.page_ids[1], 1, blob, 'book-page-image:v1'))

        server = ThreadingHTTPServer(('127.0.0.1', 0), production_handler(self.catalog, 'test', ai=self.ai))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        origin = f'http://127.0.0.1:{server.server_port}'
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def post(path, payload):
            req = urllib.request.Request(origin + path, json.dumps(payload).encode(),
                headers={'Origin': origin, 'X-Aredoko-Token': 'test', 'Content-Type': 'application/json'})
            with opener.open(req, timeout=5) as resp:
                return json.loads(resp.read())

        req_id = post('/api/library/ai/searches/prepare', {})['request_id']
        seen_calls = []
        def fake_frame(item_id, at_ms, rev):
            seen_calls.append(at_ms)
            if at_ms == 1500:
                raise PreviewUnavailable('eof')
            return png(color=(90, 80, 70)), 'image/png'

        with patch.object(self.ai.previews, 'video_manifest', return_value={'revision': 'a' * 64}), \
             patch.object(self.ai.previews, 'video_frame', side_effect=fake_frame):
            mixed = post('/api/library/ai/similar', {'item_id': vo_id, 'kind': '', 'view': 'all', 'page': 0, 'limit': 60, 'scope': all_scope, 'origin_ms': 1500, 'request_id': req_id})
            self.assertEqual(seen_calls, [1500, 1250])
            self.assertEqual(mixed['origin_ms'], 1500)
            self.assertEqual(mixed['similarity_status'], 'ready')
            mixed_kinds = {it['kind']: it for it in mixed['items']}
            self.assertEqual(set(mixed_kinds), {'image', 'book', 'video'})
            self.assertIn('ai_page_match', mixed_kinds['book'])
            self.assertEqual(mixed_kinds['video']['video_match_ms'], 3000)

            req_img = post('/api/library/ai/searches/prepare', {})['request_id']
            only_img = post('/api/library/ai/similar', {'item_id': vo_id, 'kind': 'image', 'view': 'all', 'page': 0, 'limit': 60, 'scope': all_scope, 'origin_ms': 1250, 'request_id': req_img})
            self.assertEqual({it['kind'] for it in only_img['items']}, {'image'})
            self.assertIn(img_id, [it['id'] for it in only_img['items']])

            req_vid = post('/api/library/ai/searches/prepare', {})['request_id']
            only_vid = post('/api/library/ai/similar', {'item_id': vo_id, 'kind': 'video', 'view': 'all', 'page': 0, 'limit': 60, 'scope': all_scope, 'origin_ms': 1250, 'request_id': req_vid})
            self.assertEqual([it['id'] for it in only_vid['items']], [vc_id])

        # Validation guards
        with self.assertRaises(ValueError):
            self.ai.similar(vo_id, scope=all_scope, origin_ms=-1)
        with self.assertRaises(ValueError):
            self.ai.similar(self.item, scope=all_scope, origin_page=0, origin_ms=0)
        with self.assertRaises(ValueError):
            self.ai.similar(img_id, scope=all_scope, origin_ms=100)

    def test_all_pages_skips_none_encoded_image_without_type_error(self):
        all_scope = {'root_ids': [self.root], 'book_pages': 'all_pages'}
        orig_encode = self.encoder.encode
        def encode_skip_first_page(operation, value):
            if operation == 'image' and value == self.first:
                return None
            return orig_encode(operation, value)
        with patch.object(self.encoder, 'encode', side_effect=encode_skip_first_page):
            self.ai.start(scope=all_scope)
            self.ai.worker.join(10)
        status = self.ai.status()
        self.assertEqual(status['state'], 'complete', status)
        recs = self.records()
        self.assertEqual([r[3] for r in recs], [1])

    def test_all_pages_skips_unavailable_page_during_library_build(self):
        all_scope = {'root_ids': [self.root], 'book_pages': 'all_pages'}
        orig_input = self.ai.pages.index.input
        def input_fail_first_page(item_id, page_id, revision):
            if item_id == self.item and page_id == self.page_ids[0]:
                raise PreviewUnavailable('oversized test page')
            return orig_input(item_id, page_id, revision)
        with patch.object(self.ai.pages.index, 'input', side_effect=input_fail_first_page):
            self.ai.start(scope=all_scope)
            self.ai.worker.join(10)
        status = self.ai.status()
        self.assertEqual(status['state'], 'complete', status)
        recs = self.records()
        self.assertEqual([r[3] for r in recs], [1])

    def test_explicit_page_start_skips_none_encoded_image(self):
        orig_encode = self.encoder.encode
        def encode_skip_first_page(operation, value):
            if operation == 'image' and value == self.first:
                return None
            return orig_encode(operation, value)
        with patch.object(self.encoder, 'encode', side_effect=encode_skip_first_page):
            self.build()
        status = self.ai.status()
        self.assertEqual(status['skipped'], 1, status)
        self.assertEqual(status['indexed'], 1, status)
        self.assertEqual([r[3] for r in self.records()], [1])

    def test_ai_build_exception_writes_traceback_to_stderr(self):
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf), \
             patch.object(self.encoder, 'encode', side_effect=RuntimeError('boom')):
            self.ai.start(scope=self.scope)
            self.ai.worker.join(10)
        status = self.ai.status()
        self.assertEqual(status['state'], 'failed', status)
        self.assertIn('RuntimeError: boom', buf.getvalue())

    def test_bulk_page_inputs_opens_zip_once_and_supports_folder_and_skip(self):
        import zipfile
        big_cbz = self.loose / 'bulk_8.cbz'
        with zipfile.ZipFile(big_cbz, 'w') as zf:
            for idx in range(8):
                zf.writestr(f'{idx:03d}.png', png(color=(90, 80, 70) if idx == 5 else (10 + idx, 20, 30)))
        self.scan()
        bulk_id = self.ids['bulk_8.cbz']
        self.pages.refresh(bulk_id)
        snap = self.pages.list(bulk_id)
        bulk_rev = snap['source_revision']
        bulk_pids = [p['page_id'] for p in snap['pages']]

        real_zip = zipfile.ZipFile
        open_count = 0
        def counted_zip(*args, **kwargs):
            nonlocal open_count
            open_count += 1
            return real_zip(*args, **kwargs)
        with patch('previews.zipfile.ZipFile', side_effect=counted_zip):
            got = self.pages.inputs(bulk_id, bulk_pids, bulk_rev)
        self.assertEqual(open_count, 1)
        self.assertEqual(len(got), 8)
        self.assertEqual(got[bulk_pids[5]]['data'], png(color=(90, 80, 70)))

        # Oversized page skipped when skip_unavailable=True
        over_cbz = self.loose / 'mixed_over.cbz'
        small_img = png(width=16, height=16, color=(10, 20, 30))
        large_img = png(color=(90, 80, 70))
        with zipfile.ZipFile(over_cbz, 'w') as zf:
            zf.writestr('000.png', large_img)
            zf.writestr('001.png', small_img)
        self.scan()
        over_id = self.ids['mixed_over.cbz']
        self.pages.refresh(over_id)
        osnap = self.pages.list(over_id)
        opids = [p['page_id'] for p in osnap['pages']]
        cutoff = (len(small_img) + len(large_img)) // 2
        with patch('previews.MAX_IMAGE_BYTES', cutoff):
            ogot = self.pages.inputs(over_id, opids, osnap['source_revision'], skip_unavailable=True)
        self.assertIsNone(ogot[opids[0]])
        self.assertEqual(ogot[opids[1]]['data'], small_img)

        folder_id = self.ids['comic/']
        self.pages.refresh(folder_id)
        fsnap = self.pages.list(folder_id)
        fpids = [p['page_id'] for p in fsnap['pages']]
        fgot = self.pages.inputs(folder_id, fpids, fsnap['source_revision'])
        self.assertEqual(set(fgot), set(fpids))
        self.assertIsNotNone(fgot[fpids[1]])

        # Mutate archive -> ReaderChanged
        self.write_archive([('1.png', png(color=(1, 2, 3)))])
        with self.assertRaises(ReaderChanged):
            self.pages.inputs(self.item, self.page_ids, self.revision)

    def test_batch_capable_encoder_indexes_normal_turbo_video_and_skips_none(self):
        import zipfile
        class BatchEncoder:
            available = True
            device = 'cuda-fake'
            def __init__(self):
                self.profile = replace(DEFAULT_PROFILE, dimension=8)
                self.batch_calls = []
                self.single_calls = []
            def encode(self, operation, value):
                self.single_calls.append(operation)
                return [float(i == (1 if operation == 'query' else 0)) for i in range(self.profile.dimension)]
            def encode_batch(self, operation, values, *, mode='normal'):
                self.batch_calls.append((operation, len(values), mode))
                out = []
                for v in values:
                    if operation == 'image' and v == self.skip_target:
                        out.append(None)
                    elif operation == 'image' and v == png(color=(90, 80, 70)):
                        out.append([float(i == 1) for i in range(self.profile.dimension)])
                    else:
                        out.append([float(i == 0) for i in range(self.profile.dimension)])
                return out
            def close(self):
                pass

        enc = BatchEncoder()
        enc.skip_target = self.first
        ai = AISearch(self.catalog, enc)
        self.addCleanup(ai.close)
        ai.configure(index_mode='turbo')
        self.assertEqual(ai.status()['index_mode'], 'turbo')

        vid = self.loose / 'vid.mp4'
        vid.write_bytes(b'ftypmp42' + b'\0' * 128)
        extra_img = self.loose / 'hero.png'
        extra_img.write_bytes(png(color=(90, 80, 70)))
        self.scan()
        vid_id = self.ids['vid.mp4']

        fake_frames = [(0, self.second), (2500, png(color=(90, 80, 70)))]
        all_scope = {'root_ids': [self.root], 'book_pages': 'all_pages'}
        with patch.object(ai.previews, 'video_representative_frames', return_value=fake_frames):
            ai.start(scope=all_scope)
            ai.worker.join(10)
        st = ai.status()
        self.assertEqual(st['state'], 'complete', st)
        self.assertTrue(any(op == 'document' and m == 'turbo' for op, _, m in enc.batch_calls))
        self.assertTrue(any(op == 'image' and m == 'turbo' for op, _, m in enc.batch_calls))
        # Page 0 of comic.cbz matched skip_target -> skipped; page 1 persisted; video persisted 2 frames
        with ai.store.connect() as db:
            cbz_pages = [r[0] for r in db.execute('SELECT page FROM ai_page_vectors WHERE item_id=? ORDER BY page', (self.item,))]
            vframes = [r[0] for r in db.execute('SELECT at_ms FROM ai_video_frames WHERE item_id=? ORDER BY at_ms', (vid_id,))]
        self.assertEqual(cbz_pages, [1])
        self.assertEqual(vframes, [0, 2500])


if __name__=='__main__':unittest.main()
