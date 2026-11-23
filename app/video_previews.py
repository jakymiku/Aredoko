"""Bounded thumbnails from an already validated, open source handle.

No source pathname is passed to FFmpeg. Pipe/fd-only I/O and a demuxer allowlist
exclude playlists/external resources; non-streamable containers may fail safely.
Limits bound application output and worker lifetime, not total native heap use.
"""
import json
import os
import shutil
import struct
import subprocess
import threading
import time
from collections import OrderedDict
from pathlib import Path

VIDEO_SUFFIXES = frozenset({'.mp4', '.mkv', '.webm', '.avi', '.mov', '.wmv', '.m4v', '.ts'})
# Input is a seekable handle, never a whole-file bytes allocation. Keep native
# time/pixel/probe/output budgets while allowing ordinary multi-GB local videos.
MAX_VIDEO_BYTES = 32 * 1024 ** 3
MAX_VIDEO_PIXELS = 16_000_000
MAX_FRAME_BYTES = 512 * 1024
MAX_PROBE_BYTES = 16 * 1024
VIDEO_EDGE = 256
MIN_VIDEO_EDGE = 128
MAX_VIDEO_EDGE = 512
VIDEO_TIMEOUT = 10.0
VIDEO_CACHE_ENTRIES = 32  # At most 16 MiB of derived PNG data; never disk cache.
FORMATS = 'mov,matroska,webm,avi,asf,mpegts'
# Convert the displayed geometry to square pixels before bounding each edge.
# Merely setting SAR=1 after a raw-pixel resize distorts anamorphic videos.
# Explicit expressions also work on older installed builds without reset_sar.
_display_width = 'iw*if(gt(sar,0),sar,1)'


def _thumbnail_filter(edge=VIDEO_EDGE):
    scale = f'min(1,min({edge}/({_display_width}),{edge}/ih))'
    return (f"scale=w='max(1,trunc(({_display_width})*{scale}))':"
            f"h='max(1,trunc(ih*{scale}))',setsar=1")


THUMBNAIL_FILTER = _thumbnail_filter(VIDEO_EDGE)


class VideoPreviewUnavailable(ValueError):
    pass


class MediaDecodeCancelled(Exception):
    """An explicitly owned native decode was cancelled and reaped."""


def _executable(name):
    media = os.environ.get('AREDOKO_MEDIA_TOOLS')
    if media is not None:
        from storage_lease import plain_path
        try:
            value = str(plain_path(Path(media) / (name + ('.exe' if os.name == 'nt' else ''))))
        except (ValueError, OSError) as error:
            raise VideoPreviewUnavailable('Video preview tools unavailable') from error
    else:
        value = shutil.which(name)
    if not value or Path(value).suffix.casefold() in {'.bat', '.cmd'}:
        raise VideoPreviewUnavailable('Video preview tools unavailable')
    return str(Path(value).resolve())


def _run(args, source, limit, deadline, cancel=None):
    if cancel is not None and cancel.is_set():raise MediaDecodeCancelled('Media decode cancelled')
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise VideoPreviewUnavailable('Video preview deadline exceeded')
    # Invalidate Python read-ahead before handing the descriptor to a child.
    # A buffered seek within an existing buffer may not reset its OS offset.
    source.seek(0, os.SEEK_END)
    source.seek(0)
    # FFREPORT can otherwise make an inherited environment write a log file.
    environment = {k: v for k, v in os.environ.items() if k.upper() != 'FFREPORT'}
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with subprocess.Popen(args, stdin=source, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, shell=False, env=environment,
                          creationflags=flags) as process:
        output = bytearray()
        failed = []

        def drain():
            try:
                while chunk := process.stdout.read(8192):
                    if len(output) + len(chunk) > limit:
                        failed.append('Video preview output exceeds limit')
                        process.kill()
                        return
                    output.extend(chunk)
            except OSError:
                failed.append('Video preview output unavailable')

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        try:
            if cancel is None:
                process.wait(timeout=max(0.001, deadline - time.monotonic()))
            else:
                while process.poll() is None:
                    if cancel.is_set():raise MediaDecodeCancelled('Media decode cancelled')
                    remaining=deadline-time.monotonic()
                    if remaining<=0:raise subprocess.TimeoutExpired(args,0)
                    try:process.wait(timeout=min(.05,remaining))
                    except subprocess.TimeoutExpired:pass
                if cancel.is_set():raise MediaDecodeCancelled('Media decode cancelled')
        except MediaDecodeCancelled:
            if process.poll() is None:process.kill()
            process.wait()
            raise
        except subprocess.TimeoutExpired as error:
            process.kill()
            process.wait()
            raise VideoPreviewUnavailable('Video preview deadline exceeded') from error
        finally:
            # The child is reaped before the shared preview slot is returned.
            reader.join()
        if failed or process.returncode != 0 or time.monotonic() > deadline:
            raise VideoPreviewUnavailable(failed[0] if failed else 'Video preview unavailable')
        return bytes(output)


def _dimensions(document):
    try:
        data = json.loads(document)
        streams = data['streams']
        if not isinstance(streams, list) or len(streams) != 1:
            raise ValueError()
        width, height = streams[0]['width'], streams[0]['height']
        if (type(width) is not int or type(height) is not int or min(width, height) < 1
                or width * height > MAX_VIDEO_PIXELS):
            raise ValueError()
    except (ValueError, KeyError, TypeError, IndexError) as error:
        raise VideoPreviewUnavailable('Video dimensions unavailable or exceed limits') from error


