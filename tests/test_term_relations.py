"""Related-term dictionary expansion; generated temporary files only."""
import json, sys, tempfile, threading, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from production import ProductionCatalog
from production_server import production_handler
from term_relations import MAX_ALTERNATIVES, MAX_WORDS, validate_entry

REIMU = {'term': '博麗霊夢', 'aliases': ['霊夢', 'Reimu'], 'related': ['東方', '巫女']}


class ValidateTests(unittest.TestCase):
    def test_entry_is_trimmed_deduplicated_and_normalized(self):
        entry = validate_entry({'term': ' 博麗霊夢 ', 'aliases': ['霊夢', 'ＲＥＩＭＵ', 'reimu', '博麗霊夢'],
                                'related': ['東方', '霊夢', '東方']})
        self.assertEqual(entry, {'term': '博麗霊夢', 'aliases': ['霊夢', 'ＲＥＩＭＵ'], 'related': ['東方']})

    def test_invalid_entries_rejected(self):
        for body in [None, [], {}, {'term': ''}, {'term': 'a b'}, {'term': 'x' * 61}, {'term': 'a', 'extra': 1},
                     {'term': 'a', 'aliases': 'b'}, {'term': 'a', 'related': [1]},
                     {'term': 'a', 'aliases': [f'w{i}' for i in range(MAX_WORDS + 1)]},
                     {'term': 'a', 'related': ['two words']}]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                validate_entry(body)


class ExpansionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name); self.media = base / 'media'; self.media.mkdir(); self.db = base / 'catalog.sqlite'
        self.catalog = ProductionCatalog(self.db); self.addCleanup(self.catalog.close)
        names = ['reimu_standing.png', 'shrine_maiden.png', 'marisa.png', 'touhou_poster.png', 'unrelated.png']
        for name in names:
            (self.media / name).write_bytes(b'fictional, not an actual media file')
        self.sources = {n: (self.media / n).read_bytes() for n in names}
        root = self.catalog.add_root(str(self.media)); self.catalog.start_scan(root); self.catalog._worker.join(10)
        self.ids = {i['title']: i['id'] for i in self.catalog.search(limit=120)['items']}
        self.catalog.update([self.ids['reimu_standing.png']], {'tags': ['博麗霊夢', '立ち絵']})
        self.catalog.update([self.ids['shrine_maiden.png']], {'tags': ['巫女']})
        self.catalog.update([self.ids['marisa.png']], {'tags': ['霧雨魔理沙']})
        self.catalog.update([self.ids['touhou_poster.png']], {'tags': ['東方', '巫女']})

    def titles(self, result):
        return [i['title'] for i in result['items']]

    def test_without_dictionary_vague_query_misses_the_named_file(self):
        result = self.catalog.search('東方 巫女')
        self.assertEqual(self.titles(result), ['touhou_poster.png'])
        self.assertNotIn('expansions', result)
        self.assertNotIn('match', result['items'][0])

    def test_vision_case_tohou_miko_finds_reimu_after_direct_hits(self):
        self.catalog.terms.upsert(REIMU)
        self.catalog.terms.upsert({'term': '霧雨魔理沙', 'related': ['東方', '魔法使い']})
        result = self.catalog.search('東方 巫女')
        # Direct hit first, then the related candidate; Marisa lacks 巫女.
        self.assertEqual(self.titles(result), ['touhou_poster.png', 'reimu_standing.png'])
        self.assertEqual([i['match'] for i in result['items']], ['direct', 'related'])
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['expansions'], [{'term': '東方', 'added': ['博麗霊夢', '霊夢', 'Reimu', '霧雨魔理沙']},
                                                {'term': '巫女', 'added': ['博麗霊夢', '霊夢', 'Reimu']}])
        self.assertNotIn('direct_hits', result['items'][0])

    def test_aliases_match_spelling_variants_and_filters_still_apply(self):
        self.catalog.terms.upsert(REIMU)
        self.assertEqual(self.titles(self.catalog.search('霊夢')), ['reimu_standing.png'])
        self.assertEqual(self.titles(self.catalog.search('ＲＥＩＭＵ')), ['reimu_standing.png'])
        self.assertEqual(self.catalog.search('東方 巫女', kind='book')['total'], 0)
        self.catalog.update([self.ids['reimu_standing.png']], {'favorite': True})
        self.assertEqual(self.titles(self.catalog.search('東方 巫女', view='favorites')), ['reimu_standing.png'])
        self.assertEqual(self.catalog.search('東方 巫女 立ち絵')['total'], 1)

    def test_persist_update_delete_and_sources_untouched(self):
        self.catalog.terms.upsert(REIMU)
        self.catalog.terms.upsert({'term': '博麗霊夢', 'aliases': ['霊夢']})  # replace: no related words
        restarted = ProductionCatalog(self.db); self.addCleanup(restarted.close)
        self.assertEqual(restarted.terms.entries(), [{'term': '博麗霊夢', 'aliases': ['霊夢'], 'related': []}])
        self.assertEqual(self.titles(restarted.search('東方 巫女')), ['touhou_poster.png'])
        restarted.terms.delete('博麗霊夢')
        self.assertEqual(restarted.terms.entries(), [])
        with self.assertRaises(KeyError):
            restarted.terms.delete('博麗霊夢')
        self.assertEqual(self.sources, {n: (self.media / n).read_bytes() for n in self.sources})

    def test_large_dictionary_keeps_candidates_related_to_every_word(self):
        for i in range(300):  # 900 spellings related to 東方 alone exceed the per-word cap
            self.catalog.terms.upsert({'term': f'キャラ{i}', 'aliases': [f'chara{i}', f'c{i}x'], 'related': ['東方']})
        self.catalog.terms.upsert(REIMU)
        result = self.catalog.search('東方 巫女')
        self.assertEqual(self.titles(result), ['touhou_poster.png', 'reimu_standing.png'])
        first = result['expansions'][0]
        self.assertEqual((first['term'], first['added'][:3], first['truncated']), ('東方', ['博麗霊夢', '霊夢', 'Reimu'], True))
        self.assertEqual(len(first['added']), MAX_ALTERNATIVES - 1)
        self.assertNotIn('truncated', result['expansions'][1])

    def test_http_routes_require_session_and_origin(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), production_handler(self.catalog, 'term-token'))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        origin = f'http://127.0.0.1:{server.server_port}'
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def call(route, body=None, token='term-token', origin_header=origin):
            headers = {'X-Aredoko-Token': token, 'Content-Type': 'application/json'}
            if origin_header: headers['Origin'] = origin_header
            data = None if body is None else json.dumps(body).encode()
            try:
                with opener.open(urllib.request.Request(origin + route, data, headers=headers)) as response:
                    return response.status, json.loads(response.read())
            except urllib.error.HTTPError as error:
                with error: return error.code, json.loads(error.read())

        self.assertEqual(call('/api/library/terms', token='wrong')[0], 403)
        self.assertEqual(call('/api/library/terms', REIMU, token='wrong')[0], 403)
        self.assertEqual(call('/api/library/terms', REIMU, origin_header='http://evil.invalid')[0], 403)
        status, body = call('/api/library/terms', {'term': 'a b'})
        self.assertEqual(status, 400); self.assertIn('single word', body['error'])
        self.assertEqual(call('/api/library/terms', REIMU), (200, {'entry': REIMU}))
        self.assertEqual(call('/api/library/terms'), (200, {'items': [REIMU]}))
        status, body = call('/api/items?q=' + urllib.parse.quote('東方 巫女'))
        self.assertEqual(status, 200); self.assertEqual(body['total'], 2); self.assertEqual(len(body['expansions']), 2)
        self.assertEqual(call('/api/library/terms/delete', {'term': '博麗霊夢', 'x': 1})[0], 400)
        self.assertEqual(call('/api/library/terms/delete', {'term': '博麗霊夢'}), (200, {'deleted': True}))
        self.assertEqual(call('/api/library/terms/delete', {'term': '博麗霊夢'})[0], 404)


if __name__ == '__main__':
    unittest.main()
