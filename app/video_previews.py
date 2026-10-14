"""Optional first-frame thumbnails from an already validated, open source handle.

No source pathname is passed to FFmpeg. Pipe-only I/O and a demuxer allowlist
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
MAX_VIDEO_BYTES = 512 * 1024 * 1024
MAX_VIDEO_PIXELS = 16_000_000
MAX_FRAME_BYTES = 512 * 1024
MAX_PROBE_BYTES = 16 * 1024
VIDEO_EDGE = 256
VIDEO_TIMEOUT = 10.0
VIDEO_CACHE_ENTRIES = 32  # At most 16 MiB of derived PNG data; never disk cache.
FORMATS = 'mov,matroska,webm,avi,asf,mpegts'


class VideoPreviewUnavailable(ValueError):
    pass


def _executable(name):
    value = shutil.which(name)
    if not value or Path(value).suffix.casefold() in {'.bat', '.cmd'}:
        raise VideoPreviewUnavailable('Video preview tools unavailable')
    return str(Path(value).resolve())


def _run(args, source, limit, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise VideoPreviewUnavailable('Video preview deadline exceeded')
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
            process.wait(timeout=max(0.001, deadline - time.monotonic()))
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


def _validate_png(data):
    if (len(data) < 33 or len(data) > MAX_FRAME_BYTES
            or data[:8] != b'\x89PNG\r\n\x1a\n' or data[8:16] != b'\0\0\0\rIHDR'):
        raise VideoPreviewUnavailable('Invalid video thumbnail')
    width, height = struct.unpack_from('>II', data, 16)
    if min(width, height) < 1 or max(width, height) > VIDEO_EDGE:
        raise VideoPreviewUnavailable('Video thumbnail exceeds dimensions')


class VideoThumbnailer:
    def __init__(self):
        self.cache = OrderedDict()
        self.lock = threading.Lock()

    def read(self, source, revision):
        with self.lock:
            if revision in self.cache:
                self.cache.move_to_end(revision)
                return self.cache[revision]
        ffprobe, ffmpeg = _executable('ffprobe'), _executable('ffmpeg')
        deadline = time.monotonic() + VIDEO_TIMEOUT
        # These options are input-scoped. Only the already open stdin handle
        # can be read, including when a container tries to reference another file.
        common = ['-v', 'error', '-max_alloc', str(64 * 1024 * 1024),
                  '-protocol_whitelist', 'pipe', '-format_whitelist', FORMATS,
                  '-probesize', '1048576', '-analyzeduration', '1000000',
                  '-max_streams', '16', '-max_probe_packets', '128',
                  '-threads', '1', '-max_pixels', str(MAX_VIDEO_PIXELS)]
        probe = _run([ffprobe, *common, '-select_streams', 'V:0',
                      '-show_entries', 'stream=width,height', '-of', 'json',
                      '-i', 'pipe:0'], source, MAX_PROBE_BYTES, deadline)
        _dimensions(probe)
        png = _run([ffmpeg, '-nostdin', *common, '-i', 'pipe:0',
                    '-map', '0:V:0', '-an', '-sn', '-dn', '-frames:v', '1',
                    '-vf', "scale=w='min(256,iw)':h='min(256,ih)':force_original_aspect_ratio=decrease,setsar=1",
                    '-filter_threads', '1', '-threads', '1', '-c:v', 'png',
                    '-f', 'image2pipe', 'pipe:1'], source, MAX_FRAME_BYTES, deadline)
        _validate_png(png)
        with self.lock:
            self.cache[revision] = png
            self.cache.move_to_end(revision)
            while len(self.cache) > VIDEO_CACHE_ENTRIES:
                self.cache.popitem(last=False)
        return png
