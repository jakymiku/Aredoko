"""Generated persistent-cache corruption must remain a cache miss."""
from contextlib import closing
import sqlite3
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from thumbnail_disk import ThumbnailDisk


class PersistentRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'thumbs.sqlite'
        self.key = ('method', 'image', 1, 'revision', 0, 128)
        self.png = b'\x89PNG\r\n\x1a\n' + b'generated-payload'
        first = ThumbnailDisk(path=self.path)
        first.put(self.key, (self.png, None))
        first.close()

    def reopen(self):
        disk = ThumbnailDisk(path=self.path)
        self.addCleanup(disk.close)
        return disk

    def change(self, sql, values=()):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(sql, values)
            db.commit()

    def test_invalid_lru_value_does_not_escape_or_disable_new_writes(self):
        for value in ('corrupt-order', b'bad-order', -1, 0.5):
            with self.subTest(value=value):
                self.change('UPDATE thumbs SET touched=?', (value,))
                disk = self.reopen()
                self.assertIsNone(disk.get(self.key))
                disk.put(self.key, (self.png, None))
                self.assertEqual(disk.get(self.key), (self.png, None))
                self.assertFalse(disk.disabled)
                disk.close()

    def test_maximum_sqlite_tick_is_rebased_without_losing_valid_entries(self):
        self.change('UPDATE thumbs SET touched=?', (2**63 - 1,))
        disk = self.reopen()
        self.assertEqual(disk.get(self.key), (self.png, None))
        self.assertLess(disk.tick, 100)
        disk.close()
        self.assertEqual(self.reopen().get(self.key), (self.png, None))

    def test_same_column_names_with_wrong_constraints_are_recreated(self):
        self.change('DROP TABLE thumbs')
        self.change('CREATE TABLE thumbs(key TEXT, png BLOB, digest TEXT, tag TEXT, touched INTEGER)')
        disk = self.reopen()
        disk.put(self.key, (self.png, None))
        disk.put(self.key, (self.png, None))
        self.assertEqual(disk.get(self.key), (self.png, None))
        self.assertEqual(disk.db.execute('SELECT COUNT(*) FROM thumbs').fetchone()[0], 1)
        columns = disk.db.execute('PRAGMA table_info(thumbs)').fetchall()
        self.assertEqual(columns[0][5], 1)
        self.assertEqual(columns[1][3], 1)

    def test_open_failure_releases_connection_and_lease(self):
        # Fail after connecting but before publishing the initialized handle.
        original = sqlite3.connect
        connections = []
        class FaultyConnection:
            closed = False
            def __init__(self, *args, **kwargs):
                self.inner = original(*args, **kwargs)
                connections.append(self)
            def execute(self, sql, *args):
                if sql == 'PRAGMA journal_mode=DELETE':
                    raise sqlite3.OperationalError('generated initialization failure')
                return self.inner.execute(sql, *args)
            def __getattr__(self, name):
                return getattr(self.inner, name)
            def close(self):
                self.closed = True
                self.inner.close()
        disk = ThumbnailDisk(path=self.path)
        self.addCleanup(disk.close)
        with patch('thumbnail_disk.sqlite3.connect', side_effect=FaultyConnection):
            self.assertIsNone(disk.get(self.key))
        self.assertTrue(disk.disabled)
        try:
            self.assertTrue(connections[0].closed)
        finally:
            for connection in connections:
                connection.close()
        with closing(sqlite3.connect(self.path, timeout=0)) as db:
            db.execute('BEGIN EXCLUSIVE')
            db.rollback()
        again = self.reopen()
        self.assertEqual(again.get(self.key), (self.png, None))

    def test_hits_batch_disk_writes_and_flush_on_graceful_close(self):
        disk = self.reopen()
        disk._open()
        trace = []
        disk.db.set_trace_callback(trace.append)
        for _ in range(10):
            self.assertEqual(disk.get(self.key), (self.png, None))
        self.assertFalse(any(sql.startswith(('UPDATE', 'COMMIT', 'BEGIN')) for sql in trace))
        tick = disk.tick
        disk.close()
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT touched FROM thumbs').fetchone()[0], tick)
        self.assertEqual(sum(sql.startswith('COMMIT') for sql in trace), 1)

    def test_buffered_hit_is_used_by_eviction(self):
        disk = self.reopen()
        other = (*self.key[:-1], 256)
        last = (*self.key[:-1], 512)
        disk.put(other, (self.png, None))
        self.assertEqual(disk.get(self.key), (self.png, None))
        with patch('thumbnail_disk.MAX_ENTRIES', 2):
            disk.put(last, (self.png, None))
        self.assertIsNone(disk.get(other))
        self.assertEqual(disk.get(self.key), (self.png, None))
        self.assertEqual(disk.get(last), (self.png, None))

    def test_many_hits_bound_pending_writes_even_for_one_repeated_key(self):
        disk = self.reopen()
        disk._open()
        trace = []
        disk.db.set_trace_callback(trace.append)
        for _ in range(128):
            self.assertEqual(disk.get(self.key), (self.png, None))
        self.assertEqual(sum(sql.startswith('COMMIT') for sql in trace), 2)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT touched FROM thumbs').fetchone()[0], disk.tick)
