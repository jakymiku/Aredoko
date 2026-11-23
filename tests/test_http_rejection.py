"""Rejected uploads remain unauthorized and cannot hold a worker indefinitely."""
import http.client,json,sys,tempfile,threading,unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from production import ProductionCatalog
from production_server import production_handler,DisabledAI

class RejectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.catalog=ProductionCatalog(Path(self.tmp.name)/'catalog.sqlite');self.addCleanup(self.catalog.close)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'test-token',ai=DisabledAI()))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)
    def stop(self):
        self.server.shutdown();self.thread.join(3);self.server.server_close()
    def client(self):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        self.addCleanup(conn.close);return conn
    def test_large_bad_origin_upload_returns_403_without_dictionary_changes(self):
        conn=self.client();body=json.dumps({'format':'aredoko-related-terms','version':1,'entries':[{'term':'x','related':['a'*50]}]*1500}).encode()
        conn.request('POST','/api/library/terms/import',body,{'Origin':'http://invalid.test','X-Aredoko-Token':'test-token','Content-Type':'application/json'})
        response=conn.getresponse();self.assertEqual(response.status,403);self.assertEqual(json.loads(response.read())['error'],'Invalid session')
        self.assertEqual(self.catalog.terms.entries(),[])
    def test_oversized_regular_upload_returns_413_without_parsing(self):
        conn=self.client();body=b'not-json'*6000
        conn.request('POST','/api/library/terms',body,{'Origin':f'http://127.0.0.1:{self.server.server_port}','X-Aredoko-Token':'test-token'})
        response=conn.getresponse();self.assertEqual(response.status,413);self.assertEqual(json.loads(response.read())['error'],'Invalid body size')
        self.assertEqual(self.catalog.terms.entries(),[])
    def test_incomplete_rejected_upload_still_gets_a_response_before_client_deadline(self):
        conn=self.client();conn.putrequest('POST','/api/library/terms/import')
        conn.putheader('Content-Length','16777216');conn.putheader('X-Aredoko-Token','wrong');conn.endheaders()
        response=conn.getresponse();self.assertEqual(response.status,403);self.assertEqual(json.loads(response.read())['error'],'Invalid session')
        self.assertEqual(self.catalog.terms.entries(),[])

if __name__=='__main__':unittest.main()
