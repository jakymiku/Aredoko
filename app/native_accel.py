"""Optional pure-Rust native accelerator (`aredoko_native.dll`) via ctypes.

Every entrypoint degrades cleanly to the existing pure-Python implementation
when the DLL is absent or `AREDOKO_DISABLE_NATIVE_ACCEL=1` is set.
"""
from array import array
import ctypes
from ctypes import (
    CFUNCTYPE,
    POINTER,
    c_char_p,
    c_double,
    c_int32,
    c_size_t,
    c_uint8,
    c_uint32,
    c_uint64,
    c_void_p,
)
from dataclasses import dataclass
import os
from pathlib import Path
import struct
import threading

from storage_lease import StoragePathError, plain_path

OK = 0
ERR_INVALID_ARG = -1
ERR_PATH_MISSING = -2
ERR_LINK_REJECTED = -3
ERR_HARDLINK_REJECTED = -4
ERR_NOT_PLAIN = -5
ERR_CHANGED = -6
ERR_CANCELLED = -7
ERR_OBSERVER = -8
ERR_TOO_LARGE = -9
ERR_OUTPUT_TOO_LARGE = -10
ERR_UNSUPPORTED = -11
ERR_IO = -12
ERR_PANIC = -99

KINDS = ('book', 'archive', 'image', 'video', 'audio', 'material')

_CANCEL_CB = CFUNCTYPE(c_int32, c_void_p)
_PROGRESS_CB = CFUNCTYPE(c_int32, c_void_p, c_uint64, c_uint64)

_LOAD_LOCK = threading.Lock()
_LOADED = False
_LIB = None
_LIB_PATH = None


class NativeCancelled(RuntimeError):
    pass


class NativeVerificationChanged(ValueError):
    def __init__(self, path: str = ''):
        super().__init__(path)
        self.path = path


class NativeImageTooLarge(ValueError):
    pass


class NativeDirectoryChanged(OSError):
    pass


@dataclass(frozen=True)
class NativeScanResult:
    ignored_files: int
    skipped_links: int
    items: list
    folder_pages: list


def _candidate_paths():
    here = Path(__file__).resolve()
    app_dir = here.parent
    repo_or_backend = app_dir.parent
    root_or_repo = repo_or_backend.parent
    candidates = [
        root_or_repo / 'bin' / 'aredoko_native.dll',
        repo_or_backend / 'bin' / 'aredoko_native.dll',
        repo_or_backend / 'src' / 'aredoko-native' / 'target' / 'x86_64-pc-windows-gnu' / 'release' / 'aredoko_native.dll',
        repo_or_backend / 'src' / 'aredoko-native' / 'target' / 'release' / 'aredoko_native.dll',
    ]
    return candidates


def _configure(lib):
    lib.aredoko_native_version.argtypes = []
    lib.aredoko_native_version.restype = c_uint32

    lib.aredoko_free_buffer.argtypes = [c_void_p, c_size_t]
    lib.aredoko_free_buffer.restype = None

    lib.aredoko_verify_manifest.argtypes = [
        c_char_p, c_size_t,
        c_char_p, c_size_t,
        c_uint32,
        c_void_p,
        _CANCEL_CB,
        _PROGRESS_CB,
        POINTER(c_void_p), POINTER(c_size_t),
    ]
    lib.aredoko_verify_manifest.restype = c_int32

    lib.aredoko_list_plain_files.argtypes = [
        c_char_p, c_size_t,
        c_uint8,
        c_void_p,
        _CANCEL_CB,
        POINTER(c_void_p), POINTER(c_size_t),
        POINTER(c_void_p), POINTER(c_size_t),
    ]
    lib.aredoko_list_plain_files.restype = c_int32

    lib.aredoko_image_probe.argtypes = [
        c_char_p, c_size_t,
        POINTER(c_uint32), POINTER(c_uint32),
    ]
    lib.aredoko_image_probe.restype = c_int32

    lib.aredoko_render_thumbnail.argtypes = [
        c_char_p, c_size_t,
        c_uint32, c_uint64, c_size_t,
        POINTER(c_void_p), POINTER(c_size_t),
    ]
    lib.aredoko_render_thumbnail.restype = c_int32

    lib.aredoko_score_f32_batch.argtypes = [
        POINTER(c_double), c_size_t,
        c_char_p, c_size_t, c_size_t,
        c_uint8,
        POINTER(c_double), POINTER(c_uint32), POINTER(c_uint8),
    ]
    lib.aredoko_score_f32_batch.restype = c_int32

    lib.aredoko_scan_tree.argtypes = [
        c_char_p, c_size_t,
        c_char_p, c_size_t,
        c_char_p, c_size_t,
        c_uint8, c_uint8,
        c_void_p,
        _CANCEL_CB,
        POINTER(c_void_p), POINTER(c_size_t),
        POINTER(c_void_p), POINTER(c_size_t),
    ]
    lib.aredoko_scan_tree.restype = c_int32


