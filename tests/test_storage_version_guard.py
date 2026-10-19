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
            media_dir = Path(tmp) / 'media'
            media_dir.mkdir()
            cat.add_root(str(media_dir))
            # Hold a connection to keep WAL file active with uncheckpointed frames
            with closing(sqlite3.connect(db_path)) as db:
                db.execute("INSERT INTO items(id, title, kind, tags) VALUES(100, 't', 'image', '[]')")
                db.commit()
                wal_path = Path(str(db_path) + '-wal')
                self.assertTrue(wal_path.exists(), "Catalog WAL must exist during active connection")
                self.assertGreater(wal_path.stat().st_size, 0, "Catalog WAL must have active frames before checkpoint")
                # Close catalog, which must execute PRAGMA wal_checkpoint(TRUNCATE)
                cat.close()
                self.assertEqual(wal_path.stat().st_size, 0, "Catalog WAL must be truncated to 0 bytes by close checkpoint")

    def test_wal_checkpoint_truncate_on_ai_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / 'ai_catalog.sqlite'
            cat = ProductionCatalog(db_path)
            ai = AISearch(cat, StubEncoder())
            # Hold a connection to keep vector store WAL file active with uncheckpointed frames
            with closing(sqlite3.connect(ai.store.path)) as vdb:
                vdb.execute("INSERT INTO ai_vectors(item_id, revision, modality, vector) VALUES(1, 'rev1', 'text', ?)", (b'dummy',))
                vdb.commit()
                wal_path = Path(str(ai.store.path) + '-wal')
                self.assertTrue(wal_path.exists(), "Vector store WAL must exist during active connection")
                self.assertGreater(wal_path.stat().st_size, 0, "Vector store WAL must have active frames before checkpoint")
                ai.close()
                self.assertEqual(wal_path.stat().st_size, 0, "Vector store WAL must be truncated to 0 bytes by close checkpoint")
            cat.close()


if __name__ == '__main__':
    unittest.main()
