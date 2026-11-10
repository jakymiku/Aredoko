"""Generated disposable cache only; models/venv/database preservation checks."""
import json
from pathlib import Path
import sys,tempfile,threading,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import runtime_cache as cache
from storage_lease import storage_lease

class RuntimeCacheTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.data=Path(temp.name);self.settings=self.data/'launch-settings.json'
        self.runtime=self.data/'runtimes/verified';self.runtime.mkdir(parents=True)
        self.manager=cache.RuntimeCache(self.settings);self.addCleanup(self.manager.close)
        self.root=self.manager.root;self.root.mkdir(parents=True)
        self.wheel=self.root/'generated.whl';self.wheel.write_bytes(b'generated cache')
        self.settings.write_text(json.dumps({'ai_runtime_root':str(self.runtime),'ai_runtime_manifest_sha256':'a'*64}))
        (self.runtime/'aredoko-ai-runtime.json').write_text(json.dumps({'wheel_cache':str(self.root)}))
        self.originals={self.data/'models/model.safetensors':b'generated model',self.runtime/'python.exe':b'generated executable',self.data/'catalog.sqlite':b'generated DB'}
        for path,content in self.originals.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
        self.addCleanup(patch.stopall)
        patch.object(cache,'recipe',return_value={'entries':[{'filename':'generated.whl'}]}).start()
        self.info={'root':str(self.runtime),'cache_required':False}
        self.inspect=patch.object(cache,'inspect_runtime',return_value=self.info).start()

    def finish(self):
        self.manager.thread.join(5);self.assertFalse(self.manager.thread.is_alive())
        return self.manager.snapshot()

    def test_clear_removes_only_owned_cache_after_full_verification(self):
        before=self.settings.read_bytes()
        self.assertTrue(self.manager.describe()['can_delete'])
        self.manager.start({'consent':True});result=self.finish()
        self.assertEqual(result['state'],'complete');self.assertFalse(self.wheel.exists())
        self.assertEqual(self.settings.read_bytes(),before)
        for path,content in self.originals.items():self.assertEqual(path.read_bytes(),content)
        self.assertTrue(any(call.kwargs.get('verify') is True for call in self.inspect.call_args_list))

    def test_unknown_file_or_unverified_runtime_preserves_all_cache(self):
        unknown=self.root/'model.safetensors';unknown.write_bytes(b'not a cache')
        self.manager.start({'consent':True});self.assertEqual(self.finish()['state'],'failed')
        self.assertTrue(self.wheel.exists());self.assertTrue(unknown.exists())
        unknown.unlink();self.inspect.return_value={'root':str(self.runtime),'cache_required':True}
        self.manager.start({'consent':True});self.assertEqual(self.finish()['state'],'failed')
        self.assertTrue(self.wheel.exists())

    def test_active_job_or_shared_use_lease_protects_cache(self):
        self.manager.busy=lambda:True
        with self.assertRaises(cache.CacheBusy):self.manager.start({'consent':True})
        self.manager.busy=lambda:False
        with cache.cache_lease(self.data):
            self.manager.start({'consent':True});self.assertEqual(self.finish()['state'],'failed')
        self.assertTrue(self.wheel.exists())

    def test_cancel_before_deletion_keeps_cache(self):
        entered=threading.Event();release=threading.Event()
        def inspect(*args,**kwargs):
            entered.set();release.wait(3)
            if kwargs['cancelled']():raise InterruptedError('generated cancellation')
            return self.info
        with patch.object(cache,'inspect_runtime',side_effect=inspect):
            self.manager.start({'consent':True});self.assertTrue(entered.wait(2))
            self.assertTrue(self.manager.cancel()['cancel_accepted']);release.set()
            self.assertEqual(self.finish()['state'],'cancelled')
        self.assertTrue(self.wheel.exists())

    def test_consent_and_arbitrary_paths_cannot_be_supplied(self):
        for body in ({},{'consent':1},{'consent':True,'path':str(self.runtime)}):
            with self.assertRaises(ValueError):self.manager.start(body)
        self.assertTrue(self.wheel.exists())

    def test_worker_start_failure_is_reported_without_unjoinable_thread(self):
        with patch.object(threading.Thread,'start',side_effect=RuntimeError('generated failure')):
            with self.assertRaises(cache.CacheBusy):self.manager.start({'consent':True})
        self.assertEqual(self.manager.snapshot()['state'],'failed');self.assertTrue(self.manager.close())

    def test_http_requires_session_origin_and_explicit_consent(self):
        from http.server import ThreadingHTTPServer
        import urllib.request,urllib.error
        from production import ProductionCatalog
        from production_server import production_handler,DisabledAI
        from ai_settings import AIProfileSettings
        catalog=ProductionCatalog(self.data/'http-catalog.sqlite')
        profiles=AIProfileSettings(self.data,self.data/'ai-settings.json',profile_directory=self.data/'profiles')
        handler=production_handler(catalog,'generated-token',DisabledAI(),profiles=profiles,runtime_preferences=self.settings)
        server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        origin=f'http://127.0.0.1:{server.server_port}'
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def request(route,body=None,headers=None):
            values={'Origin':origin,'X-Aredoko-Token':'generated-token','Content-Type':'application/json'}
            if headers is not None:values=headers
            data=json.dumps(body).encode() if body is not None else None
            with opener.open(urllib.request.Request(origin+route,data=data,headers=values),timeout=3) as response:
                return response.status,json.load(response)
        try:
            self.assertTrue(request('/api/library/runtime-cache')[1]['can_delete'])
            self.assertFalse(request('/api/library/ai/setup/build')[1]['supported'])
            for headers in ({'Origin':origin},{'X-Aredoko-Token':'generated-token'}):
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    request('/api/library/runtime-cache/clear',{'consent':True},headers)
                self.assertEqual(rejected.exception.code,403);rejected.exception.close()
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    request('/api/library/ai/setup/build/start',{'consent':True},headers)
                self.assertEqual(rejected.exception.code,403);rejected.exception.close()
            for body in ({},{'consent':1},{'consent':True,'runtime_root':str(self.runtime)}):
                with self.assertRaises(urllib.error.HTTPError) as rejected:request('/api/library/ai/setup/build/start',body)
                self.assertEqual(rejected.exception.code,400);rejected.exception.close()
            for body in ({},{'consent':1},{'consent':True,'path':str(self.runtime)}):
                with self.assertRaises(urllib.error.HTTPError) as rejected:request('/api/library/runtime-cache/clear',body)
                self.assertEqual(rejected.exception.code,400);rejected.exception.close()
            status,_=request('/api/library/runtime-cache/clear',{'consent':True});self.assertEqual(status,202)
            handler.cache_jobs.thread.join(3)
            self.assertEqual(request('/api/library/runtime-cache/job')[1]['state'],'complete')
            self.assertFalse(self.wheel.exists())
        finally:
            server.shutdown();server.server_close();thread.join(3)
            handler.environment_jobs.close();handler.cache_jobs.close();handler.setup_jobs.close();handler.download_jobs.close();catalog.close()

if __name__=='__main__':unittest.main()
