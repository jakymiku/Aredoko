"""Invalid numeric inputs return validation errors before SQLite or mutation."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from catalog import Catalog
from production import ProductionCatalog
from production_server import production_handler, DisabledAI
from server import handler_for

MAX_ID = 9223372036854775807


class RequestIdTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.media = self.base / 'generated'; self.media.mkdir()
        self.source = self.media / 'fixture.png'; self.source.write_bytes(b'generated placeholder')
        self.catalog = ProductionCatalog(self.base / 'production.sqlite'); self.addCleanup(self.catalog.close)
        self.root = self.catalog.add_root(str(self.media)); self.catalog.index.scan(self.root); self.catalog.sync_index()
        self.item = self.catalog.search()['items'][0]['id']
        self.catalog.update([self.item], {'tags': ['保全'], 'shelf': '保存棚'})
        self.demo = Catalog(self.base / 'demo.sqlite'); self.demo.seed(1)

    def test_item_ids_reject_overflow_boolean_zero_and_negative_atomically(self):
        for catalog, item in ((self.catalog, self.item), (self.demo, 1)):
            before = catalog.get(item)
            for bad in (True, False, 0, -1, MAX_ID + 1, 10**100, '1', None):
                with self.subTest(catalog=type(catalog).__name__, bad=bad):
                    with self.assertRaises(ValueError): catalog.get(bad)
                    with self.assertRaises(ValueError): catalog.update([item, bad], {'favorite': True})
                    self.assertEqual(catalog.get(item), before)
            with self.assertRaises(KeyError): catalog.get(MAX_ID)
            with self.assertRaises(KeyError): catalog.update([item, MAX_ID], {'favorite': True})
            self.assertEqual(catalog.get(item), before)

    def test_root_boundaries_do_not_create_jobs_or_change_exclusions(self):
        before = self.catalog.index.roots()
        state = self.catalog.scan_state()
        source = (self.source.read_bytes(), self.source.stat().st_mtime_ns)
        for bad in (True, 0, -1, MAX_ID + 1, 10**100, '1', None):
            for operation in (lambda value: self.catalog.set_excludes(value, []),
                              self.catalog.start_scan, self.catalog.index.locations,
                              self.catalog.index.scan):
                with self.subTest(bad=bad, operation=operation):
                    with self.assertRaises(ValueError): operation(bad)
        self.assertIsNone(self.catalog._worker)
        self.assertEqual(self.catalog.scan_state(), state)
        self.assertEqual(self.catalog.index.roots(), before)
        self.assertEqual((self.source.read_bytes(), self.source.stat().st_mtime_ns), source)
        self.assertEqual(self.catalog.index.locations(self.root, offset=MAX_ID)['items'], [])
        with self.assertRaises(ValueError): self.catalog.index.locations(self.root, offset=MAX_ID + 1)

    def serve(self, handler):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return f'http://127.0.0.1:{server.server_port}'

    def request(self, origin, route, body=None, token='fixture-token'):
        headers = {'X-Aredoko-Token': token, 'Origin': origin}
        data = json.dumps(body).encode() if body is not None else None
        if data is not None: headers['Content-Type'] = 'application/json'
        return urllib.request.urlopen(urllib.request.Request(origin + route, data=data, headers=headers), timeout=5)

    def expect_error(self, origin, route, body=None, status=400, token='fixture-token'):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request(origin, route, body, token)
        self.assertEqual(caught.exception.code, status)
        self.assertIn('error', json.loads(caught.exception.read())); caught.exception.close()

    def test_production_http_invalid_get_update_excludes_and_scan_return_400(self):
        origin = self.serve(production_handler(self.catalog, 'fixture-token', ai=DisabledAI()))
        before = self.catalog.get(self.item)
        for bad in (MAX_ID + 1, 10**100):
            self.expect_error(origin, f'/api/items/{bad}')
            self.expect_error(origin, '/api/items/update', {'ids': [self.item, bad], 'changes': {'favorite': True}})
            self.expect_error(origin, '/api/library/excludes', {'root_id': bad, 'patterns': []})
            self.expect_error(origin, '/api/library/scan', {'root_id': bad})
        self.expect_error(origin, '/api/items/update', {'ids': [True], 'changes': {'favorite': True}})
        self.expect_error(origin, '/api/library/scan', {'root_id': MAX_ID + 1}, status=403, token='wrong')
        self.expect_error(origin, f'/api/items/{MAX_ID}', status=404)
        self.assertEqual(self.catalog.get(self.item), before)
        self.assertEqual(self.catalog.scan_state()['state'], 'idle')
        with self.request(origin, '/api/items/update', {'ids': [self.item], 'changes': {'favorite': True}}) as response:
            self.assertEqual(json.load(response)['updated'], 1)
        with self.request(origin, f'/api/items/{self.item}') as response:
            saved = json.load(response)
            self.assertTrue(saved['favorite']); self.assertEqual(saved['tags'], ['保全'])

    def test_demo_http_uses_the_same_item_boundary_and_valid_updates_still_work(self):
        origin = self.serve(handler_for(self.demo, 'fixture-token'))
        self.expect_error(origin, f'/api/items/{MAX_ID + 1}')
        self.expect_error(origin, '/api/items/update', {'ids': [1, MAX_ID + 1], 'changes': {'favorite': True}})
        self.assertFalse(self.demo.get(1)['favorite'])
        with self.request(origin, '/api/items/update', {'ids': [1], 'changes': {'favorite': True}}) as response:
            self.assertEqual(json.load(response)['updated'], 1)
        self.assertTrue(self.demo.get(1)['favorite'])


if __name__ == '__main__': unittest.main()
