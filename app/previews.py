"""Bounded, read-only image preview sources. No extraction or persistent cache."""
import hashlib
import json
import os
import re
import stat
import struct
import threading
import unicodedata
import zipfile
import zlib
from pathlib import Path, PurePosixPath
from library_index import _excluded, _reparse

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_DIRECTORY_BYTES = 4 * 1024 * 1024
IMAGE_MIME = {'.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg',
              '.webp':'image/webp', '.gif':'image/gif', '.bmp':'image/bmp'}

class PreviewUnavailable(ValueError):
    pass

class PreviewBusyError(PreviewUnavailable):
    pass

class ReaderChanged(PreviewUnavailable):
    """The caller must rescan/reopen instead of using old page numbers."""
    pass


def _revision(row, info):
    # A file-identity/metadata token, not a content digest. Recomputed under
    # the same open handle on every request; never accepts a client path.
    identity = [row['root_id'], row['relative_path'], info.st_dev,
                info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]
    return hashlib.sha256(json.dumps(identity).encode('utf-8')).hexdigest()


def natural_key(name):
    def part_key(part):
        if not part.isdecimal():
            return (0, part.casefold())
        # Compare numeric strings without constructing unbounded integers.
        # Unicode decimal digits and leading zeroes keep their existing ties.
        digits = ''.join(str(unicodedata.decimal(c)) for c in part).lstrip('0') or '0'
        return (1, len(digits), digits)
    return tuple(part_key(part) for part in re.split(r'(\d+)', name))

def _safe_path(root, relative):
    parts = PurePosixPath(relative).parts
    if not parts or PurePosixPath(relative).is_absolute() or '..' in parts or '\\' in relative:
        raise PreviewUnavailable('Invalid location')
    root = Path(root)
    source = root.joinpath(*parts)
    # Recheck every component at read time: a previously indexed directory may
    # have been replaced by a junction/link since the scan.
    for component in [*reversed(root.parents), root, *[root.joinpath(*parts[:i]) for i in range(1, len(parts)+1)]]:
        info = component.stat(follow_symlinks=False)
        if _reparse(info) or stat.S_ISLNK(info.st_mode):
            raise PreviewUnavailable('Linked locations are not previewed')
    if not source.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
        raise PreviewUnavailable('Location outside root')
    return source

def _zip_directory_limit(file):
    """Inspect the end record before ZipFile allocates the central directory.

    ZIP64/multi-disk archives are intentionally unsupported in this first slice.
    """
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(max(0, size - 65557))
    tail = file.read(65557)
    pos = tail.rfind(b'PK\x05\x06')
    if pos < 0 or len(tail) - pos < 22:
        raise PreviewUnavailable('Invalid archive')
    signature, disk, cd_disk, disk_count, count, cd_size, offset, comment = struct.unpack_from('<4s4H2IH', tail, pos)
    if (disk or cd_disk or disk_count != count or count >= 65535 or count > 10000
            or cd_size > MAX_DIRECTORY_BYTES or offset + cd_size > size
            or len(tail) - pos != 22 + comment):
        raise PreviewUnavailable('Archive exceeds preview limits')
    end_offset = size - len(tail) + pos
    # zipfile accepts a ZIP64 locator even when the legacy fields do not use
    # sentinel values, and then replaces the size/count we just checked.
    if end_offset >= 20:
        file.seek(end_offset - 20)
        if file.read(4) == b'PK\x06\x07':
            raise PreviewUnavailable('ZIP64 archives are not supported')
    # Match zipfile's location calculation for a prefixed (self-extracting)
    # archive. Scan fixed headers before it allocates any ZipInfo objects;
    # the declared entry count alone can lie about the actual directory.
    directory_start = end_offset - cd_size
    if directory_start < 0 or offset > directory_start:
        raise PreviewUnavailable('Invalid archive directory')
    file.seek(directory_start)
    consumed = actual_count = 0
    while consumed < cd_size:
        header = file.read(46)
        if len(header) != 46 or header[:4] != b'PK\x01\x02':
            raise PreviewUnavailable('Invalid archive directory')
        name_size, extra_size, comment_size = struct.unpack_from('<3H', header, 28)
        packed_size, plain_size = struct.unpack_from('<2I', header, 20)
        volume = struct.unpack_from('<H', header, 34)[0]
        local_offset = struct.unpack_from('<I', header, 42)[0]
        entry_size = 46 + name_size + extra_size + comment_size
        actual_count += 1
        if (actual_count > 10000 or consumed + entry_size > cd_size or volume
                or 0xffffffff in (packed_size, plain_size, local_offset)):
            raise PreviewUnavailable('Archive exceeds preview limits')
        file.seek(entry_size - 46, os.SEEK_CUR)
        consumed += entry_size
    if actual_count != count:
        raise PreviewUnavailable('Archive directory count mismatch')
    file.seek(0)

