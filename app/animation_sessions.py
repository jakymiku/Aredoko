"""Owned, pull-driven Pillow decoders. No paths, PNG cache or whole-file scan.

The source factory transfers a validated open handle. Each pull revalidates the
current catalog/path and the retained handle before and after decoding. Frames
are composited by Pillow, then sent as premultiplied BGRA for WriteableBitmap.
"""
import json
import os
import re
import struct
import threading
import time

from image_animations import (AnimationUnavailable, MAX_IMAGE_PIXELS,
                              VIEWER_MAX_EDGE, _clamp_duration, _clamp_loop)

MAX_BATCH_FRAMES = 4
MAX_BATCH_BYTES = 128 * 1024 * 1024
MAX_SESSIONS = 3
IDLE_SECONDS = 300
MIME = 'application/vnd.aredoko.animation-frame-batch'


class AnimationBusy(ValueError):
    pass


class AnimationGone(ValueError):
    pass


def _identity(file):
    s = os.fstat(file.fileno())
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


class Decoder:
    def __init__(self, file, info, validate):
        self.file, self.info, self.validate = file, info, validate
        self.lock = threading.Lock()
        self.cancelled = threading.Event()
        self.last_used = time.monotonic()
        self.image = None
        try:
            from PIL import Image
            self.identity = _identity(file)
            self.image = Image.open(file)
            width, height = self.image.size
            if not (1 <= width <= 16384 and 1 <= height <= 16384
                    and width * height <= MAX_IMAGE_PIXELS):
                raise AnimationUnavailable('Image dimensions exceed limit')
            # Do not ask GIF n_frames/is_animated: they seek the entire stream.
            self.first = 1 if self.image.info.get('default_image', False) else 0
            self.image.seek(self.first)
            loop = self.image.info.get('loop')
            self.plays = (1 if loop is None else 0 if _clamp_loop(loop) == 0
                          else _clamp_loop(loop) + (1 if self.image.format == 'GIF' else 0))
            scale = min(1.0, VIEWER_MAX_EDGE / max(width, height))
            self.width, self.height = max(1, round(width * scale)), max(1, round(height * scale))
            self.index = self.cycle = self.sequence = 0
            self.advance = False
            self.done = False
        except Exception:
            self.close()
            raise

    def check(self):
        if self.cancelled.is_set():
            raise AnimationGone('Animation session closed')
        self.validate(self.info['revision'])
        if self.cancelled.is_set():
            raise AnimationGone('Animation session closed')
        if _identity(self.file) != self.identity:
            raise AnimationGone('Animation source changed')

    def _reopen_loop(self):
        from PIL import Image
        self.check()
        if self.image is not None:
            self.image.fp = None
            if hasattr(self.image, '_fp'):
                self.image._fp = None
            self.image.close()
            self.image = None
        self.file.seek(0)
        self.image = Image.open(self.file)
        width, height = self.image.size
        scale = min(1.0, VIEWER_MAX_EDGE / max(width, height))
        if max(1, round(width * scale)) != self.width or max(1, round(height * scale)) != self.height:
            raise AnimationGone('Animation source changed')
        self.image.seek(self.first)
        self.index = 0

    def pull(self, count):
        from PIL import Image
        if not self.lock.acquire(blocking=False):
            raise AnimationBusy('Animation pull already in progress')
        try:
            self.last_used = time.monotonic()
            self.check()
            frames, pixels = [], []
            frame_bytes = self.width * self.height * 4
            for _ in range(min(count, MAX_BATCH_BYTES // frame_bytes)):
                if self.done:
                    break
                if self.cancelled.is_set():
                    raise AnimationGone('Animation session closed')
                if self.advance:
                    try:
                        self.image.seek(self.first + self.index + 1)
                        self.index += 1
                    except EOFError:
                        self.cycle += 1
                        if self.plays and self.cycle >= self.plays:
                            self.done = True
                            break
                        self._reopen_loop()
                rgba = self.image.convert('RGBA')
                try:
                    if rgba.size != (self.width, self.height):
                        resized = rgba.resize((self.width, self.height), Image.Resampling.LANCZOS)
                        rgba.close()
                        rgba = resized
                    premultiplied = rgba.convert('RGBa')
                    try:
                        data = premultiplied.tobytes('raw', 'BGRa')
                    finally:
                        premultiplied.close()
                finally:
                    rgba.close()
                frames.append({'sequence': self.sequence, 'index': self.index, 'cycle': self.cycle,
                               'duration_ms': _clamp_duration(self.image.info.get('duration', 100)),
                               'byte_length': len(data)})
                pixels.append(data)
                self.sequence += 1
                self.advance = True
            self.check()
            self.last_used = time.monotonic()
            header = {**self.info, 'width': self.width, 'height': self.height,
                      'stride': self.width * 4, 'pixel_format': 'bgra8',
                      'alpha': 'premultiplied', 'frames': frames, 'done': self.done}
            encoded = json.dumps(header, separators=(',', ':')).encode('utf-8')
            return struct.pack('<I', len(encoded)) + encoded + b''.join(pixels)
        finally:
            self.lock.release()
            if self.cancelled.is_set():
                self.close()

    def close(self):
        self.cancelled.set()
        # A cancelled active decoder closes in pull's finally. Never close a
        # Pillow object concurrently with its seek/convert operation.
        if not self.lock.acquire(blocking=False):
            return
        try:
            if self.image is not None:
                self.image.close()
                self.image = None
            self.file.close()
        finally:
            self.lock.release()


class AnimationSessions:
    def __init__(self, previews):
        self.previews = previews
        self.sessions = {}
        self.closed_ids = {}
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.reaper = None

    def _expire(self):
        self.closed_ids = {key: stamp for key, stamp in self.closed_ids.items()
                           if time.monotonic() - stamp <= IDLE_SECONDS}
        expired = [key for key, decoder in self.sessions.items()
                   if time.monotonic() - decoder.last_used > IDLE_SECONDS]
        for key in expired:
            self.sessions.pop(key).close()

    def _reap(self):
        while not self.stopped.wait(5):
            with self.lock:
                self._expire()

    def open(self, item_id, revision, session_id):
        self.validate_id(session_id)
        if type(item_id) is not int or not 1 <= item_id <= 9223372036854775807:
            raise ValueError('Invalid item')
        if type(revision) is not str or re.fullmatch('[0-9a-f]{64}', revision) is None:
            raise ValueError('Invalid revision')
        with self.lock:
            self._expire()
            if self.stopped.is_set():
                raise AnimationGone('Animation owner closed')
            if session_id in self.closed_ids or session_id in self.sessions:
                raise AnimationGone('Animation session already used')
            if len(self.closed_ids) >= 4096:
                raise AnimationBusy('Too many recently closed animation sessions')
            if len(self.sessions) >= MAX_SESSIONS:
                raise AnimationBusy('Too many animation sessions')
            file, info = self.previews.animation_source(item_id, revision)
            def validate(expected):
                self.previews.validate_animation(item_id, expected, file)
            try:
                decoder = Decoder(file, {**info, 'session_id': session_id}, validate)
            except Exception:
                file.close()
                raise
            self.sessions[session_id] = decoder
            if self.reaper is None:
                self.reaper = threading.Thread(target=self._reap, daemon=True, name='animation-owner')
                self.reaper.start()
            return {**info, 'session_id': session_id, 'max_batch_frames': MAX_BATCH_FRAMES,
                    'max_batch_bytes': MAX_BATCH_BYTES}

    def open_first(self, item_id, revision, session_id):
        # The client chooses the ID before sending, retaining close-before-open
        # protection when this combined response is cancelled or lost.
        self.open(item_id, revision, session_id)
        return self.pull(session_id, 1)

    @staticmethod
    def validate_id(session_id):
        if type(session_id) is not str or re.fullmatch('[0-9a-f]{32}', session_id) is None:
            raise ValueError('Invalid animation session')

    def pull(self, session_id, count=1):
        self.validate_id(session_id)
        if type(count) is not int or not 1 <= count <= MAX_BATCH_FRAMES:
            raise ValueError('Invalid animation batch size')
        with self.lock:
            self._expire()
            decoder = self.sessions.get(session_id)
            if decoder is None:
                raise AnimationGone('Animation session expired')
        try:
            return decoder.pull(count)
        except AnimationBusy:
            raise
        except Exception:
            self.cancel(session_id)
            raise

    def cancel(self, session_id):
        self.validate_id(session_id)
        with self.lock:
            self._expire()
            if len(self.closed_ids) >= 4096 and session_id not in self.closed_ids and session_id not in self.sessions:
                raise AnimationBusy('Too many recently closed animation sessions')
            self.closed_ids[session_id] = time.monotonic()
            decoder = self.sessions.pop(session_id, None)
        if decoder is not None:
            decoder.close()
        return {'closed': True}

    def close(self):
        self.stopped.set()
        with self.lock:
            decoders = list(self.sessions.values())
            self.sessions.clear()
        for decoder in decoders:
            decoder.close()
