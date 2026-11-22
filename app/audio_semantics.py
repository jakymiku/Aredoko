"""Time-grounded audio speech content embeddings and retrieval (R06/R07).

Separated modular speech semantic space (768D text-semantic space).
No cross-modality vector mixing; acoustic/music similarity is handled in R08.
"""
from array import array
import itertools
import math
import operator
import re

from ai_process import AIUnavailable
from ai_vectors import normalized
import native_accel

CONTRACT = 'audio-speech-segment:v1'
MAX_AUDIO_BYTES = 512 * 1024 * 1024  # 512 MiB
MAX_DURATION_MS = 86_400_000         # 24 hours
MAX_SNIPPET_LENGTH = 1024
ROW_BATCH_SIZE = 500

SCHEMA = '''CREATE TABLE IF NOT EXISTS ai_audio_segments(
    item_id INTEGER NOT NULL,
    source_revision TEXT NOT NULL,
    segment_id TEXT NOT NULL,
    start_ms INTEGER NOT NULL CHECK(start_ms>=0 AND start_ms<=86400000),
    end_ms INTEGER NOT NULL CHECK(end_ms>=start_ms AND end_ms<=86400000),
    snippet TEXT NOT NULL,
    vector BLOB NOT NULL,
    contract TEXT NOT NULL,
    PRIMARY KEY(item_id, segment_id));'''


def unpack(data, dimension, allocate=True):
    """Unpack float32 vector blob, validate finite unit length, optionally allocate."""
    try:
        value = array('f')
        value.frombytes(data)
        if len(value) != dimension:
            return None if allocate else False
        squared_norm = sum(map(operator.mul, value, value))
        if not math.isfinite(squared_norm) or abs(squared_norm - 1.0) > 1e-4:
            return None if allocate else False
        if not allocate:
            return True
        norm = math.sqrt(squared_norm)
        return list(map(operator.truediv, value, itertools.repeat(norm)))
    except (ValueError, TypeError, OverflowError):
        return None if allocate else False


def _is_valid_packed(data, dimension):
    """Validate stored float32 audio segment vector without allocating a list."""
    return unpack(data, dimension, False)


def _score_packed(data, dimension, query):
    """Unpack, validate and compute exact float64 dot product without allocating a list."""
    try:
        if len(query) != dimension:
            return None
        value = array('f')
        value.frombytes(data)
        if len(value) != dimension:
            return None
        squared_norm = sum(map(operator.mul, value, value))
        if not math.isfinite(squared_norm) or abs(squared_norm - 1.0) > 1e-4:
            return None
        norm = math.sqrt(squared_norm)
        return sum(map(operator.mul, query, map(operator.truediv, value, itertools.repeat(norm))))
    except (ValueError, TypeError, OverflowError):
        return None


_ORIG_SCORE_PACKED = _score_packed