class PreviewReader:
    def __init__(self, catalog):
        self.catalog = catalog
        self.slots = threading.BoundedSemaphore(2)

    def read(self, item_id):
        return self._read(item_id)

    def manifest(self, item_id):
        """Count naturally ordered archive pages without decompressing images."""
        return self._read(item_id, operation='manifest')

    def read_page(self, item_id, page, revision):
        if type(page) is not int or not 0 <= page < 10000:
            raise ValueError('Invalid page')
        if type(revision) is not str or re.fullmatch(r'[0-9a-f]{64}', revision) is None:
            raise ValueError('Invalid reader revision')
        return self._read(item_id, operation='page', page=page, revision=revision)

    def _read(self, item_id, operation='preview', page=0, revision=None):
        if type(item_id) is not int or item_id < 1:
            raise PreviewUnavailable('Invalid item')
        if not self.slots.acquire(blocking=False):
            raise PreviewBusyError('Preview workers busy')
        try:
            with self.catalog.connect() as db:
                row = db.execute('SELECT l.*, r.path, r.excludes_json FROM item_locations m '
                    'JOIN library_locations l ON l.id=m.location_id '
                    'JOIN library_roots r ON r.id=l.root_id WHERE m.item_id=? AND r.enabled=1', (item_id,)).fetchone()
            if row is None or row['status'] != 'present':
                raise PreviewUnavailable('Location unavailable')
            if _excluded(row['relative_path'], tuple(json.loads(row['excludes_json']))):
                raise PreviewUnavailable('Location excluded')
            source = _safe_path(row['path'], row['relative_path'])
            suffix = source.suffix.casefold()
            if suffix not in IMAGE_MIME and suffix not in ('.cbz', '.zip'):
                raise PreviewUnavailable('Unsupported preview type')
            if operation != 'preview' and suffix not in ('.cbz', '.zip'):
                raise PreviewUnavailable('Reader requires a CBZ or ZIP archive')
            initial = source.stat(follow_symlinks=False)
            with source.open('rb') as file:
                info = os.fstat(file.fileno())
                if (not stat.S_ISREG(info.st_mode) or _reparse(info)
                        or (info.st_ino, info.st_dev) != (initial.st_ino, initial.st_dev)):
                    raise PreviewUnavailable('Location changed')
                _safe_path(row['path'], row['relative_path'])
                if info.st_size != row['size_bytes'] or info.st_mtime_ns != row['mtime_ns']:
                    if operation != 'preview':
                        raise ReaderChanged('Rescan changed files before reading')
                    raise PreviewUnavailable('Rescan changed files before previewing')
                current_revision = _revision(row, info) if operation != 'preview' else None
                if revision is not None and revision != current_revision:
                    raise ReaderChanged('Archive changed; reopen the reader')
                if suffix in IMAGE_MIME:
                    if info.st_size > MAX_IMAGE_BYTES:
                        raise PreviewUnavailable('Image exceeds preview limit')
                    data, mime = file.read(MAX_IMAGE_BYTES + 1), IMAGE_MIME[suffix]
                else:
                    if info.st_size > MAX_ARCHIVE_BYTES:
                        raise PreviewUnavailable('Archive exceeds preview limit')
                    _zip_directory_limit(file)
                    with zipfile.ZipFile(file) as archive:
                        entries = [e for e in archive.infolist() if not e.is_dir()
                                   and PurePosixPath(e.filename).suffix.casefold() in IMAGE_MIME
                                   and not e.filename.startswith('__MACOSX/')]
                        if not entries:
                            raise PreviewUnavailable('Archive has no supported image')
                        if operation == 'manifest':
                            result = {'item_id':item_id, 'page_count':len(entries),
                                      'revision':current_revision}
                        else:
                            if page >= len(entries):
                                raise PreviewUnavailable('Page unavailable')
                            # Stable sort preserves central-directory order for
                            # duplicate names; open the ZipInfo, not its name.
                            entry = (min(entries, key=lambda e: natural_key(e.filename))
                                     if operation == 'preview' else
                                     sorted(entries, key=lambda e: natural_key(e.filename))[page])
                            if (entry.flag_bits & 1 or entry.file_size > MAX_IMAGE_BYTES
                                    or entry.file_size > max(1, entry.compress_size) * 200):
                                raise PreviewUnavailable('Archive image exceeds preview limits')
                            with archive.open(entry) as image:
                                data = image.read(MAX_IMAGE_BYTES + 1)
                            mime = IMAGE_MIME[PurePosixPath(entry.filename).suffix.casefold()]
                if operation != 'manifest' and len(data) > MAX_IMAGE_BYTES:
                    raise PreviewUnavailable('Image exceeds preview limit')
                after = os.fstat(file.fileno())
                if (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (info.st_size, info.st_mtime_ns, info.st_ctime_ns):
                    if operation != 'preview':
                        raise ReaderChanged('Source changed while reading')
                    raise PreviewUnavailable('Source changed while reading')
                if operation == 'manifest':
                    return result
                return data, mime
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, zlib.error) as error:
            raise PreviewUnavailable('Invalid or unsupported archive') from error
        finally:
            self.slots.release()

