"""Optional page text extraction and explicit evidence search, separate from tags.

The default extractor is absent. Trusted local adapters provide .info.record()
and .extract(payload, cancelled) -> str; they must own/release their runtime and
honor cancellation. No public path/model/text injection and no implicit downloads.
"""
from shelves import shelf_clause
import json
import hashlib
import re
import threading
import time

from ai_process import AIUnavailable
from ai_search import AIBusy
from library_index import TYPES, _excluded
from media_filters import QUERY_KINDS,kind_clause,tag_clause
from page_index import identifier, token
from previews import ReaderChanged
from search_terms import normalize_document, split_terms

MAX_PAGES = 16
MAX_TEXT = 20000
MAX_BATCH_TEXT = 100000

SCHEMA = '''
CREATE TABLE IF NOT EXISTS page_texts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL,
    page_id TEXT NOT NULL,
    producer_key TEXT NOT NULL,
    producer_json TEXT NOT NULL,
    text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY(snapshot_id,page_id) REFERENCES page_entries(snapshot_id,page_id),
    UNIQUE(snapshot_id,page_id,producer_key));
CREATE TABLE IF NOT EXISTS page_text_heads (
    snapshot_id INTEGER NOT NULL,
    page_id TEXT NOT NULL,
    text_id INTEGER NOT NULL REFERENCES page_texts(id),
    PRIMARY KEY(snapshot_id,page_id),
    FOREIGN KEY(snapshot_id,page_id) REFERENCES page_entries(snapshot_id,page_id));
'''


