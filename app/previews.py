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
from library_index import (_excluded, _reparse, is_folder_book, folder_signature,
                           FOLDER_ROOT, FOLDER_IMAGES)
from page_identity import describe_page
from image_animations import (AnimationInspector, AnimationUnavailable,
                              MAX_LARGE_IMAGE_BYTES, MAX_ANIMATION_FRAMES,
                              THUMBNAIL_MAX_EDGE, VIEWER_MAX_EDGE,
                              REPRESENTATIVE_MAX_EDGE, detect_animation_header)
from video_previews import (VideoThumbnailer, VideoPreviewUnavailable,
                            VIDEO_SUFFIXES, MAX_VIDEO_BYTES)

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_DIRECTORY_BYTES = 4 * 1024 * 1024
MAX_PLAYBACK_BYTES = 64 * 1024 * 1024
MAX_VIDEO_RANGE_BYTES = 1024 * 1024
MAX_STREAM_VIDEO_BYTES = 2 * 1024 ** 4
MAX_FOLDER_PAGES = 10000
IMAGE_MIME = {'.png':'image/png', '.apng':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg',
              '.webp':'image/webp', '.gif':'image/gif', '.bmp':'image/bmp'}
VIDEO_MIME = {'.mp4':'video/mp4', '.m4v':'video/mp4', '.mov':'video/quicktime',
              '.webm':'video/webm', '.mkv':'video/x-matroska', '.avi':'video/x-msvideo',
              '.wmv':'video/x-ms-wmv', '.ts':'video/mp2t'}

class PreviewUnavailable(ValueError):
    pass

class PreviewBusyError(PreviewUnavailable):
    pass

