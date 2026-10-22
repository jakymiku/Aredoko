"""Guarded, bounded derived PNGs. No paths or original media are written.

The request which creates a job does its work; other requests share its result.
Disconnecting that request only abandons work when no other waiter needs it.
"""
from collections import OrderedDict
from dataclasses import dataclass, field
import io
import threading

from previews import PreviewUnavailable, PreviewBusyError, ReaderChanged
from image_animations import MAX_IMAGE_PIXELS, MAX_RENDERED_PNG_BYTES
from thumbnail_disk import ThumbnailDisk

EDGES = (128, 256, 512, 1024)
METHOD = 'first-visible-exif-rgba-lanczos-v1'
CACHE_BYTES = 64 * 1024 * 1024
CACHE_ENTRIES = 256
MAX_JOBS = 32


class ThumbnailCancelled(Exception):
    pass


@dataclass
class _Job:
    ready: threading.Event = field(default_factory=threading.Event)
    stop: threading.Event = field(default_factory=threading.Event)
    waiters: int = 0
    result: tuple | None = None
    error: Exception | None = None


class ThumbnailCache:
    def __init__(self, previews, *, max_bytes=CACHE_BYTES, max_entries=CACHE_ENTRIES):
        self.previews = previews
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(2)
        self.cache = OrderedDict()
        self.bytes = 0
        self.jobs = {}
        self.closed = False
        self.disk = ThumbnailDisk()

    def close(self):
        with self.lock:
            self.closed = True
            self.cache.clear()
            self.bytes = 0
            self.disk.close()
            for job in self.jobs.values():
                job.stop.set()

    def _probe(self, item_id):
        kind = self.previews.catalog.get(item_id)['kind']
        if kind == 'image':
            info = self.previews.image_info(item_id)
        elif kind in ('book', 'archive'):
            info = self.previews.manifest(item_id)
        else:
            raise PreviewUnavailable('No derived thumbnail for this media')
        return kind, info['revision']

    def _validate(self, item_id, kind, revision, result):
        if self._probe(item_id) != (kind, revision):
            raise ReaderChanged('Thumbnail source changed')
        if kind != 'image':
            data, _, tag = self.previews.page_source(item_id, 0, revision, result[1])
            if data is not None or tag != result[1]:
                raise ReaderChanged('Thumbnail page changed')

    def _put(self, key, result):
        data = result[0]
        if self.closed:
            return
        self.disk.put(key, result)
        if len(data) > self.max_bytes:
            return
        previous = self.cache.pop(key, None)
        if previous is not None:
            self.bytes -= len(previous[0])
        self.cache[key] = result
        self.bytes += len(data)
        while self.bytes > self.max_bytes or len(self.cache) > self.max_entries:
            _, removed = self.cache.popitem(last=False)
            self.bytes -= len(removed[0])

    def read(self, item_id, edge=256, *, cancelled=lambda: False):
        if type(edge) is not int or edge not in EDGES:
            raise ValueError('Invalid thumbnail size')
        if cancelled():
            raise ThumbnailCancelled()
        kind, revision = self._probe(item_id)
        key = (METHOD, kind, item_id, revision, 0, edge)
        with self.lock:
            if self.closed:
                raise ThumbnailCancelled()
            result = self.cache.get(key)
            if result is not None:
                self.cache.move_to_end(key)
            else:
                result = self.disk.get(key)
            if result is None:
                job = self.jobs.get(key)
                if job is not None and job.stop.is_set():
                    raise PreviewBusyError('Thumbnail cancellation completing')
                leader = job is None
                if leader:
                    if len(self.jobs) >= MAX_JOBS:
                        raise PreviewBusyError('Thumbnail workers busy')
                    job = _Job()
                    self.jobs[key] = job
                job.waiters += 1
        if result is not None:
            self._validate(item_id, kind, revision, result)
            with self.lock:
                if self.closed or cancelled():
                    raise ThumbnailCancelled()
            return result[0]
        attached = True

        def detach():
            nonlocal attached
            with self.lock:
                if attached:
                    attached = False
                    job.waiters -= 1
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
                    while not acquired:
                        if stopped():
                            raise ThumbnailCancelled()
                        acquired = self.slots.acquire(timeout=.05)
                    if stopped():
                        raise ThumbnailCancelled()
                    result = self._build(item_id, kind, revision, edge, stopped)
                    if stopped():
                        raise ThumbnailCancelled()
                    with self.lock:
                        if not job.stop.is_set():
                            self._put(key, result)
                            job.result = result
                except Exception as error:
                    job.error = error
                finally:
                    if acquired:
                        self.slots.release()
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
            self._validate(item_id, kind, revision, job.result)
            if cancelled() or job.stop.is_set():
                raise ThumbnailCancelled()
            return job.result[0]
        finally:
            detach()

    def _build(self, item_id, kind, revision, edge, stopped):
        if kind == 'image':
            source, _ = self.previews.animation_source(item_id, revision)
            with source:
                png = self._decode(source, edge, stopped)
                self.previews.validate_animation(item_id, revision, source)
            return png, None
        data, _, tag = self.previews.page_source(item_id, 0, revision)
        with io.BytesIO(data) as source:
            png = self._decode(source, edge, stopped)
        self._validate(item_id, kind, revision, (png, tag))
        return png, tag

    @staticmethod
    def _decode(source, edge, stopped):
        # Import lazily: missing optional codecs must not prevent library startup.
        from PIL import Image, ImageOps
        if stopped():
            raise ThumbnailCancelled()
        with Image.open(source) as image:
            if image.width < 1 or image.height < 1 or image.width * image.height > MAX_IMAGE_PIXELS:
                raise PreviewUnavailable('Thumbnail image too large')
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
