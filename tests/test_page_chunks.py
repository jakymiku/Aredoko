"""Generated 145-page books: bounded HTTP plans, atomic chunks and restart resume."""
import copy
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from test_page_index import PageFixture
from test_page_semantics import Encoder
from ai_search import AISearch, AIBusy
from page_chunks import plan_chunked, start_chunked, resume_chunked
from previews import ReaderChanged, PreviewUnavailable
from production_server import production_handler, DisabledAI


class PageChunkTests(PageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.write_archive([(f'{p:03}.png', self.first) for p in range(145)])
        self.scan(); self.item = self.ids['comic.cbz']
        self.pages.refresh(self.item)
        first = self.pages.list(self.item, limit=100)
        self.rev = first['source_revision']
        tail = self.pages.list(self.item, offset=100, limit=100, revision=self.rev)
        self.ids_in_order = [p['page_id'] for p in first['pages']+tail['pages']]
        self.scope = {'root_ids':[self.root]}
        self.encoder = Encoder(); self.ai = AISearch(self.catalog, self.encoder)
        self.addCleanup(lambda:self.ai.close())
        self.profile = self.ai.profile.key

    def start(self, count=33):
        return start_chunked(self.ai, self.item, self.ids_in_order[:count], self.rev, self.scope, self.profile)

    def finish(self, expected='complete'):
        self.ai.worker.join(20)
        self.assertFalse(self.ai.worker.is_alive())
        result = self.ai.status()
        self.assertEqual(result['state'], expected, result)
        return result

    def stored(self):
        with self.ai.store.connect() as db:
            return list(db.execute('SELECT page,vector FROM ai_page_vectors WHERE item_id=? ORDER BY page', (self.item,)))

    def cancel_after_first(self):
        self.encoder.hook = lambda *args:self.ai.cancel.set() if len(self.encoder.calls)==17 else None
        self.start(); result = self.finish('cancelled'); self.encoder.hook = None
        self.assertEqual((result['indexed'], result['chunks_completed'], len(self.stored())), (16, 1, 16))
        return result

    def test_cpu_plan_skips_ready_pages_caps_128_and_never_changes_job_or_sources(self):
        before = (self.archive.read_bytes(), self.archive.stat().st_mtime_ns)
        self.ai.pages.start(self.item, self.ids_in_order[:3], self.rev, self.scope); self.finish()
        state = self.ai.store.state(); calls = list(self.encoder.calls)
        class TimedGuard:
            def __enter__(inner):
                if not guard.acquire(timeout=2):
                    raise AssertionError('AI guard nested or lock order deadlock')
            def __exit__(inner, *args):
                guard.release()
        guard = self.ai.guard
        with patch.object(self.ai, 'guard', TimedGuard()):
            plan = plan_chunked(self.ai, self.item, self.rev, self.scope, 128, self.profile)
        self.assertEqual((plan['total_gap_pages'], plan['chunk_size'], len(plan['chunks'])), (128, 16, 8))
        self.assertEqual(plan['page_ids'], self.ids_in_order[3:131])
        self.assertEqual(plan['chunks'][0], {'start':3, 'count':16})
        self.assertEqual((self.ai.store.state(), self.encoder.calls), (state, calls))
        self.assertEqual(before, (self.archive.read_bytes(), self.archive.stat().st_mtime_ns))

    def test_real_128_page_ceiling_publishes_eight_chunks_and_preserves_manual_data(self):
        self.catalog.update([self.item], {'tags':['keep'], 'shelf':'manual', 'favorite':True})
        before = (self.archive.read_bytes(), self.archive.stat().st_mtime_ns)
        self.start(128); result = self.finish()
        self.assertEqual((result['indexed'], result['chunks_completed'], result['chunks_total']), (128, 8, 8))
        self.assertEqual(len(self.encoder.calls), 128)
        self.assertEqual([p for p, _ in self.stored()], list(range(128)))
        self.assertEqual(self.catalog.get(self.item)['tags'], ['keep'])
        self.assertEqual(self.catalog.get(self.item)['shelf'], 'manual')
        self.assertTrue(self.catalog.get(self.item)['favorite'])
        self.assertEqual(before, (self.archive.read_bytes(), self.archive.stat().st_mtime_ns))
        plan = plan_chunked(self.ai, self.item, self.rev, self.scope, 64, self.profile)
        self.assertEqual((plan['total_gap_pages'], plan['page_ids']), (17, self.ids_in_order[128:]))

    def test_cancel_and_restart_resume_fixed_selection_reuses_durable_chunk(self):
        result = self.cancel_after_first(); job = result['job_id']; original = self.stored()
        self.ai.close(); self.encoder = Encoder(); self.ai = AISearch(self.catalog, self.encoder)
        self.assertEqual(self.encoder.calls, [])
        self.assertEqual(self.ai.status()['state'], 'cancelled')
        resume_chunked(self.ai, job, self.scope, self.profile); result = self.finish()
        self.assertEqual((result['indexed'], result['reused'], result['resumed_from']), (33, 16, job))
        self.assertEqual(len(self.encoder.calls), 17)
        self.assertEqual(self.stored()[:16], original)
        with self.assertRaises(ValueError):
            resume_chunked(self.ai, result['job_id'], self.scope, self.profile)

    def test_crash_interrupted_state_is_persistent_but_never_auto_started(self):
        result = self.cancel_after_first()
        self.ai.close(); self.ai.store.save_state({**result, 'state':'running'})
        self.encoder = Encoder(); self.ai = AISearch(self.catalog, self.encoder)
        state = self.ai.status()
        self.assertEqual((state['state'], state['job_id']), ('interrupted', result['job_id']))
        self.assertEqual(self.encoder.calls, [])
        self.assertFalse(self.ai.worker and self.ai.worker.is_alive())
        resume_chunked(self.ai, state['job_id'], self.scope, self.profile); self.finish()
        self.assertEqual(len(self.encoder.calls), 17)

    def test_resume_rejects_profile_scope_stale_source_and_replaced_job(self):
        state = self.cancel_after_first(); before = self.stored(); calls = len(self.encoder.calls)
        for scope, profile in ((self.scope, 'other'), ({'root_ids':[self.root, self.bookroot]}, self.profile)):
            with self.assertRaises(ValueError):
                resume_chunked(self.ai, state['job_id'], scope, profile)
        with self.assertRaises(KeyError):
            resume_chunked(self.ai, 'a'*32, self.scope, self.profile)
        self.write_archive([(f'{p:03}.png', self.second) for p in range(145)])
        with self.assertRaises(ReaderChanged):
            resume_chunked(self.ai, state['job_id'], self.scope, self.profile)
        self.assertEqual((self.stored(), len(self.encoder.calls)), (before, calls))
        self.ai.store.save_state({'job':'other', 'job_id':state['job_id'], 'state':'cancelled'})
        with self.assertRaises(KeyError):
            resume_chunked(self.ai, state['job_id'], self.scope, self.profile)

    def test_source_exclusion_between_chunks_keeps_completed_and_never_infers_next(self):
        original = self.ai.pages._publish_range
        def publish(*args):
            original(*args)
            self.catalog.set_excludes(self.root, ['*.cbz'])
        with patch.object(self.ai.pages, '_publish_range', side_effect=publish):
            self.start(); result = self.finish('failed')
        self.assertEqual((result['indexed'], result['chunks_completed'], len(self.encoder.calls)), (16, 1, 16))
        self.assertEqual(len(self.stored()), 16)
        with self.assertRaises(KeyError):
            resume_chunked(self.ai, result['job_id'], self.scope, self.profile)

    def test_failed_partial_chunk_stays_invisible_and_retry_reuses_first(self):
        original = self.ai.pages.index.input
        def read(*args):
            if len(self.encoder.calls)==17:
                raise PreviewUnavailable('generated fixture failure')
            return original(*args)
        with patch.object(self.ai.pages.index, 'input', side_effect=read):
            self.start(); result = self.finish('failed')
        self.assertEqual((result['indexed'], result['chunks_completed'], len(self.stored())), (16, 1, 16))
        before = len(self.encoder.calls)
        resume_chunked(self.ai, result['job_id'], self.scope, self.profile); result = self.finish()
        self.assertEqual((result['reused'], len(self.encoder.calls)-before), (16, 17))

    def test_strict_limits_profile_and_empty_scope_never_start_job(self):
        state = self.ai.store.state()
        for ids in ([], self.ids_in_order[:129], self.ids_in_order[:2]*2, [None], ['bad']):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                start_chunked(self.ai, self.item, ids, self.rev, self.scope, self.profile)
        for maximum in (0, 129, True, 1.5):
            with self.assertRaises(ValueError):
                plan_chunked(self.ai, self.item, self.rev, self.scope, maximum, self.profile)
        for profile in (None, 'other'):
            with self.assertRaises(ValueError):
                start_chunked(self.ai, self.item, self.ids_in_order[:2], self.rev, self.scope, profile)
        with self.assertRaises(KeyError):
            start_chunked(self.ai, self.item, self.ids_in_order[:2], self.rev, {'root_ids':[]}, self.profile)
        with self.assertRaises(ValueError):
            start_chunked(self.ai, self.item, self.ids_in_order[:2], self.rev, None, self.profile)
        self.assertEqual((self.encoder.calls, self.ai.store.state()), ([], state))

    def test_worker_busy_and_caller_mutation_cannot_change_saved_selection(self):
        ids = self.ids_in_order[:33]; scope = copy.deepcopy(self.scope)
        self.ai.inference.acquire()
        try:
            with patch.object(self.ai, 'status', side_effect=AssertionError('Use detached initial snapshot')):
                initial = start_chunked(self.ai, self.item, ids, self.rev, scope, self.profile)
            initial['page_ids'].clear(); initial['scope']['root_ids'].clear()
            ids.clear(); scope['root_ids'].clear()
            with self.assertRaises(AIBusy):
                self.start()
            with self.assertRaises(AIBusy):
                self.ai.pages.start(self.item, self.ids_in_order[:1], self.rev, self.scope)
            with self.assertRaises(AIBusy):
                self.ai.start(scope=self.scope)
        finally:
            self.ai.inference.release()
        result = self.finish()
        self.assertEqual((len(result['page_ids']), result['scope']['root_ids']), (33, [self.root]))

    def test_legacy_missing_plan_and_corrupt_resume_record_fail_closed(self):
        state = self.cancel_after_first(); before = self.stored(); calls = len(self.encoder.calls)
        for field in ('page_ids', 'profile', 'chunk_size'):
            bad = copy.deepcopy(state); bad.pop(field)
            self.ai.store.save_state(bad)
            with self.assertRaises(ValueError):
                resume_chunked(self.ai, state['job_id'], self.scope, self.profile)
        self.assertEqual((self.stored(), len(self.encoder.calls)), (before, calls))

    def test_sparse_gap_ranges_are_flattened_into_the_reported_atomic_chunk_count(self):
        self.ai.pages.start(self.item, [self.ids_in_order[p] for p in (0, 2, 4)], self.rev, self.scope)
        self.finish()
        plan = plan_chunked(self.ai, self.item, self.rev, self.scope, 16, self.profile)
        self.assertEqual((len(plan['chunks']), plan['chunks_total'], len(plan['page_ids'])), (3, 1, 16))
        start_chunked(self.ai, self.item, plan['page_ids'], self.rev, self.scope, self.profile)
        result = self.finish()
        self.assertEqual((result['indexed'], result['chunks_completed'], len(self.stored())), (16, 1, 19))

    def test_job_replacement_between_resume_read_and_start_cannot_overwrite_new_job(self):
        state = self.cancel_after_first(); calls = len(self.encoder.calls)
        replacement = {**state, 'job_id':'a'*32}
        def interleave(*args, **kwargs):
            self.ai.store.save_state(replacement)
            return start_chunked(*args, **kwargs)
        with patch('page_chunks.start_chunked', side_effect=interleave):
            with self.assertRaises(ValueError):
                resume_chunked(self.ai, state['job_id'], self.scope, self.profile)
        self.assertEqual(self.ai.store.state(), replacement)
        self.assertEqual(len(self.encoder.calls), calls)

    def server(self, ai=None):
        server = ThreadingHTTPServer(('127.0.0.1', 0), production_handler(self.catalog, 'secret', ai=self.ai if ai is None else ai))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        def stop():
            server.shutdown(); thread.join(5); server.server_close()
        self.addCleanup(stop)
        def post(route, body, auth='secret', origin=None):
            address = f'http://127.0.0.1:{server.server_port}'
            req = urllib.request.Request(address+'/api/library/ai/pages/'+route,
                data=json.dumps(body).encode(), headers={'X-Aredoko-Token':auth,
                    'Origin':address if origin is None else origin, 'Content-Type':'application/json'})
            try:
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=10) as res:
                    return res.status, json.load(res)
            except urllib.error.HTTPError as ex:
                with ex:
                    return ex.code, json.load(ex)
        return post

    def test_http_strict_auth_cpu_plan_cancel_ownership_resume_and_missing_job(self):
        post = self.server()
        plan_body = {'item_id':self.item, 'revision':self.rev, 'scope':self.scope, 'profile':self.profile, 'max_pages':33}
        self.assertEqual(post('chunked/plan', plan_body, auth='bad')[0], 403)
        self.assertEqual(post('chunked/plan', plan_body, origin='https://example.invalid')[0], 403)
        for bad in (dict(plan_body, extra=True), {k:v for k,v in plan_body.items() if k!='profile'},
                    dict(plan_body, max_pages=True), dict(plan_body, profile=None), dict(plan_body, item_id=True)):
            self.assertEqual(post('chunked/plan', bad)[0], 400)
        code, plan = post('chunked/plan', plan_body)
        self.assertEqual((code, plan['total_gap_pages'], len(self.encoder.calls)), (200, 33, 0))
        body = {k:v for k,v in plan_body.items() if k!='max_pages'}; body['page_ids'] = plan['page_ids']
        self.ai.inference.acquire()
        try:
            code, initial = post('chunked', body); self.assertEqual(code, 200)
            self.assertEqual(post('chunked', body)[0], 409)
            self.assertFalse(post('cancel', {'job_id':'a'*32})[1]['cancel_requested'])
            self.assertTrue(post('cancel', {'job_id':initial['job_id']})[1]['cancel_requested'])
        finally:
            self.ai.inference.release()
        self.finish('cancelled')
        request = {'job_id':initial['job_id'], 'scope':self.scope, 'profile':self.profile}
        self.assertEqual(post('chunked/resume', request)[0], 200); self.finish()
        self.assertEqual(post('chunked/resume', dict(request, job_id='a'*32))[0], 404)
        self.assertEqual(post('chunked/resume', {k:v for k,v in request.items() if k!='scope'})[0], 400)
        self.write_archive([('new.png', self.second)])
        self.assertEqual(post('chunked', body)[0], 409)

    def test_plan_rechecks_scope_after_coverage_before_returning_page_ids(self):
        original = self.ai.pages.next_gaps
        before = self.ai.store.state()
        def gaps(*args, **kwargs):
            result = original(*args, **kwargs)
            self.catalog.unregister_root(self.root)
            return result
        with patch.object(self.ai.pages, 'next_gaps', side_effect=gaps):
            with self.assertRaises((ValueError, KeyError)):
                plan_chunked(self.ai, self.item, self.rev, self.scope, 33, self.profile)
        self.assertEqual((self.encoder.calls, self.ai.store.state()), ([], before))

    def test_plan_rechecks_physical_revision_after_coverage(self):
        original = self.ai.pages.next_gaps
        def gaps(*args, **kwargs):
            result = original(*args, **kwargs)
            self.write_archive([('new.png', self.second)])
            return result
        with patch.object(self.ai.pages, 'next_gaps', side_effect=gaps):
            with self.assertRaises(ReaderChanged):
                plan_chunked(self.ai, self.item, self.rev, self.scope, 33, self.profile)
        self.assertEqual(self.encoder.calls, [])

    def test_http_unconfigured_model_never_starts_and_profile_plan_is_cpu_only(self):
        post = self.server(DisabledAI())
        body = {'item_id':self.item, 'revision':self.rev, 'scope':self.scope, 'profile':self.profile, 'max_pages':16}
        self.assertEqual(post('chunked/plan', body)[0], 503)
        self.encoder.available = False
        plan = plan_chunked(self.ai, self.item, self.rev, self.scope, 33, self.profile)
        self.assertFalse(plan['available'])
        self.assertEqual(plan['total_gap_pages'], 33)
        self.assertEqual(self.encoder.calls, [])


if __name__ == '__main__':
    unittest.main()
