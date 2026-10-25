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

    def test_scan_modes_separation_and_ai_hook(self):
        root1 = self.catalog.add_root(str(self.media))
        media2 = self.base / 'media2'; media2.mkdir()
        (media2 / 'item2.png').write_bytes(b'media2 item')
        root2 = self.catalog.add_root(str(media2))
        self.fixture('item1.png')

        # 1. Invalid mode is rejected
        with self.assertRaises(ValueError) as ctx:
            self.catalog.start_scan(root1, mode='bad_mode')
        self.assertIn('Invalid scan mode', str(ctx.exception))

        # Invalid root combinations (both or neither)
        with self.assertRaises(ValueError):
            self.catalog.start_scan()
        with self.assertRaises(ValueError):
            self.catalog.start_scan(root1, root_ids=[root1])

        # 2. Legacy start_scan(root) defaults to mode='list' and makes 0 calls to spy on ai
        class SpyAI:
            def __init__(self):
                self.calls = []
                self.cancelled = False
            def status(self):
                return {'available': True, 'state': 'running' if self.calls else 'idle',
                        'processed': 5, 'total': 10, 'error': ''}
            def start(self, *args, **kwargs):
                self.calls.append((args, kwargs))
            def cancel_build(self):
                self.cancelled = True
                return {'cancel_requested': True}

        spy = SpyAI()
        server = ThreadingHTTPServer(('127.0.0.1', 0), production_handler(self.catalog, 'token', ai=spy))
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        origin = f'http://127.0.0.1:{server.server_port}'

        def post_scan(body, token='token'):
            req = urllib.request.Request(
                origin + '/api/library/scan',
                json.dumps(body).encode(),
                headers={'Origin': origin, 'X-Aredoko-Token': token, 'Content-Type': 'application/json'}
            )
            return urllib.request.urlopen(req)

        def get_scan(token='token'):
            req = urllib.request.Request(
                origin + '/api/library/scan',
                headers={'Origin': origin, 'X-Aredoko-Token': token}
            )
            return urllib.request.urlopen(req)

        # HTTP: invalid mode is rejected with 400
        with self.assertRaises(urllib.error.HTTPError) as err:
            post_scan({'root_id': root1, 'mode': 'invalid'})
        self.assertEqual(err.exception.code, 400)
        self.assertEqual(json.loads(err.exception.read())['error'], 'Invalid scan mode')

        # HTTP: unknown fields rejected
        with self.assertRaises(urllib.error.HTTPError) as err:
            post_scan({'root_id': root1, 'extra': 123})
        self.assertEqual(err.exception.code, 400)

        # HTTP: POST without mode defaults to 'list'
        with post_scan({'root_id': root1}) as resp:
            data = json.load(resp)
            self.assertEqual(data['mode'], 'list')
            self.assertEqual(data['root_ids'], [root1])

        self.catalog._worker.join(10)
        self.assertFalse(self.catalog._worker.is_alive())
        self.assertEqual(len(spy.calls), 0)  # 0 calls to AI
        st = self.catalog.scan_state()
        self.assertEqual(st['mode'], 'list')
        self.assertEqual(st['stage'], 'complete')
        self.assertEqual(st['ai_state'], 'none')
        self.assertEqual(self.catalog.search()['total'], 1)

        # 3. mode='list_and_ai' invokes ai.start after list scan succeeds
        with post_scan({'root_id': root1, 'mode': 'list_and_ai'}) as resp:
            data = json.load(resp)
            self.assertEqual(data['mode'], 'list_and_ai')
            self.assertEqual(data['stage'], 'list')
        self.catalog._worker.join(10)
        self.assertFalse(self.catalog._worker.is_alive())
        self.assertEqual(len(spy.calls), 1)  # Invoked ai.start
        st = self.catalog.scan_state()
        self.assertEqual(st['mode'], 'list_and_ai')
        self.assertEqual(st['stage'], 'ai')
        self.assertEqual(st['ai_state'], 'running')

        with get_scan() as resp:
            http_st = json.load(resp)
            self.assertEqual(http_st['stage'], 'ai')
            self.assertEqual(http_st['ai_processed'], 5)
            self.assertEqual(http_st['ai_total'], 10)

        # Cancel while in stage 'ai' cancels build
        def post_cancel():
            req = urllib.request.Request(
                origin + '/api/library/cancel',
                b'{}',
                headers={'Origin': origin, 'X-Aredoko-Token': 'token', 'Content-Type': 'application/json'}
            )
            return urllib.request.urlopen(req)

        with post_cancel() as resp:
            cancel_data = json.load(resp)
            self.assertTrue(cancel_data['cancel_requested'])
            self.assertTrue(cancel_data.get('ai_cancel_requested', False))
            self.assertTrue(spy.cancelled)

        # 4. mode='list_and_ai' when AI is unavailable / fails: keeps list items
        from production_server import DisabledAI
        server2 = ThreadingHTTPServer(('127.0.0.1', 0), production_handler(self.catalog, 'token', ai=DisabledAI()))
        worker2 = threading.Thread(target=server2.serve_forever, daemon=True); worker2.start()
        self.addCleanup(server2.server_close); self.addCleanup(server2.shutdown)
        origin2 = f'http://127.0.0.1:{server2.server_port}'

        req2 = urllib.request.Request(
            origin2 + '/api/library/scan',
            json.dumps({'root_id': root1, 'mode': 'list_and_ai'}).encode(),
            headers={'Origin': origin2, 'X-Aredoko-Token': 'token', 'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req2) as resp:
            data = json.load(resp)
            self.assertEqual(data['mode'], 'list_and_ai')
        self.catalog._worker.join(10)
        st = self.catalog.scan_state()
        self.assertEqual(st['state'], 'complete')  # list items committed!
        self.assertEqual(st['ai_state'], 'failed')
        self.assertTrue(st['ai_error'])
        self.assertEqual(self.catalog.search()['total'], 1)  # list items not rolled back

        # 5. Multi-root scanning [root1, root2]
        with post_scan({'root_ids': [root1, root2], 'mode': 'list'}) as resp:
            data = json.load(resp)
            self.assertEqual(data['root_ids'], [root1, root2])
        self.catalog._worker.join(10)
        self.assertEqual(self.catalog.search()['total'], 2)
        st = self.catalog.scan_state()
        self.assertEqual(st['root_ids'], [root1, root2])

        # 6. Cancelling during list scan rolls back partial scan and never calls AI
        for i in range(110):
            (self.media / f'extra_{i}.png').write_bytes(b'extra')
        spy.calls.clear()
        self.catalog.start_scan(root_ids=[root1], mode='list_and_ai')
        self.catalog._cancel.set()
        self.catalog._worker.join(10)
        st = self.catalog.scan_state()
        self.assertEqual(st['state'], 'cancelled')
        self.assertEqual(st['ai_state'], 'cancelled')
        self.assertEqual(len(spy.calls), 0)  # Never called AI!

if __name__=='__main__':unittest.main()