def _validate_png(data, max_edge=VIDEO_EDGE):
    if (len(data) < 33 or len(data) > MAX_FRAME_BYTES
            or data[:8] != b'\x89PNG\r\n\x1a\n' or data[8:16] != b'\0\0\0\rIHDR'):
        raise VideoPreviewUnavailable('Invalid video thumbnail')
    width, height = struct.unpack_from('>II', data, 16)
    if min(width, height) < 1 or max(width, height) > max_edge:
        raise VideoPreviewUnavailable('Video thumbnail exceeds dimensions')


def _video_representative_times_ms(duration_seconds):
    try:
        dur = float(duration_seconds)
    except (TypeError, ValueError):
        return [0]
    if not (dur > 0 and dur <= 86400):
        return [0]
    total_ms = int(round(dur * 1000))
    if total_ms <= 600:
        return [0]
    if total_ms <= 2500:
        candidates = [0, max(0, min(total_ms - 100, total_ms // 2)), max(0, total_ms - 250)]
    else:
        candidates = [
            min(total_ms - 100, max(0, int(total_ms * 0.10))),
            min(total_ms - 100, max(0, int(total_ms * 0.35))),
            min(total_ms - 100, max(0, int(total_ms * 0.60))),
            min(total_ms - 100, max(0, int(total_ms * 0.85))),
        ]
    out = []
    for ms in candidates:
        clamped = max(0, min(86_400_000, int(ms)))
        if not out or abs(clamped - out[-1]) >= 250:
            out.append(clamped)
    return out or [0]


class VideoThumbnailer:
    def __init__(self):
        self.cache = OrderedDict()
        self.lock = threading.Lock()

    def representative_frames(self, source, revision):
        """Extract up to 4 time-coded representative PNG frames for AI video content indexing."""
        ffprobe, _ = _executable('ffprobe'), _executable('ffmpeg')
        deadline = time.monotonic() + VIDEO_TIMEOUT
        common = ['-v', 'error', '-max_alloc', str(64 * 1024 * 1024),
                  '-protocol_whitelist', 'fd,pipe', '-format_whitelist', FORMATS,
                  '-probesize', '4194304', '-analyzeduration', '3000000',
                  '-max_streams', '16', '-max_probe_packets', '512',
                  '-threads', '1', '-max_pixels', str(MAX_VIDEO_PIXELS)]
        probe = _run([ffprobe, *common, '-select_streams', 'V:0',
                      '-show_entries', 'stream=width,height,duration:format=duration', '-of', 'json',
                      '-i', 'fd:'], source, MAX_PROBE_BYTES, deadline)
        _dimensions(probe)
        data = json.loads(probe)
        dur = (data.get('streams') or [{}])[0].get('duration') or (data.get('format') or {}).get('duration')
        times = _video_representative_times_ms(dur)
        frames = []
        for at_ms in times:
            try:
                png = self.read(source, revision, at_ms=at_ms if at_ms > 0 else None)
                frames.append((at_ms, png))
            except VideoPreviewUnavailable:
                if at_ms == 0:
                    raise
        if not frames:
            frames.append((0, self.read(source, revision, at_ms=None)))
        return frames

    def read(self, source, revision, at_ms=None, edge=VIDEO_EDGE):
        if at_ms is not None and (type(at_ms) is not int or not 0 <= at_ms <= 86_400_000):
            raise ValueError('Invalid video frame time')
        if type(edge) is not int or not MIN_VIDEO_EDGE <= edge <= MAX_VIDEO_EDGE:
            raise ValueError('Invalid video thumbnail size')
        cache_key = (revision if at_ms is None else (revision, at_ms)) if edge == VIDEO_EDGE else (revision, at_ms, edge)
        with self.lock:
            if cache_key in self.cache:
                self.cache.move_to_end(cache_key)
                return self.cache[cache_key]
        ffprobe, ffmpeg = _executable('ffprobe'), _executable('ffmpeg')
        deadline = time.monotonic() + VIDEO_TIMEOUT
        # Always use seekable fd: on the already open regular-file handle so
        # non-faststart MP4/MOV (moov after >1 MiB mdat) probe cleanly with no paths.
        common = ['-v', 'error', '-max_alloc', str(64 * 1024 * 1024),
                  '-protocol_whitelist', 'fd,pipe', '-format_whitelist', FORMATS,
                  '-probesize', '4194304', '-analyzeduration', '3000000',
                  '-max_streams', '16', '-max_probe_packets', '512',
                  '-threads', '1', '-max_pixels', str(MAX_VIDEO_PIXELS)]
        input_url = 'fd:'
        probe = _run([ffprobe, *common, '-select_streams', 'V:0',
                      '-show_entries', 'stream=width,height', '-of', 'json',
                      '-i', input_url], source, MAX_PROBE_BYTES, deadline)
        _dimensions(probe)
        vf = THUMBNAIL_FILTER if edge == VIDEO_EDGE else _thumbnail_filter(edge)
        png = _run([ffmpeg, '-nostdin', *common, *([] if at_ms is None else ['-ss', f'{at_ms / 1000:.3f}']), '-i', input_url,
                    '-map', '0:V:0', '-an', '-sn', '-dn', '-frames:v', '1',
                    '-vf', vf,
                    '-filter_threads', '1', '-threads', '1', '-c:v', 'png',
                    '-f', 'image2pipe', 'pipe:1'], source, MAX_FRAME_BYTES, deadline)
        _validate_png(png, max_edge=edge)
        with self.lock:
            self.cache[cache_key] = png
            self.cache.move_to_end(cache_key)
            while len(self.cache) > VIDEO_CACHE_ENTRIES:
                self.cache.popitem(last=False)
        return png
