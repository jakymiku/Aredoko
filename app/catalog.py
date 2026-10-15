"""Shared catalog prototype. No media filesystem access; fictional records only."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

KINDS = ('book', 'image', 'video', 'audio')
THEMES = ('雨の街', '夜の図書館', '青い海', '森の散歩', '古い紙', '静かな部屋', '夕焼け', '星空')


def validate_tags(tags):
    if not isinstance(tags, list) or len(tags) > 30 or any(not isinstance(t, str) or not 1 <= len(t.strip()) <= 60 for t in tags):
        raise ValueError('Tags must contain 1 to 60 characters, at most 30 tags')
    return list(dict.fromkeys(t.strip() for t in tags))


class Catalog:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS items (
                  id INTEGER PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL,
                  tags TEXT NOT NULL, shelf TEXT NOT NULL DEFAULT '',
                  favorite INTEGER NOT NULL DEFAULT 0, reviewed INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS items_kind ON items(kind, id);
                CREATE INDEX IF NOT EXISTS items_favorite ON items(favorite, id);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def seed(self, count=50000):
        with self.connect() as db:
            if db.execute('SELECT count(*) FROM items').fetchone()[0]:
                return
            db.executemany('INSERT INTO items(id,title,kind,tags) VALUES(?,?,?,?)', (
                (i, f'{THEMES[(i // 4) % len(THEMES)]} — Sample {i:05}', KINDS[i % 4],
                 json.dumps([THEMES[(i // 4) % len(THEMES)], 'サンプル'], ensure_ascii=False))
                for i in range(1, count + 1)))

    @staticmethod
    def item(row):
        result = dict(row)
        result['tags'] = json.loads(result['tags'])
        result['favorite'] = bool(result['favorite'])
        result['reviewed'] = bool(result['reviewed'])
        result['synthetic'] = True
        return result

    def stats(self):
        with self.connect() as db:
            row = db.execute('SELECT count(*) total, coalesce(sum(favorite),0) favorites, '
                             'coalesce(sum(1-reviewed),0) unreviewed FROM items').fetchone()
            return dict(row)

    def search(self, query='', kind='', view='all', page=0, limit=60):
        if kind and kind not in KINDS:
            raise ValueError('Unknown media type')
        if view not in ('all', 'favorites', 'unreviewed', 'shelf'):
            raise ValueError('Unknown view')
        if page < 0 or limit < 1 or limit > 120 or len(query) > 300:
            raise ValueError('Invalid search limits')
        where, values = [], []
        if query.strip():
            # Literal substring search: wildcard characters in user input are escaped.
            escaped = query.strip().replace('!', '!!').replace('%', '!%').replace('_', '!_')
            where.append("(title LIKE ? ESCAPE '!' OR tags LIKE ? ESCAPE '!')")
            values.extend([f'%{escaped}%'] * 2)
        if kind:
            where.append('kind=?')
            values.append(kind)
        if view == 'favorites':
            where.append('favorite=1')
        if view == 'unreviewed':
            where.append('reviewed=0')
        if view == 'shelf':
            where.append("shelf<>''")
        clause = ' WHERE ' + ' AND '.join(where) if where else ''
        with self.connect() as db:
            total = db.execute('SELECT count(*) FROM items' + clause, values).fetchone()[0]
            rows = db.execute('SELECT * FROM items' + clause + ' ORDER BY id LIMIT ? OFFSET ?',
                              values + [limit, page * limit]).fetchall()
        return {'total': total, 'page': page, 'limit': limit, 'items': [self.item(r) for r in rows]}

    def get(self, item_id):
        if type(item_id) is not int or not 1 <= item_id <= 9223372036854775807:
            raise ValueError('Invalid item')
        with self.connect() as db:
            row = db.execute('SELECT * FROM items WHERE id=?', (item_id,)).fetchone()
        if row is None:
            raise KeyError(item_id)
        return self.item(row)

    def update(self, ids, changes):
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 120
                or any(type(i) is not int or not 1 <= i <= 9223372036854775807 for i in ids)):
            raise ValueError('Select 1 to 120 valid IDs')
        if not isinstance(changes, dict) or not changes or set(changes) - {'tags', 'shelf', 'favorite', 'reviewed'}:
            raise ValueError('Invalid changes')
        changes = dict(changes)
        if 'tags' in changes:
            changes['tags'] = json.dumps(validate_tags(changes['tags']), ensure_ascii=False)
        if 'shelf' in changes and (not isinstance(changes['shelf'], str) or len(changes['shelf']) > 80):
            raise ValueError('Shelf must be 80 characters or less')
        for key in ('favorite', 'reviewed'):
            if key in changes and type(changes[key]) is not bool:
                raise ValueError('Expected a boolean')
        marks = ','.join('?' for _ in ids)
        with self.connect() as db:
            count = db.execute(f'SELECT count(*) FROM items WHERE id IN ({marks})', ids).fetchone()[0]
            if count != len(set(ids)):
                raise KeyError('Some items no longer exist')
            assignments = ','.join(f'{key}=?' for key in changes)
            db.execute(f'UPDATE items SET {assignments} WHERE id IN ({marks})', list(changes.values()) + ids)
        return {'updated': count}
