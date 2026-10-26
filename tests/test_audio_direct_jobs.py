"""Owned job/query and image/audio handover with supplied CPU encoders only."""
from pathlib import Path
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


if __name__=='__main__':unittest.main()
