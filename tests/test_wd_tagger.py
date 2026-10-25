"""WD profile/controller/setup contracts; stub scores are not model quality."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
sys.path.insert(0,str(ROOT/'tools'))
from ai_process import AIUnavailable
from ai_search import AIBusy
from tag_suggestions import SuggestionConflict,TagSuggestions
from tagger_profile import WDProfile,load_profile,RUNTIME_VERSION
from wd_tagger import WDTagger,create_tagger
import setup_wd_tagger as setup
from create_preview_fixture import png


class WDTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo=Path(self.temp.name)
        self.config=load_profile(ROOT).data()
        self.config['label_count']=5
        self.config['timeout_seconds']=5
        self.csv=b'tag_id,name,category,count\n1,general,9,100\n2,red_hair,0,100\n3,hatsune_miku,4,100\n4,nsfw_fixture,0,100\n5,lower,0,100\n'
        self.model=b'not an ONNX model - controller fixture only'
        for name,data in [('model.onnx',self.model),('selected_tags.csv',self.csv)]:
            self.config['artifacts'][name]={'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        self.profile=WDProfile.from_dict(self.config)
        self.directory=self.profile.directory(self.repo)
        self.directory.mkdir(parents=True)
        (self.directory/'model.onnx').write_bytes(self.model)
        (self.directory/'selected_tags.csv').write_bytes(self.csv)
        (self.directory/'aredoko-source.json').write_text(json.dumps(self.profile.identity()),encoding='utf-8')
        (self.directory/'aredoko-runtime.json').write_text(json.dumps({'onnxruntime':RUNTIME_VERSION}),encoding='utf-8')
        self.adapter=WDTagger(self.repo,self.profile)
        self.adapter.python=Path(sys.executable)
        self.addCleanup(self.adapter.close)
        self.source={'data':png(),'mime':'image/png','source':{'page':0}}

    def test_profile_is_immutable_and_all_policy_changes_have_distinct_provenance(self):
        original=self.profile.key
        self.config['general_threshold']=.5
        self.assertEqual(self.profile.key,original)
        updated=WDProfile.from_dict(self.config)
        self.assertNotEqual(updated.key,original)
        other=WDTagger(self.repo,updated)
        self.assertNotEqual(self.adapter.info.record(),other.info.record())
        self.assertTrue(self.adapter.status()['available'])
        self.profile.verify(self.repo,hashes=True)

    def test_explicit_relocated_models_reach_controller_and_worker(self):
        relocated=self.repo/'relocated models'
        (self.repo/'models').rename(relocated)
        adapter=WDTagger(self.repo,self.profile,ai_python=sys.executable,models_root=relocated)
        self.addCleanup(adapter.close)
        self.assertTrue(adapter.status()['available'])
        self.assertEqual(adapter.info,self.adapter.info)
        with patch('wd_tagger.subprocess.Popen',side_effect=RuntimeError('capture only')) as spawn:
            with self.assertRaises(RuntimeError):adapter._scores(b'fixture',lambda:False)
        command=spawn.call_args.args[0]
        self.assertEqual(command[0],sys.executable)
        self.assertEqual(command[command.index('--models-root')+1],str(relocated))
        with patch.object(adapter,'_scores',return_value=[0,.9,.95,0,0]):
            result=adapter.suggest(self.source,lambda:False)
        self.assertTrue(result)

    def test_invalid_profiles_paths_limits_hashes_and_types(self):
        bads=[('model_directory','../models/a'),('model_directory','C:/elsewhere'),
              ('model_directory','models/../private'),('model_directory','models'),
              ('model_directory','models\\elsewhere'),('model_directory','/models/a'),
              ('revision','main'),('general_threshold',True),('character_threshold',float('nan')),
              ('max_candidates',31),('timeout_seconds',181),('cpu_threads',0),('input_size',False)]
        for key,value in bads:
            with self.subTest(key=key,value=value):
                config=self.profile.data();config[key]=value
                with self.assertRaises(ValueError):WDProfile.from_dict(config)
        config=self.profile.data();config['extra']='no'
        with self.assertRaises(ValueError):WDProfile.from_dict(config)
        config=self.profile.data();config['artifacts']['selected_tags.csv']['sha256']='bad'
        with self.assertRaises(ValueError):WDProfile.from_dict(config)

    def test_missing_or_modified_local_assets_never_start_worker(self):
        (self.directory/'model.onnx').write_bytes(b'x'*len(self.model))
        with self.assertRaises(ValueError):self.profile.verify(self.repo,hashes=True)
        (self.directory/'aredoko-runtime.json').unlink()
        with patch('wd_tagger.subprocess.Popen',side_effect=AssertionError('must not launch')):
            with self.assertRaises(AIUnavailable):self.adapter.suggest(self.source,lambda:False)
        self.assertFalse(create_tagger(repo=self.repo).status()['available'])
        with patch.object(Path,'is_symlink',return_value=True):
            with self.assertRaises(ValueError):self.profile.directory(self.repo)

    def test_sealed_runtime_owns_onnx_version_without_legacy_model_marker(self):
        (self.directory/'aredoko-runtime.json').unlink()
        runtime=self.repo/'runtime';runtime.mkdir();self.adapter.python=runtime/'python.exe';self.adapter.python.write_bytes(b'fixture')
        (runtime/'aredoko-ai-runtime.json').write_text('{}')
        folder=runtime/f'Lib/site-packages/onnxruntime-{RUNTIME_VERSION}.dist-info';folder.mkdir(parents=True)
        metadata=folder/'METADATA';metadata.write_text('Name: onnxruntime\nVersion: '+RUNTIME_VERSION+'\n')
        with patch('wd_tagger.inspect_runtime',return_value={'abi':{'modules':['onnxruntime']}}):
            self.assertTrue(self.adapter.status()['available'])
            metadata.write_text('Name: onnxruntime\nVersion: wrong\n');self.assertFalse(self.adapter.status()['available'])
        with patch('wd_tagger.inspect_runtime',side_effect=ValueError('invalid pack')):
            self.assertFalse(self.adapter.status()['available'])
        self.assertFalse((self.directory/'aredoko-runtime.json').exists())

    def test_threshold_category_topk_and_no_nsfw_word_filter(self):
        with patch.object(self.adapter,'_scores',return_value=[.99,.7,.9,.6,.35]):
            proposals=self.adapter.suggest(self.source,lambda:False)
        self.assertEqual([p.tag for p in proposals],['hatsune_miku','red_hair','nsfw_fixture'])
        self.assertTrue(all(p.page==0 and '正解確率ではありません' in p.explanation for p in proposals))
        with patch.object(self.adapter,'_scores',return_value=[1,.35,.85,.35,0]):
            self.assertEqual(self.adapter.suggest(self.source,lambda:False),[])
        config=self.profile.data();config['max_candidates']=1
        limited=WDTagger(self.repo,WDProfile.from_dict(config));limited.python=Path(sys.executable)
        with patch.object(limited,'_scores',return_value=[.9,.7,.9,.8,.4]):
            self.assertEqual([p.tag for p in limited.suggest(self.source,lambda:False)],['hatsune_miku'])

    def test_shared_inference_lock_scan_closed_and_cleanup(self):
        ai=SimpleNamespace(inference=threading.Lock(),guard=threading.Lock(),worker=None,_closed=False,_last_activity=0)
        self.adapter.ai=ai
        ai.inference.acquire()
        try:
            with self.assertRaises(AIBusy):self.adapter.suggest(self.source,lambda:False)
        finally:ai.inference.release()
        ai.worker=SimpleNamespace(is_alive=lambda:True)
        with self.assertRaises(AIBusy):self.adapter.suggest(self.source,lambda:False)
        self.assertFalse(ai.inference.locked())
        ai.worker=None
        with patch.object(self.adapter,'_scores',side_effect=AIUnavailable('fixture failure')):
            with self.assertRaises(AIUnavailable):self.adapter.suggest(self.source,lambda:False)
        self.assertGreater(ai._last_activity,0)
        self.assertFalse(ai.inference.locked())
        ai._closed=True
        with self.assertRaises(AIUnavailable):self.adapter.suggest(self.source,lambda:False)
        self.adapter.close()
        self.assertFalse(self.adapter.status()['available'])

    def worker(self,mode):
        real=subprocess.Popen
        self.processes=[]
        self.spawned=threading.Event()
        code='import sys,json,time; request=json.loads(sys.stdin.buffer.readline()); '
        if mode=='hang':code+='time.sleep(30)'
        elif mode=='exit':code+='sys.exit(3)'
        elif mode=='big':code+="sys.stdout.write('x'*2000001);sys.stdout.flush();time.sleep(30)"
        else:
            value={'key':self.profile.key,'scores':[.5]*5}
            if mode=='wrong-key':value['key']='wrong'
            if mode=='bad-score':value['scores'][0]=True
            if mode=='wrong-size':value['scores']=[.5]
            if mode=='nan':value['scores'][0]=float('nan')
            code+='print('+repr(json.dumps(value))+',flush=True)'
        def spawn(args,**kwargs):
            process=real([sys.executable,'-u','-c',code],**kwargs)
            self.processes.append(process)
            self.spawned.set()
            return process
        return patch('wd_tagger.subprocess.Popen',side_effect=spawn)

    def assert_stopped(self):
        self.assertTrue(self.processes)
        for process in self.processes:
            self.assertIsNotNone(process.poll())
            self.assertTrue(process.stdin.closed)
            self.assertTrue(process.stdout.closed)

    def test_real_owned_process_protocol_and_invalid_responses_cleanup(self):
        with self.worker('valid'):
            self.assertEqual(self.adapter._scores(png(),lambda:False),[.5]*5)
        self.assert_stopped()
        for mode in ('wrong-key','bad-score','wrong-size','nan','exit','big'):
            with self.subTest(mode=mode),self.worker(mode):
                with self.assertRaises(AIUnavailable):self.adapter._scores(png(),lambda:False)
            self.assert_stopped()

    def test_timeout_cancel_and_close_stop_owned_worker(self):
        with self.worker('hang'):
            with self.assertRaisesRegex(AIUnavailable,'制限時間'):self.adapter._scores(png(),lambda:False)
        self.assert_stopped()
        # The runtime verifier now observes cancellation before process launch.
        # Keep this case about an actual spawned worker, not callback call count.
        def cancel():return self.spawned.is_set()
        with self.worker('hang'):
            with self.assertRaises(SuggestionConflict):self.adapter._scores(png(),cancel)
        self.assert_stopped()
        with self.worker('hang'):
            with self.assertRaises(SuggestionConflict):self.adapter._scores(png(),lambda:True)
            self.assertEqual(self.processes,[])
        errors=[]
        with self.worker('hang'):
            def run():
                try:
                    self.adapter.suggest(self.source,lambda:False)
                except Exception as error:errors.append(error)
            worker=threading.Thread(target=run)
            worker.start();self.assertTrue(self.spawned.wait(3))
            self.adapter.close();worker.join(3)
            self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors),1)
        self.assertIsInstance(errors[0],(AIUnavailable,SuggestionConflict))
        for process in self.processes:self.assertIsNotNone(process.poll())

    def test_setup_is_dry_by_default_and_refuses_unapproved_environment(self):
        with (patch.object(sys,'argv',['setup_wd_tagger']),patch.object(setup.subprocess,'run',side_effect=AssertionError('no child')),
                contextlib.redirect_stdout(io.StringIO()) as output):
            setup.main()
        plan=json.loads(output.getvalue())
        self.assertEqual(plan['model_bytes']+plan['wheel_bytes'],481921772)
        self.assertEqual(plan['aggregate_rate'],6000000)
        with (patch.object(sys,'argv',['setup_wd_tagger','--install-and-download']),patch.object(sys,'prefix',str(self.repo)),
                patch.object(setup.subprocess,'run',side_effect=AssertionError('no install')),
                contextlib.redirect_stdout(io.StringIO())):
            with self.assertRaises(RuntimeError):setup.main()
        for rate in ('0','6000001'):
            with patch.object(sys,'argv',['setup_wd_tagger','--rate',rate]),contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):setup.main()
        before={'torch':'keep','numpy':'keep'}
        after={**before,**{k:v[0] for k,v in setup.PACKAGES.items()}}
        setup.check_inventory(before,after)
        for changed in ({**after,'torch':'changed'},{**after,'surprise':'1'}):
            with self.assertRaises(RuntimeError):setup.check_inventory(before,changed)
        self.assertIn('--hash=sha256:',setup.requirements())

    def test_setup_offline_install_sequence_and_preserved_packages(self):
        before={'torch':'keep','numpy':'keep','pillow':'keep','packaging':'keep','sympy':'keep','huggingface-hub':'keep'}
        after={**before,**{k:v[0] for k,v in setup.PACKAGES.items()}}
        proxy=SimpleNamespace(server_address=('127.0.0.1',1234),gate=SimpleNamespace(bytes=12345),
            serve_forever=lambda:None,shutdown=lambda:None,server_close=lambda:None)
        (self.directory/'aredoko-runtime.json').unlink()
        with (patch.object(setup,'REPO',self.repo),patch.object(setup,'load_profile',return_value=self.profile),
              patch.object(setup,'require_environment'),patch.object(setup,'inventory',side_effect=[before,after]),
              patch.object(setup,'ThrottledProxy',return_value=proxy),patch.object(setup.subprocess,'run') as run,
              patch.object(sys,'argv',['setup_wd_tagger','--install-and-download']),contextlib.redirect_stdout(io.StringIO())):
            setup.main()
        commands=[call.args[0] for call in run.call_args_list]
        self.assertEqual(len(commands),6)
        self.assertIn('download',commands[1])
        self.assertIn('--require-hashes',commands[1])
        self.assertTrue({'--no-index','--no-deps','--require-hashes'}<=set(commands[2]))
        self.assertIn('--download-child',commands[-1])
        self.assertEqual(json.loads((self.directory/'aredoko-runtime.json').read_text()),{'onnxruntime':RUNTIME_VERSION})
        report=json.loads((self.repo/'data/wd-setup/result.json').read_text())
        self.assertTrue(report['existing_packages_unchanged'])
        self.assertEqual(report['tls_bytes'],12345)
        for call in run.call_args_list[1:]:
            self.assertEqual(call.kwargs['env']['HF_HUB_DISABLE_XET'],'1')
            self.assertEqual(call.kwargs['env']['HTTPS_PROXY'],'http://127.0.0.1:1234')


if __name__=='__main__':unittest.main()
