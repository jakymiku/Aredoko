"""Generated loopback HTTP only; no external model/package downloads."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import hashlib,json,sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from ai_acquisition import Catalog,acquire

class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.content=b'generated-artifact-'*10000;self.requests=[];self.cut=False;self.corrupt=False;self.ignore_range=False
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                requested=self.headers.get('Range');owner.requests.append(requested)
                payload=(b'x'*len(owner.content)) if owner.corrupt else owner.content
                offset=int(requested[6:-1]) if requested and not owner.ignore_range else 0
                self.send_response(206 if requested and not owner.ignore_range else 200)
                self.send_header('Content-Length',str(len(payload)-offset))
                if requested and not owner.ignore_range:self.send_header('Content-Range',f'bytes {offset}-{len(payload)-1}/{len(payload)}')
                self.end_headers()
                try:self.wfile.write(payload[offset:offset+70000] if owner.cut else payload[offset:])
                except (BrokenPipeError,ConnectionResetError):pass
                self.close_connection=True
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        self.addCleanup(lambda:(self.server.shutdown(),self.server.server_close(),thread.join(3)))
        self.value={'format':'aredoko-acquisition-v1','id':'generated-pack','revision':'a'*40,'kind':'runtime','license':'MIT','license_url':'https://example.org/license','allowed_hosts':['127.0.0.1'],'entries':[{'path':'runtime/generated.bin','url':f'http://127.0.0.1:{self.server.server_port}/artifact','bytes':len(self.content),'sha256':hashlib.sha256(self.content).hexdigest(),'role':'runtime'}]}
    def catalog(self):return Catalog.parse(json.dumps(self.value).encode(),test_loopback=True)
    def fetch(self,**kwargs):
        return acquire(self.catalog(),self.base/'versions',validate=lambda root,cancel:self.assertEqual((root/'runtime/generated.bin').read_bytes(),self.content),publish=lambda operation:operation(),**kwargs)
    def test_success_verified_new_version_without_settings_or_execution(self):
        progress=[];result=self.fetch(progress=progress.append)
        self.assertEqual((Path(result['root'])/'runtime/generated.bin').read_bytes(),self.content)
        self.assertEqual(progress[-1]['bytes_verified'],len(self.content))
        self.assertEqual(self.requests,[None]);self.assertFalse((self.base/'launch-settings.json').exists())
        file=Path(result['root'])/'runtime/generated.bin';before=(file.read_bytes(),file.stat().st_mtime_ns)
        reused=self.fetch();self.assertTrue(reused['reused']);self.assertEqual(reused['root'],result['root'])
        self.assertEqual(self.requests,[None]);self.assertEqual((file.read_bytes(),file.stat().st_mtime_ns),before)
    def test_existing_version_corruption_is_preserved_and_never_redownloaded(self):
        result=self.fetch();file=Path(result['root'])/'runtime/generated.bin';bad=b'x'*len(self.content);file.write_bytes(bad)
        with self.assertRaisesRegex(ValueError,'checksum'):self.fetch()
        self.assertEqual(file.read_bytes(),bad);self.assertEqual(self.requests,[None])

    def test_existing_version_extra_file_is_preserved_and_rejected(self):
        result=self.fetch();extra=Path(result['root'])/'unlisted.py';extra.write_bytes(b'untrusted')
        with self.assertRaisesRegex(ValueError,'inventory'):self.fetch()
        self.assertEqual(extra.read_bytes(),b'untrusted');self.assertEqual(self.requests,[None])

    def test_existing_version_cancellation_before_acknowledgement_keeps_files(self):
        result=self.fetch();target=Path(result['root']);cancel=threading.Event()
        def progress(value):
            if value['stage']=='publishing':cancel.set()
        with self.assertRaises(InterruptedError):self.fetch(cancelled=cancel.is_set,progress=progress)
        self.assertEqual((target/'runtime/generated.bin').read_bytes(),self.content);self.assertEqual(self.requests,[None])

    def test_truncated_download_resumes_exact_range(self):
        self.cut=True
        with self.assertRaises(OSError):self.fetch()
        self.cut=False;result=self.fetch()
        self.assertTrue(self.requests[-1].startswith('bytes='))
        self.assertEqual((Path(result['root'])/'runtime/generated.bin').read_bytes(),self.content)
    def test_server_ignoring_range_restarts_instead_of_appending(self):
        self.cut=True
        with self.assertRaises(OSError):self.fetch()
        self.cut=False;self.ignore_range=True;self.fetch()
        self.assertTrue(self.requests[-1].startswith('bytes='))
    def test_checksum_failure_never_publishes_and_can_retry(self):
        self.corrupt=True
        with self.assertRaisesRegex(ValueError,'checksum'):self.fetch()
        self.assertFalse(any(p.is_dir() and not p.name.startswith('.') for p in (self.base/'versions').iterdir()))
        self.corrupt=False;self.fetch();self.assertIsNone(self.requests[-1])
    def test_cancel_preserves_partial_and_next_request_resumes(self):
        cancel=threading.Event()
        def progress(value):
            if value['stage']=='downloading' and value['bytes_received']>=65536:cancel.set()
        with self.assertRaises(InterruptedError):self.fetch(cancelled=cancel.is_set,progress=progress)
        self.fetch();self.assertTrue(self.requests[-1].startswith('bytes='))
    def test_validator_and_publication_owner_must_succeed_before_visibility(self):
        catalog=self.catalog();root=self.base/'versions'
        with self.assertRaisesRegex(ValueError,'validation failed'):
            acquire(catalog,root,validate=lambda *args:(_ for _ in ()).throw(ValueError('validation failed')),publish=lambda op:op())
        with self.assertRaisesRegex(InterruptedError,'owner closed'):
            acquire(catalog,root,validate=lambda *args:None,publish=lambda op:(_ for _ in ()).throw(InterruptedError('owner closed')))
        self.assertFalse(any(p.is_dir() and not p.name.startswith('.') for p in root.iterdir()))
    def test_catalog_rejects_path_collisions_mutable_identity_and_production_http(self):
        with self.assertRaises(ValueError):Catalog.parse(json.dumps(self.value).encode())
        self.value['revision']='main'
        with self.assertRaises(ValueError):self.catalog()
        self.value['revision']='a'*40
        for path in ('../escape','CON.txt','runtime/../escape','/absolute'):
            self.value['entries'][0]['path']=path
            with self.assertRaises(ValueError):self.catalog()
        self.value['entries'][0]['path']='runtime'
        self.value['entries'].append({**self.value['entries'][0],'path':'runtime/child'})
        with self.assertRaises(ValueError):self.catalog()
    def test_optional_rate_limit_applies_across_all_files(self):
        self.value['entries'].append({**self.value['entries'][0],'path':'runtime/second.bin'})
        clock=[0.0]
        def sleep(seconds):clock[0]+=seconds
        with patch('ai_acquisition.time.monotonic',side_effect=lambda:clock[0]),patch('ai_acquisition.time.sleep',side_effect=sleep):
            self.fetch(bytes_per_second=65536)
        self.assertGreaterEqual(clock[0],len(self.content)*2/65536)

    def test_unlisted_staged_file_cannot_be_published(self):
        catalog=self.catalog();root=self.base/'versions'
        stage=root/('.acquire-'+catalog.fingerprint)
        (stage/'payload').mkdir(parents=True)
        (stage/'payload/unlisted.py').write_text('untrusted extra',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'inventory'):self.fetch()
        self.assertTrue((stage/'payload/unlisted.py').exists())
        self.assertFalse((root/(catalog.key+'-'+catalog.fingerprint[:24])).exists())

    def test_prefix_collision_cannot_hide_between_lexical_siblings(self):
        entry=self.value['entries'][0]
        self.value['entries']=[{**entry,'path':name} for name in ('a','a-b','a/child')]
        with self.assertRaisesRegex(ValueError,'collision'):self.catalog()

    def test_space_failure_occurs_before_network(self):
        from collections import namedtuple
        usage=namedtuple('Usage','total used free')(1,1,0)
        with patch('ai_acquisition.shutil.disk_usage',return_value=usage),self.assertRaises(OSError):self.fetch()
        self.assertEqual(self.requests,[])

if __name__=='__main__':unittest.main()
