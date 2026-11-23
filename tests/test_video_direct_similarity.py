"""Generated videos and supplied window vectors; no model, GPU or quality claim."""
from dataclasses import replace
from pathlib import Path
import sys
import threading
import unittest
import weakref
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_video_direct_index as fixture
import test_video_direct_search as search_fixture
from ai_process import AIUnavailable
from ai_score_spool import SearchCancelled
from result_sessions import ResultSessions,IndexStamp,ResultUnavailable
from video_direct_search import VideoSearchChanged
from video_direct_similarity import VideoDirectSimilarity


class DirectVideoSimilarityTests(unittest.TestCase):
    setUp=fixture.SuppliedIndexTests.setUp
    supplied=fixture.SuppliedIndexTests.supplied
    seed=fixture.SuppliedIndexTests.seed
    snapshot=fixture.SuppliedIndexTests.snapshot
    add_item=search_fixture.VideoDirectSearchTests.add_item

    def test_exact_best_pair_includes_both_intervals_without_inference_or_decode(self):
        with self.supplied(),patch.object(self.encoder,'encode',side_effect=[[0,1,0],[1,0,0]]):
            self.index.index_item(self.item,self.revision)
        second,_=self.add_item(vector=[1,0,0])
        with (patch.object(self.encoder,'encode',side_effect=AssertionError('unexpected inference')),
              patch.object(self.reader,'video_coverage_stream',side_effect=AssertionError('unexpected decode'))):
            result=VideoDirectSimilarity(self.index).similar(self.item)
        row=result['items'][0]
        self.assertEqual((row['id'],row['origin_match_ms'],row['origin_match_end_ms'],
                          row['video_match_ms'],row['video_match_end_ms']),(second,16000,17500,0,16000))
        self.assertEqual((row['semantic_score'],row['video_match_source']),(1,'direct-video'))
        self.assertEqual((result['profile'],result['source'],result['mode']),(self.encoder.profile.key,'video-direct','video-similar'))

    def test_stable_pages_ties_and_self_exclusion(self):
        self.seed();second,_=self.add_item();third,_=self.add_item('third.mp4')
        pages=VideoDirectSimilarity(self.index).similar(self.item,limit=1,result_sink=lambda read:[read(0),read(1)])
        self.assertEqual([p['items'][0]['id'] for p in pages],[second,third])
        self.assertTrue(all((p['total'],p['items'][0]['origin_match_ms'],p['items'][0]['video_match_ms'])==(2,0,0) for p in pages))
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_previous_candidate_vectors_are_released_before_next_load(self):
        self.seed();second,_=self.add_item();third,_=self.add_item('third.mp4')
        search=VideoDirectSimilarity(self.index);original=search._frames
        previous=[];checked=[]
        def tracking(row,db,check):
            if row['id']!=self.item and previous:
                checked.append(row['id'])
                self.assertTrue(all(ref() is None for ref in previous))
            revision,frames=original(row,db,check)
            if row['id']!=self.item:
                previous[:]=[weakref.ref(frame[2]) for frame in frames]
            return revision,frames
        with patch.object(search,'_frames',side_effect=tracking):
            self.assertEqual(search.similar(self.item)['total'],2)
        self.assertEqual(checked,[third])

    def test_candidate_favorites_origin_roots_shelves_and_exclusions(self):
        self.seed();second,other_root=self.add_item(other_root=True)
        self.catalog.update([second],{'favorite':True});search=VideoDirectSimilarity(self.index)
        self.assertEqual([row['id'] for row in search.similar(self.item,view='favorites')['items']],[second])
        with self.assertRaises(KeyError):search.similar(self.item,root_ids=[other_root])
        shelf=self.catalog.change_shelf('create',name='別の棚')['id']
        self.catalog.change_shelf('assign',entity='item',object_ids=[second],shelf_ids=[shelf])
        with self.assertRaises(KeyError):search.similar(self.item,shelf_ids=[shelf])
        self.catalog.set_excludes(other_root,['*.mp4'])
        self.assertEqual(search.similar(self.item)['total'],0)

    def test_unindexed_origin_or_candidate_never_fabricates_matches(self):
        second,_=self.add_item();search=VideoDirectSimilarity(self.index)
        self.assertEqual(search.similar(self.item)['similarity_status'],'unindexed')
        self.seed()
        with self.index.store.connect() as db:db.execute('DELETE FROM ai_video_direct_sources WHERE item_id=?',(second,))
        result=search.similar(self.item)
        self.assertEqual((result['total'],result['candidate_total'],result['indexed_total']),(0,1,0))

    def test_corrupt_origin_and_candidate_coverage_are_unindexed(self):
        second,_=self.add_item();self.seed();search=VideoDirectSimilarity(self.index)
        statements=[
            'DELETE FROM ai_video_direct_windows WHERE item_id=? AND ordinal=1',
            'UPDATE ai_video_direct_windows SET ordinal=2 WHERE item_id=? AND ordinal=1',
            'UPDATE ai_video_direct_windows SET start_ms=16001 WHERE item_id=? AND ordinal=1',
            'UPDATE ai_video_direct_windows SET end_ms=15000 WHERE item_id=? AND ordinal=0',
            'UPDATE ai_video_direct_windows SET end_ms=86400001 WHERE item_id=? AND ordinal=1',
            "UPDATE ai_video_direct_windows SET vector=x'000000000000000000000000' WHERE item_id=? AND ordinal=1",
            'UPDATE ai_video_direct_sources SET total_frames=17 WHERE item_id=?',
            'UPDATE ai_video_direct_sources SET indexed_windows=1 WHERE item_id=?',
            "UPDATE ai_video_direct_sources SET contract='bad' WHERE item_id=?",
            "UPDATE ai_video_direct_sources SET source_revision='bad' WHERE item_id=?",
        ]
        for item in (self.item,second):
            revision=self.reader.video_manifest(item)['revision']
            for statement in statements:
                with self.subTest(item=item,statement=statement):
                    with self.supplied():self.index.index_item(item,revision)
                    with self.index.store.connect() as db:db.execute(statement,(item,))
                    result=search.similar(self.item)
                    self.assertEqual(result['total'],0)
                    self.assertEqual(result['similarity_status'],'unindexed' if item==self.item else 'ready')
            with self.supplied():self.index.index_item(item,revision)

    def test_changed_origin_index_profile_and_candidate_are_rejected(self):
        self.seed();second,_=self.add_item();search=VideoDirectSimilarity(self.index)
        def index_changed(read):
            read(0)
            with self.index.store.connect() as db:db.execute('UPDATE ai_video_direct_sources SET total_frames=0')
            return read(0)
        with self.assertRaises(VideoSearchChanged):search.similar(self.item,result_sink=index_changed)
        self.seed();self.add_item('third.mp4')
        def profile_changed(read):
            read(0);self.encoder.profile=replace(self.encoder.profile,dimension=4);return read(0)
        with self.assertRaises(VideoSearchChanged):search.similar(self.item,result_sink=profile_changed)
        self.encoder.profile=self.index.profile
        def origin_changed(read):
            read(0);self.path.write_bytes(b'changed generated origin');return read(0)
        with self.assertRaises((VideoSearchChanged,fixture.ReaderChanged)):search.similar(self.item,result_sink=origin_changed)
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_stale_candidate_does_not_match(self):
        self.seed();second,_=self.add_item();(self.media/'second.mp4').write_bytes(b'changed generated candidate')
        self.assertEqual(VideoDirectSimilarity(self.index).similar(self.item)['total'],0)

    def test_cancellation_during_pair_loop_releases_spool(self):
        windows=[fixture.window(i*16000,(i+1)*16000) for i in range(4)]
        with self.supplied(windows):self.index.index_item(self.item,self.revision)
        second,_=self.add_item()
        revision=self.reader.video_manifest(second)['revision']
        with self.supplied(windows):self.index.index_item(second,revision)
        event=threading.Event();calls=[]
        from ai_vectors import dot
        def scored(query,vector):
            calls.append(1);result=dot(query,vector);event.set()
            return result
        with patch('video_direct_similarity.dot',side_effect=scored):
            with self.assertRaises(SearchCancelled):VideoDirectSimilarity(self.index).similar(self.item,cancelled=event.is_set)
        self.assertEqual(len(calls),1);self.assertEqual(list(self.stage.iterdir()),[])

    def test_pair_limit_fails_without_partial_ranking(self):
        self.seed();self.add_item()
        with patch('video_direct_similarity.MAX_PAIRS',3):
            with self.assertRaisesRegex(AIUnavailable,'フォルダーや棚'):
                VideoDirectSimilarity(self.index).similar(self.item)
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_vector_memory_limit_fails_without_partial_ranking(self):
        self.seed();self.add_item()
        with patch('video_direct_similarity.MAX_FRAME_BYTES',1):
            with self.assertRaisesRegex(AIUnavailable,'メモリ'):
                VideoDirectSimilarity(self.index).similar(self.item)
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_invalid_requests_and_cancel_before_start(self):
        self.seed();search=VideoDirectSimilarity(self.index)
        with self.assertRaises(SearchCancelled):search.similar(self.item,cancelled=lambda:True)
        for options in ({'limit':True},{'page':-1},{'kind':'image'},{'cancelled':True}):
            with self.subTest(options=options),self.assertRaises(ValueError):search.similar(self.item,**options)

    def test_result_session_invalidates_if_origin_changes(self):
        self.seed();self.add_item();search=VideoDirectSimilarity(self.index)
        sessions=ResultSessions(self.catalog,lambda conditions,consume,cancelled:search.similar(self.item,result_sink=consume,cancelled=cancelled),index_stamp=IndexStamp(self.index),parent=self.stage)
        try:
            sessions.create('a'*32,{'mode':'video-similar','item_id':self.item})
            self.assertEqual(sessions.read('a'*32,0,1)['items'][0]['origin_match_ms'],0)
            self.path.write_bytes(b'changed generated origin')
            with self.assertRaises(ResultUnavailable):sessions.read('a'*32,0,1)
        finally:sessions.close()

    def test_candidate_changes_during_range_report_refresh_conflict(self):
        self.seed();self.add_item()
        def changed(read):
            read(0);(self.media/'second.mp4').write_bytes(b'changed generated match');return read(0)
        with self.assertRaises(VideoSearchChanged):
            VideoDirectSimilarity(self.index).similar(self.item,result_sink=changed)
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_pair_cap_after_one_scored_item_returns_no_partial_result(self):
        self.seed();self.add_item();self.add_item('third.mp4')
        sink=lambda read:self.fail('Partial ranking must not be published')
        with patch('video_direct_similarity.MAX_PAIRS',4):
            with self.assertRaises(AIUnavailable):
                VideoDirectSimilarity(self.index).similar(self.item,result_sink=sink)
        self.assertEqual(list(self.stage.iterdir()),[])


if __name__=='__main__':unittest.main()
