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

import native_accel

_ORIG_SCANDIR = os.scandir

DEFAULT_EXCLUDES = ('.git', '.svn', '__pycache__', 'node_modules', 'Thumbs.db', 'desktop.ini', '$RECYCLE.BIN')
MAX_ACCESS_DENIED_LOG = 500
TYPES = {
    'book': {'.cbz', '.pdf', '.epub'},
    # A .zip may be a book OR a package of production assets; do not guess.
    'archive': {'.zip'},
    'image': {'.jpg', '.jpeg', '.png', '.apng', '.webp', '.gif', '.bmp', '.tif', '.tiff', '.avif', '.heic', '.heif'},
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


# A folder book is one location for all images directly inside a directory.
# Its relative_path ends with "/" (a file path never does); the registered
# folder itself is "./". Only roots registered with folder_books=1 produce
# them: nothing is guessed from folder names or contents.
FOLDER_ROOT = './'
FOLDER_IMAGES = TYPES['image']


def is_folder_book(relative_path) -> bool:
    return isinstance(relative_path, str) and relative_path.endswith('/')


def folder_directory(root, relative_path) -> Path:
    """Directory of a folder book; relative_path is validated, never a client path."""
    if not is_folder_book(relative_path):
        raise ValueError('Not a folder book')
    if relative_path == FOLDER_ROOT:
        return Path(root)
    inner = relative_path[:-1]
    parts = PurePosixPath(inner).parts
    if not inner or PurePosixPath(inner).is_absolute() or '..' in parts or '.' in parts or '\\' in inner:
        raise ValueError('Invalid folder book location')
    return Path(root).joinpath(*parts)


def folder_signature(pages) -> tuple[int, int]:
    """(total bytes, 63-bit content token) over sorted (name, size, mtime_ns).

    The token is stored in mtime_ns so existing revision/cache keys change
    when a page is added, removed, renamed or rewritten.
    """
    import hashlib
    ordered = sorted(pages)
    # v2 fixes natural-name ties to an ordinal filename order. Invalidate old
    # cover vectors/proposals/progress on rescan rather than reusing a cover
    # chosen by the old filesystem-enumeration order.
    digest = hashlib.sha256(json.dumps(['folder-book-v2', ordered], ensure_ascii=False).encode('utf-8')).digest()
    return sum(size for _, size, _ in ordered), int.from_bytes(digest[:8], 'big') >> 1


def folder_title(root_path, relative_path) -> str:
    return Path(root_path).name if relative_path == FOLDER_ROOT else PurePosixPath(relative_path[:-1]).name


def _reparse(info):
    return bool((getattr(info, 'st_file_attributes', 0) or 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0))


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
    skipped_access_denied: int = 0
    access_denied_entries: tuple = ()
    access_denied_truncated: bool = False

    def as_dict(self):
        data = vars(self).copy()
        data['access_denied_entries'] = [
            {'relative_path': rel, 'is_dir': is_dir}
            for rel, is_dir in self.access_denied_entries
        ]
        return data


class LibraryIndex:
    def __init__(self, db_path):
        self.path = Path(db_path).expanduser().resolve(strict=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS library_roots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                CREATE TABLE IF NOT EXISTS library_root_seq (
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    max_id INTEGER NOT NULL DEFAULT 0
                );
                INSERT OR IGNORE INTO library_root_seq VALUES(1, 0);
            ''')
            db.execute('UPDATE library_root_seq SET max_id = max(max_id, COALESCE((SELECT max(id) FROM library_roots), 0)) WHERE id=1')

            # Additive migration; existing roots keep no initial shelf.
            if 'default_shelf' not in {r['name'] for r in db.execute('PRAGMA table_info(library_roots)')}:
                db.execute("ALTER TABLE library_roots ADD COLUMN default_shelf TEXT NOT NULL DEFAULT ''")

            if 'enabled' not in {r['name'] for r in db.execute('PRAGMA table_info(library_roots)')}:
                db.execute("ALTER TABLE library_roots ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1")

            # Existing roots keep one item per image file.
            if 'folder_books' not in {r['name'] for r in db.execute('PRAGMA table_info(library_roots)')}:
                db.execute("ALTER TABLE library_roots ADD COLUMN folder_books INTEGER NOT NULL DEFAULT 0")

            if 'recursive' not in {r['name'] for r in db.execute('PRAGMA table_info(library_roots)')}:
                db.execute("ALTER TABLE library_roots ADD COLUMN recursive INTEGER NOT NULL DEFAULT 1")

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

    def add_root(self, path, excludes=None, default_shelf='', folder_books=None, recursive=None, *, metadata_hook=None):
        if not isinstance(default_shelf,str) or len(default_shelf)>80:
            raise ValueError('Shelf must be 80 characters or less')
        # None keeps a restored root's choice (False for a new root). The
        # choice is fixed once a root has index records: switching would turn
        # tagged image items into missing records instead of moving metadata.
        if folder_books is not None and type(folder_books) is not bool:
            raise ValueError('folder_books must be true or false')
        if recursive is not None and type(recursive) is not bool:
            raise ValueError('Include subfolders must be true or false')
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
                    if folder_books is not None:
                        stored = db.execute('SELECT folder_books FROM library_roots WHERE id=?', (row['id'],)).fetchone()[0]
                        if bool(stored) != folder_books and db.execute(
                                'SELECT 1 FROM library_locations WHERE root_id=? LIMIT 1', (row['id'],)).fetchone():
                            raise ValueError('Folder book mode cannot change after scanning')
                        db.execute('UPDATE library_roots SET folder_books=? WHERE id=?', (int(folder_books), row['id']))
                    if recursive is not None:
                        db.execute('UPDATE library_roots SET recursive=? WHERE id=?',(int(recursive),row['id']))
                        if not recursive:
                            db.execute("UPDATE library_locations SET status='excluded' WHERE root_id=? AND relative_path<>'./' AND instr(relative_path,'/')>0",(row['id'],))
                    db.execute('UPDATE library_roots SET enabled=1,excludes_json=?,default_shelf=? WHERE id=?',
                        (json.dumps(patterns,ensure_ascii=False),default_shelf,row['id']))
                    if metadata_hook is not None:metadata_hook(db,row['id'])
                    return row['id']
                if row['enabled'] and (existing in root.parents or root in existing.parents):
                    raise ValueError('Overlapping roots are not supported')
            next_id = max(
                db.execute('SELECT max_id FROM library_root_seq WHERE id=1').fetchone()[0],
                db.execute('SELECT COALESCE(max(id), 0) FROM library_roots').fetchone()[0],
            ) + 1
            db.execute('UPDATE library_root_seq SET max_id=? WHERE id=1', (next_id,))
            db.execute('INSERT INTO library_roots(id,path,excludes_json,created_at,default_shelf,folder_books,recursive) VALUES(?,?,?,?,?,?,?)',
                       (next_id, str(root), json.dumps(patterns, ensure_ascii=False), _now(), default_shelf, int(bool(folder_books)), int(recursive is not False)))
            if metadata_hook is not None:metadata_hook(db,next_id)
            return next_id

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
            counts = dict(db.execute("SELECT root_id, count(*) FROM library_locations WHERE status='present' GROUP BY root_id").fetchall())
        for row in result:
            row['excludes'] = json.loads(row.pop('excludes_json'))
            row['folder_books'] = bool(row['folder_books'])
            row['recursive'] = bool(row['recursive'])
            row['online'] = Path(row['path']).is_dir()
            row['present_count'] = counts.get(row['id'], 0)
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
            folder_books = bool(row['folder_books'])
            counts = dict(discovered=0, added=0, changed=0, unchanged=0,
                          missing=0, excluded=0, skipped_links=0, ignored_files=0,
                          skipped_access_denied=0)
            skipped_access_denied = []
            seen = _now()
            db.execute('CREATE TEMP TABLE scan_seen(path TEXT PRIMARY KEY) WITHOUT ROWID')
            if os.scandir is _ORIG_SCANDIR and native_accel.available():
                try:
                    native_scan = native_accel.scan_tree(
                        root, self.path, patterns,
                        recursive=bool(row['recursive']), folder_books=folder_books,
                        cancelled=cancelled,
                    )
                except native_accel.NativeCancelled as error:
                    raise InterruptedError('Scan cancelled; previous index preserved') from error
                counts['skipped_links'] = native_scan.skipped_links
                counts['ignored_files'] = native_scan.ignored_files
                skipped_access_denied.extend(native_scan.skipped_access_denied)
                for rel, kind, size, mtime_ns in native_scan.items:
                    if cancelled and cancelled():
                        raise InterruptedError('Scan cancelled; previous index preserved')
                    self._record(db, root_id, rel, kind, size, mtime_ns, seen, counts, dry_run, progress)
                for dir_rel, pages in native_scan.folder_pages:
                    if cancelled and cancelled():
                        raise InterruptedError('Scan cancelled; previous index preserved')
                    size, token = folder_signature(pages)
                    self._record(db, root_id, dir_rel, 'book', size, token, seen, counts, dry_run, progress)
            else:
                pending = [root]
                # Explicit directory stack keeps depth independent of Python recursion.
                while pending:
                    if cancelled and cancelled():
                        raise InterruptedError('Scan cancelled; previous index preserved')
                    directory = pending.pop()
                    is_root_dir = (directory == root)
                    try:
                        directory_info = directory.stat(follow_symlinks=False)
                    except PermissionError:
                        if is_root_dir:
                            raise
                        skipped_access_denied.append((directory.relative_to(root).as_posix(), True))
                        continue
                    if not stat.S_ISDIR(directory_info.st_mode) or _reparse(directory_info) or directory.is_symlink():
                        raise OSError(f'Directory changed during scan: {directory}')
                    # Finish each book before walking the next directory. Keep only
                    # one folder's page metadata, not every page in the entire root.
                    pages = []
                    try:
                        with os.scandir(directory) as entries:
                            for entry in entries:
                                if cancelled and cancelled():
                                    raise InterruptedError('Scan cancelled; previous index preserved')
                                rel = Path(entry.path).relative_to(root).as_posix()
                                try:
                                    info = entry.stat(follow_symlinks=False)
                                except PermissionError:
                                    try:
                                        entry_is_dir = entry.is_dir(follow_symlinks=False)
                                    except OSError:
                                        entry_is_dir = False
                                    skipped_access_denied.append((rel, entry_is_dir))
                                    continue
                                if stat.S_ISLNK(info.st_mode) or _reparse(info):
                                    counts['skipped_links'] += 1
                                    continue
                                if _excluded(rel, patterns):
                                    continue
                                if stat.S_ISDIR(info.st_mode):
                                    if row['recursive']:pending.append(Path(entry.path))
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
                                if folder_books and kind == 'image':
                                    pages.append((entry.name, info.st_size, info.st_mtime_ns))
                                    continue
                                self._record(db, root_id, rel, kind, info.st_size, info.st_mtime_ns, seen, counts, dry_run, progress)
                    except PermissionError:
                        if is_root_dir:
                            raise
                        skipped_access_denied.append((directory.relative_to(root).as_posix(), True))
                        continue
                    if pages:
                        if cancelled and cancelled():
                            raise InterruptedError('Scan cancelled; previous index preserved')
                        parent = directory.relative_to(root).as_posix()
                        rel = FOLDER_ROOT if parent == '.' else parent + '/'
                        size, token = folder_signature(pages)
                        self._record(db, root_id, rel, 'book', size, token, seen, counts, dry_run, progress)
            if cancelled and cancelled():
                raise InterruptedError('Scan cancelled; previous index preserved')
            unique_denied = sorted(
                set(skipped_access_denied),
                key=lambda item: (item[0].casefold(), item[0], not item[1]),
            )
            counts['skipped_access_denied'] = len(unique_denied)
            counts['access_denied_truncated'] = len(unique_denied) > MAX_ACCESS_DENIED_LOG
            counts['access_denied_entries'] = tuple(unique_denied[:MAX_ACCESS_DENIED_LOG])
            denied_dirs = tuple(rel.rstrip('/') + '/' for rel, is_dir in unique_denied if is_dir)
            denied_files = {rel for rel, is_dir in unique_denied if not is_dir}
            # No missing inference happens until a complete, error-free tree walk.
            stale = db.execute('SELECT id,relative_path,status FROM library_locations WHERE root_id=? '
                               'AND relative_path NOT IN (SELECT path FROM scan_seen)', (root_id,)).fetchall()
            for item in stale:
                item_rel = item['relative_path']
                if item_rel in denied_files or item_rel in denied_dirs or any(
                    item_rel.startswith(prefix) for prefix in denied_dirs
                ):
                    continue
                new_status = 'excluded' if _excluded(item['relative_path'], patterns) or (not row['recursive'] and item['relative_path']!='./' and '/' in item['relative_path']) else 'missing'
                if new_status != item['status']:
                    counts[new_status] += 1
                if not dry_run:
                    db.execute('UPDATE library_locations SET status=? WHERE id=?', (new_status, item['id']))
            if not dry_run:
                db.execute('UPDATE library_roots SET last_scanned_at=? WHERE id=?', (seen, root_id))
            # TEMP table is connection-scoped, and dry-run has no persisted writes.
        return ScanCounts(root_id, bool(dry_run), **counts).as_dict()

    @staticmethod
    def _record(db, root_id, rel, kind, size, mtime_ns, seen, counts, dry_run, progress):
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
                           (root_id, rel, kind, size, mtime_ns, 'present', seen, seen))
        else:
            dirty = (old['kind'] != kind or old['size_bytes'] != size or
                     old['mtime_ns'] != mtime_ns or old['status'] != 'present')
            counts['changed' if dirty else 'unchanged'] += 1
            if not dry_run:
                db.execute('UPDATE library_locations SET kind=?,size_bytes=?,mtime_ns=?,status=?,last_seen_at=? '
                           'WHERE id=?', (kind, size, mtime_ns, 'present', seen, old['id']))
