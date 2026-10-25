"""Generated-only startup preferences, ownership, migration and missing visibility."""
import sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import contextmanager
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from production import ProductionCatalog
from catalog import Catalog
from startup_scans import StartupScans
from storage_backup import backup,restore


class StartupScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.cat=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.cat.close)
        self.media=[];self.roots=[]
        for i in range(3):
            folder=self.base/str(i);folder.mkdir();(folder/'item.png').write_bytes(b'generated')
            self.media.append(folder);self.roots.append(self.cat.add_root(str(folder)))
        self.queue=StartupScans(self.cat);self.addCleanup(self.queue.close)
    def finish(self):
        if self.queue.worker:self.queue.worker.join(5);self.assertFalse(self.queue.worker.is_alive())
        return self.queue.state()
    def test_no_implicit_scan_and_default_is_off(self):
        self.assertEqual(self.cat.search()['total'],0)
        self.assertTrue(all(root['startup_scan']=='none' for root in self.cat.registered_roots()))
        self.assertEqual(self.queue.state()['state'],'idle')
        self.assertEqual(self.queue.start()['total'],0);self.assertIsNone(self.queue.worker)
    def test_selected_roots_run_once_after_explicit_frontend_ready(self):
        self.cat.set_root_startup_scan(self.roots[:2],'list')
        self.assertEqual(self.cat.search()['total'],0)
        self.queue.start();self.queue.start();state=self.finish()
        self.assertEqual(state['processed'],2);self.assertEqual(self.cat.search()['total'],2)
        self.assertEqual([r['root_id'] for r in state['results']],self.roots[:2])
        with self.cat.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM scan_jobs').fetchone()[0],2)
    def test_offline_root_fails_without_blocking_other_roots(self):
        self.cat.set_root_startup_scan(self.roots[:2],'list');self.media[0].rename(self.base/'offline')
        self.queue.start();state=self.finish()
        self.assertEqual([r['state'] for r in state['results']],['failed','complete'])
        self.assertEqual(self.cat.search()['total'],1)
    def test_manual_scan_is_not_cancelled_when_waiting_queue_is_cancelled(self):
        self.cat.set_root_startup_scan(self.roots[:1],'list');started=threading.Event();release=threading.Event()
        original=self.cat.index.scan
        def held(root,**kwargs):started.set();release.wait(3);return original(root,**kwargs)
        with patch.object(self.cat.index,'scan',side_effect=held):
            manual=self.cat.start_scan(self.roots[2]);self.assertTrue(started.wait(1))
            self.queue.start();self.queue.cancel();release.set();self.cat._worker.join(3);self.finish()
        self.assertEqual(self.cat.scan_state(manual['job_id'])['state'],'complete')
        self.assertEqual(self.queue.state()['state'],'cancelled')
    def test_close_reports_unfinished_owner_instead_of_allowing_restore_proof(self):
        self.cat.set_root_startup_scan(self.roots[:1],'list');reached=threading.Event();release=threading.Event()
        original=self.cat.index.scan
        def held(*args,**kwargs):reached.set();release.wait(3);return original(*args,**kwargs)
        with patch.object(self.cat.index,'scan',side_effect=held):
            try:
                self.queue.start();self.assertTrue(reached.wait(1))
                self.assertFalse(self.queue.close(timeout=.01))
                with self.assertRaises(ValueError):self.queue.start()
            finally:release.set()
            self.cat._worker.join(3);self.assertTrue(self.queue.close(timeout=3))
        self.assertEqual(self.queue.state()['state'],'cancelled')
    def test_ai_unavailable_keeps_successful_list(self):
        def unavailable(*args):raise RuntimeError('model missing')
        self.cat.ai_scan_hook=unavailable;self.cat.set_root_startup_scan(self.roots[:1],'list_and_ai')
        self.queue.start();state=self.finish()
        self.assertEqual(state['results'][0]['ai_state'],'failed');self.assertEqual(self.cat.search()['total'],1)
    def test_v2_migration_retains_favorites_and_defaults_to_off(self):
        self.cat.set_root_favorite(self.roots[0],True)
        with self.cat.connect() as db:
            db.execute('ALTER TABLE registered_root_preferences DROP COLUMN startup_scan');db.execute('PRAGMA user_version=2')
        self.cat.root_preferences.migrate()
        self.assertTrue(self.cat.registered_roots()[0]['favorite'])
        self.assertTrue(all(r['startup_scan']=='none' for r in self.cat.registered_roots()))
        with self.assertRaises(ValueError):Catalog(self.cat.path,supported_schema=2)
    def test_v2_migration_failure_rolls_back_column_and_version(self):
        with self.cat.connect() as db:
            db.execute('ALTER TABLE registered_root_preferences DROP COLUMN startup_scan');db.execute('PRAGMA user_version=2')
        connect=self.cat.root_preferences.connect
        @contextmanager
        def injected():
            with connect() as db:
                def execute(sql,*args):
                    if sql=='PRAGMA user_version=3':raise RuntimeError('injected migration failure')
                    return db.execute(sql,*args)
                yield SimpleNamespace(execute=execute)
        with patch.object(self.cat.root_preferences,'connect',injected),self.assertRaises(RuntimeError):self.cat.root_preferences.migrate()
        with self.cat.connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],2)
            self.assertNotIn('startup_scan',[r[1] for r in db.execute('PRAGMA table_info(registered_root_preferences)')])
    def test_invalid_or_partially_unknown_settings_do_not_commit(self):
        for roots,mode in [(self.roots[:1],True),(self.roots[:1],'automatic'),([], 'list'),([True],'list'),([self.roots[0],999],'list')]:
            with self.assertRaises((ValueError,KeyError)):self.cat.set_root_startup_scan(roots,mode)
        self.assertTrue(all(root['startup_scan']=='none' for root in self.cat.registered_roots()))
    def test_backup_restore_preserves_preferences_and_old_v2_is_supported(self):
        self.cat.set_root_startup_scan(self.roots[:1],'list_and_ai');self.cat.set_root_favorite(self.roots[0],True)
        backup(self.cat.path,self.base/'bundle');restore(self.base/'bundle',self.base/'restore')
        recovered=ProductionCatalog(self.base/'restore/catalog.sqlite');self.addCleanup(recovered.close)
        self.assertEqual(recovered.registered_roots()[0]['startup_scan'],'list_and_ai')
        self.assertTrue(recovered.registered_roots()[0]['favorite'])
        with self.cat.connect() as db:
            db.execute('ALTER TABLE registered_root_preferences DROP COLUMN startup_scan');db.execute('PRAGMA user_version=2')
        backup(self.cat.path,self.base/'old-bundle');restore(self.base/'old-bundle',self.base/'old-restore')
        old=ProductionCatalog(self.base/'old-restore/catalog.sqlite');self.addCleanup(old.close)
        self.assertTrue(old.registered_roots()[0]['favorite']);self.assertEqual(old.registered_roots()[0]['startup_scan'],'none')
    def test_missing_is_hidden_but_annotations_and_identity_recover(self):
        self.cat.start_scan(self.roots[0]);self.cat._worker.join(3)
        item=self.cat.search()['items'][0];shelf=self.cat.change_shelf('create',name='保全')['id']
        self.cat.update([item['id']],{'favorite':True,'tags':['維持'],'shelf_ids':[shelf]})
        path=self.media[0]/'item.png';path.unlink();self.cat.start_scan(self.roots[0]);self.cat._worker.join(3)
        self.assertEqual(self.cat.search()['total'],0);self.assertEqual(self.cat.search(view='favorites')['total'],0)
        self.assertEqual(self.cat.shelf_descriptors()[0]['item_count'],0)
        row=self.cat.get(item['id']);self.assertEqual(row['availability'],'missing');self.assertEqual(row['tags'],['維持'])
        path.write_bytes(b'reappeared');self.cat.start_scan(self.roots[0]);self.cat._worker.join(3)
        row=self.cat.search()['items'][0];self.assertEqual(row['id'],item['id']);self.assertTrue(row['favorite']);self.assertEqual(row['shelf_ids'],[shelf])
    def test_failed_or_cancelled_scan_does_not_mark_previous_items_missing(self):
        self.cat.start_scan(self.roots[0]);self.cat._worker.join(3);item=self.cat.search()['items'][0]
        self.media[0].rename(self.base/'offline');self.cat.start_scan(self.roots[0]);self.cat._worker.join(3)
        self.assertEqual(self.cat.get(item['id'])['availability'],'present')
        (self.base/'offline').rename(self.media[0]);(self.media[0]/'item.png').unlink()
        with patch.object(self.cat.index,'scan',side_effect=InterruptedError):
            self.cat.start_scan(self.roots[0]);self.cat._worker.join(3)
        self.assertEqual(self.cat.get(item['id'])['availability'],'present')

    def test_completed_job_identity_does_not_follow_later_manual_scan(self):
        first=self.cat.start_scan(self.roots[0]);self.cat._worker.join(3)
        second=self.cat.start_scan(self.roots[1]);self.cat._worker.join(3)
        self.assertEqual(self.cat.scan_state(first['job_id'])['root_ids'],[self.roots[0]])
        self.assertEqual(self.cat.scan_state(second['job_id'])['root_ids'],[self.roots[1]])
        self.assertFalse(self.cat.cancel_scan(expected_job_id=first['job_id'])['cancel_requested'])

    def test_scan_waiting_for_backup_fence_keeps_reads_available(self):
        self.cat.set_root_startup_scan(self.roots[:1],'list')
        with self.cat.writer_fence.pause():
            self.queue.start()
            self.assertEqual(self.cat.search()['total'],0)
            self.assertEqual(self.queue.state()['processed'],0)
        self.assertEqual(self.finish()['results'][0]['state'],'complete')
        self.assertEqual(self.cat.search()['total'],1)

    def test_catalog_v3_remains_compatible_with_historical_in_catalog_vectors(self):
        from ai_search import VectorStore
        store=VectorStore(self.cat.path,writer_fence=self.cat.writer_fence)
        self.assertEqual(store.path,self.cat.path)

    def test_startup_http_requires_auth_and_exact_readiness_and_only_runs_once(self):
        import json,urllib.request,urllib.error
        from http.server import ThreadingHTTPServer
        from production_server import production_handler,DisabledAI
        from ai_settings import AIProfileSettings
        from wd_tagger import DisabledTagger
        profiles=AIProfileSettings(Path(__file__).resolve().parents[1],self.base/'settings.json',profile_directory=self.base/'profiles')
        handler=production_handler(self.cat,'fixture',ai=DisabledAI(),tagger=DisabledTagger(),profiles=profiles)
        handler.log_message=lambda *args:None
        server=ThreadingHTTPServer(('127.0.0.1',0),handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def close():
            server.shutdown();server.server_close();thread.join(5)
            for resource in (handler.startup_scans,handler.results,handler.animations,handler.thumbnails,handler.setup_jobs):resource.close()
        self.addCleanup(close);origin=f'http://127.0.0.1:{server.server_port}'
        def request(path,body,token='fixture'):
            data=body if isinstance(body,str) else json.dumps(body)
            req=urllib.request.Request(origin+path,data=data.encode(),headers={'Origin':origin,'X-Aredoko-Token':token,'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(req,timeout=5) as response:return response.status,json.load(response)
            except urllib.error.HTTPError as ex:
                with ex:return ex.code,json.load(ex)
        pref='/api/library/roots/startup-scan';start='/api/library/startup-scan/start'
        self.assertEqual(request(pref,{'root_ids':[self.roots[0]],'mode':'list'},'wrong')[0],403)
        for bad in ({'root_ids':[True],'mode':'list'},{'root_ids':[self.roots[0]],'mode':'all'},{'root_ids':[self.roots[0]],'mode':'list','extra':1}):
            self.assertEqual(request(pref,bad)[0],400)
        self.assertEqual(request(pref,{'root_ids':[self.roots[0]],'mode':'list'})[0],200)
        self.assertIsNone(handler.startup_scans.worker)
        for bad in ({},{'frontend_ready':1},{'frontend_ready':True,'extra':1},'{"frontend_ready":false,"frontend_ready":true}'):
            self.assertEqual(request(start,bad)[0],400)
        self.assertEqual(request(start,{'frontend_ready':True},'wrong')[0],403)
        self.assertEqual(request(start,{'frontend_ready':True})[0],200)
        handler.startup_scans.worker.join(5)
        self.assertEqual(request(start,{'frontend_ready':True})[1]['processed'],1)
        with self.cat.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM scan_jobs').fetchone()[0],1)

if __name__=='__main__':unittest.main()
