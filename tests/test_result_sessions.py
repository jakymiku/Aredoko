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
        import result_sessions
        entered=threading.Event();release=threading.Event();errors=[];closed=[];original=result_sessions._safe_path
        def held(*args,**kwargs):entered.set();release.wait(3);return original(*args,**kwargs)
        def build():
            try:self.create()
            except Exception as error:errors.append(error)
        with patch('result_sessions._safe_path',side_effect=held):
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
        path.unlink(); self.create(); path.write_bytes(data)
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

    def test_capacity_never_publishes_a_truncated_result(self):
        self.owner.max_bytes = 65536
        with self.catalog.connect() as db: db.execute('UPDATE items SET title=?', ('x' * 2000,))
        with self.assertRaises(ResultCapacity): self.create()
        self.assertNotIn(self.sid, self.owner.sessions)
        self.assertFalse(list(self.base.glob('aredoko-results-*')))

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

    def test_capture_overlaps_at_most_four_sources_but_keeps_provider_order(self):
        import result_sessions
        original=result_sessions.FrozenResult._current
        lock=threading.Lock();another=threading.Event();active=0;peak=0
        first=self.items[0]['id'];completed=[]
        def checked(session,payload,**kwargs):
            nonlocal active,peak
            with lock:active+=1;peak=max(peak,active)
            try:
                if payload['id']==first:
                    self.assertTrue(another.wait(3))
                else:another.set()
                result=original(session,payload,**kwargs)
                with lock:completed.append(payload['id'])
                return result
            finally:
                with lock:active-=1
        with patch.object(result_sessions.FrozenResult,'_current',new=checked):self.create()
        session=self.owner.sessions[self.sid]
        self.assertEqual([row[0] for row in session.db.execute('SELECT item_id FROM results ORDER BY ordinal')],[i['id'] for i in self.items])
        self.assertGreaterEqual(peak,2);self.assertLessEqual(peak,4)
        self.assertEqual(sorted(completed),sorted(i['id'] for i in self.items))
        self.assertIsNone(session.capture_executor)
        self.assertFalse(any(t.name.startswith('result-source') for t in threading.enumerate()))

    def test_close_during_parallel_capture_joins_checks_before_workspace_cleanup(self):
        import result_sessions
        original=result_sessions.FrozenResult._current;entered=threading.Event();release=threading.Event();errors=[]
        def held(session,payload,**kwargs):
            entered.set();release.wait(4)
            return original(session,payload,**kwargs)
        def build():
            try:self.create()
            except Exception as error:errors.append(error)
        with patch.object(result_sessions.FrozenResult,'_current',new=held):
            thread=threading.Thread(target=build);thread.start();self.assertTrue(entered.wait(3))
            try:self.assertFalse(self.owner.close(timeout=.02))
            finally:release.set();thread.join(6)
        self.assertFalse(thread.is_alive());self.assertTrue(errors)
        self.assertFalse(list(self.base.glob('aredoko-results-*')))
        self.assertFalse(any(t.name.startswith('result-source') for t in threading.enumerate()))

    def test_parallel_capture_failure_never_publishes_partial_results(self):
        import result_sessions
        original=result_sessions.FrozenResult._current
        def failed(session,payload,**kwargs):
            if payload['id']==self.items[2]['id']:raise ResultUnavailable('Generated capture failure')
            return original(session,payload,**kwargs)
        with patch.object(result_sessions.FrozenResult,'_current',new=failed):
            with self.assertRaises(ResultUnavailable):self.create()
        self.assertNotIn(self.sid,self.owner.sessions)
        self.assertFalse(list(self.base.glob('aredoko-results-*')))
        self.assertFalse(any(t.name.startswith('result-source') for t in threading.enumerate()))

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


if __name__ == '__main__': unittest.main()
