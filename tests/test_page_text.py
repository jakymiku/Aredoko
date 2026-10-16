"""Generated pages and deterministic adapters only; no OCR quality claims."""
import json
import threading
import unittest
from dataclasses import replace
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import test_page_index
from test_page_index import PageFixture
from ai_process import AIUnavailable
from ai_search import AIBusy
from page_text import PageTextIndex, MAX_TEXT
from previews import ReaderChanged, PreviewBusyError
from production import ScanBusyError
from production_server import production_handler, DisabledAI
from tag_suggestions import TaggerInfo


class FakeExtractor:
    def __init__(self):
        self.info = TaggerInfo('fixture-text', '1', 'no-real-model', 'v1', 'checked-bytes-v1')
        self.calls = []
        self.output = lambda payload, cancelled: '図書室で レイム が待つ ＡＢＣ'

    def extract(self, payload, cancelled):
        self.calls.append(payload)
        return self.output(payload, cancelled)


class TextFixture(PageFixture):
    def setUp(self):
        super().setUp()
        self.extractor = FakeExtractor()
        self.texts = PageTextIndex(self.catalog, self.pages, self.extractor)
        self.item = self.ids['comic/']
        self.pages.refresh(self.item)
        self.listing = self.pages.list(self.item)
        self.revision = self.listing['source_revision']
        self.page_ids = [p['page_id'] for p in self.listing['pages']]
        self.request = 'a' * 32

    def generate(self, **overrides):
        args = dict(item_id=self.item, page_ids=self.page_ids, revision=self.revision, request_id=self.request)
        args.update(overrides)
        return self.texts.generate(**args)

    def text_counts(self):
        with self.catalog.connect() as db:
            return tuple(db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                         for table in ('page_texts', 'page_text_heads'))