def _get_lib():
    if os.name != 'nt' or os.environ.get('AREDOKO_DISABLE_NATIVE_ACCEL') == '1':
        return None
    global _LOADED, _LIB, _LIB_PATH
    if _LOADED:
        return _LIB
    with _LOAD_LOCK:
        if _LOADED:
            return _LIB
        chosen = None
        for candidate in _candidate_paths():
            try:
                if candidate.exists():
                    checked = plain_path(candidate)
                    lib = ctypes.CDLL(str(checked))
                    _configure(lib)
                    if lib.aredoko_native_version() == 1:
                        chosen = lib
                        _LIB_PATH = checked
                        break
            except (OSError, ValueError, AttributeError):
                continue
        _LIB = chosen
        _LOADED = True
        return _LIB


def available() -> bool:
    return _get_lib() is not None


def loaded_path():
    _get_lib()
    return _LIB_PATH


def _take_buf(lib, ptr_box, len_box) -> bytes:
    ptr = ptr_box.value
    length = len_box.value
    if not ptr or length == 0:
        return b''
    try:
        return ctypes.string_at(ptr, length)
    finally:
        lib.aredoko_free_buffer(ptr, length)


def _raise_path_or_io(rc: int, err_text: str):
    if rc == ERR_PATH_MISSING:
        raise StoragePathError('Storage parent does not exist')
    if rc == ERR_LINK_REJECTED:
        raise StoragePathError('Linked storage paths are not supported')
    if rc == ERR_HARDLINK_REJECTED:
        raise StoragePathError('Hardlinked storage files are not supported')
    if rc == ERR_NOT_PLAIN:
        raise StoragePathError('Expected ordinary storage file or directory')
    if rc == ERR_CHANGED:
        raise NativeVerificationChanged(err_text)
    if rc == ERR_CANCELLED:
        raise NativeCancelled('Runtime validation cancelled')
    raise OSError(f'Native accelerator failed (code={rc}, detail={err_text})')


def verify_manifest(root, entries, *, workers=0, cancelled=lambda: False, progress=None):
    lib = _get_lib()
    if lib is None:
        raise RuntimeError('Native accelerator unavailable')
    root_b = os.fspath(root).encode('utf-8')

    parts = []
    append = parts.append
    pack_u64 = struct.Struct('<Q').pack
    pack_u32 = struct.Struct('<I').pack
    for entry in entries:
        rel_b = entry['path'].encode('utf-8')
        append(pack_u64(entry['bytes']))
        append(bytes.fromhex(entry['sha256']))
        append(pack_u32(len(rel_b)))
        append(rel_b)
    manifest_b = b''.join(parts)

    callback_exc = None

    def _on_cancel(_ctx):
        nonlocal callback_exc
        try:
            return 1 if cancelled() else 0
        except Exception as exc:
            callback_exc = exc
            return 1

    def _on_progress(_ctx, files_done, bytes_done):
        nonlocal callback_exc
        if progress is None:
            return 0
        try:
            progress(int(files_done), int(bytes_done))
            return 0
        except Exception as exc:
            callback_exc = exc
            return 1

    c_cancel = _CANCEL_CB(_on_cancel)
    c_progress = _PROGRESS_CB(_on_progress) if progress is not None else _PROGRESS_CB()

    err_ptr = c_void_p()
    err_len = c_size_t()
    rc = lib.aredoko_verify_manifest(
        root_b, len(root_b),
        manifest_b, len(manifest_b),
        workers,
        None,
        c_cancel,
        c_progress,
        ctypes.byref(err_ptr), ctypes.byref(err_len),
    )
    err_msg = _take_buf(lib, err_ptr, err_len).decode('utf-8', errors='replace')
    if callback_exc is not None:
        raise callback_exc
    if rc != OK:
        _raise_path_or_io(rc, err_msg)