class VideoRangeUnsatisfiable(ValueError):
    def __init__(self,size):self.size=size;super().__init__('Video range outside source')

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
        self.videos = VideoThumbnailer()
        self.animations = AnimationInspector()

    def read(self, item_id):
        return self._read(item_id)

    def read_cover(self, item_id):
        """Bounded cover/representative-frame bytes for AI visual indexing."""
        return self._read(item_id, operation='cover_input')

    def image_manifest(self, item_id):
        return self._read(item_id, operation='image_manifest')

    def image_frame(self, item_id, frame, revision):
        if type(frame) is not int or not 0 <= frame < MAX_ANIMATION_FRAMES:
            raise ValueError('Invalid image frame')
        if type(revision) is not str or re.fullmatch(r'[0-9a-f]{64}', revision) is None:
            raise ValueError('Invalid image revision')
        return self._read(item_id, operation='image_frame', page=frame, revision=revision)

    def read_video(self, item_id):
        return self._read(item_id, operation='video')

    def video_manifest(self,item_id):
        return self._read(item_id,operation='video_manifest')

    def video_range(self,item_id,start,end,revision):
        if type(start) is not int or type(end) is not int or start<0 or end<start or end-start+1>MAX_VIDEO_RANGE_BYTES:
            raise ValueError('Invalid bounded video range')
        if type(revision) is not str or re.fullmatch(r'[0-9a-f]{64}',revision) is None:
            raise ValueError('Invalid video revision')
        return self._read(item_id,operation='video_range',revision=revision,start=start,end=end)

    def video_frame(self,item_id,at_ms,revision):
        if type(at_ms) is not int or not 0 <= at_ms <= 86_400_000:
            raise ValueError('Invalid video frame time')
        if type(revision) is not str or re.fullmatch(r'[0-9a-f]{64}',revision) is None:
            raise ValueError('Invalid video revision')
        return self._read(item_id,operation='video_frame',revision=revision,page=at_ms)

    def manifest(self, item_id):
        """Count naturally ordered archive pages without decompressing images."""
        return self._read(item_id, operation='manifest')

    def read_page(self, item_id, page, revision):
        if type(page) is not int or not 0 <= page < 10000:
            raise ValueError('Invalid page')
        if type(revision) is not str or re.fullmatch(r'[0-9a-f]{64}', revision) is None:
            raise ValueError('Invalid reader revision')
        return self._read(item_id, operation='page', page=page, revision=revision)

    def tag_source(self, item_id):
        """Physical provenance, independent of editable tags/title; no pixels read."""
        return self._read(item_id, operation='tag_source')

    def tag_input(self, item_id):
        """Bounded image/first cover bytes and provenance from the same handle."""
        return self._read(item_id, operation='tag_input')

    def page_catalog(self, item_id):
        """Bounded page descriptors without decoding/decompressing image pixels."""
        return self._read(item_id, operation='page_catalog')

    def page_input(self, item_id, page, revision):
        """A selected page and its identity from the same checked source read."""
        if type(page) is not int or not 0 <= page < 10000:
            raise ValueError('Invalid page')
        if type(revision) is not str or re.fullmatch(r'[0-9a-f]{64}', revision) is None:
            raise ValueError('Invalid reader revision')
        return self._read(item_id, operation='page_input', page=page, revision=revision)

    def _read_folder(self, row, item_id, operation, page, revision):
        try:
            return _folder_read(row, item_id, operation, page, revision)
        except PreviewUnavailable:
            raise
        except OSError as error:
            # A vanished/replaced page or folder is a rescan case, never a crash.
            raise (ReaderChanged if operation != 'preview' else PreviewUnavailable)('Folder book changed') from error

    def _read(self, item_id, operation='preview', page=0, revision=None,start=None,end=None):
        if type(item_id) is not int or not 1 <= item_id <= 9223372036854775807:
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
            if is_folder_book(row['relative_path']):
                return self._read_folder(row, item_id, operation, page, revision)
            source = _safe_path(row['path'], row['relative_path'])
            suffix = source.suffix.casefold()
            if suffix not in IMAGE_MIME and suffix not in ('.cbz', '.zip') and suffix not in VIDEO_SUFFIXES:
                raise PreviewUnavailable('Unsupported preview type')
            if operation in ('video','video_manifest','video_range','video_frame'):
                if suffix not in VIDEO_MIME:
                    raise PreviewUnavailable('Video player requires a supported video item')
            elif operation in ('image_manifest', 'image_frame'):
                if suffix not in IMAGE_MIME:
                    raise PreviewUnavailable('Image viewer requires a supported image item')
            elif operation in ('tag_source', 'tag_input', 'page_catalog', 'page_input', 'cover_input'):
                if suffix not in IMAGE_MIME and suffix not in ('.cbz', '.zip'):
                    raise PreviewUnavailable('Tagging requires an image, CBZ or ZIP')
            elif operation != 'preview' and suffix not in ('.cbz', '.zip'):
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
                current_revision = _revision(row, info) if operation not in ('preview', 'video') else None
                if revision is not None and revision != current_revision:
                    raise ReaderChanged('Archive changed; reopen the reader')
                if operation in ('tag_source', 'tag_input'):
                    result = {'item_id': item_id, 'revision': current_revision,
                              'kind': 'image' if suffix in IMAGE_MIME else 'cover', 'page': 0}
                if operation == 'video':
                    if info.st_size < 1 or info.st_size > MAX_PLAYBACK_BYTES:
                        raise PreviewUnavailable('Video exceeds playback limit')
                    data, mime = file.read(MAX_PLAYBACK_BYTES + 1), VIDEO_MIME[suffix]
                    if len(data) < 1 or len(data) > MAX_PLAYBACK_BYTES:
                        raise PreviewUnavailable('Video exceeds playback limit')
                    if data.lstrip()[:16].upper().startswith((b'#EXTM3U', b'[PLAYLIST]', b'<ASX')):
                        raise PreviewUnavailable('Playlist files are not played')
                elif operation in ('video_manifest','video_range','video_frame'):
                    if not 1 <= info.st_size <= MAX_STREAM_VIDEO_BYTES:
                        raise PreviewUnavailable('Video exceeds stream limit')
                    prefix=file.read(512).lstrip()
                    if not prefix or prefix[:16].upper().startswith((b'#EXTM3U',b'[PLAYLIST]',b'<ASX')):
                        raise PreviewUnavailable('Playlist files are not played')
                    mime=VIDEO_MIME[suffix]
                    if operation=='video_frame':
                        file.seek(0);data=self.videos.read(file,current_revision,at_ms=page);mime='image/png'
                    elif operation=='video_manifest':
                        result={'item_id':item_id,'size_bytes':info.st_size,'mime':mime,'revision':current_revision}
                    else:
                        if start>=info.st_size or end>=info.st_size:raise VideoRangeUnsatisfiable(info.st_size)
                        file.seek(start);data=file.read(end-start+1)
                        if len(data)!=end-start+1:raise ReaderChanged('Video changed during range read')
                elif suffix in VIDEO_SUFFIXES:
                    if info.st_size > MAX_VIDEO_BYTES:
                        raise PreviewUnavailable('Video exceeds preview limit')
                    data, mime = self.videos.read(file, _revision(row, info)), 'image/png'
                elif suffix in IMAGE_MIME:
                    if not 1 <= info.st_size <= MAX_LARGE_IMAGE_BYTES:
                        raise PreviewUnavailable('Image exceeds preview limit')
                    descriptor = describe_page(item_id, 'image', '', 0, 0, IMAGE_MIME[suffix], info.st_size)
                    if operation == 'page_catalog':
                        result = {'item_id': item_id, 'revision': current_revision,
                                  'source_kind': 'image', 'pages': [descriptor]}
                    elif operation == 'page_input':
                        if page != 0:
                            raise PreviewUnavailable('Page unavailable')
                        result = {'item_id': item_id, 'revision': current_revision,
                                  'kind': 'image', 'page': 0, 'page_id': descriptor['page_id']}
                    elif operation == 'image_manifest':
                        result = self.animations.inspect(file, info.st_size, current_revision, item_id, IMAGE_MIME[suffix])
                    elif operation == 'image_frame':
                        data = self.animations.render_frame(file, info.st_size, current_revision, page, VIEWER_MAX_EDGE)
                        mime = 'image/png'
                    if operation not in ('tag_source', 'page_catalog', 'image_manifest', 'image_frame'):
                        header = file.read(4096)
                        file.seek(0)
                        is_anim_header = detect_animation_header(header)
                        if info.st_size <= MAX_IMAGE_BYTES and not (operation in ('cover_input', 'tag_input') and is_anim_header):
                            data, mime = file.read(MAX_IMAGE_BYTES + 1), IMAGE_MIME[suffix]
                        else:
                            rev = current_revision or _revision(row, info)
                            meta = self.animations.inspect(file, info.st_size, rev, item_id, IMAGE_MIME[suffix])
                            if operation in ('cover_input', 'tag_input'):
                                rep = meta['representative_frame']
                                data = self.animations.render_frame(file, info.st_size, rev, rep, REPRESENTATIVE_MAX_EDGE)
                                mime = 'image/png'
                            else:
                                data = self.animations.render_frame(file, info.st_size, rev, 0, VIEWER_MAX_EDGE)
                                mime = 'image/png'
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
                        if operation == 'tag_source':
                            pass
                        elif operation in ('page_catalog', 'page_input'):
                            # Exact duplicate names have separate occurrence IDs;
                            # natural ties retain the archive's directory order.
                            occurrences = {}
                            described = []
                            for entry in entries:
                                occurrence = occurrences.get(entry.filename, 0)
                                occurrences[entry.filename] = occurrence + 1
                                described.append((entry, occurrence))
                            described.sort(key=lambda pair: natural_key(pair[0].filename))
                            descriptors = [describe_page(item_id, 'archive', entry.filename, occurrence, number,
                                IMAGE_MIME[PurePosixPath(entry.filename).suffix.casefold()], entry.file_size)
                                for number, (entry, occurrence) in enumerate(described)]
                            if operation == 'page_catalog':
                                result = {'item_id': item_id, 'revision': current_revision,
                                          'source_kind': 'archive', 'pages': descriptors}
                            else:
                                if page >= len(described):
                                    raise PreviewUnavailable('Page unavailable')
                                entry = described[page][0]
                                if (entry.flag_bits & 1 or entry.file_size > MAX_IMAGE_BYTES
                                        or entry.file_size > max(1, entry.compress_size) * 200):
                                    raise PreviewUnavailable('Archive image exceeds preview limits')
                                with archive.open(entry) as image:
                                    data = image.read(MAX_IMAGE_BYTES + 1)
                                mime = descriptors[page]['mime']
                                result = {'item_id': item_id, 'revision': current_revision, 'kind': 'page',
                                          'page': page, 'page_id': descriptors[page]['page_id']}
                        elif operation == 'manifest':
                            result = {'item_id':item_id, 'page_count':len(entries),
                                      'revision':current_revision}
                        else:
                            if page >= len(entries):
                                raise PreviewUnavailable('Page unavailable')
                            # Stable sort preserves central-directory order for
                            # duplicate names; open the ZipInfo, not its name.
                            entry = (min(entries, key=lambda e: natural_key(e.filename))
                                     if operation in ('preview', 'tag_input', 'cover_input') else
                                     sorted(entries, key=lambda e: natural_key(e.filename))[page])
                            if (entry.flag_bits & 1 or entry.file_size > MAX_IMAGE_BYTES
                                    or entry.file_size > max(1, entry.compress_size) * 200):
                                raise PreviewUnavailable('Archive image exceeds preview limits')
                            with archive.open(entry) as image:
                                data = image.read(MAX_IMAGE_BYTES + 1)
                            mime = IMAGE_MIME[PurePosixPath(entry.filename).suffix.casefold()]
                if operation not in ('manifest','video','video_manifest','video_range','tag_source','page_catalog','image_manifest') and len(data) > MAX_IMAGE_BYTES:
                    raise PreviewUnavailable('Image exceeds preview limit')
                after = os.fstat(file.fileno())
                if suffix in VIDEO_SUFFIXES or operation in ('tag_source', 'tag_input', 'page_catalog', 'page_input', 'image_manifest', 'image_frame', 'cover_input'):
                    # The native tools inherit this handle, never reopen a path.
                    # Do not publish its old frame if the location was replaced.
                    current = _safe_path(row['path'], row['relative_path']).stat(follow_symlinks=False)
                    if (current.st_ino, current.st_dev) != (info.st_ino, info.st_dev):
                        if operation in ('video_manifest','video_range','video_frame','tag_source','tag_input','page_catalog','page_input','image_manifest','image_frame'):raise ReaderChanged('Source location changed')
                        raise PreviewUnavailable('Location changed while previewing')
                if (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (info.st_size, info.st_mtime_ns, info.st_ctime_ns):
                    if operation not in ('preview', 'cover_input'):
                        raise ReaderChanged('Source changed while reading')
                    raise PreviewUnavailable('Source changed while reading')
                if operation == 'tag_source': return result
                if operation in ('tag_input', 'page_input'): return {'source': result, 'data': data, 'mime': mime}
                if operation in ('manifest','video_manifest','page_catalog','image_manifest'):
                    return result
                if operation=='video_range':return data,mime,info.st_size
                return data, mime
        except (VideoPreviewUnavailable, AnimationUnavailable) as error:
            raise PreviewUnavailable('Preview unavailable') from error
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, zlib.error) as error:
            raise PreviewUnavailable('Invalid or unsupported archive') from error
        finally:
            self.slots.release()



