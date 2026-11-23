"""Exercise the generated handoff sandbox through the real production HTTP API."""
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.request
from unittest.mock import Mock

REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'tools'))
from similarity_sandbox import SimilaritySandbox
from server import handler_for

class SimilaritySandboxTests(unittest.TestCase):
    def sandbox(self,scenario='indexed'):
        folder=REPO/'data/ai-ui';folder.mkdir(parents=True,exist_ok=True)
        tmp=tempfile.TemporaryDirectory(dir=folder);self.addCleanup(tmp.cleanup)
        sandbox=SimilaritySandbox(Path(tmp.name)/'fixture',scenario);self.addCleanup(sandbox.close)
        return sandbox
    def test_indexed_fixture_paging_scope_and_source_bytes(self):
        sandbox=self.sandbox();origin=sandbox.item('generated-065.png')
        before=sandbox.ai.store.path.read_bytes()
        page0=sandbox.ai.similar(origin,page=0,scope=sandbox.scope)
        page1=sandbox.ai.similar(origin,page=1,scope=sandbox.scope)
        self.assertEqual((page0['total'],len(page0['items']),len(page1['items'])),(72,60,12))
        self.assertNotIn(origin,[row['id'] for row in page0['items']+page1['items']])
        self.assertTrue(all(row['root_id']==sandbox.roots[0] for row in page0['items']+page1['items']))
        self.assertEqual(sandbox.encoder.calls,0);self.assertFalse(sandbox.encoder.available)
        self.assertEqual(before,sandbox.ai.store.path.read_bytes())
        self.assertEqual(sandbox.source_before,sandbox.source_digest())
        self.assertEqual(sandbox.settings_before,(sandbox.target/'settings.json').read_bytes())
    def test_sandbox_scenarios_have_explicit_empty_fallbacks(self):
        for scenario,status in [('unindexed','unindexed'),('text-only','unsupported_profile')]:
            sandbox=self.sandbox(scenario)
            result=sandbox.ai.similar(sandbox.item('generated-001.png'),scope=sandbox.scope)
            self.assertEqual((result['similarity_status'],result['total'],result['items']),(status,0,[]))
            self.assertEqual(sandbox.encoder.calls,0)
    def test_real_http_contract_and_error_hooks(self):
        sandbox=self.sandbox()
        server=ThreadingHTTPServer(('127.0.0.1',0),sandbox.handler());thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(thread.join,5);self.addCleanup(server.shutdown)
        base=f'http://127.0.0.1:{server.server_port}'
        with urllib.request.urlopen(base+'/api/session') as response:session=json.load(response)
        def post(item):
            request=urllib.request.Request(base+'/api/library/ai/similar',data=json.dumps({'item_id':item,'scope':sandbox.scope}).encode(),
                headers={'Origin':base,'X-Aredoko-Token':session['token'],'Content-Type':'application/json'})
            with urllib.request.urlopen(request) as response:return json.load(response)
        result=post(sandbox.item('generated-001.png'))
        self.assertEqual((result['origin_id'],result['mode'],result['page'],result['limit']),(sandbox.item('generated-001.png'),'similar',0,60))
        self.assertEqual(len(result['origin_revision']),64)
        self.assertEqual(post(sandbox.item('generated-unindexed.png'))['similarity_status'],'unindexed')
        for fault,code in [('busy',409),('unavailable',503)]:
            sandbox.ai.fail=fault
            with self.assertRaises(urllib.error.HTTPError) as caught:post(sandbox.item('generated-001.png'))
            self.assertEqual(caught.exception.code,code);caught.exception.close()
        sandbox.ai.fail=None
    def test_output_refuses_reuse_and_non_fixture_locations(self):
        sandbox=self.sandbox()
        with self.assertRaises(FileExistsError):SimilaritySandbox(sandbox.target)
        with self.assertRaises(ValueError):SimilaritySandbox(REPO/'data')
        self.assertEqual(sandbox.source_before,sandbox.source_digest())
    def test_cancelled_reply_does_not_raise_or_retry(self):
        cls=handler_for(None,'not-a-session')
        for error in (BrokenPipeError,ConnectionResetError):
            handler=cls.__new__(cls)
            handler.send_response=Mock();handler.send_header=Mock();handler.end_headers=Mock()
            handler.wfile=Mock();handler.wfile.write.side_effect=error()
            handler.send(200,{'items':[]})
            self.assertTrue(handler.close_connection);handler.wfile.write.assert_called_once()

if __name__=='__main__':unittest.main()
