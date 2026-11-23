"""R02-C generated-only lifecycle/HTTP tests; no real encoder or native GUI."""
from array import array
from dataclasses import replace
import concurrent.futures
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import urllib.request
import urllib.error

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'));sys.path.insert(0,str(ROOT/'tools'))
from search_requests import SearchRequests,SearchRequestConflict
from ai_search import AISearch,revision
from ai_score_spool import SearchCancelled,ScoreSpool
from production_server import production_handler,DisabledAI
from audit_large_library_boundary import seed,QueryOnlyEncoder

class ReservationTests(unittest.TestCase):
    def test_one_use_capacity_expiry_and_close(self):
        clock=[0];requests=SearchRequests(capacity=1,ttl=60,clock=lambda:clock[0])
        first=requests.prepare()['request_id']
        with self.assertRaises(SearchRequestConflict):requests.prepare()
        clock[0]=61;second=requests.prepare()['request_id'];self.assertNotEqual(first,second)
        with self.assertRaises(SearchRequestConflict):
            with requests.claim(first):pass
        with requests.claim(second) as cancelled:
            clock[0]=999
            with self.assertRaises(SearchRequestConflict):requests.prepare() # running never expires
            with self.assertRaises(SearchRequestConflict):
                with requests.claim(second):pass
            self.assertFalse(cancelled());self.assertTrue(requests.cancel(second)['cancel_requested']);self.assertTrue(cancelled())
        self.assertFalse(requests.cancel(second)['cancel_requested'])
        third=requests.prepare()['request_id'];requests.close()
        self.assertFalse(requests.cancel(third)['cancel_requested'])
        with self.assertRaises(SearchRequestConflict):requests.prepare()

    def test_cancel_before_start_and_invalid_ids_never_cancel_another(self):
        requests=SearchRequests();first=requests.prepare()['request_id'];second=requests.prepare()['request_id']
        for bad in (None,True,[],{},'', 'A'*32,'0'*31,'0'*33):
            with self.subTest(bad=bad),self.assertRaises(ValueError):requests.cancel(bad)
        self.assertTrue(requests.cancel(first)['cancel_requested'])
        with self.assertRaises(SearchRequestConflict):
            with requests.claim(first):pass
        with requests.claim(second) as cancelled:
            self.assertFalse(requests.cancel(first)['cancel_requested']);self.assertFalse(cancelled())
            requests.close();self.assertTrue(cancelled())

class SearchCancellationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.catalog,self.roots,_,_,self.paths=seed(Path(self.tmp.name)/'fixture',257,10000)
        self.addCleanup(self.catalog.close)
        self.encoder=QueryOnlyEncoder();self.ai=AISearch(self.catalog,self.encoder);self.addCleanup(self.ai.close)
        self.rows=self.ai._current_rows(list(range(1,257)))
        tail=self.ai._current_rows([257]);self.rows.update(tail)
        with self.ai.store.connect() as db:
            db.executemany('INSERT INTO ai_vectors VALUES(?,?,?,?)',[(item,revision(row),mode,array('f',[1.,0.,0.]).tobytes()) for item,row in self.rows.items() for mode in ('text','cover')])
        self.source_before={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.paths}
        self.server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'cancel-test',ai=self.ai))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.thread.join,5);self.addCleanup(self.server.shutdown)
        self.origin=f'http://127.0.0.1:{self.server.server_port}'
        self.headers={'Origin':self.origin,'X-Aredoko-Token':'cancel-test','Content-Type':'application/json'}

    def post(self,route,body,headers=None):
        req=urllib.request.Request(self.origin+'/api/library/'+route,data=json.dumps(body).encode(),headers=self.headers if headers is None else headers)
        try:
            with urllib.request.urlopen(req,timeout=8) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as ex:
            with ex:return ex.code,json.load(ex)

    def prepare(self):
        status,result=self.post('ai/searches/prepare',{});self.assertEqual(status,200);return result['request_id']

    def assert_released(self,paths):
        self.assertTrue(all(not p.exists() for p in paths))
        self.assertTrue(self.ai.inference.acquire(blocking=False));self.ai.inference.release()
        self.assertFalse(self.ai.cancel.is_set()) # index-job cancellation is separate
        self.assertEqual(self.source_before,{p:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.paths})

    def test_auth_validation_prestart_echo_and_old_id(self):
        for route,body in (('ai/searches/prepare',{}),('ai/searches/cancel',{'request_id':'0'*32})):
            for headers in ({},{**self.headers,'Origin':'http://evil.invalid'},{**self.headers,'X-Aredoko-Token':'bad'},{**self.headers,'Host':'evil.invalid'}):
                self.assertEqual(self.post(route,body,headers)[0],403)
        request_id=self.prepare()
        for body in ({},{'request_id':None},{'request_id':True},{'request_id':'A'*32},{'request_id':request_id,'all':True}):
            self.assertEqual(self.post('ai/searches/cancel',body)[0],400)
        for route,body in (('ai/search',{'query':'boundary','source':'text'}),('ai/similar',{'item_id':1})):
            current=self.prepare();status,result=self.post(route,{**body,'request_id':current})
            self.assertEqual(status,200);self.assertEqual(result['request_id'],current)
            self.assertFalse(self.post('ai/searches/cancel',{'request_id':current})[1]['cancel_requested'])
            self.assertEqual(self.post(route,{**body,'request_id':current})[0],409)
        self.assertTrue(self.post('ai/searches/cancel',{'request_id':request_id})[1]['cancel_requested'])
        before=len(self.encoder.calls)
        self.assertEqual(self.post('ai/search',{'query':'boundary','request_id':request_id})[0],409)
        self.assertEqual(len(self.encoder.calls),before)
        self.assertEqual(self.post('ai/search',{'query':'boundary','request_id':None})[0],400)
        self.assertEqual(self.post('ai/searches/prepare',{'request_id':'0'*32})[0],400)

    def test_cancel_running_search_and_similarity_cleanup_then_next_query(self):
        for route,body in (('ai/search',{'query':'boundary','source':'text'}),('ai/similar',{'item_id':1})):
            request_id=self.prepare();wrong=self.prepare();entered=threading.Event();resume=threading.Event();paths=[]
            scored=self.ai.store.scores_with_content;init=ScoreSpool.__init__
            def started(spool,*args,**kwargs):init(spool,*args,**kwargs);paths.append(spool.path.parent)
            def score(*args,**kwargs):
                result=scored(*args,**kwargs);entered.set()
                if not resume.wait(5):raise AssertionError('test resume timeout')
                return result
            with patch.object(self.ai.store,'scores_with_content',side_effect=score),patch.object(ScoreSpool,'__init__',started),concurrent.futures.ThreadPoolExecutor(1) as pool:
                future=pool.submit(self.post,route,{**body,'request_id':request_id})
                try:
                    self.assertTrue(entered.wait(5));start=time.monotonic()
                    self.assertTrue(self.post('ai/searches/cancel',{'request_id':wrong})[1]['cancel_requested'])
                    self.assertFalse(future.done())
                    self.assertTrue(self.post('ai/searches/cancel',{'request_id':request_id})[1]['cancel_requested'])
                    self.assertLess(time.monotonic()-start,2) # test bound, not R12 p95
                finally:resume.set()
                status,result=future.result(timeout=5)
            self.assertEqual((status,result.get('error_code')),(409,'search_cancelled'))
            self.assert_released(paths)
            self.assertEqual(self.post(route,body)[0],200) # legacy still works

    def test_disconnect_stops_before_next_batch_and_cleans_workspace(self):
        entered=threading.Event();resume=threading.Event();finished=threading.Event();paths=[];batches=[]
        scored=self.ai.store.scores_with_content;init=ScoreSpool.__init__;search=self.ai.search
        def started(spool,*args,**kwargs):init(spool,*args,**kwargs);paths.append(spool.path.parent)
        def score(rows,*args,**kwargs):
            batches.append(len(rows));result=scored(rows,*args,**kwargs);entered.set()
            if not resume.wait(5):raise AssertionError('resume timeout')
            return result
        def searched(*args,**kwargs):
            try:return search(*args,**kwargs)
            finally:finished.set()
        body=json.dumps({'query':'boundary','source':'text'}).encode()
        with patch.object(ScoreSpool,'__init__',started),patch.object(self.ai.store,'scores_with_content',side_effect=score),patch.object(self.ai,'search',side_effect=searched):
            connection=socket.create_connection(('127.0.0.1',self.server.server_port),timeout=5)
            try:
                connection.sendall((f'POST /api/library/ai/search HTTP/1.1\r\nHost: 127.0.0.1:{self.server.server_port}\r\nOrigin: {self.origin}\r\nX-Aredoko-Token: cancel-test\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n').encode()+body)
                self.assertTrue(entered.wait(5))
            finally:connection.shutdown(socket.SHUT_RDWR);connection.close();resume.set()
            self.assertTrue(finished.wait(5))
        self.assertEqual(batches,[256]);self.assert_released(paths)

    def test_query_and_sqlite_phase_cancel_never_return_partial_results(self):
        stop=threading.Event();encode=self.encoder.encode
        def encoded(*args,**kwargs):result=encode(*args,**kwargs);stop.set();return result
        with patch.object(self.encoder,'encode',side_effect=encoded),self.assertRaises(SearchCancelled):
            self.ai.search('boundary',source='text',cancelled=stop.is_set)
        stop.clear();finalize=ScoreSpool.finalize
        def finalized(spool,*args,**kwargs):stop.set();return finalize(spool,*args,**kwargs)
        with patch.object(ScoreSpool,'finalize',finalized),self.assertRaises(SearchCancelled):
            self.ai.search('boundary',source='text',cancelled=stop.is_set)
        self.assert_released([])

    def test_close_waits_for_inflight_encode_then_discards_and_cleans(self):
        entered=threading.Event();resume=threading.Event();paths=[]
        encode=self.encoder.encode;init=ScoreSpool.__init__
        def encoded(*args,**kwargs):
            entered.set()
            if not resume.wait(5):raise AssertionError('encoder release timeout')
            return encode(*args,**kwargs)
        def started(spool,*args,**kwargs):init(spool,*args,**kwargs);paths.append(spool.path.parent)
        request_id=self.prepare()
        with patch.object(self.encoder,'encode',side_effect=encoded),patch.object(ScoreSpool,'__init__',started),concurrent.futures.ThreadPoolExecutor(2) as pool:
            query=pool.submit(self.post,'ai/search',{'query':'boundary','request_id':request_id})
            try:
                self.assertTrue(entered.wait(5));closing=pool.submit(self.ai.close)
                deadline=time.monotonic()+3
                while not self.ai._closed and time.monotonic()<deadline:time.sleep(.005)
                self.assertTrue(self.ai._closed);self.assertFalse(closing.done())
            finally:resume.set()
            self.assertIn(query.result(timeout=5)[0],(409,503));closing.result(timeout=5)
        self.assertTrue(all(not p.exists() for p in paths))
        self.assertTrue(self.ai.inference.acquire(blocking=False));self.ai.inference.release()
        self.assertEqual(self.source_before,{p:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.paths})

    def test_close_signals_active_capability_and_rejects_new_searches(self):
        request_id=self.prepare()
        with self.ai.search_requests.claim(request_id) as cancelled:
            self.ai.close();self.assertTrue(cancelled())
        self.assertEqual(self.post('ai/searches/prepare',{})[0],409)

if __name__=='__main__':unittest.main()
