"""Generated vector scores verify display grouping, not actual retrieval precision."""
import math,sys,tempfile,unittest
from dataclasses import replace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from ai_result_groups import boundary
from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch,revision
from production import ProductionCatalog

class Encoder:
    available=True;profile=replace(DEFAULT_PROFILE,dimension=8)
    def __init__(self):self.calls=0
    def encode(self,operation,value):self.calls+=1;return [1.0]+[0.0]*7
    def close(self):pass

class GroupTests(unittest.TestCase):
    def test_relative_gap_and_tied_boundary_never_split_ties(self):
        cut=boundary(list(enumerate([.9,.89,.88,.2,.19,.18])),'cosine')
        self.assertAlmostEqual(cut,.54)
        self.assertAlmostEqual(boundary(list(enumerate([.9,.9,.9,.1,.1,.1])),'cosine'),.5)
        self.assertIsNone(boundary(list(enumerate([.5,.49,.48,.47])),'cosine'))
        self.assertIsNone(boundary([(1,.5)],'cosine'))
    def test_manual_boundary_and_rrf_are_different_scales(self):
        self.assertEqual(boundary([], 'cosine',.3),.3)
        self.assertIsNone(boundary([(1,.02),(2,.001)],'reciprocal-rank'))
        for bad in (True,math.nan,math.inf,1.1,'0.5'):
            with self.assertRaises(ValueError):boundary([], 'cosine',bad)
        with self.assertRaises(ValueError):boundary([], 'reciprocal-rank',.3)
    def test_groups_global_before_paging_and_literal_evidence_is_optional(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);media=base/'media';media.mkdir()
            for i in range(6):(media/f'{i}.png').write_bytes(b'generated')
            catalog=ProductionCatalog(base/'catalog.sqlite');self.addCleanup(catalog.close)
            root=catalog.add_root(str(media));catalog.start_scan(root);catalog._worker.join(10)
            rows=catalog.search()['items'];encoder=Encoder();ai=AISearch(catalog,encoder);self.addCleanup(ai.close)
            for row,score in zip(rows,[.9,.89,.88,.2,.19,.18]):
                vector=[score,math.sqrt(1-score*score)]+[0.0]*6
                ai.store.put(row['id'],revision(row),{'text':vector,'cover':vector})
            all_result=ai.search('初音ミク',source='cover',limit=2,page=1)
            self.assertEqual((all_result['total'],all_result['leading_total'],all_result['other_total']),(6,3,3))
            self.assertEqual([r['similarity_group'] for r in all_result['items']],['leading','other'])
            self.assertEqual(ai.search('初音ミク',source='cover',result_group='leading')['total'],3)
            self.assertEqual(ai.search('初音ミク',source='cover',result_group='other')['total'],3)
            self.assertEqual(ai.search('初音ミク',source='cover',result_group='leading',group_threshold=.85)['total'],3)
            self.assertEqual(ai.search('初音ミク',source='cover',literal_only=True)['total'],0)
            catalog.update([rows[0]['id']],{'tags':['初音ミク']});row=catalog.get(rows[0]['id'])
            ai.store.put(row['id'],revision(row),{'text':[1.0]+[0.0]*7,'cover':[1.0]+[0.0]*7})
            selected=ai.search('初音ミク',source='cover',literal_only=True)
            self.assertEqual(selected['total'],1);self.assertEqual((selected['items'][0]['literal_hits'],selected['items'][0]['literal_words']),(1,1))
            count=encoder.calls
            with self.assertRaises(ValueError):ai.search('初音ミク',source='cover',group_threshold=2)
            self.assertEqual(encoder.calls,count)
            catalog.unregister_root(root);self.assertEqual(ai.search('初音ミク',source='cover')['total'],0)
            with self.assertRaises(ValueError):ai.search('初音ミク',scope={'root_ids':[root]})

if __name__=='__main__':unittest.main()