def _safe_folder(root, relative):
    """Directory of a folder book, rechecked for links/junctions on every read."""
    if relative == FOLDER_ROOT:
        directory = Path(root)
        for component in [*reversed(directory.parents), directory]:
            info = component.stat(follow_symlinks=False)
            if _reparse(info) or stat.S_ISLNK(info.st_mode):
                raise PreviewUnavailable('Linked locations are not previewed')
    else:
        inner = relative[:-1]
        if not inner or '.' in PurePosixPath(inner).parts:
            raise PreviewUnavailable('Invalid location')
        directory = _safe_path(root, inner)
    if not stat.S_ISDIR(directory.stat(follow_symlinks=False).st_mode):
        raise PreviewUnavailable('Folder book is no longer a folder')
    return directory


def folder_pages(directory, relative, patterns):
    """Direct image children as the scan sees them: regular, unlinked, not excluded."""
    pages = []
    with os.scandir(directory) as entries:
        for entry in entries:
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode) or _reparse(info) or not stat.S_ISREG(info.st_mode):
                continue
            if Path(entry.name).suffix.casefold() not in FOLDER_IMAGES:
                continue
            child = entry.name if relative == FOLDER_ROOT else relative + entry.name
            if _excluded(child, patterns):
                continue
            pages.append((entry.name, info.st_size, info.st_mtime_ns))
            if len(pages) > MAX_FOLDER_PAGES:
                raise PreviewUnavailable('Folder has too many pages')
    return pages


