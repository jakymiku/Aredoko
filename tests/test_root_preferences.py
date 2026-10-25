"""Root favorites and catalog2 migration/recovery, generated files only."""
import json,sqlite3,sys,tempfile,unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from production import ProductionCatalog
from catalog import Catalog
from root_preferences import RootPreferences
from storage_backup import backup,restore,_database,RecoveryError

class RootPreferencesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.media=self.base/'media';self.media.mkdir();(self.media/'a.png').write_bytes(b'generated-only')
        self.cat=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.cat.close)
        self.root=self.cat.add_root(str(self.media));self.cat.index.scan(self.root);self.cat.sync_index();self.item=self.cat.search()['items'][0]['id']
    def test_favorite_is_independent_and_survives_unregister_and_reregister(self):
        self.cat.set_root_favorite(self.root,True)
        self.assertTrue(self.cat.registered_roots()[0]['favorite']);self.assertFalse(self.cat.get(self.item)['favorite'])
        self.cat.unregister_root(self.root);self.assertEqual(self.cat.registered_roots(),[])
        self.assertTrue(self.cat.registered_roots(include_inactive=True)[0]['favorite'])
        self.assertEqual(self.cat.add_root(str(self.media)),self.root)
        reopened=ProductionCatalog(self.cat.path);self.addCleanup(reopened.close);self.assertTrue(reopened.registered_roots()[0]['favorite'])
        self.cat.set_root_favorite(self.root,False);self.assertFalse(self.cat.registered_roots()[0]['favorite'])
    def test_invalid_flags_and_unknown_roots_do_not_commit(self):
        for value in (1,'true',None):
            with self.assertRaises(ValueError):self.cat.set_root_favorite(self.root,value)
        with self.assertRaises(KeyError):self.cat.set_root_favorite(9999,True)
        self.assertFalse(self.cat.registered_roots()[0]['favorite'])
    def test_purge_removes_root_metadata_without_dropping_shelves(self):
        self.cat.set_root_favorite(self.root,True);self.cat.unregister_root(self.root);self.cat.purge_inactive_root(self.root,True)
        with self.cat.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM registered_root_preferences').fetchone()[0],0)
            self.assertIsNone(db.execute('PRAGMA foreign_key_check').fetchone())
    def test_v1_migration_rolls_back_and_old_binary_refuses_v2(self):
        with self.cat.connect() as db:db.execute('DROP TABLE registered_root_preferences');db.execute('PRAGMA user_version=1')
        original=RootPreferences._create
        def fail(db):original(db);raise RuntimeError('injected')
        with patch.object(RootPreferences,'_create',side_effect=fail),self.assertRaises(RuntimeError):self.cat.root_preferences.migrate()
        with self.cat.connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],1)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='registered_root_preferences'").fetchone())
        self.cat.root_preferences.migrate();self.cat.root_preferences.migrate()
        with self.assertRaisesRegex(ValueError,'user_version'):Catalog(self.cat.path,supported_schema=1)
    def test_backup_roundtrip_preserves_root_favorites_and_rejects_bad_versions(self):
        self.cat.set_root_favorite(self.root,True);backup(self.cat.path,self.base/'bundle')
        restore(self.base/'bundle',self.base/'restored')
        recovered=ProductionCatalog(self.base/'restored/catalog.sqlite');self.addCleanup(recovered.close)
        self.assertTrue(recovered.registered_roots()[0]['favorite'])
        with self.cat.connect() as db:db.execute('PRAGMA user_version=1')
        with self.assertRaises(RecoveryError):_database(self.cat.path,'catalog')
        with self.cat.connect() as db:db.execute('PRAGMA user_version=4')
        with self.assertRaises(RecoveryError):_database(self.cat.path,'catalog')
        with self.assertRaisesRegex(ValueError,'user_version'):ProductionCatalog(self.cat.path)

    def test_http_favorite_requires_authentication_and_strict_boolean(self):
        import threading,urllib.request,urllib.error
        from http.server import ThreadingHTTPServer
        from production_server import production_handler,DisabledAI
        from ai_settings import AIProfileSettings
        from wd_tagger import DisabledTagger
        repo=Path(__file__).resolve().parents[1]
        profiles=AIProfileSettings(repo,self.base/'ai-settings.json',profile_directory=self.base/'profiles')
        handler=production_handler(self.cat,'fixture',ai=DisabledAI(),tagger=DisabledTagger(),profiles=profiles);handler.log_message=lambda *args:None
        server=ThreadingHTTPServer(('127.0.0.1',0),handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def close():
            server.shutdown();server.server_close();thread.join(5)
            for resource in (handler.results,handler.animations,handler.thumbnails,handler.setup_jobs):resource.close()
        self.addCleanup(close);origin=f'http://127.0.0.1:{server.server_port}'
        def request(body,token='fixture',route='/api/library/roots/favorite'):
            payload=body if isinstance(body,str) else json.dumps(body)
            req=urllib.request.Request(origin+route,data=payload.encode(),headers={'Origin':origin,'X-Aredoko-Token':token,'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(req,timeout=5) as response:return response.status,json.load(response)
            except urllib.error.HTTPError as ex:return ex.code,json.load(ex)
        self.assertEqual(request({'root_id':self.root,'favorite':True},'wrong')[0],403)
        self.assertEqual(request({'root_id':self.root,'favorite':1})[0],400)
        self.assertEqual(request('{"root_id":'+str(self.root)+',"favorite":false,"favorite":true}')[0],400)
        self.assertEqual(request({'root_id':self.root,'favorite':True})[0],200)
        self.assertTrue(self.cat.registered_roots()[0]['favorite'])
        shelf=self.cat.change_shelf('create',name='初期棚')['id']
        self.assertEqual(request({'root_ids':[self.root],'shelf_ids':[shelf],'fill_unset':True},route='/api/library/roots/shelves')[0],200)
        self.assertEqual(self.cat.get(self.item)['shelf_ids'],[shelf])
        self.assertEqual(request('{"root_ids":['+str(self.root)+'],"shelf_ids":[],"fill_unset":false,"fill_unset":true}',route='/api/library/roots/shelves')[0],400)
