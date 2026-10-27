"""Authenticated local audio APIs using generated PCM and CPU fake encoders."""
from dataclasses import replace
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import types
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_audio_direct_index as fixture
from test_audio_direct_jobs import Encoder
from ai_profiles import DEFAULT_PROFILE
from ai_settings import AIProfileSettings
from audio_direct_feature import AudioDirectFeature
from audio_direct_jobs import AudioDirectJobs
from inference_ownership import InferenceOwnership
from production_server import production_handler,DisabledAI
from wd_tagger import DisabledTagger


class AudioHTTPTests(unittest.TestCase):
    supplied=fixture.DirectAudioIndexTests.supplied
    def setUp(self):
        fixture.DirectAudioIndexTests.setUp(self)
        group=InferenceOwnership();vision=Encoder();group.for_encoder(vision)
        image=types.SimpleNamespace(profile=replace(DEFAULT_PROFILE,dimension=3),encoder=vision,inference_group=group)
        def encoder(profile):value=Encoder();value.profile=profile;return value
        self.feature=AudioDirectFeature(self.catalog,image,encoder_factory=encoder,stage_parent=self.stage)
        self.addCleanup(self.feature.close)
        def owner(catalog,encoder,**options):
            return AudioDirectJobs(catalog,encoder,**{**options,'reader':self.reader})
        patched=patch('audio_direct_feature.AudioDirectJobs',side_effect=owner);patched.start();self.addCleanup(patched.stop)
        profiles=AIProfileSettings(self.base,self.base/'settings.json',profile_directory=self.base/'profiles',
                                  ai_python=str(self.base/'missing-python'),models_root=self.base/'models')
        self.token='test-audio-session'
        self.handler=production_handler(self.catalog,self.token,ai=DisabledAI(),profiles=profiles,
                                        tagger=DisabledTagger(),audio_feature=self.feature)
        self.handler.log_message=lambda *args:None
        self.server=ThreadingHTTPServer(('127.0.0.1',0),self.handler)
        self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base_url='http://127.0.0.1:'+str(self.server.server_port);self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown();self.server.server_close();self.thread.join(3)
        for owner in (self.handler.results,self.handler.startup_scans,self.handler.setup_jobs,self.handler.download_jobs,
                      self.handler.animations,self.handler.thumbnails,self.handler.backup_jobs,self.handler.restore_jobs):owner.close()

    def request(self,path,body=None,*,authorized=True,raw=None):
        headers={'Connection':'close','Origin':self.base_url}
        if authorized:headers['X-Aredoko-Token']=self.token
        data=raw if raw is not None else json.dumps(body).encode() if body is not None else None
        if data is not None:headers['Content-Type']='application/json'
        request=urllib.request.Request(self.base_url+path,data=data,headers=headers)
        try:
            with urllib.request.urlopen(request,timeout=10) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:
            with error:return error.code,json.load(error)

    def prepare(self):
        with self.supplied():
            code,state=self.request('/api/library/audio-ai/start',{'consent':True});self.assertEqual(code,200)
            self.assertTrue(state['supported']);self.assertTrue(state['available'])
            self.feature.owner.thread.join(5)
        self.assertEqual(self.feature.status()['state'],'completed')

    def test_authenticated_status_is_lazy_and_unauthorized_calls_do_not_activate(self):
        self.assertEqual(self.request('/api/library/audio-ai/status',authorized=False)[0],403)
        self.assertEqual(self.request('/api/library/audio-ai/start',{'consent':True},authorized=False)[0],403)
        code,value=self.request('/api/library/audio-ai/status')
        self.assertEqual(code,200);self.assertFalse(value['initialized']);self.assertIsNone(self.feature.owner)
        self.assertEqual(self.feature.encoder.calls,0)

    def test_start_requires_consent_strict_json_and_valid_scope(self):
        for body in ({'consent':False},{'consent':True,'limit':0},{'consent':True,'conditions':{'root_ids':[999]}}):
            self.assertEqual(self.request('/api/library/audio-ai/start',body)[0],400)
        self.assertEqual(self.request('/api/library/audio-ai/start',raw=b'{"consent":true,"consent":false}')[0],400)
        self.assertIsNone(self.feature.owner);self.assertEqual(self.feature.encoder.calls,0)

    def test_owned_job_query_and_release_routes_keep_time_evidence(self):
        self.prepare()
        code,state=self.request('/api/library/audio-ai/status');self.assertEqual(code,200)
        self.assertEqual(state['indexed'],1)
        code,result=self.request('/api/library/audio-ai/search',{'query':'audio'})
        self.assertEqual(code,200);self.assertEqual(result['items'][0]['audio_match_ms'],0)
        self.assertNotIn('audio_match_snippet',result['items'][0])
        code,result=self.request('/api/library/audio-ai/release',{})
        self.assertEqual(code,200);self.assertFalse(result['resident'])

    def test_audio_result_session_tracks_only_its_own_index_namespace(self):
        self.prepare()
        self.assertEqual(self.request('/api/library/results/create',{'session_id':'a'*32,'conditions':{'mode':'literal'}})[0],200)
        self.assertEqual(self.request('/api/library/results/create',{'session_id':'b'*32,'conditions':{'mode':'audio-direct','query':'audio'}})[0],200)
        code,result=self.request('/api/library/results/range',{'session_id':'b'*32,'offset':0,'limit':1})
        self.assertEqual(code,200);self.assertEqual(result['items'][0]['audio_match_source'],'direct-audio')
        with self.feature.owner.index.store.connect() as db:db.execute('UPDATE ai_audio_direct_sources SET indexed_windows=0')
        self.assertEqual(self.request('/api/library/results/range',{'session_id':'b'*32,'offset':0,'limit':1})[0],409)
        self.assertEqual(self.request('/api/library/results/range',{'session_id':'a'*32,'offset':0,'limit':1})[0],200)

    def test_unsupported_profile_does_not_create_an_audio_namespace(self):
        unsupported=AudioDirectFeature(self.catalog,DisabledAI())
        try:
            self.assertFalse(unsupported.status()['supported']);self.assertFalse(unsupported.status()['available'])
        finally:unsupported.close()

    def test_direct_similarity_uses_cached_audio_without_an_encoder_or_legacy_vectors(self):
        (self.media/'second.wav').write_bytes(self.path.read_bytes())
        self.catalog.index.scan(self.root);self.catalog.sync_index();self.prepare()
        origin=self.item;before=self.feature.encoder.calls
        self.feature.encoder.available=False
        code,result=self.request('/api/library/audio-ai/similar',{'item_id':origin})
        self.assertEqual(code,200);self.assertEqual(result['source'],'audio-direct')
        self.assertEqual(result['origin_id'],origin);self.assertEqual(result['total'],1)
        self.assertEqual(result['items'][0]['origin_match_ms'],0)
        self.assertNotEqual(result['items'][0]['id'],origin)
        self.assertEqual(self.feature.encoder.calls,before)

        self.assertEqual(self.request('/api/library/audio-ai/similar',{'item_id':origin},authorized=False)[0],403)
        self.assertEqual(self.request('/api/library/audio-ai/similar',{'item_id':origin,'kind':'video'})[0],400)
        code,_=self.request('/api/library/results/create',{'session_id':'c'*32,'conditions':{'mode':'audio-similar','item_id':origin}})
        self.assertEqual(code,200)
        code,result=self.request('/api/library/results/range',{'session_id':'c'*32,'offset':0,'limit':1})
        self.assertEqual(code,200);self.assertEqual(result['mode'],'audio-similar')
        self.assertEqual(self.feature.encoder.calls,before)

    def test_similarity_pair_overflow_returns_actionable_error_without_results(self):
        (self.media/'second.wav').write_bytes(self.path.read_bytes())
        self.catalog.index.scan(self.root);self.catalog.sync_index();self.prepare()
        with patch('audio_direct_similarity.MAX_PAIRS',3):
            code,result=self.request('/api/library/audio-ai/similar',{'item_id':self.item})
        self.assertEqual(code,503);self.assertEqual(result['error_code'],'ai_unavailable')
        self.assertIn('フォルダーや棚',result['error']);self.assertNotIn('items',result)

    def test_matched_audio_change_returns_a_refresh_conflict_instead_of_bad_request(self):
        self.prepare();manifest=self.reader.audio_manifest;calls=[]
        def changed(item):
            calls.append(item)
            if len(calls)==2:self.path.write_bytes(b'changed generated source')
            return manifest(item)
        with patch.object(self.reader,'audio_manifest',side_effect=changed):
            code,result=self.request('/api/library/audio-ai/search',{'query':'audio'})
        self.assertEqual(code,409);self.assertEqual(result['error_code'],'audio_scope_changed')
        self.assertNotIn('items',result)


if __name__=='__main__':unittest.main()
