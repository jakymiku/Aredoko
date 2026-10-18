"""Deterministic unit tests for R10 AI state clarity, unindexed distinction, and error recovery."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))

from ai_search import AISearch, VectorStore
from ai_process import AIUnavailable
from production import ProductionCatalog
from production_server import DisabledAI


def unit_vector(dim=768, axis=0):
    vec = [0.0] * dim
    vec[axis] = 1.0
    return vec


class DummyEncoder:
    available = True
    device = 'cpu'

    def __init__(self, available=True):
        self.available = available
        self.resident = False

    def encode(self, operation, text):
        return unit_vector(axis=0)

    def close(self):
        pass


class AIStatusClarityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.media = self.base / 'media'
        self.media.mkdir()
        (self.media / 'rain.wav').write_text('audio-test', encoding='utf-8')
        (self.media / 'jazz.mp3').write_text('audio-test', encoding='utf-8')
        self.catalog = ProductionCatalog(self.base / 'catalog.sqlite')
        self.addCleanup(self.catalog.close)
        self.root = self.catalog.add_root(str(self.media))
        self.catalog.start_scan(self.root)
        self.catalog._worker.join(10)

    def test_status_code_ready_and_model_missing(self):
        encoder = DummyEncoder(available=True)
        ai = AISearch(self.catalog, encoder)
        self.addCleanup(ai.close)
        st = ai.status()
        self.assertEqual(st['status_code'], 'ready')
        self.assertTrue(st['available'])

        # Unavailable encoder -> model_missing
        encoder_missing = DummyEncoder(available=False)
        ai_missing = AISearch(self.catalog, encoder_missing)
        self.addCleanup(ai_missing.close)
        st_missing = ai_missing.status()
        self.assertEqual(st_missing['status_code'], 'model_missing')
        self.assertFalse(st_missing['available'])

        # Store states: running, cancelling, interrupted, failed
        with ai.guard:
            ai.store.save_state({'state': 'running', 'processed': 1, 'total': 2, 'indexed': 1, 'skipped': 0, 'error': ''})
        self.assertEqual(ai.status()['status_code'], 'running')

        with ai.guard:
            ai.store.save_state({'state': 'cancelling', 'processed': 1, 'total': 2, 'indexed': 1, 'skipped': 0, 'error': ''})
        self.assertEqual(ai.status()['status_code'], 'cancelling')

        with ai.guard:
            ai.store.save_state({'state': 'interrupted', 'processed': 1, 'total': 2, 'indexed': 1, 'skipped': 0, 'error': ''})
        self.assertEqual(ai.status()['status_code'], 'interrupted')

        with ai.guard:
            ai.store.save_state({'state': 'failed', 'processed': 1, 'total': 2, 'indexed': 1, 'skipped': 0, 'error': 'worker crashed'})
        self.assertEqual(ai.status()['status_code'], 'worker_failed')

    def test_coverage_status_progression(self):
        encoder = DummyEncoder(available=True)
        ai = AISearch(self.catalog, encoder)
        self.addCleanup(ai.close)

        # Before indexing: unindexed
        cov = ai.coverage()
        self.assertEqual(cov['target_total'], 2)
        self.assertEqual(cov['fresh_total'], 0)
        self.assertEqual(cov['coverage_status'], 'unindexed')

        # Index the items
        ai.start()
        ai.worker.join(10)

        # After indexing: ready
        cov2 = ai.coverage()
        self.assertEqual(cov2['fresh_total'], 2)
        self.assertEqual(cov2['coverage_status'], 'ready')

        # Empty scope: empty_scope
        cov_empty = ai.coverage(scope={'shelf': 'non_existent_shelf'})
        self.assertEqual(cov_empty['target_total'], 0)
        self.assertEqual(cov_empty['coverage_status'], 'empty_scope')

    def test_search_status_progression(self):
        encoder = DummyEncoder(available=True)
        ai = AISearch(self.catalog, encoder)
        self.addCleanup(ai.close)

        # Before indexing: candidate_total > 0 and indexed_total == 0 -> unindexed
        res_unindexed = ai.search('雨')
        self.assertEqual(res_unindexed['search_candidate_total'], 2)
        self.assertEqual(res_unindexed['indexed_total'], 0)
        self.assertEqual(res_unindexed['search_status'], 'unindexed')
        self.assertEqual(len(res_unindexed['items']), 0)

        # Index the items
        ai.start()
        ai.worker.join(10)

        # After indexing: candidate_total == indexed_total -> ready
        res_ready = ai.search('雨')
        self.assertEqual(res_ready['search_candidate_total'], 2)
        self.assertEqual(res_ready['indexed_total'], 2)
        self.assertEqual(res_ready['search_status'], 'ready')
        self.assertGreater(len(res_ready['items']), 0)

        # Out of scope query
        res_oos = ai.search('雨', scope={'shelf': 'non_existent_shelf'})
        self.assertEqual(res_oos['search_candidate_total'], 0)
        self.assertEqual(res_oos['search_status'], 'out_of_scope')

    def test_disabled_ai_behavior(self):
        disabled = DisabledAI('モデルがインストールされていません。', status_code='model_missing')
        st = disabled.status()
        self.assertFalse(st['available'])
        self.assertEqual(st['state'], 'failed')
        self.assertEqual(st['status_code'], 'model_missing')
        self.assertIn('未導入', st['model'])

        with self.assertRaises(AIUnavailable):
            disabled.search('テスト')
        with self.assertRaises(AIUnavailable):
            disabled.start()
        with self.assertRaises(AIUnavailable):
            disabled.similar(1)
        with self.assertRaises(AIUnavailable):
            disabled.coverage()

        # Default DisabledAI provides actionable message containing 未導入
        default_disabled = DisabledAI()
        self.assertEqual(default_disabled.status()['status_code'], 'model_missing')
        self.assertIn('未導入', default_disabled.status()['error'])

        # DisabledAI with corrupt_profile
        corrupt_disabled = DisabledAI('プロファイル破損', status_code='corrupt_profile')
        self.assertEqual(corrupt_disabled.status()['status_code'], 'corrupt_profile')

        # create_ai categorization: corrupt profile JSON -> corrupt_profile
        from production_server import create_ai
        corrupt_file = self.base / 'corrupt_profile.json'
        corrupt_file.write_text('{ "invalid": syntax ', encoding='utf-8')
        bad_profile_ai = create_ai(self.catalog, profile_path=corrupt_file)
        self.assertIsInstance(bad_profile_ai, DisabledAI)
        self.assertEqual(bad_profile_ai.status()['status_code'], 'corrupt_profile')

        # create_ai categorization: missing profile file -> model_missing
        missing_ai = create_ai(self.catalog, profile_path=self.base / 'missing_profile.json')
        self.assertIsInstance(missing_ai, DisabledAI)
        self.assertEqual(missing_ai.status()['status_code'], 'model_missing')


if __name__ == '__main__':
    unittest.main()
