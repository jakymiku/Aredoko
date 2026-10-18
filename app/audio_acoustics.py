"""Time-grounded audio acoustic & music feature embeddings, search, and similarity (R08/R09).

Candidate B: Dedicated 512D acoustic feature space strictly isolated from
the 768D text/speech and visual spaces. No cross-space inner products.
"""
from array import array
import itertools
import json
import math
import operator
import re

from ai_vectors import normalized

CONTRACT = 'audio-acoustic-feature:v1'
ACOUSTIC_DIMENSION = 512
MAX_AUDIO_BYTES = 512 * 1024 * 1024  # 512 MiB
MAX_DURATION_MS = 86_400_000         # 24 hours
MAX_DESCRIPTORS_COUNT = 64
MAX_DESCRIPTOR_LENGTH = 128
ROW_BATCH_SIZE = 500

SCHEMA = '''CREATE TABLE IF NOT EXISTS ai_audio_acoustics(
    item_id INTEGER NOT NULL,
    source_revision TEXT NOT NULL,
    at_ms INTEGER NOT NULL CHECK(at_ms>=0 AND at_ms<=86400000),
    vector BLOB NOT NULL,
    descriptors TEXT NOT NULL,
    contract TEXT NOT NULL,
    PRIMARY KEY(item_id, at_ms));'''


def unpack(data, dimension=ACOUSTIC_DIMENSION, allocate=True):
    """Unpack float32 acoustic vector blob, validate finite unit length, optionally allocate."""
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


def _is_valid_packed(data, dimension=ACOUSTIC_DIMENSION):
    """Validate stored float32 acoustic vector without allocating a list."""
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