class PageTextIndex:
    def __init__(self, catalog, pages, extractor=None):
        self.catalog, self.pages, self.extractor = catalog, pages, extractor
        self._job_guard = threading.Lock()
        self._active = None
        with catalog.connect() as db:
            db.executescript(SCHEMA)

    def status(self):
        if self.extractor is None:
            return {'available': False, 'reason': '文字抽出モデルは未接続です。保存済みのページ本文は検索できます。'}
        check = getattr(self.extractor, 'status', None)
        return check() if check else {'available': True, 'reason': ''}

    @staticmethod
    def _request(value):
        if type(value) is not str or re.fullmatch('[0-9a-f]{32}', value) is None:
            raise ValueError('Invalid extraction request ID')

    def cancel(self, request_id):
        self._request(request_id)
        with self._job_guard:
            matched = self._active is not None and self._active[0] == request_id
            if matched:
                self._active[1].set()
        return {'cancel_requested': matched}

    @staticmethod
    def _check_cancel(cancelled):
        if cancelled.is_set():
            raise AIBusy('Page text extraction cancelled; no text saved')

    def generate(self, item_id, page_ids, revision, request_id):
        identifier(item_id)
        token(revision)
        self._request(request_id)
        if type(page_ids) is not list or not 1 <= len(page_ids) <= MAX_PAGES:
            raise ValueError('Choose 1 to 16 pages')
        for value in page_ids:
            token(value)
        if len(set(page_ids)) != len(page_ids):
            raise ValueError('Repeated page ID')
        status = self.status()
        if not status['available']:
            raise AIUnavailable(status['reason'])
        try:
            producer = self.extractor.info.record()
            producer_json = json.dumps(producer, sort_keys=True, ensure_ascii=False)
            if (set(producer) != {'adapter','version','model','model_revision','preprocessing'}
                    or any(type(v) is not str or not 1 <= len(v) <= 256
                           or any(ord(c) < 32 for c in v) for v in producer.values())):
                raise ValueError('Invalid producer')
            key = hashlib.sha256(producer_json.encode()).hexdigest()
        except Exception as error:
            raise AIUnavailable('Invalid page text extractor configuration') from error
        cancelled = threading.Event()
        with self._job_guard:
            if self._active is not None:
                raise AIBusy('Page text extraction in progress')
            self._active = request_id, cancelled
        try:
            with self.catalog._guard:
                self.catalog._require_idle()
                with self.catalog.connect() as db:
                    self.pages._allowed(db, item_id)
                    head = self.pages._head(db, item_id)
                    if head is None:
                        raise KeyError('Page index unavailable')
                    if head['source_revision'] != revision:
                        raise ReaderChanged('Page index changed')
                    pending = []
                    for page_id in page_ids:
                        if not db.execute('SELECT 1 FROM page_entries WHERE snapshot_id=? AND page_id=?',
                                          (head['id'], page_id)).fetchone():
                            raise KeyError('Page unavailable')
                        if not db.execute('SELECT 1 FROM page_texts WHERE snapshot_id=? AND page_id=? AND producer_key=?',
                                          (head['id'], page_id, key)).fetchone():
                            pending.append(page_id)
            extracted, total = [], 0
            for page_id in pending:
                self._check_cancel(cancelled)
                payload = self.pages.input(item_id, page_id, revision)
                # No catalog/SQLite lock during model work. The adapter gets
                # only this checked image and its opaque page provenance.
                try:
                    value = self.extractor.extract(payload, cancelled.is_set)
                except (AIUnavailable, AIBusy):
                    raise
                except Exception as error:
                    raise AIUnavailable('Page text extraction failed; no text saved') from error
                self._check_cancel(cancelled)
                if (type(value) is not str or len(value) > MAX_TEXT
                        or any((ord(c) < 32 and c not in '\n\r\t')
                               or 0xd800 <= ord(c) <= 0xdfff for c in value)):
                    raise AIUnavailable('Invalid page text output; no text saved')
                total += len(value)
                if total > MAX_BATCH_TEXT:
                    raise AIUnavailable('Page text batch exceeds limit; no text saved')
                extracted.append((page_id, value))
            try:
                same_producer = self.extractor.info.record() == producer
            except Exception:
                same_producer = False
            if not same_producer:
                raise AIBusy('Page text extractor changed; retry')
            with self.catalog._guard:
                self.catalog._require_idle()
                with self._job_guard:
                    self._check_cancel(cancelled)
                    with self.catalog.connect() as db:
                        self.pages._allowed(db, item_id)
                        current = self.pages._head(db, item_id)
                        if current is None or current['id'] != head['id']:
                            raise ReaderChanged('Page index changed')
                        for page_id, value in extracted:
                            db.execute('INSERT OR IGNORE INTO page_texts '
                                '(snapshot_id,page_id,producer_key,producer_json,text,normalized_text,created_at) '
                                'VALUES(?,?,?,?,?,?,?)', (head['id'], page_id, key, producer_json,
                                                       value, normalize_document(value), time.time()))
                        for page_id in page_ids:
                            row = db.execute('SELECT id FROM page_texts WHERE snapshot_id=? AND page_id=? AND producer_key=?',
                                             (head['id'], page_id, key)).fetchone()
                            db.execute('INSERT INTO page_text_heads VALUES(?,?,?) ON CONFLICT(snapshot_id,page_id) '
                                'DO UPDATE SET text_id=excluded.text_id', (head['id'], page_id, row['id']))
                        if self.pages.previews.tag_source(item_id)['revision'] != revision:
                            raise ReaderChanged('Source changed during text extraction')
                    self._active = None
            return {'item_id': item_id, 'source_revision': revision,
                    'processed': len(extracted), 'reused': len(page_ids) - len(extracted)}
        finally:
            with self._job_guard:
                if self._active is not None and self._active[1] is cancelled:
                    self._active = None

    def list(self, item_id, *, offset=0, limit=10, revision=None):
        identifier(item_id)
        if type(offset) is not int or not 0 <= offset <= 10000 or type(limit) is not int or not 1 <= limit <= 10:
            raise ValueError('Invalid text paging')
        if revision is not None:
            token(revision)
        if offset and revision is None:
            raise ValueError('A revision is required when paging')
        with self.catalog._guard:
            with self.catalog.connect() as db:
                self.pages._allowed(db, item_id)
                head = self.pages._head(db, item_id)
                if revision is not None and (head is None or head['source_revision'] != revision):
                    raise ReaderChanged('Page index changed')
                if head is None:
                    return {'item_id': item_id, 'source_revision': None, 'source_state': 'unindexed',
                            'total': 0, 'offset': offset, 'limit': limit, 'pages': []}
                clause = (' FROM page_text_heads h JOIN page_texts t ON t.id=h.text_id '
                          'JOIN page_entries e ON e.snapshot_id=t.snapshot_id AND e.page_id=t.page_id '
                          'WHERE h.snapshot_id=?')
                total = db.execute('SELECT count(*)' + clause, (head['id'],)).fetchone()[0]
                rows = db.execute('SELECT e.page,e.page_id,t.text,t.producer_json' + clause +
                                  ' ORDER BY e.page LIMIT ? OFFSET ?', (head['id'], limit, offset)).fetchall()
                pages = [{**dict(row), 'producer': json.loads(row['producer_json'])} for row in rows]
                for row in pages:
                    row.pop('producer_json')
            return {'item_id': item_id, 'source_revision': head['source_revision'],
                    'source_state': self.pages.state(item_id, head['source_revision']),
                    'total': total, 'offset': offset, 'limit': limit, 'pages': pages}

    def search(self, query, *, kind='', view='all', page=0, root_ids=None, shelf=None, model=None, shelf_ids=None, tag=None):
        if type(query) is not str or not 1 <= len(query) <= 300:
            raise ValueError('Invalid text query')
        terms = split_terms(query)
        if not terms or kind not in ('', *QUERY_KINDS) or view not in ('all','favorites','unreviewed','shelf'):
            raise ValueError('Invalid text filter')
        if type(page) is not int or not 0 <= page <= 1000000:
            raise ValueError('Invalid text paging')
        if root_ids is not None:
            if type(root_ids) is not list or not 1 <= len(root_ids) <= 256:
                raise ValueError('Invalid roots')
            for value in root_ids:
                identifier(value)
            if len(set(root_ids)) != len(root_ids):
                raise ValueError('Repeated root')
        if shelf is not None and (type(shelf) is not str or len(shelf) > 80):
            raise ValueError('Invalid shelf')
        if model is not None and (type(model) is not str or not 1 <= len(model) <= 256):
            raise ValueError('Invalid model')
        tag_where, tag_values = tag_clause(tag)
        with self.catalog._guard:
            with self.catalog.connect() as db:
                # Apply current root rules even before the next scan. Historical
                # text must not bring an excluded or unregistered item back.
                rules = {row['id']: tuple(json.loads(row['excludes_json'])) for row in
                         db.execute('SELECT id,excludes_json FROM library_roots WHERE enabled=1')}
                db.create_function('aredoko_page_visible', 2,
                    lambda root, relative: root in rules and not _excluded(relative, rules[root]),
                    deterministic=True)
                where = ["l.status='present'", 'aredoko_page_visible(l.root_id,l.relative_path)']
                values = []
                if root_ids is not None:
                    placeholders = ','.join('?' for _ in root_ids)
                    active = db.execute(f'SELECT count(*) FROM library_roots WHERE enabled=1 AND id IN ({placeholders})', root_ids).fetchone()[0]
                    if active != len(root_ids):
                        raise ValueError('Unknown registered root')
                    where.append(f'l.root_id IN ({placeholders})')
                    values.extend(root_ids)
                clauses,parameters=kind_clause(kind);where.extend(clauses);values.extend(parameters)
                where.extend({'all': [], 'favorites': ['i.favorite=1'], 'unreviewed': ['i.reviewed=0'], 'shelf': ["i.shelf<>''"]}[view])
                shelf_where,shelf_values=shelf_clause(shelf,shelf_ids)
                where.extend(shelf_where);values.extend(shelf_values)
                where.extend(tag_where);values.extend(tag_values)
                if model is not None:
                    where.append("json_extract(t.producer_json,'$.model')=?"); values.append(model)
                for term in terms:
                    where.append('instr(t.normalized_text,?)>0'); values.append(term)
                clause = (self.catalog.JOIN + ' JOIN page_heads ph ON ph.item_id=i.id '
                    'JOIN page_snapshots s ON s.id=ph.snapshot_id '
                    'JOIN page_text_heads th ON th.snapshot_id=s.id '
                    'JOIN page_texts t ON t.id=th.text_id '
                    'JOIN page_entries e ON e.snapshot_id=t.snapshot_id AND e.page_id=t.page_id '
                    'WHERE ' + ' AND '.join(where))
                total = db.execute('SELECT count(DISTINCT i.id)' + clause, values).fetchone()[0]
                rows = db.execute('SELECT ' + self.catalog.FIELDS + ',s.source_revision,count(*) AS matching_pages' +
                    clause + ' GROUP BY i.id ORDER BY i.id LIMIT 20 OFFSET ?', values + [page * 20]).fetchall()
                items = []
                for raw in rows:
                    row = dict(raw)
                    revision = row.pop('source_revision')
                    count = row.pop('matching_pages')
                    item = self.catalog.item(row)
                    evidence = db.execute('SELECT e.page_id,e.page,t.text,t.producer_json' + clause +
                        ' AND i.id=? ORDER BY e.page LIMIT 3', values + [item['id']]).fetchall()
                    item['page_text_match'] = {'source_revision': revision, 'source_state': self.pages.state(item['id'], revision),
                        'matching_pages': count, 'pages': [{'page_id': r['page_id'], 'page': r['page'],
                            'excerpt': r['text'][:240], 'producer': json.loads(r['producer_json'])} for r in evidence]}
                    items.append(item)
            return {'search_mode': 'page-text', 'total': total, 'page': page, 'limit': 20, 'items': items}
