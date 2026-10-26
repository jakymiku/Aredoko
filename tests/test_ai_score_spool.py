"""CPU-only exact oracle, paging and bounded workspace lifecycle regressions."""
import gc
import math
from pathlib import Path
import random
import sqlite3
import sys
import tempfile
import threading
import tracemalloc
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from ai_ranking import fuse_modalities
from ai_result_groups import boundary
from ai_score_spool import ScoreSpool, ScoreSpoolError, SearchCancelled


def exact(rows):
    return [(item, value.hex()) for item, value in rows]


class ScoreSpoolTests(unittest.TestCase):
    def test_cancelled_enter_removes_workspace_without_waiting_for_gc(self):
        with tempfile.TemporaryDirectory() as parent:
            with self.assertRaises(SearchCancelled):
                with ScoreSpool(parent=parent,cancelled=lambda:True):
                    self.fail('Cancelled owner must not enter')
            self.assertEqual(list(Path(parent).iterdir()),[])

    def test_exact_fusion_with_missing_modes_global_spans_and_cross_batch_ties(self):
        rng = random.Random(20261018)
        scores = {}
        for item in range(1, 1030):
            modes = {mode: rng.choice([-.9, -.2, -0., .0, .3, .98])
                     for mode in ('text', 'cover') if rng.randrange(4)}
            scores[item] = modes or {'text': .3}
        for policy in ('max', 'mean-rrf'):
            with self.subTest(policy=policy), ScoreSpool() as spool:
                # Insertion order intentionally differs from item/mode order.
                for item in reversed(scores): spool.add(item, scores[item])
                spool.finalize(policy)
                self.assertEqual(exact(spool.ranked()), exact(fuse_modalities(scores, policy)))

    def test_constant_single_insufficient_pool_and_extreme_fallbacks(self):
        fixtures = [
            {}, {1: {'text': -0.}},
            {item: {'cover': .5, 'text': .5} for item in range(1, 600)},
            {1: {'text': .7, 'cover': .5}, 2: {'text': .7}, 3: {'text': .7}},
            {1: {'text': -1e308, 'cover': 1e308}, 2: {'text': 1e308, 'cover': -1e308}},
            {1: {'cover': .1, 'text': 0.}, 2: {'cover': .4, 'text': 0.}, 3: {'text': 0.}},
        ]
        for index, scores in enumerate(fixtures):
            for policy in ('max', 'mean-rrf'):
                with self.subTest(fixture=index, policy=policy), ScoreSpool() as spool:
                    for item, modes in scores.items(): spool.add(item, modes)
                    spool.finalize(policy)
                    self.assertEqual(exact(spool.ranked()), exact(fuse_modalities(scores, policy)))

    def test_three_mode_order_and_zero_weight_denominator_match_oracle(self):
        scores = {1: {'z': .6, 'a': .2, 'm': .5}, 2: {'a': -.3, 'z': .7, 'm': .5},
                  3: {'m': .5}, 4: {'m': .5, 'z': -.2}}
        with ScoreSpool() as spool:
            for item, modes in scores.items(): spool.add(item, modes)
            spool.finalize('mean-rrf')
            self.assertEqual(exact(spool.ranked()), exact(fuse_modalities(scores, 'mean-rrf')))

    def test_paging_literal_and_groups_match_global_oracle(self):
        scores = {item: {'text': .99 - item / 10000 if item < 5 else .3 - item / 10000}
                  for item in range(1, 610)}
        with ScoreSpool() as spool:
            for item, modes in scores.items():
                spool.add(item, modes, literal_hits=int(item % 2 == 1), literal_words=1,
                          payload={'revision': str(item), 'evidence': {'page': item}})
            spool.finalize('max')
            for literal in (False, True):
                ranked = [(item, value) for item, value in fuse_modalities(scores, 'max') if not literal or item % 2 == 1]
                for threshold in (None, .2, -1., 1.):
                    cut = boundary(ranked, 'cosine', threshold)
                    leading = sum(value >= cut for _, value in ranked) if cut is not None else len(ranked)
                    for group in ('all', 'leading', 'other'):
                        expected = [(item, value) for item, value in ranked if group == 'all' or
                                    group == 'leading' and (cut is None or value >= cut) or
                                    group == 'other' and cut is not None and value < cut]
                        for page in (0, 1, 4, 10, 10**100):
                            result = spool.page(page, 120, literal_only=literal, group_threshold=threshold, result_group=group)
                            self.assertEqual(result['total'], len(expected))
                            self.assertEqual(result['group_boundary'], cut)
                            self.assertEqual((result['leading_total'], result['other_total']), (leading, len(ranked) - leading))
                            self.assertEqual(exact(result['ranked']), exact(expected[page * 120:(page + 1) * 120]))
            self.assertEqual(spool.evidence([609, 1]), {
                1: {'revision': '1', 'evidence': {'page': 1}},
                609: {'revision': '609', 'evidence': {'page': 609}}})

    def test_rrf_groups_never_invent_cosine_boundary(self):
        with ScoreSpool() as spool:
            for item in range(1, 305): spool.add(item, {'text': .5})
            spool.finalize('mean-rrf')
            self.assertEqual(spool.page(result_group='other')['total'], 0)
            self.assertEqual(spool.page(result_group='leading')['total'], 304)
            with self.assertRaises(ValueError): spool.page(group_threshold=.5)

    def test_invalid_values_and_payload_never_publish_partial_items(self):
        with ScoreSpool() as spool:
            for modes in ({}, {'text': math.nan}, {'text': math.inf}, {'text': -math.inf},
                          {'text': True}, {'': .5}, {'x' * 33: .5}, {'text': '1'}, {'text': 10**400}):
                with self.subTest(modes=modes), self.assertRaises(ValueError): spool.add(1, modes)
            for kwargs in ({'literal_hits': 2, 'literal_words': 1}, {'literal_words': True},
                           {'payload': []}, {'payload': {'data': 'x' * 65_536}}, {'payload': {'x': math.nan}}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): spool.add(1, {'text': .5}, **kwargs)
            spool.add(1, {'text': .5}); spool.finalize()
            self.assertEqual(list(spool.ranked()), [(1, .5)])
            for kwargs in ({'page': True}, {'limit': 121}, {'literal_only': 1}, {'result_group': 'bad'}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): spool.page(**kwargs)
            for ids in ([True], [0], [2**63], list(range(1, 122)), '1'):
                with self.assertRaises(ValueError): spool.evidence(ids)

    def test_global_modality_names_remain_bounded(self):
        with ScoreSpool() as spool:
            for item in range(1, 17): spool.add(item, {str(item): .5})
            with self.assertRaises(ValueError): spool.add(17, {'extra': .5})
            spool.finalize('mean-rrf')
            self.assertEqual(len(list(spool.ranked())), 16)

    def test_cancel_in_ingestion_fusion_and_page_cleans_only_owned_directory(self):
        for stage in ('add', 'finalize', 'page'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmp:
                parent = Path(tmp); marker = parent / 'keep'; marker.write_bytes(b'keep')
                event = threading.Event()
                with self.assertRaises(SearchCancelled):
                    with ScoreSpool(parent=parent, cancelled=event.is_set) as spool:
                        owned = spool.path.parent
                        spool.add(1, {'text': .5})
                        if stage == 'page': spool.finalize()
                        event.set()
                        if stage == 'add': spool.add(2, {'text': .5})
                        elif stage == 'finalize': spool.finalize()
                        else: spool.page()
                self.assertFalse(owned.exists())
                self.assertEqual(list(parent.iterdir()), [marker])
                self.assertEqual(marker.read_bytes(), b'keep')

    def test_sqlite_progress_interrupt_is_translated_and_cleanup_survives(self):
        calls = 0
        armed = False
        def cancelled():
            nonlocal calls
            if armed: calls += 1
            return armed and calls >= 5
        with self.assertRaises(SearchCancelled) as raised:
            with ScoreSpool(cancelled=cancelled) as spool:
                owned = spool.path.parent
                for item in range(1, 1500): spool.add(item, {'text': item / 1500})
                armed = True
                spool.finalize('mean-rrf')
        self.assertFalse(owned.exists())
        self.assertIsInstance(raised.exception.__cause__, sqlite3.OperationalError)

    def test_database_capacity_duplicate_and_user_exception_close_handles(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            with self.assertRaises(ScoreSpoolError):
                with ScoreSpool(parent=parent, max_bytes=65_536) as spool:
                    for item in range(1, 1000): spool.add(item, {'text': .5}, payload={'data': 'x' * 4096})
            self.assertEqual(list(parent.iterdir()), [])
            with self.assertRaises(ScoreSpoolError):
                with ScoreSpool(parent=parent) as spool:
                    spool.add(1, {'text': .5}); spool.add(1, {'text': .7})
            self.assertEqual(list(parent.iterdir()), [])
            with self.assertRaisesRegex(RuntimeError, 'generated failure'):
                with ScoreSpool(parent=parent): raise RuntimeError('generated failure')
            self.assertEqual(list(parent.iterdir()), [])

    def test_phase_and_closed_guards(self):
        with ScoreSpool() as spool:
            with self.assertRaises(ScoreSpoolError): spool.page()
            with self.assertRaises(ScoreSpoolError): list(spool.ranked())
            spool.finalize()
            self.assertEqual(spool.page()['total'], 0)
            with self.assertRaises(ScoreSpoolError): spool.finalize()
            with self.assertRaises(ScoreSpoolError): spool.add(1, {'text': .5})
            path = spool.path
        self.assertFalse(path.parent.exists())
        spool.close()
        with self.assertRaises(ScoreSpoolError): spool.page()

    def test_streamed_fifty_thousand_scores_keep_python_peak_bounded(self):
        # Engine-only scores, generated lazily; no metadata/vector list/oracle in RAM.
        gc.collect(); tracemalloc.start()
        try:
            with ScoreSpool() as spool:
                for item in range(1, 50_002):
                    spool.add(item, {'text': float(item % 7) / 7, 'cover': float(item % 11) / 11})
                spool.finalize('mean-rrf')
                result = spool.page(page=416, limit=120)
                self.assertEqual((result['total'], len(result['ranked'])), (50_001, 81))
                peak = tracemalloc.get_traced_memory()[1]
                self.assertLess(peak, 32 * 1024 * 1024)
                self.assertLessEqual(spool.path.stat().st_size, 256 * 1024 * 1024)
        finally:
            tracemalloc.stop()


if __name__ == '__main__': unittest.main()
