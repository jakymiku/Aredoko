"""Exact physical model placements; generated settings/DB and non-executing spies."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json,sys,unittest
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/name) for name in ('app','tools')]
import test_model_role_locations as fixtures
from model_locations import FIELD,ModelTarget,parse_locations,serialize_locations
from ai_runtime_preferences import AIRuntimePreferences,read_preferences,model_root,MODEL_ROOT_FIELDS
from ai_setup_jobs import AISetupJobs
from ai_profiles import DEFAULT_PROFILE
from tagger_profile import load_profile as load_tagger
from production_server import DisabledAI
from wd_tagger import DisabledTagger
import production_server as server
import launch_release
REPO=Path(__file__).resolve().parents[1]
class ModelPlacementsTests(unittest.TestCase):
    def setUp(self):
        fixtures.ModelRoleLocationsTests.setUp(self)
        self.first=replace(DEFAULT_PROFILE,model_id='example/first',directory='first')
        self.second=replace(DEFAULT_PROFILE,model_id='example/second',directory='second')
        self.a=ModelTarget.for_profile('embedding',self.first);self.b=ModelTarget.for_profile('embedding',self.second)
        self.tag=ModelTarget.for_profile('tagger',load_tagger(REPO))
        self.root_a=self.base/'version-a';self.root_b=self.base/'version-b';self.root_tag=self.base/'version-tag'
        for root in (self.root_a,self.root_b,self.root_tag):root.mkdir()
        self.service=AIRuntimePreferences(self.path,self.base,self.first)
    def save(self,target,root):return self.service.select(models_root=str(root) if root is not None else None,model_target=target.to_dict(),consent=True)
    def test_two_embedding_models_and_tagger_keep_independent_locations(self):
        self.save(self.a,self.root_a);self.save(self.tag,self.root_tag);result=self.save(self.b,self.root_b)
        value=read_preferences(self.path)
        for target,expected in ((self.a,self.root_a),(self.b,self.root_b),(self.tag,self.root_tag)):
            self.assertEqual(model_root(value,target.role,target=target),str(expected))
        for field in self.values:self.assertEqual(value[field],self.values[field])
        self.assertEqual(result['models_root'],str(self.root_a));self.assertTrue(result['restart_required'])
        self.save(self.a,None);value=read_preferences(self.path)
        self.assertEqual(model_root(value,'embedding',target=self.a),self.values['embedding_models_root'])
        self.assertEqual(model_root(value,'embedding',target=self.b),str(self.root_b));self.assertEqual(model_root(value,'tagger',target=self.tag),str(self.root_tag))
    def test_exact_revision_and_layout_but_independent_vector_namespace(self):
        self.save(self.a,self.root_a);value=read_preferences(self.path)
        other=replace(self.first,query_prompt_name=None,query_prefix='different:')
        self.assertNotEqual(self.first.key,other.key)
        self.assertEqual(model_root(value,'embedding',target=ModelTarget.for_profile('embedding',other)),str(self.root_a))
        for changed in (replace(self.first,revision='f'*40),replace(self.first,directory='other')):
            self.assertEqual(model_root(value,'embedding',target=ModelTarget.for_profile('embedding',changed)),self.values['embedding_models_root'])
    def test_role_and_common_manual_resets_have_explicit_scopes(self):
        self.save(self.a,self.root_a);self.save(self.b,self.root_b);self.save(self.tag,self.root_tag)
        self.service.select(model_role='embedding',models_root=None,consent=True)
        value=read_preferences(self.path);self.assertEqual(parse_locations(value[FIELD]),((self.tag,str(self.root_tag)),))
        self.assertNotIn('embedding_models_root',value);self.assertIn('tagger_models_root',value)
        self.service.select(models_root=str(self.common),consent=True);value=read_preferences(self.path)
        self.assertNotIn(FIELD,value);self.assertTrue(all(k not in value for k in MODEL_ROOT_FIELDS.values()))
    def test_owned_job_selects_target_and_rejects_ambiguous_requests_before_thread(self):
        jobs=AISetupJobs(self.service);self.addCleanup(jobs.close)
        for body in ({'model_role':None},{'model_target':None},{'model_role':'tagger','model_target':self.a.to_dict()}):
            with self.subTest(body=body),self.assertRaises(ValueError):jobs.start({'consent':True,'models_root':str(self.root_a),**body})
        self.assertIsNone(jobs.thread)
        jobs.start({'consent':True,'models_root':str(self.root_a),'model_target':self.a.to_dict()});jobs.thread.join(5)
        self.assertEqual(jobs.snapshot()['state'],'complete');self.assertTrue(jobs.snapshot()['saved'])
        self.assertEqual(read_preferences(self.path)[FIELD][0]['root'],str(self.root_a))
    def test_invalid_paths_duplicates_and_bounded_metadata_are_rejected(self):
        row=self.a.to_dict()|{'root':str(self.root_a)}
        for values in ([row,row],[row|{'root':'relative'}],[row|{'directory':'../escape'}],[row|{'role':'unknown'}],{},[row]*33):
            with self.subTest(values=values),self.assertRaises(ValueError):parse_locations(values)
        with self.assertRaises(ValueError):launch_release.validate_settings({'model_locations':[row|{'directory':'CON'}]})
    def test_cancelled_selection_keeps_all_placements_and_original_settings(self):
        self.save(self.tag,self.root_tag);before=self.path.read_bytes()
        with self.assertRaises(RuntimeError):self.service.select(models_root=str(self.root_a),model_target=self.a.to_dict(),consent=True,cancelled=lambda:True)
        self.assertEqual(self.path.read_bytes(),before)
    def test_invalid_optional_model_layout_remains_diagnostic_not_api_crash(self):
        service=AIRuntimePreferences(self.path,self.base,replace(DEFAULT_PROFILE,directory='CON'))
        self.assertFalse(service.snapshot()['model']['ready'])
    def test_dispatcher_uses_model_identity_and_passes_frozen_definition(self):
        default=ModelTarget.for_profile('embedding',DEFAULT_PROFILE)
        self.save(default,self.root_a);self.save(self.tag,self.root_tag)
        args=SimpleNamespace(db=self.base/'generated.sqlite',ai_python=self.base/'missing-python',models_root=self.common,runtime_preferences=self.path,restore_session_dir=None,instance_id=None,ai_settings=self.base/'ai-settings.json',ai_profile=None,ai_profiles_dir=None,ai_ranking='mean-rrf',laya_intent=False,intent_questions='v2-hybrid',intent_no_order_check=False,tagger_profile=None,port=0,exit_on_stdin_close=False,**{f:Path(self.values[f]) for f in MODEL_ROOT_FIELDS.values()})
        observed={};original=server.create_intent
        def ai(*a,**kw):observed['embedding']=kw;return DisabledAI()
        def tagger(*a,**kw):observed['tagger']=kw;return DisabledTagger()
        fake=SimpleNamespace(server_port=0,server_close=lambda:None,serve_forever=lambda **kw:None)
        with patch.object(server,'create_ai',side_effect=ai),patch.object(server,'create_tagger',side_effect=tagger),patch.object(server,'ThreadingHTTPServer',return_value=fake):server._serve(args)
        self.assertEqual(observed['embedding']['models_root'],str(self.root_a));self.assertEqual(observed['embedding']['profile_definition'],DEFAULT_PROFILE)
        self.assertEqual(observed['tagger']['models_root'],str(self.root_tag));self.assertEqual(observed['tagger']['profile_definition'].data()['revision'],self.tag.revision)
if __name__=='__main__':unittest.main()
