"""Request-local exact score fusion with bounded Python buffers.

Internal R02 engine. Callers must still enumerate/revalidate the full catalog,
check model/source identity, and connect cancellation; this is not a snapshot.
"""
from contextlib import contextmanager
import json
import math
from pathlib import Path
import sqlite3
import tempfile

from ai_ranking import POLICIES, RRF_K
from ai_result_groups import boundary

BATCH_SIZE = 256
MAX_MODES = 16
MAX_PAYLOAD_BYTES = 65_536


class SearchCancelled(RuntimeError):
    pass


class ScoreSpoolError(RuntimeError):
    pass


class ScoreSpool:
    """One disposable SQLite DB; scores retain their exact Python hex value."""

    def __init__(self, *, cancelled=None, parent=None, max_bytes=256 * 1024 * 1024):
        if type(max_bytes) is not int or not 65_536 <= max_bytes <= 256 * 1024 * 1024:
            raise ValueError('Invalid score workspace limit')
        if cancelled is not None and not callable(cancelled):
            raise ValueError('Invalid cancellation callback')
        self._cancelled = cancelled or (lambda: False)
        self._closed = False; self._failed = False; self._policy = None; self._modes = set()
        self._directory = tempfile.TemporaryDirectory(prefix='aredoko-query-', dir=parent)
        self.path = Path(self._directory.name) / 'scores.sqlite'
        self._db = None
        try:
            self._db = sqlite3.connect(self.path)
            self._db.execute('PRAGMA page_size=4096')
            self._db.execute('PRAGMA max_page_count=' + str(max_bytes // 4096))
            self._db.execute('PRAGMA cache_size=-8192')
            self._db.execute('PRAGMA temp_store=FILE')
            self._db.execute('PRAGMA threads=1')
            self._db.executescript('''
                CREATE TABLE candidates(item_id INTEGER PRIMARY KEY, literal_hits INTEGER NOT NULL,
                    literal_words INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE scores(item_id INTEGER NOT NULL, mode TEXT NOT NULL, ordinal INTEGER NOT NULL,
                    value REAL NOT NULL, exact TEXT NOT NULL, contribution TEXT,
                    PRIMARY KEY(item_id,mode));
                CREATE INDEX scores_mode ON scores(mode,value DESC,item_id);
                CREATE TABLE results(item_id INTEGER PRIMARY KEY, value REAL NOT NULL, exact TEXT NOT NULL);
                CREATE INDEX results_order ON results(value DESC,item_id);
            ''')
            self._db.set_progress_handler(lambda: int(self._cancelled()), 1000)
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self._closed: return
        self._closed = True
        try:
            if self._db is not None: self._db.close()
        finally:
            self._directory.cleanup()

    def _check(self):
        if self._closed or self._failed: raise ScoreSpoolError('Score workspace is unavailable')
        if self._cancelled(): raise SearchCancelled('Search cancelled')

    @contextmanager
    def _operation(self):
        self._check()
        try:
            yield
        except sqlite3.Error as error:
            self._failed = True
            if self._cancelled(): raise SearchCancelled('Search cancelled') from error
            raise ScoreSpoolError('Score workspace failed; retry the search') from error

    def _records(self, sql, params=()):
        with self._operation():
            cursor = self._db.execute(sql, params)
            try:
                while True:
                    self._check()
                    batch = cursor.fetchmany(BATCH_SIZE)
                    if not batch: break
                    yield from batch
            finally:
                cursor.close()

    def add(self, item_id, modes, *, literal_hits=0, literal_words=0, payload=None):
        """One already-aggregated item; never supply page vectors or metadata lists."""
        self._check()
        if self._policy is not None: raise ScoreSpoolError('Scores already finalized')
        if type(item_id) is not int or not 1 <= item_id <= 9223372036854775807:
            raise ValueError('Invalid score item')
        if not isinstance(modes, dict) or not 1 <= len(modes) <= MAX_MODES:
            raise ValueError('Invalid modality scores')
        values = []
        for ordinal, (mode, value) in enumerate(modes.items()):
            if (not isinstance(mode, str) or not 1 <= len(mode) <= 32 or
                    type(value) not in (int, float)):
                raise ValueError('Invalid modality score')
            try:
                value = float(value)
            except OverflowError as error:
                raise ValueError('Invalid modality score') from error
            if not math.isfinite(value): raise ValueError('Invalid modality score')
            values.append((item_id, mode, ordinal, value, value.hex()))
        if len(self._modes | set(modes)) > MAX_MODES:
            raise ValueError('Too many global modalities')
        if (type(literal_hits) is not int or type(literal_words) is not int or
                not 0 <= literal_hits <= literal_words <= 300):
            raise ValueError('Invalid literal evidence')
        if payload is not None and not isinstance(payload, dict): raise ValueError('Invalid score evidence')
        packed = json.dumps(payload or {}, ensure_ascii=False, allow_nan=False)
        if len(packed.encode('utf-8')) > MAX_PAYLOAD_BYTES: raise ValueError('Score evidence exceeds limit')
        with self._operation():
            self._db.execute('INSERT INTO candidates VALUES(?,?,?,?)',
                             (item_id, literal_hits, literal_words, packed))
            self._db.executemany('INSERT INTO scores(item_id,mode,ordinal,value,exact) VALUES(?,?,?,?,?)', values)
        self._modes.update(modes)

    def finalize(self, policy='max'):
        self._check()
        if policy not in POLICIES: raise ValueError('Unknown ranking policy')
        if self._policy is not None: raise ScoreSpoolError('Scores already finalized')
        pools = list(self._records('SELECT mode,count(*),min(value),max(value) FROM scores GROUP BY mode ORDER BY mode'))
        # The per-item cap alone does not bound distinct global modality names.
        if len(pools) > MAX_MODES: raise ValueError('Too many global modalities')
        spans = {mode: high / 2 - low / 2 for mode, _, low, high in pools}
        largest = max(spans.values(), default=0.)
        informative = len(pools) > 1 and all(count > 1 for _, count, _, _ in pools) and largest > 0
        weights = {mode: spans[mode] / largest if informative else 1. for mode, *_ in pools}
        if policy == 'mean-rrf':
            for mode, *_ in pools:
                position = 0
                for value, count in self._records('SELECT value,count(*) FROM scores WHERE mode=? GROUP BY value ORDER BY value DESC', (mode,)):
                    tied_position = ((position + 1) + (position + count)) / 2
                    contribution = weights[mode] / (RRF_K + tied_position)
                    with self._operation():
                        self._db.execute('UPDATE scores SET contribution=? WHERE mode=? AND value=?',
                                         (contribution.hex(), mode, value))
                    position += count
        current = None; modes = []

        def publish(item, entries):
            if item is None: return
            if policy == 'max':
                # Equal signed zeros preserve original modality insertion order.
                score = max(float.fromhex(exact) for _, _, exact, _ in sorted(entries, key=lambda entry: entry[1]))
            else:
                score = 0.
                # Cursor is sorted by modality, matching fuse_modalities.
                for _, _, _, contribution in entries: score += float.fromhex(contribution)
                denominator = sum(weights[mode] for mode, _, _, _ in sorted(entries, key=lambda entry: entry[1]))
                score = score / denominator if denominator > 0 else 0.
            with self._operation():
                self._db.execute('INSERT INTO results VALUES(?,?,?)', (item, score, score.hex()))

        for item, mode, ordinal, exact, contribution in self._records('SELECT item_id,mode,ordinal,exact,contribution FROM scores ORDER BY item_id,mode'):
            if current != item:
                publish(current, modes); current = item; modes = []
            modes.append((mode, ordinal, exact, contribution))
        publish(current, modes)
        with self._operation(): self._db.commit()
        self._policy = policy

    def ranked(self):
        if self._policy is None: raise ScoreSpoolError('Scores not finalized')
        for item, exact in self._records('SELECT item_id,exact FROM results ORDER BY value DESC,item_id'):
            yield item, float.fromhex(exact)

    def page(self, page=0, limit=60, *, literal_only=False, group_threshold=None, result_group='all'):
        if self._policy is None: raise ScoreSpoolError('Scores not finalized')
        if type(page) is not int or page < 0 or type(limit) is not int or not 1 <= limit <= 120:
            raise ValueError('Invalid paging')
        if type(literal_only) is not bool or result_group not in ('all', 'leading', 'other'):
            raise ValueError('Invalid result filter')
        # No unbounded Python integer may overflow SQLite's OFFSET parameter.
        offset = page * limit
        score_kind = 'reciprocal-rank' if self._policy == 'mean-rrf' else 'cosine'
        clause = ' WHERE c.literal_hits=c.literal_words' if literal_only else ''
        join = ' FROM results r JOIN candidates c ON c.item_id=r.item_id'
        top = [(item, float.fromhex(exact)) for item, exact in self._records(
            'SELECT r.item_id,r.exact' + join + clause + ' ORDER BY r.value DESC,r.item_id LIMIT 32')]
        cut = boundary(top, score_kind, group_threshold)
        total = next(self._records('SELECT count(*)' + join + clause))[0]
        leading = total if cut is None else next(self._records(
            'SELECT count(*)' + join + clause + (' AND ' if clause else ' WHERE ') + 'r.value>=?', (cut,)))[0]
        other = total - leading
        params = []
        if result_group == 'leading' and cut is not None:
            clause += (' AND ' if clause else ' WHERE ') + 'r.value>=?'; params.append(cut)
        elif result_group == 'other':
            clause += (' AND ' if clause else ' WHERE ') + ('0=1' if cut is None else 'r.value<?')
            if cut is not None: params.append(cut)
        selected = other if result_group == 'other' else leading if result_group == 'leading' else total
        rows = [] if offset >= selected else list(self._records(
            'SELECT r.item_id,r.exact' + join + clause + ' ORDER BY r.value DESC,r.item_id LIMIT ? OFFSET ?', params + [limit, offset]))
        return {'total': selected, 'page': page, 'limit': limit,
                'ranked': [(item, float.fromhex(exact)) for item, exact in rows],
                'group_boundary': cut, 'leading_total': leading, 'other_total': other}

    def evidence(self, ids):
        self._check()
        if not isinstance(ids, (list, tuple)) or len(ids) > 120 or any(type(item) is not int or not 1 <= item <= 9223372036854775807 for item in ids):
            raise ValueError('Invalid evidence page')
        if not ids: return {}
        return {item: json.loads(payload) for item, payload in self._records(
            'SELECT item_id,payload FROM candidates WHERE item_id IN (' + ','.join('?' for _ in ids) + ')', ids)}
