"""Owned generated-folder validation jobs; no models/network downloads/GPU/GUI."""
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tools'),str(ROOT/'tests')]
from ai_profiles import DEFAULT_PROFILE
from ai_runtime import inspect_runtime,MARKER
from ai_runtime_preferences import AIRuntimePreferences
from ai_setup_jobs import AISetupJobs,SetupBusy
from storage_lease import storage_lease
from test_ai_runtime import fixture


class SetupJobTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='aredoko-setup-job-');self.addCleanup(temporary.cleanup)
        self.base=Path(temporary.name);self.pack=fixture(self.base/'pack')
        self.path=self.base/'launch-settings.json';self.path.write_text('{"ui_theme":"dark"}')
        self.before=self.path.read_bytes()
        self.preferences=AIRuntimePreferences(self.path,self.base,DEFAULT_PROFILE,active_python=sys.executable)
        self.jobs=AISetupJobs(self.preferences);self.addCleanup(self.jobs.close)

    def finish(self):
        self.jobs.thread.join(timeout=5);self.assertFalse(self.jobs.thread.is_alive())
        return self.jobs.snapshot()

    def start(self,**fields):
        return self.jobs.start({'runtime_root':str(self.pack),'consent':True,**fields})

    def test_complete_has_exact_progress_next_restart_and_no_source_changes(self):
        before={p:(hashlib.sha256(p.read_bytes()).digest(),p.stat().st_mtime_ns) for p in self.pack.rglob('*') if p.is_file()}
        expected=inspect_runtime(self.pack)
        self.start();result=self.finish()
        self.assertEqual(result['state'],'complete');self.assertTrue(result['saved'])
        self.assertTrue(result['result']['restart_required'])
        self.assertEqual(result['files_done'],expected['files']);self.assertEqual(result['files_total'],expected['files'])
        self.assertEqual(result['bytes_done'],expected['bytes']);self.assertEqual(result['bytes_total'],expected['bytes'])
        self.assertEqual(json.loads(self.path.read_text())['ui_theme'],'dark')
        self.assertEqual(before,{p:(hashlib.sha256(p.read_bytes()).digest(),p.stat().st_mtime_ns) for p in self.pack.rglob('*') if p.is_file()})
        self.assertFalse(result['result']['inference_verified'])

    def test_unlisted_corrupt_pack_fails_and_preserves_preferences(self):
        (self.pack/'unknown.py').write_bytes(b'generated')
        self.start();result=self.finish()
        self.assertEqual(result['state'],'failed');self.assertEqual(result['error_code'],'validation_failed')
        self.assertFalse(result['saved']);self.assertEqual(self.path.read_bytes(),self.before)
        self.assertNotIn(str(self.pack),result['message'])

    def test_cancellation_is_owned_and_busy_does_not_replace_running_job(self):
        entered=threading.Event();release=threading.Event()
        def controlled(*args,**kwargs):
            original=kwargs['progress']
            def report(counts):
                original(counts)
                if counts['bytes_done']>0:entered.set();release.wait(timeout=4)
            return inspect_runtime(*args,**{**kwargs,'progress':report})
        self.addCleanup(release.set)
        with patch('ai_runtime_preferences.inspect_runtime',side_effect=controlled):
            first=self.start();self.assertTrue(entered.wait(timeout=3))
            with self.assertRaises(SetupBusy):self.start()
            with self.assertRaises(KeyError):self.jobs.cancel('0'*32)
            self.assertEqual(self.jobs.snapshot()['job_id'],first['job_id'])
            self.assertTrue(self.jobs.cancel(first['job_id'])['cancel_accepted']);release.set()
            result=self.finish()
        self.assertEqual(result['state'],'cancelled');self.assertFalse(result['saved'])
        self.assertEqual(self.path.read_bytes(),self.before)
        self.assertEqual(list(self.base.glob('*.tmp')),[])

    def test_cancel_after_temp_write_but_before_commit_keeps_old_settings(self):
        entered=threading.Event();release=threading.Event();publish=self.jobs._publish
        def controlled(operation):
            entered.set();release.wait(timeout=4);publish(operation)
        self.addCleanup(release.set)
        with patch.object(self.jobs,'_publish',side_effect=controlled):
            first=self.start();self.assertTrue(entered.wait(timeout=3))
            self.assertTrue(list(self.base.glob('*.tmp')))
            self.assertTrue(self.jobs.cancel(first['job_id'])['cancel_accepted'])
            release.set();result=self.finish()
        self.assertEqual(result['state'],'cancelled');self.assertFalse(result['saved'])
        self.assertEqual(self.path.read_bytes(),self.before);self.assertEqual(list(self.base.glob('*.tmp')),[])

    def test_cancel_cannot_claim_rollback_after_atomic_commit(self):
        entered=threading.Event();release=threading.Event();started=threading.Event();answers=[]
        replace=os.replace
        def controlled(*args):
            entered.set();release.wait(timeout=4);return replace(*args)
        self.addCleanup(release.set)
        with patch('ai_runtime_preferences.os.replace',side_effect=controlled):
            first=self.start();self.assertTrue(entered.wait(timeout=3))
            def cancel():started.set();answers.append(self.jobs.cancel(first['job_id']))
            canceller=threading.Thread(target=cancel);canceller.start()
            self.assertTrue(started.wait(timeout=2));release.set();canceller.join(timeout=3)
            self.assertFalse(canceller.is_alive());result=self.finish()
        self.assertTrue(result['saved']);self.assertEqual(result['state'],'complete')
        self.assertFalse(answers[0]['cancel_accepted']);self.assertNotEqual(self.path.read_bytes(),self.before)

    def test_close_revokes_late_commit_even_if_read_is_temporarily_blocked(self):
        entered=threading.Event();release=threading.Event()
        def controlled(*args,**kwargs):
            entered.set();release.wait(timeout=4);return inspect_runtime(*args,**kwargs)
        self.addCleanup(release.set)
        with patch('ai_runtime_preferences.inspect_runtime',side_effect=controlled):
            self.start();self.assertTrue(entered.wait(timeout=3))
            self.assertFalse(self.jobs.close(timeout=.01))
            with self.assertRaises(SetupBusy):self.start()
            release.set();result=self.finish()
        self.assertTrue(self.jobs.close());self.assertEqual(result['state'],'cancelled')
        self.assertEqual(self.path.read_bytes(),self.before)

    def test_saved_but_diagnostic_error_is_not_reported_as_cancelled(self):
        with patch.object(self.preferences,'snapshot',side_effect=RuntimeError('generated failure')):
            self.start();result=self.finish()
        self.assertEqual(result['state'],'complete');self.assertTrue(result['saved'])
        self.assertEqual(result['error_code'],'diagnostics_failed')

    def test_settings_lease_conflict_preserves_existing_file(self):
        with storage_lease(self.path):self.start();result=self.finish()
        self.assertEqual(result['state'],'failed');self.assertEqual(result['error_code'],'settings_busy')
        self.assertEqual(self.path.read_bytes(),self.before)

    def test_validation_rejects_missing_consent_unknown_fields_and_relative_paths(self):
        for body in ({},{'runtime_root':str(self.pack),'consent':1},
                     {'runtime_root':'relative','consent':True},
                     {'models_root':[],'consent':True},
                     {'runtime_root':str(self.pack),'consent':True,'python':'unknown'}):
            with self.subTest(body=body),self.assertRaises(ValueError):self.jobs.start(body)
        self.assertIsNone(self.jobs.thread);self.assertEqual(self.path.read_bytes(),self.before)

    def test_worker_start_failure_is_visible_and_can_retry(self):
        with patch('ai_setup_jobs.threading.Thread.start',side_effect=RuntimeError('generated failure')):
            with self.assertRaises(SetupBusy):self.start()
        self.assertEqual(self.jobs.snapshot()['error_code'],'worker_start_failed')
        self.assertEqual(self.path.read_bytes(),self.before)
        self.start();self.assertEqual(self.finish()['state'],'complete')

    def test_unstarted_worker_can_be_closed_without_join_error(self):
        with patch('ai_setup_jobs.threading.Thread.start',side_effect=RuntimeError('generated failure')):
            with self.assertRaises(SetupBusy):self.start()
        self.assertTrue(self.jobs.close())
        with self.assertRaises(SetupBusy):self.start()

    def test_independent_models_choice_reset_and_late_cancel(self):
        models=self.base/'models';models.mkdir()
        first=self.jobs.start({'models_root':str(models),'consent':True});result=self.finish()
        self.assertTrue(result['saved']);self.assertEqual(result['files_done'],0)
        self.assertIsNone(result['bytes_total'])
        self.assertFalse(self.jobs.cancel(first['job_id'])['cancel_accepted'])
        self.jobs.start({'models_root':None,'runtime_root':None,'consent':True});result=self.finish()
        with self.assertRaises(KeyError):self.jobs.cancel(first['job_id'])
        self.assertEqual(json.loads(self.path.read_text()),{'ui_theme':'dark'})

    def test_progress_is_exact_and_callback_cancellation_retains_original(self):
        reports=[];before=(self.pack/MARKER).read_bytes()
        inspect_runtime(self.pack,verify=True,progress=reports.append)
        self.assertEqual(reports[-1]['files_done'],reports[-1]['files_total'])
        self.assertEqual(reports[-1]['bytes_done'],reports[-1]['bytes_total'])
        self.assertEqual([r['bytes_done'] for r in reports],sorted(r['bytes_done'] for r in reports))
        self.assertEqual((self.pack/MARKER).read_bytes(),before)


