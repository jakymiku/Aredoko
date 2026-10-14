"""Read-only filesystem discovery into an independent SQLite location index.

The scanner never opens media contents or edits library files. It does not touch
Catalog's fictional demo items, assign content identities or infer moves.
"""
from __future__ import annotations

import fnmatch
import json
import os
import sqlite3
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

DEFAULT_EXCLUDES = ('.git', '.svn', '__pycache__', 'node_modules', 'Thumbs.db', 'desktop.ini')
TYPES = {
    'book': {'.cbz', '.pdf', '.epub'},
    # A .zip may be a book OR a package of production assets; do not guess.
    'archive': {'.zip'},
    'image': {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tif', '.tiff', '.avif', '.heic', '.heif'},
    'video': {'.mp4', '.mkv', '.webm', '.avi', '.mov', '.wmv', '.m4v', '.ts'},
    'audio': {'.mp3', '.flac', '.wav', '.ogg', '.opus', '.m4a', '.aac', '.wma'},
    'material': {'.psd', '.clip', '.kra', '.ora', '.blend', '.svg', '.ase', '.aseprite'},
}
EXT_TYPES = {ext: kind for kind, extensions in TYPES.items() for ext in extensions}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _excluded(rel_path: str, patterns: tuple[str, ...]) -> bool:
    """Match basename or relative paths, including excluded ancestor folders."""
    parts = PurePosixPath(rel_path).parts
    for i in range(len(parts)):
        partial = '/'.join(parts[:i + 1]).casefold()
        component = parts[i].casefold()
        if any(fnmatch.fnmatchcase(component, p.casefold()) or
               fnmatch.fnmatchcase(partial, p.casefold()) for p in patterns):
            return True
    return False


def _validate_excludes(patterns):
    if patterns is None:
        return tuple(DEFAULT_EXCLUDES)
    if not isinstance(patterns, (list, tuple)) or len(patterns) > 64:
        raise ValueError('Exclusion patterns must be a list (max 64)')
    out = list(DEFAULT_EXCLUDES)
    for pattern in patterns:
        if not isinstance(pattern, str) or not 1 <= len(pattern) <= 200:
            raise ValueError('Invalid exclusion pattern')
        if '\\' in pattern or pattern.startswith('/') or '..' in PurePosixPath(pattern).parts:
            raise ValueError('Use relative POSIX-style exclusion patterns')
        if pattern not in out:
            out.append(pattern)
    return tuple(out)


def _reparse(info):
    return bool(getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0))


@dataclass(frozen=True)
class ScanCounts:
    root_id: int
    dry_run: bool
    discovered: int = 0
    added: int = 0
    changed: int = 0
    unchanged: int = 0
    missing: int = 0
    excluded: int = 0
    skipped_links: int = 0
    ignored_files: int = 0

    def as_dict(self):
        return vars(self).copy()


