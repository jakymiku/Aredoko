"""Background restore staging jobs. Staging and validation only; no production pointer switch."""
from copy import deepcopy
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
import tempfile
import threading
import time
import zipfile

from storage_backup import (
    restore,
    DEFAULT_MAX_BYTES,
    MAX_FILES,
    RecoveryError,
    CATALOG,
)
from storage_lease import plain_path, identity, StorageBusyError, StoragePathError, storage_parent

ID_PATTERN = re.compile(r'^[0-9a-f]{32}\Z')
ACTIVE_STATES = {'queued', 'running'}
TERMINAL_STATES = {'completed', 'failed', 'cancelled'}


class RestoreJob:
    """Represents a restore staging job with dual attribute and dict access."""

    def __init__(self, job_id, zip_path, staging_path, *, max_bytes=DEFAULT_MAX_BYTES, without_vectors=False):
        self.job_id = job_id
        self.zip_path = Path(os.path.abspath(zip_path)) if zip_path else None
        self.staging_path = Path(os.path.abspath(staging_path)) if staging_path else None
        self.max_bytes = max_bytes
        self.without_vectors = without_vectors
        self.state = 'queued'
        self.progress_ratio = 0.0
        self.message = 'リストアの準備を待機しています。'
        self.manifest = None
        self.error = None
        self.result = None
        self._created_staging = False
        self._staging_identity = None
        self._cancelled = threading.Event()
        self._thread = None
        self._lock = threading.RLock()

    def to_dict(self):
        with self._lock:
            return {
                'job_id': self.job_id,
                'state': self.state,
                'progress_ratio': self.progress_ratio,
                'message': self.message,
                'staging_path': str(self.staging_path) if self.staging_path else None,
                'manifest': deepcopy(self.manifest),
                'error': self.error,
            }

    def __getitem__(self, key):
        return self.to_dict()[key]

    def __setitem__(self, key, value):
        with self._lock:
            if hasattr(self, key):
                setattr(self, key, value)

    def get(self, key, default=None):
        return self.to_dict().get(key, default)

    def __contains__(self, key):
        return key in self.to_dict()

    def __str__(self):
        return self.job_id

    def __repr__(self):
        with self._lock:
            return f"<RestoreJob {self.job_id}: {self.state} ({int(self.progress_ratio * 100)}%)>"


