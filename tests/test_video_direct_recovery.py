"""Direct-video recovery must preserve complete indexes and clean purged roots."""
from contextlib import closing
from pathlib import Path
import sqlite3,sys,unittest
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_video_direct_index as fixture
from ai_profiles import DEFAULT_PROFILE
from ai_search import VectorStore
from live_backup import capture_live,BackupSelection
from storage_backup import restore,_database,RecoveryError
from audio_direct_index import TABLES as AUDIO_TABLES

class VideoRecoveryTests(unittest.TestCase):
    setUp=fixture.SuppliedIndexTests.setUp
    supplied=fixture.SuppliedIndexTests.supplied
    snapshot=fixture.SuppliedIndexTests.snapshot
    seed=fixture.SuppliedIndexTests.seed
    def test_video_and_legacy_backup_restore_preserve_both_namespaces(self):
        previous=self.seed()
        VectorStore(DEFAULT_PROFILE.store_path(self.catalog.path),DEFAULT_PROFILE,writer_fence=self.catalog.writer_fence)
        bundle=self.base/'bundle'
        capture_live(self.catalog,bundle,quiesce=self.catalog.writer_fence.pause,selection=BackupSelection(settings=False,history=True,reader_progress=True,vectors=True))
        destination=self.base/'restored';restore(bundle,destination)
        with closing(sqlite3.connect(self.encoder.profile.store_path(destination/'catalog.sqlite'))) as db:
            actual=[db.execute('SELECT * FROM '+table+' ORDER BY item_id,rowid').fetchall() for table in ('ai_video_direct_sources','ai_video_direct_windows')]
        self.assertEqual(actual,previous)
        self.assertTrue(DEFAULT_PROFILE.store_path(destination/'catalog.sqlite').is_file())
    def test_partial_mixed_or_wrong_version_direct_tables_are_rejected(self):
        self.seed()
        with self.index.store.connect() as db:db.execute('PRAGMA user_version=0')
        with self.assertRaises(RecoveryError):_database(self.index.store.path,'vectors')
        with self.index.store.connect() as db:
            db.execute('PRAGMA user_version=1')
            for statement in AUDIO_TABLES:db.execute(statement)
        with self.assertRaises(RecoveryError):_database(self.index.store.path,'vectors')
        with self.index.store.connect() as db:
            for table in ('ai_audio_direct_sources','ai_audio_direct_windows','ai_video_direct_windows'):db.execute('DROP TABLE '+table)
        with self.assertRaises(RecoveryError):_database(self.index.store.path,'vectors')
    def test_root_purge_removes_video_vectors_and_preserves_original(self):
        self.seed();before=self.path.read_bytes()
        self.catalog.unregister_root(self.root);self.catalog.purge_inactive_root(self.root,consent=True)
        self.assertEqual(self.snapshot(),[[],[]]);self.assertEqual(self.path.read_bytes(),before)

if __name__=='__main__':unittest.main()
