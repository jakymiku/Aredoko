"""CPU-only handoff tests; generated bundles and simulated owned exit handles."""
import json
from pathlib import Path
import sys,tempfile,unittest
import socket,subprocess,time,urllib.request,os
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from production import ProductionCatalog
from storage_backup import backup
from restore_jobs import RestoreStagingJobs
from restore_handoff import RestoreHandoff
from storage_lease import storage_lease,StorageBusyError
from launch_release import launch

class Exited:
    def __init__(self,code=0):self.code=code
    def poll(self):return self.code

class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.data=self.base/'user';self.data.mkdir()
        self.catalog=self.data/'catalog.sqlite'
        catalog=ProductionCatalog(self.catalog);catalog.close()
        backup(self.catalog,self.base/'bundle',include_vectors=False)
        session=self.data/'logs';session.mkdir()
        self.handoff=RestoreHandoff(session,'a'*32,self.catalog)
        self.jobs=RestoreStagingJobs(self.data/'restore-staging',handoff=self.handoff)
        self.addCleanup(self.jobs.close)
        value=self.jobs.start({'consent':True,'source':str(self.base/'bundle'),'without_vectors':True})
        self.jobs.manager.wait(value['job_id'])
        self.body={'consent':True,'job_id':value['job_id']}
        self.jobs.request_restart(self.body)

    def test_normal_closed_children_switch_without_mutating_old_catalog(self):
        before=self.catalog.read_bytes()
        self.handoff.mark_closed()
        value=self.handoff.finish(self.data,Exited(),Exited())
        self.assertTrue(value['restart'])
        self.assertEqual(self.catalog.read_bytes(),before)
        settings=json.loads((self.data/'launch-settings.json').read_text())
        self.assertIn('restores',settings['database'])

    def test_live_or_failed_children_cannot_switch(self):
        self.handoff.mark_closed()
        for code in (None,1,-1):
            with self.subTest(code=code),self.assertRaises(RuntimeError):
                self.handoff.finish(self.data,Exited(code),Exited())
        self.assertFalse((self.data/'launch-settings.json').exists())

    def test_missing_closure_proof_cannot_switch(self):
        with self.assertRaises(ValueError):
            self.handoff.finish(self.data,Exited(),Exited())
        self.assertFalse((self.data/'launch-settings.json').exists())

    def test_old_catalog_kernel_lease_must_be_released(self):
        self.handoff.mark_closed()
        with storage_lease(self.catalog),self.assertRaises(StorageBusyError):
            self.handoff.finish(self.data,Exited(),Exited())
        self.assertFalse((self.data/'launch-settings.json').exists())

    def test_restart_request_prevents_discard_and_duplicate_request(self):
        from restore_jobs import RestoreBusy
        with self.assertRaises(RestoreBusy):self.jobs.discard(self.body)
        with self.assertRaises(RestoreBusy):self.jobs.request_restart(self.body)
        self.assertTrue(self.jobs.snapshot()['restart_requested'])

    def test_real_backend_publishes_closure_after_owned_pipe_shutdown(self):
        session=self.data/'real-session';session.mkdir()
        handoff=RestoreHandoff(session,'c'*32,self.catalog)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        origin=f'http://127.0.0.1:{port}'
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        root=Path(__file__).resolve().parents[1]
        env=dict(os.environ,LOCALAPPDATA=str(self.base/'isolated-local'))
        command=[sys.executable,'-B',str(root/'app/production_server.py'),'--db',str(self.catalog),'--port',str(port),'--instance-id','c'*32,'--exit-on-stdin-close','--restore-session-dir',str(session),'--ai-python',str(self.base/'missing-python'),'--models-root',str(self.base/'missing-models'),'--ai-settings',str(self.base/'isolated-settings.json')]
        with (session/'backend.log').open('wb') as log:
            child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=log,stderr=log,env=env)
            try:
                deadline=time.monotonic()+8
                while True:
                    try:
                        with opener.open(origin+'/api/session',timeout=.5) as response:token=json.load(response)['token']
                        break
                    except OSError:
                        if child.poll() is not None or time.monotonic()>deadline:self.fail('Generated backend did not start')
                        time.sleep(.05)
                def request(path,body=None):
                    data=None if body is None else json.dumps(body).encode()
                    req=urllib.request.Request(origin+path,data=data,headers={'X-Aredoko-Token':token,'Origin':origin,'Content-Type':'application/json'})
                    with opener.open(req,timeout=2) as response:return json.load(response)
                value=request('/api/library/restore/start',{'consent':True,'source':str(self.base/'bundle'),'without_vectors':True})
                deadline=time.monotonic()+5
                while value['state'] in ('queued','running'):
                    if time.monotonic()>deadline:self.fail('Restore preparation timed out')
                    time.sleep(.05);value=request('/api/library/restore')
                self.assertEqual(value['state'],'completed',value)
                request('/api/library/restore/restart',{'consent':True,'job_id':value['job_id']})
                self.assertFalse(handoff.closed.exists())
            finally:
                child.stdin.close();child.wait(timeout=15)
        self.assertEqual(child.returncode,0,(session/'backend.log').read_text(errors='replace'))
        self.assertTrue(handoff.closed.exists())
        self.assertTrue(handoff.finish(self.data,child,Exited())['restart'])

    def test_launcher_reuses_owner_loop_and_initial_bootstrap_only_once(self):
        root=self.base/'release';root.mkdir()
        pipe=object()
        with patch('launch_release._launch_once',side_effect=[{'restart':True},None]) as run:
            launch(root,self.data,{},startup_pipe=pipe)
        self.assertEqual(run.call_count,2)
        self.assertIs(run.call_args_list[0].kwargs['startup_pipe'],pipe)
        self.assertIsNone(run.call_args_list[1].kwargs['startup_pipe'])

if __name__=='__main__':unittest.main()