def list_plain_files(root, *, include_cache=False, cancelled=lambda: False) -> list[str]:
    lib = _get_lib()
    if lib is None:
        raise RuntimeError('Native accelerator unavailable')
    root_b = os.fspath(root).encode('utf-8')
    callback_exc = None

    def _on_cancel(_ctx):
        nonlocal callback_exc
        try:
            return 1 if cancelled() else 0
        except Exception as exc:
            callback_exc = exc
            return 1

    c_cancel = _CANCEL_CB(_on_cancel)
    out_ptr = c_void_p()
    out_len = c_size_t()
    err_ptr = c_void_p()
    err_len = c_size_t()
    rc = lib.aredoko_list_plain_files(
        root_b, len(root_b),
        1 if include_cache else 0,
        None,
        c_cancel,
        ctypes.byref(out_ptr), ctypes.byref(out_len),
        ctypes.byref(err_ptr), ctypes.byref(err_len),
    )
    out_bytes = _take_buf(lib, out_ptr, out_len)
    err_msg = _take_buf(lib, err_ptr, err_len).decode('utf-8', errors='replace')
    if callback_exc is not None:
        raise callback_exc
    if rc != OK:
        _raise_path_or_io(rc, err_msg)

    result = []
    pos = 0
    view = memoryview(out_bytes)
    n = len(view)
    unpack_u32 = struct.Struct('<I').unpack_from
    while pos < n:
        (plen,) = unpack_u32(view, pos)
        pos += 4
        result.append(bytes(view[pos:pos + plen]).decode('utf-8'))
        pos += plen
    return result


def probe_image(data: bytes):
    lib = _get_lib()
    if lib is None or not data:
        return None
    w = c_uint32()
    h = c_uint32()
    rc = lib.aredoko_image_probe(data, len(data), ctypes.byref(w), ctypes.byref(h))
    if rc != OK:
        return None
    return int(w.value), int(h.value)


def render_thumbnail(data: bytes, edge: int, max_pixels: int, max_png_bytes: int):
    lib = _get_lib()
    if lib is None or not data:
        return None
    out_ptr = c_void_p()
    out_len = c_size_t()
    rc = lib.aredoko_render_thumbnail(
        data, len(data),
        edge, max_pixels, max_png_bytes,
        ctypes.byref(out_ptr), ctypes.byref(out_len),
    )
    out_bytes = _take_buf(lib, out_ptr, out_len)
    if rc == OK:
        return out_bytes
    if rc == ERR_TOO_LARGE:
        raise NativeImageTooLarge('Thumbnail image too large')
    if rc == ERR_OUTPUT_TOO_LARGE:
        raise NativeImageTooLarge('Thumbnail output too large')
    return None


def score_f32_batch(queries, blobs_bytes: bytes, n_vectors: int, dim: int, *, normalize_vec: bool = False):
    """Returns `(scores_array_f64, best_q_array_u32, valid_bytes)` for `n_vectors`."""
    lib = _get_lib()
    if lib is None:
        raise RuntimeError('Native accelerator unavailable')
    if n_vectors == 0:
        return array('d'), array('I'), b''
    n_queries = len(queries)
    flat_q = array('d')
    for q in queries:
        flat_q.extend(q)
    q_buf = (c_double * len(flat_q)).from_buffer(flat_q)
    out_scores = array('d', [0.0]) * n_vectors
    out_best_q = array('I', [0]) * n_vectors
    out_valid = bytearray(n_vectors)

    s_buf = (c_double * n_vectors).from_buffer(out_scores)
    bq_buf = (c_uint32 * n_vectors).from_buffer(out_best_q)
    v_buf = (c_uint8 * n_vectors).from_buffer(out_valid)

    rc = lib.aredoko_score_f32_batch(
        q_buf, n_queries,
        blobs_bytes, n_vectors, dim,
        1 if normalize_vec else 0,
        s_buf, bq_buf, v_buf,
    )
    if rc != OK:
        raise ValueError(f'Native vector scoring failed (code={rc})')
    return out_scores, out_best_q, out_valid


