"""Literal search normalization/AND terms; generated temporary files only."""
import sys, tempfile, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from production import ProductionCatalog
from search_terms import MAX_TERMS, normalize, split_terms


class NormalizeTests(unittest.TestCase):
    def test_width_case_and_kana_are_folded(self):
        self.assertEqual(normalize('ﾚｲﾑ'), normalize('れいむ'))
        self.assertEqual(normalize('レイム'), 'れいむ')
        self.assertEqual(normalize('ＲＥＩＭＵ'), 'reimu')
        self.assertEqual(normalize('ヴァ'), 'ゔぁ')
        self.assertEqual(normalize('東方'), '東方')
        self.assertEqual(normalize(None), '')

    def test_split_on_any_whitespace_dedupes_and_limits(self):
        self.assertEqual(split_terms(' 東方\u3000巫女\t東方 '), ['東方', '巫女'])
        self.assertEqual(split_terms('   '), [])
        self.assertEqual(len(split_terms(' '.join(f'w{i}' for i in range(MAX_TERMS)))), MAX_TERMS)
        with self.assertRaises(ValueError):
            split_terms(' '.join(f'w{i}' for i in range(MAX_TERMS + 1)))


class CatalogTermTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name); self.media = base / 'media'; self.media.mkdir()
        self.catalog = ProductionCatalog(base / 'catalog.sqlite'); self.addCleanup(self.catalog.close)

    def scan(self, names):
        for name in names:
            (self.media / name).write_bytes(b'fictional, not an actual media file')
        root = self.catalog.add_root(str(self.media))
        self.catalog.start_scan(root); self.catalog._worker.join(10)
        self.assertEqual(self.catalog.scan_state()['state'], 'complete')
        return {item['title']: item['id'] for item in self.catalog.search(limit=120)['items']}

    def titles(self, query, **kwargs):
        return sorted(item['title'] for item in self.catalog.search(query, limit=120, **kwargs)['items'])

    def test_all_words_must_match_title_or_tags_in_any_order(self):
        ids = self.scan(['standing_A.png', 'shrine_B.png', 'other.png'])
        self.catalog.update([ids['standing_A.png']], {'tags': ['東方', '巫女']})
        self.catalog.update([ids['shrine_B.png']], {'tags': ['巫女']})
        self.assertEqual(self.titles('東方 巫女'), ['standing_A.png'])
        self.assertEqual(self.titles('巫女\u3000東方'), ['standing_A.png'])
        self.assertEqual(self.titles('巫女'), ['shrine_B.png', 'standing_A.png'])
        self.assertEqual(self.titles('巫女 shrine'), ['shrine_B.png'])
        # No item has every word: items missing one word come back marked partial.
        partial = self.catalog.search('東方 存在しない')
        self.assertEqual(([i['title'] for i in partial['items']], partial['partial']),
                         (['standing_A.png'], {'words': 2, 'required': 1}))
        self.assertEqual(self.titles('存在しない'), [])
        # Nothing with even all-but-one word: a plain empty result, no partial flag.
        self.assertNotIn('partial', self.catalog.search('存在しない 別の語'))

    def test_variants_and_old_substring_queries_still_match(self):
        ids = self.scan(['Reimu_Stand.PNG', 'ﾚｲﾑ_half.png', 'plain 100%_a.png'])
        self.catalog.update([ids['Reimu_Stand.PNG']], {'tags': ['レイム']})
        self.assertEqual(self.titles('reimu'), ['Reimu_Stand.PNG'])
        self.assertEqual(self.titles('ＲＥＩＭＵ'), ['Reimu_Stand.PNG'])
        self.assertEqual(self.titles('れいむ'), ['Reimu_Stand.PNG', 'ﾚｲﾑ_half.png'])
        # Former LIKE wildcards are literal characters, not patterns.
        self.assertEqual(self.titles('100%_'), ['plain 100%_a.png'])
        self.assertEqual(self.titles('%'), ['plain 100%_a.png'])
        self.assertEqual(self.titles('_'), sorted(ids))
        self.assertEqual(self.titles('stand.png'), ['Reimu_Stand.PNG'])

    def test_filters_paging_and_validation_unchanged(self):
        ids = self.scan([f'{i:03}_東方.png' for i in range(70)] + ['東方.cbz'])
        self.catalog.update([ids['000_東方.png']], {'favorite': True})
        self.assertEqual(self.catalog.search('東方')['total'], 71)
        self.assertEqual(len(self.catalog.search('東方', page=1)['items']), 11)
        self.assertEqual(self.titles('東方', kind='book'), ['東方.cbz'])
        self.assertEqual(self.titles('東方', view='favorites'), ['000_東方.png'])
        with self.assertRaises(ValueError):
            self.catalog.search(' '.join(f'w{i}' for i in range(MAX_TERMS + 1)))
        with self.assertRaises(ValueError):
            self.catalog.search('x' * 301)

    def test_fifty_thousand_rows_two_terms_stay_interactive(self):
        self.scan(['seed.png'])
        with self.catalog.connect() as db:
            root = db.execute('SELECT id FROM library_roots').fetchone()[0]
            for i in range(50000):
                loc = db.execute("INSERT INTO library_locations(root_id,relative_path,kind,status,size_bytes,mtime_ns,"
                                 "discovered_at,last_seen_at) VALUES(?,?,?,?,?,?,?,?)",
                                 (root, f'gen/{i}.png', 'image', 'present', 1, 1, 'generated', 'generated')).lastrowid
                item = db.execute('INSERT INTO items(title,kind,tags) VALUES(?,?,?)',
                                  (f'生成{i}.png', 'image', '["東方","巫女"]' if i % 1000 == 0 else '["雨"]')).lastrowid
                db.execute('INSERT INTO item_locations VALUES(?,?)', (item, loc))
        started = time.perf_counter()
        result = self.catalog.search('東方 巫女')
        elapsed = time.perf_counter() - started
        print(f'\n[search_terms] 50001 rows two-term literal search {elapsed:.3f}s', file=sys.stderr)
        self.assertEqual(result['total'], 50)
        self.assertLess(elapsed, 5.0, f'two-term literal search took {elapsed:.2f}s')


if __name__ == '__main__':
    unittest.main()