class AudioAcousticVectors:
    def __init__(self, ai):
        self.ai = ai
        self.dimension = ACOUSTIC_DIMENSION

    def put_features(self, item_id, source_revision, features):
        """Atomically replace time-coded acoustic features for item_id."""
        if type(item_id) is not int or item_id <= 0:
            raise ValueError('Invalid item_id')
        if not isinstance(source_revision, str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', source_revision):
            raise ValueError('Invalid source revision')

        dimension = self.dimension
        packed_records = []
        seen_timestamps = set()

        for idx, feat in enumerate(features):
            if isinstance(feat, dict):
                at_ms = feat.get('at_ms')
                vec = feat.get('vector')
                raw_descriptors = feat.get('descriptors', [])
            elif isinstance(feat, (tuple, list)):
                if len(feat) == 3:
                    at_ms, vec, raw_descriptors = feat
                elif len(feat) == 2:
                    at_ms, vec = feat
                    raw_descriptors = []
                else:
                    raise ValueError('Invalid acoustic feature tuple format')
            else:
                raise ValueError('Invalid acoustic feature format')

            if type(at_ms) is not int or not (0 <= at_ms <= MAX_DURATION_MS):
                raise ValueError(f"Invalid acoustic feature timestamp: {at_ms}")
            if at_ms in seen_timestamps:
                raise ValueError(f"Duplicate acoustic feature timestamp: {at_ms}")
            seen_timestamps.add(at_ms)

            # Validate descriptors
            if isinstance(raw_descriptors, str):
                raw_descriptors = [d.strip() for d in raw_descriptors.split(',') if d.strip()]
            elif not isinstance(raw_descriptors, (list, tuple)):
                raise ValueError("Invalid descriptors format")

            if len(raw_descriptors) > MAX_DESCRIPTORS_COUNT:
                raise ValueError("Too many descriptors")

            cleaned_descriptors = []
            for d in raw_descriptors:
                if not isinstance(d, str):
                    raise ValueError("Descriptor must be a string")
                c = d.strip()
                if c and len(c) <= MAX_DESCRIPTOR_LENGTH and c not in cleaned_descriptors:
                    cleaned_descriptors.append(c)

            descriptors_json = json.dumps(cleaned_descriptors, ensure_ascii=False)

            # Validate and pack vector
            if isinstance(vec, (bytes, bytearray, memoryview)):
                if not _is_valid_packed(vec, dimension):
                    raise ValueError("Invalid packed acoustic vector blob")
                packed_vec = bytes(vec)
            else:
                if len(vec) != dimension:
                    raise ValueError(f"Acoustic vector dimension mismatch: expected {dimension}, got {len(vec)}")
                packed_vec = array('f', normalized(vec, dimension)).tobytes()

            packed_records.append((item_id, source_revision, at_ms, packed_vec, descriptors_json, CONTRACT))

        with self.ai.store.connect() as db:
            db.execute('DELETE FROM ai_audio_acoustics WHERE item_id=?', (item_id,))
            if packed_records:
                db.executemany(
                    'INSERT INTO ai_audio_acoustics VALUES (?, ?, ?, ?, ?, ?)',
                    packed_records
                )

    def get_features(self, item_id, source_revision, include_vectors=True):
        """Retrieve ordered valid acoustic features for an audio item."""
        if type(item_id) is not int or item_id <= 0:
            return []
        if not isinstance(source_revision, str):
            return []
        dimension = self.dimension
        with self.ai.store.connect() as db:
            rows = db.execute(
                "SELECT at_ms, vector, descriptors FROM ai_audio_acoustics "
                "WHERE item_id=? AND source_revision=? AND contract=? ORDER BY at_ms",
                (item_id, source_revision, CONTRACT)
            ).fetchall()

        result = []
        for at_ms, data, desc_json in rows:
            if include_vectors:
                vec = unpack(data, dimension, allocate=True)
                if vec is None:
                    continue
            else:
                if not _is_valid_packed(data, dimension):
                    continue
                vec = bytes(data)
            try:
                descriptors = json.loads(desc_json)
            except (ValueError, TypeError):
                descriptors = []
            result.append({
                'at_ms': at_ms,
                'vector': vec,
                'descriptors': descriptors
            })
        return result

    def acoustic_frames(self, row):
        """Current-revision acoustic frames [(at_ms, vector_512), ...]."""
        from ai_search import revision
        rev = revision(row)
        features = self.get_features(row['id'], rev, include_vectors=True)
        return [(f['at_ms'], f['vector']) for f in features]

    def fresh(self, item_id, source_revision):
        """Check whether valid indexed acoustic features exist for item_id at source_revision."""
        if type(item_id) is not int or item_id <= 0 or not isinstance(source_revision, str):
            return False
        dimension = self.dimension
        with self.ai.store.connect() as db:
            rows = db.execute(
                "SELECT vector FROM ai_audio_acoustics WHERE item_id=? AND source_revision=? AND contract=?",
                (item_id, source_revision, CONTRACT)
            ).fetchall()
        if not rows:
            return False
        return all(_is_valid_packed(data, dimension) for (data,) in rows)

    def delete_item(self, item_id):
        """Remove all acoustic features for item_id."""
        if type(item_id) is not int or item_id <= 0:
            raise ValueError('Invalid item_id')
        with self.ai.store.connect() as db:
            db.execute("DELETE FROM ai_audio_acoustics WHERE item_id=?", (item_id,))

    def rank(self, rows, query, query_vector=None, check=None):
        """Rank audio candidate rows against query using descriptive acoustic descriptors.

        Matches Japanese acoustic/music descriptors (e.g. '雨音', 'ピアノ', 'ジャズ', '爆発音')
        without hallucinating on silent WAVs.
        """
        if not rows or not query or not isinstance(query, str):
            return {}
        audio_candidates = [r for r in rows if r.get('kind') == 'audio']
        if not audio_candidates:
            return {}

        from ai_search import revision, normalize
        eligible = {r['id']: revision(r) for r in audio_candidates}
        scores = {}

        candidate_ids = list(eligible.keys())
        query_norm = normalize(query)
        query_words = [w for w in query_norm.split() if w]
        if not query_words and not query_norm:
            return {}

        rec_count = 0
        with self.ai.store.connect() as db:
            for i in range(0, len(candidate_ids), ROW_BATCH_SIZE):
                if check:
                    check()
                batch_ids = candidate_ids[i:i + ROW_BATCH_SIZE]
                placeholders = ','.join('?' for _ in batch_ids)
                sql = (f"SELECT item_id, source_revision, at_ms, descriptors "
                       f"FROM ai_audio_acoustics WHERE contract=? AND item_id IN ({placeholders}) "
                       f"ORDER BY item_id, at_ms")
                records = db.execute(sql, [CONTRACT, *batch_ids]).fetchall()

                for item_id, src_rev, at_ms, desc_json in records:
                    rec_count += 1
                    if check and rec_count % 256 == 0:
                        check()
                    if eligible.get(item_id) != src_rev:
                        continue
                    if not (type(at_ms) is int and 0 <= at_ms <= MAX_DURATION_MS):
                        continue
                    try:
                        descriptors = json.loads(desc_json)
                    except (ValueError, TypeError):
                        continue
                    if not descriptors:
                        continue

                    # Score matching descriptors
                    best_match_term = None
                    best_match_score = 0.0
                    for desc in descriptors:
                        desc_norm = normalize(desc)
                        if query_norm == desc_norm:
                            score = 0.98
                        elif query_norm in desc_norm or desc_norm in query_norm:
                            score = 0.92
                        elif any(qw in desc_norm or desc_norm in qw for qw in query_words):
                            score = 0.85
                        else:
                            continue
                        if score > best_match_score:
                            best_match_score = score
                            best_match_term = desc

                    if best_match_score > 0.0:
                        current = scores.get(item_id)
                        if current is None or best_match_score > current[0]:
                            scores[item_id] = (best_match_score, {
                                'start_ms': at_ms,
                                'end_ms': at_ms,
                                'snippet': f"音響特徴: {best_match_term}",
                                'segment_id': f"acoustic_{item_id}_{at_ms}"
                            })

        return scores

    def score_candidates(self, rows, origin_frames, check=None):
        """Score candidate audio rows against origin_frames using 512D acoustic vectors.

        Multi-frame max aggregation, returning (scores, audio_hits, origin_hits).
        """
        if not rows or not origin_frames:
            return {}, {}, {}

        # Strictly enforce space isolation!
        for orig_ms, orig_vec in origin_frames:
            if len(orig_vec) != self.dimension:
                raise ValueError(f"Cross-space vector comparison rejected: acoustic dimension {self.dimension} required, got {len(orig_vec)}")

        from ai_search import revision
        audio_candidates = [r for r in rows if r.get('kind') == 'audio']
        if not audio_candidates:
            return {}, {}, {}

        eligible = {r['id']: revision(r) for r in audio_candidates}
        scores = {}
        audio_hits = {}
        origin_hits = {}

        candidate_ids = list(eligible.keys())
        eval_count = 0
        dimension = self.dimension

        with self.ai.store.connect() as db:
            for i in range(0, len(candidate_ids), ROW_BATCH_SIZE):
                if check:
                    check()
                batch_ids = candidate_ids[i:i + ROW_BATCH_SIZE]
                placeholders = ','.join('?' for _ in batch_ids)
                sql = (f"SELECT item_id, source_revision, at_ms, vector "
                       f"FROM ai_audio_acoustics WHERE contract=? AND item_id IN ({placeholders}) "
                       f"ORDER BY item_id, at_ms")
                records = db.execute(sql, [CONTRACT, *batch_ids]).fetchall()

                for item_id, src_rev, cand_ms, data in records:
                    eval_count += 1
                    if check and eval_count % 256 == 0:
                        check()
                    if eligible.get(item_id) != src_rev:
                        continue
                    if not (type(cand_ms) is int and 0 <= cand_ms <= MAX_DURATION_MS):
                        continue

                    for orig_ms, orig_vec in origin_frames:
                        dot = _score_packed(data, dimension, orig_vec)
                        if dot is None:
                            continue
                        prev = scores.get(item_id)
                        if prev is None or dot > prev:
                            scores[item_id] = dot
                            audio_hits[item_id] = cand_ms
                            origin_hits[item_id] = orig_ms

        return scores, audio_hits, origin_hits
