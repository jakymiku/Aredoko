"""CPU-only ownership handover; no model, worker, GPU or UI is executed."""
from pathlib import Path
import sys
import threading
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from inference_ownership import InferenceOwnership


class Encoder:
    def __init__(self):self.resident=False;self.releases=0
    def release(self):self.releases+=1;self.resident=False


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.group=InferenceOwnership();self.image=Encoder();self.audio=Encoder()
        self.left=self.group.for_encoder(self.image);self.right=self.group.for_encoder(self.audio)

    def test_handover_releases_the_other_worker_before_entering(self):
        with self.left:self.image.resident=True
        with self.right:
            self.assertFalse(self.image.resident);self.audio.resident=True
        with self.left:
            self.assertFalse(self.audio.resident);self.image.resident=True
        self.assertEqual((self.image.releases,self.audio.releases),(1,1))

    def test_same_owner_does_not_unload_its_own_resident_worker(self):
        self.image.resident=True
        with self.left:pass
        with self.left:self.assertTrue(self.image.resident)
        self.assertEqual(self.image.releases,0)

    def test_busy_acquisition_does_not_touch_the_other_worker(self):
        with self.left:
            self.image.resident=True
            self.assertFalse(self.right.acquire(blocking=False))
            self.assertTrue(self.image.resident);self.assertEqual(self.image.releases,0)

    def test_failed_release_does_not_admit_next_owner_or_leave_lock_held(self):
        self.image.resident=True
        def failed():raise RuntimeError('generated worker is busy')
        self.image.release=failed
        with self.assertRaisesRegex(RuntimeError,'busy'):self.right.acquire()
        self.assertFalse(self.right.locked());self.assertTrue(self.image.resident)
        self.image.release=lambda:setattr(self.image,'resident',False)
        with self.right:self.assertFalse(self.image.resident)

    def test_noop_release_with_resident_worker_is_rejected(self):
        self.image.resident=True;self.image.release=lambda:None
        with self.assertRaisesRegex(RuntimeError,'still resident'):self.right.acquire()
        self.assertFalse(self.right.locked())

    def test_registration_is_explicit_bounded_and_reuses_identical_encoder(self):
        self.assertIs(self.group.for_encoder(self.image),self.left)
        with self.assertRaises(ValueError):self.group.for_encoder(Encoder())
        with self.assertRaises(ValueError):InferenceOwnership().for_encoder(object())

    def test_cross_thread_release_is_rejected(self):
        errors=[]
        def release():
            try:self.left.release()
            except RuntimeError as error:errors.append(error)
        with self.left:
            thread=threading.Thread(target=release);thread.start();thread.join(1)
            self.assertEqual(len(errors),1);self.assertTrue(self.left.locked())


if __name__=='__main__':unittest.main()
