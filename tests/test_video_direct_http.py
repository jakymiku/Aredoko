"""Authenticated direct-video production routes over generated inputs."""
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys,threading,types,unittest
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_video_direct_index as fixture
import test_audio_direct_http as audio_fixture
from ai_profiles import DEFAULT_PROFILE
from ai_settings import AIProfileSettings
from inference_ownership import InferenceOwnership
from production_server import production_handler,DisabledAI
from video_direct_feature import VideoDirectFeature
from video_direct_jobs import VideoDirectJobs
from wd_tagger import DisabledTagger

class Encoder:
    available=True
    def __init__(self,profile=None):self.profile=profile;self.resident=False;self.calls=0
    def encode(self,*args):self.calls+=1;self.resident=True;return [1,0,0]
    def release(self):self.resident=False;return {'released':True,'resident':False}
    def close(self):self.resident=False

class VideoHTTPTests(unittest.TestCase):
    supplied=fixture.SuppliedIndexTests.supplied
    request=audio_fixture.AudioHTTPTests.request
    def setUp(self):
        fixture.SuppliedIndexTests.setUp(self)
        group=InferenceOwnership();vision=Encoder();group.for_encoder(vision)
        image=types.SimpleNamespace(profile=replace(DEFAULT_PROFILE,dimension=3),encoder=vision,inference_group=group)
        self.feature=VideoDirectFeature(self.catalog,image,encoder_factory=Encoder,stage_parent=self.stage)
        self.addCleanup(self.feature.close)
        def owner(catalog,encoder,**opts):return VideoDirectJobs(catalog,encoder,**{**opts,'reader':self.reader})
        patched=patch('video_direct_feature.VideoDirectJobs',side_effect=owner);patched.start();self.addCleanup(patched.stop)
        profiles=AIProfileSettings(self.base,self.base/'settings.json',profile_directory=self.base/'profiles',ai_python=str(self.base/'missing-python'),models_root=self.base/'models')
        self.token='test-video-session'
        self.handler=production_handler(self.catalog,self.token,ai=DisabledAI(),profiles=profiles,tagger=DisabledTagger(),video_feature=self.feature)
        self.handler.log_message=lambda *args:None
        self.server=ThreadingHTTPServer(('127.0.0.1',0),self.handler);self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base_url='http://127.0.0.1:'+str(self.server.server_port);self.addCleanup(self.stop)
    def stop(self):
        self.server.shutdown();self.server.server_close();self.thread.join(3)
        for name in ('results','startup_scans','setup_jobs','download_jobs','animations','thumbnails','backup_jobs','restore_jobs','audio_content'):
            getattr(self.handler,name).close()
    def prepare(self):
        with self.supplied():
            code,_=self.request('/api/library/video-ai/start',{'consent':True});self.assertEqual(code,200)
            self.feature.owner.thread.join(5)
        self.assertEqual(self.feature.status()['state'],'completed')
    def test_auth_status_and_invalid_requests_never_initialize(self):
        self.assertEqual(self.request('/api/library/video-ai/status',authorized=False)[0],403)
        self.assertEqual(self.request('/api/library/video-ai/start',{'consent':True},authorized=False)[0],403)
        self.assertFalse(self.request('/api/library/video-ai/status')[1]['initialized'])
        for body in ({'consent':False},{'consent':True,'limit':0},{'consent':True,'conditions':{'root_ids':[999]}}):
            self.assertEqual(self.request('/api/library/video-ai/start',body)[0],400)
        self.assertEqual(self.request('/api/library/video-ai/start',raw=b'{"consent":true,"consent":false}')[0],400)
        self.assertIsNone(self.feature.owner);self.assertEqual(self.feature.encoder.calls,0)
    def test_job_query_release_and_time_evidence(self):
        self.prepare()
        code,result=self.request('/api/library/video-ai/search',{'query':'video'})
        self.assertEqual(code,200);self.assertEqual(result['items'][0]['video_match_source'],'direct-video')
        self.assertEqual(result['items'][0]['video_match_end_ms'],16000)
        self.assertEqual(self.request('/api/library/video-ai/release',{})[0],200)
        self.assertFalse(self.feature.encoder.resident)
    def test_sessions_track_video_index_only(self):
        self.prepare()
        self.assertEqual(self.request('/api/library/results/create',{'session_id':'a'*32,'conditions':{'mode':'literal'}})[0],200)
        self.assertEqual(self.request('/api/library/results/create',{'session_id':'b'*32,'conditions':{'mode':'video-direct','query':'video'}})[0],200)
        self.assertEqual(self.request('/api/library/results/range',{'session_id':'b'*32,'offset':0,'limit':1})[0],200)
        with self.feature.owner.index.store.connect() as db:db.execute('UPDATE ai_video_direct_sources SET indexed_windows=0')
        self.assertEqual(self.request('/api/library/results/range',{'session_id':'b'*32,'offset':0,'limit':1})[0],409)
        self.assertEqual(self.request('/api/library/results/range',{'session_id':'a'*32,'offset':0,'limit':1})[0],200)

    def test_cached_similarity_route_has_both_intervals_without_model_or_inference_lock(self):
        (self.media/'second.mp4').write_bytes(self.path.read_bytes())
        self.catalog.index.scan(self.root);self.catalog.sync_index();self.prepare()
        before=self.feature.encoder.calls;self.feature.encoder.available=False
        group=self.feature.image_ai.inference_group
        image=group.owners[0]
        with image:
            image.encoder.resident=True
            code,result=self.request('/api/library/video-ai/similar',{'item_id':self.item})
        self.assertEqual(code,200);self.assertEqual(result['total'],1)
        row=result['items'][0]
        self.assertNotEqual(row['id'],self.item)
        self.assertEqual((row['origin_match_ms'],row['origin_match_end_ms']),(0,16000))
        self.assertEqual((row['video_match_ms'],row['video_match_end_ms']),(0,16000))
        self.assertEqual(row['video_match_source'],'direct-video')
        self.assertEqual(self.feature.encoder.calls,before)
        self.assertTrue(image.encoder.resident)
        self.assertEqual(self.request('/api/library/video-ai/similar',{'item_id':self.item},authorized=False)[0],403)
        self.assertEqual(self.request('/api/library/video-ai/similar',{'item_id':self.item,'kind':'image'})[0],400)

    def test_similarity_session_invalidates_when_origin_changes(self):
        (self.media/'second.mp4').write_bytes(self.path.read_bytes())
        self.catalog.index.scan(self.root);self.catalog.sync_index();self.prepare()
        code,_=self.request('/api/library/results/create',{'session_id':'c'*32,'conditions':{'mode':'video-similar','item_id':self.item}})
        self.assertEqual(code,200)
        code,result=self.request('/api/library/results/range',{'session_id':'c'*32,'offset':0,'limit':1})
        self.assertEqual(code,200);self.assertEqual(result['mode'],'video-similar')
        self.path.write_bytes(b'changed generated origin')
        self.assertEqual(self.request('/api/library/results/range',{'session_id':'c'*32,'offset':0,'limit':1})[0],409)
