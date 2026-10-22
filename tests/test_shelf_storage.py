"""Independent shelf storage/migration; generated DB only, not production activation."""
import json,sqlite3,sys,tempfile,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from production import ProductionCatalog
from shelves import ShelfStore,TABLES
from storage_backup import backup,restore,_database,RecoveryError

class ShelfStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        media=self.base/'media';media.mkdir();(media/'a.png').write_bytes(b'generated-only fixture');(media/'b.png').write_bytes(b'generated-only fixture')
        self.catalog=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.catalog.close)
        self.root=self.catalog.add_root(str(media),default_shelf='初期棚');self.catalog.index.scan(self.root);self.catalog.sync_index()
        self.ids=[row['id'] for row in self.catalog.search()['items']]
        self.catalog.update([self.ids[0]],{'shelf':'手動棚','tags':['keep'],'favorite':True})
        self.store=ShelfStore(self.catalog.connect)
    def migrate(self):self.store.migrate();return {r['name']:r['id'] for r in self.store.list()}
    def memberships(self,item):
        with self.catalog.connect() as db:return [r[0] for r in db.execute('SELECT shelf_id FROM item_shelves WHERE item_id=? ORDER BY shelf_id',(item,))]
    def test_migration_preserves_names_memberships_and_empty_shelves(self):
        names=self.migrate();self.assertEqual(set(names),{'初期棚','手動棚'})
        self.assertEqual(self.memberships(self.ids[0]),[names['手動棚']]);self.assertEqual(self.memberships(self.ids[1]),[names['初期棚']])
        with self.catalog.connect() as db:self.assertEqual(db.execute('SELECT shelf_id FROM root_shelves WHERE root_id=?',(self.root,)).fetchone()[0],names['初期棚'])
        empty=self.store.create('空の棚');self.assertEqual(next(r['item_count'] for r in self.store.list() if r['id']==empty),0)
        self.store.migrate();self.assertEqual(len(self.store.list()),3)
    def test_failed_migration_rolls_back_schema_version_and_scalar(self):
        original=ShelfStore._migrate_rows
        def fail(db):original(db);raise RuntimeError('injected precommit failure')
        with patch.object(ShelfStore,'_migrate_rows',side_effect=fail),self.assertRaises(RuntimeError):self.store.migrate()
        with self.catalog.connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],0)
            self.assertFalse(TABLES&{r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")})
        self.assertEqual(self.catalog.get(self.ids[0])['shelf'],'手動棚')
    def test_multiple_memberships_partial_removal_and_scalar_rejection(self):
        names=self.migrate();selected=list(names.values());self.store.replace('item',[self.ids[0]],selected)
        with self.assertRaisesRegex(ValueError,'lose multiple'):self.store.legacy_replace([self.ids[0],self.ids[1]],'replacement')
        self.assertEqual(self.memberships(self.ids[0]),sorted(selected));self.assertEqual(self.catalog.get(self.ids[1])['shelf'],'初期棚')
        self.store.replace('item',[self.ids[0]],[selected[1]]);self.assertEqual(self.memberships(self.ids[0]),[selected[1]])
        self.store.legacy_replace([self.ids[0]],'new scalar');self.assertEqual(self.catalog.get(self.ids[0])['shelf'],'new scalar')
    def test_rename_delete_preserve_items_annotations_and_other_shelf(self):
        names=self.migrate();first,second=names.values();self.store.replace('item',[self.ids[0]],[first,second])
        self.store.rename(first,'改名棚');self.assertEqual(self.catalog.get(self.ids[1])['shelf'],'改名棚')
        self.store.delete(first);self.assertEqual(self.memberships(self.ids[0]),[second]);self.assertEqual(self.catalog.get(self.ids[0])['tags'],['keep'])
        self.assertTrue(self.catalog.get(self.ids[0])['favorite']);self.assertEqual(self.catalog.search()['total'],2)
        self.assertGreater(self.store.create('新規棚'),max(first,second))
    def test_unknown_ids_and_conflicting_rename_are_atomic(self):
        names=self.migrate();before=self.store.list();prior=self.memberships(self.ids[0])
        with self.assertRaises(KeyError):self.store.replace('item',[self.ids[0],999999],list(names.values()))
        with self.assertRaises(KeyError):self.store.replace('root',[self.root],[999999])
        with self.assertRaises(sqlite3.IntegrityError):self.store.rename(next(iter(names.values())),list(names)[1])
        self.assertEqual(self.store.list(),before);self.assertEqual(self.memberships(self.ids[0]),prior)
        for ids in ([True],[0],[-1],[1,1]):
            with self.assertRaises(ValueError):self.store.replace('item',[self.ids[0]],ids)
    def test_version_rejects_old_app_and_future_or_incomplete_schema(self):
        self.migrate()
        with self.assertRaisesRegex(ValueError,'Unsupported database'):ProductionCatalog(self.catalog.path)
        with self.catalog.connect() as db:db.execute('PRAGMA user_version=2')
        with self.assertRaises(ValueError):self.store.migrate()
    def test_backup_roundtrip_preserves_version1_and_all_memberships(self):
        names=self.migrate();self.store.replace('item',self.ids,list(names.values()));self.store.create('empty')
        with self.catalog.connect() as db:
            before={t:db.execute('SELECT * FROM '+t+' ORDER BY rowid').fetchall() for t in TABLES}
        bundle=self.base/'backup';output=self.base/'restored'
        backup(self.catalog.path,bundle,include_vectors=False);restore(bundle,output)
        _database(output/'catalog.sqlite','catalog')
        with closing(sqlite3.connect(output/'catalog.sqlite')) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],1)
            self.assertEqual({t:db.execute('SELECT * FROM '+t+' ORDER BY rowid').fetchall() for t in TABLES},{t:[tuple(r) for r in rows] for t,rows in before.items()})
        # A partial version0 schema must never pass recovery validation.
        with self.catalog.connect() as db:db.execute('PRAGMA user_version=0')
        with self.assertRaises(RecoveryError):_database(self.catalog.path,'catalog')
