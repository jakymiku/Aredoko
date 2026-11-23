"""Bounded read-only animation and large-image inspection/rendering.

Only already-validated open file handles are read; no filesystem paths are opened
or written, and source files are never modified.
"""
from collections import OrderedDict
import io
import struct
import threading

MAX_LARGE_IMAGE_BYTES = 64 * 1024 * 1024
# Handle-based probes/decoders retain separate compressed-file and pixel budgets.
MAX_STREAM_IMAGE_BYTES = 256 * 1024 * 1024
MAX_ANIMATION_FRAMES = 64
MAX_IMAGE_PIXELS = 16_000_000
MAX_RENDERED_PNG_BYTES = 8 * 1024 * 1024
VIEWER_MAX_EDGE = 2048
THUMBNAIL_MAX_EDGE = 256
REPRESENTATIVE_MAX_EDGE = 768
CACHE_ENTRIES = 16


class AnimationUnavailable(ValueError):
    pass


def image_mime(header: bytes) -> str:
    """Identify supported image containers from bytes, never their filename.

    This is routing, not proof that the complete image can be decoded.
    """
    if header.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    if header.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if len(header) >= 12 and header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return 'image/webp'
    if header.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if header.startswith(b'BM'):
        return 'image/bmp'
    raise AnimationUnavailable('Unrecognized image container')


def detect_animation_header(header: bytes) -> bool:
    """Fast header check for GIF, animated WebP, or APNG."""
    if not isinstance(header, (bytes, bytearray)) or len(header) < 16:
        return False
    if header.startswith((b'GIF87a', b'GIF89a')):
        return True
    if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        if header[12:16] == b'VP8X' and len(header) >= 21 and (header[20] & 0x02):
            return True
        return b'ANIM' in header[:128] or b'ANMF' in header[:128]
    if header.startswith(b'\x89PNG\r\n\x1a\n'):
        offset = 8
        limit = min(len(header), 32768)
        while offset + 8 <= limit:
            length, kind = struct.unpack_from('>I4s', header, offset)
            if kind == b'acTL':
                return True
            if kind in (b'IDAT', b'IEND'):
                return False
            if length > limit or offset + 12 + length > limit:
                break
            offset += 12 + length
    return False


def representative_frame_index(frame_count: int) -> int:
    """Deterministic representative frame for AI indexing/tagging of animations."""
    if type(frame_count) is not int or frame_count < 1:
        raise ValueError('Invalid frame count')
    if frame_count == 1:
        return 0
    return min(frame_count - 1, frame_count // 2)


def _clamp_duration(value) -> int:
    try:
        ms = int(round(float(value)))
    except (TypeError, ValueError):
        ms = 100
    return max(20, min(60_000, ms if ms > 0 else 100))


def _clamp_loop(value) -> int:
    try:
        loop = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(10_000, loop))


