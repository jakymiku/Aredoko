"""Disposable SQLite tier for derived PNGs; cache errors are always misses.

One backend owns one lazily created temporary directory. No source, catalog or
model writes, persistent schema migration, or cross-process cache sharing.
The caller serializes access and validates the original source even on hits.
"""
import hashlib
import re
import sqlite3
import tempfile
from pathlib import Path

from image_animations import MAX_RENDERED_PNG_BYTES

MAX_BYTES = 512 * 1024 * 1024
MAX_ENTRIES = 4096


class ThumbnailDisk:
    def __init__(self, *, max_bytes=MAX_BYTES, parent=None):
        self.max_bytes = max_bytes
        self.parent = parent
        self.directory = None
        self.db = None
        self.disabled = False
        self.tick = 0

    def _open(self):
        if self.db is None and not self.disabled:
            try:
                self.directory = tempfile.TemporaryDirectory(prefix='aredoko-thumbnails-', dir=self.parent)
                self.db = sqlite3.connect(Path(self.directory.name) / 'derived.sqlite', check_same_thread=False)
                self.db.execute('PRAGMA journal_mode=MEMORY')
                self.db.execute('PRAGMA cache_size=-2048')
                self.db.execute('PRAGMA max_page_count=' + str(max(1, self.max_bytes // 4096)))
                self.db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_RENDERED_PNG_BYTES + 4096)
                self.db.execute('CREATE TABLE thumbs(key TEXT PRIMARY KEY, png BLOB NOT NULL, digest TEXT NOT NULL, tag TEXT, touched INTEGER NOT NULL)')
            except (sqlite3.Error, OSError):
                self.close()
        return self.db

    @staticmethod
    def key(value):
        return hashlib.sha256(repr(value).encode('utf-8')).hexdigest()

    def get(self, key):
        db = self._open()
        if db is None:
            return None
        try:
            row = db.execute('SELECT png,digest,tag FROM thumbs WHERE key=?', (self.key(key),)).fetchone()
            if row is None:
                return None
            data, digest, tag = row
            if (not isinstance(data, bytes) or not 8 <= len(data) <= MAX_RENDERED_PNG_BYTES
                    or not data.startswith(b'\x89PNG\r\n\x1a\n') or hashlib.sha256(data).hexdigest() != digest
                    or (key[1] == 'image' and tag is not None)
                    or (key[1] != 'image' and (not isinstance(tag, str) or re.fullmatch(r'W/"[0-9a-f]{64}"', tag) is None))):
                db.execute('DELETE FROM thumbs WHERE key=?', (self.key(key),)); db.commit()
                return None
            self.tick += 1
            db.execute('UPDATE thumbs SET touched=? WHERE key=?', (self.tick, self.key(key))); db.commit()
            return data, tag
        except (sqlite3.Error, OSError, TypeError, ValueError):
            self.close()
            return None

    def put(self, key, result):
        db = self._open()
        if db is None:
            return
        data, tag = result
        # Leave room for SQLite pages/indexes. max_page_count is the hard file cap.
        budget = max(0, self.max_bytes - min(1024 * 1024, self.max_bytes // 4))
        if len(data) > budget:
            return
        try:
            db.execute('DELETE FROM thumbs WHERE key=?', (self.key(key),))
            size, count = db.execute('SELECT COALESCE(SUM(length(png)),0),COUNT(*) FROM thumbs').fetchone()
            while size + len(data) > budget or count >= MAX_ENTRIES:
                old = db.execute('SELECT key,length(png) FROM thumbs ORDER BY touched,key LIMIT 1').fetchone()
                if old is None:
                    break
                db.execute('DELETE FROM thumbs WHERE key=?', (old[0],)); size -= old[1]; count -= 1
            self.tick += 1
            db.execute('INSERT INTO thumbs VALUES(?,?,?,?,?)',
                       (self.key(key), data, hashlib.sha256(data).hexdigest(), tag, self.tick))
            db.commit()
        except (sqlite3.Error, OSError, TypeError, ValueError):
            self.close()

    def close(self):
        self.disabled = True
        if self.db is not None:
            try: self.db.close()
            except sqlite3.Error: pass
            self.db = None
        if self.directory is not None:
            try: self.directory.cleanup()
            except OSError: pass
            self.directory = None
