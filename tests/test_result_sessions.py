"""Fixed generated results, disk ownership and API contracts. No model/GPU/UI."""
from dataclasses import replace
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from production import ProductionCatalog
from production_server import production_handler, DisabledAI
from result_sessions import ResultSessions, ResultUnavailable, ResultCapacity, IndexStamp, IDLE_SECONDS
from ai_search import AISearch, revision
from ai_profiles import DEFAULT_PROFILE
from PIL import Image


class Encoder:
    profile = replace(DEFAULT_PROFILE, dimension=8)
    available = True
    def __init__(self): self.calls = 0
    def encode(self, operation, text): self.calls += 1; return [1.] + [0.] * 7
    def close(self): pass


class ResultSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name); self.media = self.base / 'media'; self.media.mkdir()
        output = io.BytesIO(); Image.new('RGB', (2, 2), 'red').save(output, format='PNG'); png = output.getvalue()
        for index in range(125): (self.media / f'{index:03}.png').write_bytes(png)
        self.catalog = ProductionCatalog(self.base / 'library.sqlite'); self.addCleanup(self.catalog.close)
        self.root = self.catalog.add_root(str(self.media)); self.catalog.index.scan(self.root); self.catalog.sync_index()
        self.items = []
        for page in range(3): self.items.extend(self.catalog.search(page=page)['items'])
        self.sid = 'a' * 32
        self.pages = []
        def provider(conditions, consume, cancelled):
            def page(number):
                self.pages.append(number)
                return self.catalog.search(page=number, **conditions)
            return consume(page)
        self.owner = ResultSessions(self.catalog, provider, parent=self.base)
        self.addCleanup(self.owner.close)

    def create(self, **conditions): return self.owner.create(self.sid, conditions)

    def test_60_61_reverse_and_120_121_boundaries_without_requery(self):
        self.create(); calls = list(self.pages)
        for index, direction, expected in [(59, 1, 60), (60, -1, 59), (119, 1, 120)]:
            result = self.owner.neighbor(self.sid, self.items[index]['id'], direction)
            self.assertEqual(result['neighbor']['item']['id'], self.items[expected]['id'])
            self.assertEqual(result['neighbor']['ordinal'], expected)
        self.assertIsNone(self.owner.neighbor(self.sid, self.items[-1]['id'], 1)['neighbor'])
        self.assertEqual(self.pages, calls)
        self.assertEqual([i['id'] for i in self.owner.read(self.sid, 60, 60)['items']], [i['id'] for i in self.items[60:120]])

    def test_literal_cursor_preserves_paged_order_evidence_partial_and_scope(self):
        self.catalog.update([self.items[2]['id']],{'tags':['星空'],'favorite':True})
        self.catalog.update([self.items[3]['id']],{'tags':['宇宙']})
        self.catalog.terms.upsert({'term':'星空','related':['宇宙']})
        self.catalog.record_view(self.items[4]['id']);self.catalog.record_view(self.items[2]['id'])
        shelf=self.catalog.change_shelf('create',name='生成棚')['id']
        self.catalog.change_shelf('assign',entity='item',object_ids=[self.items[2]['id']],shelf_ids=[shelf])
        for conditions in ({},{'query':'星空'},{'query':'星空 無一致'},{'query':'無一致'},
                {'query':'宇宙'},{'view':'history'},{'view':'favorites'},{'kind':'video'},
                {'root_ids':[self.root]},{'shelf_ids':[shelf]}):
            with self.subTest(conditions=conditions):
                reference=[];number=0
                while True:
                    page=self.catalog.search(page=number,limit=17,**conditions);reference.append(page)
                    if (number+1)*17>=page['total']:break
                    number+=1
                def consume(render):return [render(i) for i in range(len(reference))]
                self.assertEqual(self.catalog.search(limit=17,**conditions,result_sink=consume),reference)

    def test_literal_cursor_counts_once_and_cancellation_closes_cursor(self):
        from contextlib import contextmanager
        original=self.catalog.connect;sql=[];pages=[]
        @contextmanager
        def traced():
            with original() as db:
                db.set_trace_callback(sql.append)
                yield db
        def consume(render):
            for number in range(3):pages.append(render(number))
        with patch.object(self.catalog,'connect',side_effect=traced):
            self.catalog.search(limit=60,result_sink=consume)
        self.assertEqual([len(p['items']) for p in pages],[60,60,5])
        self.assertEqual(sum(q.startswith('SELECT count(*)') for q in sql),1)
        self.assertEqual(sum(' OFFSET ' in q for q in sql),0)
        cancelled=[False]
        def cancel(render):
            render(0);cancelled[0]=True;render(1)
        with self.assertRaises(InterruptedError):self.catalog.search(limit=60,result_sink=cancel,cancelled=lambda:cancelled[0])
        self.catalog.update([self.items[0]['id']],{'favorite':True})
        self.assertTrue(self.catalog.get(self.items[0]['id'])['favorite'])
        with self.assertRaises(ValueError):self.catalog.search(page=1,result_sink=lambda render:render(0))
        with self.assertRaises(ValueError):self.catalog.search(result_sink=lambda render:render(1))

    def test_page_validation_shares_one_connection_but_checks_every_physical_source(self):
        import result_sessions
        self.create();session=self.owner.sessions[self.sid];items=self.items[:60]
        reference=[session._current(item,capture=True) for item in items]
        with patch.object(self.catalog,'connect',wraps=self.catalog.connect) as connection,patch('result_sessions._safe_path',wraps=result_sessions._safe_path) as physical:
            actual=list(session._currents(items,capture=True))
        self.assertEqual(actual,reference);self.assertEqual(connection.call_count,1);self.assertEqual(physical.call_count,len(items))

    def test_creation_skips_per_item_source_checks_and_reads_validate_unshared(self):
        import result_sessions
        original=result_sessions._safe_path;calls=[]
        def observed(*args,**kwargs):
            calls.append((kwargs.get('root_cache'),args[1]))
            return original(*args,**kwargs)
        with patch('result_sessions._safe_path',side_effect=observed):self.create()
        self.assertEqual(len(calls),0)
        with patch('result_sessions._safe_path',side_effect=observed):
            first=self.owner.read(self.sid,0,1)
        self.assertEqual(len(calls),1);self.assertIsNone(calls[0][0])
        self.assertNotIn('_source_identity',first['items'][0])
        stored=json.loads(self.owner.sessions[self.sid].db.execute('SELECT payload FROM results WHERE ordinal=0').fetchone()[0])
        self.assertIn('_source_identity',stored)
        calls.clear()
        with patch('result_sessions._safe_path',side_effect=observed):
            page=self.owner.read(self.sid,60,60)
        self.assertEqual(len(calls),60);self.assertEqual(len(page['items']),60)
        self.assertTrue(all(cache is None for cache,_ in calls))

    def test_metadata_write_during_page_validation_never_returns_mixed_rows(self):
        import result_sessions
        self.create();original=result_sessions._safe_path;changed=[False]
        def mutate(*args,**kwargs):
            if not changed[0]:
                changed[0]=True;self.catalog.update([self.items[-1]['id']],{'favorite':True})
            return original(*args,**kwargs)
        with patch('result_sessions._safe_path',side_effect=mutate),self.assertRaises(ResultUnavailable):self.owner.read(self.sid,0,60)
        self.assertTrue(changed[0])

    def test_unregister_during_page_validation_never_leaks_stale_scope(self):
        import result_sessions
        self.create();original=result_sessions._safe_path;changed=[False]
        def mutate(*args,**kwargs):
            if not changed[0]:changed[0]=True;self.catalog.unregister_root(self.root)
            return original(*args,**kwargs)
        with patch('result_sessions._safe_path',side_effect=mutate),self.assertRaises(ResultUnavailable):self.owner.read(self.sid,0,60)

    def test_owner_close_waits_for_cancelled_builder_to_release_workspace(self):
        old=self.owner.provider
        entered=threading.Event();release=threading.Event();errors=[];closed=[]
        def held(conditions,consume,cancelled):
            entered.set();release.wait(3)
            return old(conditions,consume,cancelled)
        self.owner.provider=held
        def build():
            try:self.create()
            except Exception as error:errors.append(error)
        worker=threading.Thread(target=build);worker.start();self.assertTrue(entered.wait(2))
        closer=threading.Thread(target=lambda:closed.append(self.owner.close(timeout=3)));closer.start()
        self.assertTrue(self.owner.stopped.wait(2));release.set();worker.join(4);closer.join(4)
        self.assertFalse(worker.is_alive());self.assertFalse(closer.is_alive());self.assertTrue(errors);self.assertEqual(closed,[True])
        self.assertFalse(list(self.base.glob('aredoko-results-*')))

    def test_history_order_is_frozen_after_new_view_records(self):
        self.catalog.record_view(self.items[1]['id']); self.catalog.record_view(self.items[0]['id'])
        self.create(view='history')
        self.catalog.record_view(self.items[1]['id'])
        self.assertEqual([x['id'] for x in self.owner.read(self.sid)['items']], [self.items[0]['id'], self.items[1]['id']])
        self.assertEqual(self.owner.neighbor(self.sid, self.items[0]['id'], 1)['neighbor']['item']['id'], self.items[1]['id'])

    def test_metadata_edit_elsewhere_invalidates_instead_of_mixing_results(self):
        self.create(); self.catalog.update([self.items[-1]['id']], {'favorite': True})
        with self.assertRaises(ResultUnavailable): self.owner.read(self.sid, 0, 1)

    def test_root_exclusion_and_unregistration_never_broaden_scope(self):
        self.create(root_ids=[self.root])
        self.catalog.set_excludes(self.root, ['000.png'])
        with self.assertRaises(ResultUnavailable): self.owner.neighbor(self.sid, self.items[0]['id'], 1)
        self.owner.cancel(self.sid); self.sid = 'b' * 32
        self.create(root_ids=[self.root]); self.catalog.unregister_root(self.root)
        with self.assertRaises(ResultUnavailable): self.owner.read(self.sid)

    def test_literal_exclusions_apply_before_rescan(self):
        self.catalog.set_excludes(self.root, ['000.png'])
        self.assertNotIn('000.png', [item['title'] for item in self.catalog.search(limit=120)['items']])

    def test_replaced_source_with_preserved_metadata_is_rejected(self):
        import os
        self.create()
        self.owner.read(self.sid, 60, 1)  # Pin observed source identity
        target = self.media / self.items[60]['relative_path']; before = target.stat()
        replacement = self.media / 'replacement.tmp'; replacement.write_bytes(target.read_bytes())
        os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns)); os.replace(replacement, target)
        with self.assertRaises(ResultUnavailable): self.owner.neighbor(self.sid, self.items[59]['id'], 1)

    def test_initially_disconnected_item_does_not_break_metadata_listing(self):
        target = self.items[60]
        (self.media / target['relative_path']).unlink()
        self.create()
        result = self.owner.read(self.sid, 60, 1)
        self.assertEqual(result['total'], 125)
        self.assertEqual(result['items'][0]['id'], target['id'])
        self.assertEqual(result['items'][0]['availability'], 'unavailable')
        self.assertEqual(result['items'][0]['source_state'], 'unavailable')
        self.assertNotIn('_source_identity', result['items'][0])
        with self.assertRaises(ResultUnavailable): self.owner.neighbor(self.sid, self.items[59]['id'], 1)

    def test_reconnected_item_requires_refresh_of_unavailable_snapshot(self):
        import os
        path = self.media / self.items[60]['relative_path']; data = path.read_bytes(); before = path.stat()
        path.unlink(); self.create()
        self.assertEqual(self.owner.read(self.sid, 60, 1)['items'][0]['availability'], 'unavailable')
        path.write_bytes(data)
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaises(ResultUnavailable): self.owner.read(self.sid, 60, 1)

    def test_successful_rescan_invalidates_old_results_and_hides_missing(self):
        self.create();target=self.items[60]
        (self.media/target['relative_path']).unlink()
        self.catalog.start_scan(self.root);self.catalog._worker.join(5)
        with self.assertRaises(ResultUnavailable):self.owner.read(self.sid,60,1)
        self.owner.cancel(self.sid);self.sid='b'*32
        self.create()
        self.assertEqual(self.owner.read(self.sid,0,1)['total'],124)
        self.assertFalse(any(row['id']==target['id'] for row in self.catalog.search(page=1)['items']))

    def test_physical_source_change_is_refresh_error_not_end_of_sequence(self):
        self.create(); (self.media / self.items[60]['relative_path']).write_bytes(b'changed')
        with self.assertRaises(ResultUnavailable): self.owner.neighbor(self.sid, self.items[59]['id'], 1)

    def test_mixed_results_navigate_only_images_in_original_order(self):
        (self.media / 'video.mp4').write_bytes(b'generated metadata fixture')
        self.catalog.index.scan(self.root); self.catalog.sync_index()
        self.create()
        result = self.owner.neighbor(self.sid, self.items[-1]['id'], 1)
        self.assertIsNone(result['neighbor'])
        video = self.catalog.search(kind='video')['items'][0]
        self.assertEqual(self.owner.neighbor(self.sid, video['id'], -1)['neighbor']['item']['id'], self.items[-1]['id'])

    def test_query_filter_and_conditions_are_immutable(self):
        conditions = {'query': '06', 'root_ids': [self.root]}
        self.owner.create(self.sid, conditions); conditions['query'] = 'changed'; conditions['root_ids'].clear()
        result = self.owner.read(self.sid)
        self.assertEqual(result['conditions']['query'], '06'); self.assertEqual(result['total'], sum('06' in i['title'] for i in self.items))
        self.assertTrue(all('06' in i['title'] for i in result['items']))

    def test_expiry_retains_conditions_and_removes_owned_directory(self):
        self.create(query='001'); session = self.owner.sessions[self.sid]; directory = session.path.parent
        session.last_used -= IDLE_SECONDS + 1
        with self.assertRaises(ResultUnavailable) as error: self.owner.read(self.sid)
        self.assertTrue(error.exception.expired); self.assertEqual(error.exception.conditions, {'query': '001'})
        self.assertFalse(directory.exists())

    def test_status_refreshes_last_used_and_prevents_idle_expiry(self):
        self.create(query='001'); session = self.owner.sessions[self.sid]
        session.last_used -= IDLE_SECONDS - 30
        status = self.owner.status(self.sid)
        self.assertEqual(status['state'], 'ready')
        self.owner._expire()
        self.assertIn(self.sid, self.owner.sessions)
        self.assertEqual(self.owner.read(self.sid)['total'], sum('001' in i['title'] for i in self.items))

    def test_capacity_never_publishes_a_truncated_result(self):
        self.owner.max_bytes = 65536
        with self.catalog.connect() as db: db.execute('UPDATE items SET title=?', ('x' * 2000,))
        with self.assertRaises(ResultCapacity): self.create()
        self.assertNotIn(self.sid, self.owner.sessions)
        self.assertFalse(list(self.base.glob('aredoko-results-*')))

    def test_audio_similarity_reserves_ranking_workspace_before_starting_provider(self):
        self.owner.max_bytes=128*1024*1024
        with self.assertRaises(ResultCapacity):self.owner.create(self.sid,{'mode':'audio-similar','item_id':1})
        self.assertNotIn(self.sid,self.owner.sessions)

    def test_closed_marker_expires_without_another_close_request(self):
        self.owner.cancel(self.sid)
        stamp, conditions = self.owner.retired[self.sid]
        self.owner.retired[self.sid] = (stamp - IDLE_SECONDS - 1, conditions)
        self.assertEqual(self.create()['total'], 125)

    def test_three_sessions_limit_close_and_unknown_neighbor(self):
        self.create()
        for key in ('b' * 32, 'c' * 32): self.owner.create(key, {})
        with self.assertRaises(ResultCapacity): self.owner.create('d' * 32, {})
        with self.assertRaises(ResultUnavailable): self.owner.neighbor(self.sid, 987654, 1)
        self.owner.cancel(self.sid); self.owner.create('d' * 32, {})
        for invalid in (True, 0, 121):
            with self.assertRaises(ValueError): self.owner.read('d' * 32, 0, invalid)

    def test_close_during_build_cannot_publish_late_results(self):
        entered = threading.Event(); release = threading.Event(); errors = []
        old = self.owner.provider
        def blocked(*args): entered.set(); release.wait(3); return old(*args)
        self.owner.provider = blocked
        def create():
            try: self.create()
            except Exception as error: errors.append(error)
        thread = threading.Thread(target=create); thread.start(); self.assertTrue(entered.wait(2))
        self.owner.cancel(self.sid); release.set(); thread.join(5)
        self.assertFalse(thread.is_alive()); self.assertTrue(errors)
        self.assertFalse(list(self.base.glob('aredoko-results-*')))

    def test_sqlite_storage_keeps_only_bounded_page_lists_in_memory(self):
        self.create(); session = self.owner.sessions[self.sid]
        self.assertTrue(session.path.exists()); self.assertEqual(session.total, 125)
        self.assertNotIn('items', session.metadata)
        self.assertEqual(self.owner.read(self.sid, 120, 120)['total'], 125)

    def test_create_keeps_provider_order_with_zero_upfront_safe_path_calls(self):
        with patch('result_sessions._safe_path', side_effect=AssertionError('must not scan all sources on create')):
            self.create()
        session=self.owner.sessions[self.sid]
        self.assertEqual([row[0] for row in session.db.execute('SELECT item_id FROM results ORDER BY ordinal')],[i['id'] for i in self.items])
        self.assertEqual(len(self.owner.read(self.sid,0,60)['items']),60)

    def test_close_during_provider_build_joins_before_workspace_cleanup(self):
        old=self.owner.provider;entered=threading.Event();release=threading.Event();errors=[]
        def held(conditions,consume,cancelled):
            def delayed(page):
                def read_page(number):
                    if number==1:entered.set();release.wait(4)
                    return page(number)
                return consume(read_page)
            return old(conditions,delayed,cancelled)
        self.owner.provider=held
        def build():
            try:self.create()
            except Exception as error:errors.append(error)
        thread=threading.Thread(target=build);thread.start();self.assertTrue(entered.wait(3))
        try:self.assertFalse(self.owner.close(timeout=.02))
        finally:release.set();thread.join(6)
        self.assertFalse(thread.is_alive());self.assertTrue(errors)
        self.assertFalse(list(self.base.glob('aredoko-results-*')))

    def test_provider_failure_mid_build_never_publishes_partial_results(self):
        old=self.owner.provider
        def failing(conditions,consume,cancelled):
            def broken(page):
                def read_page(number):
                    if number==1:raise ResultUnavailable('Generated provider failure')
                    return page(number)
                return consume(read_page)
            return old(conditions,broken,cancelled)
        self.owner.provider=failing
        with self.assertRaises(ResultUnavailable):self.create()
        self.assertNotIn(self.sid,self.owner.sessions)
        self.assertFalse(list(self.base.glob('aredoko-results-*')))

    def test_building_status_reports_committed_count_without_exposing_partial_ranges(self):
        old=self.owner.provider;entered=threading.Event();release=threading.Event();errors=[]
        def provider(conditions,consume,cancelled):
            def observed(page):
                def delayed(number):
                    if number==1:entered.set();release.wait(4)
                    return page(number)
                return consume(delayed)
            return old(conditions,observed,cancelled)
        self.owner.provider=provider
        def build():
            try:self.create()
            except Exception as error:errors.append(error)
        thread=threading.Thread(target=build);thread.start()
        try:
            self.assertTrue(entered.wait(3))
            status=self.owner.status(self.sid)
            self.assertEqual((status['state'],status['processed'],status['total']),('building',60,125))
            self.assertNotIn('items',status)
            with self.assertRaises(ResultUnavailable):self.owner.read(self.sid,0,1)
            with self.assertRaises(ResultUnavailable):self.owner.neighbor(self.sid,self.items[0]['id'],1)
        finally:release.set();thread.join(5)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        status=self.owner.status(self.sid)
        self.assertEqual((status['state'],status['processed'],status['total']),('ready',125,125))

    def test_building_status_validates_generation_and_can_be_cancelled(self):
        old=self.owner.provider;entered=threading.Event();release=threading.Event();errors=[]
        def provider(*args):entered.set();release.wait(4);return old(*args)
        self.owner.provider=provider
        def build():
            try:self.create()
            except Exception as error:errors.append(error)
        thread=threading.Thread(target=build);thread.start()
        try:
            self.assertTrue(entered.wait(3))
            status=self.owner.status(self.sid)
            self.assertEqual((status['processed'],status['total']),(0,None))
            self.catalog.unregister_root(self.root)
            with self.assertRaises(ResultUnavailable):self.owner.status(self.sid)
            self.owner.cancel(self.sid)
            with self.assertRaises(ResultUnavailable):self.owner.status(self.sid)
        finally:release.set();thread.join(5)
        self.assertFalse(thread.is_alive());self.assertTrue(errors)
        self.assertFalse(list(self.base.glob('aredoko-results-*')))

    def test_ai_one_encoding_one_rank_and_index_change_detection(self):
        encoder = Encoder(); ai = AISearch(self.catalog, encoder); self.addCleanup(ai.close)
        for item in self.items: ai.store.put(item['id'], revision(item), {'text': [1.] + [0.] * 7})
        self.owner.close()
        self.owner = ResultSessions(self.catalog,
            lambda conditions, consume, cancelled: ai.search('generated', source='text', limit=60, result_sink=consume, cancelled=cancelled),
            index_stamp=IndexStamp(ai), parent=self.base)
        self.addCleanup(self.owner.close)
        self.create(); self.assertEqual(encoder.calls, 1)
        with patch.object(ai.encoder, 'encode', side_effect=AssertionError('reranked')):
            self.assertEqual(self.owner.read(self.sid, 120, 120)['items'][0]['id'], self.items[120]['id'])
            self.owner.neighbor(self.sid, self.items[59]['id'], 1)
        self.assertEqual(encoder.calls, 1)
        item = self.items[-1]; ai.store.put(item['id'], revision(item), {'text': [0., 1.] + [0.] * 6})
        with self.assertRaises(ResultUnavailable): self.owner.read(self.sid, 0, 1)

    def test_existing_page_api_remains_compatible_with_optional_ai_consumer(self):
        encoder = Encoder(); ai = AISearch(self.catalog, encoder); self.addCleanup(ai.close)
        for item in self.items: ai.store.put(item['id'], revision(item), {'cover': [1.] + [0.] * 7})
        legacy = ai.similar(self.items[0]['id'], page=1)
        pages = []
        def sink(page):
            pages.extend([page(0), page(1), page(2)]); return 'consumed'
        self.assertEqual(ai.similar(self.items[0]['id'], result_sink=sink), 'consumed')
        self.assertEqual(pages[1], legacy)
        self.assertTrue(all(i['id'] != self.items[0]['id'] for p in pages for i in p['items']))

    def test_all_result_provider_modes_share_the_same_api_contract(self):
        encoder = Encoder(); ai = AISearch(self.catalog, encoder); self.addCleanup(ai.close)
        for item in self.items:
            ai.store.put(item['id'], revision(item), {'text': [1.] + [0.] * 7, 'cover': [1.] + [0.] * 7})
        handler = production_handler(self.catalog, 'fixture', ai=ai)
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        def post(action, body):
            with urllib.request.urlopen(urllib.request.Request(origin + '/api/library/results/' + action,
                data=json.dumps(body).encode(), headers={'Origin': origin, 'X-Aredoko-Token': 'fixture'}), timeout=5) as response:
                return json.load(response)
        modes = [({'mode': 'literal'}, 125), ({'mode': 'history'}, 0),
                 ({'mode': 'semantic', 'query': 'generated', 'source': 'text'}, 125),
                 ({'mode': 'similar', 'item_id': self.items[0]['id']}, 124),
                 ({'mode': 'page-text', 'query': 'generated'}, 0),
                 ({'mode': 'pending-proposals', 'query': 'generated'}, 0),
                 ({'mode': 'pending-proposals-semantic', 'query': 'generated'}, 0)]
        try:
            for number, (conditions, total) in enumerate(modes, 1):
                with self.subTest(mode=conditions['mode']):
                    sid = f'{number:032x}'
                    self.assertEqual(post('create', {'session_id': sid, 'conditions': conditions})['total'], total)
                    result = post('range', {'session_id': sid, 'offset': 0, 'limit': 120})
                    self.assertEqual(result['total'], total); self.assertEqual(len(result['items']), min(total, 120))
                    post('close', {'session_id': sid})
            self.assertEqual(encoder.calls, 1)  # no query model for empty proposals or similarity
        finally:
            server.shutdown(); server.server_close(); thread.join(5)
            handler.results.close(); handler.animations.close(); handler.setup_jobs.close()

    def test_http_create_range_neighbor_status_auth_and_expired_conditions(self):
        handler = production_handler(self.catalog, 'fixture', ai=DisabledAI())
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        def post(action, body, token='fixture'):
            return urllib.request.urlopen(urllib.request.Request(origin + '/api/library/results/' + action,
                data=json.dumps(body).encode(), headers={'Origin': origin, 'X-Aredoko-Token': token}), timeout=5)
        try:
            with post('create', {'session_id': self.sid, 'conditions': {'mode': 'literal'}}) as response:
                self.assertEqual(json.load(response)['total'], 125)
            with post('range', {'session_id': self.sid, 'offset': 60, 'limit': 60}) as response:
                self.assertEqual(json.load(response)['items'][0]['id'], self.items[60]['id'])
            with post('neighbor', {'session_id': self.sid, 'item_id': self.items[119]['id'], 'direction': 1}) as response:
                self.assertEqual(json.load(response)['neighbor']['item']['id'], self.items[120]['id'])
            with post('status', {'session_id': self.sid}) as response: self.assertEqual(json.load(response)['state'], 'ready')
            with self.assertRaises(urllib.error.HTTPError) as error: post('status', {'session_id': self.sid}, 'wrong')
            self.assertEqual(error.exception.code, 403); error.exception.close()
            handler.results.sessions[self.sid].last_used -= IDLE_SECONDS + 1
            with self.assertRaises(urllib.error.HTTPError) as error: post('neighbor', {'session_id': self.sid, 'item_id': 60, 'direction': 1})
            self.assertEqual(error.exception.code, 410)
            with error.exception as response:
                value = json.load(response); self.assertEqual(value['current_id'], 60); self.assertEqual(value['conditions'], {'mode': 'literal'})
        finally:
            server.shutdown(); server.server_close(); thread.join(5)
            handler.results.close(); handler.animations.close(); handler.setup_jobs.close()

    def test_visual_neighbor_include_books_traverses_images_and_cbz(self):
        import zipfile
        output = io.BytesIO(); Image.new('RGB', (4, 4), 'blue').save(output, format='PNG'); blue = output.getvalue()
        with zipfile.ZipFile(self.media / '000_book.cbz', 'w') as zf:
            zf.writestr('001.png', blue)
        (self.media / '000_clip.mp4').write_bytes(b'placeholder')
        (self.media / '125_after.png').write_bytes(blue)
        self.catalog.index.scan(self.root); self.catalog.sync_index()
        by_name = {Path(r['relative_path']).name: r['id'] for p in range(3) for r in self.catalog.search(page=p)['items']}
        prev_img = by_name['124.png']
        cbz_id = by_name['000_book.cbz']
        next_img = by_name['125_after.png']
        self.create()
        # Default include_books=False continues skipping books and videos.
        self.assertEqual(self.owner.neighbor(self.sid, prev_img, 1)['neighbor']['item']['id'], next_img)
        # include_books=True crosses from Image -> CBZ -> Image while still skipping videos.
        self.assertEqual(self.owner.neighbor(self.sid, prev_img, 1, include_books=True)['neighbor']['item']['id'], cbz_id)
        self.assertEqual(self.owner.neighbor(self.sid, cbz_id, 1, include_books=True)['neighbor']['item']['id'], next_img)
        self.assertEqual(self.owner.neighbor(self.sid, next_img, -1, include_books=True)['neighbor']['item']['id'], cbz_id)

    def test_cancel_during_locate_closes_sqlite_and_removes_workspace(self):
        self.create()
        session = self.owner.sessions[self.sid]
        entered = threading.Event()
        release = threading.Event()
        original_check = session.check
        calls = 0

        def held_check():
            nonlocal calls
            calls += 1
            if calls == 2:
                entered.set()
                release.wait(3)
            return original_check()

        errors = []
        session.check = held_check

        def run_locate():
            try:
                self.owner.locate(self.sid, [self.items[0]['id']])
            except Exception as error:
                errors.append(error)

        worker = threading.Thread(target=run_locate)
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            self.owner.cancel(self.sid)
        finally:
            release.set()
            worker.join(4)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ResultUnavailable)
        self.assertFalse(list(self.base.glob('aredoko-results-*')))

    def test_ai_vector_writes_keep_non_ai_sessions_valid_while_invalidating_ai_sessions(self):
        encoder = Encoder(); ai = AISearch(self.catalog, encoder); self.addCleanup(ai.close)
        for item in self.items[:5]:
            ai.store.put(item['id'], revision(item), {'text': [1.] + [0.] * 7, 'cover': [1.] + [0.] * 7})
        self.catalog.record_view(self.items[0]['id'])
        handler = production_handler(self.catalog, 'fixture', ai=ai)
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        def post(action, body):
            req = urllib.request.Request(origin + '/api/library/results/' + action,
                data=json.dumps(body).encode(), headers={'Origin': origin, 'X-Aredoko-Token': 'fixture'})
            return urllib.request.urlopen(req, timeout=5)
        groups = [
            ([('0' * 31 + '1', {'mode': 'literal'}), ('0' * 31 + '2', {'mode': 'history'})],
             [('0' * 31 + '5', {'mode': 'semantic', 'query': 'generated', 'source': 'text'})]),
            ([('0' * 31 + '3', {'mode': 'page-text', 'query': 'generated'}), ('0' * 31 + '4', {'mode': 'pending-proposals', 'query': 'generated'})],
             [('0' * 31 + '6', {'mode': 'similar', 'item_id': self.items[0]['id']})]),
            ([], [('0' * 31 + '7', {'mode': 'pending-proposals-semantic', 'query': 'generated'})]),
        ]
        try:
            for idx, (non_ai_group, ai_group) in enumerate(groups):
                for sid, conditions in non_ai_group + ai_group:
                    with post('create', {'session_id': sid, 'conditions': conditions}) as resp:
                        self.assertEqual(resp.status, 200)
                # Writing a vector to ai_index.sqlite invalidates AI modes only.
                target = self.items[5 + idx]
                ai.store.put(target['id'], revision(target), {'text': [0., 1.] + [0.] * 6, 'cover': [0., 1.] + [0.] * 6})
                for sid, conditions in non_ai_group:
                    with self.subTest(kept=conditions['mode']):
                        with post('range', {'session_id': sid, 'offset': 0, 'limit': 10}) as resp:
                            self.assertEqual(resp.status, 200)
                for sid, conditions in ai_group:
                    with self.subTest(invalidated=conditions['mode']):
                        with self.assertRaises(urllib.error.HTTPError) as caught:
                            post('range', {'session_id': sid, 'offset': 0, 'limit': 10})
                        self.assertEqual(caught.exception.code, 409)
                        payload = json.loads(caught.exception.read())
                        self.assertEqual(payload['error_code'], 'result_session_changed')
                        self.assertNotIn('ai_indexing', payload)
                        caught.exception.close()
                if idx == 0:
                    # Catalog mutations still invalidate non-AI sessions.
                    self.catalog.update([self.items[0]['id']], {'tags': ['updated']})
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        post('range', {'session_id': non_ai_group[0][0], 'offset': 0, 'limit': 10})
                    self.assertEqual(caught.exception.code, 409)
                    self.assertEqual(json.loads(caught.exception.read())['error_code'], 'result_session_changed')
                    caught.exception.close()
                for sid, _ in non_ai_group + ai_group:
                    with post('close', {'session_id': sid}) as resp:
                        self.assertEqual(resp.status, 200)
        finally:
            server.shutdown(); server.server_close(); thread.join(5)
            handler.results.close(); handler.animations.close(); handler.setup_jobs.close()

    def test_ai_mode_conflict_during_active_indexing_includes_ai_indexing_flag(self):
        encoder = Encoder(); ai = AISearch(self.catalog, encoder); self.addCleanup(ai.close)
        for item in self.items[:4]:
            ai.store.put(item['id'], revision(item), {'text': [1.] + [0.] * 7, 'cover': [1.] + [0.] * 7})
        handler = production_handler(self.catalog, 'fixture', ai=ai)
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        def post(action, body):
            req = urllib.request.Request(origin + '/api/library/results/' + action,
                data=json.dumps(body).encode(), headers={'Origin': origin, 'X-Aredoko-Token': 'fixture'})
            return urllib.request.urlopen(req, timeout=5)
        try:
            lit_sid = '1' * 32
            sem_sid = '2' * 32
            sim_sid = '3' * 32
            exp_sid = '4' * 32
            for sid, cond in [(lit_sid, {'mode': 'literal'}),
                              (sem_sid, {'mode': 'semantic', 'query': 'generated', 'source': 'text'}),
                              (sim_sid, {'mode': 'similar', 'item_id': self.items[0]['id']})]:
                with post('create', {'session_id': sid, 'conditions': cond}) as resp:
                    self.assertEqual(resp.status, 200)
            # Simulate active AI build writing a vector while state is running / cancelling.
            ai.store.put(self.items[4]['id'], revision(self.items[4]), {'text': [0., 1.] + [0.] * 6, 'cover': [0., 1.] + [0.] * 6})
            for state, sid, cond in [
                ('running', sem_sid, {'mode': 'semantic', 'query': 'generated', 'source': 'text'}),
                ('cancelling', sim_sid, {'mode': 'similar', 'item_id': self.items[0]['id']}),
            ]:
                ai.store.save_state({'state': state, 'processed': 1, 'total': 10, 'indexed': 1, 'skipped': 0, 'error': ''})
                with self.subTest(state=state, mode=cond['mode']):
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        post('range', {'session_id': sid, 'offset': 0, 'limit': 10})
                    self.assertEqual(caught.exception.code, 409)
                    payload = json.loads(caught.exception.read())
                    self.assertEqual(payload['error_code'], 'result_session_changed')
                    self.assertEqual(payload['conditions'], cond)
                    self.assertIsNone(payload['current_id'])
                    self.assertIs(payload['ai_indexing'], True)
                    caught.exception.close()
                # Literal session remains completely valid while AI build is active.
                with post('range', {'session_id': lit_sid, 'offset': 0, 'limit': 10}) as resp:
                    self.assertEqual(resp.status, 200)
            for sid in (lit_sid, sem_sid, sim_sid):
                with post('close', {'session_id': sid}) as resp:
                    self.assertEqual(resp.status, 200)
            # Expired (410) sessions must not be tagged as ai_indexing even while running.
            with post('create', {'session_id': exp_sid, 'conditions': {'mode': 'semantic', 'query': 'generated', 'source': 'text'}}) as resp:
                self.assertEqual(resp.status, 200)
            handler.results.sessions[exp_sid].last_used -= IDLE_SECONDS + 1
            with self.assertRaises(urllib.error.HTTPError) as caught:
                post('range', {'session_id': exp_sid, 'offset': 0, 'limit': 10})
            self.assertEqual(caught.exception.code, 410)
            payload = json.loads(caught.exception.read())
            self.assertEqual(payload['error_code'], 'result_session_expired')
            self.assertNotIn('ai_indexing', payload)
            caught.exception.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(5)
            handler.results.close(); handler.animations.close(); handler.setup_jobs.close()


if __name__ == '__main__': unittest.main()
