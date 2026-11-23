"""Transient transfer recovery; real loopback bytes, no external traffic."""
import hashlib,http.server,io,json,re,ssl,sys,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'app')]
import ai_acquisition
import test_ai_acquisition as fixture


class TransientTransferTests(unittest.TestCase):
    setUp=fixture.AcquisitionTests.setUp
    catalog=fixture.AcquisitionTests.catalog
    fetch=fixture.AcquisitionTests.fetch

    def response_fault(self,error_factory,*,always=False,cancel=None):
        original=urllib.request.OpenerDirector.open
        owner=self;opens=[]
        class Response:
            def __init__(self,wrapped):self.wrapped=wrapped;self.reads=0
            def __getattr__(self,name):return getattr(self.wrapped,name)
            def __enter__(self):return self
            def __exit__(self,*args):self.wrapped.close()
            def read(self,*args):
                self.reads+=1
                if self.reads==2:
                    if cancel:cancel.set()
                    raise error_factory()
                return self.wrapped.read(*args)
        def opened(opener,request,*args,**kwargs):
            response=original(opener,request,*args,**kwargs);opens.append(request)
            return Response(response) if always or len(opens)==1 else response
        return patch.object(urllib.request.OpenerDirector,'open',opened)

    def test_timeout_reconnects_at_written_offset_and_verifies_full_digest(self):
        with self.response_fault(TimeoutError):result=self.fetch()
        self.assertEqual(self.requests,[None,'bytes=65536-'])
        self.assertEqual((Path(result['root'])/'runtime/generated.bin').read_bytes(),self.content)

    def test_connection_reset_reconnects_without_duplicate_bytes(self):
        with self.response_fault(ConnectionResetError):result=self.fetch()
        self.assertEqual(self.requests,[None,'bytes=65536-'])
        self.assertEqual((Path(result['root'])/'runtime/generated.bin').read_bytes(),self.content)

    def test_reconnect_limit_retains_partial_without_publishing(self):
        self.content*=10
        self.value['entries'][0]['bytes']=len(self.content)
        import hashlib
        self.value['entries'][0]['sha256']=hashlib.sha256(self.content).hexdigest()
        with self.response_fault(TimeoutError,always=True),self.assertRaisesRegex(OSError,'resume'):
            self.fetch()
        self.assertEqual(self.requests,[None,'bytes=65536-','bytes=131072-'])
        root=self.base/'versions';catalog=self.catalog()
        self.assertEqual((root/('.acquire-'+catalog.fingerprint)/'parts/0.part').stat().st_size,196608)
        self.assertFalse((root/(catalog.key+'-'+catalog.fingerprint[:24])).exists())

    def test_cancellation_after_timeout_stops_before_reconnect(self):
        cancel=threading.Event()
        with self.response_fault(TimeoutError,cancel=cancel),self.assertRaises(InterruptedError):
            self.fetch(cancelled=cancel.is_set)
        self.assertEqual(self.requests,[None])

    def test_http_authorization_failure_is_not_retried(self):
        error=urllib.error.HTTPError(self.value['entries'][0]['url'],403,'Forbidden',None,None)
        with patch.object(urllib.request.OpenerDirector,'open',side_effect=error) as opened:
            with self.assertRaises(urllib.error.HTTPError):self.fetch()
        self.assertEqual(opened.call_count,1)

    def test_clean_early_eof_reconnects_without_waiting_for_manual_restart(self):
        # Real HTTP peer closes a declared-length response after 70,000 bytes.
        self.cut=True
        def progress(value):
            if value['stage']=='downloading' and value['bytes_received']>=65536:self.cut=False
        result=self.fetch(progress=progress)
        self.assertEqual(self.requests,[None,'bytes=70000-'])
        self.assertEqual((Path(result['root'])/'runtime/generated.bin').read_bytes(),self.content)

    def test_transient_transfer_classifies_ssl_eof_vs_cert_verification(self):
        self.assertTrue(ai_acquisition._transient_transfer(ssl.SSLEOFError('unexpected eof')))
        self.assertFalse(ai_acquisition._transient_transfer(urllib.error.URLError(ssl.SSLCertVerificationError('bad cert'))))

    def _https_catalog(self,payload):
        doc={'format':'aredoko-acquisition-v1','id':'generated-https','revision':'a'*40,'kind':'runtime',
             'license':'MIT','license_url':'https://example.org/license','allowed_hosts':['example.invalid'],
             'entries':[{'path':'runtime/generated.bin','url':'https://example.invalid/generated.bin',
                         'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),'role':'runtime'}]}
        return ai_acquisition.Catalog.parse(json.dumps(doc).encode())

    def test_tls_cert_verification_switches_to_winhttp_and_verifies_digest(self):
        payload=b'verified-https-bytes'
        catalog=self._https_catalog(payload)
        class FakeResponse:
            status=200
            headers={'Content-Length':str(len(payload)),'Content-Encoding':'identity'}
            def __init__(self):self.buf=io.BytesIO(payload)
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def geturl(self):return catalog.entries[0].url
            def read(self,n=-1):return self.buf.read(n)
        cert_err=urllib.error.URLError(ssl.SSLCertVerificationError('unable to get local issuer certificate'))
        with patch.object(ai_acquisition.os,'name','nt'),\
             patch.object(urllib.request.OpenerDirector,'open',side_effect=cert_err) as opened,\
             patch.object(ai_acquisition,'_winhttp_open',return_value=FakeResponse()) as winhttp_opened:
            result=ai_acquisition.acquire(catalog,self.base/'https-ok',validate=lambda r,c:None,publish=lambda op:op())
        self.assertEqual(opened.call_count,1)
        winhttp_opened.assert_called_once_with(catalog.entries[0].url,{'Accept-Encoding':'identity'},catalog,timeout=30)
        self.assertEqual((Path(result['root'])/'runtime/generated.bin').read_bytes(),payload)

    def test_tls_cert_verification_fails_closed_when_winhttp_also_fails(self):
        payload=b'verified-https-bytes'
        catalog=self._https_catalog(payload)
        cert_err=urllib.error.URLError(ssl.SSLCertVerificationError('unable to get local issuer certificate'))
        winhttp_cert_err=urllib.error.URLError(OSError(12045,'WinHTTP send failed (12045)'))
        with patch.object(ai_acquisition.os,'name','nt'),\
             patch.object(urllib.request.OpenerDirector,'open',side_effect=cert_err) as opened,\
             patch.object(ai_acquisition,'_winhttp_open',side_effect=winhttp_cert_err) as winhttp_opened:
            with self.assertRaises(urllib.error.URLError):
                ai_acquisition.acquire(catalog,self.base/'https-fail1',validate=lambda r,c:None,publish=lambda op:op())
        self.assertEqual(opened.call_count,1)
        self.assertEqual(winhttp_opened.call_count,1)

        http_err=urllib.error.HTTPError(catalog.entries[0].url,403,'Forbidden',None,None)
        with patch.object(ai_acquisition.os,'name','nt'),\
             patch.object(urllib.request.OpenerDirector,'open',side_effect=cert_err) as opened2,\
             patch.object(ai_acquisition,'_winhttp_open',side_effect=http_err) as winhttp_opened2:
            with self.assertRaises(urllib.error.HTTPError):
                ai_acquisition.acquire(catalog,self.base/'https-fail2',validate=lambda r,c:None,publish=lambda op:op())
        self.assertEqual(opened2.call_count,1)
        self.assertEqual(winhttp_opened2.call_count,1)

    def test_winhttp_error_classification(self):
        timeout_err=ai_acquisition._winhttp_error('read',12002)
        self.assertIsInstance(timeout_err,TimeoutError)
        self.assertTrue(ai_acquisition._transient_transfer(timeout_err))
        for code in (12030,12031,12152):
            conn_err=ai_acquisition._winhttp_error('read',code)
            self.assertIsInstance(conn_err,ConnectionResetError)
            self.assertTrue(ai_acquisition._transient_transfer(conn_err))
        cert_err=ai_acquisition._winhttp_error('send',12045)
        self.assertIsInstance(cert_err,urllib.error.URLError)
        self.assertFalse(ai_acquisition._transient_transfer(cert_err))

    def test_winhttp_open_loopback_get_range_redirect_and_error(self):
        if ai_acquisition.os.name!='nt':self.skipTest('Windows only')
        payload=b'0123456789abcdef'*5000
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                if self.path=='/file':
                    rng=self.headers.get('Range')
                    if rng:
                        m=re.fullmatch(r'bytes=(\d+)-',rng)
                        start=int(m.group(1))
                        body=payload[start:]
                        self.send_response(206)
                        self.send_header('Content-Range',f'bytes {start}-{len(payload)-1}/{len(payload)}')
                        self.send_header('Content-Length',str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                    else:
                        self.send_response(200)
                        self.send_header('Content-Length',str(len(payload)))
                        self.end_headers()
                        self.wfile.write(payload)
                elif self.path=='/redir-ok':
                    self.send_response(302)
                    self.send_header('Location','/file')
                    self.send_header('Content-Length','0')
                    self.end_headers()
                elif self.path=='/redir-bad':
                    self.send_response(302)
                    self.send_header('Location','https://evil.invalid/x')
                    self.send_header('Content-Length','0')
                    self.end_headers()
                else:
                    self.send_response(404)
                    self.send_header('Content-Length','0')
                    self.end_headers()
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        port=server.server_port
        doc={'format':'aredoko-acquisition-v1','id':'winhttp-loopback','revision':'a'*40,'kind':'runtime',
             'license':'MIT','license_url':'https://example.org/license','allowed_hosts':['127.0.0.1'],
             'entries':[{'path':'runtime/generated.bin','url':f'http://127.0.0.1:{port}/file',
                         'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),'role':'runtime'}]}
        catalog=ai_acquisition.Catalog.parse(json.dumps(doc).encode(),test_loopback=True)

        with ai_acquisition._winhttp_open(f'http://127.0.0.1:{port}/file',{'Accept-Encoding':'identity'},catalog,timeout=10) as resp:
            self.assertEqual(resp.status,200)
            self.assertEqual(resp.headers.get('Content-Length'),str(len(payload)))
            chunks=[];chunk=resp.read(16384)
            while chunk:
                chunks.append(chunk)
                chunk=resp.read(16384)
            self.assertEqual(b''.join(chunks),payload)
            self.assertEqual(resp.read(1),b'')

        with ai_acquisition._winhttp_open(f'http://127.0.0.1:{port}/file',{'Accept-Encoding':'identity','Range':'bytes=10-'},catalog,timeout=10) as resp:
            self.assertEqual(resp.status,206)
            self.assertEqual(resp.headers.get('Content-Range'),f'bytes 10-{len(payload)-1}/{len(payload)}')
            chunks=[];chunk=resp.read(65536)
            while chunk:
                chunks.append(chunk)
                chunk=resp.read(65536)
            self.assertEqual(b''.join(chunks),payload[10:])

        with ai_acquisition._winhttp_open(f'http://127.0.0.1:{port}/redir-ok',{'Accept-Encoding':'identity'},catalog,timeout=10) as resp:
            self.assertEqual(resp.status,200)
            self.assertTrue(resp.geturl().endswith('/file'))
            chunks=[];chunk=resp.read(65536)
            while chunk:
                chunks.append(chunk)
                chunk=resp.read(65536)
            self.assertEqual(b''.join(chunks),payload)

        with self.assertRaisesRegex(ValueError,'Untrusted source URL'):
            ai_acquisition._winhttp_open(f'http://127.0.0.1:{port}/redir-bad',{'Accept-Encoding':'identity'},catalog,timeout=10)

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            ai_acquisition._winhttp_open(f'http://127.0.0.1:{port}/missing',{'Accept-Encoding':'identity'},catalog,timeout=10)
        self.assertEqual(ctx.exception.code,404)
