"""Role-specific restart locations. Generated paths/DB only, no model execution."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json,sys,tempfile,unittest,subprocess
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/name) for name in ('app','tools')]
from ai_runtime_preferences import AIRuntimePreferences,read_preferences,model_root,MODEL_ROOT_FIELDS
import production_server as server
from production_server import DisabledAI
from wd_tagger import DisabledTagger
import launch_release
REPO=Path(__file__).resolve().parents[1]
class ModelRoleLocationsTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.base=Path(t.name)
        self.path=self.base/'launch-settings.json';self.common=self.base/'common';self.common.mkdir()
        self.values={'models_root':str(self.common),'ui_theme':'light',**{key:str(self.base/role) for role,key in MODEL_ROOT_FIELDS.items()}}
        for role in MODEL_ROOT_FIELDS:(self.base/role).mkdir()
        self.path.write_text(json.dumps(self.values))
    def test_each_role_overrides_only_itself_and_common_fallback_is_unchanged(self):
        for role,field in MODEL_ROOT_FIELDS.items():
            self.assertEqual(model_root(self.values,role),self.values[field])
            self.assertEqual(model_root({'models_root':str(self.common)},role),str(self.common))
            self.assertEqual(model_root({},role,'default'),'default')
        with self.assertRaises(ValueError):model_root(self.values,'guessed')
    def test_preferences_reject_relative_or_null_role_paths(self):
        for bad in ('relative',None,12):
            self.path.write_text(json.dumps(self.values|{'tagger_models_root':bad}))
            with self.subTest(bad=bad),self.assertRaises(ValueError):read_preferences(self.path)
    def test_snapshot_reports_effective_roots_without_loading_models(self):
        service=AIRuntimePreferences(self.path,self.base,None,active_models_root=self.values['embedding_models_root'])
        with patch('subprocess.Popen',side_effect=AssertionError('No model execution')):snapshot=service.snapshot()
        self.assertEqual(snapshot['models_root'],self.values['embedding_models_root'])
        self.assertEqual(snapshot['model_roots'],{r:self.values[f] for r,f in MODEL_ROOT_FIELDS.items()})
        self.assertFalse(snapshot['restart_required'])
        changed=self.values|{'tagger_models_root':str(self.base/'another')};self.path.write_text(json.dumps(changed))
        self.assertTrue(service.snapshot()['restart_required'])
    def test_explicit_legacy_common_choice_and_reset_clear_role_overrides(self):
        service=AIRuntimePreferences(self.path,self.base,None);other=self.base/'new-common';other.mkdir()
        result=service.select(models_root=str(other),consent=True);saved=read_preferences(self.path)
        self.assertTrue(all(field not in saved for field in MODEL_ROOT_FIELDS.values()))
        self.assertEqual(saved['ui_theme'],'light');self.assertEqual(result['model_roots'],{r:str(other) for r in MODEL_ROOT_FIELDS})
        self.path.write_text(json.dumps(self.values));service.select(models_root=None,consent=True)
        self.assertEqual(read_preferences(self.path),{'ui_theme':'light'})
    def test_cancelled_common_choice_preserves_all_role_choices(self):
        original=self.path.read_bytes();service=AIRuntimePreferences(self.path,self.base,None)
        with self.assertRaises(RuntimeError):service.select(models_root=str(self.common),consent=True,cancelled=lambda:True)
        self.assertEqual(self.path.read_bytes(),original)
    def test_launcher_passes_explicit_role_paths_to_owned_backend(self):
        observed=[];root=self.base/'release';root.mkdir();data=self.base/'user';data.mkdir()
        with patch('startup_validation.startup_preflight',return_value={'frontend_activation':'unconfigured'}),patch.object(launch_release,'prepare_frontend',return_value=SimpleNamespace(start=lambda *a:None)),patch.object(launch_release,'run_session',side_effect=lambda command,*a,**k:observed.append(command)):
            launch_release._launch_once(root,data,launch_release.validate_settings(self.values))
        for role,field in MODEL_ROOT_FIELDS.items():
            option='--'+field.replace('_','-');self.assertEqual(observed[0][observed[0].index(option)+1],self.values[field])
    def test_dispatcher_routes_embedding_tagger_and_intent_independently(self):
        args=SimpleNamespace(db=self.base/'generated.sqlite',ai_python=self.base/'missing-python',models_root=self.common,runtime_preferences=None,restore_session_dir=None,instance_id=None,ai_settings=self.base/'ai-settings.json',ai_profile=None,ai_profiles_dir=None,ai_ranking='mean-rrf',laya_intent=False,intent_questions='v2-hybrid',intent_no_order_check=False,tagger_profile=None,port=0,exit_on_stdin_close=False,**{f:Path(self.values[f]) for f in MODEL_ROOT_FIELDS.values()})
        observed={};original=server.create_intent
        def intent(*a,**kw):observed['intent']=kw['models_root'];return original(*a,**kw)
        def ai(*a,**kw):observed['embedding']=kw['models_root'];return DisabledAI()
        def tagger(*a,**kw):observed['tagger']=kw['models_root'];return DisabledTagger()
        fake=SimpleNamespace(server_port=0,server_close=lambda:None,serve_forever=lambda **kw:None)
        with patch.object(server,'create_ai',side_effect=ai),patch.object(server,'create_intent',side_effect=intent),patch.object(server,'create_tagger',side_effect=tagger),patch.object(server,'OwnedHTTPServer',return_value=fake):server._serve(args)
        self.assertEqual(observed,{r:Path(self.values[f]) for r,f in MODEL_ROOT_FIELDS.items()})
    def test_invalid_direct_cli_role_root_fails_before_creating_database(self):
        output=self.base/'untouched'/'catalog.sqlite'
        result=subprocess.run([sys.executable,'-B',str(REPO/'app/production_server.py'),'--db',str(output),'--tagger-models-root','relative'],capture_output=True,timeout=10)
        self.assertEqual(result.returncode,2);self.assertFalse(output.parent.exists())
if __name__=='__main__':unittest.main()
