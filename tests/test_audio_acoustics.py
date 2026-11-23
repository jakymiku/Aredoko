"""Unit tests for R08 audio acoustic & music feature indexing and similarity search."""
from array import array
import json
import math
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))

from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch, revision
from audio_acoustics import (
    AudioAcousticVectors, CONTRACT, ACOUSTIC_DIMENSION, SCHEMA as ACOUSTIC_SCHEMA,
    unpack, _is_valid_packed, _score_packed
)
from production import ProductionCatalog


def _pack_vector(values):
    return array('f', values).tobytes()


def _unit_vector(dim, index):
    vec = [0.0] * dim
    vec[index % dim] = 1.0
    return vec


class DummyEncoder:
    def __init__(self, dimension=DEFAULT_PROFILE.dimension):
        self.profile = DEFAULT_PROFILE
        self.dimension = dimension
        self.available = True
        self.resident = True

    def encode(self, operation, text):
        vec = [0.0] * self.dimension
        vec[0] = 1.0
        return vec

    def release(self):
        return {'released': True, 'resident': False}

    def close(self):
        pass


class AudioAcousticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.catalog = ProductionCatalog(self.base / 'catalog.sqlite')
        self.addCleanup(self.catalog.close)

        self.media_dir = self.base / 'media'
        self.media_dir.mkdir()
        (self.media_dir / 'rain_sound.wav').write_bytes(b'RIFF audio rain sfx')
        (self.media_dir / 'jazz_piano.mp3').write_bytes(b'ID3 audio jazz piano music')
        (self.media_dir / 'silence.wav').write_bytes(b'RIFF silent test audio')
        (self.media_dir / 'photo.png').write_bytes(b'PNG image test')

        self.root_id = self.catalog.add_root(str(self.media_dir))
        self.catalog.start_scan(self.root_id)
        if self.catalog._worker:
            self.catalog._worker.join(10)
        self.assertEqual(self.catalog.scan_state()['state'], 'complete')

        self.encoder = DummyEncoder()
        self.ai = AISearch(self.catalog, self.encoder, store_path=self.base / 'test_ai.sqlite')
        self.addCleanup(self.ai.close)
        self.acoustics = self.ai.audio_acoustics

    def _find_item(self, name):
        items = self.catalog.search()['items']
        return next(it for it in items if name in it.get('title', ''))

    def test_schema_and_constants(self):
        self.assertEqual(CONTRACT, 'audio-acoustic-feature:v1')
        self.assertEqual(ACOUSTIC_DIMENSION, 512)
        with self.ai.store.connect() as db:
            cols = [col[1] for col in db.execute("PRAGMA table_info(ai_audio_acoustics)").fetchall()]
            self.assertIn('item_id', cols)
            self.assertIn('at_ms', cols)
            self.assertIn('vector', cols)
            self.assertIn('descriptors', cols)
            self.assertIn('contract', cols)

    def test_unpack_and_validation(self):
        dim = ACOUSTIC_DIMENSION
        vec = _unit_vector(dim, 0)
        packed = _pack_vector(vec)

        self.assertTrue(_is_valid_packed(packed, dim))
        unpacked = unpack(packed, dim, allocate=True)
        self.assertIsNotNone(unpacked)
        self.assertEqual(len(unpacked), dim)
        self.assertAlmostEqual(unpacked[0], 1.0)

        # Reject wrong dimension (e.g. 768D text vector in 512D acoustic space)
        wrong_dim = _pack_vector(_unit_vector(768, 0))
        self.assertFalse(_is_valid_packed(wrong_dim, dim))
        self.assertIsNone(unpack(wrong_dim, dim, allocate=True))

        # Reject unaligned lengths
        self.assertFalse(_is_valid_packed(packed[:-1], dim))
        self.assertFalse(_is_valid_packed(packed + b'\x00', dim))

        # Reject non-finite values (NaN / Inf)
        nan_vec = _unit_vector(dim, 0)
        nan_vec[0] = float('nan')
        self.assertFalse(_is_valid_packed(_pack_vector(nan_vec), dim))

        inf_vec = _unit_vector(dim, 0)
        inf_vec[0] = float('inf')
        self.assertFalse(_is_valid_packed(_pack_vector(inf_vec), dim))

        # Reject non-unit / zero vectors
        zero_vec = [0.0] * dim
        self.assertFalse(_is_valid_packed(_pack_vector(zero_vec), dim))

    def test_score_packed(self):
        dim = ACOUSTIC_DIMENSION
        v1 = _unit_vector(dim, 5)
        v2 = _unit_vector(dim, 5)
        v3 = _unit_vector(dim, 10)

        p1 = _pack_vector(v1)
        # Dot product identical unit vectors = 1.0
        score = _score_packed(p1, dim, v2)
        self.assertIsNotNone(score)
        self.assertAlmostEqual(score, 1.0, places=5)

        # Orthogonal unit vectors = 0.0
        score_ortho = _score_packed(p1, dim, v3)
        self.assertIsNotNone(score_ortho)
        self.assertAlmostEqual(score_ortho, 0.0, places=5)

        # Dimension mismatch returns None
        self.assertIsNone(_score_packed(p1, dim, [0.0] * 768))

    def test_space_isolation(self):
        # Passing 768D vector to score_candidates raises ValueError
        with self.assertRaises(ValueError) as ctx:
            self.acoustics.score_candidates(
                [{'id': 1, 'kind': 'audio'}],
                [(1000, [0.0] * 768)]
            )
        self.assertIn("Cross-space vector comparison rejected", str(ctx.exception))

    def test_put_and_get_features(self):
        item = self._find_item('rain_sound.wav')
        self.assertIsNotNone(item)
        rev = revision(item)

        dim = ACOUSTIC_DIMENSION
        v1 = _unit_vector(dim, 1)
        v2 = _unit_vector(dim, 2)

        features = [
            {'at_ms': 5000, 'vector': v1, 'descriptors': ['雨音', '環境音', '自然']},
            {'at_ms': 15000, 'vector': v2, 'descriptors': ['雷', '豪雨']}
        ]

        self.acoustics.put_features(item['id'], rev, features)

        # Retrieve with allocated vectors
        loaded = self.acoustics.get_features(item['id'], rev, include_vectors=True)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]['at_ms'], 5000)
        self.assertEqual(loaded[0]['descriptors'], ['雨音', '環境音', '自然'])
        self.assertAlmostEqual(loaded[0]['vector'][1], 1.0)
        self.assertEqual(loaded[1]['at_ms'], 15000)

        # Retrieve with raw packed vectors (zero list allocation)
        raw_loaded = self.acoustics.get_features(item['id'], rev, include_vectors=False)
        self.assertEqual(len(raw_loaded), 2)
        self.assertIsInstance(raw_loaded[0]['vector'], bytes)
        self.assertEqual(len(raw_loaded[0]['vector']), dim * 4)

        # Acoustic frames helper
        frames = self.acoustics.acoustic_frames(item)
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0][0], 5000)

        # Atomic replacement on re-index
        v3 = _unit_vector(dim, 3)
        self.acoustics.put_features(item['id'], rev, [
            {'at_ms': 2000, 'vector': v3, 'descriptors': ['小雨']}
        ])
        updated = self.acoustics.get_features(item['id'], rev)
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0]['at_ms'], 2000)
        self.assertEqual(updated[0]['descriptors'], ['小雨'])

    def test_put_features_validation(self):
        item = self._find_item('rain_sound.wav')
        rev = revision(item)
        dim = ACOUSTIC_DIMENSION

        # Duplicate timestamp rejected
        with self.assertRaises(ValueError):
            self.acoustics.put_features(item['id'], rev, [
                {'at_ms': 1000, 'vector': _unit_vector(dim, 0)},
                {'at_ms': 1000, 'vector': _unit_vector(dim, 1)}
            ])

        # Negative timestamp rejected
        with self.assertRaises(ValueError):
            self.acoustics.put_features(item['id'], rev, [
                {'at_ms': -500, 'vector': _unit_vector(dim, 0)}
            ])

        # Timestamp exceeding 24 hours rejected
        with self.assertRaises(ValueError):
            self.acoustics.put_features(item['id'], rev, [
                {'at_ms': 86_400_001, 'vector': _unit_vector(dim, 0)}
            ])

    def test_fresh_and_delete_item(self):
        item = self._find_item('rain_sound.wav')
        rev = revision(item)
        dim = ACOUSTIC_DIMENSION

        self.assertFalse(self.acoustics.fresh(item['id'], rev))

        self.acoustics.put_features(item['id'], rev, [
            {'at_ms': 1000, 'vector': _unit_vector(dim, 0), 'descriptors': ['雨音']}
        ])
        self.assertTrue(self.acoustics.fresh(item['id'], rev))
        # Wrong revision is not fresh
        self.assertFalse(self.acoustics.fresh(item['id'], '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef'))

        # Delete item
        self.acoustics.delete_item(item['id'])
        self.assertFalse(self.acoustics.fresh(item['id'], rev))
        self.assertEqual(len(self.acoustics.get_features(item['id'], rev)), 0)

    def test_rank_japanese_descriptors(self):
        rain = self._find_item('rain_sound.wav')
        jazz = self._find_item('jazz_piano.mp3')
        silence = self._find_item('silence.wav')
        photo = self._find_item('photo.png')

        dim = ACOUSTIC_DIMENSION
        self.acoustics.put_features(rain['id'], revision(rain), [
            {'at_ms': 3000, 'vector': _unit_vector(dim, 0), 'descriptors': ['雨音', '自然環境音', '静かな雨']}
        ])
        self.acoustics.put_features(jazz['id'], revision(jazz), [
            {'at_ms': 8000, 'vector': _unit_vector(dim, 1), 'descriptors': ['ジャズピアノ', 'ピアノソロ', 'BGM']}
        ])
        # silence has no features indexed

        candidates = [rain, jazz, silence, photo]

        # Exact match query
        scores = self.acoustics.rank(candidates, '雨音')
        self.assertIn(rain['id'], scores)
        self.assertNotIn(jazz['id'], scores)
        self.assertNotIn(silence['id'], scores)  # No hallucination on silent WAV
        self.assertNotIn(photo['id'], scores)    # Non-audio candidate ignored

        score_val, meta = scores[rain['id']]
        self.assertGreaterEqual(score_val, 0.95)
        self.assertEqual(meta['start_ms'], 3000)
        self.assertEqual(meta['snippet'], '音響特徴: 雨音')

        # Substring / partial match query
        jazz_scores = self.acoustics.rank(candidates, 'ピアノ')
        self.assertIn(jazz['id'], jazz_scores)
        self.assertNotIn(rain['id'], jazz_scores)
        score_val_j, meta_j = jazz_scores[jazz['id']]
        self.assertGreaterEqual(score_val_j, 0.90)
        self.assertEqual(meta_j['start_ms'], 8000)
        self.assertIn('ピアノ', meta_j['snippet'])

        # Query with leading/trailing whitespace stripped to exact match
        spaced_scores = self.acoustics.rank(candidates, '  雨音  ')
        self.assertIn(rain['id'], spaced_scores)
        self.assertGreaterEqual(spaced_scores[rain['id']][0], 0.95)

        # Pure whitespace query cleanly returns empty
        self.assertEqual(self.acoustics.rank(candidates, '   '), {})

        # Single hiragana particle does not cause false-positive matches
        hiragana_query_scores = self.acoustics.rank(candidates, '海 の 景色')
        self.assertNotIn(rain['id'], hiragana_query_scores)
        self.assertNotIn(jazz['id'], hiragana_query_scores)

    def test_audio_similarity_search(self):
        rain = self._find_item('rain_sound.wav')
        jazz = self._find_item('jazz_piano.mp3')
        silence = self._find_item('silence.wav')
        photo = self._find_item('photo.png')

        dim = ACOUSTIC_DIMENSION
        # rain has feature at 1000ms and 5000ms
        v_common = _unit_vector(dim, 10)
        v_diff = _unit_vector(dim, 20)

        self.acoustics.put_features(rain['id'], revision(rain), [
            {'at_ms': 1000, 'vector': v_common},
            {'at_ms': 5000, 'vector': v_diff}
        ])
        # jazz has matching feature v_common at 12000ms
        self.acoustics.put_features(jazz['id'], revision(jazz), [
            {'at_ms': 12000, 'vector': v_common}
        ])

        # Similarity search with rain as origin
        result = self.ai.similar(rain['id'])
        self.assertEqual(result['similarity_status'], 'ready')
        self.assertEqual(result['source'], 'acoustic')
        self.assertEqual(result['origin_kind'], 'audio')
        self.assertEqual(result['origin_id'], rain['id'])

        # Self-exclusion: origin item must not be in items
        item_ids = [item['id'] for item in result['items']]
        self.assertNotIn(rain['id'], item_ids)
        self.assertIn(jazz['id'], item_ids)
        self.assertNotIn(photo['id'], item_ids)  # Non-audio candidates excluded

        # Timepoint grounding check
        jazz_item = next(it for it in result['items'] if it['id'] == jazz['id'])
        self.assertAlmostEqual(jazz_item['semantic_score'], 1.0, places=4)
        self.assertEqual(jazz_item['audio_match_ms'], 12000)
        self.assertEqual(jazz_item['origin_match_ms'], 1000)

        # Unindexed origin (silence.wav) returns unindexed fallback cleanly
        silence_result = self.ai.similar(silence['id'])
        self.assertEqual(silence_result['similarity_status'], 'unindexed')
        self.assertEqual(len(silence_result['items']), 0)

    def test_search_integration_acoustic(self):
        rain = self._find_item('rain_sound.wav')
        dim = ACOUSTIC_DIMENSION
        self.acoustics.put_features(rain['id'], revision(rain), [
            {'at_ms': 7500, 'vector': _unit_vector(dim, 5), 'descriptors': ['雨音', '激しい雨']}
        ])

        # ai.search with query "雨音" finds the audio file via acoustic descriptors
        res = self.ai.search('雨音', source='all')
        self.assertTrue(res['search_complete'])
        matched = [it for it in res['items'] if it['id'] == rain['id']]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]['audio_match_ms'], 7500)
        self.assertIn('雨音', matched[0]['audio_match_snippet'])

    def test_cancellation(self):
        rain = self._find_item('rain_sound.wav')
        dim = ACOUSTIC_DIMENSION
        records = [
            {'at_ms': i * 1000, 'vector': _unit_vector(dim, i % dim), 'descriptors': [f'sound_{i}']}
            for i in range(300)
        ]
        self.acoustics.put_features(rain['id'], revision(rain), records)

        calls = []
        def cancel_check():
            calls.append(1)

        # Candidate scoring checks cancellation
        self.acoustics.score_candidates([rain], [(1000, _unit_vector(dim, 0))], check=cancel_check)
        self.assertGreater(len(calls), 0)

        # Japanese descriptor rank checks cancellation
        calls.clear()
        self.acoustics.rank([rain], 'sound_5', check=cancel_check)
        self.assertGreater(len(calls), 0)


if __name__ == '__main__':
    unittest.main()