def scan_tree(root, db_path, patterns, *, recursive: bool, folder_books: bool, cancelled=None) -> NativeScanResult:
    lib = _get_lib()
    if lib is None:
        raise RuntimeError('Native accelerator unavailable')
    root_b = os.fspath(root).encode('utf-8')
    db_b = os.fspath(db_path).encode('utf-8') if db_path is not None else b''

    pack_u32 = struct.Struct('<I').pack
    pat_parts = []
    for p in patterns:
        pb = p.encode('utf-8')
        pat_parts.append(pack_u32(len(pb)))
        pat_parts.append(pb)
    patterns_b = b''.join(pat_parts)

    callback_exc = None

    def _on_cancel(_ctx):
        nonlocal callback_exc
        if cancelled is None:
            return 0
        try:
            return 1 if cancelled() else 0
        except Exception as exc:
            callback_exc = exc
            return 1

    c_cancel = _CANCEL_CB(_on_cancel)
    out_ptr = c_void_p()
    out_len = c_size_t()
    err_ptr = c_void_p()
    err_len = c_size_t()

    rc = lib.aredoko_scan_tree(
        root_b, len(root_b),
        db_b, len(db_b),
        patterns_b, len(patterns_b),
        1 if recursive else 0,
        1 if folder_books else 0,
        None,
        c_cancel,
        ctypes.byref(out_ptr), ctypes.byref(out_len),
        ctypes.byref(err_ptr), ctypes.byref(err_len),
    )
    out_bytes = _take_buf(lib, out_ptr, out_len)
    err_msg = _take_buf(lib, err_ptr, err_len).decode('utf-8', errors='replace')
    if callback_exc is not None:
        raise callback_exc
    if rc == ERR_CANCELLED:
        raise NativeCancelled('Scan cancelled')
    if rc in (ERR_CHANGED, ERR_LINK_REJECTED, ERR_NOT_PLAIN, ERR_PATH_MISSING):
        raise NativeDirectoryChanged(f'Directory changed during scan: {err_msg or root}')
    if rc != OK:
        raise OSError(f'Native scan failed (code={rc}, detail={err_msg})')

    view = memoryview(out_bytes)
    n = len(view)
    ignored_files, skipped_links = struct.unpack_from('<II', view, 0)
    pos = 8
    items = []
    folder_pages = []
    unpack_item = struct.Struct('<QqBI').unpack_from
    unpack_u32 = struct.Struct('<I').unpack_from
    unpack_page = struct.Struct('<QqI').unpack_from
    while pos < n:
        rtype = view[pos]
        pos += 1
        if rtype == 1:
            size, mtime_ns, kind_id, rlen = unpack_item(view, pos)
            pos += 21
            rel = bytes(view[pos:pos + rlen]).decode('utf-8')
            pos += rlen
            items.append((rel, KINDS[kind_id], size, mtime_ns))
        elif rtype == 2:
            (dlen,) = unpack_u32(view, pos)
            pos += 4
            dir_rel = bytes(view[pos:pos + dlen]).decode('utf-8')
            pos += dlen
            (page_count,) = unpack_u32(view, pos)
            pos += 4
            pages = []
            for _ in range(page_count):
                size, mtime_ns, nlen = unpack_page(view, pos)
                pos += 20
                name = bytes(view[pos:pos + nlen]).decode('utf-8')
                pos += nlen
                pages.append((name, size, mtime_ns))
            folder_pages.append((dir_rel, pages))
        else:
            raise ValueError(f'Invalid native scan record type: {rtype}')
    return NativeScanResult(
        ignored_files=ignored_files,
        skipped_links=skipped_links,
        items=items,
        folder_pages=folder_pages,
    )
