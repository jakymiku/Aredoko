"""Word-level search reasons on generated metadata; no media decode or inference."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from production import ProductionCatalog
from production_server import production_handler, DisabledAI
from search_terms import explain_matches, matcher


class SearchEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.media = self.base/'generated'; self.media.mkdir()
        for name in ('a.png','b.png','c.cbz'):(self.media/name).write_bytes(b'generated placeholder')
        self.catalog = ProductionCatalog(self.base/'catalog.sqlite'); self.addCleanup(self.catalog.close)
        self.root = self.catalog.add_root(str(self.media)); self.catalog.index.scan(self.root); self.catalog.sync_index()
        self.ids = {row['title']:row['id'] for row in self.catalog.search()['items']}

    def test_direct_words_are_normalized_deduplicated_and_cover_real_tag_values(self):
        self.catalog.update([self.ids['a.png']], {'tags':['ﾚｲﾑ',r'C:\textures','魔法"少女']})
        result = self.catalog.search('ＲＥＩＭＵ れいむ')
        self.assertEqual(result['items'][0]['search_evidence'],
                         {'direct_words':['れいむ'],'related_words':[],'missing_words':['reimu']})
        result = self.catalog.search('れいむ ﾚｲﾑ C:\\textures 魔法"少女')
        self.assertEqual(result['items'][0]['search_evidence'],
                         {'direct_words':['れいむ',r'c:\textures','魔法"少女'],'related_words':[],'missing_words':[]})

    def test_direct_and_related_words_are_separate_per_result(self):
        self.catalog.update([self.ids['a.png']], {'tags':['東方','巫女']})
        self.catalog.update([self.ids['b.png']], {'tags':['博麗霊夢']})
        self.catalog.terms.upsert({'term':'博麗霊夢','aliases':['霊夢'],'related':['東方','巫女']})
        rows = self.catalog.search('東方 巫女')['items']
        self.assertEqual([row['id'] for row in rows],[self.ids['a.png'],self.ids['b.png']])
        self.assertEqual(rows[0]['search_evidence'],{'direct_words':['東方','巫女'],'related_words':[],'missing_words':[]})
        self.assertEqual(rows[1]['search_evidence'],{'direct_words':[],'related_words':['東方','巫女'],'missing_words':[]})
        self.assertEqual([row['match'] for row in rows],['direct','related'])

    def test_partial_rows_explain_different_missing_words_with_filters_before_fallback(self):
        self.catalog.update([self.ids['a.png']], {'tags':['東方','赤'],'favorite':True})
        self.catalog.update([self.ids['b.png']], {'tags':['東方','夜']})
        self.catalog.update([self.ids['c.cbz']], {'tags':['東方','赤','夜']})
        other=self.base/'other';other.mkdir();(other/'outside.png').write_bytes(b'generated')
        root2=self.catalog.add_root(str(other));self.catalog.index.scan(root2);self.catalog.sync_index()
        outside=self.catalog.search(root_id=root2)['items'][0]['id']
        self.catalog.update([outside], {'tags':['東方','赤','夜']})
        result=self.catalog.search('東方 赤 夜',kind='image',root_id=self.root)
        self.assertEqual(result['partial'],{'words':3,'required':2})
        evidence={row['id']:row['search_evidence'] for row in result['items']}
        self.assertEqual(evidence[self.ids['a.png']]['missing_words'],['夜'])
        self.assertEqual(evidence[self.ids['b.png']]['missing_words'],['赤'])
        self.assertNotIn(outside,evidence)
        favorite=self.catalog.search('東方 赤 夜',kind='image',view='favorites',root_id=self.root)
        self.assertEqual([row['id'] for row in favorite['items']],[self.ids['a.png']])

    def test_blank_empty_and_saved_metadata_are_unchanged(self):
        before=self.catalog.get(self.ids['a.png'])
        source={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.media.iterdir()}
        self.assertTrue(all('search_evidence' not in row for row in self.catalog.search()['items']))
        self.assertEqual(self.catalog.search('未知')['items'],[])
        self.catalog.search('a.png')
        self.assertEqual(self.catalog.get(self.ids['a.png']),before)
        self.assertEqual({p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.media.iterdir()},source)

    def test_http_returns_related_and_missing_words_without_changing_existing_partial_flag(self):
        self.catalog.update([self.ids['a.png']], {'tags':['博麗霊夢']})
        self.catalog.terms.upsert({'term':'博麗霊夢','aliases':[],'related':['東方']})
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'fixture-token',ai=DisabledAI()))
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        query=urllib.parse.urlencode({'q':'東方 未知','kind':'image'})
        with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/api/items?{query}',timeout=5) as response:
            result=json.load(response)
        self.assertEqual(result['items'][0]['match'],'partial')
        self.assertEqual(result['items'][0]['search_evidence'],
                         {'direct_words':[],'related_words':['東方'],'missing_words':['未知']})
        self.assertEqual(result['partial'],{'words':2,'required':1})

    def test_explanation_and_score_agree_for_full_related_partial_and_tag_boundaries(self):
        options=[['雨','雨音'],['街','都市'],['青','ブルー']]
        for title,tags in [('雨 街 青.png',[]),('neutral.png',['雨音','都市','ブルー']),
                           ('雨.png',['街']),('neutral.png',['雨','街青']),('none.png',[])]:
            with self.subTest(title=title,tags=tags):
                reason=explain_matches(title,tags,options)
                score=matcher(options)(title,json.dumps(tags,ensure_ascii=False))
                self.assertEqual(score,-1 if reason['missing_words'] else len(reason['direct_words']))
                self.assertEqual(sum(len(words) for words in reason.values()),len(options))


if __name__=='__main__':unittest.main()
