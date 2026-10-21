"""Offline release inventory validation. Integrity is not a publisher signature."""
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ('backend/app' if (ROOT / 'backend/app').is_dir() else 'app')))
from storage_lease import plain_path
from startup_progress import StartupProgress

MANIFEST_LIMIT = 32 * 1024 * 1024
REQUIRED_FILES = {'bin/Aredoko.WinUI.exe', 'bin/Aredoko.WinUI.dll', 'bin/Aredoko.Core.dll',
                  'bin/Aredoko.WinUI.deps.json', 'bin/Aredoko.WinUI.runtimeconfig.json',
                  'backend/app/production_server.py', 'backend/app/storage_schema_v1.json',
                  'tools/launch_release.py', 'tools/release_runtime.py', 'tools/probe_release_runtime.py'}


def digest(path, *, progress=None):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        while True:
            if progress is not None:progress.check_cancelled()
            block = stream.read(1024 * 1024)
            if not block:break
            result.update(block)
    return result.hexdigest()


def ordinary_tree(root):
    """Reject links before descending, including directory junctions on Windows."""
    root = plain_path(root, directory=True)
    for entry in sorted(root.iterdir()):
        plain_path(entry, directory=entry.is_dir())
        if entry.is_dir():
            yield from ordinary_tree(entry)
        else:
            yield entry


# Fixed I/O concurrency, independent of core count and library/model settings.
# Keep the sequential iterator above as a reference; do not cache path guards.
VERIFY_WORKERS = 4
VERIFY_BATCH = 64


def _checked_directory(root, *, progress=None):
    if progress is not None:progress.check_cancelled()
    root = plain_path(root, directory=True)
    directories, files = [], []
    for entry in sorted(root.iterdir()):
        if progress is not None:progress.check_cancelled()
        directory = entry.is_dir()
        plain_path(entry, directory=directory)
        (directories if directory else files).append(entry)
    return directories, files


def _parallel_tree(root, *, progress=None):
    """Same full lexical ancestor checks per edge/node, at most four tasks.

    Never descend into an entry before its full guard passes. Recheck a queued
    directory when its worker starts, including ancestors replaced meanwhile.
    Yield order is unspecified; inventory consumers compare sets, not ranks.
    """
    queued = deque([root])
    pending = set()
    with ThreadPoolExecutor(max_workers=VERIFY_WORKERS) as executor:
        while queued or pending:
            if progress is not None:progress.check_cancelled()
            while queued and len(pending) < VERIFY_WORKERS:
                path = queued.popleft()
                pending.add(executor.submit(_checked_directory, path) if progress is None else
                            executor.submit(_checked_directory, path, progress=progress))
            completed, pending = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
            for future in completed:
                directories, files = future.result()
                queued.extend(directories)
                yield from files


def _verify_file(root, item, *, progress=None):
    if progress is not None:progress.check_cancelled()
    path = plain_path(root / item['path'])
    if path.stat().st_size != item['bytes']:
        raise ValueError('Release file changed: ' + item['path'])
    checksum = digest(path) if progress is None else digest(path, progress=progress)
    if checksum != item['sha256']:
        raise ValueError('Release file changed: ' + item['path'])


def python_layout(root, include_ai=False, *, progress=None):
    if progress is not None:progress.check_cancelled()
    root = plain_path(root, directory=True)
    if (root / 'pyvenv.cfg').exists():
        raise ValueError('Supply a prepared standalone Python runtime, not a venv')
    for name in ('python.exe', 'pythonw.exe', 'LICENSE.txt', 'Lib/site-packages/PIL/__init__.py'):
        plain_path(root / name)
    versions = [p.stem for p in root.glob('python3*.dll') if re.fullmatch(r'python3(?:1[1-9]|[2-9][0-9])', p.stem)]
    if len(versions) != 1:
        raise ValueError('A single Python 3.11+ runtime DLL is required')
    stem = versions[0]
    plain_path(root / (stem + '.dll'))
    plain_path(root / (stem + '.zip'))
    if include_ai:
        for name in ('torch', 'transformers', 'sentence_transformers', 'numpy', 'onnxruntime'):
            plain_path(root / 'Lib/site-packages' / name / '__init__.py')
    # Walk explicitly supplied input only. Do not discover an installed runtime.
    for _ in _parallel_tree(root, progress=progress):pass
    return stem


def media_layout(root, *, progress=None):
    if progress is not None:progress.check_cancelled()
    root = plain_path(root, directory=True)
    for name in ('ffmpeg.exe', 'ffprobe.exe', 'LICENSE.txt'):
        plain_path(root / name)
    for _ in _parallel_tree(root, progress=progress):pass