class LibraryIndex:
    def __init__(self, db_path):
        self.path = Path(db_path).expanduser().resolve(strict=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS library_roots (
                    id INTEGER PRIMARY KEY,
                    path TEXT NOT NULL UNIQUE,
                    excludes_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_scanned_at TEXT
                );
                CREATE TABLE IF NOT EXISTS library_locations (
                    id INTEGER PRIMARY KEY,
                    root_id INTEGER NOT NULL REFERENCES library_roots(id),
                    relative_path TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('present','missing','excluded')),
                    discovered_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    UNIQUE(root_id, relative_path)
                );
                CREATE INDEX IF NOT EXISTS library_locations_status ON library_locations(root_id,status);
            ''')

            # Additive migration; existing roots keep no initial shelf.
            if 'default_shelf' not in {r['name'] for r in db.execute('PRAGMA table_info(library_roots)')}:
                db.execute("ALTER TABLE library_roots ADD COLUMN default_shelf TEXT NOT NULL DEFAULT ''")

            if 'enabled' not in {r['name'] for r in db.execute('PRAGMA table_info(library_roots)')}:
                db.execute("ALTER TABLE library_roots ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def add_root(self, path, excludes=None, default_shelf=''):
        if not isinstance(default_shelf,str) or len(default_shelf)>80:
            raise ValueError('Shelf must be 80 characters or less')
        default_shelf=default_shelf.strip()
        requested = Path(path).expanduser()
        if requested.is_symlink():
            raise ValueError('Symlink roots are not supported')
        try:
            requested_info = requested.stat(follow_symlinks=False)
        except OSError as error:
            raise ValueError('Root must exist and be accessible') from error
        if _reparse(requested_info):
            raise ValueError('Reparse-point roots are not supported')
        root = requested.resolve(strict=True)
        if not root.is_dir() or root.is_symlink():
            raise ValueError('Root must be an existing ordinary directory')
        if _reparse(root.stat(follow_symlinks=False)):
            raise ValueError('Reparse-point roots are not supported')
        patterns = _validate_excludes(excludes)
        with self.connect() as db:
            # Validate all active overlaps before restoring an inactive root.
            for active in db.execute('SELECT path FROM library_roots WHERE enabled=1'):
                existing=Path(active['path'])
                if existing in root.parents or root in existing.parents:
                    raise ValueError('Overlapping roots are not supported')
            for row in db.execute('SELECT id,path,enabled FROM library_roots'):
                existing = Path(row['path'])
                if os.path.normcase(str(root)) == os.path.normcase(str(existing)):
                    if row['enabled']:raise ValueError('This root is already registered')
                    db.execute('UPDATE library_roots SET enabled=1,excludes_json=?,default_shelf=? WHERE id=?',
                        (json.dumps(patterns,ensure_ascii=False),default_shelf,row['id']))
                    return row['id']
                if row['enabled'] and (existing in root.parents or root in existing.parents):
                    raise ValueError('Overlapping roots are not supported')
            cursor = db.execute('INSERT INTO library_roots(path,excludes_json,created_at,default_shelf) VALUES(?,?,?,?)',
                                (str(root), json.dumps(patterns, ensure_ascii=False), _now(), default_shelf))
            return cursor.lastrowid

    def unregister(self,root_id):
        if type(root_id) is not int or root_id<=0 or root_id>9223372036854775807:raise ValueError('Invalid root ID')
        with self.connect() as db:
            if not db.execute('UPDATE library_roots SET enabled=0 WHERE id=? AND enabled=1',(root_id,)).rowcount:
                raise ValueError('Unknown registered root')
        return {'unregistered':root_id}

    def set_excludes(self, root_id, patterns):
        """Replace user exclusions; defaults always remain. No scan is started."""
        if type(root_id) is not int or not 1 <= root_id <= 9223372036854775807:
            raise ValueError('Invalid root ID')
        patterns = _validate_excludes(patterns)
        with self.connect() as db:
            updated = db.execute('UPDATE library_roots SET excludes_json=? WHERE id=? AND enabled=1',
                                 (json.dumps(patterns, ensure_ascii=False), root_id)).rowcount
            if not updated:
                raise KeyError(root_id)
        return list(patterns)

    def roots(self,include_inactive=False):
        with self.connect() as db:
            result = [dict(row) for row in db.execute('SELECT * FROM library_roots'+('' if include_inactive else ' WHERE enabled=1')+' ORDER BY id')]
        for row in result:
            row['excludes'] = json.loads(row.pop('excludes_json'))
            row['online'] = Path(row['path']).is_dir()
        return result

    def locations(self, root_id, status=None, limit=100, offset=0):
        if type(root_id) is not int or not 1 <= root_id <= 9223372036854775807:
            raise ValueError('Invalid root ID')
        if status not in (None, 'present', 'missing', 'excluded'):
            raise ValueError('Invalid location status')
        if (type(limit) is not int or not 1 <= limit <= 500
                or type(offset) is not int or not 0 <= offset <= 9223372036854775807):
            raise ValueError('Invalid paging')
        where = 'root_id=?' + (' AND status=?' if status else '')
        args = [root_id] + ([status] if status else [])
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM library_roots WHERE id=? AND enabled=1', (root_id,)).fetchone():
                raise KeyError(root_id)
            total = db.execute('SELECT count(*) FROM library_locations WHERE ' + where, args).fetchone()[0]
            rows = db.execute('SELECT * FROM library_locations WHERE ' + where +
                              ' ORDER BY relative_path LIMIT ? OFFSET ?', args + [limit, offset]).fetchall()
        return {'total': total, 'items': [dict(row) for row in rows]}

    def scan(self, root_id, *, dry_run=False, cancelled=None, progress=None):
        """Atomic scan; failures leave previous locations and metadata unchanged.

        Missing files are retained, never deleted. The registered root being
        unavailable is an error, not evidence of deletions (offline-drive safety).
        """
        if type(root_id) is not int or not 1 <= root_id <= 9223372036854775807:
            raise ValueError('Invalid root ID')
        with self.connect() as db:
            row = db.execute('SELECT * FROM library_roots WHERE id=? AND enabled=1', (root_id,)).fetchone()
            if row is None:
                raise KeyError(root_id)
            root = Path(row['path'])
            try:
                root_info = root.stat(follow_symlinks=False)
            except OSError as error:
                raise OSError(f'Root unavailable, records preserved: {root}') from error
            if not stat.S_ISDIR(root_info.st_mode) or _reparse(root_info) or root.is_symlink():
                raise OSError(f'Root is no longer an ordinary directory: {root}')
            patterns = tuple(json.loads(row['excludes_json']))
            counts = dict(discovered=0, added=0, changed=0, unchanged=0,
                          missing=0, excluded=0, skipped_links=0, ignored_files=0)
            seen = _now()
            db.execute('CREATE TEMP TABLE scan_seen(path TEXT PRIMARY KEY) WITHOUT ROWID')
            pending = [root]
            # Explicit directory stack keeps depth independent of Python recursion.
            while pending:
                if cancelled and cancelled():
                    raise InterruptedError('Scan cancelled; previous index preserved')
                directory = pending.pop()
                directory_info = directory.stat(follow_symlinks=False)
                if not stat.S_ISDIR(directory_info.st_mode) or _reparse(directory_info) or directory.is_symlink():
                    raise OSError(f'Directory changed during scan: {directory}')
                with os.scandir(directory) as entries:
                    for entry in entries:
                        if cancelled and cancelled():
                            raise InterruptedError('Scan cancelled; previous index preserved')
                        rel = Path(entry.path).relative_to(root).as_posix()
                        info = entry.stat(follow_symlinks=False)
                        if stat.S_ISLNK(info.st_mode) or _reparse(info):
                            counts['skipped_links'] += 1
                            continue
                        if _excluded(rel, patterns):
                            continue
                        if stat.S_ISDIR(info.st_mode):
                            pending.append(Path(entry.path))
                            continue
                        if not stat.S_ISREG(info.st_mode):
                            continue
                        # Never index the local SQLite database as a media item.
                        if Path(entry.path).resolve(strict=False) in (self.path,):
                            continue
                        kind = EXT_TYPES.get(Path(entry.name).suffix.casefold())
                        if kind is None:
                            counts['ignored_files'] += 1
                            continue
                        counts['discovered'] += 1
                        if progress and counts['discovered'] % 100 == 0:
                            progress(counts['discovered'])
                        db.execute('INSERT INTO scan_seen(path) VALUES(?)', (rel,))
                        old = db.execute('SELECT id,kind,size_bytes,mtime_ns,status FROM library_locations '
                                         'WHERE root_id=? AND relative_path=?', (root_id, rel)).fetchone()
                        if old is None:
                            counts['added'] += 1
                            if not dry_run:
                                db.execute('INSERT INTO library_locations(root_id,relative_path,kind,size_bytes,'
                                           'mtime_ns,status,discovered_at,last_seen_at) VALUES(?,?,?,?,?,?,?,?)',
                                           (root_id, rel, kind, info.st_size, info.st_mtime_ns, 'present', seen, seen))
                        else:
                            dirty = (old['kind'] != kind or old['size_bytes'] != info.st_size or
                                     old['mtime_ns'] != info.st_mtime_ns or old['status'] != 'present')
                            counts['changed' if dirty else 'unchanged'] += 1
                            if not dry_run:
                                db.execute('UPDATE library_locations SET kind=?,size_bytes=?,mtime_ns=?,status=?,last_seen_at=? '
                                           'WHERE id=?', (kind, info.st_size, info.st_mtime_ns, 'present', seen, old['id']))
            if cancelled and cancelled():
                raise InterruptedError('Scan cancelled; previous index preserved')
            # No missing inference happens until a complete, error-free tree walk.
            stale = db.execute('SELECT id,relative_path,status FROM library_locations WHERE root_id=? '
                               'AND relative_path NOT IN (SELECT path FROM scan_seen)', (root_id,)).fetchall()
            for item in stale:
                new_status = 'excluded' if _excluded(item['relative_path'], patterns) else 'missing'
                if new_status != item['status']:
                    counts[new_status] += 1
                if not dry_run:
                    db.execute('UPDATE library_locations SET status=? WHERE id=?', (new_status, item['id']))
            if not dry_run:
                db.execute('UPDATE library_roots SET last_scanned_at=? WHERE id=?', (seen, root_id))
            # TEMP table is connection-scoped, and dry-run has no persisted writes.
        return ScanCounts(root_id, bool(dry_run), **counts).as_dict()