class AudioSpeechVectors:
    def __init__(self, ai):
        self.ai = ai

    def rank(self, rows, query_vector, check=None):
        """Rank audio candidate rows against query_vector using indexed speech segments.

        Returns:
            scores: dict {item_id: (best_cosine_score, {'start_ms': int, 'end_ms': int, 'snippet': str, 'segment_id': str})}
        """
        if not rows or query_vector is None:
            return {}
        dimension = self.ai.profile.dimension
        if len(query_vector) != dimension:
            raise ValueError(f"Query vector dimension mismatch: expected {dimension}, got {len(query_vector)}")
        audio_candidates = [r for r in rows if r.get('kind') == 'audio']
        if not audio_candidates:
            return {}

        from ai_search import revision
        eligible = {r['id']: revision(r) for r in audio_candidates}
        scores = {}

        candidate_ids = list(eligible.keys())
        seg_count = 0
        use_native = _score_packed is _ORIG_SCORE_PACKED and native_accel.available()
        with self.ai.store.connect() as db:
            for i in range(0, len(candidate_ids), ROW_BATCH_SIZE):
                if check:
                    check()
                batch_ids = candidate_ids[i:i + ROW_BATCH_SIZE]
                placeholders = ','.join('?' for _ in batch_ids)
                sql = (f"SELECT item_id, source_revision, segment_id, start_ms, end_ms, snippet, vector "
                       f"FROM ai_audio_segments WHERE contract=? AND item_id IN ({placeholders}) "
                       f"ORDER BY item_id, start_ms")
                records = db.execute(sql, [CONTRACT, *batch_ids]).fetchall()
                native_meta = []
                native_chunks = []

                for item_id, src_rev, seg_id, start_ms, end_ms, snippet, data in records:
                    seg_count += 1
                    if check and seg_count % 256 == 0:
                        check()
                    if eligible.get(item_id) != src_rev:
                        continue
                    if not (type(start_ms) is int and type(end_ms) is int and 0 <= start_ms <= end_ms <= MAX_DURATION_MS):
                        continue
                    if use_native:
                        if isinstance(data, (bytes, bytearray, memoryview)) and len(data) == dimension * 4:
                            native_meta.append((item_id, seg_id, start_ms, end_ms, snippet))
                            native_chunks.append(bytes(data))
                    else:
                        dot = _score_packed(data, dimension, query_vector)
                        if dot is None:
                            continue
                        current_best = scores.get(item_id)
                        if current_best is None or dot > current_best[0]:
                            scores[item_id] = (dot, {
                                'start_ms': start_ms,
                                'end_ms': end_ms,
                                'snippet': snippet,
                                'segment_id': seg_id,
                            })
                if use_native and native_meta:
                    scores_arr, _, valid_arr = native_accel.score_f32_batch(
                        [query_vector], b''.join(native_chunks), len(native_meta), dimension, normalize_vec=True
                    )
                    for idx, (item_id, seg_id, start_ms, end_ms, snippet) in enumerate(native_meta):
                        if not valid_arr[idx]:
                            continue
                        dot = scores_arr[idx]
                        current_best = scores.get(item_id)
                        if current_best is None or dot > current_best[0]:
                            scores[item_id] = (dot, {
                                'start_ms': start_ms,
                                'end_ms': end_ms,
                                'snippet': snippet,
                                'segment_id': seg_id,
                            })

        return scores

    def put_segments(self, item_id, source_revision, segments):
        """Atomically replace time-coded speech segments for item_id."""
        if type(item_id) is not int or item_id <= 0:
            raise ValueError('Invalid item_id')
        if not isinstance(source_revision, str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', source_revision):
            raise ValueError('Invalid source revision')

        dimension = self.ai.profile.dimension
        packed_records = []
        seen_seg_ids = set()
        for idx, seg in enumerate(segments):
            if isinstance(seg, dict):
                start_ms = seg.get('start_ms')
                end_ms = seg.get('end_ms')
                raw_snippet = seg.get('snippet')
                vec = seg.get('vector')
                seg_id = str(seg.get('segment_id') or (f"seg_{idx:04d}_{start_ms:08d}" if type(start_ms) is int else f"seg_{idx:04d}"))
            elif isinstance(seg, (tuple, list)):
                if len(seg) == 5:
                    seg_id, start_ms, end_ms, raw_snippet, vec = seg
                    seg_id = str(seg_id)
                elif len(seg) == 4:
                    start_ms, end_ms, raw_snippet, vec = seg
                    seg_id = f"seg_{idx:04d}_{start_ms:08d}" if type(start_ms) is int else f"seg_{idx:04d}"
                else:
                    raise ValueError('Invalid segment tuple format')
            else:
                raise ValueError('Invalid segment format')

            if not seg_id:
                raise ValueError('Invalid segment_id')
            if seg_id in seen_seg_ids:
                raise ValueError(f"Duplicate segment_id: {seg_id}")
            seen_seg_ids.add(seg_id)

            if type(start_ms) is not int or type(end_ms) is not int or not (0 <= start_ms <= end_ms <= MAX_DURATION_MS):
                raise ValueError(f"Invalid segment timestamp: {start_ms} - {end_ms}")
            if not isinstance(raw_snippet, str):
                raise ValueError("Invalid segment snippet")
            snippet = raw_snippet.strip()
            if not snippet or len(snippet) > MAX_SNIPPET_LENGTH:
                raise ValueError("Invalid segment snippet")

            if isinstance(vec, (bytes, bytearray, memoryview)):
                if not _is_valid_packed(vec, dimension):
                    raise ValueError("Invalid packed vector blob")
                packed_vec = bytes(vec)
            else:
                packed_vec = array('f', normalized(vec, dimension)).tobytes()

            packed_records.append((item_id, source_revision, seg_id, start_ms, end_ms, snippet, packed_vec, CONTRACT))

        with self.ai.store.connect() as db:
            db.execute('DELETE FROM ai_audio_segments WHERE item_id=?', (item_id,))
            if packed_records:
                db.executemany(
                    'INSERT INTO ai_audio_segments VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                    packed_records
                )

    def get_segments(self, item_id, source_revision, include_vectors=True):
        """Retrieve ordered valid segments for an audio item."""
        if type(item_id) is not int or item_id <= 0:
            return []
        if not isinstance(source_revision, str):
            return []
        dimension = self.ai.profile.dimension
        with self.ai.store.connect() as db:
            rows = db.execute(
                "SELECT segment_id, start_ms, end_ms, snippet, vector FROM ai_audio_segments "
                "WHERE item_id=? AND source_revision=? AND contract=? ORDER BY start_ms",
                (item_id, source_revision, CONTRACT)
            ).fetchall()

        result = []
        for seg_id, start_ms, end_ms, snippet, data in rows:
            if include_vectors:
                vec = unpack(data, dimension, allocate=True)
                if vec is None:
                    continue
            else:
                if not _is_valid_packed(data, dimension):
                    continue
                vec = bytes(data)
            result.append({
                'segment_id': seg_id,
                'start_ms': start_ms,
                'end_ms': end_ms,
                'snippet': snippet,
                'vector': vec
            })
        return result

    def fresh(self, item_id, source_revision):
        """Check whether valid indexed speech segments exist for item_id at source_revision."""
        if type(item_id) is not int or item_id <= 0 or not isinstance(source_revision, str):
            return False
        dimension = self.ai.profile.dimension
        with self.ai.store.connect() as db:
            rows = db.execute(
                "SELECT vector FROM ai_audio_segments WHERE item_id=? AND source_revision=? AND contract=?",
                (item_id, source_revision, CONTRACT)
            ).fetchall()
        if not rows:
            return False
        return all(_is_valid_packed(data, dimension) for (data,) in rows)

    def delete_item(self, item_id):
        """Remove all speech segments for item_id."""
        if type(item_id) is not int or item_id <= 0:
            raise ValueError('Invalid item_id')
        with self.ai.store.connect() as db:
            db.execute("DELETE FROM ai_audio_segments WHERE item_id=?", (item_id,))
