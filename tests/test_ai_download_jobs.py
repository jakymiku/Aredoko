"""Owned acquisition and authenticated endpoints; generated loopback payloads only."""
import sys,threading,unittest,json,urllib.request,urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_ai_acquisition as fixture
from ai_download_jobs import AIDownloadJobs,DownloadBusy
from production import ProductionCatalog
from production_server import production_handler,DisabledAI
from ai_settings import AIProfileSettings

class DownloadTests(unittest.TestCase):
    def setUp(self):
        fixture.AcquisitionTests.setUp(self)
        self.catalog=fixture.AcquisitionTests.catalog(self)
        self.validate=lambda root,cancel:self.assertEqual((root/'runtime/generated.bin').read_bytes(),self.content)
        self.jobs=AIDownloadJobs(self.base/'downloads',specifications=((self.catalog,self.validate),));self.addCleanup(self.jobs.close)
        self.body={'consent':True,'catalog_id':self.catalog.fingerprint,'bytes_per_second':None}
    def finish(self):
        self.jobs.thread.join(5);self.assertFalse(self.jobs.thread.is_alive());return self.jobs.snapshot()
    def test_trusted_summary_and_exact_completion(self):
        summary=self.jobs.catalogs()['catalogs'][0]
        self.assertEqual(summary['bytes'],len(self.content));self.assertEqual(summary['license'],'MIT');self.assertNotIn('url',summary)
        first=self.jobs.start(self.body);value=self.finish()
        self.assertEqual(value['state'],'complete');self.assertTrue(value['published'])
        self.assertEqual(value['bytes_verified'],len(self.content))
        self.assertFalse(self.jobs.cancel(first['job_id'])['cancel_accepted'])
        self.assertFalse((self.base/'launch-settings.json').exists())
    def test_cancel_before_publication_never_exposes_version(self):
        entered,release=threading.Event(),threading.Event();original=self.jobs._publish
        def waiting(operation):
            entered.set();release.wait(4);return original(operation)
        with patch.object(self.jobs,'_publish',side_effect=waiting):
            value=self.jobs.start(self.body)
            try:
                self.assertTrue(entered.wait(2))
                with self.assertRaises(DownloadBusy):self.jobs.start(self.body)
                with self.assertRaises(KeyError):self.jobs.cancel('0'*32)
                self.assertTrue(self.jobs.cancel(value['job_id'])['cancel_accepted'])
            finally:release.set();finished=self.finish()
        self.assertEqual(finished['state'],'cancelled');self.assertFalse(finished['published'])
    def test_request_cannot_supply_urls_roots_or_unknown_catalog(self):
        for body in ({**self.body,'url':'https://example.org/private'},{**self.body,'root':str(self.base/'other')},{**self.body,'catalog_id':'unknown'},{**self.body,'bytes_per_second':False},{**self.body,'consent':False}):
            with self.assertRaises(ValueError):self.jobs.start(body)
        self.assertIsNone(self.jobs.thread)
    def test_close_prevents_late_publication(self):
        entered,release=threading.Event(),threading.Event();original=self.jobs._publish
        def waiting(operation):entered.set();release.wait(3);return original(operation)
        with patch.object(self.jobs,'_publish',side_effect=waiting):
            self.jobs.start(self.body)
            try:
                self.assertTrue(entered.wait(2));self.assertFalse(self.jobs.close(timeout=.01))
            finally:release.set();finished=self.finish()
        self.assertEqual(finished['state'],'cancelled');self.assertFalse(finished['published'])
    def test_http_authentication_catalog_selection_and_completion(self):
        catalog=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(catalog.close)
        profiles=AIProfileSettings(self.base,self.base/'settings.json')
        handler=production_handler(catalog,'token',DisabledAI(),profiles=profiles,acquisition_specs=((self.catalog,self.validate),))
        for value in (handler.setup_jobs,handler.download_jobs,handler.restore_jobs,handler.backup_jobs,handler.thumbnails,handler.animations,handler.results):self.addCleanup(value.close)
        server=ThreadingHTTPServer(('127.0.0.1',0),handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(lambda:(server.shutdown(),server.server_close(),thread.join(3)))
        origin=f'http://127.0.0.1:{server.server_port}';opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def request(path,body=None,headers=None,raw=None):
            data=raw if raw is not None else None if body is None else json.dumps(body).encode()
            request=urllib.request.Request(origin+'/api/library/ai/setup/download/'+path,data=data,headers=headers if headers is not None else {'Origin':origin,'X-Aredoko-Token':'token','Content-Type':'application/json'})
            with opener.open(request,timeout=2) as response:return response.status,json.load(response)
        for path,body,headers,raw,code in [('catalog',None,{},None,403),('start',self.body,{'X-Aredoko-Token':'token'},None,403),('start',None,None,b'{"consent":false,"consent":true}',400)]:
            with self.assertRaises(urllib.error.HTTPError) as caught:request(path,body,headers,raw)
            self.assertEqual(caught.exception.code,code);caught.exception.close()
        self.assertEqual(request('catalog')[1]['catalogs'][0]['catalog_id'],self.catalog.fingerprint)
        status,_=request('start',self.body);self.assertEqual(status,202)
        handler.download_jobs.thread.join(4)
        self.assertEqual(request('job')[1]['state'],'complete')

if __name__=='__main__':unittest.main()
