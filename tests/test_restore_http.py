"""Authenticated owned live backup endpoints; generated local stores only."""
from http.server import ThreadingHTTPServer
from pathlib import Path
import json,sys,tempfile,threading,unittest,urllib.request,urllib.error
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from production import ProductionCatalog
from production_server import production_handler,DisabledAI
from ai_settings import AIProfileSettings
from storage_backup import backup

class RestoreHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.catalog=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.catalog.close)
        self.settings=self.base/'ai-settings.json';self.settings.write_text('{"version":1,"profile":"default"}')
        profiles=AIProfileSettings(self.base,self.settings,profile_directory=self.base/'profiles')
        self.handler=production_handler(self.catalog,'generated-token',DisabledAI(),profiles=profiles)
        for value in (self.handler.setup_jobs,self.handler.animations,self.handler.results,self.handler.thumbnails,self.handler.backup_jobs,self.handler.restore_jobs):self.addCleanup(value.close)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),self.handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)
        self.origin=f'http://127.0.0.1:{self.server.server_port}'
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.body={'consent':True,'source':str(self.base/'bundle'),'without_vectors':True}
    def stop(self):
        self.server.shutdown();self.server.server_close();self.thread.join(3)
    def request(self,route,body=None,*,token=True,origin=True,raw=None):
        headers={'X-Aredoko-Token':'generated-token'} if token else {}
        if origin:headers['Origin']=self.origin
        data=raw if raw is not None else None if body is None else json.dumps(body).encode()
        if data is not None:headers['Content-Type']='application/json'
        with self.opener.open(urllib.request.Request(self.origin+route,data=data,headers=headers),timeout=2) as response:return response.status,json.load(response)
    def denied(self,code,route,*args,**kwargs):
        with self.assertRaises(urllib.error.HTTPError) as result:self.request(route,*args,**kwargs)
        self.assertEqual(result.exception.code,code);result.exception.close()
    def test_authentication_and_strict_contract(self):
        self.denied(403,'/api/library/restore',token=False)
        self.denied(403,'/api/library/restore/start',self.body,token=False)
        self.denied(403,'/api/library/restore/start',self.body,origin=False)
        self.denied(400,'/api/library/restore/start',raw=b'{"consent":false,"consent":true}')
        for body in ({**self.body,'consent':False},{**self.body,'source':'relative'},{**self.body,'staging_path':str(self.base/'arbitrary')},{**self.body,'without_vectors':1}):
            self.denied(400,'/api/library/restore/start',body)
        self.assertEqual(self.request('/api/library/restore')[1]['state'],'idle')

    def test_directory_staging_keeps_current_library_and_rejects_second_ready_job(self):
        backup(self.catalog.path,self.base/'bundle')
        before=(self.base/'bundle/catalog.sqlite').read_bytes()
        status,first=self.request('/api/library/restore/start',self.body)
        self.assertEqual(status,202)
        owner=self.handler.restore_jobs
        owner.manager.wait(first['job_id'],5)
        value=self.request('/api/library/restore')[1]
        self.assertEqual(value['state'],'completed',value)
        self.assertFalse(value['switch_supported'])
        self.assertNotIn('staging_path',value)
        self.assertEqual((self.base/'bundle/catalog.sqlite').read_bytes(),before)
        self.assertEqual(self.request('/api/items')[1]['total'],0)
        self.denied(409,'/api/library/restore/start',self.body)
        self.denied(409,'/api/library/restore/cancel',{'job_id':'0'*32})
        self.assertFalse(self.request('/api/library/restore/cancel',{'job_id':first['job_id']})[1]['cancel_accepted'])
        staging=owner.current.staging_path
        self.denied(400,'/api/library/restore/discard',{'job_id':first['job_id'],'consent':False})
        self.assertTrue(staging.exists())
        self.assertEqual(self.request('/api/library/restore/discard',{'job_id':first['job_id'],'consent':True})[1]['state'],'idle')
        self.assertFalse(staging.exists())
        self.assertEqual((self.base/'bundle/catalog.sqlite').read_bytes(),before)
        _,second=self.request('/api/library/restore/start',self.body)
        owner.manager.wait(second['job_id'],5)
        self.assertEqual(self.request('/api/library/restore')[1]['state'],'completed')


    def test_cancel_is_responsive_and_prevents_completion(self):
        backup(self.catalog.path,self.base/'bundle')
        entered,release=threading.Event(),threading.Event()
        import restore_jobs
        original=restore_jobs.restore
        def blocked(*args,**kwargs):
            entered.set()
            if not release.wait(5):raise RuntimeError('Test wait expired')
            return original(*args,**kwargs)
        with patch('restore_jobs.restore',side_effect=blocked):
            _,first=self.request('/api/library/restore/start',self.body)
            try:
                self.assertTrue(entered.wait(3))
                self.denied(409,'/api/library/restore/discard',{'job_id':first['job_id'],'consent':True})
                self.assertTrue(self.request('/api/library/restore/cancel',{'job_id':first['job_id']})[1]['cancel_accepted'])
                self.assertEqual(self.request('/api/items')[1]['total'],0)
            finally:
                release.set()
                self.handler.restore_jobs.manager.wait(first['job_id'],5)
        self.assertEqual(self.request('/api/library/restore')[1]['state'],'cancelled')

if __name__=='__main__':unittest.main()
