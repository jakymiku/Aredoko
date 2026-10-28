"""Owned job/query and image/video handover with generated media and CPU encoders only."""
from pathlib import Path
from contextlib import contextmanager
import sys
import shutil
import threading
import time
import unittest
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_video_direct_index as fixture
from video_direct_jobs import VideoDirectJobs
from inference_ownership import InferenceOwnership
from ai_search import AIBusy
from ai_score_spool import SearchCancelled


class Encoder(fixture.Encoder):
    available=True
    def __init__(self):self.resident=False;self.calls=0;self.releases=0;self.closed=False
    def encode(self,*args):self.calls+=1;self.resident=True;return [1,0,0]
    def release(self):self.releases+=1;self.resident=False;return {'released':True,'resident':False}
    def close(self):self.closed=True;self.resident=False


class DirectVideoJobTests(unittest.TestCase):
    supplied=fixture.SuppliedIndexTests.supplied
    snapshot=fixture.SuppliedIndexTests.snapshot
    seed=fixture.SuppliedIndexTests.seed
    def setUp(self):
        fixture.SuppliedIndexTests.setUp(self)
        self.encoder=Encoder();self.vision=Encoder();self.group=InferenceOwnership()
        self.vision_lock=self.group.for_encoder(self.vision)
        self.jobs=VideoDirectJobs(self.catalog,self.encoder,inference=self.group.for_encoder(self.encoder,role='video'),
                                  reader=self.reader,stage_parent=self.stage)
        self.index=self.jobs.index;self.addCleanup(self.jobs.close)

    def wait(self,state=None):
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            current=self.jobs.status()['state']
            if state is not None and current==state:return
            if state is None and self.jobs.thread is not None and not self.jobs.thread.is_alive():return
            time.sleep(.01)
        self.fail('Owned video job did not reach '+str(state)+': '+str(self.jobs.status()))

    def test_completed_batch_reuses_fresh_markers_after_explicit_restart(self):
        with self.supplied():self.jobs.start();self.wait()
        self.assertEqual(self.jobs.status()['state'],'completed');self.assertEqual(self.jobs.status()['indexed'],1)
        calls=self.encoder.calls
        with self.supplied():self.jobs.start();self.wait()
        self.assertEqual((self.jobs.status()['target'],self.jobs.status()['reused']),(0,1))
        self.assertEqual(self.encoder.calls,calls)

    def test_partial_item_progress_survives_observation_but_not_cancel_or_restart(self):
        self.seed()
        with self.index.store.connect() as db:db.execute('UPDATE ai_video_direct_sources SET source_revision=?',('0'*64,))
        previous=self.snapshot();ready=threading.Event();proceed=threading.Event();encode=self.encoder.encode
        def paused(operation,window):
            if window.start_ms==16000:
                ready.set()
                if not proceed.wait(3):raise RuntimeError('generated progress wait timed out')
            return encode(operation,window)
        with self.supplied(),patch.object(self.encoder,'encode',side_effect=paused):
            try:
                self.jobs.start();self.assertTrue(ready.wait(3));status=self.jobs.status()
                self.assertEqual((status['state'],status['processed'],status['indexed']),('running',0,0))
                self.assertEqual(status['item_progress'],{'item_id':self.item,'prepared_ms':16000,'total_ms':17500,'prepared_windows':1,'phase':'encoding'})
                status['item_progress']['prepared_ms']=0
                self.assertEqual(self.jobs.status()['item_progress']['prepared_ms'],16000)
                self.assertTrue(self.jobs.cancel()['cancel_requested']);self.assertEqual(self.snapshot(),previous)
            finally:proceed.set()
            self.wait()
        self.assertEqual(self.jobs.status()['state'],'cancelled');self.assertIsNone(self.jobs.status()['item_progress'])
        self.assertEqual(self.snapshot(),previous)
        with self.supplied():self.jobs.start();self.wait()
        status=self.jobs.status();self.assertEqual((status['state'],status['indexed']),('completed',1))
        self.assertIsNone(status['item_progress']);self.assertEqual(list(self.stage.iterdir()),[])

    def test_next_explicit_batch_repairs_damaged_complete_marker(self):
        with self.supplied():self.jobs.start();self.wait()
        with self.index.store.connect() as db:db.execute('DELETE FROM ai_video_direct_windows WHERE ordinal=1')
        self.assertFalse(self.index.fresh(self.item,self.revision));calls=self.encoder.calls
        with self.supplied():self.jobs.start();self.wait()
        self.assertEqual((self.jobs.status()['indexed'],self.jobs.status()['reused']),(1,0))
        self.assertGreater(self.encoder.calls,calls)
        self.assertTrue(self.index.fresh(self.item,self.revision))

    def test_bounded_batches_progress_beyond_already_indexed_first_item(self):
        shutil.copyfile(self.path,self.media/'second.mp4')
        self.catalog.index.scan(self.root);self.catalog.sync_index()
        with self.supplied():
            self.jobs.start(limit=1);self.wait()
            self.assertEqual(self.jobs.status()['remaining_candidates'],1)
            self.jobs.start(limit=1);self.wait()
            self.assertEqual((self.jobs.status()['target'],self.jobs.status()['reused']),(1,1))
            self.jobs.start(limit=1);self.wait()
            self.assertEqual((self.jobs.status()['target'],self.jobs.status()['reused']),(0,2))

    def test_cancel_while_image_owner_busy_starts_no_video_inference(self):
        with self.vision_lock,self.supplied():
            self.vision.resident=True;self.jobs.start();self.wait('waiting')
            self.assertTrue(self.jobs.cancel()['cancel_requested']);self.wait()
            self.assertEqual(self.jobs.status()['state'],'cancelled')
            self.assertEqual(self.encoder.calls,0);self.assertTrue(self.vision.resident)

    def test_failed_current_item_preserves_previous_complete_revision(self):
        self.seed()
        with self.index.store.connect() as db:db.execute("UPDATE ai_video_direct_sources SET source_revision=?",('0'*64,))
        previous=self.snapshot()
        def cancelled(*args):self.jobs.cancel();return [0,1,0]
        with self.supplied(),patch.object(self.encoder,'encode',side_effect=cancelled):
            self.jobs.start();self.wait()
        self.assertEqual(self.jobs.status()['state'],'cancelled');self.assertEqual(self.snapshot(),previous)
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_cancel_before_commit_keeps_previous_publication(self):
        self.seed()
        with self.index.store.connect() as db:db.execute("UPDATE ai_video_direct_sources SET source_revision=?",('0'*64,))
        previous=self.snapshot();ready=threading.Event();proceed=threading.Event();lock=threading.Lock()
        job=self.jobs
        class Gate:
            def __enter__(self):
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

    def test_cancel_after_final_commit_is_rejected(self):
        self.seed()
        with self.index.store.connect() as db:db.execute("UPDATE ai_video_direct_sources SET source_revision=?",('0'*64,))
        previous=self.snapshot();ready=threading.Event();proceed=threading.Event()
        connect=self.index.store.connect
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
        shutil.copyfile(self.path,self.media/'second.mp4')
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

    def test_scope_changes_before_publication_are_reported_and_not_saved(self):
        def changed(*args):self.catalog.update([self.item],{'favorite':True});return [1,0,0]
        with self.supplied(),patch.object(self.encoder,'encode',side_effect=changed):
            self.jobs.start();self.wait()
        self.assertEqual(self.jobs.status()['error_code'],'scope_changed');self.assertEqual(self.snapshot(),[[],[]])

    def test_query_and_index_reject_busy_owner_and_swap_residency(self):
        self.seed()
        with self.vision_lock:
            self.vision.resident=True
            with self.assertRaises(AIBusy):self.jobs.search('video')
        result=self.jobs.search('video')
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

    def test_real_generated_video_end_to_end_with_scoped_search(self):
        self.jobs.start(limit=1);self.wait()
        self.assertEqual(self.jobs.status()['state'],'completed')
        result=self.jobs.search('generated',root_ids=[self.root])
        self.assertEqual(result['total'],1)
        self.assertEqual((result['items'][0]['video_match_ms'],result['items'][0]['video_match_end_ms']),(0,3300))
        self.assertEqual(self.jobs.search('generated',view='favorites')['total'],0)
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_index_scope_and_search_cancellation(self):
        shutil.copyfile(self.path,self.media/'second.mp4')
        self.catalog.index.scan(self.root);self.catalog.sync_index()
        self.catalog.update([self.item],{'favorite':True})
        with self.supplied():
            self.jobs.start({'view':'favorites'});self.wait()
        self.assertEqual((self.jobs.status()['candidate_total'],self.jobs.status()['indexed']),(1,1))
        with self.assertRaises(SearchCancelled):self.jobs.search('video',cancelled=lambda:True)
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_source_changes_during_index_keep_previous_publication(self):
        self.seed()
        with self.index.store.connect() as db:db.execute("UPDATE ai_video_direct_sources SET source_revision=?",('0'*64,))
        previous=self.snapshot()
        def changed(*args):
            self.path.write_bytes(b'changed generated video')
            return [1,0,0]
        with self.supplied(),patch.object(self.encoder,'encode',side_effect=changed):
            self.jobs.start();self.wait()
        self.assertEqual(self.jobs.status()['state'],'failed')
        self.assertIsNone(self.jobs.status()['item_progress'])
        self.assertEqual(self.snapshot(),previous)
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_idle_release_stops_only_its_resident_worker(self):
        self.encoder.resident=True;self.jobs.last_used=time.monotonic()-3;self.jobs.configure(idle_release_seconds=1)
        deadline=time.monotonic()+2
        while self.encoder.resident and time.monotonic()<deadline:time.sleep(.01)
        self.assertFalse(self.encoder.resident);self.assertEqual(self.vision.releases,0)


if __name__=='__main__':unittest.main()
