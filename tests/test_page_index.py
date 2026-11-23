"""Generated-only page identities, persistence, stale evidence and HTTP contracts."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import warnings
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
sys.path.insert(0, str(ROOT / 'tools'))
from create_preview_fixture import png
from page_index import PageIndex
from previews import PreviewReader, PreviewUnavailable, ReaderChanged, PreviewBusyError
from production import ProductionCatalog, ScanBusyError
from production_server import production_handler, DisabledAI


class PageFixture:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.loose = self.base / 'loose'
        self.loose.mkdir()
        self.books = self.base / 'books'
        self.folder = self.books / 'comic'
        self.folder.mkdir(parents=True)
        self.first = png(color=(20, 30, 40))
        self.second = png(color=(90, 80, 70))
        self.image = self.loose / 'asset.png'
        self.image.write_bytes(self.first)
        self.archive = self.loose / 'comic.cbz'
        self.write_archive([('2.png', self.second), ('1.png', self.first)])
        (self.folder / '2.png').write_bytes(self.second)
        (self.folder / '1.png').write_bytes(self.first)
        self.catalog = ProductionCatalog(self.base / 'catalog.sqlite')
        self.addCleanup(self.catalog.close)
        self.root = self.catalog.add_root(str(self.loose))
        self.bookroot = self.catalog.add_root(str(self.books), folder_books=True)
        self.scan()
        self.reader = PreviewReader(self.catalog)
        self.pages = PageIndex(self.catalog, self.reader)

    def write_archive(self, entries):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(self.archive, 'w') as archive:
                for name, data in entries:
                    archive.writestr(name, data)

    def scan(self):
        for root in (self.root, self.bookroot):
            self.catalog.index.scan(root)
        self.catalog.sync_index()
        rows = self.catalog.search()['items']
        self.ids = {row['relative_path']: row['id'] for row in rows}

    def counts(self):
        with self.catalog.connect() as db:
            return tuple(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                         for table in ('page_snapshots', 'page_entries', 'page_heads'))


class PageIndexTests(PageFixture, unittest.TestCase):
    def test_image_archive_and_folder_roundtrip_preserve_sources_and_annotations(self):
        files = [self.image, self.archive, *self.folder.iterdir()]
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files}
        for relative, kind, expected in [('asset.png', 'image', [self.first]),
                ('comic.cbz', 'archive', [self.first, self.second]), ('comic/', 'folder', [self.first, self.second])]:
            item = self.ids[relative]
            self.catalog.update([item], {'tags': ['手動'], 'favorite': True})
            self.assertEqual(self.pages.list(item)['source_state'], 'unindexed')
            result = self.pages.refresh(item)
            self.assertEqual(result['source_kind'], kind)
            listing = self.pages.list(item)
            self.assertEqual(listing['source_state'], 'current')
            self.assertEqual(listing['page_count'], len(expected))
            self.assertEqual(listing['source_revision'], self.reader.tag_source(item)['revision'])
            for entry, data in zip(listing['pages'], expected):
                payload = self.pages.input(item, entry['page_id'], listing['source_revision'])
                self.assertEqual(payload['data'], data)
                self.assertEqual(payload['source']['page_id'], entry['page_id'])
                self.assertEqual(payload['source']['page'], entry['page'])
                self.assertNotIn('path', payload['source'])
            self.assertEqual(self.catalog.get(item)['tags'], ['手動'])
            self.assertTrue(self.catalog.get(item)['favorite'])
        self.assertEqual({p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files}, before)

    def test_metadata_index_does_not_decompress_archive_images(self):
        with patch.object(zipfile.ZipFile, 'open', side_effect=AssertionError('pixels requested')):
            self.pages.refresh(self.ids['comic.cbz'])
            self.assertEqual(self.pages.list(self.ids['comic.cbz'])['page_count'], 2)

    def test_snapshot_reuse_and_restart_keep_page_ids(self):
        item = self.ids['comic/']
        self.assertFalse(self.pages.refresh(item)['reused'])
        first = self.pages.list(item)
        counts = self.counts()
        reopened = PageIndex(self.catalog)
        self.assertTrue(reopened.refresh(item)['reused'])
        self.assertEqual(reopened.list(item), first)
        self.assertEqual(self.counts(), counts)

    def test_inserted_page_keeps_ids_but_old_revision_cannot_fetch_new_page_numbers(self):
        item = self.ids['comic/']
        self.pages.refresh(item)
        old = self.pages.list(item)
        (self.folder / '0.png').write_bytes(png(color=(5, 6, 7)))
        self.assertEqual(self.pages.list(item)['source_state'], 'stale')
        with self.assertRaises(ReaderChanged):
            self.pages.input(item, old['pages'][0]['page_id'], old['source_revision'])
        self.scan()
        self.pages.refresh(item)
        new = self.pages.list(item)
        self.assertEqual([p['page_id'] for p in new['pages'][1:]], [p['page_id'] for p in old['pages']])
        self.assertNotEqual(new['source_revision'], old['source_revision'])
        with self.assertRaises(ReaderChanged):
            self.pages.list(item, offset=1, revision=old['source_revision'])
        with self.assertRaises(ReaderChanged):
            self.pages.input(item, old['pages'][0]['page_id'], old['source_revision'])
        self.assertEqual(self.pages.input(item, old['pages'][0]['page_id'], new['source_revision'])['data'], self.first)

    def test_duplicate_archive_names_have_distinct_ids_and_never_extract(self):
        self.write_archive([('same.png', self.first), ('same.png', self.second), ('../../outside.png', self.first)])
        self.scan()
        item = self.ids['comic.cbz']
        self.pages.refresh(item)
        listing = self.pages.list(item)
        self.assertEqual(len({p['page_id'] for p in listing['pages']}), 3)
        data = [self.pages.input(item, p['page_id'], listing['source_revision'])['data'] for p in listing['pages']]
        self.assertEqual(data, [self.first, self.first, self.second])
        self.assertNotIn('outside', json.dumps(listing))
        self.assertFalse((self.base / 'outside.png').exists())

    def test_archive_reordering_keeps_ids_for_distinct_names(self):
        item = self.ids['comic.cbz']
        self.pages.refresh(item)
        old = self.pages.list(item)
        self.write_archive([('1.png', self.first), ('2.png', self.second)])
        self.scan()
        self.pages.refresh(item)
        self.assertEqual([p['page_id'] for p in self.pages.list(item)['pages']], [p['page_id'] for p in old['pages']])

    def test_changed_source_rolls_back_snapshot_and_previous_head(self):
        item = self.ids['comic/']
        self.pages.refresh(item)
        old = self.pages.list(item)
        counts = self.counts()
        (self.folder / '3.png').write_bytes(self.first)
        self.scan()
        original = self.reader.tag_source

        def change_before_commit(value):
            (self.folder / '4.png').write_bytes(self.first)
            return original(value)

        with patch.object(self.reader, 'tag_source', side_effect=change_before_commit):
            with self.assertRaises(ReaderChanged):
                self.pages.refresh(item)
        self.assertEqual(self.counts(), counts)
        self.assertEqual(self.pages.list(item)['source_revision'], old['source_revision'])

    def test_cancelled_snapshot_has_no_partial_rows(self):
        calls = 0

        def cancel():
            nonlocal calls
            calls += 1
            return calls >= 4

        with self.assertRaises(InterruptedError):
            self.pages.refresh(self.ids['comic/'], cancelled=cancel)
        self.assertEqual(self.counts(), (0, 0, 0))
        self.pages.refresh(self.ids['comic/'])
        self.assertEqual(self.counts(), (1, 2, 1))

    def test_unavailable_busy_excluded_and_unregistered_sources_are_distinct(self):
        item = self.ids['asset.png']
        self.pages.refresh(item)
        with patch.object(self.reader, 'tag_source', side_effect=PreviewBusyError()):
            self.assertEqual(self.pages.list(item)['source_state'], 'unverified')
        self.image.unlink()
        self.assertEqual(self.pages.list(item)['source_state'], 'unavailable')
        self.catalog.set_excludes(self.root, ['*.png'])
        with self.assertRaises(KeyError):
            self.pages.list(item)
        self.catalog.set_excludes(self.root, [])
        self.catalog.unregister_root(self.root)
        with self.assertRaises(KeyError):
            self.pages.list(item)

    def test_bad_archive_refresh_preserves_existing_snapshot(self):
        item = self.ids['comic.cbz']
        self.pages.refresh(item)
        counts = self.counts()
        self.archive.write_bytes(b'not a zip')
        self.scan()
        with self.assertRaises(PreviewUnavailable):
            self.pages.refresh(item)
        self.assertEqual(self.counts(), counts)

    def test_bounds_and_cross_item_page_ids_are_rejected(self):
        item = self.ids['comic/']
        for bad in (True, 0, -1, 2**63, '1'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.pages.refresh(bad)
        for args in ({'offset': True}, {'offset': -1}, {'offset': 10001}, {'limit': 0}, {'limit': 101},
                     {'limit': True}, {'offset': 1}, {'revision': 'g' * 64}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.pages.list(item, **args)
        self.pages.refresh(item)
        self.pages.refresh(self.ids['asset.png'])
        foreign = self.pages.list(self.ids['asset.png'])['pages'][0]['page_id']
        revision = self.pages.list(item)['source_revision']
        with self.assertRaises(KeyError):
            self.pages.input(item, foreign, revision)
        self.assertEqual(len(self.pages.list(item, offset=1, limit=1, revision=revision)['pages']), 1)

    def test_running_scan_blocks_snapshot_write(self):
        with patch.object(self.catalog, '_require_idle', side_effect=ScanBusyError('busy')):
            with self.assertRaises(ScanBusyError):
                self.pages.refresh(self.ids['comic/'])
        self.assertEqual(self.counts(), (0, 0, 0))


class PageHTTPTests(PageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), production_handler(self.catalog, 'test', ai=DisabledAI()))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, route, body=None, token='test', origin=None):
        request = urllib.request.Request(self.origin + route,
            None if body is None else json.dumps(body).encode(),
            headers={'X-Aredoko-Token': token, 'Origin': origin or self.origin, 'Content-Type': 'application/json'})
        try:
            response = self.opener.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            return response.code, json.loads(raw) if response.headers.get_content_type() == 'application/json' else raw

    def test_http_index_paging_evidence_and_source_change(self):
        item = self.ids['comic/']
        self.assertEqual(self.call('/api/library/page-index', {'item_id': item})[0], 200)
        status, listing = self.call(f'/api/library/page-index/{item}?limit=1')
        self.assertEqual((status, len(listing['pages'])), (200, 1))
        entry = listing['pages'][0]
        route = f'/api/library/page-index/{item}/pages/{entry["page_id"]}?revision={listing["source_revision"]}'
        self.assertEqual(self.call(route), (200, self.first))
        (self.folder / '0.png').write_bytes(self.second)
        self.assertEqual(self.call(route)[0], 409)
        self.assertEqual(self.call(f'/api/library/page-index/{item}')[1]['source_state'], 'stale')

    def test_http_auth_and_malformed_requests(self):
        item = self.ids['asset.png']
        self.assertEqual(self.call('/api/library/page-index', {'item_id': item}, token='bad')[0], 403)
        self.assertEqual(self.call('/api/library/page-index', {'item_id': item}, origin='https://example.invalid')[0], 403)
        self.assertEqual(self.call(f'/api/library/page-index/{item}', token='bad')[0], 403)
        for route in ('0', '01', '9' * 30, f'{item}?offset=1', f'{item}?limit=2&limit=3',
                      f'{item}?limit=0', f'{item}?path=elsewhere', f'{item}/pages/not-an-id', f'{item}?revision=bad'):
            with self.subTest(route=route):
                self.assertEqual(self.call('/api/library/page-index/' + route)[0], 400)
        for body in ({'item_id': True}, {'item_id': 2**63}, {'item_id': item, 'path': 'x'}, {}):
            with self.subTest(body=body):
                self.assertEqual(self.call('/api/library/page-index', body)[0], 400)


if __name__ == '__main__':
    unittest.main()
