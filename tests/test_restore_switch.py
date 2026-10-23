"""Unit tests for P5 Safe Restore Switch and Rollback mechanism.

Strict CPU-only tests using isolated temp directories. No GUI, no network,
and safe atomic pointers to restored databases.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))

from production import ProductionCatalog
import storage_backup
from restore_switch import (
    apply_restore_switch,
    commit_restore_switch,
    rollback_restore_switch,
    check_pending_restore,
    is_restore_pending,
    get_restore_pending_info,
    get_restore_history,
    RestoreSwitchError,
    PENDING_FILE,
    ROLLBACK_FILE,
    LAUNCH_SETTINGS_FILE,
    HISTORY_FILE,
)
from launch_release import run_session, load_settings, validate_settings, launch


class RestoreSwitchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='aredoko-switch-test-')
        self.base = Path(self.tmp.name)
        self.data_dir = self.base / 'user_data'
        self.data_dir.mkdir(mode=0o700)

        # Original user database
        self.orig_catalog = self.data_dir / 'catalog.sqlite'
        self._init_catalog(self.orig_catalog, item_title='元データアイテム')

        # Original launch-settings.json
        self.orig_settings = {
            'database': str(self.orig_catalog),
            'ui_theme': 'dark',
            'ai_ranking': 'mean-rrf',
        }
        (self.data_dir / LAUNCH_SETTINGS_FILE).write_text(
            json.dumps(self.orig_settings, indent=2), encoding='utf-8'
        )

        self.addCleanup(self.tmp.cleanup)

    def _init_catalog(self, path, item_title='テスト'):
        cat = ProductionCatalog(path)
        with cat.connect() as db:
            db.execute("INSERT INTO items(id, title, kind, tags) VALUES(1, ?, 'book', '[]')", (item_title,))
            db.commit()
        cat.close()

    def _create_staging(self, name='staging', restored_title='リストアデータアイテム', extra_settings=True):
        staging = self.base / name
        staging.mkdir(mode=0o700)
        self._init_catalog(staging / 'catalog.sqlite', item_title=restored_title)
        (staging / 'recovery.json').write_text(json.dumps({
            'format': 'aredoko-restored',
            'version': 1,
            'source_manifest_sha256': '0' * 64,
            'cache_policy': 'omitted',
        }), encoding='utf-8')

        if extra_settings:
            settings_dir = staging / 'settings'
            settings_dir.mkdir(mode=0o700)
            (settings_dir / 'ai-settings.json').write_text(json.dumps({
                'version': 1,
                'profile': 'default',
            }), encoding='utf-8')
            (settings_dir / 'viewer-settings.json').write_text(json.dumps({
                'version': 1,
                'page_mode': 'single',
            }), encoding='utf-8')

            profiles_dir = staging / 'profiles'
            profiles_dir.mkdir(mode=0o700)
            (profiles_dir / 'custom.json').write_text(json.dumps({
                'version': 1,
                'name': 'custom',
            }), encoding='utf-8')

        return staging

    def test_apply_restore_switch_creates_target_and_sentinel(self):
        staging = self._create_staging('staging_1')
        receipt = apply_restore_switch(self.data_dir, staging, restore_id='0123456789abcdef0123456789abcdef')

        self.assertEqual(receipt['restore_id'], '0123456789abcdef0123456789abcdef')
        self.assertEqual(receipt['status'], 'pending')
        target_dir = Path(receipt['target_restore_dir'])
        self.assertTrue(target_dir.is_dir())
        self.assertTrue((target_dir / 'catalog.sqlite').is_file())
        self.assertFalse(staging.exists())  # Staging was moved

        # Verify rollback backup exists
        rollback_file = self.data_dir / ROLLBACK_FILE
        self.assertTrue(rollback_file.is_file())
        saved_rollback = json.loads(rollback_file.read_text(encoding='utf-8'))
        self.assertEqual(saved_rollback, self.orig_settings)

        # Verify restore-pending sentinel
        pending_file = self.data_dir / PENDING_FILE
        self.assertTrue(pending_file.is_file())
        self.assertTrue(is_restore_pending(self.data_dir))
        pending_data = get_restore_pending_info(self.data_dir)
        self.assertIsNotNone(pending_data)
        self.assertEqual(pending_data['restore_id'], '0123456789abcdef0123456789abcdef')
        self.assertEqual(pending_data['target_restore_dir'], str(target_dir))
        self.assertFalse(pending_data['attempted'])
        self.assertTrue(pending_data['previous_settings_existed'])

        # Verify launch-settings updated to restored data
        updated_settings = json.loads((self.data_dir / LAUNCH_SETTINGS_FILE).read_text(encoding='utf-8'))
        self.assertEqual(updated_settings['database'], str(target_dir / 'catalog.sqlite'))
        self.assertEqual(updated_settings['ai_settings'], str(target_dir / 'settings' / 'ai-settings.json'))
        self.assertEqual(updated_settings['viewer_settings'], str(target_dir / 'settings' / 'viewer-settings.json'))
        self.assertEqual(updated_settings['ai_profiles_dir'], str(target_dir / 'profiles'))
        # Prior settings preserved
        self.assertEqual(updated_settings['ui_theme'], 'dark')
        self.assertEqual(updated_settings['ai_ranking'], 'mean-rrf')

    def test_normal_switch_and_commit_flow(self):
        """Test full happy path: switch -> check_pending (first attempt) -> commit on ready."""
        staging = self._create_staging('staging_commit')
        apply_restore_switch(self.data_dir, staging)
        self.assertTrue(is_restore_pending(self.data_dir))

        # First launch check: marks attempted=True, does not roll back
        rolled_back = check_pending_restore(self.data_dir)
        self.assertFalse(rolled_back)
        pending_info = get_restore_pending_info(self.data_dir)
        self.assertTrue(pending_info['attempted'])

        # Application reaches ready -> commit
        receipt = commit_restore_switch(self.data_dir)
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt['status'], 'committed')

        # Sentinel and rollback files are cleaned up
        self.assertFalse(is_restore_pending(self.data_dir))
        self.assertFalse((self.data_dir / PENDING_FILE).exists())
        self.assertFalse((self.data_dir / ROLLBACK_FILE).exists())

        # History records commit
        history = get_restore_history(self.data_dir)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['status'], 'committed')
        self.assertEqual(history[0]['restore_id'], receipt['restore_id'])
        self.assertIn('recovery_meta', history[0])

        # Launch settings permanently point to restored database
        current_settings = json.loads((self.data_dir / LAUNCH_SETTINGS_FILE).read_text(encoding='utf-8'))
        self.assertTrue(Path(current_settings['database']).is_file())
        self.assertIn('restores', current_settings['database'])

    def test_switch_and_rollback_on_startup_failure(self):
        """Test rollback when startup fails before reaching ready state."""
        staging = self._create_staging('staging_fail')
        apply_restore_switch(self.data_dir, staging)
        self.assertTrue(is_restore_pending(self.data_dir))

        # Simulate exception during startup
        simulated_error = "Frontend crash: initial screen timed out"
        receipt = rollback_restore_switch(self.data_dir, error=simulated_error)
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt['status'], 'rolled_back')
        self.assertEqual(receipt['error'], simulated_error)

        # Sentinel is cleared
        self.assertFalse(is_restore_pending(self.data_dir))
        self.assertFalse((self.data_dir / PENDING_FILE).exists())
        self.assertFalse((self.data_dir / ROLLBACK_FILE).exists())

        # Settings are rolled back to original user settings
        current_settings = json.loads((self.data_dir / LAUNCH_SETTINGS_FILE).read_text(encoding='utf-8'))
        self.assertEqual(current_settings, self.orig_settings)
        self.assertEqual(current_settings['database'], str(self.orig_catalog))

        # Original database is intact and contains original title
        cat = ProductionCatalog(self.orig_catalog)
        with cat.connect() as db:
            title = db.execute("SELECT title FROM items WHERE id=1").fetchone()[0]
            self.assertEqual(title, '元データアイテム')
        cat.close()

        # History records rollback
        history = get_restore_history(self.data_dir)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['status'], 'rolled_back')
        self.assertEqual(history[0]['error'], simulated_error)

    def test_crash_recovery_on_next_launch(self):
        """Test recovery when previous launch crashed unhandled (attempted=True leftover)."""
        staging = self._create_staging('staging_crash')
        apply_restore_switch(self.data_dir, staging)

        # First launch check: marks attempted=True
        rolled_back = check_pending_restore(self.data_dir)
        self.assertFalse(rolled_back)
        self.assertTrue(is_restore_pending(self.data_dir))

        # Simulate unhandled exit / sudden crash (process terminated before commit or rollback)
        # Sentinel remains on disk with attempted=True.

        # Next launch starts: check_pending_restore sees attempted=True -> rolls back
        rolled_back_2 = check_pending_restore(self.data_dir)
        self.assertTrue(rolled_back_2)

        # Sentinel is cleared
        self.assertFalse(is_restore_pending(self.data_dir))

        # launch-settings.json is rolled back to original
        current_settings = json.loads((self.data_dir / LAUNCH_SETTINGS_FILE).read_text(encoding='utf-8'))
        self.assertEqual(current_settings['database'], str(self.orig_catalog))
        self.assertEqual(current_settings, self.orig_settings)

        # Subsequent launch check is a clean no-op
        self.assertFalse(check_pending_restore(self.data_dir))

    def test_rollback_when_no_prior_launch_settings_existed(self):
        """If user had no launch-settings.json before restore, rollback deletes launch-settings.json."""
        # Remove existing launch-settings
        (self.data_dir / LAUNCH_SETTINGS_FILE).unlink()
        self.assertFalse((self.data_dir / LAUNCH_SETTINGS_FILE).exists())

        staging = self._create_staging('staging_no_prior')
        apply_restore_switch(self.data_dir, staging)
        self.assertTrue((self.data_dir / LAUNCH_SETTINGS_FILE).exists())

        # Rollback
        rollback_restore_switch(self.data_dir, error="Test failure")
        self.assertFalse((self.data_dir / LAUNCH_SETTINGS_FILE).exists())
        self.assertFalse(is_restore_pending(self.data_dir))

    def test_apply_restore_switch_validation_guards(self):
        # 1. Staging missing catalog.sqlite
        empty_staging = self.base / 'empty_staging'
        empty_staging.mkdir()
        with self.assertRaises(RestoreSwitchError):
            apply_restore_switch(self.data_dir, empty_staging)

        # 2. Invalid restore ID
        staging2 = self._create_staging('staging_invalid_id')
        with self.assertRaises(ValueError):
            apply_restore_switch(self.data_dir, staging2, restore_id='../invalid_path')
        with self.assertRaises(ValueError):
            apply_restore_switch(self.data_dir, staging2, restore_id='short')

        # 3. Live SQLite companion files in staging catalog
        staging3 = self._create_staging('staging_wal')
        (staging3 / 'catalog.sqlite-wal').touch()
        with self.assertRaises(RestoreSwitchError):
            apply_restore_switch(self.data_dir, staging3)

        # 4. Target already exists
        staging4 = self._create_staging('staging_exists')
        fixed_id = 'a' * 32
        target = self.data_dir / 'restores' / fixed_id
        target.mkdir(parents=True)
        with self.assertRaises(RestoreSwitchError):
            apply_restore_switch(self.data_dir, staging4, restore_id=fixed_id)

    def test_duplicate_pending_restore_rejected(self):
        staging1 = self._create_staging('staging_dup_1')
        staging2 = self._create_staging('staging_dup_2')
        apply_restore_switch(self.data_dir, staging1)

        with self.assertRaises(RestoreSwitchError):
            apply_restore_switch(self.data_dir, staging2)

    def test_corrupted_pending_sentinel_recovery(self):
        """Corrupted JSON in restore-pending.json triggers automatic rollback on check."""
        # Create corrupted sentinel
        (self.data_dir / PENDING_FILE).write_text("NOT VALID JSON", encoding='utf-8')
        (self.data_dir / ROLLBACK_FILE).write_text(json.dumps(self.orig_settings), encoding='utf-8')

        # Change launch settings to corrupt target
        (self.data_dir / LAUNCH_SETTINGS_FILE).write_text(json.dumps({'database': 'bad.sqlite'}), encoding='utf-8')

        # check_pending_restore handles corruption gracefully
        rolled_back = check_pending_restore(self.data_dir)
        self.assertTrue(rolled_back)
        self.assertFalse(is_restore_pending(self.data_dir))

        # Restored to original
        current_settings = json.loads((self.data_dir / LAUNCH_SETTINGS_FILE).read_text(encoding='utf-8'))
        self.assertEqual(current_settings, self.orig_settings)

    def test_run_session_commits_pending_restore_on_ready(self):
        """Verify run_session commits pending restore when on_ready is called."""
        staging = self._create_staging('staging_run_ready')
        apply_restore_switch(self.data_dir, staging)
        self.assertTrue(is_restore_pending(self.data_dir))

        logs_dir = self.data_dir / 'logs' / 'test-run-session'
        logs_dir.mkdir(parents=True)

        backend_proc = MagicMock()
        backend_proc.returncode = 0
        backend_proc.poll.return_value = None
        backend_proc.stdin = MagicMock()
        backend_proc.wait.return_value = 0

        app_proc = MagicMock()
        app_proc.returncode = 0
        app_proc.poll.return_value = 0
        app_proc.stdin = None
        app_proc.wait.return_value = 0

        ready_called = []
        def on_ready():
            ready_called.append(True)

        # Mock backend and session to test run_session logic safely
        with patch('launch_release._session') as mock_session, \
             patch('launch_release.subprocess.Popen', side_effect=[backend_proc, app_proc]):
            mock_session.return_value = {'mode': 'production', 'instance_id': 'test-inst'}

            run_session(
                backend_command=['python', '-c', 'pass'],
                app_command=['python', '-c', 'pass'],
                port=8769,
                instance='test-inst',
                logs=logs_dir,
                cwd=self.base,
                env={},
                require_ready=False,
                on_ready=on_ready,
                data=self.data_dir,
            )

        self.assertEqual(ready_called, [True])
        # Restore switch was committed
        self.assertFalse(is_restore_pending(self.data_dir))
        history = get_restore_history(self.data_dir)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['status'], 'committed')

    def test_run_session_rolls_back_on_failure_before_ready(self):
        """Verify run_session rolls back pending restore if backend fails before ready."""
        staging = self._create_staging('staging_run_fail')
        apply_restore_switch(self.data_dir, staging)
        self.assertTrue(is_restore_pending(self.data_dir))

        logs_dir = self.data_dir / 'logs' / 'test-run-fail'
        logs_dir.mkdir(parents=True)

        class ExitedBackend:
            def __init__(self):
                self.returncode = 1
                self.stdin = MagicMock()
            def poll(self):
                return 1

        with patch('launch_release.subprocess.Popen', return_value=ExitedBackend()):
            with self.assertRaises(RuntimeError):
                run_session(
                    backend_command=['python', '-c', 'exit(1)'],
                    app_command=['python', '-c', 'pass'],
                    port=8769,
                    instance='test-inst',
                    logs=logs_dir,
                    cwd=self.base,
                    env={},
                    data=self.data_dir,
                )

        # Restore switch was rolled back
        self.assertFalse(is_restore_pending(self.data_dir))
        current_settings = json.loads((self.data_dir / LAUNCH_SETTINGS_FILE).read_text(encoding='utf-8'))
        self.assertEqual(current_settings, self.orig_settings)
        history = get_restore_history(self.data_dir)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['status'], 'rolled_back')

    def test_launch_auto_rollback_on_pending_sentinel(self):
        """Verify launch() automatically detects unhandled crash and rolls back settings."""
        staging = self._create_staging('staging_launch_rollback')
        apply_restore_switch(self.data_dir, staging)
        # Mark attempted to simulate previous unhandled crash
        pending_info = get_restore_pending_info(self.data_dir)
        pending_info['attempted'] = True
        (self.data_dir / PENDING_FILE).write_text(json.dumps(pending_info), encoding='utf-8')

        dummy_root = self.base / 'release'
        dummy_root.mkdir()

        # Settings passed in pointing to restore
        staged_settings = load_settings(self.data_dir)
        self.assertIn('restores', staged_settings['database'])

        with patch('startup_validation.startup_preflight') as mock_preflight, \
             patch('launch_release.prepare_frontend') as mock_frontend, \
             patch('launch_release.run_session') as mock_session:
            mock_preflight.return_value = {'frontend_activation': 'installed'}
            mock_frontend.return_value = MagicMock()
            launch(dummy_root, self.data_dir, staged_settings)
            mock_session.assert_called_once()

        # Verify launch rolled back settings before running session
        self.assertFalse(is_restore_pending(self.data_dir))
        current_settings = json.loads((self.data_dir / LAUNCH_SETTINGS_FILE).read_text(encoding='utf-8'))
        self.assertEqual(current_settings, self.orig_settings)

    def test_non_object_pending_rolls_back_from_valid_copy(self):
        for raw in ('[]', 'null', '42', '"broken"'):
            with self.subTest(raw=raw):
                (self.data_dir / ROLLBACK_FILE).write_text(json.dumps(self.orig_settings), encoding='utf-8')
                (self.data_dir / PENDING_FILE).write_text(raw, encoding='utf-8')
                self.assertTrue(check_pending_restore(self.data_dir))
                self.assertEqual(load_settings(self.data_dir), self.orig_settings)

    def test_missing_recovery_information_preserves_evidence(self):
        pending = self.data_dir / PENDING_FILE
        pending.write_text('[]', encoding='utf-8')
        before = (self.data_dir / LAUNCH_SETTINGS_FILE).read_bytes()
        with self.assertRaises(RestoreSwitchError):
            check_pending_restore(self.data_dir)
        self.assertEqual(pending.read_text(encoding='utf-8'), '[]')
        self.assertEqual((self.data_dir / LAUNCH_SETTINGS_FILE).read_bytes(), before)

    def test_corrupt_rollback_does_not_replace_current_settings(self):
        pending = self.data_dir / PENDING_FILE
        pending.write_text('{"attempted": true}', encoding='utf-8')
        rollback = self.data_dir / ROLLBACK_FILE
        rollback.write_text('[]', encoding='utf-8')
        before = (self.data_dir / LAUNCH_SETTINGS_FILE).read_bytes()
        with self.assertRaises(RestoreSwitchError):
            check_pending_restore(self.data_dir)
        self.assertTrue(pending.exists())
        self.assertTrue(rollback.exists())
        self.assertEqual((self.data_dir / LAUNCH_SETTINGS_FILE).read_bytes(), before)

    def test_launch_exception_triggers_rollback(self):
        """Verify launch() exception handler triggers rollback if startup preflight fails."""
        staging = self._create_staging('staging_launch_exc')
        apply_restore_switch(self.data_dir, staging)
        self.assertTrue(is_restore_pending(self.data_dir))

        dummy_root = self.base / 'release_exc'
        dummy_root.mkdir()
        staged_settings = load_settings(self.data_dir)

        with patch('startup_validation.startup_preflight', side_effect=RuntimeError("Preflight validation failed")):
            with self.assertRaises(RuntimeError):
                launch(dummy_root, self.data_dir, staged_settings)

        # Verified rollback was executed by launch exception handler
        self.assertFalse(is_restore_pending(self.data_dir))
        current_settings = json.loads((self.data_dir / LAUNCH_SETTINGS_FILE).read_text(encoding='utf-8'))
        self.assertEqual(current_settings, self.orig_settings)
        history = get_restore_history(self.data_dir)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['status'], 'rolled_back')
        self.assertIn("Preflight validation failed", history[0]['error'])


if __name__ == '__main__':
    unittest.main()
