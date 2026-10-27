"""Lazy video feature lifecycle with generated media and a CPU test encoder."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import shutil
import sys
import threading
import time
import unittest

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_video_direct_index as fixture
from ai_profiles import DEFAULT_PROFILE,video_profile_for
from ai_process import AIUnavailable
from inference_ownership import InferenceOwnership
from video_direct_feature import VideoDirectFeature
from video_direct_index import VideoDirectIndex


class Encoder:
    available=True
    def __init__(self,profile):
        self.profile=profile;self.resident=False;self.closed=False;self.calls=[]
    def encode(self,kind,value):
        self.resident=True;self.calls.append(kind);return [1.0,0.0,0.0]
    def release(self):
        self.resident=False;return {'released':True,'resident':False}
    def close(self):self.closed=True;self.resident=False


class VideoFeatureTests(unittest.TestCase):
    def setUp(self):
        fixture.RealVideoIndexTests.setUp(self)
        shutil.copyfile(fixture.fixture.VideoWindowTests.path,self.media/'generated.mp4')
        self.catalog.index.scan(self.root);self.catalog.sync_index()
        self.stage=self.base/'stages';self.stage.mkdir()
        self.base_profile=replace(DEFAULT_PROFILE,dimension=3)
        self.vision=Encoder(self.base_profile);self.group=InferenceOwnership()
        self.group.for_encoder(self.vision)
        self.image=SimpleNamespace(profile=self.base_profile,encoder=self.vision,inference_group=self.group,_idle_seconds=0)
        self.created=[]
        def factory(profile):
            encoder=Encoder(profile);self.created.append(encoder);return encoder
        self.feature=VideoDirectFeature(self.catalog,self.image,encoder_factory=factory,stage_parent=self.stage)
        self.addCleanup(self.feature.close)

    def wait(self):
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            owner=self.feature.owner
            if owner is not None and owner.thread is not None and not owner.thread.is_alive():return
            time.sleep(.01)
        self.fail('Video job did not finish: '+str(self.feature.status()))

    def test_status_and_invalid_requests_are_lazy(self):
        path=video_profile_for(self.base_profile).store_path(self.catalog.path)
        self.assertFalse(path.exists());self.assertFalse(self.feature.status()['initialized'])
        for body in ({},{'consent':False},{'consent':True,'limit':0},{'consent':True,'conditions':{'kind':'image'}}):
            with self.subTest(body=body),self.assertRaises(ValueError):self.feature.start(body)
        with self.assertRaises(ValueError):self.feature.search(' ',view='all')
        self.assertFalse(path.exists());self.assertEqual(self.created[0].calls,[])
        self.assertFalse(self.feature.cancel()['cancel_requested'])

    def test_explicit_start_search_resume_release_and_close(self):
        self.feature.start({'consent':True,'conditions':{'root_ids':[self.root]},'limit':1});self.wait()
        self.assertEqual(self.feature.status()['indexed'],1)
        result=self.feature.search('generated',root_ids=[self.root])
        self.assertEqual(result['total'],1)
        self.assertEqual((result['items'][0]['video_match_ms'],result['items'][0]['video_match_end_ms']),(0,3300))
        self.feature.start({'consent':True});self.wait()
        self.assertEqual(self.feature.status()['reused'],1)
        self.assertTrue(self.feature.release()['released'])
        self.feature.close();self.assertTrue(self.created[0].closed)
        with self.assertRaises(AIUnavailable):self.feature.search('generated')

    def test_unavailable_model_and_uninitialized_close(self):
        self.created[0].available=False
        self.assertFalse(self.feature.status()['available'])
        with self.assertRaises(AIUnavailable):self.feature.start({'consent':True})
        self.assertFalse(self.feature.status()['initialized'])
        self.feature.close();self.assertTrue(self.created[0].closed)

    def test_unsupported_image_owner_is_safe(self):
        feature=VideoDirectFeature(self.catalog,SimpleNamespace())
        self.addCleanup(feature.close)
        self.assertFalse(feature.status()['supported'])
        with self.assertRaises(AIUnavailable):feature.start({'consent':True})

    def test_close_interrupts_initialization_waiting_for_catalog_guard(self):
        entered=threading.Event();errors=[]
        def initialize():
            entered.set()
            try:self.feature._ensure()
            except Exception as error:errors.append(error)
        with self.catalog._guard:
            opening=threading.Thread(target=initialize);opening.start();self.assertTrue(entered.wait(1))
            # Wait until initialization owns its lock and is blocked at the boundary.
            deadline=time.monotonic()+2
            while not self.feature.init_lock.locked() and time.monotonic()<deadline:time.sleep(.005)
            self.assertTrue(self.feature.init_lock.locked())
            closing=threading.Thread(target=self.feature.close);closing.start();closing.join(1)
            try:self.assertFalse(closing.is_alive())
            finally:opening.join(1)
        opening.join(2);closing.join(2)
        self.assertEqual(len(errors),1);self.assertIsInstance(errors[0],AIUnavailable)
        self.assertTrue(self.created[0].closed)

    def test_initialization_writer_fence_wait_is_cancellable(self):
        cancel=threading.Event();started=threading.Event();errors=[]
        def initialize():
            started.set()
            try:VideoDirectIndex(self.catalog,self.created[0],init_cancel=cancel)
            except Exception as error:errors.append(error)
        with self.catalog.writer_fence.pause():
            opening=threading.Thread(target=initialize);opening.start();self.assertTrue(started.wait(1))
            # Acquiring the catalog guard proves the thread is in the fenced wait.
            deadline=time.monotonic()+2
            while not self.catalog._guard.locked() and time.monotonic()<deadline:time.sleep(.005)
            self.assertTrue(self.catalog._guard.locked())
            cancel.set();opening.join(1)
            self.assertFalse(opening.is_alive())
        self.assertEqual(len(errors),1);self.assertIsInstance(errors[0],InterruptedError)


if __name__=='__main__':unittest.main()
