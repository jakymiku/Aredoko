"""Unit tests for R06/R07 audio speech content indexing and time-grounded search."""
from array import array
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))

from ai_profiles import DEFAULT_PROFILE, ModelProfile
from ai_search import AISearch, VectorStore, revision
from audio_semantics import (
    AudioSpeechVectors, CONTRACT, SCHEMA as AUDIO_SCHEMA,
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
        self.calls = []

    def encode(self, operation, text):
        self.calls.append((operation, text))
        # Simple deterministic vector based on text keywords
        vec = [0.0] * self.dimension
        if '進捗' in text or '報告' in text:
            vec[0] = 1.0
        elif '事件' in text or '真相' in text:
            vec[1] = 1.0
        elif 'おはよう' in text:
            vec[2] = 1.0
        else:
            vec[3] = 1.0
        return vec

    def release(self):
        return {'released': True, 'resident': False}

    def close(self):
        pass


class AudioSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.catalog = ProductionCatalog(self.base / 'catalog.sqlite')
        self.addCleanup(self.catalog.close)

        self.media_dir = self.base / 'media'
        self.media_dir.mkdir()
        (self.media_dir / 'standup.mp3').write_bytes(b'ID3 audio speech test content')
        (self.media_dir / 'silence.wav').write_bytes(b'RIFF silence test')
        (self.media_dir / 'chart.png').write_bytes(b'PNG image test')

        self.root_id = self.catalog.add_root(str(self.media_dir))
        self.catalog.start_scan(self.root_id)
        if self.catalog._worker:
            self.catalog._worker.join(10)
        self.assertEqual(self.catalog.scan_state()['state'], 'complete')

        self.encoder = DummyEncoder()
        self.ai = AISearch(self.catalog, self.encoder, store_path=self.base / 'test_ai.sqlite')
        self.addCleanup(self.ai.close)
        self.store = self.ai.store
        self.audio = self.ai.audio_speech

    def test_schema_and_vector_unpack(self):
        dim = self.ai.profile.dimension
        vec = _unit_vector(dim, 0)
        packed = _pack_vector(vec)

        # Valid unpacked vector
        self.assertTrue(_is_valid_packed(packed, dim))
        unpacked = unpack(packed, dim, allocate=True)
        self.assertIsNotNone(unpacked)
        self.assertEqual(len(unpacked), dim)
        self.assertAlmostEqual(unpacked[0], 1.0)

        # Invalid dimensions
        bad_dim = _pack_vector([1.0, 0.0])
        self.assertFalse(_is_valid_packed(bad_dim, dim))
        self.assertIsNone(unpack(bad_dim, dim))

        # Non-finite values (NaN, Inf)
        nan_vec = _pack_vector([float('nan')] * dim)
        self.assertFalse(_is_valid_packed(nan_vec, dim))
        self.assertIsNone(unpack(nan_vec, dim))

        inf_vec = _pack_vector([float('inf')] * dim)
        self.assertFalse(_is_valid_packed(inf_vec, dim))
        self.assertIsNone(unpack(inf_vec, dim))

        # Unnormalized vector
        unnorm_vec = _pack_vector([2.0] * dim)
        self.assertFalse(_is_valid_packed(unnorm_vec, dim))
        self.assertIsNone(unpack(unnorm_vec, dim))

        # Dot product scoring without allocation
        query = _unit_vector(dim, 0)
        score = _score_packed(packed, dim, query)
        self.assertIsNotNone(score)
        self.assertAlmostEqual(score, 1.0)

        other = _pack_vector(_unit_vector(dim, 1))
        self.assertAlmostEqual(_score_packed(other, dim, query), 0.0)

    def test_put_and_get_segments(self):
        dim = self.ai.profile.dimension
        item_id = 1
        rev = 'a' * 64

        segments = [
            (0, 5000, "おはようございます、本日の進捗報告です。", _unit_vector(dim, 0)),
            (5000, 12000, "システムに異常はありません。", _unit_vector(dim, 1)),
        ]
        self.audio.put_segments(item_id, rev, segments)

        # Retrieve segments
        saved = self.audio.get_segments(item_id, rev)
        self.assertEqual(len(saved), 2)
        self.assertEqual(saved[0]['start_ms'], 0)
        self.assertEqual(saved[0]['end_ms'], 5000)
        self.assertEqual(saved[0]['snippet'], "おはようございます、本日の進捗報告です。")
        self.assertEqual(saved[1]['start_ms'], 5000)
        self.assertEqual(saved[1]['end_ms'], 12000)
        self.assertEqual(saved[1]['snippet'], "システムに異常はありません。")

        # Freshness check
        self.assertTrue(self.audio.fresh(item_id, rev))
        self.assertFalse(self.audio.fresh(item_id, 'b' * 64))

        # Invalidation on update (atomic replacement)
        new_segments = [
            (10000, 20000, "更新後の発話内容です。", _unit_vector(dim, 2))
        ]
        self.audio.put_segments(item_id, rev, new_segments)
        saved_updated = self.audio.get_segments(item_id, rev)
        self.assertEqual(len(saved_updated), 1)
        self.assertEqual(saved_updated[0]['start_ms'], 10000)
        self.assertEqual(saved_updated[0]['snippet'], "更新後の発話内容です。")

    def test_invalid_segment_timestamps_and_bounds_rejected(self):
        dim = self.ai.profile.dimension
        item_id = 1
        rev = 'a' * 64

        # Negative start_ms
        with self.assertRaises(ValueError):
            self.audio.put_segments(item_id, rev, [(-100, 5000, "test", _unit_vector(dim, 0))])

        # end_ms < start_ms
        with self.assertRaises(ValueError):
            self.audio.put_segments(item_id, rev, [(5000, 4000, "test", _unit_vector(dim, 0))])

        # Exceeds max 24 hours (86,400,000 ms)
        with self.assertRaises(ValueError):
            self.audio.put_segments(item_id, rev, [(0, 86_400_001, "test", _unit_vector(dim, 0))])

        # Empty snippet
        with self.assertRaises(ValueError):
            self.audio.put_segments(item_id, rev, [(0, 1000, "   ", _unit_vector(dim, 0))])

        # Oversized snippet (> 1024 chars)
        with self.assertRaises(ValueError):
            self.audio.put_segments(item_id, rev, [(0, 1000, "a" * 1025, _unit_vector(dim, 0))])

    def test_audio_speech_search_and_timepoint_grounding(self):
        dim = self.ai.profile.dimension
        items = self.catalog.search()['items']
        audio_item = next(it for it in items if it['kind'] == 'audio' and 'standup' in it['title'])
        image_item = next(it for it in items if it['kind'] == 'image')

        rev_audio = revision(audio_item)
        rev_image = revision(image_item)

        # Index segments for standup.mp3: 2 segments
        # Segment 1 (0..5000ms): "おはようございます" (vector dim 2)
        # Segment 2 (5000..15000ms): "本日の進捗報告を行います" (vector dim 0)
        segments = [
            (0, 5000, "おはようございます", _unit_vector(dim, 2)),
            (5000, 15000, "本日の進捗報告を行います", _unit_vector(dim, 0)),
        ]
        self.audio.put_segments(audio_item['id'], rev_audio, segments)

        # Index text vector for image item
        self.store.put(image_item['id'], rev_image, {'text': _unit_vector(dim, 3)})

        # Query "進捗" matches Segment 2 (vector dim 0)
        query_vec = _unit_vector(dim, 0)
        speech_scores = self.audio.rank([audio_item, image_item], query_vec)

        self.assertIn(audio_item['id'], speech_scores)
        score, evidence = speech_scores[audio_item['id']]
        self.assertAlmostEqual(score, 1.0)
        self.assertEqual(evidence['start_ms'], 5000)
        self.assertEqual(evidence['end_ms'], 15000)
        self.assertEqual(evidence['snippet'], "本日の進捗報告を行います")

        # scores_with_content integration
        scores, video_hits, page_hits, audio_hits = self.store.scores_with_content(
            [audio_item, image_item], query_vec, source='text', audio_scores=speech_scores
        )
        self.assertIn(audio_item['id'], scores)
        self.assertIn(audio_item['id'], audio_hits)
        self.assertEqual(audio_hits[audio_item['id']]['start_ms'], 5000)
        self.assertEqual(audio_hits[audio_item['id']]['snippet'], "本日の進捗報告を行います")

        # Full AISearch.search execution
        search_res = self.ai.search("進捗報告", source='all')
        self.assertTrue(search_res['search_complete'])
        self.assertGreater(len(search_res['items']), 0)
        matched = next(it for it in search_res['items'] if it['id'] == audio_item['id'])
        self.assertEqual(matched['audio_match_ms'], 5000)
        self.assertEqual(matched['audio_match_snippet'], "本日の進捗報告を行います")

    def test_silence_or_corrupt_audio_no_false_hits(self):
        dim = self.ai.profile.dimension
        items = self.catalog.search()['items']
        silence_item = next(it for it in items if it['kind'] == 'audio' and 'silence' in it['title'])

        query_vec = _unit_vector(dim, 0)

        # Silent audio has no segments indexed
        speech_scores = self.audio.rank([silence_item], query_vec)
        self.assertEqual(speech_scores, {})

        scores, video_hits, page_hits, audio_hits = self.store.scores_with_content(
            [silence_item], query_vec, source='text', audio_scores=speech_scores
        )
        self.assertNotIn(silence_item['id'], scores)
        self.assertNotIn(silence_item['id'], audio_hits)

    def test_source_modification_invalidates_speech_segments(self):
        dim = self.ai.profile.dimension
        items = self.catalog.search()['items']
        audio_item = next(it for it in items if it['kind'] == 'audio' and 'standup' in it['title'])

        rev_initial = revision(audio_item)
        segments = [(0, 3000, "講義を始めます", _unit_vector(dim, 0))]
        self.audio.put_segments(audio_item['id'], rev_initial, segments)

        query_vec = _unit_vector(dim, 0)
        self.assertIn(audio_item['id'], self.audio.rank([audio_item], query_vec))

        # Modify source file (mtime_ns changes)
        row_modified = dict(audio_item, mtime_ns=audio_item['mtime_ns'] + 5000)
        rev_modified = revision(row_modified)
        self.assertNotEqual(rev_initial, rev_modified)

        # Query with modified row: old segments are obsolete and ignored
        self.assertEqual(self.audio.rank([row_modified], query_vec), {})
        self.assertFalse(self.audio.fresh(audio_item['id'], rev_modified))

    def test_dict_and_tuple_formats_and_duplicate_rejection(self):
        dim = self.ai.profile.dimension
        item_id = 99
        rev = 'c' * 64

        # Dict format with explicit segment_id
        dict_segs = [
            {'segment_id': 'seg_alpha', 'start_ms': 1000, 'end_ms': 4000, 'snippet': 'アルファ区間です', 'vector': _unit_vector(dim, 0)},
            {'start_ms': 4000, 'end_ms': 9000, 'snippet': 'ベータ区間です', 'vector': _unit_vector(dim, 1)},
        ]
        self.audio.put_segments(item_id, rev, dict_segs)
        saved = self.audio.get_segments(item_id, rev)
        self.assertEqual(len(saved), 2)
        self.assertEqual(saved[0]['segment_id'], 'seg_alpha')
        self.assertEqual(saved[0]['snippet'], 'アルファ区間です')
        self.assertTrue(saved[1]['segment_id'].startswith('seg_0001_'))

        # 5-tuple format: (seg_id, start_ms, end_ms, snippet, vector)
        five_tuple_segs = [
            ('seg_five_01', 10000, 15000, '5要素タプル区間', _unit_vector(dim, 2))
        ]
        self.audio.put_segments(item_id, rev, five_tuple_segs)
        saved5 = self.audio.get_segments(item_id, rev)
        self.assertEqual(len(saved5), 1)
        self.assertEqual(saved5[0]['segment_id'], 'seg_five_01')

        # Duplicate segment_id rejected
        dup_segs = [
            {'segment_id': 'same_id', 'start_ms': 100, 'end_ms': 200, 'snippet': '区間1', 'vector': _unit_vector(dim, 0)},
            {'segment_id': 'same_id', 'start_ms': 300, 'end_ms': 400, 'snippet': '区間2', 'vector': _unit_vector(dim, 0)},
        ]
        with self.assertRaises(ValueError):
            self.audio.put_segments(item_id, rev, dup_segs)

        # Non-string snippets rejected
        with self.assertRaises(ValueError):
            self.audio.put_segments(item_id, rev, [{'start_ms': 0, 'end_ms': 1000, 'snippet': None, 'vector': _unit_vector(dim, 0)}])
        with self.assertRaises(ValueError):
            self.audio.put_segments(item_id, rev, [(0, 1000, 12345, _unit_vector(dim, 0))])

    def test_packed_vector_reuse(self):
        dim = self.ai.profile.dimension
        item_id = 88
        rev = 'd' * 64

        orig_segs = [
            (0, 3000, "再利用対象の発話です", _unit_vector(dim, 0)),
            (3000, 6000, "2つ目の発話です", _unit_vector(dim, 1)),
        ]
        self.audio.put_segments(item_id, rev, orig_segs)

        # Retrieve with include_vectors=False to get raw bytes
        cached_segs = self.audio.get_segments(item_id, rev, include_vectors=False)
        self.assertEqual(len(cached_segs), 2)
        self.assertIsInstance(cached_segs[0]['vector'], bytes)
        self.assertEqual(len(cached_segs[0]['vector']), dim * 4)

        # Put segments using the cached bytes (zero allocation vector reuse)
        new_item_id = 89
        self.audio.put_segments(new_item_id, rev, cached_segs)
        reused_segs = self.audio.get_segments(new_item_id, rev, include_vectors=False)
        self.assertEqual(cached_segs[0]['vector'], reused_segs[0]['vector'])
        self.assertTrue(self.audio.fresh(new_item_id, rev))

    def test_long_audio_windowing_and_scale(self):
        dim = self.ai.profile.dimension
        item_id = 77
        rev = 'e' * 64

        # Generate 120 segments spanning 2 hours (60,000ms each)
        # Target segment at 01:45:00 (6,300,000 ms to 6,360,000 ms) matching dim 0
        long_segments = []
        for i in range(120):
            start = i * 60_000
            end = start + 60_000
            is_target = (i == 105)  # 105 * 60,000 = 6,300,000 ms (01:45:00)
            vec = _unit_vector(dim, 0 if is_target else 1)
            snip = "重要な決断が行われた瞬間です" if is_target else f"通常議論の区間{i}"
            long_segments.append((start, end, snip, vec))

        self.audio.put_segments(item_id, rev, long_segments)
        saved = self.audio.get_segments(item_id, rev)
        self.assertEqual(len(saved), 120)

        # Query targeting dim 0
        audio_row = {'id': item_id, 'kind': 'audio', 'root_id': 1, 'relative_path': 'long.mp3',
                     'size_bytes': 1000, 'mtime_ns': 1000, 'title': 'long.mp3', 'tags': ''}
        from ai_search import revision as make_rev
        with patch('ai_search.revision', return_value=rev):
            res = self.audio.rank([audio_row], _unit_vector(dim, 0))
            self.assertIn(item_id, res)
            score, evid = res[item_id]
            self.assertAlmostEqual(score, 1.0)
            self.assertEqual(evid['start_ms'], 6_300_000)
            self.assertEqual(evid['end_ms'], 6_360_000)
            self.assertEqual(evid['snippet'], "重要な決断が行われた瞬間です")

        # 1,000 segments scale verification (reviewer attack surface)
        scale_segs = [
            (i * 1000, (i + 1) * 1000, f"セグメント{i:04d}", _unit_vector(dim, 0 if i == 777 else 2))
            for i in range(1000)
        ]
        scale_id = 78
        self.audio.put_segments(scale_id, rev, scale_segs)
        scale_row = dict(audio_row, id=scale_id)
        with patch('ai_search.revision', return_value=rev):
            scale_res = self.audio.rank([scale_row], _unit_vector(dim, 0))
            self.assertIn(scale_id, scale_res)
            score, evid = scale_res[scale_id]
            self.assertAlmostEqual(score, 1.0)
            self.assertEqual(evid['start_ms'], 777_000)
            self.assertEqual(evid['snippet'], "セグメント0777")

    def test_corrupt_vector_in_database_safe_skip_and_freshness(self):
        dim = self.ai.profile.dimension
        item_id = 66
        rev = 'f' * 64

        # Put 1 valid segment
        self.audio.put_segments(item_id, rev, [(0, 5000, "正常発話", _unit_vector(dim, 0))])
        self.assertTrue(self.audio.fresh(item_id, rev))

        # Directly corrupt database row with invalid byte length (12 bytes instead of 3072)
        with self.store.connect() as db:
            db.execute(
                "INSERT INTO ai_audio_segments VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (item_id, rev, "corrupt_seg", 5000, 10000, "破損区間", b'\x00' * 12, CONTRACT)
            )

        # fresh() must detect corruption and report False
        self.assertFalse(self.audio.fresh(item_id, rev))

        # rank() must safely skip corrupt vector without crashing and still find the valid one
        audio_row = {'id': item_id, 'kind': 'audio', 'root_id': 1, 'relative_path': 'test.mp3',
                     'size_bytes': 1000, 'mtime_ns': 1000, 'title': 'test.mp3', 'tags': ''}
        with patch('ai_search.revision', return_value=rev):
            res = self.audio.rank([audio_row], _unit_vector(dim, 0))
            self.assertIn(item_id, res)
            score, evid = res[item_id]
            self.assertAlmostEqual(score, 1.0)
            self.assertEqual(evid['segment_id'], 'seg_0000_00000000')

    def test_cancellation_during_rank_and_search(self):
        dim = self.ai.profile.dimension
        item_id = 55
        rev = '7' * 64

        self.audio.put_segments(item_id, rev, [(0, 5000, "発話", _unit_vector(dim, 0))])
        audio_row = {'id': item_id, 'kind': 'audio', 'root_id': 1, 'relative_path': 'test.mp3',
                     'size_bytes': 1000, 'mtime_ns': 1000, 'title': 'test.mp3', 'tags': ''}

        # check callback raising InterruptedError
        def cancel_check():
            raise InterruptedError("Cancelled")

        with self.assertRaises(InterruptedError):
            self.audio.rank([audio_row], _unit_vector(dim, 0), check=cancel_check)

        # AISearch.search with pre-cancelled event
        import threading
        from ai_score_spool import SearchCancelled
        cancelled_event = threading.Event()
        cancelled_event.set()
        with self.assertRaises(SearchCancelled):
            self.ai.search("進捗報告", cancelled=cancelled_event.is_set)

    def test_delete_item(self):
        dim = self.ai.profile.dimension
        item_id = 44
        rev = '8' * 64

        self.audio.put_segments(item_id, rev, [(0, 5000, "削除前発話", _unit_vector(dim, 0))])
        self.assertTrue(self.audio.fresh(item_id, rev))

        self.audio.delete_item(item_id)
        self.assertFalse(self.audio.fresh(item_id, rev))
        self.assertEqual(self.audio.get_segments(item_id, rev), [])

        with self.assertRaises(ValueError):
            self.audio.delete_item(-1)
        with self.assertRaises(ValueError):
            self.audio.delete_item(0)


if __name__ == '__main__':
    unittest.main()

