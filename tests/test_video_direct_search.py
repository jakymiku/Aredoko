"""Scoped retrieval over supplied direct video vectors; no GPU/quality claim."""
import shutil
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_video_window_decode as fixture
import test_video_direct_index as index_fixture
from video_direct_search import VideoDirectSearch,VideoSearchChanged


class VideoDirectSearchTests(unittest.TestCase):
    setUp=index_fixture.SuppliedIndexTests.setUp
    supplied=index_fixture.SuppliedIndexTests.supplied
    seed=index_fixture.SuppliedIndexTests.seed
    snapshot=index_fixture.SuppliedIndexTests.snapshot

    def add_item(self,name='second.mp4',*,other_root=False,vector=None):
        directory=self.base/'other-media' if other_root else self.media
        directory.mkdir(exist_ok=True);shutil.copyfile(fixture.VideoWindowTests.path,directory/name)
        root=self.catalog.add_root(str(directory)) if other_root else self.root
        self.catalog.index.scan(root);self.catalog.sync_index()
        item=next(row['id'] for row in self.catalog.search()['items'] if row['title']==name)
        revision=self.reader.video_manifest(item)['revision']
        with self.supplied(),patch.object(self.encoder,'encode',return_value=vector or [1,0,0]):
            self.index.index_item(item,revision)
        return item,root

    def test_text_query_has_best_time_without_invented_description(self):
        with self.supplied(),patch.object(self.encoder,'encode',side_effect=[[0,1,0],[1,0,0]]):
            self.index.index_item(self.item,self.revision)
        with patch.object(self.encoder,'encode',return_value=[1,0,0]) as encode:
            result=VideoDirectSearch(self.index).search('生成した動画の特徴')
        self.assertEqual(encode.call_count,1);self.assertEqual(encode.call_args.args,('query','生成した動画の特徴'))
        self.assertEqual(result['total'],1);row=result['items'][0]
        self.assertEqual((row['id'],row['video_match_ms'],row['video_match_end_ms']),(self.item,16000,17500))
        self.assertEqual(row['video_match_source'],'direct-video');self.assertNotIn('video_match_snippet',row)
        self.assertEqual(row['semantic_score'],1)

    def test_common_favorite_shelf_root_and_exclusion_filters_are_preserved(self):
        self.seed();other,root=self.add_item(other_root=True)
        self.catalog.update([other],{'favorite':True})
        shelf=self.catalog.change_shelf('create',name='生成動画')
        self.catalog.change_shelf('assign',entity='item',object_ids=[other],shelf_ids=[shelf['id']])
        search=VideoDirectSearch(self.index)
        for conditions in ({'view':'favorites'},{'root_ids':[root]},{'shelf_ids':[shelf['id']]},
                           {'view':'favorites','root_ids':[root],'shelf_ids':[shelf['id']]}):
            with self.subTest(conditions=conditions):
                self.assertEqual([row['id'] for row in search.search('video',**conditions)['items']],[other])
        self.catalog.set_excludes(root,['*.mp4'])
        self.assertEqual(search.search('video',root_ids=[root])['total'],0)

    def test_range_sink_reuses_ranking_and_stable_id_ties(self):
        self.seed();second,_=self.add_item();third,_=self.add_item('third.mp4')
        def consume(fetch):return [fetch(0),fetch(1),fetch(2)]
        with patch.object(self.encoder,'encode',return_value=[1,0,0]) as encode:
            pages=VideoDirectSearch(self.index).search('video',limit=1,result_sink=consume)
        self.assertEqual(encode.call_count,1)
        self.assertEqual([page['items'][0]['id'] for page in pages],[self.item,second,third])
        self.assertTrue(all(page['total']==3 for page in pages));self.assertEqual(list(self.stage.iterdir()),[])

    def test_stale_sources_are_not_false_matches(self):
        self.seed();self.path.write_bytes(b'changed generated source')
        self.assertEqual(VideoDirectSearch(self.index).search('video')['total'],0)

    def test_unindexed_scope_reports_status_without_matches(self):
        result=VideoDirectSearch(self.index).search('video')
        self.assertEqual((result['total'],result['indexed_total'],result['search_status']),(0,0,'unindexed'))

    def test_empty_scope_and_invalid_conditions_do_not_load_encoder(self):
        self.seed()
        with patch.object(self.encoder,'encode') as encode:
            self.assertEqual(VideoDirectSearch(self.index).search('video',view='favorites')['candidate_total'],0)
            encode.assert_not_called()
            with self.assertRaises(ValueError):VideoDirectSearch(self.index).search('video',root_ids=[999])
            with self.assertRaises(ValueError):VideoDirectSearch(self.index).search('video',kind='image')

    def test_cancelled_search_raises_before_ranking(self):
        from ai_score_spool import SearchCancelled
        self.seed()
        with self.assertRaises(SearchCancelled):
            VideoDirectSearch(self.index).search('video',cancelled=lambda:True)


if __name__=='__main__':unittest.main()
