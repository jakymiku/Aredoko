"""Regression tests for backend audit fixes (Build 67 follow-up)."""
from dataclasses import replace
from pathlib import Path
import io
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'app'))

from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch
from previews import PreviewReader, PreviewUnavailable
from production import ProductionCatalog
from result_sessions import ResultCapacity, ResultSessions
from storage_backup import RecoveryError, _configuration


class StubEncoder:
    profile = replace(DEFAULT_PROFILE, dimension=3)
    available = True
    resident = False

    def encode(self, operation, value):
        return [1.0, 0.0, 0.0]

    def close(self):
        pass


class BackendAuditFixTests(unittest.TestCase):
    def test_viewer_settings_backup_accepts_language_and_rejects_invalid(self):
        valid = json.dumps({
            'version': 1,
            'wheel_up_advances': False,
            'library_item_scale': 100,
            'library_view': 'list',
            'theme': 'system',
            'enlarge_small_images': False,
            'always_show_controls': False,
            'loop_book_pages': False,
            'double_click_viewer': 'internal',
            'ai_setup_features': 3,
            'open_details_on_click': False,
            'language': 'ja',
        }).encode('utf-8')
        _configuration('viewer_settings', valid)

        for lang in ('system', 'ja', 'en'):
            payload = json.dumps({'version': 1, 'wheel_up_advances': True, 'language': lang}).encode('utf-8')
            _configuration('viewer_settings', payload)

        invalid = json.dumps({'version': 1, 'wheel_up_advances': False, 'language': 'fr'}).encode('utf-8')
        with self.assertRaises(RecoveryError):
            _configuration('viewer_settings', invalid)

    def test_library_index_respects_writer_fence_pause(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cat = ProductionCatalog(base / 'catalog.sqlite')
            self.addCleanup(cat.close)
            media = base / 'media'
            media.mkdir()
            (media / 'sample.png').write_bytes(b'png')
            entered = threading.Event()
            done = threading.Event()

            def do_add():
                entered.set()
                cat.index.add_root(str(media))
                done.set()

            t = threading.Thread(target=do_add)
            with cat.writer_fence.pause():
                t.start()
                self.assertTrue(entered.wait(2))
                self.assertFalse(done.wait(0.15))
            t.join(3)
            self.assertFalse(t.is_alive())
            self.assertTrue(done.is_set())

    def test_single_root_query_does_not_use_cross_join(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cat = ProductionCatalog(base / 'catalog.sqlite')
            self.addCleanup(cat.close)
            d1 = base / 'r1'; d1.mkdir()
            d2 = base / 'r2'; d2.mkdir()
            r1 = cat.add_root(str(d1))
            r2 = cat.add_root(str(d2))
            ai = AISearch(cat, StubEncoder(), base / 'vec.sqlite')
            self.addCleanup(ai.close)
            _, join_single, _, _ = ai._row_query_parts(scope={'root_ids': [r1]})
            _, join_multi, _, _ = ai._row_query_parts(scope={'root_ids': [r1, r2]})
            self.assertNotIn('CROSS JOIN', join_single)
            self.assertIn('CROSS JOIN', join_multi)

    def test_continuation_all_pages_selects_cover_only_books_and_counts_page_failure_as_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cat = ProductionCatalog(base / 'catalog.sqlite')
            self.addCleanup(cat.close)
            media = base / 'media'; media.mkdir()
            cbz = media / 'book1.cbz'
            with zipfile.ZipFile(cbz, 'w') as zf:
                zf.writestr('001.png', b'\x89PNG\r\n\x1a\n' + b'\x00' * 32)
            root = cat.add_root(str(media))
            cat.index.scan(root)
            cat.sync_index()
            ai = AISearch(cat, StubEncoder(), base / 'vec.sqlite')
            self.addCleanup(ai.close)

            # Build with cover_only first
            with patch.object(ai.previews, 'read', return_value=(b'img', 'image/png')):
                ai.start(scope={'book_pages': 'cover_only'})
                ai.worker.join(10)
            self.assertEqual(ai.status()['state'], 'complete')
            self.assertEqual(ai.coverage(scope={'book_pages': 'cover_only'})['coverage_status'], 'ready')

            # Switch to all_pages: continuation must select the book
            plan = ai.continuation.prepare(scope={'book_pages': 'all_pages'}, profile=ai.profile.key)
            self.assertEqual(plan['selected_total'], 1)

            # When index_all_pages fails with PreviewUnavailable, it must be counted as skipped (not reused)
            with patch.object(ai.pages, 'index_all_pages', side_effect=PreviewUnavailable('corrupt')):
                ai.start(scope={'book_pages': 'all_pages'})
                ai.worker.join(10)
            st = ai.status()
            self.assertEqual(st['skipped'], 1)
            self.assertEqual(st['reused'], 0)

    def test_pin_identities_converts_sqlite_error_to_result_capacity(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cat = ProductionCatalog(base / 'catalog.sqlite')
            self.addCleanup(cat.close)
            media = base / 'media'; media.mkdir()
            (media / 'a.png').write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 32)
            root = cat.add_root(str(media))
            cat.index.scan(root)
            cat.sync_index()
            sdir = base / 'sessions'; sdir.mkdir()
            sessions = ResultSessions(cat, lambda cond, consume, stop: consume(lambda page: cat.search(page=page)), parent=sdir)
            self.addCleanup(sessions.close)
            created = sessions.create('a' * 32, {'mode': 'literal', 'query': ''})
            session = sessions._get('a' * 32)
            item_id = cat.search()['items'][0]['id']
            class FailingDB:
                def __enter__(self): return self
                def __exit__(self, *args): return False
                def executemany(self, *args): raise sqlite3.OperationalError('database or disk is full')
            real_db = session.db
            session.db = FailingDB()
            try:
                with self.assertRaises(ResultCapacity):
                    session._pin_identities({item_id: {'id': item_id}}, {item_id: 'sig'})
            finally:
                session.db = real_db


if __name__ == '__main__':
    unittest.main()
