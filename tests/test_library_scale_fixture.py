import json
from pathlib import Path
import sys
import tempfile
import unittest
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'));sys.path.insert(0,str(REPO/'app'))
from create_library_scale_fixture import create,digest
from production import ProductionCatalog
from ai_search import AISearch
from ai_process import AIUnavailable

class NoInference:
    available=False
    def encode(self,*args):raise AssertionError('No inference expected')
    def close(self):pass

class LibraryScaleTests(unittest.TestCase):
    def test_generated_fixture_paging_scope_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'fixture';info=create(folder,count=301,root_count=3)
            catalog=ProductionCatalog(folder/'catalog.sqlite');ai=AISearch(catalog,NoInference())
            try:
                self.assertEqual(catalog.search()['total'],301)
                self.assertEqual(len(catalog.search(page=5)['items']),1)
                self.assertEqual(catalog.search('最後の検証候補')['items'][0]['id'],301)
                self.assertEqual(ai.coverage()['target_total'],301)
                self.assertEqual(ai.coverage({'root_ids':[info['long_root_id']]})['target_total'],info['per_root'][str(info['long_root_id'])])
                self.assertEqual(len(list((folder/'generated').rglob('*.png'))),75)
                self.assertEqual(digest(folder/'generated'),info['source_digest'])
                self.assertEqual(catalog.get(1)['tags'][0],'架空データ')
            finally:ai.close();catalog.close()
            with self.assertRaises(FileExistsError):create(folder,count=301,root_count=3)
    def test_multiple_root_keyset_keeps_order_scope_and_exclusions(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'fixture';info=create(folder,count=901,root_count=4)
            catalog=ProductionCatalog(folder/'catalog.sqlite');ai=AISearch(catalog,NoInference())
            try:
                chosen=info['roots'][1:3]
                with catalog.connect() as db:
                    db.execute("UPDATE library_roots SET excludes_json=? WHERE id=?",(json.dumps(['*00899*']),chosen[1]))
                    # Metadata-driven independent expected IDs, not the iterator SQL.
                    expected=[row['id'] for row in db.execute("SELECT i.id,i.kind,l.root_id,l.relative_path FROM items i JOIN item_locations m ON m.item_id=i.id JOIN library_locations l ON l.id=m.location_id ORDER BY i.id")
                              if row['root_id'] in chosen and '00899' not in row['relative_path']]
                self.assertGreater(len(expected),256)
                scope={'root_ids':chosen}
                actual=[row['id'] for row in ai._iter_rows(scope=scope,all_candidates=True)]
                self.assertEqual(actual,expected)
                self.assertEqual([row['id'] for row in ai._iter_rows(scope=scope,limit=260)],expected[:260])
                self.assertEqual(ai.coverage(scope)['candidate_total'],len(expected))
                filtered=[row['id'] for row in ai._iter_rows(scope={**scope,'kind':'audio'},all_candidates=True)]
                self.assertEqual(filtered,[item for item in expected if catalog.get(item)['kind']=='audio'])
            finally:ai.close();catalog.close()

    def test_no_unbounded_seed_argument(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'fixture'
            for count,roots in [(119,3),(50001,3),(301,259)]:
                with self.assertRaises(ValueError):create(folder,count=count,root_count=roots)
            self.assertFalse(folder.exists())

if __name__=='__main__':unittest.main()
