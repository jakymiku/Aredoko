"""Bounded temporary H.264/AAC MP4 transcoding fallback for videos incompatible with inbox codecs.

Uses already validated read-only file handles (`fd:` input) and bundled ffmpeg;
never passes source pathnames to child processes and never modifies originals.
"""
from collections import OrderedDict
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import threading

from previews import PreviewUnavailable, ReaderChanged, MAX_VIDEO_RANGE_BYTES, VideoRangeUnsatisfiable
from video_previews import FORMATS, MAX_VIDEO_PIXELS, _executable

MAX_COMPAT_BYTES = 256 * 1024 * 1024
MAX_COMPAT_ENTRIES = 4
TRANSCODE_TIMEOUT = 45.0


class _Entry:
    def __init__(self, path: Path, size_bytes: int):
        self.path = path
        self.size_bytes = size_bytes


class _Job:
    def __init__(self):
        self.ready = threading.Event()
        self.entry: _Entry | None = None
        self.error: Exception | None = None


class VideoCompatCache:
    def __init__(self, previews, *, max_bytes=MAX_COMPAT_BYTES, max_entries=MAX_COMPAT_ENTRIES):
        self.previews = previews
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self.lock = threading.Lock()
        self.cache: OrderedDict[tuple[int, str], _Entry] = OrderedDict()
        self.jobs: dict[tuple[int, str], _Job] = {}
        self.total_bytes = 0
        self.closed = False
        self.directory: tempfile.TemporaryDirectory | None = None

    def close(self):
        with self.lock:
            self.closed = True
            self.cache.clear()
            self.total_bytes = 0
            directory = self.directory
            self.directory = None
        if directory is not None:
            directory.cleanup()

    def _ensure_dir(self) -> Path:
        if self.closed:
            raise PreviewUnavailable('Compat cache closed')
        if self.directory is None:
            self.directory = tempfile.TemporaryDirectory(prefix='aredoko-video-compat-', ignore_cleanup_errors=True)
        return Path(self.directory.name)

    def _evict_to_budget_locked(self):
        while self.total_bytes > self.max_bytes or len(self.cache) > self.max_entries:
            _, evicted = self.cache.popitem(last=False)
            self.total_bytes -= evicted.size_bytes
            try:
                evicted.path.unlink(missing_ok=True)
            except OSError:
                pass

    def _transcode(self, source_handle, target_path: Path) -> int:
        ffmpeg = _executable('ffmpeg')
        source_handle.seek(0, os.SEEK_END)
        source_handle.seek(0)
        part_path = target_path.with_suffix('.part.mp4')
        env = {k: v for k, v in os.environ.items() if k.upper() != 'FFREPORT'}
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        args = [
            ffmpeg, '-nostdin', '-v', 'error', '-max_alloc', str(128 * 1024 * 1024),
            '-protocol_whitelist', 'fd,pipe', '-format_whitelist', FORMATS,
            '-probesize', '4194304', '-analyzeduration', '3000000',
            '-max_streams', '16', '-max_probe_packets', '512',
            '-max_pixels', str(MAX_VIDEO_PIXELS),
            '-i', 'fd:',
            '-map', '0:V:0', '-map', '0:a:0?',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22', '-pix_fmt', 'yuv420p',
            '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
            '-c:a', 'aac', '-b:a', '128k',
            '-threads', '2', '-movflags', '+faststart', '-f', 'mp4', str(part_path),
        ]
        try:
            proc = subprocess.Popen(
                args, stdin=source_handle, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                shell=False, env=env, creationflags=flags,
            )
            try:
                rc = proc.wait(timeout=TRANSCODE_TIMEOUT)
            except subprocess.TimeoutExpired as err:
                proc.kill()
                proc.wait()
                raise PreviewUnavailable('Compat video transcode timed out') from err
            if rc != 0 or not part_path.is_file():
                raise PreviewUnavailable('Compat video transcode failed')
            size = part_path.stat().st_size
            if size < 64 or size > self.max_bytes:
                raise PreviewUnavailable('Compat video output outside size budget')
            os.replace(part_path, target_path)
            return size
        except BaseException:
            try:
                part_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def manifest(self, item_id: int) -> dict:
        revision = self.previews.video_compat_revision(item_id)
        key = (item_id, revision)
        with self.lock:
            if self.closed:
                raise PreviewUnavailable('Compat cache closed')
            hit = self.cache.get(key)
            if hit is not None and hit.path.is_file():
                self.cache.move_to_end(key)
                return {'item_id': item_id, 'size_bytes': hit.size_bytes, 'mime': 'video/mp4', 'revision': revision}
            job = self.jobs.get(key)
            leader = job is None
            if leader:
                job = _Job()
                self.jobs[key] = job
        if not leader:
            job.ready.wait(timeout=TRANSCODE_TIMEOUT + 5.0)
            if job.error is not None:
                raise job.error
            if job.entry is None or not job.entry.path.is_file():
                raise PreviewUnavailable('Compat video unavailable')
            return {'item_id': item_id, 'size_bytes': job.entry.size_bytes, 'mime': 'video/mp4', 'revision': revision}

        entry: _Entry | None = None
        try:
            with self.lock:
                out_dir = self._ensure_dir()
            out_path = out_dir / f'{item_id}-{revision[:12]}-{secrets.token_hex(4)}.mp4'
            with self.previews.open_video_for_compat(item_id, revision) as (handle, _):
                size_bytes = self._transcode(handle, out_path)
            # Revalidate live catalog state before publishing derived stream
            if self.previews.video_compat_revision(item_id) != revision:
                out_path.unlink(missing_ok=True)
                raise ReaderChanged('Video changed during compat preparation')
            entry = _Entry(out_path, size_bytes)
            with self.lock:
                if self.closed:
                    out_path.unlink(missing_ok=True)
                    raise PreviewUnavailable('Compat cache closed')
                old = self.cache.pop(key, None)
                if old is not None:
                    self.total_bytes -= old.size_bytes
                    try:
                        old.path.unlink(missing_ok=True)
                    except OSError:
                        pass
                self.cache[key] = entry
                self.total_bytes += size_bytes
                self._evict_to_budget_locked()
            job.entry = entry
            return {'item_id': item_id, 'size_bytes': entry.size_bytes, 'mime': 'video/mp4', 'revision': revision}
        except Exception as err:
            job.error = err
            raise
        finally:
            job.ready.set()
            with self.lock:
                if self.jobs.get(key) is job:
                    self.jobs.pop(key, None)

    def read_range(self, item_id: int, start: int, end: int, revision: str):
        if type(start) is not int or type(end) is not int or start < 0 or end < start or end - start + 1 > MAX_VIDEO_RANGE_BYTES:
            raise ValueError('Invalid bounded video range')
        # Enforce live catalog authorization/exclusions/revision on every range read
        if self.previews.video_compat_revision(item_id) != revision:
            raise ReaderChanged('Video changed; reopen')
        key = (item_id, revision)
        with self.lock:
            if self.closed:
                raise PreviewUnavailable('Compat cache closed')
            entry = self.cache.get(key)
            if entry is None or not entry.path.is_file():
                raise ReaderChanged('Compat stream expired; reopen')
            self.cache.move_to_end(key)
            path = entry.path
            size_bytes = entry.size_bytes
        if start >= size_bytes or end >= size_bytes:
            raise VideoRangeUnsatisfiable(size_bytes)
        with path.open('rb') as stream:
            stream.seek(start)
            data = stream.read(end - start + 1)
        if len(data) != end - start + 1:
            raise ReaderChanged('Compat video stream truncated')
        return data, 'video/mp4', size_bytes
