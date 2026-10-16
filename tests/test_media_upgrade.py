"""Upgrade/purge regression contracts. No real models or private media."""
from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch, VectorStore, revision
from production import ProductionCatalog


def vec(axis):
    return [float(i == axis) for i in range(768)]


class Encoder:
    available = True
    resident = False
    device = 'fixture'

    def __init__(self):
        self.calls = []
        self.on_image = None

    def encode(self, operation, payload):
        self.calls.append(operation)
        if operation == 'image' and self.on_image:
            self.on_image()
        return vec(1 if operation == 'image' else 0)

    def close(self):
        pass


class Previews:
    def read_cover(self, item_id):
        return b'generated representative frame', 'image/png'

    def video_representative_frames(self, item_id):
        return [(0, b'red'), (1000, b'blue')]


class MediaUpgradeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / 'generated'
        self.root.mkdir()
        for name in ('sample.png', 'sample.mp4', 'sample.wav'):
            (self.root / name).write_bytes(b'generated index-only fixture')
        self.catalog = ProductionCatalog(self.base / 'catalog.sqlite')
        self.addCleanup(self.catalog.close)
        self.root_id = self.catalog.add_root(str(self.root))
        self.catalog.index.scan(self.root_id)
        self.catalog.sync_index()
        self.rows = {r['kind']: r for r in self.catalog.search()['items']}

    def ai(self):
        encoder = Encoder()
        ai = AISearch(self.catalog, encoder)
        ai.previews = Previews()
        self.addCleanup(ai.close)
        return ai, encoder

    def test_old_index_refreshes_visual_inputs_once_without_reencoding_text(self):
        ai, encoder = self.ai()
        for row in self.rows.values():
            vectors = {'text': vec(0)}
            if row['kind'] == 'image': vectors['cover'] = vec(0)
            ai.store.put(row['id'], revision(row), vectors)
        self.assertEqual(ai.coverage()['remaining_total'], 2)
        ai.start(); ai.worker.join(10)
        self.assertEqual(ai.status()['state'], 'complete')
        self.assertEqual(encoder.calls, ['image', 'image', 'image'])
        self.assertEqual(ai.coverage()['remaining_total'], 0)
        calls = len(encoder.calls)
        ai.start(); ai.worker.join(10)
        self.assertEqual(len(encoder.calls), calls)
        result = ai.search('fixture', kind='video', source='cover')
        self.assertEqual(result['items'][0]['video_match_ms'], 0)

    def test_cancelled_video_refresh_keeps_previous_vectors_for_resume(self):
        ai, encoder = self.ai()
        row = self.rows['video']
        ai.store.put(row['id'], revision(row), {'text': vec(0)})
        encoder.on_image = ai.cancel.set
        ai.start(scope={'root_ids': [self.root_id], 'kind': 'video', 'shelf': None}); ai.worker.join(10)
        self.assertEqual(ai.status()['state'], 'cancelled')
        with ai.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM ai_video_frames').fetchone()[0], 0)
        self.assertEqual(ai.coverage(scope={'root_ids': [self.root_id], 'kind': 'video', 'shelf': None})['remaining_total'], 1)
        encoder.on_image = None
        ai.start(scope={'root_ids': [self.root_id], 'kind': 'video', 'shelf': None}); ai.worker.join(10)
        self.assertEqual(ai.status()['state'], 'complete')
        self.assertEqual(ai.coverage(scope={'root_ids': [self.root_id], 'kind': 'video', 'shelf': None})['remaining_total'], 0)

    def test_purge_removes_actual_profile_sidecars_and_main_video_frames(self):
        other = self.base / 'other'
        other.mkdir(); (other / 'keep.mp4').write_bytes(b'generated')
        other_root = self.catalog.add_root(str(other))
        self.catalog.index.scan(other_root); self.catalog.sync_index()
        keep = self.catalog.search(root_id=other_root)['items'][0]
        stores = [VectorStore(p.store_path(self.catalog.path), p) for p in
                  (DEFAULT_PROFILE, replace(DEFAULT_PROFILE, revision='a' * 40))]
        stores.append(VectorStore(self.catalog.path))
        remove = self.rows['video']
        for store in stores:
            for row in (remove, keep):
                store.put(row['id'], revision(row), {'text': vec(0), 'cover': vec(1)}, [(0, vec(1))])
        self.catalog.unregister_root(self.root_id)
        self.catalog.purge_inactive_root(self.root_id, consent=True)
        for store in stores:
            with store.connect() as db:
                for table in ('ai_vectors', 'ai_video_frames'):
                    self.assertEqual(db.execute(f'SELECT count(*) FROM {table} WHERE item_id=?', (remove['id'],)).fetchone()[0], 0, str(store.path))
                    self.assertGreater(db.execute(f'SELECT count(*) FROM {table} WHERE item_id=?', (keep['id'],)).fetchone()[0], 0)

    def test_purge_does_not_exceed_sqlite_variable_limit(self):
        with self.catalog.connect() as db:
            for n in range(300):
                loc = db.execute("INSERT INTO library_locations(root_id,relative_path,kind,size_bytes,mtime_ns,status,discovered_at,last_seen_at) VALUES(?,?,'image',1,1,'present','fixture','fixture')", (self.root_id, f'{n}.png')).lastrowid
                item = db.execute("INSERT INTO items(title,kind,tags) VALUES(?,'image','[]')", (f'{n}.png',)).lastrowid
                db.execute('INSERT INTO item_locations VALUES(?,?)', (item, loc))
        self.catalog.unregister_root(self.root_id)
        original = self.catalog.connect
        @contextmanager
        def constrained():
            with original() as db:
                db.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 100)
                yield db
        self.catalog.connect = constrained
        result = self.catalog.purge_inactive_root(self.root_id, consent=True)
        self.assertEqual(result['removed_items'], 303)
        self.assertEqual(self.catalog.search()['total'], 0)


    def test_failed_visual_refresh_preserves_legacy_cover_and_can_retry(self):
        from previews import PreviewUnavailable
        ai, encoder = self.ai()
        row = self.rows['image']
        ai.store.put(row['id'], revision(row), {'text': vec(0), 'cover': vec(0)})
        class Unavailable(Previews):
            def read_cover(self, item_id): raise PreviewUnavailable('generated transient failure')
        ai.previews = Unavailable()
        scope = {'root_ids': [self.root_id], 'kind': 'image', 'shelf': None}
        ai.start(scope=scope); ai.worker.join(10)
        self.assertEqual(ai.status()['state'], 'complete')
        self.assertEqual(ai.store.cover(row), vec(0))
        self.assertEqual(ai.coverage(scope=scope)['remaining_total'], 1)
        ai.previews = Previews()
        ai.start(scope=scope); ai.worker.join(10)
        self.assertEqual(ai.store.cover(row), vec(1))
        self.assertEqual(encoder.calls, ['image'])
        self.assertEqual(ai.coverage(scope=scope)['remaining_total'], 0)

    def test_text_only_profile_needs_no_visual_migration(self):
        encoder = Encoder()
        encoder.profile = replace(DEFAULT_PROFILE, modalities=('text',))
        ai = AISearch(self.catalog, encoder)
        self.addCleanup(ai.close)
        for row in self.rows.values(): ai.store.put(row['id'], revision(row), {'text': vec(0)})
        ai.previews = None
        self.assertEqual(ai.coverage()['remaining_total'], 0)
        ai.start(); ai.worker.join(10)
        self.assertEqual(ai.status()['state'], 'complete')
        self.assertEqual(encoder.calls, [])

    def test_invalid_frame_replace_rolls_back_contract_and_vectors(self):
        from ai_search import VIDEO_SOURCE_CONTRACT
        ai, _ = self.ai()
        row = self.rows['video']
        ai.store.put(row['id'], revision(row), {'text': vec(0), 'cover': vec(1)}, [(0, vec(1))], source_contract=VIDEO_SOURCE_CONTRACT)
        with self.assertRaises(sqlite3.IntegrityError):
            ai.store.put(row['id'], revision(row), {'text': vec(1)}, [(0, vec(0)), (0, vec(1))], source_contract=VIDEO_SOURCE_CONTRACT)
        self.assertTrue(ai.store.fresh_row(row))
        self.assertEqual(ai.store.text(row), vec(0))
        self.assertEqual(ai.store.cover(row), vec(1))

    def test_purge_refuses_wrong_profile_keeps_metadata_then_retries(self):
        row = self.rows['image']
        self.catalog.update([row['id']], {'tags': ['manual-keep'], 'shelf': 'manual'})
        store = VectorStore(DEFAULT_PROFILE.store_path(self.catalog.path))
        store.put(row['id'], revision(row), {'text': vec(0)})
        with store.connect() as db: db.execute("UPDATE ai_profile SET value='unexpected-profile'")
        self.catalog.unregister_root(self.root_id)
        with self.assertRaisesRegex(ValueError, 'library records were kept'):
            self.catalog.purge_inactive_root(self.root_id, consent=True)
        self.assertEqual(self.catalog.get(row['id'])['tags'], ['manual-keep'])
        self.assertEqual(len(self.catalog.index.roots(include_inactive=True)), 1)
        with store.connect() as db: db.execute('UPDATE ai_profile SET value=?', (DEFAULT_PROFILE.key,))
        self.assertEqual(self.catalog.purge_inactive_root(self.root_id, consent=True)['removed_items'], 3)

    def test_purge_profile_failure_rolls_back_that_cache_and_keeps_manual_records(self):
        from ai_search import IMAGE_SOURCE_CONTRACT
        row = self.rows['image']
        self.catalog.update([row['id']], {'tags': ['manual-keep']})
        store = VectorStore(DEFAULT_PROFILE.store_path(self.catalog.path))
        store.put(row['id'], revision(row), {'text': vec(0)}, source_contract=IMAGE_SOURCE_CONTRACT)
        with store.connect() as db:
            db.execute("CREATE TRIGGER stop_cleanup BEFORE DELETE ON ai_source_contracts BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
        self.catalog.unregister_root(self.root_id)
        with self.assertRaisesRegex(ValueError, 'library records were kept'):
            self.catalog.purge_inactive_root(self.root_id, consent=True)
        self.assertEqual(self.catalog.get(row['id'])['tags'], ['manual-keep'])
        self.assertIsNotNone(store.text(row))
        with store.connect() as db: db.execute('DROP TRIGGER stop_cleanup')
        self.catalog.purge_inactive_root(self.root_id, consent=True)

    def test_purge_ignores_unrelated_sqlite_files(self):
        other = self.base / (self.catalog.path.name + '.ai.not-a-profile.sqlite')
        other.write_bytes(b'unrelated generated data')
        self.catalog.unregister_root(self.root_id)
        self.catalog.purge_inactive_root(self.root_id, consent=True)
        self.assertEqual(other.read_bytes(), b'unrelated generated data')


if __name__ == '__main__': unittest.main()
