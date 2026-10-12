"""CPU-only lifecycle/API contract. Never opens private media or CUDA."""
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from ai_search import AISearch, AIBusy
from ai_process import AIUnavailable, EncoderProcess
from production import ProductionCatalog
from production_server import production_handler

class FakeEncoder:
    available=True
    device="CPU-test"
    telemetry={"elapsed_ms":1}
    def __init__(self):
        self.resident=False
        self.closed=False
        self.loads=0
        self.releases=0
        self.documents=0
        self.enter=threading.Event()
        self.resume=threading.Event()
        self.block=False
        self.lock=threading.Lock()
    def encode(self, operation, text):
        with self.lock:
            if self.closed: raise AIUnavailable("closed")
            if not self.resident:
                self.resident=True
                self.loads+=1
            if self.block:
                self.enter.set()
                if not self.resume.wait(5):
                    raise TimeoutError("fake encoder gate timed out")
            if operation=="document":self.documents+=1
            return [1.0]+[0.0]*767
    def release(self):
        if not self.lock.acquire(False):raise AIUnavailable("busy")
        try:
            if self.closed:raise AIUnavailable("closed")
            previous=self.resident
            self.resident=False
            self.device=""
            self.telemetry={}
            self.releases+=1
            return {"released":previous,"resident":False}
        finally:self.lock.release()
    def close(self):
        with self.lock:self.closed=True;self.resident=False;self.device="";self.telemetry={}

class FakeProcess:
    def __init__(self):
        self.dead=False
        self.stdin=io.StringIO()
        self.stdout=io.StringIO()
    def poll(self):return 0 if self.dead else None
    def kill(self):self.dead=True
    def wait(self,timeout=None):return 0

