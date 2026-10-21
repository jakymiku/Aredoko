"""Ordinary-startup validation after a stable full preflight.

Metadata is a damage/change detector, not a cryptographic proof for unchanged
bulk files. Full checks remain available and are never redefined by this cache.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat

import release_runtime as runtime
from startup_progress import StartupProgress
from storage_lease import plain_path, storage_parent, storage_lease

FORMAT = 'aredoko-startup-validation-v1'
LIMIT = 32 * 1024 * 1024
CONTRACT = 'windows-imports-media-v1'


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:raise ValueError('Duplicate validation key')
        value[key] = item
    return value


def _fingerprint(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError('Expected an ordinary validation file')
    if info.st_nlink != 1:raise ValueError('Hardlinked validation files are not supported')
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_mode, info.st_nlink,
            getattr(info, 'st_file_attributes', 0)]


def _snapshot(root, progress):
    # Reuse the complete lexical ancestor/reparse/type/hardlink guards. Never
    # trust directory timestamps to stand in for contained file metadata.
    result = {}
    for path in runtime._parallel_tree(root, progress=progress):
        progress.check_cancelled()
        name = path.relative_to(root).as_posix()
        # _parallel_tree already performed the full lexical ancestor guard for
        # this entry. Refresh leaf type/link/identity here without repeating all
        # ancestor syscalls. Content reads below still call _verify_file/guard.
        result[name] = _fingerprint(path)
    return result


def _critical(name):
    parts = name.split('/')
    return (parts[0] in {'bin', 'backend', 'tools'} or name == 'Aredoko.exe'
            or name.startswith('runtime/python/') and (
                len(parts) == 3 or parts[2] == 'DLLs'))


def _load(path):
    if not path.exists():return None
    path = plain_path(path)
    if path.stat().st_size > LIMIT:return None
    try:
        value = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_object)
    except (ValueError, UnicodeError):return None
    if not isinstance(value, dict) or set(value) != {'format', 'root', 'manifest', 'contract', 'files'}:
        return None
    if value['format'] != FORMAT or not isinstance(value['files'], dict):return None
    for name, fingerprint in value['files'].items():
        if not isinstance(name, str) or not isinstance(fingerprint, list) or len(fingerprint) != 8:
            return None
        if any(type(v) is not int for v in fingerprint):return None
    return value


def _save(path, value, progress):
    progress.check_cancelled()
    storage_parent(path)
    plain_path(path, missing=True)
    temporary = path.with_name(path.name + '.' + secrets.token_hex(8) + '.tmp')
    # The temporary is always a fresh file in the guarded cache directory.
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, separators=(',', ':'))
            stream.flush();os.fsync(stream.fileno())
        progress.check_cancelled()
        plain_path(temporary);plain_path(path, missing=True)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            plain_path(temporary);temporary.unlink()


def startup_preflight(root, cache_directory, full_check, *, progress=None,
                      force_full=False, contract=CONTRACT):
    """Return the unchanged manifest; only explicit Portable normal startup caches.

    full_check must perform the existing FULL SHA/layout/import/media preflight.
    No success receipt is written until the inventory is stable before/after it.
    A version/path/contract change, damaged receipt or changed file forces full
    verification. A known content mismatch is rejected, never learned as valid.
    """
    control = progress if progress is not None else StartupProgress()
    with control.phase('manifest'):
        root, manifest, entries, expected, total = runtime._manifest(root, control)
        manifest_hash = runtime.digest(plain_path(root / 'manifest.json'), progress=control)
    if manifest.get('frontend_activation') != 'portable':return full_check()
    normalized_root = os.path.normcase(str(root))
    identity = {'format': FORMAT, 'root': normalized_root,
                'manifest': manifest_hash, 'contract': contract}
    key = hashlib.sha256((normalized_root + '\n' + manifest_hash + '\n' + contract).encode()).hexdigest()
    cache = Path(os.path.abspath(cache_directory)) / (key + '.json')
    if cache.is_relative_to(root) or root.is_relative_to(cache.parent):
        raise ValueError('Startup validation must stay outside the release')
    storage_parent(cache)
    with storage_lease(cache):
        previous = None if force_full else _load(cache)
        with control.phase('inventory'):
            before = _snapshot(root, control)
            runtime._verify_inventory(root, manifest, entries, expected, total, control, actual=set(before))
        matched = previous is not None and all(previous[k] == v for k, v in identity.items()) and previous['files'] == before
        if matched:
            critical = [entry for entry in entries if _critical(entry['path'])]
            with control.phase('file_hashes', files=len(critical), bytes=sum(e['bytes'] for e in critical)):
                for entry in critical:
                    runtime._verify_file(root, entry, progress=control)
                    control.advance(files=1, bytes=entry['bytes'])
            return manifest
        result = full_check()
        with control.phase('inventory'):
            after = _snapshot(root, control)
            runtime._verify_inventory(root, manifest, entries, expected, total, control, actual=set(after))
        if (before != after or runtime.digest(plain_path(root / 'manifest.json'), progress=control) != manifest_hash
                or result != manifest):
            raise ValueError('Release changed during complete startup validation')
        _save(cache, {**identity, 'files': after}, control)
        return result
