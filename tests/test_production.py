"""Production integration tests use generated temporary files only."""
import sys, tempfile, unittest, json, threading, urllib.request, urllib.error
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from production import ProductionCatalog
from production_server import production_handler
from catalog import Catalog

class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.media=self.base/'media';self.media.mkdir()
        self.db=self.base/'catalog.sqlite';self.catalog=ProductionCatalog(self.db)
        self.addCleanup(self.catalog.close)
    def fixture(self,name='夜の本.cbz'):
        path=self.media/name;path.write_bytes(b'fictional, not an actual media file');return path
    def scan(self,root):
        self.catalog.start_scan(root);self.catalog._worker.join(10)
        self.assertFalse(self.catalog._worker.is_alive())
        return self.catalog.scan_state()
    def test_persist_metadata_rescan_and_readonly(self):
        path=self.fixture();before=(path.read_bytes(),path.stat().st_mtime_ns)
        root=self.catalog.add_root(str(self.media));self.assertEqual(self.catalog.search()['total'],0)
        self.assertEqual(self.scan(root)['state'],'complete')
        item=self.catalog.search()['items'][0];self.assertFalse(item['synthetic'])
        self.catalog.update([item['id']],{'tags':['青い夜'],'favorite':True,'reviewed':True,'shelf':'本棚'})
        self.scan(root)
        restarted=ProductionCatalog(self.db);self.addCleanup(restarted.close)
        row=restarted.search('青い夜',view='favorites')['items'][0]
        self.assertEqual(row['id'],item['id']);self.assertEqual(row['shelf'],'本棚');self.assertTrue(row['reviewed'])
        self.assertEqual(before,(path.read_bytes(),path.stat().st_mtime_ns))
    def test_missing_offline_and_excluded_preserve_annotations(self):
        path=self.fixture();root=self.catalog.add_root(str(self.media));self.scan(root)
        item=self.catalog.search()['items'][0];self.catalog.update([item['id']],{'tags':['keep']})
        # Fixture-only mutation simulates an external move/offline drive.
        path.unlink();self.scan(root)
        self.assertEqual(self.catalog.get(item['id'])['availability'],'missing')
        self.media.rename(self.base/'offline');self.assertEqual(self.scan(root)['state'],'failed')
        self.assertEqual(self.catalog.get(item['id'])['tags'],['keep'])
        (self.base/'offline').rename(self.media);self.fixture();self.scan(root)
        self.catalog.index.set_excludes(root,['*.cbz']);self.scan(root)
        self.assertEqual(self.catalog.search()['total'],0)
        self.assertEqual(self.catalog.get(item['id'])['tags'],['keep'])
    def test_cancel_rolls_back_partial_index(self):
        self.fixture();root=self.catalog.add_root(str(self.media));self.scan(root)
        for i in range(110):self.fixture(f'{i}.png')
        with self.assertRaises(InterruptedError):
            self.catalog.index.scan(root,cancelled=self.catalog._cancel.is_set,progress=lambda n:self.catalog._cancel.set())
        self.assertEqual(self.catalog.index.locations(root)['total'],1)
        self.assertEqual(self.scan(root)['state'],'complete')
        self.assertEqual(self.catalog.search()['total'],111)
    def test_interrupted_job_recovered_on_restart(self):
        with self.catalog.connect() as db:db.execute("INSERT INTO scan_jobs(root_id,state) VALUES(1,'running')")
        restarted=ProductionCatalog(self.db);self.addCleanup(restarted.close)
        self.assertEqual(restarted.scan_state()['state'],'interrupted')
    def test_demo_db_rejected_and_nested_database_rejected(self):
        demo=self.base/'demo.sqlite';Catalog(demo).seed(1)
        with self.assertRaises(ValueError):ProductionCatalog(demo)
        with self.assertRaises(ValueError):self.catalog.add_root(str(self.base))
    def test_http_requires_consent_and_session(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'test-token'))
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        origin=f'http://127.0.0.1:{server.server_port}'
        def post(body,token='test-token'):
            req=urllib.request.Request(origin+'/api/library/roots',json.dumps(body).encode(),headers={'Origin':origin,'X-Aredoko-Token':token,'Content-Type':'application/json'})
            return urllib.request.urlopen(req)
        for body,token in [({'path':str(self.media)},'test-token'),({'path':str(self.media),'consent':True},'wrong')]:
            with self.assertRaises(urllib.error.HTTPError) as caught:post(body,token)
            caught.exception.close()
        self.assertEqual(self.catalog.index.roots(),[])
        with post({'path':str(self.media),'consent':True}) as response:self.assertEqual(response.status,200)

    def test_state_epoch_increments_only_on_successful_mutations(self):
        epoch_before = self.catalog._state_epoch
        # sync_index increments epoch
        self.catalog.sync_index()
        self.assertEqual(self.catalog._state_epoch, epoch_before + 1)
        # Invalid add_root does not increment epoch
        with self.assertRaises(ValueError):
            self.catalog.add_root(str(self.base))
        self.assertEqual(self.catalog._state_epoch, epoch_before + 1)
        # Successful add_root increments epoch
        root = self.catalog.add_root(str(self.media))
        self.assertEqual(self.catalog._state_epoch, epoch_before + 2)
        # Invalid set_excludes does not increment epoch
        with self.assertRaises(KeyError):
            self.catalog.set_excludes(999999, ['bad'])
        self.assertEqual(self.catalog._state_epoch, epoch_before + 2)
        # Successful set_excludes increments epoch
        self.catalog.set_excludes(root, ['*.cbz'])
        self.assertEqual(self.catalog._state_epoch, epoch_before + 3)
        # Invalid unregister_root does not increment epoch
        with self.assertRaises(ValueError):
            self.catalog.unregister_root(999999)
        self.assertEqual(self.catalog._state_epoch, epoch_before + 3)
        # Successful unregister_root increments epoch
        self.catalog.unregister_root(root)
        self.assertEqual(self.catalog._state_epoch, epoch_before + 4)
        # Invalid purge without consent does not increment epoch
        with self.assertRaises(ValueError):
            self.catalog.purge_inactive_root(root, consent=False)
        self.assertEqual(self.catalog._state_epoch, epoch_before + 4)
        # Successful purge_inactive_root increments epoch
        self.catalog.purge_inactive_root(root, consent=True)
        self.assertEqual(self.catalog._state_epoch, epoch_before + 5)

if __name__=='__main__':unittest.main()