class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        media=root/"media";media.mkdir()
        (media/"rain.wav").write_bytes(b"generated")
        self.catalog=ProductionCatalog(root/"catalog.sqlite")
        self.addCleanup(self.catalog.close)
        folder=self.catalog.add_root(str(media))
        self.catalog.start_scan(folder)
        self.catalog._worker.join(10)
        self.encoder=FakeEncoder()
        self.ai=AISearch(self.catalog,self.encoder)
        self.addCleanup(self.ai.close)
    def build(self):
        self.ai.start()
        self.ai.worker.join(10)
        self.assertEqual(self.ai.status()["state"],"complete")
    def test_release_reload_and_vectors_unchanged(self):
        self.build()
        self.ai.search("雨")
        with self.ai.store.connect() as db:
            before=db.execute("SELECT item_id,revision,modality,vector FROM ai_vectors ORDER BY item_id,modality").fetchall()
        self.assertTrue(self.ai.status()["resident"])
        self.assertTrue(self.ai.release()["released"])
        self.assertFalse(self.ai.status()["resident"])
        self.assertEqual(self.ai.status()["device"],"")
        self.assertEqual(self.ai.status()["telemetry"],{})
        self.assertFalse(self.ai.release()["released"])
        with self.ai.store.connect() as db:
            self.assertEqual(before,db.execute("SELECT item_id,revision,modality,vector FROM ai_vectors ORDER BY item_id,modality").fetchall())
        old_documents=self.encoder.documents
        self.ai.search("雨")
        self.assertEqual(self.encoder.loads,2)
        self.build()
        self.assertEqual(self.encoder.documents,old_documents)
        with self.ai.store.connect() as db:
            self.assertEqual(before,db.execute("SELECT item_id,revision,modality,vector FROM ai_vectors ORDER BY item_id,modality").fetchall())
    def test_busy_search_and_build_returns_promptly(self):
        self.build()
        self.encoder.block=True
        def query():self.ai.search("雨")
        thread=threading.Thread(target=query)
        thread.start()
        self.assertTrue(self.encoder.enter.wait(3))
        start=time.monotonic()
        with self.assertRaises(AIBusy):self.ai.release()
        self.assertLess(time.monotonic()-start,0.5)
        self.encoder.resume.set()
        thread.join(10);self.assertFalse(thread.is_alive())
        self.encoder.block=True
        self.encoder.enter.clear();self.encoder.resume.clear()
        # Force a fresh document to test the indexing guard.
        item=self.catalog.search()["items"][0]
        self.catalog.update([item["id"]],{"tags":["changed"]})
        self.ai.start()
        self.assertTrue(self.encoder.enter.wait(3))
        # A live index thread is busy even in the pre-inference scheduling gap.
        start=time.monotonic()
        with self.assertRaises(AIBusy):self.ai.release()
        self.assertLess(time.monotonic()-start,0.5)
        self.encoder.resume.set()
        self.ai.worker.join(10)
        self.assertEqual(self.ai.status()["state"],"complete")
    def test_close_never_relaunches_worker(self):
        self.build()
        self.encoder.block=True
        query_done=threading.Event()
        def query():
            try:self.ai.search("雨")
            finally:query_done.set()
        t=threading.Thread(target=query);t.start()
        self.assertTrue(self.encoder.enter.wait(3))
        ending=threading.Thread(target=self.ai.close);ending.start()
        for _ in range(100):
            if self.ai._closed: break
            time.sleep(0.01)
        self.assertTrue(self.ai._closed)
        self.encoder.resume.set()
        ending.join(10);t.join(10)
        self.assertFalse(ending.is_alive())
        self.assertTrue(query_done.is_set())
        old_loads=self.encoder.loads
        with self.assertRaises(AIUnavailable):self.ai.search("雨")
        with self.assertRaises(AIUnavailable):self.ai.start()
        with self.assertRaises(AIUnavailable):self.ai.release()
        self.assertEqual(self.encoder.loads,old_loads)
        self.assertFalse(self.encoder.resident)
    def test_authenticated_release_http_and_busy(self):
        self.build()
        server=ThreadingHTTPServer(("127.0.0.1",0),production_handler(self.catalog,"token",self.ai))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        root=f"http://127.0.0.1:{server.server_port}"
        def post(body={},token="token",origin=True):
            headers={"X-Aredoko-Token":token,"Content-Type":"application/json"}
            if origin:headers["Origin"]=root
            data=json.dumps(body).encode()
            return urllib.request.urlopen(urllib.request.Request(root+"/api/library/ai/release",data,headers))
        for body,token,origin,code in [
            ({}, "wrong", True, 403), ({}, "token", False,403),
            ({"force":True},"token",True,400)]:
            with self.assertRaises(urllib.error.HTTPError) as err:post(body,token,origin)
            self.assertEqual(err.exception.code,code);err.exception.close()
        self.encoder.block=True
        work=threading.Thread(target=lambda:self.ai.search("雨"));work.start()
        self.assertTrue(self.encoder.enter.wait(3))
        start=time.monotonic()
        with self.assertRaises(urllib.error.HTTPError) as err:post()
        self.assertEqual(err.exception.code,409);err.exception.close()
        self.assertLess(time.monotonic()-start,1.0)
        self.encoder.resume.set();work.join(10)
        with post() as response:self.assertTrue(json.load(response)["released"])
        request=urllib.request.Request(root+"/api/library/ai/status",headers={"X-Aredoko-Token":"token"})
        with urllib.request.urlopen(request) as response:
            data=json.load(response)
            self.assertFalse(data["resident"])
            self.assertEqual(data["device"],"")
        with urllib.request.urlopen(root+"/api/items?q=rain") as response:
            self.assertEqual(json.load(response)["total"],1)
    def test_encoderprocess_owned_stop_and_close(self):
        from ai_profiles import DEFAULT_PROFILE
        proc=EncoderProcess("fake-python","fake-model",DEFAULT_PROFILE)
        workers=[]
        def spawn(*args,**kw):
            worker=FakeProcess()
            workers.append(worker)
            return worker
        def respond(*args,**kw):
            if not proc.device:
                return {"profile":DEFAULT_PROFILE.key,"dimension":768,"device":"CPU-test"}
            return {"vector":[1.0]+[0.0]*767,"elapsed_ms":5}
        with patch.object(EncoderProcess,"available",property(lambda self:True)), \
             patch("ai_process.subprocess.Popen",side_effect=spawn), \
             patch("ai_process.threading.Thread") as no_reader, \
             patch.object(proc,"_response",side_effect=respond):
            proc.encode("query","hello")
            self.assertEqual(len(workers),1)
            self.assertEqual(proc.device,"CPU-test")
            self.assertTrue(proc.release()["released"])
            self.assertTrue(workers[0].dead)
            self.assertEqual(proc.telemetry,{})
            self.assertEqual(proc.device,"")
            proc.encode("query","again")
            self.assertEqual(len(workers),2)
            proc.close()
            self.assertTrue(workers[1].dead)
            with self.assertRaises(AIUnavailable):proc.encode("query","no")
            self.assertEqual(len(workers),2)

if __name__=="__main__":unittest.main()
