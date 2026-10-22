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
