"""Guarded, bounded derived PNGs. No paths or original media are written.

The request which creates a job does its work; other requests share its result.
Disconnecting that request only abandons work when no other waiter needs it.
"""
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field
import io
import os
import threading
import time

import native_accel
from previews import PreviewUnavailable, PreviewBusyError, ReaderChanged
from image_animations import (
    MAX_IMAGE_PIXELS,
    MAX_RENDERED_PNG_BYTES,
    MAX_STREAM_IMAGE_BYTES,
    detect_animation_header,
)
from thumbnail_disk import ThumbnailDisk

EDGES = (128, 256, 512, 1024)
METHOD = 'first-visible-exif-rgba-lanczos-v1'
CACHE_BYTES = 512 * 1024 * 1024
CACHE_ENTRIES = 8192
MAX_JOBS = 32


class ThumbnailCancelled(Exception):
    pass


class DecodeBudget:
    """64 MiB estimated decoded-work admission; one oversize image runs alone.

    Pillow/native codec heap and compressed inputs are not hard RSS bounded.
    Rejecting previously supported large originals just to meet an estimate
    would break browsing, so oversize work takes the entire reservation.
    """
    def __init__(self, capacity=64 * 1024 * 1024):
        self.capacity = capacity
        self.used = 0
        self.changed = threading.Condition()
        self.closed = False

    @contextmanager
    def reserve(self, estimate, stopped):
        charge = min(self.capacity, max(1, estimate))
        while True:
            if stopped():
                raise ThumbnailCancelled()
            with self.changed:
                if self.closed:
                    raise ThumbnailCancelled()
                if self.used + charge <= self.capacity:
                    self.used += charge
                    break
                self.changed.wait(.05)
        try:
            if stopped():
                raise ThumbnailCancelled()
            yield
        finally:
            with self.changed:
                self.used -= charge
                self.changed.notify_all()

    def close(self):
        with self.changed:
            self.closed = True
            self.changed.notify_all()


@dataclass
class _Job:
    ready: threading.Event = field(default_factory=threading.Event)
    stop: threading.Event = field(default_factory=threading.Event)
    waiters: int = 0
    visible_waiters: int = 0
    order: int = 0
    running: bool = False
    result: tuple | None = None
    error: Exception | None = None