class AnimationInspector:
    def __init__(self):
        self._manifest_cache = OrderedDict()
        self._frame_cache = OrderedDict()
        self._lock = threading.Lock()

    def inspect(self, file_obj, size_bytes: int, revision: str, item_id: int, mime: str) -> dict:
        if type(size_bytes) is not int or not 1 <= size_bytes <= MAX_LARGE_IMAGE_BYTES:
            raise AnimationUnavailable('Image exceeds size limit')
        with self._lock:
            cached = self._manifest_cache.get(revision)
            if cached is not None:
                self._manifest_cache.move_to_end(revision)
                return {**cached, 'item_id': item_id}
        file_obj.seek(0)
        header = file_obj.read(4096)
        maybe_anim = detect_animation_header(header)
        file_obj.seek(0)
        try:
            from PIL import Image, ImageOps
            Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
            with Image.open(file_obj) as img:
                width, height = img.size
                if not (1 <= width <= 16384 and 1 <= height <= 16384 and width * height <= MAX_IMAGE_PIXELS):
                    raise AnimationUnavailable('Image dimensions exceed limit')
                raw_frames = int(getattr(img, 'n_frames', 1) or 1)
                is_anim = bool(getattr(img, 'is_animated', False) and raw_frames > 1)
                if not is_anim and maybe_anim and raw_frames > 1:
                    is_anim = True
                first_frame = 1 if is_anim and img.info.get('default_image', False) else 0
                frame_count = min(MAX_ANIMATION_FRAMES, max(1, raw_frames - first_frame)) if is_anim else 1
                durations = []
                loop = _clamp_loop(img.info.get('loop', 0)) if is_anim else 0
                if is_anim:
                    for idx in range(frame_count):
                        img.seek(idx + first_frame)
                        durations.append(_clamp_duration(img.info.get('duration', 100)))
                else:
                    durations = [100]
                    orient_w, orient_h = ImageOps.exif_transpose(img).size
                    width, height = orient_w, orient_h
        except AnimationUnavailable:
            raise
        except Exception as error:
            raise AnimationUnavailable('Invalid or unsupported image') from error
        result = {
            'item_id': item_id,
            'revision': revision,
            'mime': image_mime(header),
            'size_bytes': size_bytes,
            'width': width,
            'height': height,
            'animated': is_anim and frame_count > 1,
            'frame_count': frame_count,
            'loop_count': loop,
            'durations_ms': durations,
            'representative_frame': representative_frame_index(frame_count),
        }
        with self._lock:
            self._manifest_cache[revision] = dict(result)
            self._manifest_cache.move_to_end(revision)
            while len(self._manifest_cache) > CACHE_ENTRIES * 2:
                self._manifest_cache.popitem(last=False)
        return result

    def render_frame(self, file_obj, size_bytes: int, revision: str, frame_index: int = 0, max_edge: int = VIEWER_MAX_EDGE) -> bytes:
        if type(size_bytes) is not int or not 1 <= size_bytes <= MAX_LARGE_IMAGE_BYTES:
            raise AnimationUnavailable('Image exceeds size limit')
        if type(frame_index) is not int or not 0 <= frame_index < MAX_ANIMATION_FRAMES:
            raise ValueError('Invalid frame index')
        if type(max_edge) is not int or not 1 <= max_edge <= VIEWER_MAX_EDGE:
            raise ValueError('Invalid max edge')
        cache_key = (revision, frame_index, max_edge)
        with self._lock:
            cached = self._frame_cache.get(cache_key)
            if cached is not None:
                self._frame_cache.move_to_end(cache_key)
                return cached
        file_obj.seek(0)
        try:
            from PIL import Image, ImageOps
            Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
            with Image.open(file_obj) as img:
                width, height = img.size
                if not (1 <= width <= 16384 and 1 <= height <= 16384 and width * height <= MAX_IMAGE_PIXELS):
                    raise AnimationUnavailable('Image dimensions exceed limit')
                raw_frames = int(getattr(img, 'n_frames', 1) or 1)
                is_anim = bool(getattr(img, 'is_animated', False) and raw_frames > 1)
                first_frame = 1 if is_anim and img.info.get('default_image', False) else 0
                limit = min(MAX_ANIMATION_FRAMES, max(1, raw_frames - first_frame)) if is_anim else 1
                if frame_index >= limit:
                    raise AnimationUnavailable('Frame index out of range')
                if is_anim:
                    img.seek(frame_index + first_frame)
                    frame = img.convert('RGBA')
                else:
                    frame = ImageOps.exif_transpose(img).convert('RGBA')
                scale = min(1.0, float(max_edge) / max(frame.width, frame.height))
                if scale < 1.0:
                    target_w = max(1, int(round(frame.width * scale)))
                    target_h = max(1, int(round(frame.height * scale)))
                    frame = frame.resize((target_w, target_h), Image.Resampling.LANCZOS)
                out = io.BytesIO()
                frame.save(out, format='PNG', optimize=False)
                png_bytes = out.getvalue()
        except AnimationUnavailable:
            raise
        except Exception as error:
            raise AnimationUnavailable('Unable to decode image frame') from error
        if not 1 <= len(png_bytes) <= MAX_RENDERED_PNG_BYTES:
            raise AnimationUnavailable('Rendered frame exceeds size limit')
        with self._lock:
            self._frame_cache[cache_key] = png_bytes
            self._frame_cache.move_to_end(cache_key)
            while len(self._frame_cache) > CACHE_ENTRIES:
                self._frame_cache.popitem(last=False)
        return png_bytes
