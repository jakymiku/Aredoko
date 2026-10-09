import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from catalog import Catalog
from server import handler_for


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.catalog = Catalog(Path(self.temp.name) / 'demo.sqlite')
        self.catalog.seed(250)

    def tearDown(self):
        self.temp.cleanup()

    def test_pagination_and_literal_search(self):
        first = self.catalog.search()
        second = self.catalog.search(page=1)
        self.assertEqual(first['total'], 250)
        self.assertEqual(len(first['items']), 60)
        self.assertFalse({x['id'] for x in first['items']} & {x['id'] for x in second['items']})
        self.assertEqual(self.catalog.search(query='%')['total'], 0)
        self.assertGreater(self.catalog.search(query='雨の街')['total'], 0)
        self.assertTrue(all(i['kind'] == 'book' for i in self.catalog.search(kind='book')['items']))

    def test_updates_survive_reopen_and_reseed(self):
        self.catalog.update([1, 2], {'tags': ['自分のタグ'], 'favorite': True, 'shelf': '制作'})
        reopened = Catalog(self.catalog.path)
        reopened.seed(50000)
        self.assertEqual(reopened.get(1)['tags'], ['自分のタグ'])
        self.assertEqual(reopened.search(view='favorites')['total'], 2)
        self.assertEqual(reopened.stats()['total'], 250)

    def test_bad_batch_is_atomic(self):
        with self.assertRaises(KeyError):
            self.catalog.update([1, 999], {'favorite': True})
        self.assertFalse(self.catalog.get(1)['favorite'])
        with self.assertRaises(ValueError):
            self.catalog.update([1], {'title': 'not editable'})

    def test_filters_and_validation_do_not_mutate_records(self):
        self.catalog.update([1], {'tags': ['雨の街', '雨の街', ' 映画 '], 'favorite': True, 'shelf': '閲覧'})
        self.assertEqual(self.catalog.get(1)['tags'], ['雨の街', '映画'])
        self.assertEqual(self.catalog.search(view='favorites')['total'], 1)
        self.assertEqual(self.catalog.search(view='shelf')['total'], 1)
        self.assertEqual(self.catalog.search(view='unreviewed')['total'], 250)
        self.assertEqual(self.catalog.search(query='_')['total'], 0)
        for updates in ({'tags': ['x' * 61]}, {'shelf': 'x' * 81},
                        {'favorite': 1}, {'reviewed': 'yes'}, {'tags': 'not-list'}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                self.catalog.update([1], updates)
        self.assertTrue(self.catalog.get(1)['favorite'])
        self.assertEqual(self.catalog.get(1)['shelf'], '閲覧')

    def test_search_rejects_invalid_queries(self):
        for kwargs in ({'kind': 'other'}, {'view': 'missing'}, {'page': -1},
                       {'limit': 0}, {'limit': 121}, {'query': 'x' * 301}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.catalog.search(**kwargs)

    def test_http_session_boundary(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.catalog, 'test-token'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base + '/api/items') as response:
                self.assertEqual(json.load(response)['total'], 250)
            body = json.dumps({'ids': [1], 'changes': {'reviewed': True}}).encode()
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base + '/api/items/update', data=body))
            self.assertEqual(error.exception.code, 403)
            error.exception.close()
            req = Request(base + '/api/items/update', data=body, headers={
                'Content-Type': 'application/json', 'Origin': base, 'X-Aredoko-Token': 'test-token'})
            with urlopen(req) as response:
                self.assertEqual(json.load(response)['updated'], 1)
            self.assertTrue(self.catalog.get(1)['reviewed'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
