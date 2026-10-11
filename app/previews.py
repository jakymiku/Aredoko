"""Bounded, read-only image preview sources. No extraction or persistent cache."""
import os
import re
import stat
import struct
import threading
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


def natural_key(name):
    return tuple((1, int(p)) if p.isdigit() else (0, p.casefold())
                 for p in re.split(r'(\d+)', name))

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
    file.seek(0)

class PreviewReader:
    def __init__(self, catalog):
        self.catalog = catalog
        self.slots = threading.BoundedSemaphore(2)

    def read(self, item_id):
        if type(item_id) is not int or item_id < 1:
            raise PreviewUnavailable('Invalid item')
        if not self.slots.acquire(blocking=False):
            raise PreviewBusyError('Preview workers busy')
        try:
            with self.catalog.connect() as db:
                row = db.execute('SELECT l.*, r.path, r.excludes_json FROM item_locations m '
                    'JOIN library_locations l ON l.id=m.location_id '
                    'JOIN library_roots r ON r.id=l.root_id WHERE m.item_id=?', (item_id,)).fetchone()
            if row is None or row['status'] != 'present':
                raise PreviewUnavailable('Location unavailable')
            import json
            if _excluded(row['relative_path'], tuple(json.loads(row['excludes_json']))):
                raise PreviewUnavailable('Location excluded')
            source = _safe_path(row['path'], row['relative_path'])
            suffix = source.suffix.casefold()
            if suffix not in IMAGE_MIME and suffix not in ('.cbz', '.zip'):
                raise PreviewUnavailable('Unsupported preview type')
            initial = source.stat(follow_symlinks=False)
            with source.open('rb') as file:
                info = os.fstat(file.fileno())
                if (not stat.S_ISREG(info.st_mode) or _reparse(info)
                        or (info.st_ino, info.st_dev) != (initial.st_ino, initial.st_dev)):
                    raise PreviewUnavailable('Location changed')
                _safe_path(row['path'], row['relative_path'])
                if info.st_size != row['size_bytes'] or info.st_mtime_ns != row['mtime_ns']:
                    raise PreviewUnavailable('Rescan changed files before previewing')
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
                        entry = min(entries, key=lambda e: natural_key(e.filename))
                        if (entry.flag_bits & 1 or entry.file_size > MAX_IMAGE_BYTES
                                or entry.file_size > max(1, entry.compress_size) * 200):
                            raise PreviewUnavailable('Archive image exceeds preview limits')
                        with archive.open(entry) as image:
                            data = image.read(MAX_IMAGE_BYTES + 1)
                        mime = IMAGE_MIME[PurePosixPath(entry.filename).suffix.casefold()]
                if len(data) > MAX_IMAGE_BYTES:
                    raise PreviewUnavailable('Image exceeds preview limit')
                after = os.fstat(file.fileno())
                if (after.st_size, after.st_mtime_ns) != (info.st_size, info.st_mtime_ns):
                    raise PreviewUnavailable('Source changed while reading')
                return data, mime
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, zlib.error) as error:
            raise PreviewUnavailable('Invalid or unsupported archive') from error
        finally:
            self.slots.release()