class SetupHttpTests(unittest.TestCase):
    setUp=SetupJobTests.setUp
    def test_async_api_stays_responsive_and_requires_full_session(self):
        from production import ProductionCatalog
        from production_server import production_handler,DisabledAI
        from ai_settings import AIProfileSettings
        catalog=ProductionCatalog(self.base/'catalog.sqlite')
        profiles=AIProfileSettings(self.base,self.base/'ai-settings.json',profile_directory=self.base/'profiles')
        handler=production_handler(catalog,'generated-token',DisabledAI(),profiles=profiles,runtime_preferences=self.path)
        server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        origin=f'http://127.0.0.1:{server.server_port}'
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        entered=threading.Event();release=threading.Event();self.addCleanup(release.set)
        def request(route,body=None,*,token=True,origin_header=True):
            headers={}
            if token:headers['X-Aredoko-Token']='generated-token'
            if origin_header:headers['Origin']=origin
            data=None if body is None else json.dumps(body).encode()
            if data is not None:headers['Content-Type']='application/json'
            with opener.open(urllib.request.Request(origin+route,data=data,headers=headers),timeout=2) as response:
                return response.status,json.load(response)
        def controlled(*args,**kwargs):
            entered.set();release.wait(timeout=5);return inspect_runtime(*args,**kwargs)
        select='/api/library/ai/setup/select';cancel='/api/library/ai/setup/cancel';job='/api/library/ai/setup/job'
        body={'runtime_root':str(self.pack),'consent':True}
        try:
            raw=urllib.request.Request(origin+select,data=b'{"consent":false,"consent":true,"runtime_root":null}',
                headers={'Origin':origin,'X-Aredoko-Token':'generated-token','Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as duplicate:opener.open(raw,timeout=2)
            self.assertEqual(duplicate.exception.code,400);duplicate.exception.close()
            self.assertEqual(request(job)[1]['state'],'idle')
            with self.assertRaises(urllib.error.HTTPError) as denied:request(job,token=False)
            self.assertEqual(denied.exception.code,403);denied.exception.close()
            for kwargs in ({'token':False},{'origin_header':False}):
                with self.assertRaises(urllib.error.HTTPError) as denied:request(select,body,**kwargs)
                self.assertEqual(denied.exception.code,403);denied.exception.close()
            with patch('ai_runtime_preferences.inspect_runtime',side_effect=controlled):
                status,first=request(select,body);self.assertEqual(status,202)
                self.assertTrue(entered.wait(timeout=3))
                self.assertEqual(request(job)[1]['job_id'],first['job_id'])
                self.assertEqual(request('/api/items')[1]['total'],0)
                with self.assertRaises(urllib.error.HTTPError) as busy:request(select,body)
                self.assertEqual(busy.exception.code,409);busy.exception.close()
                with self.assertRaises(urllib.error.HTTPError) as stale:request(cancel,{'job_id':'0'*32})
                self.assertEqual(stale.exception.code,409);stale.exception.close()
                self.assertTrue(request(cancel,{'job_id':first['job_id']})[1]['cancel_accepted'])
                release.set();handler.setup_jobs.thread.join(timeout=4)
            self.assertEqual(request(job)[1]['state'],'cancelled')
            self.assertEqual(self.path.read_bytes(),self.before)
            setup=request('/api/library/ai/setup')[1]
            self.assertTrue(setup['selection_api_supported']);self.assertFalse(setup['downloads_supported'])
        finally:
            release.set();server.shutdown();server.server_close();handler.setup_jobs.close();thread.join(timeout=3);catalog.close()


if __name__=='__main__':unittest.main()
