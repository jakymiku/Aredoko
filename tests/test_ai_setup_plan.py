"""Read-only optional setup planning. No network, hardware probe or model."""
from dataclasses import replace
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch
from urllib.request import build_opener,ProxyHandler,Request
from urllib.error import HTTPError

REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'app'),str(REPO/'tools')]
from ai_setup_plan import plan_setup
from ai_profiles import DEFAULT_PROFILE
from model_locations import ModelTarget


class SetupPlanTests(unittest.TestCase):
    def plan(self,features,*,profile=DEFAULT_PROFILE,state=None,rows=None):
        state=state or {'runtime':{'ready':False,'state':'not_selected'},'model':{'ready':False,'state':'missing'}}
        target=ModelTarget.for_profile('embedding',profile).to_dict()
        rows=rows if rows is not None else [dict(catalog_id='a'*64,kind='model',bytes=100,
            model_target=target,name='generated-model',license='fixture',license_url='https://example.invalid/fixture')]
        return plan_setup({'features':features},profile=profile,environment=lambda:state,catalogs=lambda:{'catalogs':rows})

    def test_four_features_share_one_exact_model_and_separate_missing_runtime(self):
        result=self.plan(['semantic','image_similarity','video','audio'])
        self.assertEqual(len(result['features']),4)
        self.assertEqual([r['id'] for r in result['requirements']],['embedding-runtime','embedding-model'])
        self.assertEqual(result['selected_catalog_ids'],['a'*64])
        self.assertEqual(result['known_download_bytes'],100)
        self.assertIsNone(result['total_download_bytes'])
        self.assertEqual(result['unresolved_requirements'],['embedding-runtime'])
        self.assertFalse(result['can_download_all_missing'])
        self.assertTrue(result['automatic_setup_supported'])
        self.assertFalse(result['hardware_checked_by_plan']);self.assertFalse(result['inference_checked_by_plan'])

    def test_skip_and_bad_requests_never_inspect_the_environment(self):
        env=Mock(side_effect=AssertionError('Do not inspect'))
        catalogs=Mock(side_effect=AssertionError('Do not read catalogs'))
        selection=Mock(side_effect=AssertionError('Do not inspect saved profile selection'))
        result=plan_setup({'features':[]},profile=None,environment=env,catalogs=catalogs,profile_status=selection)
        self.assertTrue(result['skip_ai']);self.assertEqual(result['requirements'],[])
        self.assertFalse(result['automatic_setup_supported'])
        for body in ({},{'features':'video'},{'features':['video','video']},{'features':['future']},
                     {'features':[{}]},{'features':[True]},{'features':[],'consent':True}):
            with self.subTest(body=body),self.assertRaises(ValueError):
                plan_setup(body,profile=DEFAULT_PROFILE,environment=env,catalogs=catalogs)
        env.assert_not_called();catalogs.assert_not_called();selection.assert_not_called()

    def test_profile_pending_flags_do_not_hot_swap_the_dependency_target(self):
        state={'runtime':{'ready':True},'model':{'ready':True}}
        selection=lambda:{'restart_required':True,'command_line_override':False,'selection_invalid':False}
        reply=plan_setup({'features':['audio']},profile=DEFAULT_PROFILE,environment=lambda:state,catalogs=lambda:{'catalogs':[]},profile_status=selection)
        self.assertTrue(reply['restart_required']);self.assertTrue(reply['profile_restart_required'])
        self.assertFalse(reply['automatic_setup_supported'])
        self.assertEqual(reply['requirements'][1]['model_target'],ModelTarget.for_profile('embedding',DEFAULT_PROFILE).to_dict())
        self.assertFalse(reply['settings_saved']);self.assertFalse(reply['acquisition_started'])

    def test_wrong_revision_and_tagger_are_not_recommended(self):
        target=ModelTarget.for_profile('embedding',DEFAULT_PROFILE).to_dict()
        rows=[{'catalog_id':'a'*64,'kind':'model','bytes':100,'model_target':{**target,'revision':'b'*40}},
              {'catalog_id':'b'*64,'kind':'model','bytes':200,'model_target':{**target,'role':'tagger'}}]
        result=self.plan(['video'],rows=rows)
        self.assertEqual(result['selected_catalog_ids'],[]);self.assertEqual(result['known_download_bytes'],0)

    def test_files_present_do_not_imply_inference_or_need_another_download(self):
        result=self.plan(['audio'],state={'runtime':{'ready':True,'state':'pack_files_present'},
            'model':{'ready':True,'state':'model_files_present'},'restart_required':True,'runtime_root':'private-path'})
        self.assertEqual(result['selected_catalog_ids'],[]);self.assertEqual(result['total_download_bytes'],0)
        self.assertTrue(result['restart_required']);self.assertNotIn('private-path',json.dumps(result))
        self.assertFalse(result['inference_checked_by_plan']);self.assertFalse(result['acquisition_started'])

    def test_unsupported_profile_does_not_claim_audio_or_video_capability(self):
        profile=replace(DEFAULT_PROFILE,adapter='sentence-transformers',modalities=('text',))
        result=self.plan(['semantic','image_similarity','video','audio'],profile=profile)
        self.assertEqual(result['unresolved_features'],['image_similarity','video','audio'])
        self.assertEqual([r['id'] for r in result['features'] if r['supported']],['semantic'])

    def test_ambiguous_registered_download_is_not_chosen_implicitly(self):
        target=ModelTarget.for_profile('embedding',DEFAULT_PROFILE).to_dict()
        rows=[{'catalog_id':key*64,'kind':'model','bytes':100,'model_target':target} for key in ('a','b')]
        result=self.plan(['semantic'],rows=rows)
        self.assertEqual(result['requirements'][1]['action'],'choose_download')
        self.assertEqual(result['selected_catalog_ids'],[])