class ThumbnailCache:
    def __init__(self, previews, *, max_bytes=CACHE_BYTES, max_entries=CACHE_ENTRIES, disk_path=None, disk_max_bytes=None, max_active=2):
        self.previews = previews
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self.max_active = max(1, int(max_active))
        self.lock = threading.Lock()
        self.disk_lock = threading.Lock()
        self.changed = threading.Condition(self.lock)
        self.active = 0
        self.order = 0
        self.cache = OrderedDict()
        self.bytes = 0
        self.jobs = {}
        self.closed = False
        disk_kwargs = {} if disk_max_bytes is None else {'max_bytes': disk_max_bytes}
        self.disk = ThumbnailDisk(path=disk_path, **disk_kwargs)
        self.decode_budget = DecodeBudget()

    def close(self):
        with self.lock:
            self.closed = True
            self.cache.clear()
            self.bytes = 0
            self.decode_budget.close()
            for job in self.jobs.values():
                job.stop.set()
            self.changed.notify_all()
        with self.disk_lock:
            self.disk.close()

    def _acquire(self, job, stopped):
        while True:
            if stopped():
                raise ThumbnailCancelled()
            with self.changed:
                if job.stop.is_set():
                    raise ThumbnailCancelled()
                pending = [value for value in self.jobs.values()
                           if not value.running and not value.ready.is_set() and not value.stop.is_set()]
                first = min(pending, key=lambda value: (not bool(value.visible_waiters), value.order), default=None)
                if self.active < self.max_active and first is job:
                    job.running = True
                    self.active += 1
                    self.changed.notify_all()
                    return
                self.changed.wait(.05)

    def _release(self, job):
        with self.changed:
            job.running = False
            self.active -= 1
            # Mark done before selecting the next pending job.
            job.ready.set()
            self.changed.notify_all()

    @staticmethod
    def _source_call(operation, stopped):
        # PreviewReader also has two slots. Completed shared callers must not
        # race active builders into a spurious 503 during post-validation.
        deadline = time.monotonic() + 10
        while True:
            if stopped():
                raise ThumbnailCancelled()
            try:
                return operation()
            except PreviewBusyError:
                if time.monotonic() >= deadline:
                    raise
                threading.Event().wait(.02)

    def _probe(self, item_id):
        kind = self.previews.catalog.get(item_id)['kind']
        if kind == 'image':
            info = self.previews.image_info(item_id)
        elif kind in ('book', 'archive'):
            info = self.previews.manifest(item_id)
        elif kind == 'video':
            info = self.previews.video_manifest(item_id)
        else:
            raise PreviewUnavailable('No derived thumbnail for this media')
        return kind, info['revision']

    def _validate(self, item_id, kind, revision, result):
        if self._probe(item_id) != (kind, revision):
            raise ReaderChanged('Thumbnail source changed')
        if kind not in ('image', 'video'):
            data, _, tag = self.previews.page_source(item_id, 0, revision, result[1])
            if data is not None or tag != result[1]:
                raise ReaderChanged('Thumbnail page changed')

    def _put_ram(self, key, result):
        data = result[0]
        if self.closed or len(data) > self.max_bytes:
            return
        previous = self.cache.pop(key, None)
        if previous is not None:
            self.bytes -= len(previous[0])
        self.cache[key] = result
        self.bytes += len(data)
        while self.bytes > self.max_bytes or len(self.cache) > self.max_entries:
            _, removed = self.cache.popitem(last=False)
            self.bytes -= len(removed[0])

    def _put(self, key, result):
        if self.closed:
            return
        self._put_ram(key, result)
        self.disk.put(key, result)

    def read(self, item_id, edge=256, *, priority='visible', cancelled=lambda: False):
        if type(priority) is not str or priority not in ('visible', 'nearby'):
            raise ValueError('Invalid thumbnail priority')
        if type(edge) is not int or edge not in EDGES:
            raise ValueError('Invalid thumbnail size')
        if cancelled():
            raise ThumbnailCancelled()
        kind, revision = self._source_call(lambda: self._probe(item_id), cancelled)
        key = (METHOD, kind, item_id, revision, 0, edge)
        from_disk = False
        with self.lock:
            if self.closed:
                raise ThumbnailCancelled()
            result = self.cache.get(key)
            if result is not None:
                self.cache.move_to_end(key)
        if result is None:
            with self.disk_lock:
                disk_result = None if self.closed else self.disk.get(key)
            with self.lock:
                if self.closed:
                    raise ThumbnailCancelled()
                result = self.cache.get(key)
                if result is not None:
                    self.cache.move_to_end(key)
                elif disk_result is not None:
                    result = disk_result
                    from_disk = True
                if result is None:
                    job = self.jobs.get(key)
                    if job is not None and job.stop.is_set():
                        raise PreviewBusyError('Thumbnail cancellation completing')
                    leader = job is None
                    if leader:
                        if len(self.jobs) >= MAX_JOBS:
                            raise PreviewBusyError('Thumbnail workers busy')
                        self.order += 1
                        job = _Job(order=self.order)
                        self.jobs[key] = job
                    job.waiters += 1
                    job.visible_waiters += priority == 'visible'
                    self.changed.notify_all()
        if result is not None:
            self._source_call(lambda: self._validate(item_id, kind, revision, result), cancelled)
            with self.lock:
                if self.closed or cancelled():
                    raise ThumbnailCancelled()
                if from_disk and key not in self.cache:
                    self._put_ram(key, result)
            return result[0]
        attached = True

        def detach():
            nonlocal attached
            with self.lock:
                if attached:
                    attached = False
                    job.waiters -= 1
                    job.visible_waiters -= priority == 'visible'
                    self.changed.notify_all()
                    if not job.waiters:
                        job.stop.set()
                        if job.ready.is_set() and self.jobs.get(key) is job:
                            del self.jobs[key]

        def stopped():
            # The leader may keep serving another request after its own client left.
            if cancelled():
                detach()
            return job.stop.is_set()

        try:
            if leader:
                acquired = False
                try:
                    self._acquire(job, stopped)
                    acquired = True
                    if stopped():
                        raise ThumbnailCancelled()
                    result = self._build(item_id, kind, revision, edge, stopped)
                    if stopped():
                        raise ThumbnailCancelled()
                    should_store = False
                    with self.lock:
                        if not self.closed and not job.stop.is_set():
                            self._put_ram(key, result)
                            job.result = result
                            should_store = True
                    if should_store:
                        with self.disk_lock:
                            if not self.closed and not job.stop.is_set():
                                self.disk.put(key, result)
                except Exception as error:
                    job.error = error
                finally:
                    if acquired:
                        self._release(job)
                    with self.lock:
                        job.ready.set()
                        if not job.waiters and self.jobs.get(key) is job:
                            del self.jobs[key]
            else:
                while not job.ready.wait(.05):
                    if cancelled() or job.stop.is_set():
                        raise ThumbnailCancelled()
            if cancelled() or job.stop.is_set():
                raise ThumbnailCancelled()
            if job.error is not None:
                raise job.error
            self._source_call(lambda: self._validate(item_id, kind, revision, job.result), cancelled)
            if cancelled() or job.stop.is_set():
                raise ThumbnailCancelled()
            return job.result[0]
        finally:
            detach()

    def _build(self, item_id, kind, revision, edge, stopped):
        if kind == 'video':
            png, _ = self._source_call(lambda: self.previews.video_thumbnail(item_id, min(edge, 512)), stopped)
            return png, None
        if kind == 'image':
            source, _ = self._source_call(lambda: self.previews.animation_source(item_id, revision), stopped)
            with source:
                png = self._decode(source, edge, stopped)
                self.previews.validate_animation(item_id, revision, source)
            return png, None
        data, _, tag = self._source_call(lambda: self.previews.page_source(item_id, 0, revision), stopped)
        with io.BytesIO(data) as source:
            png = self._decode(source, edge, stopped)
        self._source_call(lambda: self._validate(item_id, kind, revision, (png, tag)), stopped)
        return png, tag

    def _decode(self, source, edge, stopped):
        # Import lazily: missing optional codecs must not prevent library startup.
        from PIL import Image, ImageOps
        if stopped():
            raise ThumbnailCancelled()
        if native_accel.available() and getattr(Image.open, '__module__', '') == 'PIL.Image':
            raw = None
            try:
                source.seek(0, os.SEEK_END)
                raw_size = source.tell()
                source.seek(0)
                if 0 < raw_size <= MAX_STREAM_IMAGE_BYTES:
                    raw = source.read()
            except (OSError, ValueError, AttributeError):
                raw = None
            if raw and not detect_animation_header(raw[:32768]):
                dims = native_accel.probe_image(raw)
                if dims is not None:
                    w, h = dims
                    if w < 1 or h < 1 or w * h > MAX_IMAGE_PIXELS:
                        raise PreviewUnavailable('Thumbnail image too large')
                    estimate = w * h * 12 + edge * edge * 16
                    with self.decode_budget.reserve(estimate, stopped):
                        if stopped():
                            raise ThumbnailCancelled()
                        try:
                            png_bytes = native_accel.render_thumbnail(
                                raw, edge, MAX_IMAGE_PIXELS, MAX_RENDERED_PNG_BYTES
                            )
                        except native_accel.NativeImageTooLarge as error:
                            raise PreviewUnavailable(str(error)) from error
                        if png_bytes is not None:
                            return png_bytes
            try:
                source.seek(0)
            except (OSError, ValueError, AttributeError):
                pass
        try:
            with Image.open(source) as image:
                if image.width < 1 or image.height < 1 or image.width * image.height > MAX_IMAGE_PIXELS:
                    raise PreviewUnavailable('Thumbnail image too large')
                # Conservative estimate for original/orientation/RGBA copies and
                # derived resize/encode buffers. Oversize work is serialized.
                estimate = image.width * image.height * 12 + edge * edge * 16
                with self.decode_budget.reserve(estimate, stopped):
                    # APNG's default image is a poster, not the first animation frame.
                    # Never ask n_frames/is_animated: GIF would scan the whole file.
                    if image.format == 'PNG' and image.info.get('default_image'):
                        image.seek(1)
                    with ImageOps.exif_transpose(image) as oriented:
                        with oriented.convert('RGBA') as pixels:
                            if stopped():
                                raise ThumbnailCancelled()
                            pixels.thumbnail((edge, edge), Image.Resampling.LANCZOS)
                            with io.BytesIO() as output:
                                pixels.save(output, format='PNG')
                                if output.tell() > MAX_RENDERED_PNG_BYTES:
                                    raise PreviewUnavailable('Thumbnail output too large')
                                return output.getvalue()
        except (ThumbnailCancelled, PreviewUnavailable):
            raise
        except Exception as error:
            # Pillow's bomb/codec/EOF errors are unavailable media, not a bad
            # request or an unhandled handler failure. Other waiters see it too.
            raise PreviewUnavailable('Invalid or unsupported thumbnail image') from error
