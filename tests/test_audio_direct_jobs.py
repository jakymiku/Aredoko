"""Owned job/query and image/audio handover with supplied CPU encoders only."""
from pathlib import Path
from contextlib import contextmanager
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_audio_direct_index as fixture
from audio_direct_jobs import AudioDirectJobs
from inference_ownership import InferenceOwnership
from ai_search import AIBusy
from ai_process import AIUnavailable


class Encoder(fixture.Encoder):
    available=True
    def __init__(self):self.resident=False;self.calls=0;self.releases=0;self.closed=False
    def encode(self,*args):self.calls+=1;self.resident=True;return [1,0,0]
    def release(self):self.releases+=1;self.resident=False;return {'released':True,'resident':False}
    def close(self):self.closed=True;self.resident=False


class DirectAudioJobTests(unittest.TestCase):
    supplied=fixture.DirectAudioIndexTests.supplied
    snapshot=fixture.DirectAudioIndexTests.snapshot
    seed=fixture.DirectAudioIndexTests.seed
    def setUp(self):
        fixture.DirectAudioIndexTests.setUp(self)
        self.encoder=Encoder();self.vision=Encoder();self.group=InferenceOwnership()
        self.vision_lock=self.group.for_encoder(self.vision)
        self.jobs=AudioDirectJobs(self.catalog,self.encoder,inference=self.group.for_encoder(self.encoder),
                                  reader=self.reader,stage_parent=self.stage)
        self.index=self.jobs.index;self.addCleanup(self.jobs.close)

    def wait(self,state=None):
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            current=self.jobs.status()['state']
            if state is not None and current==state:return
            if state is None and self.jobs.thread is not None and not self.jobs.thread.is_alive():return
            time.sleep(.01)
        self.fail('Owned audio job did not reach '+str(state)+': '+str(self.jobs.status()))

    def test_completed_batch_reuses_fresh_markers_after_explicit_restart(self):
        with self.supplied():self.jobs.start();self.wait()
        self.assertEqual(self.jobs.status()['state'],'completed');self.assertEqual(self.jobs.status()['indexed'],1)
        calls=self.encoder.calls
        with self.supplied():self.jobs.start();self.wait()
        self.assertEqual((self.jobs.status()['target'],self.jobs.status()['reused']),(0,1))
        self.assertEqual(self.encoder.calls,calls)

    def test_item_progress_is_uncommitted_and_cleared_on_cancel_restart_and_save(self):
        self.seed()
        with self.index.store.connect() as db:db.execute('UPDATE ai_audio_direct_sources SET source_revision=?',('0'*64,))
        previous=self.snapshot();ready=threading.Event();proceed=threading.Event();encode=self.encoder.encode
        def paused(operation,window):
            if window.start_ms==30000:
                ready.set()
                if not proceed.wait(3):raise RuntimeError('generated progress wait timed out')
            return encode(operation,window)
        with self.supplied(),patch.object(self.encoder,'encode',side_effect=paused):
            try:
                self.jobs.start();self.assertTrue(ready.wait(3));status=self.jobs.status()
                self.assertEqual((status['state'],status['processed'],status['indexed']),('running',0,0))
                self.assertEqual(status['item_progress'],{'item_id':self.item,'prepared_ms':30000,'total_ms':None,'prepared_windows':1,'phase':'encoding','item_title':self.path.name})
                status['item_progress']['prepared_ms']=0
                self.assertEqual(self.jobs.status()['item_progress']['prepared_ms'],30000)
                self.assertTrue(self.jobs.cancel()['cancel_requested']);self.assertEqual(self.snapshot(),previous)
            finally:proceed.set()
            self.wait()
        self.assertIsNone(self.jobs.status()['item_progress']);self.assertEqual(self.snapshot(),previous)
        with self.supplied():self.jobs.start();self.wait()
        self.assertEqual((self.jobs.status()['state'],self.jobs.status()['indexed']),('completed',1))
        self.assertIsNone(self.jobs.status()['item_progress'])

    def test_explicit_batch_rebuilds_a_corrupt_item_instead_of_reusing_its_marker(self):
        self.seed()
        with self.index.store.connect() as db:db.execute('DELETE FROM ai_audio_direct_windows WHERE item_id=? AND ordinal=1',(self.item,))
        before=self.encoder.calls
        with self.supplied():self.jobs.start();self.wait()
        self.assertEqual((self.jobs.status()['state'],self.jobs.status()['reused'],self.jobs.status()['indexed']),('completed',0,1))
        self.assertEqual(self.encoder.calls-before,2)
        self.assertTrue(self.index.fresh(self.item,self.revision));self.assertEqual(len(self.snapshot()[1]),2)

    def test_bounded_batches_progress_beyond_already_indexed_first_item(self):
        (self.media/'second.wav').write_bytes(fixture.wav_bytes())
        self.catalog.index.scan(self.root);self.catalog.sync_index()
        with self.supplied():
            self.jobs.start(limit=1);self.wait()
            self.assertEqual(self.jobs.status()['remaining_candidates'],1)
            self.jobs.start(limit=1);self.wait()
            self.assertEqual((self.jobs.status()['target'],self.jobs.status()['reused']),(1,1))
            self.jobs.start(limit=1);self.wait()
            self.assertEqual((self.jobs.status()['target'],self.jobs.status()['reused']),(0,2))

    def test_cancel_while_image_owner_busy_starts_no_audio_inference(self):
        with self.vision_lock,self.supplied():
            self.vision.resident=True;self.jobs.start();self.wait('waiting')
            self.assertTrue(self.jobs.cancel()['cancel_requested']);self.wait()
            self.assertEqual(self.jobs.status()['state'],'cancelled')
            self.assertEqual(self.encoder.calls,0);self.assertTrue(self.vision.resident)

    def test_failed_current_item_preserves_previous_complete_revision(self):
        self.seed()
        with self.index.store.connect() as db:db.execute("UPDATE ai_audio_direct_sources SET source_revision=?",('0'*64,))
        previous=self.snapshot()
        def cancelled(*args):self.jobs.cancel();return [0,1,0]
        with self.supplied(),patch.object(self.encoder,'encode',side_effect=cancelled):
            self.jobs.start();self.wait()
        self.assertEqual(self.jobs.status()['state'],'cancelled');self.assertEqual(self.snapshot(),previous)
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_cancel_after_copy_before_commit_keeps_previous_publication(self):
        self.seed()
        with self.index.store.connect() as db:db.execute("UPDATE ai_audio_direct_sources SET source_revision=?",('0'*64,))
        previous=self.snapshot();ready=threading.Event();proceed=threading.Event();lock=threading.Lock();job=self.jobs
        class Gate:
            def __enter__(self):
                # Planning also enters the gate; pause only after copying the item.
                if threading.current_thread() is job.thread and job.status()['state']=='running':
                    ready.set()
                    if not proceed.wait(3):raise RuntimeError('test release timed out')
                lock.acquire()
            def __exit__(self,*args):lock.release()
        self.jobs.publication_guard=Gate()
        with self.supplied():
            try:
                self.jobs.start();self.assertTrue(ready.wait(3))
                self.assertTrue(self.jobs.cancel()['cancel_requested'])
            finally:proceed.set()
            self.wait()
        self.assertEqual(self.jobs.status()['state'],'cancelled')
        self.assertEqual(self.snapshot(),previous)
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_cancel_after_final_commit_is_rejected(self):
        self.seed()
        with self.index.store.connect() as db:db.execute("UPDATE ai_audio_direct_sources SET source_revision=?",('0'*64,))
        previous=self.snapshot();ready=threading.Event();proceed=threading.Event();connect=self.index.store.connect
        @contextmanager
        def paused():
            with connect() as db:
                yield db
                if threading.current_thread() is self.jobs.thread and self.jobs.status()['state']=='completed':
                    ready.set()
                    if not proceed.wait(3):raise RuntimeError('test release timed out')
        with self.supplied(),patch.object(self.encoder,'encode',return_value=[0,1,0]),patch.object(self.index.store,'connect',side_effect=paused):
            try:
                self.jobs.start();self.assertTrue(ready.wait(3))
                self.assertFalse(self.jobs.cancel()['cancel_requested'])
            finally:proceed.set()
            self.wait()
        self.assertEqual((self.jobs.status()['state'],self.jobs.status()['indexed']),('completed',1))
        self.assertNotEqual(self.snapshot(),previous)

    def test_cancel_after_partial_commit_preserves_completed_item_and_resumes(self):
        (self.media/'second.wav').write_bytes(fixture.wav_bytes())
        self.catalog.index.scan(self.root);self.catalog.sync_index()
        ready=threading.Event();proceed=threading.Event();connect=self.index.store.connect
        @contextmanager
        def paused():
            with connect() as db:
                yield db
                if threading.current_thread() is self.jobs.thread and self.jobs.status()['indexed']==1:
                    ready.set()
                    if not proceed.wait(3):raise RuntimeError('test release timed out')
        with self.supplied(),patch.object(self.index.store,'connect',side_effect=paused):
            try:
                self.jobs.start(limit=2);self.assertTrue(ready.wait(3))
                self.assertTrue(self.jobs.cancel()['cancel_requested'])
            finally:proceed.set()
            self.wait()
        self.assertEqual((self.jobs.status()['state'],self.jobs.status()['indexed']),('cancelled',1))
        self.assertEqual(len(self.snapshot()[0]),1)
        with self.supplied():self.jobs.start(limit=2);self.wait()
        self.assertEqual((self.jobs.status()['reused'],self.jobs.status()['indexed']),(1,1))

    def test_silent_item_commits_success_without_encoder_and_is_reused(self):
        silent=[fixture.PCMWindow(0,30000,b'\0'*(480000*4))]
        with self.supplied(silent),patch.object(self.encoder,'encode',side_effect=AssertionError('silent window must not infer')):
            self.jobs.start();self.wait()
            self.assertEqual((self.jobs.status()['state'],self.jobs.status()['indexed']),('completed',1))
            self.assertEqual(len(self.snapshot()[1]),0)
            self.jobs.start();self.wait()
            self.assertEqual((self.jobs.status()['target'],self.jobs.status()['reused']),(0,1))

    def test_scope_changes_before_publication_are_reported_and_not_saved(self):
        def changed(*args):self.catalog.update([self.item],{'favorite':True});return [1,0,0]
        with self.supplied(),patch.object(self.encoder,'encode',side_effect=changed):
            self.jobs.start();self.wait()
        self.assertEqual(self.jobs.status()['error_code'],'scope_changed');self.assertEqual(self.snapshot(),[[],[]])

    def test_query_and_index_reject_busy_owner_and_swap_residency(self):
        self.seed()
        with self.vision_lock:
            self.vision.resident=True
            with self.assertRaises(AIBusy):self.jobs.search('audio')
        result=self.jobs.search('audio')
        self.assertEqual(result['total'],1);self.assertFalse(self.vision.resident);self.assertTrue(self.encoder.resident)
        with self.vision_lock:
            self.assertFalse(self.encoder.resident);self.vision.resident=True

    def test_close_cancels_waiting_job_and_permanently_closes_own_encoder(self):
        with self.vision_lock,self.supplied():
            self.jobs.start();self.wait('waiting')
            closing=threading.Thread(target=self.jobs.close);closing.start();closing.join(2)
            closed_without_waiting_for_image=not closing.is_alive()
        closing.join(3)
        self.assertTrue(closed_without_waiting_for_image)
        self.assertTrue(self.encoder.closed);self.assertTrue(self.jobs.status()['closed'])

    def test_idle_release_stops_only_its_resident_worker(self):
        self.encoder.resident=True;self.jobs.last_used=time.monotonic()-3;self.jobs.configure(idle_release_seconds=1)
        deadline=time.monotonic()+2
        while self.encoder.resident and time.monotonic()<deadline:time.sleep(.01)
        self.assertFalse(self.encoder.resident);self.assertEqual(self.vision.releases,0)


    def test_idle_release_survives_transient_peer_release_failure(self):
        self.encoder.resident=True;self.jobs.last_used=time.monotonic()-3
        acquire=self.jobs.inference.acquire;attempts=[];errors=[]
        def transient(*args,**kwargs):
            attempts.append(1)
            if len(attempts)==1:raise AIUnavailable('generated transient peer release failure')
            return acquire(*args,**kwargs)
        with patch.object(self.jobs.inference,'acquire',side_effect=transient),patch('threading.excepthook',side_effect=lambda args:errors.append(args.exc_value)):
            self.jobs.configure(idle_release_seconds=1)
            deadline=time.monotonic()+2
            while self.encoder.resident and time.monotonic()<deadline:time.sleep(.01)
            self.assertFalse(self.encoder.resident,repr(errors))
            self.assertGreaterEqual(len(attempts),2);self.assertEqual(errors,[])
            self.assertTrue(self.jobs.idle_thread.is_alive());self.assertFalse(self.group.lock.locked())


if __name__=='__main__':unittest.main()
