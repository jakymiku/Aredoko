"""User-feedback contracts on generated media and isolated DBs only."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from production import ProductionCatalog
from production_server import production_handler


class LibraryFeedbackTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.media = self.base / 'media'
        (self.media / 'nested').mkdir(parents=True)
        for name in ('first.png', 'second.png', 'nested/third.png'):
            (self.media / name).write_bytes(b'generated index-only fixture')
        self.catalog = ProductionCatalog(self.base / 'catalog.sqlite')
        self.addCleanup(self.catalog.close)

    def index(self, root):
        self.catalog.index.scan(root)
        self.catalog.sync_index()
        return {i['relative_path']: i for i in self.catalog.search(root_id=root)['items']}

    def test_recursive_default_and_direct_only(self):
        root = self.catalog.add_root(str(self.media), recursive=False)
        self.assertFalse(self.catalog.index.roots()[0]['recursive'])
        self.assertEqual(set(self.index(root)), {'first.png', 'second.png'})
        self.catalog.unregister_root(root)
        self.assertEqual(self.catalog.add_root(str(self.media)), root)
        self.assertFalse(self.catalog.index.roots()[0]['recursive'])
        self.catalog.unregister_root(root)
        self.catalog.add_root(str(self.media), recursive=True)
        self.assertIn('nested/third.png', self.index(root))

    def test_recursive_restore_hides_nested_immediately_and_preserves_metadata(self):
        root = self.catalog.add_root(str(self.media))
        self.assertTrue(self.catalog.index.roots()[0]['recursive'])
        item = self.index(root)['nested/third.png']['id']
        self.catalog.update([item], {'tags': ['keep'], 'shelf': 'manual', 'favorite': True})
        self.catalog.record_view(item)
        self.catalog.unregister_root(root)
        self.catalog.add_root(str(self.media), recursive=False)
        self.assertEqual(self.catalog.search()['total'], 2)
        self.assertEqual(self.catalog.search(view='history')['total'], 0)
        self.assertEqual(set(self.index(root)), {'first.png', 'second.png'})
        self.catalog.unregister_root(root)
        self.catalog.add_root(str(self.media), recursive=True)
        restored = self.index(root)['nested/third.png']
        self.assertEqual((restored['id'], restored['tags'], restored['shelf'], restored['favorite']), (item, ['keep'], 'manual', True))
        self.assertEqual(self.catalog.search(view='history')['total'], 1)

    def test_direct_only_folder_book_keeps_root_book(self):
        root = self.catalog.add_root(str(self.media), recursive=False, folder_books=True)
        items = self.index(root)
        self.assertEqual(set(items), {'./'})
        self.assertEqual(items['./']['kind'], 'book')

    def test_recursive_migration_preserves_old_default(self):
        root = self.catalog.add_root(str(self.media))
        self.index(root)
        with self.catalog.index.connect() as db:
            db.execute('ALTER TABLE library_roots DROP COLUMN recursive')
        reopened = ProductionCatalog(self.base / 'catalog.sqlite')
        self.addCleanup(reopened.close)
        self.assertTrue(reopened.index.roots()[0]['recursive'])
        self.assertEqual(reopened.search()['total'], 3)

    def test_recursive_rejects_non_bool(self):
        for value in (0, 1, 'false', [], {}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Include subfolders'):
                self.catalog.add_root(str(self.media), recursive=value)
        self.assertEqual(self.catalog.index.roots(), [])

    def test_history_order_count_scope_restart_and_readonly(self):
        root = self.catalog.add_root(str(self.media))
        items = self.index(root)
        a, b = items['first.png']['id'], items['second.png']['id']
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.media.rglob('*.png')}
        self.catalog.update([a], {'tags': ['blue'], 'favorite': True})
        self.assertEqual(self.catalog.search(view='history')['total'], 0)
        with patch('time.time_ns', side_effect=[100, 200, 300]):
            self.catalog.record_view(a)
            self.catalog.record_view(b)
            self.catalog.record_view(a)
        self.assertEqual([i['id'] for i in self.catalog.search(view='history')['items']], [a, b])
        self.assertEqual(self.catalog.search(view='history', page=1, limit=1)['items'][0]['id'], b)
        self.assertEqual(self.catalog.search('blue', 'image', 'history', root_ids=[root])['items'][0]['id'], a)
        self.assertEqual(self.catalog.search('unknown', view='history')['total'], 0)
        with self.catalog.connect() as db:
            self.assertEqual(db.execute('SELECT open_count FROM view_history WHERE item_id=?', (a,)).fetchone()[0], 2)
        reopened = ProductionCatalog(self.base / 'catalog.sqlite')
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.search(view='history')['items'][0]['id'], a)
        self.assertEqual(reopened.get(a)['tags'], ['blue'])
        self.assertTrue(reopened.get(a)['favorite'])
        self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.media.rglob('*.png')})
        self.catalog.unregister_root(root)
        self.assertEqual(self.catalog.search(view='history')['total'], 0)
        with self.assertRaises(KeyError): self.catalog.record_view(a)
        self.catalog.add_root(str(self.media))
        self.assertEqual(self.catalog.search(view='history')['total'], 2)

    def test_history_current_exclusions_without_rescan(self):
        root = self.catalog.add_root(str(self.media))
        item = self.index(root)['nested/third.png']['id']
        self.catalog.record_view(item)
        self.catalog.set_excludes(root, ['nested/*'])
        self.assertEqual(self.catalog.search(view='history')['total'], 0)
        with self.assertRaises(KeyError): self.catalog.record_view(item)
        self.catalog.set_excludes(root, [])
        self.assertEqual(self.catalog.search(view='history')['total'], 1)

    def test_history_invalid_or_missing_never_creates_rows(self):
        root = self.catalog.add_root(str(self.media))
        item = self.index(root)['first.png']['id']
        for invalid in (True, None, 0, -1, 2**63, '1', []):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError): self.catalog.record_view(invalid)
        with self.assertRaises(KeyError): self.catalog.record_view(99999)
        (self.media / 'first.png').unlink()  # generated fixture only
        self.index(root)
        with self.assertRaises(KeyError): self.catalog.record_view(item)
        with self.catalog.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM view_history').fetchone()[0], 0)

    def test_http_history_and_registration_auth_contract(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), production_handler(self.catalog, 'fixture-token'))
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f'http://127.0.0.1:{server.server_port}'
        def post(path, data, token='fixture-token', request_origin=None):
            request = urllib.request.Request(origin+path, json.dumps(data).encode(), headers={'Content-Type':'application/json', 'Origin':request_origin or origin, 'X-Aredoko-Token':token})
            try:
                with urllib.request.urlopen(request) as response: return response.status, json.load(response)
            except urllib.error.HTTPError as error:
                with error: return error.code, json.load(error)
        self.assertEqual(post('/api/library/roots', {'path':str(self.media), 'recursive':False})[0], 400)
        self.assertEqual(post('/api/library/roots', {'path':str(self.media), 'consent':True, 'recursive':'false'})[0], 400)
        status, body = post('/api/library/roots', {'path':str(self.media), 'consent':True, 'recursive':False})
        self.assertEqual(status, 200)
        item = self.index(body['root_id'])['first.png']['id']
        endpoint = '/api/library/history'
        self.assertEqual(post(endpoint, {'item_id':item}, token='wrong')[0], 403)
        self.assertEqual(post(endpoint, {'item_id':item}, request_origin='https://example.invalid')[0], 403)
        self.assertEqual(post(endpoint, {'item_id':item, 'path':'injection'})[0], 400)
        self.assertEqual(post(endpoint, {'item_id':True})[0], 400)
        self.assertEqual(post(endpoint, {'item_id':99999})[0], 404)
        self.assertEqual(post(endpoint, {'item_id':item}), (200, {'recorded':item}))
        with urllib.request.urlopen(origin+'/api/items?view=history') as response:
            self.assertEqual(json.load(response)['items'][0]['id'], item)


if __name__ == '__main__': unittest.main()
