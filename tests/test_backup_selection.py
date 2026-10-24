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
from restore_switch import apply_restore_switch,rollback_restore_switch,commit_restore_switch,check_pending_restore,get_restore_pending_info,get_restore_history,RestoreSwitchError
from storage_lease import storage_lease
import launch_release

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
    def transient_switch(self):
        self.settings.write_text('{"version":1,"profile":"default"}')
        profiles=AIProfileSettings(self.base,self.settings,profile_directory=self.folder);h=self.owner(profiles)
        profiles.choose('local:pending.json')
        return self.switch(self.capture(h.backup_jobs.configuration()))

    def test_ready_releases_only_transient_override_and_next_restart_uses_pending(self):
        _,user,_,values,_=self.transient_switch()
        running=AIProfileSettings(self.base,values['ai_settings'],values['ai_profile'],values['ai_profiles_dir'],transient_override=True)
        self.assertEqual(load_profile(running.startup_path),DEFAULT_PROFILE)
        snapshot=running.snapshot();self.assertFalse(snapshot['command_line_override']);self.assertTrue(snapshot['restored_active'])
        self.assertTrue(snapshot['restart_required']);self.assertFalse(self.owner(running).backup_jobs.configuration()['active_profile_override'])
        # Preferences edited by an independent setup job are preserved.
        changed={**values,'models_root':str(self.base/'new-models'),'ui_theme':'light'}
        changed.update(embedding_models_root=str(self.base/'embedding'),tagger_models_root=str(self.base/'tagger'),intent_models_root=str(self.base/'intent'))
        (user/'launch-settings.json').write_text(json.dumps(changed))
        commit_restore_switch(user);fresh=json.loads((user/'launch-settings.json').read_text())
        self.assertNotIn('ai_profile',fresh);self.assertEqual(fresh['models_root'],changed['models_root']);self.assertEqual(fresh['ui_theme'],'light')
        for field in ('embedding_models_root','tagger_models_root','intent_models_root'):self.assertEqual(fresh[field],changed[field])
        later=AIProfileSettings(self.base,fresh['ai_settings'],profile_directory=fresh['ai_profiles_dir'])
        self.assertEqual(load_profile(later.startup_path),self.pending)
        self.assertEqual(json.loads(running.active_definition),DEFAULT_PROFILE.to_dict())

    def test_original_explicit_override_remains_after_ready(self):
        active=self.base/'override.json';active.write_text(json.dumps(self.running.to_dict()))
        self.settings.write_text('{"version":1,"profile":"local:pending.json"}')
        profiles=AIProfileSettings(self.base,self.settings,active,profile_directory=self.folder)
        _,user,_,values,_=self.switch(self.capture(self.owner(profiles).backup_jobs.configuration()))
        commit_restore_switch(user);fresh=json.loads((user/'launch-settings.json').read_text())
        self.assertEqual(fresh['ai_profile'],values['ai_profile'])
        self.assertEqual(load_profile(fresh['ai_profile']),self.running)

    def test_busy_preferences_keep_committed_evidence_and_retry_without_rollback(self):
        _,user,_,values,_=self.transient_switch()
        with storage_lease(user/'launch-settings.json'):
            receipt=commit_restore_switch(user)
        self.assertTrue(receipt['cleanup_pending']);self.assertEqual(get_restore_pending_info(user)['status'],'committed')
        self.assertEqual(json.loads((user/'launch-settings.json').read_text())['ai_profile'],values['ai_profile'])
        with self.assertRaises(RestoreSwitchError):rollback_restore_switch(user)
        self.assertFalse(check_pending_restore(user));self.assertIsNone(get_restore_pending_info(user))
        self.assertNotIn('ai_profile',json.loads((user/'launch-settings.json').read_text()))
        self.assertEqual(len(get_restore_history(user)),1)

    def test_interrupted_preference_write_is_retried_after_commit(self):
        _,user,_,values,_=self.transient_switch();original=Path.replace
        def blocked(path,*args,**kwargs):
            if path.name.startswith('.restore-profile-'):raise PermissionError('generated cleanup interruption')
            return original(path,*args,**kwargs)
        with patch.object(Path,'replace',blocked):self.assertTrue(commit_restore_switch(user)['cleanup_pending'])
        self.assertEqual(get_restore_pending_info(user)['status'],'committed')
        self.assertEqual(json.loads((user/'launch-settings.json').read_text())['ai_profile'],values['ai_profile'])
        self.assertFalse(check_pending_restore(user));self.assertNotIn('ai_profile',json.loads((user/'launch-settings.json').read_text()))
        self.assertEqual(list(user.glob('.restore-profile-*')),[])

    def committed_cleanup_pending(self):
        _,user,_,values,_=self.transient_switch();original=Path.unlink
        def blocked(path,*args,**kwargs):
            if path==user/'restore-pending.json':raise PermissionError('generated sentinel cleanup interruption')
            return original(path,*args,**kwargs)
        with patch.object(Path,'unlink',blocked):self.assertTrue(commit_restore_switch(user)['cleanup_pending'])
        return user,values

    def test_startup_reloads_preferences_after_committed_cleanup(self):
        user,stale=self.committed_cleanup_pending();root=self.base/'release';root.mkdir();observed=[]
        with patch.object(launch_release,'_launch_once',side_effect=lambda r,d,s,**kw:observed.append(s.copy())):
            launch_release.launch(root,user,stale)
        self.assertEqual(len(observed),1);self.assertNotIn('ai_profile',observed[0])
        self.assertEqual(observed[0]['ai_settings'],stale['ai_settings'])

    def test_fresh_command_line_override_survives_committed_cleanup_reload(self):
        user,stale=self.committed_cleanup_pending();root=self.base/'release';root.mkdir();observed=[]
        manual=self.base/'manual.json';manual.write_text(json.dumps(self.running.to_dict()));overrides={'ai_profile':str(manual),'ui_theme':'light'}
        def launched(r,d,s,**kw):observed.append((s.copy(),kw['explicit_profile']))
        with patch.object(launch_release,'_launch_once',side_effect=launched):
            launch_release.launch(root,user,{**stale,**overrides},startup_overrides=overrides)
        self.assertEqual(observed[0][0]['ai_profile'],str(manual));self.assertTrue(observed[0][1])
        self.assertEqual(observed[0][0]['ui_theme'],'light')

    def test_new_persisted_override_is_not_removed_by_transient_cleanup(self):
        _,user,_,values,_=self.transient_switch();manual=self.base/'manual.json';manual.write_text(json.dumps(self.running.to_dict()))
        values['ai_profile']=str(manual);(user/'launch-settings.json').write_text(json.dumps(values))
        commit_restore_switch(user);self.assertEqual(json.loads((user/'launch-settings.json').read_text())['ai_profile'],str(manual))

    def test_owned_launcher_flags_only_transient_not_explicit_profile(self):
        _,user,_,values,_=self.transient_switch();root=self.base/'release';root.mkdir();commands=[]
        frontend=SimpleNamespace(start=lambda *args:None)
        with patch('startup_validation.startup_preflight',return_value={'frontend_activation':'unconfigured'}),patch.object(launch_release,'prepare_frontend',return_value=frontend),patch.object(launch_release,'run_session',side_effect=lambda backend,*args,**kwargs:commands.append(backend)):
            launch_release._launch_once(root,user,values)
            launch_release._launch_once(root,user,values,explicit_profile=True)
        self.assertIn('--ai-profile-transient',commands[0]);self.assertNotIn('--ai-profile-transient',commands[1])

    def test_malformed_pending_record_does_not_invent_transient_backend_flag(self):
        _,user,_,values,_=self.transient_switch();root=self.base/'release';root.mkdir();commands=[]
        (user/'restore-pending.json').write_text('[]')
        frontend=SimpleNamespace(start=lambda *args:None)
        with patch('startup_validation.startup_preflight',return_value={'frontend_activation':'unconfigured'}),patch.object(launch_release,'prepare_frontend',return_value=frontend),patch.object(launch_release,'run_session',side_effect=lambda backend,*args,**kwargs:commands.append(backend)):
            launch_release._launch_once(root,user,values)
        self.assertNotIn('--ai-profile-transient',commands[0])

    def test_real_owned_backend_exposes_transient_choice_and_backs_up_mode(self):
        import os,queue,subprocess,threading,time,urllib.request
        active=self.base/'running.json';active.write_text(json.dumps(self.running.to_dict()))
        self.settings.write_text('{"version":1,"profile":"local:pending.json"}')
        logs=self.base/'child.log';lines=queue.Queue();child=None;reader=None
        command=[sys.executable,'-B',str(REPO/'app/production_server.py'),'--db',str(self.base/'child.sqlite'),'--port','0','--instance-id','a'*32,'--exit-on-stdin-close','--ai-profile',str(active),'--ai-profile-transient','--ai-settings',str(self.settings),'--ai-profiles-dir',str(self.folder),'--runtime-preferences',str(self.base/'launch-settings.json'),'--ai-python',str(self.base/'missing-python'),'--models-root',str(self.base/'missing-models')]
        with logs.open('w',encoding='utf-8') as log:
            child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,encoding='utf-8',env={**launch_release.runtime_environment(),'LOCALAPPDATA':str(self.base/'isolated-user')})
            def read():
                for line in child.stdout:lines.put(line)
            reader=threading.Thread(target=read,daemon=True);reader.start()
            try:
                deadline=time.monotonic()+10;origin=None
                while time.monotonic()<deadline:
                    if child.poll() is not None:raise AssertionError(logs.read_text(encoding='utf-8'))
                    try:line=lines.get(timeout=.1)
                    except queue.Empty:continue
                    if line.startswith('Aredoko production: '):origin=line.split('production: ',1)[1].strip();break
                self.assertIsNotNone(origin);opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));token=None
                def request(path,body=None):
                    headers={'Origin':origin,'Content-Type':'application/json'}
                    if token:headers['X-Aredoko-Token']=token
                    req=urllib.request.Request(origin+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
                    with opener.open(req,timeout=3) as response:return json.load(response)
                session=request('/api/session');token=session['token'];self.assertEqual(session['instance_id'],'a'*32)
                state=request('/api/library/ai/profiles');self.assertFalse(state['command_line_override']);self.assertTrue(state['restored_active'])
                selected=request('/api/library/ai/profile',{'id':'default'});self.assertEqual(selected['selected'],'default')
                output=self.base/'real-bundle';request('/api/library/backup/start',{'consent':True,'output':str(output),'selection':{'settings':True,'history':True,'reader_progress':True,'vectors':False}})
                deadline=time.monotonic()+8
                while time.monotonic()<deadline:
                    job=request('/api/library/backup')
                    if job['state'] in ('complete','failed','cancelled'):break
                    time.sleep(.05)
                self.assertEqual(job['state'],'complete');self.assertTrue(job['published'])
                manifest=json.loads((output/'manifest.json').read_text());self.assertFalse(manifest['active_selection']['ai_override'])
                self.assertEqual(load_profile(output/manifest['active_selection']['ai_profile']),self.running)
                self.assertEqual(json.loads((output/'settings/ai-settings.json').read_text())['profile'],'default')
                self.assertFalse(request('/api/library/ai/status')['available'])
            finally:
                child.stdin.close();child.wait(timeout=10);reader.join(3);child.stdout.close()
        self.assertEqual(child.returncode,0)

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