class SetupPlanHttpTests(unittest.TestCase):
    def test_plan_requires_session_is_strict_and_does_not_start_jobs(self):
        from production import ProductionCatalog
        from production_server import production_handler,DisabledAI
        from ai_settings import AIProfileSettings
        from ai_acquisition_registry import load_trusted_specs
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);catalog=ProductionCatalog(base/'catalog.sqlite')
            profiles=AIProfileSettings(base,base/'ai-settings.json',profile_directory=base/'profiles')
            handler=production_handler(catalog,'test-plan-token',DisabledAI(),profiles=profiles,
                                       acquisition_specs=load_trusted_specs(REPO))
            handler.log_message=lambda *args:None
            server=ThreadingHTTPServer(('127.0.0.1',0),handler);server.daemon_threads=True
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            origin='http://127.0.0.1:'+str(server.server_port)
            opener=build_opener(ProxyHandler({}))
            def request(body,authorized=True):
                headers={'Origin':origin,'X-Aredoko-Token':'test-plan-token' if authorized else 'wrong','Content-Type':'application/json'}
                raw=body if isinstance(body,bytes) else json.dumps(body).encode()
                try:
                    with opener.open(Request(origin+'/api/library/ai/setup/plan',data=raw,headers=headers),timeout=3) as response:
                        return response.status,json.load(response)
                except HTTPError as error:
                    with error:return error.code,json.load(error)
            try:
                with patch('subprocess.Popen',side_effect=AssertionError('No subprocess during planning')):
                    self.assertEqual(request({'features':['video']},False)[0],403)
                    self.assertEqual(request(b'{"features":[],"features":["video"]}')[0],400)
                    self.assertEqual(request({'features':['unknown']})[0],400)
                    code,reply=request({'features':['semantic','image_similarity','video','audio']})
                self.assertEqual(code,200);self.assertEqual(len(reply['selected_catalog_ids']),1)
                self.assertEqual(reply['unresolved_requirements'],['embedding-runtime'])
                self.assertEqual(handler.download_jobs.snapshot()['state'],'idle')
                self.assertEqual(handler.setup_jobs.snapshot()['state'],'idle')
                self.assertIsNone(handler.audio_content.owner);self.assertIsNone(handler.video_content.owner)
                self.assertFalse((base/'launch-settings.json').exists())
                # Changing a saved profile must not silently plan downloads for
                # that profile while the old namespace is still active.
                profiles.folder.mkdir();(profiles.folder/'next.json').write_text(json.dumps(DEFAULT_PROFILE.to_dict()),encoding='utf-8')
                definition=profiles.active_definition;profiles.choose('local:next.json')
                with patch.object(profiles,'_candidate',side_effect=AssertionError('Planning must not enumerate/inspect all profiles')):
                    code,pending=request({'features':['audio']})
                self.assertEqual(code,200);self.assertTrue(pending['profile_restart_required']);self.assertTrue(pending['restart_required'])
                self.assertEqual(profiles.active_definition,definition);self.assertEqual(profiles.active,'default')
                self.assertEqual(pending['selected_catalog_ids'],[]);self.assertEqual(pending['known_download_bytes'],0)
                self.assertFalse(pending['can_download_all_missing'])
            finally:
                server.shutdown();server.server_close();thread.join(3)
                for name in ('results','startup_scans','thumbnails','audio_content','video_content','animations','setup_jobs','download_jobs','backup_jobs','restore_jobs'):
                    getattr(handler,name).close()
                catalog.close()


if __name__=='__main__':unittest.main()
