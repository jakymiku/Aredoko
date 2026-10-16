"""Persistent, revision-bound page evidence for images, archives and folder books.

No model, image decoding, extraction to disk or source-file mutation. Public
requests use item/page IDs only; page locators remain inside PreviewReader.
"""
import json
import re
import time

from library_index import _excluded
from previews import PreviewReader, PreviewUnavailable, PreviewBusyError, ReaderChanged


def identifier(value):
    if type(value) is not int or not 1 <= value <= 9223372036854775807:
        raise ValueError('Invalid item')
    return value


def token(value):
    if type(value) is not str or re.fullmatch(r'[0-9a-f]{64}', value) is None:
        raise ValueError('Invalid page identity or revision')
    return value


SCHEMA = '''
CREATE TABLE IF NOT EXISTS page_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES items(id),
    source_revision TEXT NOT NULL,
    source_kind TEXT NOT NULL CHECK(source_kind IN ('image','archive','folder')),
    page_count INTEGER NOT NULL CHECK(page_count BETWEEN 1 AND 10000),
    created_at REAL NOT NULL,
    UNIQUE(item_id, source_revision));
CREATE TABLE IF NOT EXISTS page_entries (
    snapshot_id INTEGER NOT NULL REFERENCES page_snapshots(id),
    page_id TEXT NOT NULL,
    page INTEGER NOT NULL CHECK(page BETWEEN 0 AND 9999),
    mime TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK(size_bytes>=0),
    PRIMARY KEY(snapshot_id,page_id),
    UNIQUE(snapshot_id,page));
CREATE TABLE IF NOT EXISTS page_heads (
    item_id INTEGER PRIMARY KEY REFERENCES items(id),
    snapshot_id INTEGER NOT NULL REFERENCES page_snapshots(id));
'''


class PageIndex:
    def __init__(self, catalog, previews=None):
        self.catalog = catalog
        self.previews = previews or PreviewReader(catalog)
        with catalog.connect() as db:
            db.executescript(SCHEMA)

    @staticmethod
    def _cancelled(cancelled):
        if cancelled and cancelled():
            raise InterruptedError('Page indexing cancelled; previous snapshot preserved')

    @staticmethod
    def _allowed(db, item_id):
        row = db.execute('SELECT l.status,l.relative_path,r.excludes_json,r.enabled '
            'FROM item_locations m JOIN library_locations l ON l.id=m.location_id '
            'JOIN library_roots r ON r.id=l.root_id WHERE m.item_id=?', (item_id,)).fetchone()
        if (row is None or not row['enabled'] or row['status'] == 'excluded'
                or _excluded(row['relative_path'], tuple(json.loads(row['excludes_json'])))):
            raise KeyError('Page source unavailable')

    @staticmethod
    def _head(db, item_id):
        return db.execute('SELECT s.* FROM page_heads h JOIN page_snapshots s '
                          'ON s.id=h.snapshot_id WHERE h.item_id=?', (item_id,)).fetchone()

    def refresh(self, item_id, cancelled=None):
        identifier(item_id)
        self._cancelled(cancelled)
        # Short, metadata-only work. Serialize with root edits/scan publication;
        # model inference must never run while this catalog guard is held.
        with self.catalog._guard:
            self.catalog._require_idle()
            manifest = self.previews.page_catalog(item_id)
            self._cancelled(cancelled)
            revision = token(manifest['revision'])
            pages = manifest['pages']
            if (manifest['item_id'] != item_id or not 1 <= len(pages) <= 10000
                    or len({p['page_id'] for p in pages}) != len(pages)
                    or [p['page'] for p in pages] != list(range(len(pages)))):
                raise ValueError('Invalid page manifest')
            with self.catalog.connect() as db:
                self._allowed(db, item_id)
                old = db.execute('SELECT id FROM page_snapshots WHERE item_id=? AND source_revision=?',
                                 (item_id, revision)).fetchone()
                if old:
                    snapshot_id = old['id']
                else:
                    snapshot_id = db.execute('INSERT INTO page_snapshots '
                        '(item_id,source_revision,source_kind,page_count,created_at) VALUES(?,?,?,?,?)',
                        (item_id, revision, manifest['source_kind'], len(pages), time.time())).lastrowid
                    for page in pages:
                        self._cancelled(cancelled)
                        db.execute('INSERT INTO page_entries VALUES(?,?,?,?,?)',
                            (snapshot_id, token(page['page_id']), page['page'], page['mime'], page['size_bytes']))
                # Physical changes cannot be hidden by the SQLite transaction.
                # A failure here rolls back entries and the new head together.
                if self.previews.tag_source(item_id)['revision'] != revision:
                    raise ReaderChanged('Source changed during page indexing')
                self._cancelled(cancelled)
                db.execute('INSERT INTO page_heads VALUES(?,?) ON CONFLICT(item_id) '
                           'DO UPDATE SET snapshot_id=excluded.snapshot_id', (item_id, snapshot_id))
            return {'item_id': item_id, 'source_revision': revision, 'source_kind': manifest['source_kind'],
                    'page_count': len(pages), 'reused': old is not None}

    def state(self, item_id, revision):
        """Called under the catalog guard; never treats busy as freshness."""
        try:
            return 'current' if self.previews.tag_source(item_id)['revision'] == revision else 'stale'
        except ReaderChanged:
            return 'stale'
        except PreviewBusyError:
            return 'unverified'
        except (PreviewUnavailable, OSError):
            return 'unavailable'

    def list(self, item_id, *, offset=0, limit=60, revision=None):
        identifier(item_id)
        if type(offset) is not int or not 0 <= offset <= 10000 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Invalid page list limits')
        if revision is not None:
            token(revision)
        if offset and revision is None:
            raise ValueError('A revision is required when paging')
        with self.catalog._guard:
            with self.catalog.connect() as db:
                self._allowed(db, item_id)
                head = self._head(db, item_id)
                if revision is not None and (head is None or head['source_revision'] != revision):
                    raise ReaderChanged('Page index changed; restart paging')
                if head is None:
                    return {'item_id': item_id, 'source_revision': None, 'source_kind': None,
                            'source_state': 'unindexed', 'page_count': 0, 'offset': offset, 'limit': limit, 'pages': []}
                pages = [dict(row) for row in db.execute('SELECT page_id,page,mime,size_bytes '
                    'FROM page_entries WHERE snapshot_id=? ORDER BY page LIMIT ? OFFSET ?',
                    (head['id'], limit, offset))]
            state = self.state(item_id, head['source_revision'])
            return {'item_id': item_id, 'source_revision': head['source_revision'], 'source_kind': head['source_kind'],
                    'source_state': state, 'page_count': head['page_count'], 'offset': offset, 'limit': limit, 'pages': pages}

    def input(self, item_id, page_id, revision):
        identifier(item_id)
        token(page_id)
        token(revision)
        with self.catalog._guard:
            with self.catalog.connect() as db:
                self._allowed(db, item_id)
                head = self._head(db, item_id)
                if head is None:
                    raise KeyError('Page index unavailable')
                if head['source_revision'] != revision:
                    raise ReaderChanged('Page index changed; refresh evidence')
                page = db.execute('SELECT page FROM page_entries WHERE snapshot_id=? AND page_id=?',
                                  (head['id'], page_id)).fetchone()
                if page is None:
                    raise KeyError('Page unavailable')
            payload = self.previews.page_input(item_id, page['page'], revision)
            if payload['source']['page_id'] != page_id:
                raise ReaderChanged('Page identity changed; refresh evidence')
            return payload
