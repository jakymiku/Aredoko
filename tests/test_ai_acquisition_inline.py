"""Version2 app-owned sidecars; generated HTTP only, no external downloads."""
import hashlib,json,sys,tempfile,threading,unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/name) for name in ('app','tools')]
from ai_acquisition import Catalog,acquire
from ai_model_pack import model_validator
from ai_profiles import DEFAULT_PROFILE
from build_ai_model_catalog import build_catalog
import test_ai_model_pack as model_fixtures

class InlineMetadataTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.base=Path(temp.name)
        self.payload=b'generated weights';self.requests=[];owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                owner.requests.append(self.path)
                self.send_response(200);self.send_header('Content-Length',str(len(owner.payload)));self.end_headers();self.wfile.write(owner.payload)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        self.addCleanup(lambda:(self.server.shutdown(),self.server.server_close(),thread.join(3)))
        self.value={'format':'aredoko-acquisition-v2','id':'generated-mixed','kind':'model','revision':'a'*40,'license':'fixture only','license_url':'https://example.org/NOTICE','allowed_hosts':['127.0.0.1'],'entries':[
            {'path':'model/model.bin','url':f'http://127.0.0.1:{self.server.server_port}/weights','bytes':len(self.payload),'sha256':hashlib.sha256(self.payload).hexdigest(),'role':'weights'},
            self.inline('model/aredoko-source.json','{\"revision\":\"fixture\"}\r\n'),self.inline('model/LICENSE.txt','生成ライセンス\r\n',role='license')]}
    def inline(self,path,text,role='configuration'):
        raw=text.encode('utf-8');return {'path':path,'inline_utf8':text,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'role':role}
    def catalog(self):return Catalog.parse(json.dumps(self.value).encode(),test_loopback=True)
    def fetch(self,**kwargs):
        return acquire(self.catalog(),self.base/'versions',validate=lambda *args:None,publish=lambda action:action(),**kwargs)

    def test_mixed_payload_preserves_exact_utf8_and_uses_only_remote_url(self):
        result=self.fetch();root=Path(result['root'])
        self.assertEqual(self.requests,['/weights'])
        self.assertEqual((root/'model/LICENSE.txt').read_bytes(),'生成ライセンス\r\n'.encode())
        self.assertEqual((root/'model/aredoko-source.json').read_bytes(),b'{"revision":"fixture"}\r\n')
        again=self.fetch();self.assertTrue(again['reused']);self.assertEqual(self.requests,['/weights'])
        self.assertEqual(result['bytes'],sum(e['bytes'] for e in self.value['entries']))

    def test_inline_only_performs_no_network_or_interpreter_execution(self):
        self.value['entries']=self.value['entries'][1:]
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('No network')),patch('subprocess.Popen',side_effect=AssertionError('No code execution')):self.fetch()
        self.assertEqual(self.requests,[])

    def test_old_format_mixed_sources_bad_digest_or_weight_sidecar_rejected(self):
        original=json.dumps(self.value)
        for change in ('old','future','mixed','digest','size','role','extension','license_auth','license_control'):
            self.value=json.loads(original);entry=self.value['entries'][1]
            if change=='old':self.value['format']='aredoko-acquisition-v1'
            elif change=='future':self.value['format']='aredoko-acquisition-v3'
            elif change=='mixed':entry['url']='https://example.org/metadata'
            elif change=='digest':entry['sha256']='0'*64
            elif change=='size':entry['bytes']+=1
            elif change=='role':entry['role']='weights'
            elif change=='license_auth':self.value['license_url']='https://:secret@example.org/license'
            elif change=='license_control':self.value['license_url']='https://example.org/license\n'
            else:entry['path']='model/execute.py'
            with self.subTest(change=change),self.assertRaises(ValueError):self.catalog()
        self.assertEqual(self.requests,[])

    def test_metadata_byte_and_aggregate_limits_are_enforced(self):
        self.value['entries']=[self.inline('model/a.json','界'*30000)]
        with self.assertRaises(ValueError):self.catalog()
        self.value['entries']=[self.inline(f'model/{i}.json','x'*60000) for i in range(5)]
        with self.assertRaises(ValueError):self.catalog()

    def test_inline_change_invalidates_catalog_and_published_corruption_is_preserved(self):
        before=self.catalog().fingerprint;result=self.fetch();path=Path(result['root'])/'model/LICENSE.txt';path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'checksum'):self.fetch()
        self.assertEqual(path.read_bytes(),b'changed');self.assertEqual(self.requests,['/weights'])
        self.value['entries'][2]=self.inline('model/LICENSE.txt','new fixture',role='license')
        self.assertNotEqual(self.catalog().fingerprint,before)

    def test_cancel_between_sidecars_and_publication_never_publishes(self):
        cancel=threading.Event()
        def progress(value):
            if value['stage']=='publishing':cancel.set()
        with self.assertRaises(InterruptedError):self.fetch(cancelled=cancel.is_set,progress=progress)
        self.assertFalse(any(p.is_dir() and not p.name.startswith('.') for p in (self.base/'versions').iterdir()))
        self.fetch();self.assertEqual(self.requests,['/weights'])

class InlineModelBuilderTests(unittest.TestCase):
    def test_builder_embeds_provenance_and_license_but_keeps_weights_remote(self):
        # Reuse only the generated fixture setup; do not rerun its test class.
        fixture=model_fixtures.ModelCatalogTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        notice=fixture.source/'LICENSE.txt';notice.write_bytes('fixture\r\n日本語\r\n'.encode())
        before=fixture.source_state()
        raw,catalog=build_catalog(fixture.source,fixture.profile,embed_metadata=True,**fixture.options)
        value=json.loads(raw);self.assertEqual(value['format'],'aredoko-acquisition-v2')
        embedded={e['path']:e for e in value['entries'] if 'inline_utf8' in e}
        self.assertEqual(set(embedded),{fixture.profile.directory+'/aredoko-revision.txt',fixture.profile.directory+'/LICENSE.txt'})
        self.assertEqual(embedded[fixture.profile.directory+'/LICENSE.txt']['inline_utf8'].encode(),notice.read_bytes())
        self.assertTrue(next(e for e in value['entries'] if e['role']=='weights')['url'].startswith('https://'))
        self.assertEqual(fixture.source_state(),before);self.assertTrue(callable(model_validator(fixture.profile,catalog)))

if __name__=='__main__':unittest.main()
