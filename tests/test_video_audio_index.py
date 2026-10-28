"""Generated video audio: atomic storage and scoped text retrieval, no model."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import shutil
import sys
import threading
import unittest
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_video_audio_source as fixture
from test_audio_input import wav_bytes
from ai_profiles import audio_profile_for,video_profile_for
from audio_direct_index import AudioDirectIndex
from audio_direct_search import AudioDirectSearch,AudioSearchChanged
from audio_direct_similarity import AudioDirectSimilarity
from audio_input import AudioInputUnavailable
from live_backup import capture_live,BackupSelection
from storage_backup import restore
from video_previews import MediaDecodeCancelled


class Encoder:
    profile=replace(audio_profile_for(),dimension=3)
    def __init__(self):self.calls=[]
    def encode(self,operation,value):self.calls.append(operation);return [1,0,0]


class VideoAudioIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.VideoAudioSourceTests.setUpClass()
    @classmethod
    def tearDownClass(cls):fixture.VideoAudioSourceTests.tearDownClass()
    def setUp(self):
        self.sound=fixture.VideoAudioSourceTests.sound
        fixture.VideoAudioSourceTests.setUp(self)
        self.encoder=Encoder();self.stage=self.base/'stages';self.stage.mkdir()
        self.index=AudioDirectIndex(self.catalog,self.encoder,reader=self.reader,stage_parent=self.stage,source_kind='video')
    def snapshot(self):
        with self.index.store.connect() as db:
            return [db.execute('SELECT * FROM '+table+' ORDER BY item_id,ordinal' if table.endswith('windows') else 'SELECT * FROM '+table+' ORDER BY item_id').fetchall()
                    for table in ('ai_audio_direct_sources','ai_audio_direct_windows')]
    def seed(self):return self.index.index_item(self.item,self.revision)

    def test_video_audio_storage_and_search_keep_video_identity_and_explicit_provenance(self):
        report=self.seed();self.assertEqual((report['decoded_windows'],report['indexed_windows']),(1,1))
        self.assertTrue(self.index.fresh(self.item,self.revision))
        result=AudioDirectSearch(self.index).search('生成した音声')
        self.assertEqual((result['source'],result['total'],result['indexed_total']),('video-audio-direct',1,1))
        row=result['items'][0]
        self.assertEqual((row['id'],row['kind'],row['audio_match_source']),(self.item,'video','video-audio'))
        self.assertEqual((row['audio_match_ms'],row['audio_match_end_ms']),(0,(report['total_frames']*1000+15999)//16000))
        self.assertEqual(self.encoder.calls,['audio','query'])
        self.assertFalse(replace(video_profile_for(),dimension=3).store_path(self.catalog.path).exists())
        self.assertEqual(list(self.stage.iterdir()),[])
        with self.assertRaises(ValueError):AudioDirectSimilarity(self.index)

    def test_audio_file_and_video_audio_searches_are_separate_in_the_same_pcm_profile(self):
        self.seed();(self.media/'generated.wav').write_bytes(wav_bytes())
        self.catalog.index.scan(self.root);self.catalog.sync_index()
        audio=next(row['id'] for row in self.catalog.search()['items'] if row['kind']=='audio')
        normal=AudioDirectIndex(self.catalog,self.encoder,reader=self.reader,stage_parent=self.stage)
        normal.index_item(audio,self.reader.audio_manifest(audio)['revision'])
        self.assertEqual(normal.store.path,self.index.store.path)
        self.assertEqual([r['id'] for r in AudioDirectSearch(normal).search('audio')['items']],[audio])
        search=AudioDirectSearch(self.index)
        self.assertEqual([r['id'] for r in search.search('audio')['items']],[self.item])
        self.assertEqual(search.search('audio',view='favorites')['total'],0)
        self.catalog.update([self.item],{'favorite':True})
        shelf=self.catalog.change_shelf('create',name='generated video audio')['id']
        self.catalog.change_shelf('assign',entity='item',object_ids=[self.item],shelf_ids=[shelf])
        self.assertEqual(search.search('audio',view='favorites',root_ids=[self.root],shelf_ids=[shelf])['total'],1)
        self.assertEqual(AudioDirectSearch(normal).search('audio',view='favorites')['total'],0)

    def test_cancelled_video_audio_rebuild_keeps_old_data_and_releases_pcm_slot(self):
        self.seed();previous=self.snapshot();stop=threading.Event()
        def cancel(*args):stop.set();return [0,1,0]
        with patch.object(self.encoder,'encode',side_effect=cancel),self.assertRaises(MediaDecodeCancelled):
            self.index.index_item(self.item,self.revision,cancel=stop)
        self.assertEqual(self.snapshot(),previous);self.assertEqual(list(self.stage.iterdir()),[])
        self.assertTrue(self.reader.audio_stream_slot.acquire(blocking=False));self.reader.audio_stream_slot.release()

    def test_missing_track_during_rebuild_cannot_publish_a_silence_success_marker(self):
        self.seed();previous=self.snapshot()
        shutil.copyfile(fixture.VideoAudioSourceTests.silent,self.path)
        self.catalog.index.scan(self.root);self.catalog.sync_index()
        revision=self.reader.video_manifest(self.item)['revision']
        with self.assertRaises(AudioInputUnavailable):self.index.index_item(self.item,revision)
        self.assertEqual(self.snapshot(),previous);self.assertFalse(self.index.fresh(self.item,revision))
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_video_audio_range_detects_changed_source(self):
        self.seed()
        def changed(read):
            read(0);self.path.write_bytes(b'changed generated video');return read(0)
        with self.assertRaises(AudioSearchChanged):AudioDirectSearch(self.index).search('audio',result_sink=changed)

    def test_video_audio_backup_roundtrip_and_root_purge_keep_source_media(self):
        self.seed();previous=self.snapshot();before=self.path.read_bytes();bundle=self.base/'backup'
        capture_live(self.catalog,bundle,quiesce=self.catalog.writer_fence.pause,
                     selection=BackupSelection(settings=False,history=True,reader_progress=True,vectors=True))
        destination=self.base/'restored';restore(bundle,destination)
        with closing(sqlite3.connect(self.encoder.profile.store_path(destination/'catalog.sqlite'))) as db:
            self.assertEqual(db.execute('SELECT * FROM ai_audio_direct_sources').fetchall(),previous[0])
            self.assertEqual(db.execute('SELECT * FROM ai_audio_direct_windows').fetchall(),previous[1])
        self.catalog.unregister_root(self.root);self.catalog.purge_inactive_root(self.root,consent=True)
        self.assertEqual(self.snapshot(),[[],[]]);self.assertEqual(self.path.read_bytes(),before)


if __name__=='__main__':unittest.main()
