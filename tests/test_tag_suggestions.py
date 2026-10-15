"""P2 persistence/approval contracts, not an AI tagging quality benchmark."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid
import zipfile
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
sys.path.insert(0, str(ROOT / 'tools'))
from ai_process import AIUnavailable
from ai_search import AIBusy
from create_preview_fixture import png
from production import ProductionCatalog, ScanBusyError
from production_server import production_handler, DisabledAI
from previews import PreviewReader, ReaderChanged, PreviewUnavailable, PreviewBusyError, MAX_IMAGE_BYTES
from tag_suggestions import TagSuggestions, TaggerInfo, TagProposal, SuggestionConflict


class FictionTagger:
    """Explicitly fake: checks the bounded input, returns predetermined labels."""
    info = TaggerInfo('fiction-adapter', '1', 'test-only', 'fixed-fixture', 'cover-v1')

    def __init__(self):
        self.calls = 0
        self.hook = None
        self.output = [TagProposal('生成候補', '生成fixtureの根拠です'),
                       TagProposal('別候補', '生成fixtureの別の根拠です')]

    def suggest(self, source, cancelled):
        self.calls += 1
        assert set(source) == {'source', 'data', 'mime'}
        assert source['data'].startswith(b'\x89PNG')
        assert 'path' not in source['source'] and source['mime'] == 'image/png'
        if self.hook: self.hook(cancelled)
        return self.output


class TagFixture:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.media = self.base / 'fiction'
        self.media.mkdir()
        self.path = self.media / 'fiction.png'
        self.path.write_bytes(png())
        self.book = self.media / 'fiction.cbz'
        with zipfile.ZipFile(self.book, 'w') as archive:
            archive.writestr('10.png', png(color=(100, 20, 30)))
            archive.writestr('2.png', png())
        self.catalog = ProductionCatalog(self.base / 'catalog.sqlite')
        self.addCleanup(self.catalog.close)
        self.root = self.catalog.add_root(str(self.media))
        self.scan()
        self.item = self.ids['fiction.png']
        self.adapter = FictionTagger()
        self.service = TagSuggestions(self.catalog, self.adapter)

    def scan(self):
        self.catalog.index.scan(self.root)
        self.catalog.sync_index()
        self.ids = {r['title']: r['id'] for r in self.catalog.search()['items']}

    def generate(self, item=None):
        return self.service.generate(item or self.item, uuid.uuid4().hex)

    def candidates(self, item=None):
        return self.service.list(item or self.item)['batches']

    def review(self, proposal, decision='accept', tag=None, item=None):
        return self.service.review(item or self.item, proposal['id'], proposal['version'], decision, tag)

    def counts(self):
        with self.catalog.connect() as db:
            return tuple(db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                         for table in ('tag_proposal_batches', 'tag_proposals'))

class TagSuggestionTests(TagFixture, unittest.TestCase):
    def test_provenance_is_distinct_and_accept_edit_reject_preserve_metadata(self):
        before = self.path.read_bytes(), self.path.stat().st_mtime_ns
        self.catalog.update([self.item], {'tags': ['手動'], 'shelf': '棚', 'favorite': True, 'reviewed': True})
        batch = self.generate()['batch']
        self.assertEqual(batch['producer'], self.adapter.info.record())
        self.assertEqual(batch['evidence']['kind'], 'image')
        self.assertEqual(batch['evidence']['page'], 0)
        self.assertEqual(self.catalog.search('生成候補')['total'], 0)
        self.assertEqual(self.catalog.get(self.item)['tags'], ['手動'])
        first, second = batch['proposals']
        self.review(first, tag='修正して確定')
        self.review(second, 'reject')
        self.assertEqual(self.catalog.get(self.item)['tags'], ['手動', '修正して確定'])
        self.assertEqual(self.catalog.search('修正して確定')['total'], 1)
        self.assertEqual(self.catalog.search('別候補')['total'], 0)
        item = self.catalog.get(self.item)
        self.assertEqual((item['shelf'], item['favorite'], item['reviewed']), ('棚', True, True))
        self.assertEqual(before, (self.path.read_bytes(), self.path.stat().st_mtime_ns))
        saved = self.candidates()[0]['proposals']
        self.assertEqual([p['state'] for p in saved], ['accepted', 'rejected'])
        self.assertEqual(saved[0]['tag'], '生成候補')
        self.assertEqual(saved[0]['accepted_tag'], '修正して確定')

    def test_manual_changes_do_not_stale_remaining_candidates_or_get_overwritten(self):
        proposals = self.generate()['batch']['proposals']
        revision = self.candidates()[0]['source_revision']
        self.review(proposals[0])
        self.catalog.update([self.item], {'tags': ['手動で変更', '生成候補']})
        self.assertFalse(self.candidates()[0]['stale'])
        self.review(proposals[1])
        self.assertEqual(self.catalog.get(self.item)['tags'], ['手動で変更', '生成候補', '別候補'])
        again = self.generate()
        self.assertTrue(again['reused'])
        self.assertEqual(self.adapter.calls, 1)
        self.assertEqual(again['batch']['source_revision'], revision)

    def test_restart_idempotent_and_new_adapter_keeps_history_decisions_and_progress(self):
        book = self.ids['fiction.cbz']
        reader = PreviewReader(self.catalog)
        manifest = reader.manifest(book)
        self.catalog.save_reader_progress(book, {'revision': manifest['revision'], 'page': 1, 'mode': 'rtl'}, reader)
        batch = self.generate(book)['batch']
        self.assertEqual(batch['evidence']['kind'], 'cover')
        self.assertEqual(batch['evidence']['revision'], manifest['revision'])
        self.review(batch['proposals'][0], item=book)
        self.review(batch['proposals'][1], 'reject', item=book)
        reopened = ProductionCatalog(self.catalog.path)
        self.addCleanup(reopened.close)
        service = TagSuggestions(reopened, self.adapter)
        self.assertTrue(service.generate(book, uuid.uuid4().hex)['reused'])
        self.assertEqual(reopened.reader_progress(book)['progress']['page'], 1)
        self.adapter.info = TaggerInfo('fiction-adapter', '2', 'test-only', 'fixed-fixture', 'cover-v1')
        service.generate(book, uuid.uuid4().hex)
        history = service.list(book)['batches']
        self.assertEqual(len(history), 2)
        self.assertEqual([p['state'] for p in history[1]['proposals']], ['accepted', 'rejected'])
        self.assertEqual(reopened.get(book)['tags'], ['生成候補'])

    def test_stale_source_rejects_review_and_reanalysis_preserves_manual_tags(self):
        batch = self.generate()['batch']
        self.catalog.update([self.item], {'tags': ['保全']})
        self.path.write_bytes(png(color=(44, 55, 66)))
        os.utime(self.path, ns=(self.path.stat().st_atime_ns, self.path.stat().st_mtime_ns + 1000000))
        with self.assertRaises(SuggestionConflict): self.review(batch['proposals'][0])
        self.scan()
        self.assertTrue(self.candidates()[0]['stale'])
        with self.assertRaises(SuggestionConflict): self.review(batch['proposals'][0])
        new = self.generate()['batch']
        self.assertNotEqual(new['source_revision'], batch['source_revision'])
        self.assertEqual(self.catalog.get(self.item)['tags'], ['保全'])
        self.assertEqual(len(self.candidates()), 2)

    def test_replaced_source_during_inference_publishes_nothing(self):
        def replace(_):
            replacement = self.media / 'replacement.tmp'
            replacement.write_bytes(self.path.read_bytes())
            os.replace(replacement, self.path)
        self.adapter.hook = replace
        with self.assertRaises(SuggestionConflict): self.generate()
        self.assertEqual(self.counts(), (0, 0))

    def test_decision_conflicts_and_cross_item_ids_do_not_change_tags(self):
        proposal = self.generate()['batch']['proposals'][0]
        with self.assertRaises(KeyError): self.review(proposal, item=self.ids['fiction.cbz'])
        self.review(proposal, 'reject')
        with self.assertRaises(SuggestionConflict): self.review(proposal)
        with self.assertRaises(SuggestionConflict): self.service.review(self.item, proposal['id'], 1, 'accept')
        self.assertEqual(self.catalog.get(self.item)['tags'], [])

    def test_tag_limit_rolls_back_entire_review_and_duplicate_accept_fits(self):
        proposal = self.generate()['batch']['proposals'][0]
        self.catalog.update([self.item], {'tags': [str(i) for i in range(30)]})
        with self.assertRaises(ValueError): self.review(proposal)
        self.assertEqual(self.candidates()[0]['proposals'][0]['state'], 'pending')
        self.review(proposal, tag='0')
        self.assertEqual(len(self.catalog.get(self.item)['tags']), 30)

    def test_source_check_at_transaction_end_rolls_back_tags_and_decision(self):
        proposal = self.generate()['batch']['proposals'][0]
        original = self.service.previews.tag_source
        calls = []
        def changed(item):
            calls.append(item)
            if len(calls) == 2: raise ReaderChanged('fiction replacement')
            return original(item)
        with patch.object(self.service.previews, 'tag_source', side_effect=changed):
            with self.assertRaises(SuggestionConflict): self.review(proposal)
        self.assertEqual(self.catalog.get(self.item)['tags'], [])
        self.assertEqual(self.candidates()[0]['proposals'][0]['state'], 'pending')

    def test_cancel_has_no_partial_batch_and_retry_is_possible(self):
        started = threading.Event()
        finish = threading.Event()
        errors = []
        request_id = uuid.uuid4().hex
        self.adapter.hook = lambda cancelled: (started.set(), finish.wait(5))
        def run():
            try: self.service.generate(self.item, request_id)
            except Exception as error: errors.append(error)
        worker = threading.Thread(target=run)
        worker.start()
        try:
            self.assertTrue(started.wait(5))
            with self.assertRaises(AIBusy): self.generate()
            self.assertFalse(self.service.cancel(uuid.uuid4().hex)['cancel_requested'])
            self.assertTrue(self.service.cancel(request_id)['cancel_requested'])
            # Metadata edits stay usable while the adapter is busy.
            self.catalog.update([self.item], {'tags': ['並行編集']})
        finally:
            finish.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], SuggestionConflict)
        self.assertEqual(self.counts(), (0, 0))
        self.adapter.hook = None
        self.generate()
        self.assertFalse(self.service.cancel(request_id)['cancel_requested'])
        self.assertEqual(self.catalog.get(self.item)['tags'], ['並行編集'])

    def test_invalid_adapter_output_and_failure_never_publish_partial_batch(self):
        for output in ([TagProposal('a', 'ok'), TagProposal('b', 'wrong page', 1)],
                       [TagProposal('a', 'ok'), TagProposal('a', 'duplicate')],
                       [TagProposal('a', '')], [TagProposal('a', 'bad', True)],
                       [TagProposal('a\n', 'bad')], [TagProposal('a', 'ok')] * 31):
            self.adapter.output = output
            with self.assertRaises(AIUnavailable): self.generate()
            self.assertEqual(self.counts(), (0, 0))
        def fail(_): raise AIUnavailable('fiction worker failed')
        self.adapter.hook = fail
        with self.assertRaises(AIUnavailable): self.generate()
        self.assertEqual(self.counts(), (0, 0))

    def test_unknown_is_empty_complete_batch_and_not_retry_loop(self):
        self.adapter.output = []
        self.assertEqual(self.generate()['batch']['proposals'], [])
        self.assertTrue(self.generate()['reused'])
        self.assertEqual(self.adapter.calls, 1)
        self.assertEqual(self.counts(), (1, 0))

    def test_two_services_publish_one_batch_without_replacing_decisions(self):
        other_adapter = FictionTagger()
        other = TagSuggestions(self.catalog, other_adapter)
        barrier = threading.Barrier(2, timeout=5)
        self.adapter.hook = other_adapter.hook = lambda _: barrier.wait()
        results, errors = [], []
        def generate(service):
            try: results.append(service.generate(self.item, uuid.uuid4().hex))
            except Exception as error: errors.append(error)
        workers = [threading.Thread(target=generate, args=(service,)) for service in (self.service, other)]
        for worker in workers: worker.start()
        for worker in workers: worker.join(8)
        self.assertFalse(any(w.is_alive() for w in workers))
        self.assertEqual(errors, [])
        self.assertEqual(sorted(r['reused'] for r in results), [False, True])
        self.assertEqual(self.counts(), (1, 2))
        self.review(results[0]['batch']['proposals'][0], 'reject')
        self.assertTrue(other.generate(self.item, uuid.uuid4().hex)['reused'])
        self.assertEqual(self.candidates()[0]['proposals'][0]['state'], 'rejected')

    def test_preview_boundaries_and_busy_do_not_call_adapter(self):
        with patch.object(self.service.previews, 'tag_source', side_effect=PreviewBusyError('fiction busy')):
            with self.assertRaises(AIBusy): self.generate()
        with self.path.open('wb') as file:
            file.truncate(MAX_IMAGE_BYTES + 1)
        self.scan()
        with self.assertRaises(KeyError): self.generate()
        self.assertEqual(self.adapter.calls, 0)
        self.assertEqual(self.counts(), (0, 0))

    def test_adapter_change_and_unexpected_worker_failure_publish_nothing(self):
        def change(_):
            self.adapter.info = TaggerInfo('fiction', '2', 'fixture', 'fixed', 'cover-v1')
        self.adapter.hook = change
        with self.assertRaises(SuggestionConflict): self.generate()
        self.assertEqual(self.counts(), (0, 0))
        def fail(_): raise RuntimeError('internal path must not become an HTTP response')
        self.adapter.hook = fail
        with self.assertRaisesRegex(AIUnavailable, '^Tagger failed; no proposals saved$'): self.generate()
        self.assertEqual(self.counts(), (0, 0))

    def test_scan_busy_excluded_unregistered_and_restore(self):
        proposal = self.generate()['batch']['proposals'][0]
        with patch.object(self.catalog, '_require_idle', side_effect=ScanBusyError('fiction scan')):
            with self.assertRaises(ScanBusyError): self.review(proposal)
            with self.assertRaises(ScanBusyError): self.generate()
        self.catalog.set_excludes(self.root, ['*.png'])
        with self.assertRaises(KeyError): self.review(proposal)
        self.catalog.set_excludes(self.root, [])
        self.catalog.unregister_root(self.root)
        with self.assertRaises(KeyError): self.candidates()
        self.catalog.add_root(str(self.media))
        self.scan()
        self.assertEqual(self.candidates()[0]['proposals'][0]['state'], 'pending')
        self.review(proposal)

    def test_paged_history_and_validation(self):
        for i in range(3):
            self.adapter.info = TaggerInfo('fiction', str(i), 'test-only', 'fixture', 'cover-v1')
            self.generate()
        first = self.service.list(self.item, limit=2)
        second = self.service.list(self.item, before=first['next_before'], limit=2)
        self.assertEqual(len(first['batches']), 2)
        self.assertEqual(len(second['batches']), 1)
        self.assertIsNone(second['next_before'])
        for bad in (True, 0, -1, 2**63, '1'):
            with self.assertRaises(ValueError): self.service.list(bad)
            with self.assertRaises(ValueError): self.service.list(self.item, before=bad)
        for bad in (0, 21, True, '1'):
            with self.assertRaises(ValueError): self.service.list(self.item, limit=bad)
        with self.assertRaises(ValueError): self.service.cancel('x')
        with self.assertRaises(ValueError): self.service.review(self.item, 1, True, 'accept')
        with self.assertRaises(ValueError): self.service.review(self.item, 1, 0, 'reject', 'edited')

    def test_default_model_unavailable_does_not_fake_candidates(self):
        default = TagSuggestions(self.catalog)
        self.assertFalse(default.status()['available'])
        self.assertFalse(default.list(self.item)['available'])
        with self.assertRaises(AIUnavailable): default.generate(self.item, uuid.uuid4().hex)
        self.assertEqual(self.counts(), (0, 0))


class TagSuggestionHTTPTests(TagFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), production_handler(
            self.catalog, 'fiction-token', ai=DisabledAI(), tagger=self.adapter))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def request(self, path, body=None, headers=None):
        settings = {'X-Aredoko-Token': 'fiction-token', 'Origin': self.url}
        settings.update(headers or {})
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.url + path, data=data, headers=settings)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.load(error)

    def test_http_generate_review_auth_strict_fields_and_history(self):
        route = '/api/library/tag-suggestions'
        body = {'item_id': self.item, 'request_id': uuid.uuid4().hex}
        for headers in ({'X-Aredoko-Token': 'wrong'}, {'Origin': 'https://example.invalid'}, {'Host': 'localhost'}):
            self.assertEqual(self.request(route + '/generate', body, headers)[0], 403)
        self.assertEqual(self.request(route + '/' + str(self.item), headers={'X-Aredoko-Token': 'bad'})[0], 403)
        self.assertEqual(self.request(route + '/generate', {**body, 'model_path': 'ignored'})[0], 400)
        status, generated = self.request(route + '/generate', body)
        self.assertEqual(status, 200)
        proposal = generated['batch']['proposals'][0]
        review = {'item_id': self.item, 'proposal_id': proposal['id'], 'version': 0,
                  'decision': 'accept', 'tag': 'HTTPで修正'}
        self.assertEqual(self.request(route + '/review', review)[0], 200)
        self.assertEqual(self.request(route + '/review', review)[0], 409)
        status, history = self.request(route + '/' + str(self.item))
        self.assertEqual(status, 200)
        self.assertEqual(history['batches'][0]['proposals'][0]['accepted_tag'], 'HTTPで修正')
        for query in ('?limit=0', '?limit=1&limit=2', '?unknown=x', '?before=', '?before=9223372036854775808'):
            self.assertEqual(self.request(route + '/' + str(self.item) + query)[0], 400)
        self.assertEqual(self.request(route + '/9223372036854775808')[0], 400)
        self.assertEqual(self.request(route + '/cancel', {'request_id': body['request_id']})[0], 200)
        self.assertEqual(self.request(route + '/review', {**review, 'source_revision': 'client-value'})[0], 400)

    def test_revision_bound_evidence_auth_stale_and_strict_query(self):
        revision = self.service.list(self.item)['source_revision']
        route = f'/api/library/tag-suggestions/{self.item}/evidence'
        def read(query, token='fiction-token'):
            request=urllib.request.Request(self.url+route+query,headers={'X-Aredoko-Token':token})
            try:
                with urllib.request.urlopen(request,timeout=5) as response:return response.status,response.headers.get_content_type(),response.read()
            except urllib.error.HTTPError as error:
                with error:return error.code,error.headers.get_content_type(),error.read()
        status,mime,data=read('?revision='+revision)
        self.assertEqual((status,mime,data),(200,'image/png',self.path.read_bytes()))
        self.assertEqual(read('?revision='+revision,'wrong')[0],403)
        for query in ('','?revision=bad','?revision='+revision+'&revision='+revision,'?revision='+revision+'&extra=1'):
            self.assertEqual(read(query)[0],400)
        self.assertEqual(read('?revision='+'0'*64)[0],409)
        self.path.write_bytes(png(color=(11,22,33)))
        self.assertEqual(read('?revision='+revision)[0],409)
        self.catalog.unregister_root(self.root)
        self.assertEqual(read('?revision='+revision)[0],404)

    def test_http_busy_and_adapter_failure_are_explicit(self):
        route = '/api/library/tag-suggestions'
        with patch.object(PreviewReader, 'tag_source', side_effect=PreviewBusyError('fixture busy')):
            self.assertEqual(self.request(route + '/' + str(self.item))[0], 409)
        def fail(_): raise RuntimeError('private internal details')
        self.adapter.hook = fail
        status, result = self.request(route + '/generate', {'item_id': self.item, 'request_id': uuid.uuid4().hex})
        self.assertEqual(status, 503)
        self.assertNotIn('private', result['error'])
        self.assertEqual(self.counts(), (0, 0))


if __name__ == '__main__':
    unittest.main()
