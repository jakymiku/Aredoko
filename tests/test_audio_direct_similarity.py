"""Generated sources and supplied vectors: no model, GPU or quality claim."""
import json
from pathlib import Path
import sys
import threading
import unittest
import weakref
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_audio_direct_index as fixture
import test_audio_direct_search as search_fixture
from audio_direct_similarity import AudioDirectSimilarity
from audio_direct_search import AudioSearchChanged
from ai_score_spool import SearchCancelled
from ai_process import AIUnavailable
from result_sessions import ResultSessions,IndexStamp,ResultUnavailable


class DirectSimilarityTests(unittest.TestCase):
    setUp=fixture.DirectAudioIndexTests.setUp
    supplied=fixture.DirectAudioIndexTests.supplied
    seed=fixture.DirectAudioIndexTests.seed
    snapshot=fixture.DirectAudioIndexTests.snapshot
    add_item=search_fixture.AudioDirectSearchTests.add_item

    def test_exact_best_pair_has_both_times_without_loading_a_model(self):
        with self.supplied(),patch.object(self.encoder,'encode',side_effect=[[0,1,0],[1,0,0]]):
            self.index.index_item(self.item,self.revision)
        second,_=self.add_item(vector=[1,0,0])
        with patch.object(self.encoder,'encode',side_effect=AssertionError('Cached similarity must not infer')):
            result=AudioDirectSimilarity(self.index).similar(self.item)
        row=result['items'][0]
        self.assertEqual((row['id'],row['origin_match_ms'],row['audio_match_ms']),(second,30000,0))
        self.assertEqual(row['semantic_score'],1)
        self.assertEqual(row['audio_match_source'],'direct-audio');self.assertNotIn('audio_match_snippet',row)
        self.assertEqual(result['profile'],self.encoder.profile.key);self.assertEqual(result['source'],'audio-direct')

    def test_cached_pages_are_stable_and_exclude_origin(self):
        self.seed();second,_=self.add_item();third,_=self.add_item('third.wav')
        pages=AudioDirectSimilarity(self.index).similar(self.item,limit=1,result_sink=lambda read:[read(0),read(1)])
        self.assertEqual([page['items'][0]['id'] for page in pages],[second,third])
        self.assertTrue(all(page['total']==2 for page in pages));self.assertEqual(list(self.stage.iterdir()),[])

    def test_candidate_view_does_not_hide_origin_but_root_and_shelf_do(self):
        self.seed();second,other_root=self.add_item(other_root=True)
        self.catalog.update([second],{'favorite':True})
        search=AudioDirectSimilarity(self.index)
        self.assertEqual([row['id'] for row in search.similar(self.item,view='favorites')['items']],[second])
        with self.assertRaises(KeyError):search.similar(self.item,root_ids=[other_root])
        shelf=self.catalog.change_shelf('create',name='別の棚')['id']
        self.catalog.change_shelf('assign',entity='item',object_ids=[second],shelf_ids=[shelf])
        with self.assertRaises(KeyError):search.similar(self.item,shelf_ids=[shelf])
        self.catalog.set_excludes(other_root,['*.wav'])
        self.assertEqual(search.similar(self.item)['total'],0)

    def test_missing_silent_or_corrupt_origin_does_not_fabricate_matches(self):
        second,_=self.add_item();search=AudioDirectSimilarity(self.index)
        self.assertEqual(search.similar(self.item)['similarity_status'],'unindexed')
        self.seed()
        with self.index.store.connect() as db:db.execute('UPDATE ai_audio_direct_sources SET indexed_windows=3 WHERE item_id=?',(self.item,))
        self.assertEqual(search.similar(self.item)['total'],0)
        silent=[fixture.PCMWindow(0,30000,b'\0'*(480000*4))]
        with self.supplied(silent):self.index.index_item(self.item,self.revision)
        self.assertEqual(search.similar(self.item)['similarity_status'],'unindexed')

    def test_source_change_or_index_change_during_range_is_rejected(self):
        self.seed();self.add_item();search=AudioDirectSimilarity(self.index)
        def changed(read):
            read(0);self.path.write_bytes(b'changed generated origin');return read(0)
        with self.assertRaises(AudioSearchChanged):search.similar(self.item,result_sink=changed)
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_index_write_during_range_discards_the_old_results(self):
        self.seed();self.add_item()
        def changed(read):
            read(0)
            with self.index.store.connect() as db:db.execute('UPDATE ai_audio_direct_sources SET indexed_windows=0')
            return read(0)
        with self.assertRaises(AudioSearchChanged):AudioDirectSimilarity(self.index).similar(self.item,result_sink=changed)

    def test_cancel_and_invalid_requests_never_encode(self):
        self.seed();event=threading.Event();event.set();search=AudioDirectSimilarity(self.index)
        with self.assertRaises(SearchCancelled):search.similar(self.item,cancelled=event.is_set)
        for options in ({'limit':True},{'page':-1},{'kind':'image'},{'cancelled':True}):
            with self.subTest(options=options),self.assertRaises(ValueError):search.similar(self.item,**options)

    def test_result_session_invalidates_if_origin_changes_after_capture(self):
        self.seed();self.add_item();search=AudioDirectSimilarity(self.index)
        sessions=ResultSessions(self.catalog,lambda conditions,consume,cancelled:search.similar(self.item,result_sink=consume,cancelled=cancelled),index_stamp=IndexStamp(self.index),parent=self.stage)
        try:
            sessions.create('a'*32,{'mode':'audio-similar','item_id':self.item})
            self.assertEqual(sessions.read('a'*32,0,1)['items'][0]['origin_match_ms'],0)
            self.path.write_bytes(b'changed generated origin')
            with self.assertRaises(ResultUnavailable):sessions.read('a'*32,0,1)
        finally:sessions.close()

    def test_previous_candidate_vectors_are_released_before_next_load(self):
        self.seed();self.add_item();third,_=self.add_item('third.wav')
        search=AudioDirectSimilarity(self.index);original=search._frames;previous=[];checked=[]
        def tracking(row,db,check):
            if row['id']!=self.item and previous:
                checked.append(row['id'])
                self.assertTrue(all(ref() is None for ref in previous))
            revision,frames=original(row,db,check)
            if row['id']!=self.item:previous[:]=[weakref.ref(frame[2]) for frame in frames]
            return revision,frames
        with patch.object(search,'_frames',side_effect=tracking):
            self.assertEqual(search.similar(self.item)['total'],2)
        self.assertEqual(checked,[third])

    def test_candidate_change_during_range_reports_refresh_conflict(self):
        self.seed();self.add_item()
        def changed(read):
            read(0);(self.media/'second.wav').write_bytes(b'changed generated candidate');return read(0)
        with self.assertRaises(AudioSearchChanged):
            AudioDirectSimilarity(self.index).similar(self.item,result_sink=changed)
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_corrupt_marker_types_and_frame_totals_are_excluded(self):
        self.seed();second,_=self.add_item();search=AudioDirectSimilarity(self.index)
        for item in (self.item,second):
            revision=self.reader.audio_manifest(item)['revision']
            for field,value in (('decoded_windows','bad'),('decoded_windows',1.5),
                                ('indexed_windows','bad'),('total_frames','bad'),
                                ('total_frames',496000.5),('total_frames',960001),
                                ('decoded_windows',3)):
                with self.subTest(item=item,field=field,value=value):
                    with self.supplied():self.index.index_item(item,revision)
                    with self.index.store.connect() as db:
                        db.execute('UPDATE ai_audio_direct_sources SET '+field+'=? WHERE item_id=?',(value,item))
                    result=search.similar(self.item)
                    self.assertEqual(result['total'],0)
                    self.assertEqual(list(self.stage.iterdir()),[])
            with self.supplied():self.index.index_item(item,revision)

    def test_corrupt_window_types_intervals_and_vectors_are_excluded(self):
        self.seed();second,_=self.add_item();search=AudioDirectSimilarity(self.index)
        for item in (self.item,second):
            revision=self.reader.audio_manifest(item)['revision']
            for field,value in (('ordinal',1.5),('ordinal','bad'),('start_ms','bad'),
                                ('start_ms',30000.5),('end_ms','bad'),('end_ms',30999),
                                ('end_ms',31000.5),('end_ms',31001),
                                ('vector',b'broken'),('vector',b'\0'*12),
                                ('vector',bytes.fromhex('0000c07f0000000000000000'))):
                with self.subTest(item=item,field=field,value=value):
                    with self.supplied():self.index.index_item(item,revision)
                    with self.index.store.connect() as db:
                        db.execute('UPDATE ai_audio_direct_windows SET '+field+'=? WHERE item_id=? AND ordinal=1',(value,item))
                    result=search.similar(self.item)
                    self.assertEqual(result['total'],0)
                    self.assertEqual(list(self.stage.iterdir()),[])
            with self.supplied():self.index.index_item(item,revision)

    def test_skipped_silent_window_keeps_correct_ordinal_and_time(self):
        from audio_input import PCMWindow
        silent=PCMWindow(0,30000,b'\0'*(480000*4))
        with self.supplied([silent,self.windows[1]]):self.index.index_item(self.item,self.revision)
        second,_=self.add_item()
        result=AudioDirectSimilarity(self.index).similar(self.item)
        self.assertEqual(result['total'],1)
        self.assertEqual(result['items'][0]['origin_match_ms'],30000)
        self.assertEqual(result['items'][0]['id'],second)

    def test_pair_limit_accepts_exact_boundary_and_rejects_overflow(self):
        self.seed();second,_=self.add_item();search=AudioDirectSimilarity(self.index)
        with patch('audio_direct_similarity.MAX_PAIRS',4,create=True):
            result=search.similar(self.item)
        self.assertEqual([row['id'] for row in result['items']],[second])
        with patch('audio_direct_similarity.MAX_PAIRS',3,create=True):
            with self.assertRaisesRegex(AIUnavailable,'フォルダーや棚'):
                search.similar(self.item)
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_pair_limit_accumulates_candidates_without_publishing_partial_results(self):
        self.seed();self.add_item();self.add_item('third.wav');published=[]
        with patch('audio_direct_similarity.MAX_PAIRS',7,create=True):
            with self.assertRaises(AIUnavailable):
                AudioDirectSimilarity(self.index).similar(self.item,result_sink=published.append)
        self.assertEqual(published,[])
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_pair_limit_counts_only_indexed_candidates_in_scope(self):
        self.seed();second,_=self.add_item();third,_=self.add_item('third.wav')
        self.catalog.update([second],{'favorite':True});search=AudioDirectSimilarity(self.index)
        with patch('audio_direct_similarity.MAX_PAIRS',4,create=True):
            self.assertEqual(search.similar(self.item,view='favorites')['total'],1)
            with self.index.store.connect() as db:
                db.execute('DELETE FROM ai_audio_direct_sources WHERE item_id=?',(third,))
            result=search.similar(self.item)
            self.assertEqual((result['total'],result['candidate_total'],result['indexed_total']),(1,2,1))



if __name__=='__main__':unittest.main()
