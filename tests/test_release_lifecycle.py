"""Real generated-catalog HTTP/child-process tests, without Windows or AI models."""
import json
from contextlib import closing
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'app'))
from launch_release import run_session, _session, load_settings, validate_settings
from release_runtime import runtime_environment
from storage_lease import storage_lease


class ReleaseLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aredoko-lifecycle-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.logs = self.base / 'logs';self.logs.mkdir()
        self.db = self.base / 'catalog.sqlite'
        self.instance = 'a' * 32
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0));self.port = probe.getsockname()[1]
        self.env = runtime_environment()
        self.env['LOCALAPPDATA'] = str(self.base / 'user data')

    def backend(self, instance=None):
        return [sys.executable, '-B', str(ROOT / 'app/production_server.py'), '--db', str(self.db),
                '--port', str(self.port), '--instance-id', instance or self.instance, '--exit-on-stdin-close',
                '--models-root', str(self.base / 'absent models'), '--ai-python', str(self.base / 'absent runtime')]

    def session(self, app=None, backend=None, **kwargs):
        run_session(backend or self.backend(), app or [sys.executable, '-c', 'pass'], port=self.port,
                    instance=self.instance, logs=self.logs, cwd=self.base, env=self.env, **kwargs)

    def assert_released(self):
        with storage_lease(self.db):pass
        with socket.socket() as probe:
            self.assertNotEqual(probe.connect_ex(('127.0.0.1', self.port)), 0)

    def test_normal_frontend_exit_closes_database_and_backend(self):
        self.session()
        self.assert_released()
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        wal = Path(str(self.db) + '-wal')
        self.assertTrue(not wal.exists() or wal.stat().st_size == 0)

    def test_existing_port_is_not_attached_to_or_stopped(self):
        with socket.socket() as other:
            other.bind(('127.0.0.1', self.port));other.listen()
            with patch('launch_release.subprocess.Popen') as child, self.assertRaisesRegex(RuntimeError, 'already in use'):
                self.session()
            child.assert_not_called();self.assertEqual(other.getsockname()[1], self.port)
        self.assertFalse(self.db.exists())

    def test_mismatched_session_does_not_start_frontend_and_releases_owned_backend(self):
        marker = self.base / 'app-started'
        app = [sys.executable, '-c', 'from pathlib import Path; import sys; Path(sys.argv[1]).touch()', str(marker)]
        with self.assertRaisesRegex(RuntimeError, 'does not belong'):
            self.session(app, self.backend('b' * 32))
        self.assertFalse(marker.exists());self.assert_released()

    def test_failed_frontend_activation_still_closes_backend(self):
        with self.assertRaisesRegex(RuntimeError, 'activation failed'):
            self.session([sys.executable, '-c', 'raise SystemExit(7)'])
        self.assert_released()

    def test_missing_frontend_executable_still_closes_backend(self):
        with self.assertRaises(OSError):self.session([str(self.base / 'missing.exe')])
        self.assert_released()

    def test_backend_early_exit_is_reported_without_frontend(self):
        with self.assertRaisesRegex(RuntimeError, 'exited during startup'):
            self.session(backend=[sys.executable, '-c', 'raise SystemExit(9)'])
        self.assertFalse(self.db.exists())

    def test_backend_timeout_closes_owner_pipe(self):
        marker = self.base / 'stdin-closed'
        backend = [sys.executable, '-c', 'import sys; from pathlib import Path; sys.stdin.buffer.read(); Path(sys.argv[1]).touch()', str(marker)]
        with self.assertRaisesRegex(RuntimeError, 'timed out'):self.session(backend=backend, startup_timeout=0.3)
        self.assertTrue(marker.exists())

    def test_owner_pipe_eof_exits_real_server_and_releases_lease(self):
        process = subprocess.Popen(self.backend(), stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, env=self.env, cwd=self.base)
        try:
            deadline = time.monotonic() + 10
            while True:
                try:
                    if _session(self.port).get('instance_id') == self.instance:break
                except OSError:pass
                if time.monotonic() > deadline:self.fail('backend did not start')
                time.sleep(0.05)
            process.stdin.close()
            self.assertEqual(process.wait(timeout=5), 0)
        finally:
            if process.poll() is None:process.kill();process.wait()
            if process.stdin and not process.stdin.closed:process.stdin.close()
        self.assert_released()

    def test_startup_failure_releases_catalog_lease(self):
        with socket.socket() as other:
            other.bind(('127.0.0.1', self.port));other.listen()
            process = subprocess.run(self.backend(), input=b'', stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     env=self.env, cwd=self.base, timeout=10)
            self.assertNotEqual(process.returncode, 0)
        with storage_lease(self.db):pass

    def test_launch_settings_are_explicit_bounded_and_preserved(self):
        self.assertEqual(load_settings(self.base), {})
        settings = {'models_root': str(self.base / '日本語 models'), 'ai_python': str(self.base / 'Python with spaces/python.exe'), 'ui_theme': 'dark'}
        path = self.base / 'launch-settings.json';path.write_text(json.dumps(settings))
        before = path.read_bytes(), path.stat().st_mtime_ns
        self.assertEqual(load_settings(self.base), settings)
        self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))
        for invalid in ({'shell': 'run'}, {'database': 'relative.sqlite'}, {'ai_ranking': 'unknown'}, {'database': None}):
            with self.subTest(settings=invalid), self.assertRaises(ValueError):validate_settings(invalid)


if __name__ == '__main__':unittest.main()
