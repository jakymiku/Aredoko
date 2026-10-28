"""CPU-only startup faults; no real imports, models, DLL loads or GPU use."""
import builtins
import io
import json
from pathlib import Path
import sys
import queue
import subprocess
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import ai_worker
import tagger_worker
from inference_errors import STARTUP_ERRORS,startup_error
from ai_process import AIUnavailable,AIWorkerUnavailable,EncoderProcess,worker_failure


class InferenceFailureTests(unittest.TestCase):
    def test_real_owned_child_is_reaped_after_response_overflow(self):
        encoder=EncoderProcess('unused','unused')
        child=subprocess.Popen([sys.executable,'-u','-c','import sys,time;print("{}\\n{}\\n{}",flush=True);time.sleep(10)'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        encoder.process=child
        thread=threading.Thread(target=encoder._read,args=(child,encoder.responses,encoder.protocol_fault),daemon=True)
        try:
            thread.start();thread.join(2)
            self.assertFalse(thread.is_alive());self.assertTrue(encoder.protocol_fault.is_set())
            with self.assertRaises(AIUnavailable):encoder._response(.1)
            self.assertIsNotNone(child.poll());self.assertIsNone(encoder.process)
            self.assertTrue(child.stdin.closed and child.stdout.closed)
        finally:encoder.close();thread.join(2)

    def test_surplus_worker_output_does_not_strand_a_reader_on_an_abandoned_queue(self):
        from types import SimpleNamespace
        encoder=EncoderProcess('unused','unused');responses=queue.Queue(maxsize=2);fault=threading.Event()
        process=SimpleNamespace(stdout=io.StringIO('{"ready":true}\n{"vector":[]}\n{"unexpected":true}\n'))
        thread=threading.Thread(target=encoder._read,args=(process,responses,fault),daemon=True);thread.start();thread.join(1)
        self.assertFalse(thread.is_alive());self.assertTrue(fault.is_set());self.assertEqual(responses.qsize(),2)
        self.assertFalse(encoder.protocol_fault.is_set())  # The old queue cannot fault a replacement.
        encoder.responses=responses;encoder.protocol_fault=fault
        with patch.object(encoder,'_stop') as stop:
            with self.assertRaisesRegex(AIUnavailable,'Invalid AI worker response'):encoder._response(.01)
            stop.assert_called_once()

    def test_full_queue_at_eof_or_parse_failure_also_never_blocks_cleanup(self):
        from types import SimpleNamespace
        for line in ('','not-json\n'):
            encoder=EncoderProcess('unused','unused');responses=queue.Queue(maxsize=2);fault=threading.Event()
            responses.put({'old':1});responses.put({'old':2})
            thread=threading.Thread(target=encoder._read,args=(SimpleNamespace(stdout=io.StringIO(line)),responses,fault),daemon=True)
            thread.start();thread.join(1)
            self.assertFalse(thread.is_alive());self.assertTrue(fault.is_set())

    def test_classification_uses_types_and_windows_codes_never_private_text(self):
        for error,expected in ((ImportError('C:/private/model.dll'),'DependencyUnavailable'),
                               (OSError('DLL load failed: private'),'InitializationFailed'),
                               (MemoryError('private'),'InitializationFailed')):
            self.assertEqual(startup_error(error),{'error':expected})
        for number,expected in ((126,'DependencyUnavailable'),(127,'DependencyUnavailable'),(1114,'DependencyUnavailable'),(193,'ArchitectureMismatch'),(5,'InitializationFailed')):
            error=OSError('private path');error.winerror=number
            self.assertEqual(startup_error(error),{'error':expected})

    def test_worker_sends_one_fixed_startup_response_without_ready_or_path(self):
        original=builtins.__import__
        def fail(name,*args,**kwargs):
            if name=='torch':raise ImportError('private-user-folder/native.dll')
            return original(name,*args,**kwargs)
        output=io.StringIO()
        with patch.object(sys,'argv',['worker','--model','unused']),patch.object(sys,'stdout',output),\
             patch.object(sys,'stderr',io.StringIO()),patch('ai_worker.threading.Thread'),patch('builtins.__import__',side_effect=fail):
            ai_worker.main()
        self.assertEqual(json.loads(output.getvalue()),{'error':'DependencyUnavailable'})
        self.assertNotIn('private',output.getvalue())

    def test_parent_only_accepts_exact_startup_error_envelopes(self):
        for wire,(code,message) in STARTUP_ERRORS.items():
            error=worker_failure({'error':wire})
            self.assertIsInstance(error,AIWorkerUnavailable);self.assertEqual(error.code,code);self.assertEqual(str(error),message)
        for value in ({'error':{'path':'private'}},{'error':['private']},{'error':'private C:/model'},
                      {'error':'DependencyUnavailable','scores':[]},None,[],True):
            error=worker_failure(value)
            self.assertIs(type(error),AIUnavailable);self.assertEqual(str(error),'AI inference failed')

    def test_tagger_import_failure_uses_the_same_finite_wire_contract(self):
        from types import SimpleNamespace
        original=builtins.__import__
        def fail(name,*args,**kwargs):
            if name=='onnxruntime':raise ImportError('private path: missing native dependency')
            return original(name,*args,**kwargs)
        output=io.StringIO();profile=SimpleNamespace(verify=lambda *a,**k:Path('unused'),data=lambda:{'label_count':5})
        source=SimpleNamespace(buffer=io.BytesIO(b'{"image":"Zml4dHVyZQ=="}\n'))
        with patch.object(sys,'argv',['tagger','--profile-json','{}','--parent-pid','1']),\
             patch.object(sys,'stdin',source),patch.object(sys,'stdout',output),patch('tagger_worker.threading.Thread'),\
             patch('tagger_worker.WDProfile.from_dict',return_value=profile),patch('tagger_worker.labels'),\
             patch('builtins.__import__',side_effect=fail):
            tagger_worker.main()
        self.assertEqual(json.loads(output.getvalue()),{'error':'DependencyUnavailable'})

    def test_startup_failure_releases_its_owned_process_and_allows_retry(self):
        class Process:
            def __init__(self):self.stdin=io.StringIO();self.stdout=io.StringIO();self.dead=False
            def poll(self):return 0 if self.dead else None
            def kill(self):self.dead=True
            def wait(self,timeout=None):return 0
        encoder=EncoderProcess('unused','unused');children=[]
        def spawn(*args,**kwargs):
            child=Process();children.append(child);return child
        real_response=encoder._response
        # Inject a protocol event, rather than mocking away its validation.
        def queued_response():
            encoder.responses.put({'error':'DependencyUnavailable'} if len(children)==1 else
                {'ready':True,'dimension':encoder.profile.dimension,'profile':encoder.profile.key,'device':'cpu'})
            return real_response()
        with patch.object(EncoderProcess,'available',property(lambda _:True)),patch('ai_process.worker_command',return_value=['generated']),\
             patch('ai_process.subprocess.Popen',side_effect=spawn),patch('ai_process.threading.Thread'),patch.object(encoder,'_response',side_effect=queued_response):
            with self.assertRaises(AIWorkerUnavailable):encoder._start()
            self.assertIsNone(encoder.process);self.assertEqual(encoder.device,'');self.assertEqual(encoder.telemetry,{})
            self.assertTrue(children[0].dead and children[0].stdin.closed and children[0].stdout.closed)
            encoder._start();self.assertTrue(encoder.resident);self.assertEqual(encoder.device,'cpu')
            encoder.close();self.assertTrue(children[1].dead)

    def test_malformed_response_is_unavailable_not_typeerror_or_keyerror(self):
        for value in (None,[],42,'private',{'error':None},{'error':['private']}):
            encoder=EncoderProcess('unused','unused');encoder.responses.put(value)
            with patch.object(encoder,'_stop') as stop:
                with self.assertRaises(AIUnavailable) as caught:encoder._response(.1)
                self.assertNotIn('private',str(caught.exception))
                if type(value) is not dict:stop.assert_called_once()


if __name__=='__main__':unittest.main()