class PageTextTests(TextFixture, unittest.TestCase):
    def test_body_page_roundtrip_is_explicit_and_preserves_originals(self):
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.folder.iterdir()}
        self.catalog.update([self.item], {'tags': ['手動'], 'favorite': True, 'shelf': '資料'})
        self.assertEqual(self.generate(page_ids=[self.page_ids[1]])['processed'], 1)
        payload = self.extractor.calls[0]
        self.assertEqual(payload['data'], self.second)
        self.assertEqual(payload['source']['page'], 1)
        self.assertEqual(payload['source']['page_id'], self.page_ids[1])
        self.assertNotIn('path', payload['source'])
        listing = self.texts.list(self.item)
        self.assertEqual((listing['total'], listing['source_state']), (1, 'current'))
        self.assertEqual(listing['pages'][0]['producer'], self.extractor.info.record())
        self.assertEqual(listing['pages'][0]['text'], '図書室で レイム が待つ ＡＢＣ')
        result = self.texts.search('れいむ abc 図書室', view='favorites', shelf='資料', root_ids=[self.bookroot])
        self.assertEqual(result['search_mode'], 'page-text')
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['items'][0]['page_text_match']['pages'][0]['page'], 1)
        self.assertEqual(self.catalog.search('図書室')['total'], 0)
        self.assertEqual(self.catalog.get(self.item)['tags'], ['手動'])
        self.assertEqual({p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.folder.iterdir()}, before)
        reopened = PageTextIndex(self.catalog, self.pages)
        self.assertFalse(reopened.status()['available'])
        self.assertEqual(reopened.search('図書室'), self.texts.search('図書室'))

    def test_same_page_and_matching_pages_aggregate_to_one_item(self):
        self.extractor.output = lambda p, c: '図書室' if p['source']['page'] == 0 else '幼なじみ'
        self.generate()
        self.assertEqual(self.texts.search('図書室 幼なじみ')['total'], 0)
        self.assertEqual(self.texts.search('図書室')['items'][0]['page_text_match']['matching_pages'], 1)
        self.extractor.info = replace(self.extractor.info, model_revision='v2')
        self.extractor.output = lambda p, c: '図書室 幼なじみ'
        self.generate()
        result = self.texts.search('図書室 幼なじみ')
        self.assertEqual((result['total'], len(result['items'])), (1, 1))
        self.assertEqual(result['items'][0]['page_text_match']['matching_pages'], 2)

    def test_cached_empty_text_and_producer_switch_keep_history(self):
        original = self.extractor.info
        self.extractor.output = lambda p, c: ''
        self.generate()
        self.assertEqual(self.generate()['reused'], 2)
        self.assertEqual(len(self.extractor.calls), 2)
        self.assertEqual(self.texts.list(self.item)['total'], 2)
        self.extractor.info = replace(original, model='new-model')
        self.extractor.output = lambda p, c: '図書室'
        self.generate()
        self.assertEqual(self.text_counts(), (4, 2))
        self.assertEqual(self.texts.search('図書室', model='new-model')['total'], 1)
        self.assertEqual(self.texts.search('図書室', model=original.model)['total'], 0)
        self.extractor.info = original
        self.assertEqual(self.generate()['reused'], 2)
        self.assertEqual(len(self.extractor.calls), 4)
        self.assertEqual(self.text_counts(), (4, 2))
        self.assertEqual(self.texts.search('図書室')['total'], 0)

    def test_failed_or_invalid_later_output_saves_no_partial_batch(self):
        for invalid in (None, 7, 'x' * (MAX_TEXT + 1), 'bad\x00text', '\ud800'):
            with self.subTest(kind=type(invalid).__name__):
                self.extractor.output = lambda p, c: 'valid' if p['source']['page'] == 0 else invalid
                with self.assertRaises(AIUnavailable):
                    self.generate()
                self.assertEqual(self.text_counts(), (0, 0))
        def fail(p, c):
            if p['source']['page']:
                raise RuntimeError('internal runtime path must not reach clients')
            return 'valid'
        self.extractor.output = fail
        with self.assertRaisesRegex(AIUnavailable, '^Page text extraction failed; no text saved$'):
            self.generate()
        self.assertEqual(self.text_counts(), (0, 0))
        self.extractor.output = lambda p, c: '前回の本文'
        self.generate()
        self.extractor.info = replace(self.extractor.info, model_revision='v2')
        self.extractor.output = fail
        with self.assertRaises(AIUnavailable):
            self.generate()
        self.assertEqual(self.text_counts(), (2, 2))
        self.assertEqual([p['text'] for p in self.texts.list(self.item)['pages']], ['前回の本文'] * 2)

    def test_evidence_limit_and_catalog_paging(self):
        for number in range(3, 6):
            (self.folder / f'{number}.png').write_bytes(self.first)
        for number in range(21):
            (self.loose / f'fixture-{number}.png').write_bytes(self.first)
        self.scan()
        for item in self.ids.values():
            self.pages.refresh(item)
            listing = self.pages.list(item)
            self.generate(item_id=item, page_ids=[p['page_id'] for p in listing['pages']],
                          revision=listing['source_revision'])
        result = self.texts.search('図書室')
        self.assertEqual((result['total'], len(result['items'])), (24, 20))
        rest = self.texts.search('図書室', page=1)
        self.assertEqual(len(rest['items']), 4)
        self.assertFalse({i['id'] for i in result['items']} & {i['id'] for i in rest['items']})
        match = self.texts.search('図書室', root_ids=[self.bookroot])['items'][0]['page_text_match']
        self.assertEqual((match['matching_pages'], len(match['pages'])), (5, 3))

    def test_batch_limit_rolls_back_all_pages(self):
        for number in range(3, 7):
            (self.folder / f'{number}.png').write_bytes(self.first)
        self.scan()
        self.pages.refresh(self.item)
        listing = self.pages.list(self.item)
        self.extractor.output = lambda p, c: '字' * MAX_TEXT
        with self.assertRaisesRegex(AIUnavailable, 'batch exceeds'):
            self.generate(page_ids=[p['page_id'] for p in listing['pages']], revision=listing['source_revision'])
        self.assertEqual(self.text_counts(), (0, 0))

    def test_cancel_and_parallel_generation_are_bounded_and_retryable(self):
        entered, release = threading.Event(), threading.Event()
        failures = []
        def output(p, cancelled):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('test timeout')
            self.assertTrue(cancelled())
            return 'cancelled text'
        self.extractor.output = output
        def run():
            try:
                self.generate()
            except Exception as error:
                failures.append(error)
        worker = threading.Thread(target=run)
        worker.start()
        try:
            self.assertTrue(entered.wait(5))
            with self.assertRaisesRegex(AIBusy, 'in progress'):
                self.generate(request_id='b' * 32)
            self.assertFalse(self.texts.cancel('b' * 32)['cancel_requested'])
            self.assertTrue(self.texts.cancel(self.request)['cancel_requested'])
        finally:
            release.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], AIBusy)
        self.assertEqual(self.text_counts(), (0, 0))
        self.assertFalse(self.texts.cancel(self.request)['cancel_requested'])
        self.extractor.output = lambda p, c: 'retry'
        self.assertEqual(self.generate()['processed'], 2)

    def test_source_changes_during_model_work_roll_back(self):
        def output(p, c):
            (self.folder / '1.png').write_bytes(self.second)
            return 'stale text'
        self.extractor.output = output
        with self.assertRaises(ReaderChanged):
            self.generate(page_ids=[self.page_ids[0]])
        self.assertEqual(self.text_counts(), (0, 0))

    def test_snapshot_and_producer_changes_during_model_work_roll_back(self):
        def producer_change(p, c):
            self.extractor.info = replace(self.extractor.info, model_revision='v2')
            return 'old producer'
        self.extractor.output = producer_change
        with self.assertRaisesRegex(AIBusy, 'extractor changed'):
            self.generate(page_ids=[self.page_ids[0]])
        self.assertEqual(self.text_counts(), (0, 0))
        def index_change(p, c):
            (self.folder / '0.png').write_bytes(self.second)
            self.scan()
            self.pages.refresh(self.item)
            return 'old index'
        self.extractor.output = index_change
        with self.assertRaises(ReaderChanged):
            self.generate(page_ids=[self.page_ids[0]])
        self.assertEqual(self.text_counts(), (0, 0))

    def test_user_metadata_edit_during_extraction_survives(self):
        def output(p, c):
            self.catalog.update([self.item], {'tags': ['利用者が編集'], 'shelf': '手動棚'})
            return '図書室'
        self.extractor.output = output
        self.generate()
        self.assertEqual(self.catalog.get(self.item)['tags'], ['利用者が編集'])
        self.assertEqual(self.catalog.get(self.item)['shelf'], '手動棚')

    def test_current_exclusions_and_unregistration_hide_retained_text(self):
        self.generate()
        self.catalog.set_excludes(self.bookroot, ['comic'])
        self.assertEqual(self.texts.search('図書室')['total'], 0)
        with self.assertRaises(KeyError):
            self.texts.list(self.item)
        self.catalog.set_excludes(self.bookroot, [])
        self.assertEqual(self.texts.search('図書室')['total'], 1)
        self.catalog.unregister_root(self.bookroot)
        self.assertEqual(self.texts.search('図書室')['total'], 0)
        with self.assertRaises(ValueError):
            self.texts.search('図書室', root_ids=[self.bookroot])
        self.assertEqual(self.catalog.add_root(str(self.books), folder_books=True), self.bookroot)
        self.assertEqual(self.texts.search('図書室')['total'], 1)
        self.assertEqual(self.text_counts(), (2, 2))

    def test_missing_stale_and_busy_are_not_current_and_refresh_does_not_reuse_old_text(self):
        self.generate()
        with patch.object(self.reader, 'tag_source', side_effect=PreviewBusyError('busy')):
            self.assertEqual(self.texts.search('図書室')['items'][0]['page_text_match']['source_state'], 'unverified')
        moved = self.books / 'moved'
        self.folder.rename(moved)
        self.assertEqual(self.texts.list(self.item)['source_state'], 'unavailable')
        moved.rename(self.folder)
        (self.folder / '0.png').write_bytes(self.first)
        self.assertEqual(self.texts.search('図書室')['items'][0]['page_text_match']['source_state'], 'stale')
        with self.assertRaises(ReaderChanged):
            self.generate()  # cached text also requires the current physical source
        self.scan()
        self.pages.refresh(self.item)
        self.assertEqual(self.texts.list(self.item)['total'], 0)
        self.assertEqual(self.texts.search('図書室')['total'], 0)
        self.assertEqual(self.text_counts(), (2, 2))

    def test_request_bounds_foreign_pages_and_scan_busy(self):
        for overrides in ({'item_id': True}, {'page_ids': []}, {'page_ids': self.page_ids * 9},
                          {'page_ids': [self.page_ids[0]] * 2}, {'revision': 'bad'}, {'request_id': 'bad'}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.generate(**overrides)
        with self.assertRaises(KeyError):
            self.generate(page_ids=[self.page_ids[0], 'f' * 64])
        self.assertEqual(self.extractor.calls, [])
        with patch.object(self.catalog, '_require_idle', side_effect=ScanBusyError('busy')):
            with self.assertRaises(ScanBusyError):
                self.generate()
        self.assertEqual(self.text_counts(), (0, 0))
        self.texts.extractor = None
        with self.assertRaises(AIUnavailable):
            self.generate()

    def test_search_and_list_paging_filters_never_broaden_invalid_scope(self):
        self.generate()
        for args in ({'root_ids': []}, {'root_ids': [self.root, self.root]}, {'root_ids': [2**63]},
                     {'root_ids': [True]}, {'root_ids': [99999]}, {'page': True}, {'kind': 'unknown'},
                     {'view': 'unknown'}, {'shelf': 8}, {'model': ''}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.texts.search('図書室', **args)
        for query in ('', '   ', 'x' * 301, None, ' '.join(map(str, range(17)))):
            with self.subTest(query=query), self.assertRaises(ValueError):
                self.texts.search(query)
        self.assertEqual(self.texts.search('図書室', root_ids=[self.root])['total'], 0)
        self.assertEqual(self.texts.search('図書室', page=1)['items'], [])
        for args in ({'limit': 11}, {'offset': 1}, {'offset': True}, {'revision': 'bad'}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.texts.list(self.item, **args)
        result = self.texts.list(self.item, offset=1, limit=1, revision=self.revision)
        self.assertEqual((result['total'], result['pages'][0]['page']), (2, 1))
        with self.assertRaises(ReaderChanged):
            self.texts.list(self.item, revision='0' * 64)


class PageTextHTTPTests(TextFixture, unittest.TestCase):
    call = test_page_index.PageHTTPTests.call

    def start_server(self, extractor=None):
        import urllib.request
        self.server = ThreadingHTTPServer(('127.0.0.1', 0),
            production_handler(self.catalog, 'test', ai=DisabledAI(), text_extractor=extractor))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def body(self):
        return dict(item_id=self.item, page_ids=self.page_ids, revision=self.revision, request_id=self.request)

    def test_unconnected_production_can_read_saved_text_but_cannot_generate(self):
        self.generate()
        self.start_server()
        self.assertFalse(self.call('/api/library/page-text/status')[1]['available'])
        self.assertEqual(self.call('/api/library/page-text/generate', self.body())[0], 503)
        self.assertEqual(self.call('/api/library/page-text/search', {'query': '図書室'})[1]['total'], 1)
        self.assertEqual(self.call(f'/api/library/page-text/{self.item}')[1]['total'], 2)

    def test_http_generate_cancel_auth_scopes_and_stale_conflict(self):
        self.start_server(self.extractor)
        for route, body in (('/api/library/page-text/status', None),
                            ('/api/library/page-text/generate', self.body()),
                            ('/api/library/page-text/search', {'query': '図書室'})):
            self.assertEqual(self.call(route, body, token='bad')[0], 403)
        self.assertEqual(self.call('/api/library/page-text/generate', self.body(), origin='https://example.invalid')[0], 403)
        self.assertEqual(self.call('/api/library/page-text/generate', self.body())[0], 200)
        self.assertEqual(self.call('/api/library/page-text/cancel', {'request_id': self.request})[1], {'cancel_requested': False})
        for body in ({}, {'query': '図書室', 'root_ids': []}, {'query': '図書室', 'text': 'injected'}):
            self.assertEqual(self.call('/api/library/page-text/search', body)[0], 400)
        for route in ('0', '01', 'status?x=1', f'{self.item}?limit=11', f'{self.item}?offset=1',
                      f'{self.item}?limit=1&limit=2', f'{self.item}?path=x'):
            self.assertEqual(self.call('/api/library/page-text/' + route)[0], 400)
        with patch.object(self.catalog, '_require_idle', side_effect=ScanBusyError('busy')):
            self.assertEqual(self.call('/api/library/page-text/generate', self.body())[0], 409)
        (self.folder / '0.png').write_bytes(self.second)
        self.assertEqual(self.call('/api/library/page-text/generate', self.body())[0], 409)
        self.assertEqual(self.text_counts(), (2, 2))


if __name__ == '__main__':
    unittest.main()