def _check_folder_path(row, directory_info):
    directory = _safe_folder(row['path'], row['relative_path'])
    current = directory.stat(follow_symlinks=False)
    if (current.st_dev, current.st_ino) != (directory_info.st_dev, directory_info.st_ino):
        raise ReaderChanged('Source location changed')
    return directory


def _check_folder(row, directory_info, pages):
    """Revalidate the path and complete inventory before publishing a response."""
    directory = _check_folder_path(row, directory_info)
    now = folder_pages(directory, row['relative_path'], tuple(json.loads(row['excludes_json'])))
    if sorted(now) != sorted(pages):
        raise ReaderChanged('Source changed while reading')
    # The directory may itself have been replaced during enumeration.
    return _check_folder_path(row, directory_info)


def _folder_read(row, item_id, operation, page, revision):
    """Pages of an image folder registered as one book. Read-only, bounded."""
    if operation in ('video', 'video_manifest', 'video_range', 'video_frame'):
        raise PreviewUnavailable('Video player requires a supported video item')
    if operation in ('image_manifest', 'image_frame'):
        raise PreviewUnavailable('Image viewer requires a supported image item')
    relative = row['relative_path']
    try:
        directory = _safe_folder(row['path'], relative)
        directory_info = directory.stat(follow_symlinks=False)
        pages = folder_pages(directory, relative, tuple(json.loads(row['excludes_json'])))
    except FileNotFoundError as error:
        raise PreviewUnavailable('Folder book unavailable') from error
    size, token = folder_signature(pages)
    if (size, token) != (row['size_bytes'], row['mtime_ns']):
        if operation != 'preview':
            raise ReaderChanged('Rescan changed files before reading')
        raise PreviewUnavailable('Rescan changed files before previewing')
    identity = [row['root_id'], relative, directory_info.st_dev, directory_info.st_ino, size, token]
    current_revision = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode('utf-8')).hexdigest()
    if revision is not None and revision != current_revision:
        raise ReaderChanged('Archive changed; reopen the reader')
    # scandir order is not stable. Natural ties (p1/p01, A/a) must not silently
    # change page numbers or the tagger's cover under the same revision.
    shown = sorted((p for p in pages if Path(p[0]).suffix.casefold() in IMAGE_MIME),
                   key=lambda p: (natural_key(p[0]), p[0]))
    if not shown:
        raise PreviewUnavailable('Folder has no supported image')
    source = {'item_id': item_id, 'revision': current_revision, 'kind': 'cover', 'page': 0}
    if operation == 'tag_source':
        _check_folder(row, directory_info, pages)
        return source
    if operation == 'manifest':
        _check_folder(row, directory_info, pages)
        return {'item_id': item_id, 'page_count': len(shown), 'revision': current_revision}
    if operation == 'page_catalog':
        _check_folder(row, directory_info, pages)
        return {'item_id': item_id, 'revision': current_revision, 'source_kind': 'folder',
                'pages': [describe_page(item_id, 'folder', name, 0, number,
                    IMAGE_MIME[Path(name).suffix.casefold()], size)
                    for number, (name, size, _) in enumerate(shown)]}
    index = page if operation in ('page', 'page_input') else 0
    if index >= len(shown):
        raise PreviewUnavailable('Page unavailable')
    name, expected_size, expected_mtime = shown[index]
    if expected_size > MAX_IMAGE_BYTES:
        raise PreviewUnavailable('Image exceeds preview limit')
    # Recheck ancestors before opening, then check the opened handle before
    # reading bytes. A folder may have become a link since the first inventory.
    path = _check_folder_path(row, directory_info) / name
    initial = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(initial.st_mode) or _reparse(initial):
        raise ReaderChanged('Source location changed')
    with path.open('rb') as file:
        info = os.fstat(file.fileno())
        if (not stat.S_ISREG(info.st_mode) or _reparse(info) or stat.S_ISLNK(initial.st_mode)
                or (info.st_ino, info.st_dev) != (initial.st_ino, initial.st_dev)
                or (info.st_size, info.st_mtime_ns) != (expected_size, expected_mtime)):
            raise ReaderChanged('Source changed while reading')
        current = _safe_path(row['path'], name if relative == FOLDER_ROOT else relative + name).stat(follow_symlinks=False)
        if (current.st_ino, current.st_dev) != (info.st_ino, info.st_dev):
            raise ReaderChanged('Source location changed')
        data = file.read(MAX_IMAGE_BYTES + 1)
        after = os.fstat(file.fileno())
        current = _safe_path(row['path'], name if relative == FOLDER_ROOT else relative + name).stat(follow_symlinks=False)
        # Path.stat and fstat may expose different creation-time values on
        # Windows. Match identity/size/mtime across APIs, but compare ctime
        # within each API before/after (the handle check follows below).
        if ((current.st_ino, current.st_dev, current.st_size, current.st_mtime_ns) != (
                info.st_ino, info.st_dev, info.st_size, info.st_mtime_ns)
                or current.st_ctime_ns != initial.st_ctime_ns):
            raise ReaderChanged('Source changed while reading')
        _check_folder(row, directory_info, pages)
    if len(data) > MAX_IMAGE_BYTES or len(data) != expected_size:
        raise ReaderChanged('Source changed while reading')
    if (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (info.st_size, info.st_mtime_ns, info.st_ctime_ns):
        raise ReaderChanged('Source changed while reading')
    mime = IMAGE_MIME[Path(name).suffix.casefold()]
    if operation == 'page_input':
        descriptor = describe_page(item_id, 'folder', name, 0, index, mime, expected_size)
        source = {'item_id': item_id, 'revision': current_revision, 'kind': 'page',
                  'page': index, 'page_id': descriptor['page_id']}
        return {'source': source, 'data': data, 'mime': mime}
    if operation == 'tag_input':
        return {'source': source, 'data': data, 'mime': mime}
    return data, mime

