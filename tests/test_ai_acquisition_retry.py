"""Transient transfer recovery; real loopback bytes, no external traffic."""
import sys,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
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
