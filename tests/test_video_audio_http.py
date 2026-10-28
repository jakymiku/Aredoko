"""Owned authenticated video-audio API with generated sources and fake encoder."""
from pathlib import Path
import shutil
import sys
import threading
import unittest
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_audio_direct_http as audio_fixture
import test_video_audio_source as video_fixture


class VideoAudioHTTPTests(unittest.TestCase):
    request=audio_fixture.AudioHTTPTests.request
    stop=audio_fixture.AudioHTTPTests.stop
    supplied=audio_fixture.AudioHTTPTests.supplied
    @classmethod
    def setUpClass(cls):video_fixture.VideoAudioSourceTests.setUpClass()
    @classmethod
    def tearDownClass(cls):video_fixture.VideoAudioSourceTests.tearDownClass()
    def setUp(self):
        audio_fixture.AudioHTTPTests.setUp(self)
        shutil.copyfile(video_fixture.VideoAudioSourceTests.sound,self.media/'voice.mkv')
        shutil.copyfile(video_fixture.VideoAudioSourceTests.silent,self.media/'no-track.mkv')
        self.catalog.index.scan(self.root);self.catalog.sync_index()
        self.video=next(r['id'] for r in self.catalog.search()['items'] if r['title']=='voice.mkv')
        self.no_track=next(r['id'] for r in self.catalog.search()['items'] if r['title']=='no-track.mkv')
    def start(self,route='video-audio-ai',limit=1):
        code,_=self.request('/api/library/'+route+'/start',{'consent':True,'limit':limit});self.assertEqual(code,200)
        self.feature.owner.thread.join(5);self.assertFalse(self.feature.owner.thread.is_alive())
        self.assertEqual(self.feature.status()['state'],'completed')

    def test_status_auth_strict_start_and_scope_are_lazy(self):
        self.assertEqual(self.request('/api/library/video-audio-ai/status',authorized=False)[0],403)
        self.assertEqual(self.request('/api/library/video-audio-ai/start',{'consent':True},authorized=False)[0],403)
        code,status=self.request('/api/library/video-audio-ai/status');self.assertEqual(code,200)
        self.assertFalse(status['initialized']);self.assertIsNone(self.feature.owner)
        for body in ({'consent':False},{'consent':True,'source_kind':'audio'},{'consent':True,'conditions':{'root_ids':[999]}},{'consent':True,'limit':0}):
            self.assertEqual(self.request('/api/library/video-audio-ai/start',body)[0],400)
        self.assertEqual(self.request('/api/library/video-audio-ai/start',raw=b'{"consent":true,"consent":false}')[0],400)
        self.assertIsNone(self.feature.owner);self.assertEqual(self.feature.encoder.calls,0)

    def test_owned_batch_skips_trackless_video_and_shares_one_owner_with_audio_files(self):
        self.start();owner=self.feature.owner;encoder=self.feature.encoder
        self.assertEqual((self.feature.status()['source_kind'],self.feature.status()['indexed']),('video',1))
        self.start();status=self.feature.status()
        self.assertEqual((status['target'],status['reused'],status['unavailable']),(0,1,1))
        with owner.index.store.connect() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM ai_audio_direct_sources WHERE item_id=?',(self.no_track,)).fetchone())
        code,result=self.request('/api/library/video-audio-ai/search',{'query':'tone','root_ids':[self.root]})
        self.assertEqual(code,200);self.assertEqual(result['source'],'video-audio-direct')
        self.assertEqual([(r['id'],r['kind'],r['audio_match_source']) for r in result['items']],[(self.video,'video','video-audio')])
        self.assertEqual(self.request('/api/library/audio-ai/search',{'query':'tone'})[1]['total'],0)
        self.start('audio-ai')
        self.assertIs(self.feature.owner,owner);self.assertIs(self.feature.encoder,encoder)
        self.assertEqual(self.feature.status()['source_kind'],'audio')
        self.assertEqual([r['id'] for r in self.request('/api/library/audio-ai/search',{'query':'tone'})[1]['items']],[self.item])
        self.assertEqual(self.request('/api/library/video-audio-ai/search',{'query':'tone'})[1]['items'][0]['id'],self.video)
        with patch.object(encoder,'close',wraps=encoder.close) as closed:
            self.feature.close();self.feature.close();self.assertEqual(closed.call_count,1)

    def test_video_audio_cancel_cannot_cancel_an_audio_file_job(self):
        ready=threading.Event();proceed=threading.Event();encode=self.feature.encoder.encode
        def paused(*args):
            ready.set()
            if not proceed.wait(3):raise RuntimeError('generated wait timed out')
            return encode(*args)
        with patch.object(self.feature.encoder,'encode',side_effect=paused):
            try:
                self.assertEqual(self.request('/api/library/audio-ai/start',{'consent':True})[0],200)
                self.assertTrue(ready.wait(3))
                code,reply=self.request('/api/library/video-audio-ai/cancel',{})
                self.assertEqual(code,200);self.assertFalse(reply['cancel_requested']);self.assertEqual(reply['state'],'running')
                self.assertEqual(self.request('/api/library/video-audio-ai/start',{'consent':True})[0],409)
                self.assertTrue(self.request('/api/library/audio-ai/cancel',{})[1]['cancel_requested'])
            finally:proceed.set()
            self.feature.owner.thread.join(5)
        self.assertEqual(self.feature.status()['state'],'cancelled')

    def test_trackless_batch_never_activates_encoder(self):
        (self.media/'voice.mkv').unlink();self.catalog.index.scan(self.root);self.catalog.sync_index()
        self.start();status=self.feature.status()
        self.assertEqual((status['target'],status['indexed'],status['unavailable']),(0,0,1))
        self.assertEqual(self.feature.encoder.calls,0)

    def test_video_cancel_rolls_back_and_fresh_reuse_needs_no_native_probe(self):
        self.start();owner=self.feature.owner
        with patch.object(owner.index.reader,'video_audio_available',return_value=False) as probed:
            self.start();self.assertEqual([call.args[0] for call in probed.call_args_list],[self.no_track])
        ready=threading.Event();proceed=threading.Event();encode=self.feature.encoder.encode
        # Make a fresh revision so the old committed item remains until replacement.
        path=self.media/'voice.mkv';info=path.stat()
        import os
        os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns+1000000000))
        self.catalog.index.scan(self.root);self.catalog.sync_index()
        with owner.index.store.connect() as db:
            before=[tuple(r) for r in db.execute('SELECT * FROM ai_audio_direct_sources WHERE item_id=?',(self.video,))]
        def paused(*args):
            ready.set()
            if not proceed.wait(5):raise RuntimeError('generated wait timed out')
            return encode(*args)
        with patch.object(self.feature.encoder,'encode',side_effect=paused):
            try:
                self.assertEqual(self.request('/api/library/video-audio-ai/start',{'consent':True})[0],200)
                self.assertTrue(ready.wait(3))
                self.assertTrue(self.request('/api/library/video-audio-ai/cancel',{})[1]['cancel_requested'])
            finally:proceed.set()
            owner.thread.join(5)
        self.assertEqual(self.feature.status()['state'],'cancelled')
        self.assertIsNone(self.feature.status()['item_progress'])
        with owner.index.store.connect() as db:
            self.assertEqual(before,[tuple(r) for r in db.execute('SELECT * FROM ai_audio_direct_sources WHERE item_id=?',(self.video,))])

    def test_frozen_video_audio_results_use_audio_stamp_and_guard_video_source(self):
        self.start()
        self.assertEqual(self.request('/api/library/results/create',{'session_id':'a'*32,'conditions':{'mode':'literal'}})[0],200)
        self.assertEqual(self.request('/api/library/results/create',{'session_id':'b'*32,'conditions':{'mode':'video-audio-direct','query':'tone','root_ids':[self.root]}})[0],200)
        code,result=self.request('/api/library/results/range',{'session_id':'b'*32,'offset':0,'limit':1})
        self.assertEqual(code,200);self.assertEqual(result['source'],'video-audio-direct')
        self.assertEqual(result['items'][0]['audio_match_source'],'video-audio')
        with self.feature.owner.index.store.connect() as db:
            db.execute('UPDATE ai_audio_direct_sources SET indexed_windows=0 WHERE item_id=?',(self.video,))
        self.assertEqual(self.request('/api/library/results/range',{'session_id':'b'*32,'offset':0,'limit':1})[0],409)
        self.assertEqual(self.request('/api/library/results/range',{'session_id':'a'*32,'offset':0,'limit':1})[0],200)


if __name__=='__main__':unittest.main()
