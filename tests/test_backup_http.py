"""Authenticated owned live backup endpoints; generated local stores only."""
from http.server import ThreadingHTTPServer
from pathlib import Path
import json,sys,tempfile,threading,unittest,urllib.request,urllib.error
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from production import ProductionCatalog
from production_server import production_handler,DisabledAI
from ai_settings import AIProfileSettings
from storage_backup import restore

class BackupHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.catalog=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.catalog.close)
        self.settings=self.base/'ai-settings.json';self.settings.write_text('{"version":1,"profile":"default"}')
        profiles=AIProfileSettings(self.base,self.settings,profile_directory=self.base/'profiles')
        self.handler=production_handler(self.catalog,'generated-token',DisabledAI(),profiles=profiles)
        for value in (self.handler.setup_jobs,self.handler.animations,self.handler.results,self.handler.thumbnails,self.handler.backup_jobs):self.addCleanup(value.close)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),self.handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)
        self.origin=f'http://127.0.0.1:{self.server.server_port}'
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.body={'consent':True,'output':str(self.base/'bundle'),'selection':{'settings':True,'history':True,'reader_progress':True,'vectors':False}}
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
    def finish(self):
        self.handler.backup_jobs.thread.join(5);self.assertFalse(self.handler.backup_jobs.thread.is_alive())
        return self.request('/api/library/backup')[1]
    def test_real_bundle_captures_selected_settings_and_can_restore_without_stopping_app(self):
        viewer={'version':1,'wheel_up_advances':False,'theme':'dark','library_item_scale':80,'enlarge_small_images':True}
        status,first=self.request('/api/library/backup/start',{**self.body,'viewer_settings':viewer});self.assertEqual(status,202)
        value=self.finish();self.assertEqual(value['state'],'complete');self.assertTrue(value['published'])
        self.assertTrue(value['backup_supported']);self.assertFalse(value['restore_supported'])
        self.assertFalse(value['default_selection']['vectors'])
        self.assertEqual(json.loads((self.base/'bundle/settings/viewer-settings.json').read_text()),viewer)
        self.assertEqual((self.base/'bundle/settings/ai-settings.json').read_bytes(),self.settings.read_bytes())
        restore(self.base/'bundle',self.base/'restored');self.assertTrue((self.base/'restored/catalog.sqlite').is_file())
        self.assertEqual(self.request('/api/items')[1]['total'],0)
        self.assertFalse(self.request('/api/library/backup/cancel',{'job_id':first['job_id']})[1]['cancel_accepted'])
    def test_session_origin_duplicate_fields_and_invalid_payloads_do_not_start_work(self):
        self.denied(403,'/api/library/backup',token=False)
        self.denied(403,'/api/library/backup/start',self.body,token=False)
        self.denied(403,'/api/library/backup/start',self.body,origin=False)
        self.denied(400,'/api/library/backup/start',raw=b'{"consent":false,"consent":true}')
        self.denied(400,'/api/library/backup?unknown=1')
        for body in ({**self.body,'consent':False},{**self.body,'output':'relative'},
                     {**self.body,'viewer_settings':{'version':1,'wheel_up_advances':False,'path':'private'}},
                     {**self.body,'viewer_settings':{'version':1,'wheel_up_advances':False,'theme':'x'*3000}},
                     {**self.body,'selection':{**self.body['selection'],'settings':False},'viewer_settings':{}},
                     {**self.body,'viewer_settings':None},{**self.body,'settings_path':'private'}):
            self.denied(400,'/api/library/backup/start',body)
        self.assertEqual(self.request('/api/library/backup')[1]['state'],'idle');self.assertIsNone(self.handler.backup_jobs.thread)
    def test_status_search_and_cancel_remain_responsive_during_writer_pause(self):
        reached=threading.Event();release=threading.Event();original=self.handler.backup_jobs._progress
        self.addCleanup(release.set)
        def progress(value):
            original(value)
            if value['stage']=='capturing' and value['bytes_total'] is None:reached.set();release.wait(4)
        with patch.object(self.handler.backup_jobs,'_progress',side_effect=progress):
            _,first=self.request('/api/library/backup/start',self.body);self.assertTrue(reached.wait(2))
            self.assertTrue(self.catalog.writer_fence.paused)
            self.assertEqual(self.request('/api/items')[1]['total'],0)
            self.assertEqual(self.request('/api/library/backup')[1]['job_id'],first['job_id'])
            self.denied(409,'/api/library/backup/start',self.body)
            self.denied(409,'/api/library/backup/cancel',{'job_id':'0'*32})
            self.assertTrue(self.request('/api/library/backup/cancel',{'job_id':first['job_id']})[1]['cancel_accepted'])
            release.set();value=self.finish()
        self.assertEqual(value['state'],'cancelled');self.assertFalse(self.catalog.writer_fence.paused)
        self.assertFalse((self.base/'bundle').exists())
    def test_existing_destination_is_preserved_and_settings_can_be_omitted(self):
        destination=self.base/'bundle';destination.mkdir();(destination/'keep').write_bytes(b'keep')
        self.request('/api/library/backup/start',self.body);value=self.finish()
        self.assertEqual(value['state'],'failed');self.assertEqual((destination/'keep').read_bytes(),b'keep')
        self.request('/api/library/backup/start',{**self.body,'output':str(self.base/'without'),'selection':{**self.body['selection'],'settings':False}})
        self.assertEqual(self.finish()['state'],'complete');self.assertFalse((self.base/'without/settings').exists())
        manifest=json.loads((self.base/'without/manifest.json').read_text());self.assertIn('viewer_settings',manifest['not_included'])

if __name__=='__main__':unittest.main()
