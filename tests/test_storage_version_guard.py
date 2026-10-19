"""Tests for forward-schema user_version guard and WAL checkpoint on close."""
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'app'))

from ai_process import AIUnavailable
from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch, VectorStore
from catalog import Catalog, CURRENT_SCHEMA_USER_VERSION
from production import ProductionCatalog
from storage_backup import RecoveryError, backup, restore


class StubEncoder:
    profile = DEFAULT_PROFILE
    available = True
    resident = False
    def encode(self, op, text):
        return [1.0] + [0.0] * 767
    def close(self):
        pass


class StorageVersionGuardTests(unittest.TestCase):
    def test_catalog_rejects_future_user_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / 'future_catalog.sqlite'
            with closing(sqlite3.connect(db_path)) as db:
                db.execute('CREATE TABLE dummy(id INTEGER)')
                db.execute('PRAGMA user_version = 1')
                db.commit()

            with self.assertRaises(ValueError) as ctx:
                Catalog(db_path)
            self.assertIn('Unsupported database schema user_version 1', str(ctx.exception))

            with self.assertRaises(ValueError) as ctx2:
                ProductionCatalog(db_path)
            self.assertIn('Unsupported database schema user_version 1', str(ctx2.exception))

    def test_vector_store_rejects_future_user_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / 'future_vectors.sqlite'
            with closing(sqlite3.connect(db_path)) as db:
                db.execute('CREATE TABLE dummy(id INTEGER)')
                db.execute('PRAGMA user_version = 2')
                db.commit()

            with self.assertRaises(AIUnavailable) as ctx:
                VectorStore(db_path)
            self.assertIn('Unsupported vector store user_version 2', str(ctx.exception))

    def test_wal_checkpoint_truncate_on_catalog_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / 'wal_catalog.sqlite'
            cat = ProductionCatalog(db_path)
            # Add records to generate WAL activity
            media_dir = Path(tmp) / 'media'
            media_dir.mkdir()
            root_id = cat.add_root(str(media_dir))
            wal_path = Path(str(db_path) + '-wal')
            # Close the catalog
            cat.close()
            # If WAL file exists, it must be truncated to 0 bytes
            if wal_path.exists():
                self.assertEqual(wal_path.stat().st_size, 0)

    def test_wal_checkpoint_truncate_on_ai_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / 'ai_catalog.sqlite'
            cat = ProductionCatalog(db_path)
            ai = AISearch(cat, StubEncoder())
            # Put state into vector store
            ai.store.save_state({'state': 'complete', 'processed': 1, 'total': 1, 'indexed': 1, 'skipped': 0, 'error': ''})
            wal_path = Path(str(ai.store.path) + '-wal')
            ai.close()
            cat.close()
            if wal_path.exists():
                self.assertEqual(wal_path.stat().st_size, 0)


if __name__ == '__main__':
    unittest.main()
