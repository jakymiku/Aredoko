import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from catalog import Catalog
from server import handler_for


class BenchmarkFrontendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.dist = base / 'dist'
        self.dist.mkdir()
        (self.dist / 'index.html').write_text('<title>Benchmark only</title>', encoding='utf-8')
        (self.dist / 'assets').mkdir()
        (self.dist / 'assets' / 'test.js').write_text('console.log("test")', encoding='utf-8')
        (base / 'private.txt').write_text('secret', encoding='utf-8')
        catalog = Catalog(base / 'fixture.sqlite')
        catalog.seed(12)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(catalog, 'fixture-token', self.dist))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def test_serve_benchmark_assets_and_original_api(self):
        with urlopen(self.base + '/bench/') as r:
            self.assertIn('Benchmark only', r.read().decode())
        with urlopen(self.base + '/bench/assets/test.js') as r:
            self.assertIn('javascript', r.headers['Content-Type'])
            self.assertIn('console.log', r.read().decode())
        with urlopen(self.base + '/api/items') as r:
            self.assertEqual(json.load(r)['total'], 12)

    def test_benchmark_path_stays_within_dist(self):
        for url in ('/bench/private.txt', '/bench/../../private.txt', '/bench/assets/unknown.js', '/bench/%2e%2e/private.txt'):
            with self.subTest(url=url), self.assertRaises(HTTPError) as error:
                urlopen(self.base + url)
            self.assertEqual(error.exception.code, 404)
            error.exception.close()

if __name__ == '__main__':
    unittest.main()
