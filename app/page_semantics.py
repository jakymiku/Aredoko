"""Explicit, bounded book-page embeddings; no OCR or source-media writes."""
from array import array
import itertools
import math
import operator
import re
import secrets
import threading
import time

from ai_process import AIUnavailable
from ai_vectors import normalized
from page_index import PageIndex, identifier, token
from previews import ReaderChanged

CONTRACT = 'book-page-image:v1'
MAX_PAGES = 16
_HEX64 = re.compile(r'[0-9a-f]{64}').fullmatch
SCHEMA = '''CREATE TABLE IF NOT EXISTS ai_page_vectors(
    item_id INTEGER NOT NULL, source_revision TEXT NOT NULL, page_id TEXT NOT NULL,
    page INTEGER NOT NULL CHECK(page>=0 AND page<10000), vector BLOB NOT NULL,
    contract TEXT NOT NULL, PRIMARY KEY(item_id,page_id));'''


def unpack(data, dimension):
    try:
        value = array('f'); value.frombytes(data)
        if len(value) != dimension or not all(map(math.isfinite, value)):
            return None
        squared_norm = sum(map(operator.mul, value, value))
        if abs(squared_norm-1) > 1e-4:
            return None
        # Reuse the validated sum, retaining the original sum/sqrt/division
        # arithmetic and float64 scores (including ties), not just unit length.
        norm = math.sqrt(squared_norm)
        return list(map(operator.truediv, value, itertools.repeat(norm)))
    except (ValueError, TypeError, OverflowError):
        return None


def _score_packed(data, dimension, query):
    """Unpack, validate and compute the exact float64 dot product without allocating a list."""
    try:
        value = array('f'); value.frombytes(data)
        if len(value) != dimension or not all(map(math.isfinite, value)):
            return None
        squared_norm = sum(map(operator.mul, value, value))
        if abs(squared_norm-1) > 1e-4:
            return None
        norm = math.sqrt(squared_norm)
        return sum(map(operator.mul, query, map(operator.truediv, value, itertools.repeat(norm))))
    except (ValueError, TypeError, OverflowError):
        return None


