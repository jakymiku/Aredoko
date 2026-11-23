"""Owned setup publication/cancellation; generated fixtures, no downloads/GPU."""
from contextlib import ExitStack
import json,os,sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import ai_environment_jobs as jobs
from ai_profiles import DEFAULT_PROFILE
from ai_acquisition_registry import load_trusted_specs
from ai_runtime_preferences import AIRuntimePreferences,read_preferences,runtime_python

class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        directory=self.stack.enter_context(tempfile.TemporaryDirectory());self.data=Path(directory)
        self.preferences=MagicMock();self.preferences.path=self.data/'launch-settings.json'
        self.before={'ai_runtime_root':str(self.data/'existing'),'ai_runtime_manifest_sha256':'a'*64,'models_root':str(self.data/'models')}
        self.preferences.path.write_text(json.dumps(self.before));(self.data/'models').mkdir()
        self.validator=MagicMock();spec=load_trusted_specs(Path(__file__).resolve().parents[1])[0]
        self.manager=jobs.AIEnvironmentJobs(self.preferences,profile=DEFAULT_PROFILE,specifications=((spec[0],self.validator),))
        self.addCleanup(self.manager.close)
        self.inspect=self.stack.enter_context(patch.object(jobs,'inspect_runtime',return_value={'root':self.before['ai_runtime_root'],'python':str(self.data/'existing/Scripts/python.exe'),'manifest_sha256':'a'*64}))
        self.bind=self.stack.enter_context(patch.object(jobs,'bind_runtime'))
        self.probe=self.stack.enter_context(patch.object(jobs,'probe_model',return_value={'pass':True,'device':'cpu','profile':DEFAULT_PROFILE.key}))
        self.acquire=self.stack.enter_context(patch.object(jobs,'acquire',side_effect=AssertionError('Unexpected download')))
        self.build=self.stack.enter_context(patch.object(jobs,'build_environment',side_effect=AssertionError('Unexpected rebuild')))
        def select(**kwargs):kwargs['publish'](lambda:None);return {'saved':True}
        self.preferences.select.side_effect=select

    def finish(self):
        self.manager.thread.join(5);self.assertFalse(self.manager.thread.is_alive())
        return self.manager.snapshot()

    def test_reuses_verified_runtime_and_model_then_publishes_only_after_probe(self):
        result=self.manager.describe();self.assertTrue(result['supported']);self.assertEqual(len(self.manager.catalog.entries),44)
        self.manager.start({'consent':True});result=self.finish()
        self.assertEqual(result['state'],'complete');self.assertTrue(result['saved'])
        self.inspect.assert_called_once();self.assertTrue(self.inspect.call_args.kwargs['verify'])
        self.probe.assert_called_once();self.preferences.select.assert_called_once()
        self.assertEqual(self.preferences.select.call_args.kwargs['model_target']['role'],'embedding')
        self.assertFalse(self.manager.cancel()['cancel_accepted'])

    def test_cancel_during_probe_never_publishes_settings(self):
        entered=threading.Event();release=threading.Event()
        def probe(*args,**kwargs):
            entered.set();release.wait(3)
            if kwargs['cancelled']():raise InterruptedError('generated cancel')
        self.probe.side_effect=probe
        self.manager.start({'consent':True});self.assertTrue(entered.wait(2))
        self.assertTrue(self.manager.cancel()['cancel_accepted']);release.set()
        self.assertEqual(self.finish()['state'],'cancelled');self.preferences.select.assert_not_called()
        self.assertEqual(json.loads(self.preferences.path.read_text()),self.before)

    def test_probe_failure_preserves_previous_selection(self):
        self.probe.side_effect=RuntimeError('generated model failure')
        self.manager.start({'consent':True});result=self.finish()
        self.assertEqual(result['state'],'failed');self.assertFalse(result['saved'])
        self.preferences.select.assert_not_called();self.assertEqual(json.loads(self.preferences.path.read_text()),self.before)

    def test_consent_busy_and_start_failure_are_explicit(self):
        for body in ({},{'consent':1},{'consent':True,'path':'untrusted'}):
            with self.assertRaises(ValueError):self.manager.start(body)
        self.manager.busy=lambda:True
        with self.assertRaises(jobs.EnvironmentBusy):self.manager.start({'consent':True})
        self.manager.busy=lambda:False
        with patch.object(threading.Thread,'start',side_effect=RuntimeError('generated start failure')):
            with self.assertRaises(jobs.EnvironmentBusy):self.manager.start({'consent':True})
        self.assertEqual(self.manager.snapshot()['state'],'failed');self.assertTrue(self.manager.close())

    def test_bandwidth_limit_reaches_runtime_and_model_acquisition(self):
        for rate in (True,0,-1,1.5,2**40+1):
            with self.assertRaises(ValueError):self.manager.start({'consent':True,'bytes_per_second':rate})
        self.validator.side_effect=ValueError('Generated missing model')
        self.acquire.side_effect=None;self.acquire.return_value={'root':str(self.data/'downloaded')}
        self.manager.start({'consent':True,'bytes_per_second':2_000_000});self.assertEqual(self.finish()['state'],'complete')
        self.assertEqual(self.acquire.call_args.kwargs['bytes_per_second'],2_000_000)
        self.assertEqual(self.manager.snapshot()['bytes_per_second'],2_000_000)
        self.inspect.side_effect=ValueError('Generated missing environment')
        self.acquire.reset_mock()
        def cancelled(*args,**kwargs):self.manager.cancel();raise InterruptedError('generated cancel')
        self.acquire.side_effect=cancelled
        with patch.object(jobs,'verify_base'):
            self.manager.start({'consent':True,'bytes_per_second':1_000_000});self.assertEqual(self.finish()['state'],'cancelled')
        self.assertEqual(self.acquire.call_args.kwargs['bytes_per_second'],1_000_000)

    def test_failed_model_validation_acquires_only_trusted_model(self):
        self.validator.side_effect=ValueError('generated missing model')
        target=self.data/'downloaded';target.mkdir()
        self.acquire.side_effect=None;self.acquire.return_value={'root':str(target)}
        self.manager.start({'consent':True});self.assertEqual(self.finish()['state'],'complete')
        self.assertEqual(self.acquire.call_args.args[0].key,'embeddinggemma-2')
        self.assertEqual(self.preferences.select.call_args.kwargs['models_root'],str(target))

    def test_new_environment_never_replaces_existing_and_is_sealed_after_probe(self):
        self.inspect.side_effect=ValueError('Existing runtime changed')
        target=self.manager.default_target
        cache=self.data/'runtime-cache'/jobs.RECIPES[target]['cache_dir'];cache.mkdir(parents=True)
        for item in self.manager.catalogs[target].entries:(cache/item.path).write_bytes(b'generated')
        order=[]
        self.build.side_effect=lambda *args,**kwargs:order.append('build')
        self.probe.side_effect=lambda *args,**kwargs:(order.append('probe') or {'pass':True,'device':'cpu','profile':DEFAULT_PROFILE.key})
        with patch.object(jobs,'verify_base',side_effect=lambda *args,**kwargs:order.append('base')),patch.object(jobs,'seal',side_effect=lambda *args,**kwargs:order.append('seal')):
            self.manager.start({'consent':True});self.assertEqual(self.finish()['state'],'complete')
        self.assertEqual(order,['base','build','probe','seal'])
        self.assertNotEqual(self.build.call_args.args[2],Path(self.before['ai_runtime_root']))
        self.assertEqual(self.build.call_args.args[1],cache)
        self.assertTrue(all(path.read_bytes()==b'generated' for path in cache.iterdir()))

    def test_cancelled_download_cannot_publish_settings_or_mark_runtime_ready(self):
        self.inspect.side_effect=ValueError('Generated missing runtime')
        def acquire(*args,**kwargs):
            self.manager.cancel();kwargs['publish'](lambda:None)
        self.acquire.side_effect=acquire
        with patch.object(jobs,'verify_base'):
            self.manager.start({'consent':True});self.assertEqual(self.finish()['state'],'cancelled')
        self.build.assert_not_called();self.probe.assert_not_called();self.preferences.select.assert_not_called()

    def test_detect_nvidia_gpu_and_cpu_target_selection(self):
        with patch.dict(os.environ,{'AREDOKO_AI_SETUP_TARGET':'cuda'},clear=False):
            self.assertEqual(jobs.detect_nvidia_gpu()['target'],'cuda')
        with patch.dict(os.environ,{'AREDOKO_AI_SETUP_TARGET':'cpu'},clear=False):
            self.assertEqual(jobs.detect_nvidia_gpu()['target'],'cpu')
        with patch.dict(os.environ,{'CUDA_VISIBLE_DEVICES':'-1'},clear=False):
            os.environ.pop('AREDOKO_AI_SETUP_TARGET',None)
            self.assertEqual(jobs.detect_nvidia_gpu()['target'],'cpu')
            desc=self.manager.describe()
            self.assertEqual(desc['detected_target'],'cpu')
            self.assertFalse(desc['nvidia_detected'])
        with patch.dict(os.environ,{},clear=False):
            os.environ.pop('AREDOKO_AI_SETUP_TARGET',None)
            os.environ.pop('AREDOKO_AI_DEVICE',None)
            os.environ.pop('CUDA_VISIBLE_DEVICES',None)
            with patch.object(jobs.ctypes,'WinDLL',side_effect=OSError('missing nvcuda')):
                self.assertEqual(jobs.detect_nvidia_gpu()['target'],'cpu')
        summary=self.manager.describe()
        self.assertIn('cuda',summary['targets']);self.assertIn('cpu',summary['targets'])
        self.assertLess(summary['targets']['cpu']['download_bytes'],summary['targets']['cuda']['download_bytes'])

    def test_cpu_target_uses_lightweight_cache_and_rejects_invalid_target(self):
        for bad in ('rocm',None,123):
            with self.assertRaises(ValueError):self.manager.start({'consent':True,'target':bad})
        self.inspect.side_effect=ValueError('Generated missing runtime')
        self.build.side_effect=None
        cache=self.data/'runtime-cache/wheels-cpu';cache.mkdir(parents=True)
        for item in self.manager.catalogs['cpu'].entries:(cache/item.path).write_bytes(b'generated')
        with patch.object(jobs,'verify_base'),patch.object(jobs,'seal',return_value={'root':'r','python':'p','manifest_sha256':'a'*64}) as sealed:
            self.manager.start({'consent':True,'target':'cpu'});result=self.finish()
        self.assertEqual(result['state'],'complete')
        self.assertEqual(result['target'],'cpu')
        self.assertIn('ai-cpu-',self.build.call_args.args[2].name)
        self.assertEqual(self.build.call_args.args[1],cache)
        self.assertEqual(sealed.call_args.kwargs['target'],'cpu')

    def test_switch_installed_cpu_preserves_model_and_cuda_pin(self):
        cuda=self.data/'runtimes'/('ai-cu128-'+'a'*24)
        cpu=self.data/'runtimes'/('ai-cpu-'+'b'*24)
        for root in (cpu,cuda):
            root.mkdir(parents=True)
            (root/jobs.MARKER).touch()
        self.before.update(ai_runtime_root=str(cuda))
        self.preferences.path.write_text(json.dumps(self.before))
        preferences=AIRuntimePreferences(self.preferences.path,self.data,DEFAULT_PROFILE,active_python=cuda/'Scripts/python.exe')
        self.manager.preferences=preferences
        self.manager._remember(cpu,'b'*64)
        self.inspect.return_value={'root':str(cpu),'python':str(cpu/'Scripts/python.exe'),'manifest_sha256':'b'*64,'abi':{'compute':'cpu'},'cache_required':False}
        summary=self.manager.describe()
        self.assertEqual(summary['active_target'],'cuda')
        self.assertTrue(summary['targets']['cpu']['installed'])
        with patch('ai_runtime_preferences.inspect_runtime',return_value=self.inspect.return_value) as selection:
            self.manager.start({'consent':True,'target':'cpu','installed_only':True})
            self.assertEqual(self.finish()['state'],'complete')
            self.assertTrue(self.manager.describe()['restart_required'])
            self.assertEqual(selection.call_args.kwargs['expected'],'b'*64)
            settings=read_preferences(preferences.path)
            self.assertEqual(runtime_python(settings,'fallback','unavailable'),cpu/'Scripts/python.exe')
        self.inspect.assert_called_once()
        self.assertEqual(self.inspect.call_args.kwargs['expected'],'b'*64)
        self.assertEqual(settings['models_root'],self.before['models_root'])
        self.assertEqual(self.manager._installed('cuda',{}),[(cuda,'a'*64)])
        self.acquire.assert_not_called();self.build.assert_not_called();self.probe.assert_not_called()

    def test_installed_only_never_downloads_on_missing_candidate(self):
        self.manager.start({'consent':True,'target':'cpu','installed_only':True})
        self.assertEqual(self.finish()['state'],'failed')
        self.preferences.select.assert_not_called()
        self.acquire.assert_not_called();self.build.assert_not_called()

if __name__=='__main__':unittest.main()
