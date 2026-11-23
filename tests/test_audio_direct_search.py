"""Scoped retrieval over supplied direct audio vectors; no GPU/quality claim."""
import sys
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_audio_direct_index as fixture
from audio_direct_search import AudioDirectSearch,AudioSearchChanged
from ai_score_spool import SearchCancelled
from result_sessions import ResultSessions,IndexStamp,ResultUnavailable


class AudioDirectSearchTests(unittest.TestCase):
    setUp=fixture.DirectAudioIndexTests.setUp
    supplied=fixture.DirectAudioIndexTests.supplied
    seed=fixture.DirectAudioIndexTests.seed
    snapshot=fixture.DirectAudioIndexTests.snapshot

    def add_item(self,name='second.wav',*,other_root=False,vector=None):
        directory=self.base/'other-media' if other_root else self.media
        directory.mkdir(exist_ok=True);(directory/name).write_bytes(fixture.wav_bytes())
        root=self.catalog.add_root(str(directory)) if other_root else self.root
        self.catalog.index.scan(root);self.catalog.sync_index()
        item=next(row['id'] for row in self.catalog.search()['items'] if row['title']==name)
        revision=self.reader.audio_manifest(item)['revision']
        with self.supplied(),patch.object(self.encoder,'encode',return_value=vector or [1,0,0]):
            self.index.index_item(item,revision)
        return item,root

    def test_text_query_has_best_time_without_invented_transcript(self):
        with self.supplied(),patch.object(self.encoder,'encode',side_effect=[[0,1,0],[1,0,0]]):
            self.index.index_item(self.item,self.revision)
        with patch.object(self.encoder,'encode',return_value=[1,0,0]) as encode:
            result=AudioDirectSearch(self.index).search('生成した音声の特徴')
        self.assertEqual(encode.call_count,1);self.assertEqual(encode.call_args.args,('query','生成した音声の特徴'))
        self.assertEqual(result['total'],1);row=result['items'][0]
        self.assertEqual((row['id'],row['audio_match_ms'],row['audio_match_end_ms']),(self.item,30000,31000))
        self.assertEqual(row['audio_match_source'],'direct-audio');self.assertNotIn('audio_match_snippet',row)
        self.assertEqual(row['semantic_score'],1)

    def test_common_favorite_shelf_root_and_exclusion_filters_are_preserved(self):
        self.seed();other,root=self.add_item(other_root=True)
        self.catalog.update([other],{'favorite':True})
        shelf=self.catalog.change_shelf('create',name='生成音声')
        self.catalog.change_shelf('assign',entity='item',object_ids=[other],shelf_ids=[shelf['id']])
        search=AudioDirectSearch(self.index)
        for conditions in ({'view':'favorites'},{'root_ids':[root]},{'shelf_ids':[shelf['id']]},
                           {'view':'favorites','root_ids':[root],'shelf_ids':[shelf['id']]}):
            with self.subTest(conditions=conditions):
                self.assertEqual([row['id'] for row in search.search('audio',**conditions)['items']],[other])
        self.catalog.set_excludes(root,['*.wav'])
        self.assertEqual(search.search('audio',root_ids=[root])['total'],0)

    def test_range_sink_reuses_ranking_and_stable_id_ties(self):
        self.seed();second,_=self.add_item();third,_=self.add_item('third.wav')
        def consume(fetch):return [fetch(0),fetch(1),fetch(2)]
        with patch.object(self.encoder,'encode',return_value=[1,0,0]) as encode:
            pages=AudioDirectSearch(self.index).search('audio',limit=1,result_sink=consume)
        self.assertEqual(encode.call_count,1)
        self.assertEqual([page['items'][0]['id'] for page in pages],[self.item,second,third])
        self.assertTrue(all(page['total']==3 for page in pages));self.assertEqual(list(self.stage.iterdir()),[])

    def test_silent_or_stale_sources_are_not_false_matches(self):
        self.seed();self.path.write_bytes(b'changed generated source')
        self.assertEqual(AudioDirectSearch(self.index).search('audio')['total'],0)

    def test_successful_silence_is_indexed_without_becoming_a_search_match(self):
        silent=[fixture.PCMWindow(0,30000,b'\0'*(480000*4))]
        with self.supplied(silent):self.index.index_item(self.item,self.revision)
        result=AudioDirectSearch(self.index).search('audio')
        self.assertEqual((result['total'],result['indexed_total'],result['search_status']),(0,1,'ready'))

    def test_corrupt_item_is_excluded_whole_while_valid_candidates_remain_searchable(self):
        second,_=self.add_item();search=AudioDirectSearch(self.index)
        statements=[
            "UPDATE ai_audio_direct_sources SET decoded_windows='bad' WHERE item_id=?",
            "UPDATE ai_audio_direct_sources SET indexed_windows='bad' WHERE item_id=?",
            "UPDATE ai_audio_direct_sources SET total_frames='bad' WHERE item_id=?",
            'UPDATE ai_audio_direct_sources SET decoded_windows=3 WHERE item_id=?',
            'UPDATE ai_audio_direct_sources SET total_frames=496000.5 WHERE item_id=?',
            'UPDATE ai_audio_direct_sources SET indexed_windows=0 WHERE item_id=?',
            'DELETE FROM ai_audio_direct_windows WHERE item_id=? AND ordinal=1',
            'UPDATE ai_audio_direct_windows SET ordinal=2 WHERE item_id=? AND ordinal=1',
            "UPDATE ai_audio_direct_windows SET start_ms='bad' WHERE item_id=? AND ordinal=1",
            'UPDATE ai_audio_direct_windows SET start_ms=30000.5 WHERE item_id=? AND ordinal=1',
            'UPDATE ai_audio_direct_windows SET end_ms=30999 WHERE item_id=? AND ordinal=1',
            'UPDATE ai_audio_direct_windows SET end_ms=31001 WHERE item_id=? AND ordinal=1',
            "UPDATE ai_audio_direct_windows SET vector=x'000000000000000000000000' WHERE item_id=? AND ordinal=1",
            "UPDATE ai_audio_direct_windows SET vector=x'0000c07f0000000000000000' WHERE item_id=? AND ordinal=1",
            "UPDATE ai_audio_direct_windows SET vector=x'00' WHERE item_id=? AND ordinal=1",
        ]
        for statement in statements:
            with self.subTest(statement=statement):
                self.seed()
                with self.index.store.connect() as db:db.execute(statement,(self.item,))
                result=search.search('audio')
                self.assertEqual([row['id'] for row in result['items']],[second])
                self.assertEqual((result['indexed_total'],result['search_status']),(1,'partially_indexed'))
                self.assertEqual(list(self.stage.iterdir()),[])

    def test_silent_window_gap_is_valid_and_keeps_the_later_match_time(self):
        silent=fixture.PCMWindow(0,30000,b'\0'*(480000*4))
        with self.supplied([silent,self.windows[1]]):self.index.index_item(self.item,self.revision)
        result=AudioDirectSearch(self.index).search('audio')
        self.assertEqual((result['indexed_total'],result['search_status']),(1,'ready'))
        self.assertEqual(result['items'][0]['audio_match_ms'],30000)

    def test_matched_source_unavailable_during_range_reports_refresh_conflict(self):
        self.seed()
        def changed(read):
            read(0);self.path.write_bytes(b'changed generated source');return read(0)
        with self.assertRaises(AudioSearchChanged):AudioDirectSearch(self.index).search('audio',result_sink=changed)
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_empty_scope_and_invalid_conditions_do_not_load_encoder(self):
        self.seed()
        with patch.object(self.encoder,'encode') as encode:
            self.assertEqual(AudioDirectSearch(self.index).search('audio',view='favorites')['candidate_total'],0)
            with self.assertRaises(ValueError):AudioDirectSearch(self.index).search('audio',root_ids=[999])
            with self.assertRaises(ValueError):AudioDirectSearch(self.index).search('audio',kind='image')
            encode.assert_not_called()

    def test_scope_or_namespace_write_during_query_discards_results(self):
        self.seed()
        def changed(*args):self.catalog.update([self.item],{'favorite':True});return [1,0,0]
        with patch.object(self.encoder,'encode',side_effect=changed),self.assertRaises(AudioSearchChanged):
            AudioDirectSearch(self.index).search('audio')
        def index_changed(*args):
            with self.index.store.connect() as db:db.execute('UPDATE ai_audio_direct_sources SET total_frames=1')
            return [1,0,0]
        with patch.object(self.encoder,'encode',side_effect=index_changed),self.assertRaises(AudioSearchChanged):
            AudioDirectSearch(self.index).search('audio')
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_cancel_during_query_discards_spool(self):
        self.seed();event=threading.Event()
        def cancelled(*args):event.set();return [1,0,0]
        with patch.object(self.encoder,'encode',side_effect=cancelled),self.assertRaises(SearchCancelled):
            AudioDirectSearch(self.index).search('audio',cancelled=event.is_set)
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_result_session_keeps_audio_time_and_invalidates_on_index_update(self):
        self.seed();self.add_item();search=AudioDirectSearch(self.index)
        def provider(conditions,consume,cancelled):
            return search.search(conditions['query'],result_sink=consume,cancelled=cancelled)
        owner=ResultSessions(self.catalog,provider,index_stamp=IndexStamp(self.index),parent=self.stage)
        try:
            with patch.object(self.encoder,'encode',return_value=[1,0,0]) as encode:
                owner.create('a'*32,{'mode':'semantic','query':'audio'})
                first=owner.read('a'*32,0,1)['items'][0]
                self.assertEqual(first['audio_match_ms'],0)
                owner.read('a'*32,1,1)
                self.assertEqual(encode.call_count,1)
            with self.index.store.connect() as db:db.execute('UPDATE ai_audio_direct_sources SET indexed_windows=0')
            with self.assertRaises(ResultUnavailable):owner.read('a'*32,0,1)
        finally:self.assertTrue(owner.close())


if __name__=='__main__':unittest.main()
