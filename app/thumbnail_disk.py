"""Disposable or persistent SQLite tier for derived PNGs; cache errors are always misses.

One backend owns one lazily created temporary directory (disposable mode)
or one guarded persistent SQLite file (persistent mode).
The caller serializes access and validates the original source even on hits.
"""
import hashlib
import os
import re
import sqlite3
import tempfile
from pathlib import Path

from image_animations import MAX_RENDERED_PNG_BYTES
from storage_lease import (
    plain_path,
    storage_parent,
    storage_lease,
    StorageBusyError,
    StoragePathError,
)

MAX_BYTES = 512 * 1024 * 1024
MAX_ENTRIES = 4096
SCHEMA_VERSION = 1
TABLE_COLUMNS = ('key', 'png', 'digest', 'tag', 'touched')


class ThumbnailDisk:
    def __init__(self, *, max_bytes=MAX_BYTES, parent=None, path=None):
        self.max_bytes = max_bytes
        self.parent = parent
        self.raw_path = path
        self.path = None
        self.directory = None
        self.db = None
        self.disabled = False
        self.tick = 0
        self._lease = None
        if path is not None:
            try:
                storage_parent(path)
                self.path = plain_path(path, missing=True)
                lease = storage_lease(self.path)
                lease.__enter__()
                self._lease = lease
            except (StoragePathError, StorageBusyError, OSError, ValueError, sqlite3.Error):
                self.close()

    def _open_persistent(self):
        self.path = plain_path(self.path, missing=True)
        for suffix in ('-wal', '-shm', '-journal'):
            companion = Path(str(self.path) + suffix)
            if companion.exists() or companion.is_symlink():
                plain_path(companion).unlink()

        needs_recreate = False
        db = None
        if self.path.exists() and self.path.stat().st_size > 0:
            try:
                db = sqlite3.connect(self.path, check_same_thread=False)
                db.execute('PRAGMA trusted_schema=OFF')
                user_version = db.execute('PRAGMA user_version').fetchone()[0]
                quick = db.execute('PRAGMA quick_check').fetchall()
                if quick != [('ok',)]:
                    needs_recreate = True
                elif user_version != SCHEMA_VERSION and user_version != 0:
                    needs_recreate = True
                else:
                    objects = db.execute(
                        "SELECT name, type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND type IN ('table', 'view', 'trigger')"
                    ).fetchall()
                    if any(kind != 'table' for _, kind in objects):
                        needs_recreate = True
                    else:
                        tables = {name for name, _ in objects}
                        if tables:
                            if tables != {'thumbs'} or user_version != SCHEMA_VERSION:
                                needs_recreate = True
                            else:
                                cols = tuple(row[1] for row in db.execute('PRAGMA table_info(thumbs)'))
                                if cols != TABLE_COLUMNS:
                                    needs_recreate = True
            except (sqlite3.Error, OSError, ValueError):
                needs_recreate = True

        if needs_recreate:
            if db is not None:
                try:
                    db.close()
                except sqlite3.Error:
                    pass
                db = None
            if self.path.exists() or self.path.is_symlink():
                plain_path(self.path).unlink()
            for suffix in ('-wal', '-shm', '-journal'):
                companion = Path(str(self.path) + suffix)
                if companion.exists() or companion.is_symlink():
                    plain_path(companion).unlink()

        if db is None:
            db = sqlite3.connect(self.path, check_same_thread=False)
            db.execute('PRAGMA trusted_schema=OFF')

        db.execute('PRAGMA journal_mode=DELETE')
        db.execute('PRAGMA cache_size=-2048')
        db.execute('PRAGMA max_page_count=' + str(max(1, self.max_bytes // 4096)))
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_RENDERED_PNG_BYTES + 4096)
        db.execute('CREATE TABLE IF NOT EXISTS thumbs(key TEXT PRIMARY KEY, png BLOB NOT NULL, digest TEXT NOT NULL, tag TEXT, touched INTEGER NOT NULL)')
        db.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
        db.commit()

        self.tick = db.execute('SELECT COALESCE(MAX(touched), 0) FROM thumbs').fetchone()[0]
        budget = max(0, self.max_bytes - min(1024 * 1024, self.max_bytes // 4))
        size, count = db.execute('SELECT COALESCE(SUM(length(png)),0),COUNT(*) FROM thumbs').fetchone()
        if size > budget or count > MAX_ENTRIES:
            while size > budget or count > MAX_ENTRIES:
                old = db.execute('SELECT key,length(png) FROM thumbs ORDER BY touched,key LIMIT 1').fetchone()
                if old is None:
                    break
                db.execute('DELETE FROM thumbs WHERE key=?', (old[0],))
                size -= old[1]
                count -= 1
            db.commit()
        self.db = db

    def _open(self):
        if self.db is None and not self.disabled:
            try:
                if self.path is None:
                    self.directory = tempfile.TemporaryDirectory(prefix='aredoko-thumbnails-', dir=self.parent)
                    self.db = sqlite3.connect(Path(self.directory.name) / 'derived.sqlite', check_same_thread=False)
                    self.db.execute('PRAGMA journal_mode=MEMORY')
                    self.db.execute('PRAGMA cache_size=-2048')
                    self.db.execute('PRAGMA max_page_count=' + str(max(1, self.max_bytes // 4096)))
                    self.db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_RENDERED_PNG_BYTES + 4096)
                    self.db.execute('CREATE TABLE thumbs(key TEXT PRIMARY KEY, png BLOB NOT NULL, digest TEXT NOT NULL, tag TEXT, touched INTEGER NOT NULL)')
                else:
                    self._open_persistent()
            except (StoragePathError, StorageBusyError, sqlite3.Error, OSError, ValueError):
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
            try:
                self.db.close()
            except sqlite3.Error:
                pass
            self.db = None
        if self.directory is not None:
            try:
                self.directory.cleanup()
            except OSError:
                pass
            self.directory = None
        if self._lease is not None:
            try:
                self._lease.__exit__(None, None, None)
            except (StorageBusyError, StoragePathError, OSError, ValueError):
                pass
            self._lease = None