class PageVectors:
    def __init__(self, ai):
        self.ai = ai
        self.index = PageIndex(ai.catalog, ai.previews)

    def selection(self, item_id, page_ids, revision):
        """Caller holds catalog guard; metadata/physical checks, no inference."""
        with self.ai.catalog.connect() as db:
            self.index._allowed(db, item_id)
            head = self.index._head(db, item_id)
            if head is None or head['source_revision'] != revision:
                raise ReaderChanged('Page source changed')
            marks = ','.join('?' for _ in page_ids)
            pages = [dict(p) for p in db.execute('SELECT page_id,page FROM page_entries '
                'WHERE snapshot_id=? AND page_id IN ('+marks+') ORDER BY page', [head['id'], *page_ids])]
        if len(pages) != len(page_ids):
            raise KeyError('Page source unavailable')
        if self.index.state(item_id, revision) != 'current':
            raise ReaderChanged('Page source changed')
        return pages

    def coverage(self, item_id, revision, scope):
        """Read-only CPU status. Never refresh a snapshot, decode media or infer."""
        identifier(item_id); token(revision)
        ai = self.ai; scope = ai._scope(scope)
        if scope is None: raise ValueError('Explicit scope required')
        with ai.guard:
            if ai._closed: raise AIUnavailable('AI is closing')
        supported = 'cover' in ai.profile.modalities
        available = bool(ai.encoder.available)
        with ai.catalog._guard:
            ai.catalog._require_idle()
            row = ai._current_rows([item_id], scope).get(item_id)
            if row is None or row['kind'] not in ('book', 'archive'):
                raise KeyError('Page source unavailable')
            with ai.catalog.connect() as db:
                self.index._allowed(db, item_id)
                head = self.index._head(db, item_id)
                if head is None: raise KeyError('Page source unavailable')
                if head['source_revision'] != revision:
                    raise ReaderChanged('Page source changed')
                entries = {p['page_id']:p['page'] for p in db.execute(
                    'SELECT page_id,page FROM page_entries WHERE snapshot_id=?', (head['id'],))}
            count = head['page_count']
            if len(entries) != count or sorted(entries.values()) != list(range(count)):
                raise ReaderChanged('Page index changed')
            ready = set()
            if supported:
                # Stream one blob at a time. Matching IDs alone do not make a
                # malformed, old-revision or old-preprocessing vector ready.
                with ai.store.connect() as db:
                    for pid, page, data in db.execute(
                            'SELECT page_id,page,vector FROM ai_page_vectors '
                            'WHERE item_id=? AND source_revision=? AND contract=?',
                            (item_id, revision, CONTRACT)):
                        if entries.get(pid) == page and unpack(data, ai.profile.dimension) is not None:
                            ready.add(page)
            state = self.index.state(item_id, revision)
            if state != 'current': ready.clear()
        ranges = []
        for page in sorted(ready):
            if ranges and ranges[-1]['start']+ranges[-1]['count'] == page:
                ranges[-1]['count'] += 1
            else: ranges.append({'start':page, 'count':1})
        next_range = None
        if supported and state == 'current' and len(ready) < count:
            start = next(p for p in range(count) if p not in ready)
            stop = start
            while stop < count and stop not in ready and stop-start < MAX_PAGES: stop += 1
            next_range = {'start':start, 'count':stop-start}
        return {'item_id':item_id, 'source_revision':revision, 'source_state':state,
            'profile':ai.profile.key, 'model':ai.profile.label, 'supported':supported,
            'available':available, 'page_count':count, 'indexed_pages':len(ready),
            'remaining_pages':count-len(ready), 'indexed_ranges':ranges, 'next_range':next_range}

    def start(self, item_id, page_ids, revision, scope):
        from ai_search import AIBusy
        identifier(item_id); token(revision)
        if (type(page_ids) is not list or not 1 <= len(page_ids) <= MAX_PAGES
                or any(type(p) is not str for p in page_ids) or len(set(page_ids)) != len(page_ids)):
            raise ValueError('Invalid page selection')
        for p in page_ids: token(p)
        ai = self.ai
        scope = ai._scope(scope)
        if scope is None: raise ValueError('Explicit scope required')
        if not ai.encoder.available or 'cover' not in ai.profile.modalities:
            raise AIUnavailable('選択中のモデルでは画像のAI検索を利用できません。')
        with ai.guard:
            if ai._closed: raise AIUnavailable('AI is closing')
            if ai.worker and ai.worker.is_alive(): raise AIBusy('AI索引を作成中です。')
            with ai.catalog._guard:
                ai.catalog._require_idle()
                row = ai._current_rows([item_id], scope).get(item_id)
                if row is None or row['kind'] not in ('book', 'archive'):
                    raise KeyError('Page source unavailable')
                pages = self.selection(item_id, page_ids, revision)
            ai.cancel.clear()
            state = {'state':'running', 'job':'book-pages', 'job_id':secrets.token_hex(16), 'item_id':item_id,
                'source_revision':revision, 'processed':0, 'total':len(pages),
                'indexed':0, 'reused':0, 'skipped':0, 'error':'', 'scope':scope}
            ai.store.save_state(state)
            ai.worker = threading.Thread(target=self._build, args=(pages, state), daemon=True)
            ai.worker.start()
        return ai.status()

    def _build(self, pages, state):
        ai = self.ai; item_id = state['item_id']; revision = state['source_revision']
        try:
            with ai.inference:
                self._publish_range(pages, state, item_id, revision)
                state['indexed'] = len(pages)
                state['state'] = 'complete'
        except InterruptedError:
            state['state'] = 'cancelled'
        except Exception as ex:
            state['state'] = 'failed'
            state['error'] = 'ページ索引を保存できませんでした（'+type(ex).__name__+'）。元ファイル・登録範囲を確認して再実行してください。'
        finally:
            ai._last_activity = time.monotonic()
            with ai.guard: ai.store.save_state(state)

    def _publish_range(self, pages, state, item_id, revision):
        """Caller owns shared inference lock; publish one <=16-page range atomically."""
        ai = self.ai
        if ai.cancel.is_set(): raise InterruptedError()
        with ai.store.connect() as db:
            cached = {pid: unpack(data, ai.profile.dimension) for pid, data in db.execute(
                'SELECT page_id,vector FROM ai_page_vectors WHERE item_id=? AND source_revision=? AND contract=? '
                'AND page_id IN ('+','.join('?' for _ in pages)+')',
                [item_id, revision, CONTRACT, *[p['page_id'] for p in pages]])}
        packed = []
        for p in pages:
            if ai.cancel.is_set(): raise InterruptedError()
            vector = cached.get(p['page_id'])
            did_infer = vector is None
            if did_infer:
                payload = self.index.input(item_id, p['page_id'], revision)
                vector = normalized(ai.encoder.encode('image', payload['data']), ai.profile.dimension)
            else:
                state['reused'] += 1
            packed.append((item_id, revision, p['page_id'], p['page'], array('f', vector).tobytes(), CONTRACT))
            state['processed'] += 1
            with ai.guard: ai.store.save_state(state)
            if did_infer and state['processed'] < state['total'] and ai._index_pause_ms:
                if ai.cancel.wait(ai._index_pause_ms/1000): raise InterruptedError()
        # Never hold the catalog guard while running the model. Publish the
        # entire selected range only if the root/scope/page revision survived.
        with ai.catalog._guard:
            ai.catalog._require_idle()
            if ai._current_rows([item_id], state['scope']).get(item_id) is None:
                raise KeyError('Page source unavailable')
            self.selection(item_id, [p['page_id'] for p in pages], revision)
            if ai.cancel.is_set(): raise InterruptedError()
            with ai.store.connect() as db:
                db.execute('DELETE FROM ai_page_vectors WHERE item_id=? AND (source_revision<>? OR contract<>?)',
                           (item_id, revision, CONTRACT))
                db.executemany('INSERT OR REPLACE INTO ai_page_vectors VALUES(?,?,?,?,?,?)', packed)

    def rank(self, rows, query):
        """One best page per current book. Metadata checks only; no image decode."""
        ai = self.ai; result = {}
        ids = [r['id'] for r in rows if r['kind'] in ('book', 'archive')]
        if not ids or 'cover' not in ai.profile.modalities: return result
        dim = ai.profile.dimension; model_id = ai.profile.model_id
        model_rev = ai.profile.revision; profile_key = ai.profile.key
        hex64 = _HEX64
        with ai.store.connect() as db:
            for offset in range(0, len(ids), 256):
                batch = ids[offset:offset+256]
                # Stream at most a book's best score, never retain all page blobs.
                records = db.execute('SELECT item_id,source_revision,page_id,page,vector FROM ai_page_vectors '
                    'WHERE contract=? AND item_id IN ('+','.join('?' for _ in batch)+') ORDER BY item_id,page', [CONTRACT, *batch])
                for item_id, rev, pid, page, data in records:
                    if (type(page) is not int or not 0<=page<10000
                            or type(rev) is not str or hex64(rev) is None
                            or type(pid) is not str or hex64(pid) is None):
                        continue
                    score = _score_packed(data, dim, query)
                    if score is None: continue
                    if item_id not in result or score > result[item_id][0]:
                        result[item_id] = (score, {'source_revision':rev, 'source_state':'current',
                            'page_id':pid, 'page':page, 'model':model_id,
                            'model_revision':model_rev, 'profile':profile_key,
                            'preprocessing':CONTRACT, 'semantic_score':round(score, 6)})
        # A stale or unavailable source is omitted rather than presented as a
        # current page number. Reader checks the exact revision again on opening.
        # Keep one short catalog guard hold per candidate book while batching
        # catalog location SQL reads into 256-book chunks (invalidated immediately
        # if any root/exclusion/scan mutation increments catalog._state_epoch).
        candidate_ids = list(result)
        for offset in range(0, len(candidate_ids), 256):
            batch = candidate_ids[offset:offset+256]
            loc_rows = None
            cached_epoch = None
            root_cache = {}
            for pos, item_id in enumerate(batch):
                evidence = result[item_id][1]
                with ai.catalog._guard:
                    epoch = getattr(ai.catalog, '_state_epoch', 0)
                    if loc_rows is None or epoch != cached_epoch:
                        remaining = batch[pos:]
                        with ai.catalog.connect() as db:
                            marks = ','.join('?' for _ in remaining)
                            loc_rows = {row['item_id']: row for row in db.execute(
                                'SELECT m.item_id, l.*, r.path, r.excludes_json FROM item_locations m '
                                'JOIN library_locations l ON l.id=m.location_id '
                                'JOIN library_roots r ON r.id=l.root_id WHERE m.item_id IN (' + marks + ') AND r.enabled=1',
                                remaining)}
                        cached_epoch = epoch
                        root_cache.clear()
                    try:
                        source = self.index.previews._read(
                            item_id, operation='tag_source', row=loc_rows.get(item_id),
                            row_loaded=True, root_cache=root_cache)
                        state = 'current' if source['revision'] == evidence['source_revision'] else 'stale'
                    except Exception:
                        state = self.index.state(item_id, evidence['source_revision'], root_cache=root_cache)
                    if state != 'current':
                        del result[item_id]
        return result