def configure_embedded_python(root, stem):
    # Only the new staged copy is changed. _pth works for both python/pythonw.
    content = f'{stem}.zip\n.\nDLLs\nLib/site-packages\n../../backend/app\n../../tools\nimport site\n'
    for path in root.glob('*._pth'):
        plain_path(path)
        path.write_text(content, encoding='utf-8')
    (root / (stem + '._pth')).write_text(content, encoding='utf-8')


def _relative(value):
    if not isinstance(value, str) or not value or any(c in value for c in '\\:<>"|?*') or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid release path')
    parts = value.split('/')
    if any(p in ('', '.', '..') or p.endswith((' ', '.')) or p.split('.')[0].upper() in
           {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
           for p in parts) or PurePosixPath(value).is_absolute():
        raise ValueError('Invalid release path')
    return value


def _manifest(root, progress):
    progress.check_cancelled()
    root = plain_path(root, directory=True)
    marker = plain_path(root / 'manifest.json')
    if marker.stat().st_size > MANIFEST_LIMIT:
        raise ValueError('Release manifest exceeds limit')
    data = json.loads(marker.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('format') != 'aredoko-release-manifest' or data.get('platform') != 'windows-x64':
        raise ValueError('Unsupported release manifest')
    entries = data.get('entries')
    if not isinstance(entries, list) or not entries or len(entries) > 100_000:
        raise ValueError('Invalid release inventory')
    expected, names, total = set(), set(), 0
    for item in entries:
        progress.check_cancelled()
        if not isinstance(item, dict) or set(item) != {'path', 'bytes', 'sha256'}:
            raise ValueError('Invalid release entry')
        name = _relative(item['path'])
        if name.casefold() in names or name.casefold() in ('manifest.json', 'sha256sums.txt'):
            raise ValueError('Duplicate or reserved release path')
        names.add(name.casefold()); expected.add(name)
        if type(item['bytes']) is not int or item['bytes'] < 0 or not isinstance(item['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', item['sha256']):
            raise ValueError('Invalid release digest')
        total += item['bytes']
    return root, data, entries, expected, total


def verify_release(root, *, progress=None):
    """Read/hash only; truthful stage counts and cooperative cancellation.

    Completion here only verifies files, not frontend/backend readiness.
    Existing callers remain quiet and do not create progress/log files.
    """
    control = progress if progress is not None else StartupProgress()
    with control.phase('manifest'):
        root, data, entries, expected, total = _manifest(root, control)
    # Validate metadata serially first; hash EVERY listed file exactly once.
    # A batch bounds queued futures on Python 3.11 as well as newer interpreters.
    with control.phase('file_hashes', files=len(entries), bytes=total):
        with ThreadPoolExecutor(max_workers=VERIFY_WORKERS) as executor:
            for start in range(0, len(entries), VERIFY_BATCH):
                control.check_cancelled()
                batch = entries[start:start + VERIFY_BATCH]
                for item, _ in zip(batch, executor.map(lambda item: _verify_file(root, item, progress=progress), batch)):
                    control.advance(files=1, bytes=item['bytes'])
    with control.phase('inventory'):
        _verify_inventory(root, data, entries, expected, total, progress)
    return data


def _verify_inventory(root, data, entries, expected, total, progress):
    actual = {p.relative_to(root).as_posix() for p in _parallel_tree(root, progress=progress)}
    if not REQUIRED_FILES <= expected:
        raise ValueError('Release inventory is missing required application files')
    activation = data.get('frontend_activation', 'unconfigured')
    if activation not in ('unconfigured', 'msix'):
        raise ValueError('Unsupported frontend activation')
    if activation == 'msix' and not {'frontend/Aredoko.msix', 'tools/packaged_frontend.py'} <= expected:
        raise ValueError('Release inventory is missing packaged frontend files')
    if actual != expected | {'manifest.json', 'sha256sums.txt'}:
        raise ValueError('Unlisted or missing release files')
    if type(data.get('files_count')) is not int or data['files_count'] != len(entries) or type(data.get('total_bytes')) is not int or data['total_bytes'] != total:
        raise ValueError('Release inventory totals do not match')
    checksums = ''.join(f"{e['sha256']}  {e['path']}\n" for e in entries)
    if (root / 'sha256sums.txt').read_text(encoding='utf-8') != checksums:
        raise ValueError('Release checksum list does not match')


def runtime_environment(media=None):
    env = {k: v for k, v in os.environ.items() if k.upper() not in {'PYTHONHOME', 'PYTHONPATH', 'FFREPORT'}}
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTHONUTF8='1',
               HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
    if media is not None:
        env['AREDOKO_MEDIA_TOOLS'] = str(media)
    return env
