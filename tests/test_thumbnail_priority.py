"""Visible work precedes queued speculation; shared requests retain ownership."""
import threading
import unittest
from unittest.mock import patch
import test_thumbnail_cache as fixtures
from thumbnail_cache import DecodeBudget, ThumbnailCancelled


class PriorityTests(unittest.TestCase):
    setUp = fixtures.ThumbnailTests.setUp
    scan = fixtures.ThumbnailTests.scan
    read = fixtures.ThumbnailTests.read

    def exercise_queue(self, promote=False, demote=False):
        entered = {edge: threading.Event() for edge in (128, 256, 512, 1024)}
        release = {edge: threading.Event() for edge in entered}
        original = self.owner._build; outcomes = {}; threads = []
        cancel = threading.Event()
        def build(item, kind, revision, edge, stopped):
            entered[edge].set()
            if not release[edge].wait(4): raise AssertionError('test decoder release timed out')
            return original(item, kind, revision, edge, stopped)
        def run(name, edge, priority, cancelled=lambda: False):
            try: outcomes[name] = self.read(edge=edge, priority=priority, cancelled=cancelled)
            except Exception as error: outcomes[name] = error
        def start(name, edge, priority, cancelled=lambda: False):
            t = threading.Thread(target=run, args=(name, edge, priority, cancelled)); threads.append(t); t.start()
        with patch.object(self.owner, '_build', side_effect=build):
            try:
                start('a', 128, 'visible'); start('b', 256, 'visible')
                self.assertTrue(entered[128].wait(3)); self.assertTrue(entered[256].wait(3))
                start('nearby', 512, 'nearby')
                with self.owner.changed:
                    self.assertTrue(self.owner.changed.wait_for(lambda: len(self.owner.jobs) == 3, 3))
                start('visible', 1024, 'visible')
                with self.owner.changed:
                    self.assertTrue(self.owner.changed.wait_for(lambda: len(self.owner.jobs) == 4, 3))
                if promote:
                    start('promoted', 512, 'visible', cancel.is_set)
                    with self.owner.changed:
                        self.assertTrue(self.owner.changed.wait_for(lambda: any(j.waiters == 2 and j.visible_waiters == 1 for j in self.owner.jobs.values()), 3))
                    if demote:
                        cancel.set()
                        with self.owner.changed:
                            self.assertTrue(self.owner.changed.wait_for(lambda: not any(j.waiters == 2 for j in self.owner.jobs.values()), 3))
                first, second = (512, 1024) if promote and not demote else (1024, 512)
                release[128].set()
                self.assertTrue(entered[first].wait(3)); self.assertFalse(entered[second].is_set())
                release[first].set(); self.assertTrue(entered[second].wait(3))
            finally:
                for event in release.values(): event.set()
                for thread in threads: thread.join(5)
        self.assertFalse(any(t.is_alive() for t in threads))
        for name, value in outcomes.items():
            if name == 'promoted' and demote: self.assertIsInstance(value, ThumbnailCancelled)
            else: self.assertIsInstance(value, bytes, (name, value))
        self.assertEqual(self.owner.jobs, {}); self.assertEqual(self.owner.active, 0)

    def test_visible_overtakes_older_nearby(self): self.exercise_queue()
    def test_visible_waiter_promotes_shared_queued_work(self): self.exercise_queue(promote=True)
    def test_cancelled_visible_waiter_demotes_without_cancelling_nearby(self): self.exercise_queue(promote=True, demote=True)

    def test_cancelled_and_failed_decode_reservations_are_released(self):
        budget = DecodeBudget(100)
        with self.assertRaises(OSError):
            with budget.reserve(60, lambda: False): raise OSError('generated decoder failure')
        self.assertEqual(budget.used, 0)
        cancel = threading.Event(); outcomes = []
        def queued():
            try:
                with budget.reserve(50, cancel.is_set): outcomes.append('unexpected decode')
            except ThumbnailCancelled: outcomes.append('cancelled')
        with budget.reserve(1000, lambda: False):
            self.assertEqual(budget.used, 100)
            thread = threading.Thread(target=queued); thread.start(); cancel.set(); thread.join(3)
            self.assertFalse(thread.is_alive()); self.assertEqual(outcomes, ['cancelled'])
        self.assertEqual(budget.used, 0)
        budget.close()
        with self.assertRaises(ThumbnailCancelled):
            with budget.reserve(1, lambda: False): self.fail('closed budget admitted work')

    def test_unknown_priority_is_not_treated_as_visible(self):
        for value in ('urgent', '', None, True):
            with self.assertRaises(ValueError): self.read(priority=value)
