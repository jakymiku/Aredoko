"""Generated-only multi-book lifecycle, exact scope and bounded requests."""
import copy
import json
import threading
import unittest
import urllib.request
import urllib.error
import zipfile
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from test_page_index import PageFixture
from test_page_semantics import Encoder
from ai_search import AISearch, AIBusy
from page_batch import start_batch, resume_batch
from production_server import production_handler
from previews import PreviewUnavailable, ReaderChanged


class PageBatchTests(PageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp();self.encoder=Encoder();self.ai=AISearch(self.catalog,self.encoder)
        self.addCleanup(lambda:self.ai.close())
        self.scope={'root_ids':[self.root,self.bookroot]};self.profile=self.ai.profile.key
        self.items=[self.request(self.ids[n]) for n in ('comic.cbz','comic/')]
    def request(self,item):
        self.pages.refresh(item);data=self.pages.list(item)
        return {'item_id':item,'revision':data['source_revision'],'page_ids':[p['page_id'] for p in data['pages']]}
    def start(self,items=None,limit=128):
        return start_batch(self.ai,self.items if items is None else items,self.scope,limit,self.profile)
    def finish(self,state='complete'):
        self.ai.worker.join(15);self.assertFalse(self.ai.worker.is_alive())
        result=self.ai.status();self.assertEqual(result['state'],state,result);return result
    def stored(self):
        with self.ai.store.connect() as db:return list(db.execute('SELECT item_id,page_id,vector FROM ai_page_vectors ORDER BY item_id,page'))
    def test_two_books_commit_and_reuse_preserve_manual_data_and_originals(self):
        before={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in (self.archive,*self.folder.iterdir())}
        self.catalog.update([self.items[0]['item_id']],{'tags':['manual'],'shelf':'keep','favorite':True})
        self.start();r=self.finish();self.assertEqual((r['indexed'],r['books_completed'],len(self.encoder.calls)),(4,2,4))
        self.start();r=self.finish();self.assertEqual((r['reused'],len(self.encoder.calls)),(4,4))
        self.assertEqual(before,{p:(p.read_bytes(),p.stat().st_mtime_ns) for p in before})
        self.assertEqual(self.catalog.get(self.items[0]['item_id'])['tags'],['manual'])
    def test_cancel_keeps_completed_book_and_same_ranges_resume_after_restart(self):
        self.encoder.hook=lambda *args:self.ai.cancel.set() if len(self.encoder.calls)==3 else None
        self.start();r=self.finish('cancelled');self.assertEqual(r['indexed'],2);self.assertEqual(len(self.stored()),2)
        job=r['job_id'];self.ai.close();self.encoder=Encoder();self.ai=AISearch(self.catalog,self.encoder)
        resume_batch(self.ai,job,self.scope,self.profile);r=self.finish()
        self.assertEqual((r['reused'],r['resumed_from'],len(self.encoder.calls)),(2,job,2))
    def test_partial_failure_continues_other_books_and_reuses_them_on_retry(self):
        original=self.ai.pages.index.input
        def read(item,*args):
            if item==self.items[0]['item_id']:raise PreviewUnavailable('fixture')
            return original(item,*args)
        with patch.object(self.ai.pages.index,'input',side_effect=read):
            self.start();r=self.finish('partial')
        self.assertEqual((r['books_failed'],r['books_completed'],r['indexed']),(1,1,2))
        self.assertEqual([i['state'] for i in r['books']],['failed','complete'])
        resume_batch(self.ai,r['job_id'],self.scope,self.profile);r=self.finish();self.assertEqual(r['reused'],2)
    def test_exclusion_between_books_does_not_broaden_scope_or_remove_completed(self):
        self.encoder.hook=lambda *args:self.catalog.set_excludes(self.bookroot,['comic']) if len(self.encoder.calls)==2 else None
        self.start();r=self.finish('partial');self.assertEqual(r['indexed'],2);self.assertEqual(len(self.stored()),2)
        self.encoder.hook=None
        with self.assertRaises(KeyError):resume_batch(self.ai,r['job_id'],self.scope,self.profile)
    def test_source_change_mid_range_does_not_publish_partial_book(self):
        self.encoder.hook=lambda *args:(self.folder/'1.png').write_bytes(self.second) if len(self.encoder.calls)==3 else None
        self.start();r=self.finish('partial');self.assertEqual(r['indexed'],2);self.assertEqual(len(self.stored()),2)
        with self.assertRaises(ReaderChanged):resume_batch(self.ai,r['job_id'],self.scope,self.profile)
    def test_limits_and_malformed_requests_never_start_inference(self):
        bad=[[],self.items*5,[self.items[0]]*2,[dict(self.items[0],path='x')],
            [dict(self.items[0],page_ids=[[]])],[dict(self.items[0],page_ids=['x'])],
            [dict(self.items[0],item_id=True)],[dict(self.items[0],page_ids=self.items[0]['page_ids']*2)]]
        for items in bad:
            with self.subTest(items=items),self.assertRaises((ValueError,KeyError)):self.start(items=items)
        for limit in (0,129,True,3):
            with self.subTest(limit=limit),self.assertRaises(ValueError):self.start(limit=limit)
        self.assertEqual(self.encoder.calls,[])
    def test_profile_scope_job_identity_and_complete_resume_rejected(self):
        with self.assertRaises(ValueError):start_batch(self.ai,self.items,self.scope,128,'other')
        with self.assertRaises(ValueError):start_batch(self.ai,self.items,None,128,self.profile)
        with self.assertRaises(KeyError):start_batch(self.ai,self.items,{'root_ids':[self.root]},128,self.profile)
        self.encoder.hook=lambda *args:self.ai.cancel.set();self.start();r=self.finish('cancelled');self.encoder.hook=None
        with self.assertRaises(ValueError):resume_batch(self.ai,r['job_id'],{'root_ids':[self.root]},self.profile)
        with self.assertRaises(KeyError):resume_batch(self.ai,'a'*32,self.scope,self.profile)
        resume_batch(self.ai,r['job_id'],self.scope,self.profile);r=self.finish()
        with self.assertRaises(ValueError):resume_batch(self.ai,r['job_id'],self.scope,self.profile)
    def test_shared_worker_and_caller_mutation(self):
        items=copy.deepcopy(self.items)
        self.ai.inference.acquire()
        try:
            self.start(items);items[0]['page_ids'].clear()
            with self.assertRaises(AIBusy):self.start()
        finally:self.ai.inference.release()
        r=self.finish();self.assertEqual(r['total'],4);self.assertEqual(len(r['selections'][0]['page_ids']),2)
    def test_eight_book_128_page_ceiling(self):
        for n in range(8):
            with zipfile.ZipFile(self.loose/f'book{n}.cbz','w') as archive:
                for p in range(16):archive.writestr(f'{p:02}.png',self.first)
        self.scan();items=[self.request(self.ids[f'book{n}.cbz']) for n in range(8)]
        self.start(items);r=self.finish();self.assertEqual((r['indexed'],r['books_completed']),(128,8))
    def test_http_strict_auth_cancel_ownership_and_resume(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'secret',ai=self.ai))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def stop():server.shutdown();thread.join(5);server.server_close()
        self.addCleanup(stop)
        def post(route,body,auth='secret'):
            req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/library/ai/pages/'+route,
                data=json.dumps(body).encode(),headers={'X-Aredoko-Token':auth,'Origin':f'http://127.0.0.1:{server.server_port}','Content-Type':'application/json'})
            try:
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=5) as response:return response.status,json.load(response)
            except urllib.error.HTTPError as ex:
                with ex:return ex.code,json.load(ex)
        body={'items':self.items,'scope':self.scope,'profile':self.profile,'page_limit':128}
        self.assertEqual(post('batch',body,'wrong')[0],403)
        for bad in (dict(body,extra=1),{k:v for k,v in body.items() if k!='scope'},dict(body,page_limit=True),dict(body,items=[])):
            self.assertEqual(post('batch',bad)[0],400)
        self.ai.inference.acquire()
        try:
            code,r=post('batch',body);self.assertEqual(code,200)
            self.assertEqual(post('cancel',{'job_id':'a'*32})[1]['cancel_requested'],False)
            self.assertTrue(post('cancel',{'job_id':r['job_id']})[1]['cancel_requested'])
        finally:self.ai.inference.release()
        r=self.finish('cancelled')
        code,_=post('batch/resume',{'job_id':r['job_id'],'scope':self.scope,'profile':self.profile});self.assertEqual(code,200)
        self.finish()

if __name__=='__main__':unittest.main()
