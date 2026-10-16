"""Explicit, bounded book-page embeddings; no OCR or source-media writes."""
from array import array
import math
import secrets
import threading
import time

from ai_process import AIUnavailable
from ai_vectors import normalized
from page_index import PageIndex, identifier, token
from previews import ReaderChanged

CONTRACT = 'book-page-image:v1'
MAX_PAGES = 16
SCHEMA = '''CREATE TABLE IF NOT EXISTS ai_page_vectors(
    item_id INTEGER NOT NULL, source_revision TEXT NOT NULL, page_id TEXT NOT NULL,
    page INTEGER NOT NULL CHECK(page>=0 AND page<10000), vector BLOB NOT NULL,
    contract TEXT NOT NULL, PRIMARY KEY(item_id,page_id));'''


def unpack(data, dimension):
    try:
        value = array('f'); value.frombytes(data)
        if (len(value) != dimension or any(not math.isfinite(x) for x in value)
                or abs(sum(x*x for x in value)-1) > 1e-4):
            return None
        return normalized(value, dimension)
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

    def rank(self, rows, query):
        """One best page per current book. Metadata checks only; no image decode."""
        ai = self.ai; result = {}
        ids = [r['id'] for r in rows if r['kind'] in ('book', 'archive')]
        if not ids or 'cover' not in ai.profile.modalities: return result
        for offset in range(0, len(ids), 256):
            batch = ids[offset:offset+256]
            with ai.store.connect() as db:
                # Stream at most a book's best score, never retain all page blobs.
                records = db.execute('SELECT item_id,source_revision,page_id,page,vector FROM ai_page_vectors '
                    'WHERE contract=? AND item_id IN ('+','.join('?' for _ in batch)+') ORDER BY item_id,page', [CONTRACT, *batch])
                for item_id, rev, pid, page, data in records:
                    if type(page) is not int or not 0<=page<10000:continue
                    try:token(rev);token(pid)
                    except ValueError:continue
                    vec = unpack(data, ai.profile.dimension)
                    if vec is None: continue
                    score = sum(a*b for a,b in zip(query, vec))
                    if item_id not in result or score > result[item_id][0]:
                        result[item_id] = (score, {'source_revision':rev, 'source_state':'current',
                            'page_id':pid, 'page':page, 'model':ai.profile.model_id,
                            'model_revision':ai.profile.revision, 'profile':ai.profile.key,
                            'preprocessing':CONTRACT, 'semantic_score':round(score, 6)})
        # A stale or unavailable source is omitted rather than presented as a
        # current page number. Reader checks the exact revision again on opening.
        for item_id, (_, evidence) in list(result.items()):
            with ai.catalog._guard:
                if self.index.state(item_id, evidence['source_revision']) != 'current':
                    del result[item_id]
        return result
