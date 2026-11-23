"""Exact confirmed-tag scope across literal, AI, similarity, page-text, and HTTP routes."""
from dataclasses import replace
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from ai_profiles import DEFAULT_PROFILE
from ai_scope import validate_scope
from ai_search import AISearch
from page_index import PageIndex
from page_text import PageTextIndex
from previews import PreviewReader
from production import ProductionCatalog
from production_server import DisabledAI, production_handler
from result_sessions import ResultSessions
from tag_candidate_search import search_candidates
from tag_suggestions import TagSuggestions


class Encoder:
    profile = replace(DEFAULT_PROFILE, dimension=4)
    available = True

    def encode(self, operation, value):
        return [1.0, 0.0, 0.0, 0.0]

    def close(self):
        pass


class TagScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.media = self.base / 'media'
        self.media.mkdir()
        buf = io.BytesIO()
        Image.new('RGB', (4, 4), 'blue').save(buf, format='PNG')
        png = buf.getvalue()
        # Note: item "背景.png" has no "背景" tag; "青空背景" is a superstring tag, not exact "背景".
        for name in ('alpha.png', '背景.png', 'beta.png', 'gamma.png'):
            (self.media / name).write_bytes(png)
        self.catalog = ProductionCatalog(self.base / 'catalog.sqlite')
        self.addCleanup(self.catalog.close)
        self.root = self.catalog.add_root(str(self.media))
        self.catalog.index.scan(self.root)
        self.catalog.sync_index()
        by_title = {r['title']: r['id'] for r in self.catalog.search()['items']}
        self.id_exact = by_title['alpha.png']
        self.id_filename_only = by_title['背景.png']
        self.id_superstring_tag = by_title['beta.png']
        self.id_space_tag = by_title['gamma.png']
        self.catalog.update([self.id_exact], {'tags': ['背景', '海']})
        self.catalog.update([self.id_superstring_tag], {'tags': ['青空背景', 'bg']})
        self.catalog.update([self.id_space_tag], {'tags': ['blue sky', '背景']})
        self.catalog.terms.upsert({'term': '背景', 'related': ['bg']})

    def test_exact_confirmed_tag_does_not_match_filename_substring_or_synonym(self):
        rows = self.catalog.search(tag='背景')['items']
        self.assertEqual({r['id'] for r in rows}, {self.id_exact, self.id_space_tag})
        space_rows = self.catalog.search(tag='blue sky')['items']
        self.assertEqual([r['id'] for r in space_rows], [self.id_space_tag])
        self.assertEqual(self.catalog.search(tag='blue')['total'], 0)
        # Normal query combines with exact tag AND-wise.
        combined = self.catalog.search(query='海', tag='背景')['items']
        self.assertEqual([r['id'] for r in combined], [self.id_exact])

    def test_pending_proposals_do_not_leak_into_confirmed_tag_filter(self):
        svc = TagSuggestions(self.catalog)
        with self.catalog.connect() as db:
            db.execute(
                "INSERT INTO tag_proposal_batches(item_id,source_revision,producer_key,producer_json,evidence_json,created_at) VALUES(?,?,?,?,?,1.0)",
                (self.id_filename_only, 'rev1', 'k1', '{"model":"m","model_revision":"r","adapter":"a","version":"1","preprocessing":"p"}', '{}'),
            )
            batch_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
            db.execute(
                "INSERT INTO tag_proposals(batch_id,tag,explanation,page,state,accepted_tag,version) VALUES(?,?,?,?,?,?,0)",
                (batch_id, '背景', 'pending ai tag', 0, 'pending', None),
            )
        rows = self.catalog.search(tag='背景')['items']
        self.assertNotIn(self.id_filename_only, {r['id'] for r in rows})
        # Pending candidate search with confirmed tag scope filters by confirmed tags, not pending tags.
        svc._source = lambda _id: {'revision': 'rev1'}
        cand = search_candidates(svc, tag='背景')
        self.assertEqual(cand['total'], 0)

    def test_ai_scope_and_search_similarity_honor_exact_tag(self):
        self.assertEqual(validate_scope({'tag': ' 背景 '})['tag'], '背景')
        ai = AISearch(self.catalog, Encoder())
        self.addCleanup(ai.close)
        ai.start(scope={'root_ids': [self.root]})
        ai.worker.join(timeout=10)
        res = ai.search('海', scope={'root_ids': [self.root], 'tag': '背景'})
        self.assertEqual({r['id'] for r in res['items']}, {self.id_exact, self.id_space_tag})
        with self.assertRaises(KeyError):
            ai.similar(self.id_exact, scope={'root_ids': [self.root], 'tag': 'blue sky'})
        sim_bg = ai.similar(self.id_exact, scope={'root_ids': [self.root], 'tag': '背景'})
        self.assertEqual([r['id'] for r in sim_bg['items']], [self.id_space_tag])

    def test_invalid_tag_rejected_and_http_items_applies_tag(self):
        for bad in ('', '   ', 'x' * 61, 123, True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.catalog.search(tag=bad)
        page_text = PageTextIndex(self.catalog, PageIndex(self.catalog, PreviewReader(self.catalog)))
        self.assertEqual(page_text.search('hello', tag='背景')['total'], 0)

        ai = DisabledAI()
        handler = production_handler(self.catalog, 'fixture', ai=ai)
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            origin = f'http://127.0.0.1:{server.server_port}'
            url = f"{origin}/api/items?tag={urllib.parse.quote('背景')}"
            data = json.loads(urllib.request.urlopen(url, timeout=5).read())
            self.assertEqual({r['id'] for r in data['items']}, {self.id_exact, self.id_space_tag})
            req = urllib.request.Request(
                f'{origin}/api/library/results/create',
                data=json.dumps({'session_id': 'a' * 32, 'conditions': {'mode': 'literal', 'query': '', 'kind': '', 'view': 'all', 'tag': '背景'}}).encode(),
                headers={'Content-Type': 'application/json', 'Origin': origin, 'X-Aredoko-Token': 'fixture'},
                method='POST',
            )
            session = json.loads(urllib.request.urlopen(req, timeout=5).read())
            self.assertEqual(session['total'], 2)
            with self.assertRaises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(f'{origin}/api/items?tag=', timeout=5)
            self.assertEqual(err.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)
            handler.results.close()
            handler.animations.close()
            handler.setup_jobs.close()


if __name__ == '__main__':
    unittest.main()
