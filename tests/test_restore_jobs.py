"""Tests for RestoreJobManager: background restore staging jobs and security.

Strict CPU-only tests using isolated temp directories. No GUI, no network,
and no switching of production pointers.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import struct
import sys
import tempfile
import time
import threading
from unittest.mock import patch
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

from production import ProductionCatalog
import storage_backup
from storage_backup import backup, restore, create_backup, RecoveryError
from restore_jobs import RestoreJobManager, RestoreJob


class RestoreJobsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.catalog_path = self.base / 'catalog.sqlite'
        self.cat = ProductionCatalog(self.catalog_path)
        with self.cat.connect() as db:
            db.execute("INSERT INTO items(id, title, kind, tags) VALUES(1, 'テストアイテム', 'book', '[]')")
            db.commit()
        self.cat.close()
        self.manager = RestoreJobManager(staging_base_dir=self.base / 'staging')
        self.addCleanup(self.manager.close)
        self.addCleanup(self.tmp.cleanup)

    def _create_valid_zip(self, name='valid_backup.zip'):
        zip_path = self.base / name
        storage_backup.create_backup(self.catalog_path, zip_path)
        self.assertTrue(zip_path.is_file())
        return zip_path

    def test_successful_staging_from_valid_backup_bundle(self):
        zip_path = self._create_valid_zip()
        staging_dir = self.base / 'staging_target_1'

        job = self.manager.start_job(zip_path, staging_dir=staging_dir)
        self.assertIn(job.state, ('queued', 'running', 'completed'))
        self.assertEqual(job.staging_path, staging_dir)

        self.manager.wait(job.job_id, timeout=10.0)
        self.assertEqual(job.state, 'completed')
        self.assertEqual(job.progress_ratio, 1.0)
        self.assertIsNone(job.error)
        self.assertIsNotNone(job.manifest)

        # Staging directory exists and contains restored catalog
        self.assertTrue(staging_dir.is_dir())
        restored_cat = staging_dir / 'catalog.sqlite'
        self.assertTrue(restored_cat.is_file())
        self.assertTrue((staging_dir / 'recovery.json').is_file())

        # Verify data integrity in restored catalog
        cat = ProductionCatalog(restored_cat)
        try:
            with cat.connect() as db:
                title = db.execute("SELECT title FROM items WHERE id=1").fetchone()[0]
                self.assertEqual(title, 'テストアイテム')
        finally:
            cat.close()

    def test_job_state_tracking_and_access_parity(self):
        zip_path = self._create_valid_zip()
        staging_dir = self.base / 'staging_target_parity'

        job = self.manager.start_job(zip_path, staging_dir=staging_dir)
        self.manager.wait(job.job_id, timeout=10.0)

        # Attribute access
        self.assertEqual(job.state, 'completed')
        self.assertEqual(job.progress_ratio, 1.0)
        self.assertEqual(str(job), job.job_id)

        # Dict access
        self.assertEqual(job['state'], 'completed')
        self.assertEqual(job['progress_ratio'], 1.0)
        self.assertEqual(job['staging_path'], str(staging_dir))
        self.assertEqual(job['job_id'], job.job_id)
        self.assertIsNone(job['error'])
        self.assertIn('manifest', job)

        # Status snapshot via manager
        status = self.manager.status(job.job_id)
        self.assertEqual(status['state'], 'completed')
        self.assertEqual(status['job_id'], job.job_id)

        # List jobs
        jobs = self.manager.list_jobs()
        self.assertTrue(any(j['job_id'] == job.job_id for j in jobs))

    def test_rejection_of_corrupted_zip_file(self):
        corrupt_zip = self.base / 'corrupted.zip'
        corrupt_zip.write_bytes(b'PK\x03\x04' + b'totally corrupted data not a valid zip file')
        staging_dir = self.base / 'staging_corrupt'

        job = self.manager.start_job(corrupt_zip, staging_dir=staging_dir)
        self.manager.wait(job.job_id, timeout=10.0)

        self.assertEqual(job.state, 'failed')
        self.assertIsNotNone(job.error)
        self.assertFalse(staging_dir.exists())

    def test_rejection_of_missing_manifest_file(self):
        bad_zip = self.base / 'missing_manifest.zip'
        with zipfile.ZipFile(bad_zip, 'w') as zf:
            zf.writestr('catalog.sqlite', self.catalog_path.read_bytes())
        staging_dir = self.base / 'staging_no_manifest'

        job = self.manager.start_job(bad_zip, staging_dir=staging_dir)
        self.manager.wait(job.job_id, timeout=10.0)

        self.assertEqual(job.state, 'failed')
        self.assertIn('manifest.json', job.error)
        self.assertFalse(staging_dir.exists())

    def test_rejection_of_missing_catalog_file(self):
        bad_zip = self.base / 'missing_catalog.zip'
        with zipfile.ZipFile(bad_zip, 'w') as zf:
            zf.writestr('manifest.json', b'{"format":"aredoko-recovery","version":1}')
        staging_dir = self.base / 'staging_no_catalog'

        job = self.manager.start_job(bad_zip, staging_dir=staging_dir)
        self.manager.wait(job.job_id, timeout=10.0)

        self.assertEqual(job.state, 'failed')
        self.assertIn('catalog.sqlite', job.error)
        self.assertFalse(staging_dir.exists())

    def test_rejection_of_invalid_sha256_hash_signature(self):
        # Create valid backup first
        raw_backup_dir = self.base / 'raw_backup'
        storage_backup.backup(self.catalog_path, raw_backup_dir)

        # Tamper with catalog.sqlite so SHA256 in manifest no longer matches
        with (raw_backup_dir / 'catalog.sqlite').open('ab') as f:
            f.write(b'extra bytes to invalidate sha256 signature')

        tampered_zip = self.base / 'tampered.zip'
        with zipfile.ZipFile(tampered_zip, 'w') as zf:
            for root, _, files in os.walk(raw_backup_dir):
                for file in files:
                    p = Path(root) / file
                    zf.write(p, p.relative_to(raw_backup_dir).as_posix())

        staging_dir = self.base / 'staging_tampered'
        job = self.manager.start_job(tampered_zip, staging_dir=staging_dir)
        self.manager.wait(job.job_id, timeout=10.0)

        self.assertEqual(job.state, 'failed')
        self.assertIn('mismatch', job.error.lower())
        self.assertFalse(staging_dir.exists())

    def test_rejection_of_corrupted_sqlite_database(self):
        # Corrupt sqlite database and update manifest sha256 to pass hash check but fail DB integrity
        raw_backup_dir = self.base / 'corrupt_db_backup'
        storage_backup.backup(self.catalog_path, raw_backup_dir)

        cat_file = raw_backup_dir / 'catalog.sqlite'
        # Corrupt SQLite database bytes
        data = bytearray(cat_file.read_bytes())
        data[20:30] = b'\xff' * 10
        cat_file.write_bytes(data)

        # Update manifest to match new hash
        new_size, new_hash = storage_backup._hash(cat_file)
        manifest = json.loads((raw_backup_dir / 'manifest.json').read_text(encoding='utf-8'))
        for entry in manifest['entries']:
            if entry['role'] == 'catalog':
                entry['bytes'] = new_size
                entry['sha256'] = new_hash
        (raw_backup_dir / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')

        corrupt_db_zip = self.base / 'corrupt_db.zip'
        with zipfile.ZipFile(corrupt_db_zip, 'w') as zf:
            for root, _, files in os.walk(raw_backup_dir):
                for file in files:
                    p = Path(root) / file
                    zf.write(p, p.relative_to(raw_backup_dir).as_posix())

        staging_dir = self.base / 'staging_corrupt_db'
        job = self.manager.start_job(corrupt_db_zip, staging_dir=staging_dir)
        self.manager.wait(job.job_id, timeout=10.0)

        self.assertEqual(job.state, 'failed')
        self.assertFalse(staging_dir.exists())

    def test_rejection_of_zip_slip_directory_traversal(self):
        zip_path = self.base / 'zip_slip.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('manifest.json', b'{}')
            zf.writestr('catalog.sqlite', b'')
            zf.writestr('../evil.txt', b'escaped content')

        staging_dir = self.base / 'staging_zip_slip'
        job = self.manager.start_job(zip_path, staging_dir=staging_dir)
        self.manager.wait(job.job_id, timeout=10.0)

        self.assertEqual(job.state, 'failed')
        self.assertIn('traversal', job.error.lower())
        self.assertFalse(staging_dir.exists())
        self.assertFalse((self.base / 'evil.txt').exists())

    def test_rejection_of_symlink_entry(self):
        zip_path = self.base / 'symlink_entry.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('manifest.json', b'{}')
            zf.writestr('catalog.sqlite', b'')
            # Create a symlink entry in zip
            info = zipfile.ZipInfo('symlink.txt')
            info.create_system = 3  # Unix
            info.external_attr = 0o120777 << 16  # S_IFLNK
            zf.writestr(info, 'target_file.txt')

        staging_dir = self.base / 'staging_symlink'
        job = self.manager.start_job(zip_path, staging_dir=staging_dir)
        self.manager.wait(job.job_id, timeout=10.0)

        self.assertEqual(job.state, 'failed')
        self.assertIn('symlink', job.error.lower())
        self.assertFalse(staging_dir.exists())

    def test_rejection_of_sqlite_companion_files(self):
        zip_path = self.base / 'companion_files.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('manifest.json', b'{}')
            zf.writestr('catalog.sqlite', b'')
            zf.writestr('catalog.sqlite-wal', b'live wal file')

        staging_dir = self.base / 'staging_companion'
        job = self.manager.start_job(zip_path, staging_dir=staging_dir)
        self.manager.wait(job.job_id, timeout=10.0)

        self.assertEqual(job.state, 'failed')
        self.assertIn('companion', job.error.lower())
        self.assertFalse(staging_dir.exists())

    def test_cancellation_during_job_cleans_up_staging_directory(self):
        zip_path = self._create_valid_zip()
        staging_dir = self.base / 'staging_cancel'

        # Start job
        job = self.manager.start_job(zip_path, staging_dir=staging_dir)
        # Immediately cancel
        accepted = self.manager.cancel(job.job_id, wait=True)
        self.assertTrue(accepted)

        self.assertEqual(job.state, 'cancelled')
        self.assertFalse(staging_dir.exists())

    def test_bundle_size_limit_rejection(self):
        zip_path = self._create_valid_zip()
        staging_dir = self.base / 'staging_size_limit'

        # Use an unrealistically small limit
        job = self.manager.start_job(zip_path, staging_dir=staging_dir, max_bytes=100)
        self.manager.wait(job.job_id, timeout=10.0)

        self.assertEqual(job.state, 'failed')
        self.assertIn('limit', job.error.lower())
        self.assertFalse(staging_dir.exists())

    def test_staging_directory_already_exists_fails_safely(self):
        zip_path = self._create_valid_zip()
        staging_dir = self.base / 'pre_existing_staging'
        staging_dir.mkdir()
        canary = staging_dir / 'canary.txt'
        canary.write_text('must not be overwritten', encoding='utf-8')

        job = self.manager.start_job(zip_path, staging_dir=staging_dir)
        self.manager.wait(job.job_id, timeout=10.0)

        self.assertEqual(job.state, 'failed')
        self.assertTrue(staging_dir.exists())
        self.assertEqual(canary.read_text(encoding='utf-8'), 'must not be overwritten')

    def test_production_pointers_remain_untouched(self):
        original_mtime = self.catalog_path.stat().st_mtime_ns
        original_bytes = self.catalog_path.read_bytes()

        zip_path = self._create_valid_zip()
        staging_dir = self.base / 'staging_pointer_test'

        job = self.manager.start_job(zip_path, staging_dir=staging_dir)
        self.manager.wait(job.job_id, timeout=10.0)
        self.assertEqual(job.state, 'completed')

        # The production catalog is completely unmodified
        self.assertEqual(self.catalog_path.read_bytes(), original_bytes)
        self.assertEqual(self.catalog_path.stat().st_mtime_ns, original_mtime)

    def test_staging_with_default_staging_base_dir(self):
        zip_path = self._create_valid_zip()
        # Don't specify staging_dir, let manager create in staging_base_dir
        job = self.manager.start_job(zip_path)
        self.manager.wait(job.job_id, timeout=10.0)
        self.assertEqual(job.state, 'completed')
        self.assertTrue(job.staging_path.is_dir())
        self.assertTrue(job.staging_path.is_relative_to(self.base / 'staging'))

    def test_rejection_of_invalid_manifest_format(self):
        raw_backup_dir = self.base / 'invalid_format_backup'
        storage_backup.backup(self.catalog_path, raw_backup_dir)
        manifest = json.loads((raw_backup_dir / 'manifest.json').read_text(encoding='utf-8'))
        manifest['format'] = 'unsupported-format'
        (raw_backup_dir / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')

        invalid_zip = self.base / 'invalid_manifest.zip'
        with zipfile.ZipFile(invalid_zip, 'w') as zf:
            for root, _, files in os.walk(raw_backup_dir):
                for file in files:
                    p = Path(root) / file
                    zf.write(p, p.relative_to(raw_backup_dir).as_posix())

        staging_dir = self.base / 'staging_invalid_format'
        job = self.manager.start_job(invalid_zip, staging_dir=staging_dir)
        self.manager.wait(job.job_id, timeout=10.0)

        self.assertEqual(job.state, 'failed')
        self.assertFalse(staging_dir.exists())

    def test_rejection_of_nonexistent_zip_path(self):
        nonexistent = self.base / 'nonexistent.zip'
        job = self.manager.start_job(nonexistent)
        self.manager.wait(job.job_id, timeout=10.0)
        self.assertEqual(job.state, 'failed')
        self.assertTrue('not found' in job.error.lower() or 'does not exist' in job.error.lower())

    def test_rejection_of_absolute_path_in_zip(self):
        zip_path = self.base / 'abs_path.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('manifest.json', b'{}')
            zf.writestr('catalog.sqlite', b'')
            zf.writestr('/absolute/evil.txt', b'evil')

        staging_dir = self.base / 'staging_abs_path'
        job = self.manager.start_job(zip_path, staging_dir=staging_dir)
        self.manager.wait(job.job_id, timeout=10.0)

        self.assertEqual(job.state, 'failed')
        self.assertFalse(staging_dir.exists())

    def test_rejection_of_excessive_file_count_in_zip(self):
        zip_path = self.base / 'too_many_files.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('manifest.json', b'{}')
            zf.writestr('catalog.sqlite', b'')
            for i in range(150):
                zf.writestr(f'file_{i}.txt', b'content')

        staging_dir = self.base / 'staging_excess_files'
        job = self.manager.start_job(zip_path, staging_dir=staging_dir)
        self.manager.wait(job.job_id, timeout=10.0)

        self.assertEqual(job.state, 'failed')
        self.assertIn('too many files', job.error.lower())
        self.assertFalse(staging_dir.exists())

    def test_native_directory_bundle_restores_without_modifying_source(self):
        bundle = self.base / 'live_bundle'
        backup(self.catalog_path, bundle)
        before = {p.relative_to(bundle): p.read_bytes() for p in bundle.rglob('*') if p.is_file()}
        job = self.manager.start_job(bundle)
        self.manager.wait(job)
        self.assertEqual(job.state, 'completed', job.error)
        self.assertTrue((job.staging_path / 'catalog.sqlite').is_file())
        after = {p.relative_to(bundle): p.read_bytes() for p in bundle.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_invalid_directory_bundle_is_preserved(self):
        bundle = self.base / 'invalid_bundle'
        bundle.mkdir()
        canary = bundle / 'keep.txt'
        canary.write_text('keep', encoding='utf-8')
        job = self.manager.start_job(bundle)
        self.manager.wait(job)
        self.assertEqual(job.state, 'failed')
        self.assertEqual(canary.read_text(encoding='utf-8'), 'keep')

    def test_existing_extraction_directory_is_preserved(self):
        zip_path = self._create_valid_zip()
        job_id = 'b' * 32
        parent = self.base / 'staging'
        parent.mkdir()
        extract = parent / ('.extract-' + job_id)
        extract.mkdir()
        canary = extract / 'keep.txt'
        canary.write_text('original', encoding='utf-8')
        with patch('restore_jobs.secrets.token_hex', return_value=job_id):
            job = self.manager.start_job(zip_path)
            self.manager.wait(job)
        self.assertEqual(job.state, 'failed')
        self.assertEqual(canary.read_text(encoding='utf-8'), 'original')

    def test_cancel_does_not_remove_directory_while_worker_runs(self):
        zip_path = self._create_valid_zip()
        entered, release = threading.Event(), threading.Event()
        target = self.base / 'cancel_owned'
        real_restore = restore
        def blocked_restore(*args, **kwargs):
            result = real_restore(*args, **kwargs)
            entered.set()
            if not release.wait(5):
                raise RuntimeError('Test worker wait expired')
            return result
        with patch('restore_jobs.restore', side_effect=blocked_restore):
            job = self.manager.start_job(zip_path, staging_dir=target)
            try:
                self.assertTrue(entered.wait(5))
                self.assertTrue(self.manager.cancel(job, wait=False))
                self.assertEqual(job.state, 'running')
                self.assertTrue((target / 'catalog.sqlite').exists())
            finally:
                release.set()
                self.manager.wait(job)
        self.assertEqual(job.state, 'cancelled')
        self.assertFalse(target.exists())

    def test_rejects_oversized_archive_before_reading_payload(self):
        archive = self.base / 'compressed.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('manifest.json', b'{}')
            zf.writestr('catalog.sqlite', b'0' * 100000)
        with patch.object(zipfile.ZipFile, 'testzip', side_effect=AssertionError('Unbounded CRC pass')), patch.object(zipfile.ZipFile, 'open', side_effect=AssertionError('Premature decode')):
            job = self.manager.start_job(archive, max_bytes=10000)
            self.manager.wait(job)
        self.assertEqual(job.state, 'failed')
        self.assertIn('Decompressed archive size', job.error)

    def test_manager_close_cancels_active_jobs(self):
        zip_path = self._create_valid_zip()
        staging_dir = self.base / 'staging_manager_close'
        job = self.manager.start_job(zip_path, staging_dir=staging_dir)
        self.manager.close(timeout=10.0)
        self.assertIn(job.state, ('cancelled', 'completed'))


if __name__ == '__main__':
    unittest.main()
