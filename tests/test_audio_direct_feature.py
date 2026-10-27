"""Audio lazy owner shutdown with generated data and a supplied CPU encoder."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import sys
import threading
import time
import unittest
from unittest.mock import PropertyMock,patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_audio_direct_index as fixture
from test_audio_direct_jobs import Encoder
from ai_process import AIUnavailable
from ai_profiles import DEFAULT_PROFILE
from audio_direct_feature import AudioDirectFeature
from audio_direct_index import AudioDirectIndex
from inference_ownership import InferenceOwnership


class AudioFeatureCloseTests(unittest.TestCase):
    def setUp(self):
        fixture.DirectAudioIndexTests.setUp(self)
        group=InferenceOwnership();vision=Encoder();group.for_encoder(vision)
        image=SimpleNamespace(profile=replace(DEFAULT_PROFILE,dimension=3),encoder=vision,inference_group=group)
        self.created=[]
        def factory(profile):
            encoder=Encoder();encoder.profile=profile;self.created.append(encoder);return encoder
        self.feature=AudioDirectFeature(self.catalog,image,encoder_factory=factory,stage_parent=self.stage)
        self.addCleanup(self.feature.close)

    def test_close_interrupts_initialization_waiting_for_catalog_guard(self):
        entered=threading.Event();errors=[]
        def initialize():
            entered.set()
            try:self.feature._ensure()
            except Exception as error:errors.append(error)
        with self.catalog._guard:
            opening=threading.Thread(target=initialize);opening.start();self.assertTrue(entered.wait(1))
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
            try:AudioDirectIndex(self.catalog,self.created[0],init_cancel=cancel)
            except Exception as error:errors.append(error)
        with self.catalog.writer_fence.pause():
            opening=threading.Thread(target=initialize);opening.start();self.assertTrue(started.wait(1))
            deadline=time.monotonic()+2
            while not self.catalog._guard.locked() and time.monotonic()<deadline:time.sleep(.005)
            self.assertTrue(self.catalog._guard.locked())
            cancel.set();opening.join(1)
            self.assertFalse(opening.is_alive())
        self.assertEqual(len(errors),1);self.assertIsInstance(errors[0],InterruptedError)

    def test_close_interrupts_writer_fence_wait_after_admission_race(self):
        entered=threading.Event();errors=[]
        def initialize():
            entered.set()
            try:self.feature._ensure()
            except Exception as error:errors.append(error)
        # The snapshot pause can start just after the feature's fast paused
        # check. Force that ordering while retaining the real fence behavior.
        with self.catalog.writer_fence.pause(),patch.object(type(self.catalog.writer_fence),'paused',new_callable=PropertyMock,return_value=False):
            opening=threading.Thread(target=initialize);opening.start();self.assertTrue(entered.wait(1))
            deadline=time.monotonic()+2
            while not self.catalog._guard.locked() and time.monotonic()<deadline:time.sleep(.005)
            self.assertTrue(self.catalog._guard.locked())
            closing=threading.Thread(target=self.feature.close);closing.start();closing.join(1)
            self.assertFalse(closing.is_alive())
            opening.join(1);self.assertFalse(opening.is_alive())
        self.assertEqual(len(errors),1);self.assertIsInstance(errors[0],AIUnavailable)
        self.assertTrue(self.created[0].closed)


if __name__=='__main__':unittest.main()
