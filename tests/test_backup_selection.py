"""Active/pending profiles and format1/2 recovery; generated CPU metadata only."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import json,sys,tempfile,unittest
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app')]
from ai_profiles import DEFAULT_PROFILE,load_profile
from ai_settings import AIProfileSettings
from production import ProductionCatalog
from production_server import production_handler,DisabledAI
from wd_tagger import DisabledTagger
from tagger_profile import WDProfile
from live_backup import capture_live,BackupSelection
from storage_backup import backup,restore,validate_restored,RecoveryError
from restore_switch import apply_restore_switch,rollback_restore_switch,RestoreSwitchError

REPO=Path(__file__).resolve().parents[1]
class ActiveSelectionTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.base=Path(tmp.name)
        self.cat=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.cat.close)
        self.folder=self.base/'profiles';self.folder.mkdir();self.settings=self.base/'ai-settings.json'
        self.pending=replace(DEFAULT_PROFILE,label='pending',dimension=16,modalities=('text',),directory='generated-pending')
        self.running=replace(DEFAULT_PROFILE,label='running',dimension=8,modalities=('text',),directory='generated-running')
        (self.folder/'pending.json').write_text(json.dumps(self.pending.to_dict()),encoding='utf-8')
        self.tag_definition=json.loads((REPO/'config/tagger-profiles/wd-swinv2-v3.json').read_text())
    def owner(self,profiles,tagger=None,**kwargs):
        h=production_handler(self.cat,'generated-token',DisabledAI(),profiles=profiles,tagger=tagger if tagger is not None else DisabledTagger(),**kwargs)
        for job in (h.setup_jobs,h.download_jobs,h.restore_jobs,h.backup_jobs,h.thumbnails,h.animations,h.results):self.addCleanup(job.close)
        return h
    def capture(self,configuration,name='bundle',selection=BackupSelection(),**kwargs):
        with patch('subprocess.Popen',side_effect=AssertionError('No model/runtime execution')):
            capture_live(self.cat,self.base/name,quiesce=self.cat.writer_fence.pause,selection=selection,**configuration,**kwargs)
        return self.base/name
    def switch(self,bundle):
        staging=self.base/'staging';restore(bundle,staging);report=validate_restored(staging)
        user=self.base/'user';user.mkdir();previous={'database':str(self.cat.path),'ui_theme':'dark','tagger_profile':str(self.base/'old.json')}
        (user/'launch-settings.json').write_text(json.dumps(previous),encoding='utf-8')
        result=apply_restore_switch(user,staging);settings=json.loads((user/'launch-settings.json').read_text())
        return report,user,previous,settings,Path(result['target_restore_dir'])
    def test_explicit_running_profile_and_pending_bytes_survive_switch_and_rollback(self):
        active=self.base/'override.json';active.write_text(json.dumps(self.running.to_dict()),encoding='utf-8')
        original=b'{"version":1,"profile":"local:pending.json","resource":{"idle_release_seconds":20,"index_pause_ms":30}}'
        self.settings.write_bytes(original);profiles=AIProfileSettings(self.base,self.settings,active,profile_directory=self.folder)
        # External file edits must not change the definition actually loaded at startup.
        active.write_text(json.dumps(self.pending.to_dict()),encoding='utf-8')
        h=self.owner(profiles);bundle=self.capture(h.backup_jobs.configuration());report,user,old,values,root=self.switch(bundle)
        self.assertEqual(report['version'],2);self.assertTrue(report['active_selection']['ai_override']);self.assertEqual((root/'settings/ai-settings.json').read_bytes(),original)
        self.assertEqual(load_profile(values['ai_profile']),self.running)
        resumed=AIProfileSettings(self.base,values['ai_settings'],values['ai_profile'],values.get('ai_profiles_dir',self.folder))
        self.assertEqual(resumed.selected(),'local:pending.json');self.assertEqual(load_profile(resumed.startup_path),self.running)
        self.assertEqual(self.settings.read_bytes(),original);rollback_restore_switch(user)
        self.assertEqual(json.loads((user/'launch-settings.json').read_text()),old)
    def test_builtin_active_and_later_pending_choice_remain_distinct(self):
        self.settings.write_text('{"version":1,"profile":"default"}')
        profiles=AIProfileSettings(self.base,self.settings,profile_directory=self.folder);h=self.owner(profiles)
        profiles.choose('local:pending.json');pending_bytes=self.settings.read_bytes()
        report,_,_,values,root=self.switch(self.capture(h.backup_jobs.configuration()))
        self.assertFalse(report['active_selection']['ai_override'])
        self.assertEqual(load_profile(values['ai_profile']),DEFAULT_PROFILE)
        self.assertEqual((root/'settings/ai-settings.json').read_bytes(),pending_bytes)
    def test_local_active_remains_frozen_after_gui_pending_choice(self):
        (self.folder/'running.json').write_text(json.dumps(self.running.to_dict()),encoding='utf-8')
        self.settings.write_text('{"version":1,"profile":"local:running.json"}')
        profiles=AIProfileSettings(self.base,self.settings,profile_directory=self.folder);h=self.owner(profiles)
        profiles.choose('local:pending.json');bundle=self.capture(h.backup_jobs.configuration())
        _,_,_,values,_=self.switch(bundle);self.assertEqual(load_profile(values['ai_profile']),self.running)
        self.assertEqual(json.loads(Path(values['ai_settings']).read_text())['profile'],'local:pending.json')
    def test_multiple_taggers_use_explicit_loaded_definition_not_file_order(self):
        paths=[]
        for name,threshold in [('a.json',.2),('z.json',.7)]:
            value={**self.tag_definition,'general_threshold':threshold};path=self.base/name;path.write_text(json.dumps(value));paths.append(path)
        loaded=WDProfile.from_dict(json.loads(paths[1].read_text()));tagger=SimpleNamespace(profile=loaded)
        profiles=AIProfileSettings(self.base,self.settings,profile_directory=self.folder)
        h=self.owner(profiles,tagger,tagger_profile_paths=tuple(reversed(paths)))
        _,_,_,values,root=self.switch(self.capture(h.backup_jobs.configuration()))
        self.assertEqual(json.loads(Path(values['tagger_profile']).read_text()),loaded.data())
        self.assertTrue((root/'tagger-profiles/a.json').is_file());self.assertTrue((root/'tagger-profiles/z.json').is_file())
    def test_full_profile_collections_keep_space_for_frozen_active_definitions(self):
        for i in range(63):(self.folder/f'p{i:02}.json').write_text(json.dumps(self.pending.to_dict()))
        paths=[]
        for i in range(16):
            path=self.base/f't{i:02}.json';path.write_text(json.dumps(self.tag_definition));paths.append(path)
        profiles=AIProfileSettings(self.base,self.settings,profile_directory=self.folder)
        h=self.owner(profiles,SimpleNamespace(profile=WDProfile.from_dict(self.tag_definition)),tagger_profile_paths=paths)
        bundle=self.capture(h.backup_jobs.configuration());manifest=json.loads((bundle/'manifest.json').read_text())
        self.assertEqual(sum(e['role']=='profile' for e in manifest['entries']),64)
        self.assertEqual(sum(e['role']=='tagger_profile' for e in manifest['entries']),16)
        self.assertEqual(sum(e['role'].startswith('active_') for e in manifest['entries']),2)
        restore(bundle,self.base/'restored');validate_restored(self.base/'restored')
    def test_repeated_backup_has_no_snapshot_filename_collision_or_profile_growth(self):
        (self.folder/'ai-profile.json').write_text(json.dumps(self.pending.to_dict()))
        self.settings.write_text('{"version":1,"profile":"default"}')
        profiles=AIProfileSettings(self.base,self.settings,profile_directory=self.folder);h=self.owner(profiles)
        _,_,_,values,_=self.switch(self.capture(h.backup_jobs.configuration()))
        resumed=AIProfileSettings(self.base,values['ai_settings'],values['ai_profile'],values['ai_profiles_dir'])
        second=self.owner(resumed);bundle=self.capture(second.backup_jobs.configuration(),name='second')
        manifest=json.loads((bundle/'manifest.json').read_text());self.assertEqual(sum(e['role']=='profile' for e in manifest['entries']),2)
        self.assertEqual(sum(e['role']=='active_profile' for e in manifest['entries']),1)
        restore(bundle,self.base/'second-restored');validate_restored(self.base/'second-restored')

    def test_settings_omission_does_not_capture_active_definitions(self):
        profiles=AIProfileSettings(self.base,self.settings,profile_directory=self.folder);h=self.owner(profiles)
        bundle=self.capture(h.backup_jobs.configuration(),selection=BackupSelection(settings=False))
        manifest=json.loads((bundle/'manifest.json').read_text())
        self.assertEqual(manifest['active_selection'],{'ai_profile':None,'tagger_profile':None,'ai_override':False})
        self.assertFalse(any(e['role'].startswith('active_') for e in manifest['entries']))
    def test_cancelled_active_snapshots_never_publish_or_create_source_preferences(self):
        profiles=AIProfileSettings(self.base,self.settings,profile_directory=self.folder);h=self.owner(profiles)
        def reject(operation):raise InterruptedError('cancel before publication')
        with self.assertRaises(InterruptedError):self.capture(h.backup_jobs.configuration(),publish=reject)
        self.assertFalse((self.base/'bundle').exists());self.assertFalse(self.settings.exists())
        self.assertFalse(self.cat.writer_fence.paused);self.assertEqual(list(self.base.glob('.aredoko-capture-*')),[])
    def test_legacy_v1_restore_and_single_tagger_behavior_are_supported(self):
        tag=self.base/'legacy.json';tag.write_text(json.dumps(self.tag_definition))
        bundle=self.base/'legacy';backup(self.cat.path,bundle,tagger_profiles=(tag,),include_vectors=False)
        manifest=json.loads((bundle/'manifest.json').read_text());manifest['version']=1;del manifest['active_selection']
        (bundle/'manifest.json').write_text(json.dumps(manifest))
        report,_,_,values,root=self.switch(bundle);self.assertEqual(report['version'],1)
        self.assertEqual(values['tagger_profile'],str(root/'tagger-profiles/legacy.json'))
    def test_ambiguous_legacy_multiple_taggers_do_not_guess_or_drop_current_choice(self):
        paths=[]
        for name in ('a.json','z.json'):
            path=self.base/name;path.write_text(json.dumps(self.tag_definition));paths.append(path)
        bundle=self.base/'legacy';backup(self.cat.path,bundle,tagger_profiles=paths,include_vectors=False)
        manifest=json.loads((bundle/'manifest.json').read_text());manifest['version']=1;del manifest['active_selection'];(bundle/'manifest.json').write_text(json.dumps(manifest))
        _,_,old,values,_=self.switch(bundle);self.assertEqual(values['tagger_profile'],old['tagger_profile'])
    def test_invalid_v2_selection_or_version_fails_before_output_is_created(self):
        profiles=AIProfileSettings(self.base,self.settings,profile_directory=self.folder);h=self.owner(profiles)
        bundle=self.capture(h.backup_jobs.configuration());original=json.loads((bundle/'manifest.json').read_text())
        variants=[]
        for value in ('../escape.json','C:/outside.json','profiles/missing.json',False):
            item=json.loads(json.dumps(original));item['active_selection']['ai_profile']=value;variants.append(item)
        item=json.loads(json.dumps(original));del item['active_selection'];variants.append(item)
        item=json.loads(json.dumps(original));item['version']=3;variants.append(item)
        item=json.loads(json.dumps(original));item['active_selection']['ai_override']=1;variants.append(item)
        item=json.loads(json.dumps(original));item['active_selection']['ai_profile']=None;variants.append(item)
        item=json.loads(json.dumps(original));item['version']=1;del item['active_selection'];variants.append(item)
        for i,manifest in enumerate(variants):
            with self.subTest(i=i):
                (bundle/'manifest.json').write_text(json.dumps(manifest))
                with self.assertRaises((RecoveryError,ValueError)):restore(bundle,self.base/f'invalid{i}')
                self.assertFalse((self.base/f'invalid{i}').exists())
    def test_invalid_restored_selection_preserves_stage_and_launch_settings(self):
        profiles=AIProfileSettings(self.base,self.settings,profile_directory=self.folder);h=self.owner(profiles)
        bundle=self.capture(h.backup_jobs.configuration());staging=self.base/'stage';restore(bundle,staging)
        report=json.loads((staging/'recovery.json').read_text());report['active_selection']['ai_profile']='../escape.json';(staging/'recovery.json').write_text(json.dumps(report))
        user=self.base/'user';user.mkdir();old=b'{"ui_theme":"dark"}';(user/'launch-settings.json').write_bytes(old)
        with self.assertRaises(RestoreSwitchError):apply_restore_switch(user,staging)
        self.assertTrue(staging.is_dir());self.assertEqual((user/'launch-settings.json').read_bytes(),old)

if __name__=='__main__':unittest.main()
