"""Full runtime guards under bounded parallel reads; no selected code execution."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tools'),str(ROOT/'tests')]
import test_ai_runtime as fixtures
import ai_runtime as runtime
import runtime_verification as parallel


class ParallelRuntimeValidationTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=fixtures.fixture(Path(temporary.name)/'runtime')
        extra=self.root/'Lib/site-packages/generated';extra.mkdir()
        for i in range(80):(extra/f'{i:03}.py').write_bytes(b'Generated content '+str(i).encode())
        (extra/'large.bin').write_bytes(b'Generated data'*200000);(extra/'empty.py').write_bytes(b'')
        self.manifest=fixtures.seal(self.root)
    def assert_no_workers(self):self.assertFalse(any(t.name.startswith('aredoko-runtime-verify') for t in threading.enumerate()))
    def test_same_full_checks_monotonic_progress_and_callbacks_on_owner_thread(self):
        owner=threading.get_ident();calls=[];workers=set();original=runtime.digest
        def observed(path,cancelled=lambda:False,on_bytes=None):
            if threading.get_ident()!=owner:workers.add(threading.get_ident())
            return original(path,cancelled,on_bytes)
        def progress(value):calls.append((threading.get_ident(),value.copy()))
        with patch.object(runtime,'digest',side_effect=observed),patch('subprocess.Popen',side_effect=AssertionError('No selected code execution')):
            info=runtime.inspect_runtime(self.root,verify=True,progress=progress)
        self.assertEqual(info['verification'],'full');self.assertGreaterEqual(len(workers),1);self.assertLessEqual(len(workers),2)
        self.assertTrue(all(thread==owner for thread,_ in calls));self.assertEqual(calls[0][1]['files_done'],0)
        self.assertEqual(calls[-1][1]['files_done'],len(self.manifest['entries']));self.assertEqual(calls[-1][1]['bytes_done'],self.manifest['total_bytes'])
        self.assertEqual([v['files_done'] for _,v in calls],sorted(v['files_done'] for _,v in calls))
        self.assertEqual([v['bytes_done'] for _,v in calls],sorted(v['bytes_done'] for _,v in calls));self.assert_no_workers()
    def test_owner_cancellation_stops_readers_and_a_later_validation_can_retry(self):
        stopped=threading.Event();owner=threading.get_ident();callbacks=[]
        def progress(value):
            if value['files_done']>=1:stopped.set()
        def cancelled():callbacks.append(threading.get_ident());return stopped.is_set()
        with self.assertRaisesRegex(RuntimeError,'cancelled'):runtime.inspect_runtime(self.root,verify=True,cancelled=cancelled,progress=progress)
        self.assertTrue(all(thread==owner for thread in callbacks));self.assert_no_workers()
        self.assertEqual(runtime.inspect_runtime(self.root,verify=True)['verification'],'full');self.assert_no_workers()
    def test_progress_observer_failure_preserves_its_error_and_joins_workers(self):
        def progress(value):
            if value['bytes_done']>0:raise LookupError('observer failed')
        with self.assertRaisesRegex(LookupError,'observer failed'):runtime.inspect_runtime(self.root,verify=True,progress=progress)
        self.assert_no_workers()
    def test_corrupted_noncore_file_is_never_accepted(self):
        p=self.root/'Lib/site-packages/generated/040.py';p.write_bytes(b'x'*p.stat().st_size)
        with self.assertRaisesRegex(ValueError,'file changed'):runtime.inspect_runtime(self.root,verify=True)
        self.assert_no_workers()
    def test_failed_file_cancels_a_peer_reader_before_returning(self):
        reached=threading.Event();released=threading.Event();original=runtime.digest
        def gated(path,cancelled=lambda:False,on_bytes=None):
            key=Path(path).relative_to(self.root).as_posix()
            if key=='LICENSE.txt':
                if not reached.wait(5):raise AssertionError('Peer reader did not start')
                raise ValueError('failed guarded source')
            if key=='Lib/site-packages/PIL/__init__.py':
                reached.set();deadline=time.monotonic()+5
                while not cancelled():
                    if time.monotonic()>deadline:raise AssertionError('Owner did not stop peer')
                    time.sleep(.01)
                released.set();raise RuntimeError('Runtime validation cancelled')
            return original(path,cancelled,on_bytes)
        with patch.object(runtime,'digest',side_effect=gated),self.assertRaisesRegex(ValueError,'failed guarded source'):
            runtime.inspect_runtime(self.root,verify=True)
        self.assertTrue(released.is_set());self.assert_no_workers()
    def test_changed_marker_after_file_validation_is_still_rejected(self):
        changed=False
        def progress(value):
            nonlocal changed
            if value['files_done']>=1 and not changed:
                changed=True
                with (self.root/runtime.MARKER).open('a') as stream:stream.write(' ')
        with self.assertRaisesRegex(ValueError,'inventory changed'):runtime.inspect_runtime(self.root,verify=True,progress=progress)
        self.assertTrue(changed);self.assert_no_workers()
    def test_small_inventory_keeps_serial_path_without_executor_overhead(self):
        with tempfile.TemporaryDirectory() as d:
            small=fixtures.fixture(Path(d)/'small')
            with patch.object(parallel,'ThreadPoolExecutor',side_effect=AssertionError('Small inventories stay serial')):
                self.assertEqual(runtime.inspect_runtime(small,verify=True)['verification'],'full')
        self.assert_no_workers()
    def test_callback_cancellation_before_any_reader_is_started(self):
        with patch.object(parallel,'ThreadPoolExecutor',side_effect=AssertionError('No readers after cancellation')):
            with self.assertRaisesRegex(RuntimeError,'cancelled'):runtime.inspect_runtime(self.root,verify=True,cancelled=lambda:True)
        self.assert_no_workers()


if __name__=='__main__':unittest.main()
