"""Generated video sources and supplied embeddings; no model or GPU."""
from pathlib import Path
import shutil
import sys
import threading
import unittest
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_video_audio_index as fixture
from test_audio_input import wav_bytes
from audio_direct_index import AudioDirectIndex
from audio_direct_similarity import AudioDirectSimilarity
from audio_direct_search import AudioSearchChanged
from video_audio_similarity import VideoAudioSimilarity
from ai_score_spool import SearchCancelled
from ai_process import AIUnavailable
from result_sessions import ResultSessions,IndexStamp,ResultUnavailable


class VideoAudioSimilarityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.VideoAudioIndexTests.setUpClass()
    @classmethod
    def tearDownClass(cls):fixture.VideoAudioIndexTests.tearDownClass()
    setUp=fixture.VideoAudioIndexTests.setUp
    seed=fixture.VideoAudioIndexTests.seed

    def add_video(self,name='second.mkv',vector=None,other_root=False,indexed=True):
        media=self.base/'other' if other_root else self.media
        media.mkdir(exist_ok=True);shutil.copyfile(self.sound,media/name)
        root=self.catalog.add_root(str(media)) if other_root else self.root
        self.catalog.index.scan(root);self.catalog.sync_index()
        item=next(row['id'] for row in self.catalog.search()['items'] if row['title']==name)
        if indexed:
            with patch.object(self.encoder,'encode',return_value=vector or [1,0,0]):
                self.index.index_item(item,self.reader.video_manifest(item)['revision'])
        return item,root

    def test_cached_video_pairs_keep_namespaces_intervals_and_stable_pages(self):
        self.seed();second,_=self.add_video(vector=[0,1,0]);third,_=self.add_video('third.mkv')
        (self.media/'audio.wav').write_bytes(wav_bytes());self.catalog.index.scan(self.root);self.catalog.sync_index()
        audio=next(r['id'] for r in self.catalog.search()['items'] if r['kind']=='audio')
        normal=AudioDirectIndex(self.catalog,self.encoder,reader=self.reader)
        normal.index_item(audio,self.reader.audio_manifest(audio)['revision'])
        with (patch.object(self.encoder,'encode',side_effect=AssertionError('cached similarity inferred')),
              patch.object(self.reader,'video_audio_pcm_stream',side_effect=AssertionError('cached similarity decoded'))):
            pages=VideoAudioSimilarity(self.index).similar(self.item,limit=1,result_sink=lambda read:[read(0),read(1)])
        self.assertEqual([p['items'][0]['id'] for p in pages],[third,second])
        for page in pages:
            self.assertEqual((page['mode'],page['source'],page['origin_kind']),('video-audio-similar','video-audio-direct','video'))
            row=page['items'][0]
            self.assertEqual((row['kind'],row['audio_match_source'],row['similarity_origin_id']),('video','video-audio',self.item))
            self.assertEqual((row['origin_match_ms'],row['audio_match_ms']),(0,0))
            self.assertGreater(row['origin_match_end_ms'],0);self.assertGreater(row['audio_match_end_ms'],0)
            self.assertEqual(page['candidate_total'],2);self.assertNotIn('video_match_ms',row);self.assertNotIn('audio_match_snippet',row)
        self.assertEqual(list(self.stage.iterdir()),[])
        with self.assertRaises(ValueError):AudioDirectSimilarity(self.index)
        with self.assertRaises(ValueError):VideoAudioSimilarity(normal)
        with self.assertRaises(KeyError):VideoAudioSimilarity(self.index).similar(audio)

    def test_candidates_favorite_but_origin_root_shelf_and_exclusion_guards(self):
        self.seed();second,root=self.add_video(other_root=True);search=VideoAudioSimilarity(self.index)
        self.catalog.update([second],{'favorite':True})
        self.assertEqual(search.similar(self.item,view='favorites')['items'][0]['id'],second)
        with self.assertRaises(KeyError):search.similar(self.item,root_ids=[root])
        shelf=self.catalog.change_shelf('create',name='video audio fixture')['id']
        self.catalog.change_shelf('assign',entity='item',object_ids=[second],shelf_ids=[shelf])
        with self.assertRaises(KeyError):search.similar(self.item,shelf_ids=[shelf])
        self.catalog.set_excludes(root,['*.mkv']);self.assertEqual(search.similar(self.item)['total'],0)

    def test_missing_or_corrupt_pcm_never_uses_rgb_or_partial_windows(self):
        second,_=self.add_video();search=VideoAudioSimilarity(self.index)
        self.assertEqual(search.similar(self.item)['similarity_status'],'unindexed')
        self.seed()
        with self.index.store.connect() as db:db.execute('UPDATE ai_audio_direct_sources SET indexed_windows=2 WHERE item_id=?',(second,))
        self.assertEqual(search.similar(self.item)['total'],0)
        with self.index.store.connect() as db:db.execute('UPDATE ai_audio_direct_windows SET vector=? WHERE item_id=?',(b'bad',self.item))
        self.assertEqual(search.similar(self.item)['similarity_status'],'unindexed')

    def test_cancel_and_pair_limit_publish_no_partial_ranking(self):
        self.seed();self.add_video();published=[];stop=threading.Event()
        from ai_vectors import dot
        def cancelled(*args):stop.set();return dot(*args)
        with patch('audio_direct_similarity.dot',side_effect=cancelled),self.assertRaises(SearchCancelled):
            VideoAudioSimilarity(self.index).similar(self.item,result_sink=published.append,cancelled=stop.is_set)
        self.assertEqual(published,[]);self.assertEqual(list(self.stage.iterdir()),[])
        with patch('audio_direct_similarity.MAX_PAIRS',0),self.assertRaises(AIUnavailable):
            VideoAudioSimilarity(self.index).similar(self.item,result_sink=published.append)
        self.assertEqual(published,[])

    def test_live_source_or_pcm_stamp_changes_reject_old_ranges(self):
        self.seed();self.add_video();search=VideoAudioSimilarity(self.index)
        def changed(read):
            read(0)
            with self.index.store.connect() as db:db.execute('UPDATE ai_audio_direct_sources SET indexed_windows=0')
            return read(0)
        with self.assertRaises(AudioSearchChanged):search.similar(self.item,result_sink=changed)
        self.seed()
        stamp=IndexStamp(self.index)
        sessions=ResultSessions(self.catalog,lambda conditions,consume,cancelled:search.similar(self.item,result_sink=consume,cancelled=cancelled),index_stamp=stamp,parent=self.stage)
        try:
            sessions.create('a'*32,{'mode':'video-audio-similar','item_id':self.item})
            self.path.write_bytes(b'changed generated video')
            with self.assertRaises(ResultUnavailable):sessions.read('a'*32,0,1)
        finally:sessions.close();stamp.close()


if __name__=='__main__':unittest.main()