class RestoreJobManager:
    """Manages isolated staging and validation of backup ZIP bundles before pointer switch."""

    def __init__(self, staging_base_dir=None, *, max_bytes=DEFAULT_MAX_BYTES):
        self.staging_base_dir = Path(os.path.abspath(staging_base_dir)) if staging_base_dir else None
        self.max_bytes = max_bytes
        self._jobs = {}
        self._lock = threading.RLock()
        self._closed = False

    @staticmethod
    def validate_id(job_id):
        if not isinstance(job_id, str) or ID_PATTERN.fullmatch(job_id) is None:
            raise ValueError('Invalid restore job ID')

    def start_job(self, zip_path, staging_dir=None, *, staging_path=None, without_vectors=False, max_bytes=None):
        if zip_path is None:
            raise ValueError('A backup ZIP bundle path is required')

        target_staging = staging_dir or staging_path
        with self._lock:
            if self._closed:
                raise RuntimeError('RestoreJobManager is closed')
            job_id = secrets.token_hex(16)
            if target_staging is None:
                if self.staging_base_dir is not None:
                    target_staging = self.staging_base_dir / f"restore_staging_{job_id}"
                else:
                    target_staging = Path(tempfile.gettempdir()) / f"aredoko-restore-staging-{job_id}"
            else:
                target_staging = Path(os.path.abspath(target_staging))

            effective_max = max_bytes if max_bytes is not None else self.max_bytes
            job = RestoreJob(
                job_id,
                zip_path,
                target_staging,
                max_bytes=effective_max,
                without_vectors=without_vectors,
            )
            self._jobs[job_id] = job
            thread = threading.Thread(
                target=self._run,
                args=(job,),
                name=f"aredoko-restore-{job_id}",
                daemon=True,
            )
            job._thread = thread
            thread.start()
            return job

    start = start_job

    def get_job(self, job_id):
        key = getattr(job_id, 'job_id', job_id)
        if not isinstance(key, str):
            key = str(key)
        self.validate_id(key)
        with self._lock:
            if key not in self._jobs:
                raise KeyError(f"Restore job {key} not found")
            return self._jobs[key]

    def status(self, job_id):
        return self.get_job(job_id).to_dict()

    get_status = status

    def list_jobs(self):
        with self._lock:
            return [job.to_dict() for job in self._jobs.values()]

    def cancel(self, job_id, *, timeout=10.0, wait=True):
        job = self.get_job(job_id)
        with job._lock:
            accepted = job.state in ACTIVE_STATES
            if accepted:
                job._cancelled.set()
                job.message = 'リストアを中止しています。'
        if wait and accepted and job._thread and job._thread.is_alive() and job._thread != threading.current_thread():
            job._thread.join(timeout=timeout)
        return accepted

    def wait(self, job_id, timeout=30.0):
        job = self.get_job(job_id)
        if job._thread and job._thread.is_alive() and job._thread != threading.current_thread():
            job._thread.join(timeout=timeout)
        return job

    def close(self, timeout=10.0):
        with self._lock:
            self._closed = True
            active = [job for job in self._jobs.values() if job.state in ACTIVE_STATES]
        for job in active:
            with job._lock:
                if job.state in ACTIVE_STATES:
                    job._cancelled.set()
        for job in active:
            if job._thread and job._thread.is_alive() and job._thread != threading.current_thread():
                job._thread.join(timeout=timeout)
        return not any(job._thread and job._thread.is_alive() for job in active)

    def _run(self, job):
        with job._lock:
            if job._cancelled.is_set():
                job.state = 'cancelled'
                job.message = 'リストアを中止しました。'
                return
            job.state = 'running'
            job.progress_ratio = 0.05
            job.message = 'アーカイブを検証しています。'

        staging_path = job.staging_path
        extract_dir = None
        extract_identity = None
        try:
            # 1. Ensure staging directory is new and does not exist
            if staging_path.exists():
                raise RecoveryError(f"Staging output directory already exists: {staging_path}")

            # 2. Path security on the source ZIP
            try:
                source_zip = plain_path(job.zip_path)
            except Exception as e:
                raise RecoveryError(f"Invalid backup archive path: {e}") from e

            if not source_zip.is_file():
                raise RecoveryError(f"Backup archive not found: {source_zip}")

            zip_size = source_zip.stat().st_size
            if zip_size > job.max_bytes:
                raise RecoveryError(f"Backup archive size ({zip_size} bytes) exceeds limit ({job.max_bytes} bytes)")

            if not zipfile.is_zipfile(source_zip):
                raise RecoveryError("File is not a valid ZIP archive")

            # 3. Inspect ZIP structure, test integrity and check for disallowed patterns
            with zipfile.ZipFile(source_zip, 'r') as zf:
                infolist = zf.infolist()
                if len(infolist) > MAX_FILES:
                    raise RecoveryError(f"Backup archive contains too many files ({len(infolist)} > {MAX_FILES})")

                filenames = set()
                names_seen = set()
                total_uncompressed = 0
                for info in infolist:
                    if job._cancelled.is_set():
                        raise InterruptedError('Restore cancelled')
                    name = info.filename
                    normalized = name.rstrip('/').casefold()
                    if normalized in names_seen or '\\' in name or ':' in name:
                        raise RecoveryError('Duplicate or ambiguous archive path')
                    names_seen.add(normalized)
                    total_uncompressed += info.file_size
                    if total_uncompressed > job.max_bytes:
                        raise RecoveryError("Decompressed archive size exceeds limit")

                    mode = (info.external_attr >> 16) & 0xFFFF
                    if stat.S_ISLNK(mode):
                        raise RecoveryError(f"Symlinks are forbidden in backup archive: {name}")

                    # Check unsafe paths, directory traversal, absolute paths
                    if not name or name.startswith('/') or name.startswith('\\') or re.match(r'^[a-zA-Z]:', name) or '\x00' in name:
                        raise RecoveryError(f"Unsafe path in backup archive: {name}")

                    parts = PurePosixPath(name).parts
                    if '..' in parts or '.' in parts:
                        raise RecoveryError(f"Directory traversal forbidden in archive: {name}")

                    if any(name.endswith(companion) for companion in ('-wal', '-shm', '-journal')):
                        raise RecoveryError(f"Live SQLite companion files forbidden in archive: {name}")

                    if not info.is_dir():
                        filenames.add(name)

                # Required files verification
                if 'manifest.json' not in filenames:
                    raise RecoveryError("Backup archive missing required manifest.json")
                if 'catalog.sqlite' not in filenames:
                    raise RecoveryError("Backup archive missing required catalog.sqlite")

            if job._cancelled.is_set():
                raise InterruptedError("Restore cancelled")

            # 4. Prepare intermediate extraction directory
            parent_dir = staging_path.parent
            storage_parent(staging_path)
            extract_dir = parent_dir / (f".extract-{job.job_id}")
            extract_dir.mkdir(mode=0o700)
            extract_identity = identity(extract_dir)

            with job._lock:
                job.progress_ratio = 0.15
                job.message = 'バックアップファイルを展開しています。'

            # 5. Safe file-by-file extraction
            with zipfile.ZipFile(source_zip, 'r') as zf:
                extracted_bytes = 0
                for info in infolist:
                    if job._cancelled.is_set():
                        raise InterruptedError("Restore cancelled")

                    dest_path = extract_dir / info.filename
                    # Canonical containment check (zip slip protection)
                    if not dest_path.resolve().is_relative_to(extract_dir.resolve()):
                        raise RecoveryError(f"Zip slip path traversal detected: {info.filename}")

                    if info.is_dir():
                        dest_path.mkdir(parents=True, exist_ok=True)
                        continue

                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    # Check parent path does not contain links/reparse points
                    plain_path(dest_path.parent, directory=True)

                    with zf.open(info) as src, dest_path.open('xb') as dst:
                        written = 0
                        while chunk := src.read(65536):
                            if job._cancelled.is_set():
                                raise InterruptedError("Restore cancelled")
                            written += len(chunk)
                            extracted_bytes += len(chunk)
                            if written > info.file_size or extracted_bytes > job.max_bytes:
                                raise RecoveryError("Extracted file exceeded declared size")
                            dst.write(chunk)
                        dst.flush()
                        os.fsync(dst.fileno())

                    # Verify extracted file is a plain regular file
                    plain_path(dest_path)

                    ratio = 0.15 + (0.35 * (extracted_bytes / max(1, total_uncompressed)))
                    with job._lock:
                        job.progress_ratio = min(0.50, ratio)

            if job._cancelled.is_set():
                raise InterruptedError("Restore cancelled")

            with job._lock:
                job.progress_ratio = 0.55
                job.message = 'データベースの検証と整合性確認を実行しています。'

            # 6. Execute storage_backup.restore() into staging_path
            report = restore(
                extract_dir,
                staging_path,
                without_vectors=job.without_vectors,
                max_bytes=job.max_bytes,
                cancelled=job._cancelled.is_set,
            )
            job._created_staging = staging_path.exists()
            job._staging_identity = identity(plain_path(staging_path, directory=True))

            if job._cancelled.is_set():
                raise InterruptedError("Restore cancelled")

            # 7. Load manifest data
            recovery_meta_path = staging_path / 'recovery.json'
            if recovery_meta_path.exists():
                manifest_data = json.loads(recovery_meta_path.read_text(encoding='utf-8'))
            else:
                manifest_path = staging_path / 'manifest.json'
                if manifest_path.exists():
                    manifest_data = json.loads(manifest_path.read_text(encoding='utf-8'))
                else:
                    manifest_data = report

            with job._lock:
                if job._cancelled.is_set():
                    raise InterruptedError('Restore cancelled')
                job.state = 'completed'
                job.progress_ratio = 1.0
                job.message = 'リストア準備が完了しました。'
                job.manifest = manifest_data
                job.result = report

        except InterruptedError:
            with job._lock:
                job.state = 'cancelled'
                job.message = 'リストアを中止しました。'
                job.error = None
            _remove_owned(staging_path, job._staging_identity)
        except Exception as error:
            with job._lock:
                if job._cancelled.is_set():
                    job.state = 'cancelled'
                    job.message = 'リストアを中止しました。'
                    job.error = None
                else:
                    job.state = 'failed'
                    job.message = 'リストアに失敗しました。'
                    job.error = str(error)
            _remove_owned(staging_path, job._staging_identity)
        finally:
            _remove_owned(extract_dir, extract_identity)


def _remove_owned(path, owned_identity):
    """Only the worker removes directories whose creation it observed."""
    if path is None or owned_identity is None:
        return
    try:
        checked = plain_path(path, directory=True)
        if identity(checked) == owned_identity:
            shutil.rmtree(checked)
    except (OSError, StoragePathError):
        # Preserve questionable leftovers instead of touching a replacement.
        pass
