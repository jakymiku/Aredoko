"""Registered scope, initial metadata, and reversible unregistration contracts."""
import hashlib,json,sys,tempfile,threading,unittest,urllib.error,urllib.request
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from production import ProductionCatalog,ScanBusyError
from production_server import production_handler,DisabledAI
from previews import PreviewReader,PreviewUnavailable
from create_holdout_fixture import graphic

class FolderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.a=self.base/'a';self.b=self.base/'b';self.a.mkdir();self.b.mkdir()
        self.db=self.base/'catalog.sqlite';self.catalog=ProductionCatalog(self.db);self.addCleanup(self.catalog.close)
    def scan(self,root):
        self.catalog.start_scan(root);self.catalog._worker.join(10)
        self.assertEqual(self.catalog.scan_state()['state'],'complete')
    def file(self,folder,name='image.png'):
        path=folder/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(graphic({'background':'white','objects':[]}));return path
    def test_scope_filters_before_count_paging_and_includes_subfolders(self):
        for i in range(67):self.file(self.a,f'sub/same-{i:02}.png')
        self.file(self.b,'same-other.png')
        a=self.catalog.add_root(str(self.a));b=self.catalog.add_root(str(self.b));self.scan(a);self.scan(b)
        result=self.catalog.search('same',root_id=a,page=1)
        self.assertEqual((result['total'],len(result['items'])),(67,7))
        self.assertTrue(all(row['root_id']==a for row in result['items']))
        self.assertEqual(self.catalog.search()['total'],68)
        self.assertEqual(self.catalog.search(root_id=b)['total'],1)
        self.catalog.update([self.catalog.search(root_id=b)['items'][0]['id']],{'favorite':True})
        self.assertEqual(self.catalog.search(root_id=a,view='favorites')['total'],0)
    def test_initial_shelf_new_files_only_and_manual_clear_survives_restart(self):
        self.file(self.a,'one.png');self.file(self.a,'two.png')
        root=self.catalog.add_root(str(self.a),default_shelf=' AI画像 ');self.scan(root)
        rows=self.catalog.search()['items'];self.assertEqual({r['shelf'] for r in rows},{'AI画像'})
        self.catalog.update([rows[0]['id']],{'shelf':'手動棚','tags':['確定'],'favorite':True})
        self.catalog.update([rows[1]['id']],{'shelf':''});self.file(self.a,'three.png');self.scan(root)
        self.assertEqual(self.catalog.get(rows[0]['id'])['shelf'],'手動棚')
        self.assertEqual(self.catalog.get(rows[1]['id'])['shelf'],'')
        self.assertEqual(next(r for r in self.catalog.search()['items'] if r['title']=='three.png')['shelf'],'AI画像')
        self.catalog.close();reopened=ProductionCatalog(self.db)
        try:self.assertEqual(reopened.get(rows[0]['id'])['tags'],['確定']);self.assertEqual(reopened.get(rows[1]['id'])['shelf'],'')
        finally:reopened.close()
    def test_shelves_include_unscanned_roots_and_existing_items(self):
        self.catalog.add_root(str(self.a),default_shelf='AI画像')
        self.assertEqual(self.catalog.shelves(),['AI画像'])
        self.file(self.b);root=self.catalog.add_root(str(self.b),default_shelf='AI画像');self.scan(root)
        self.catalog.update([self.catalog.search()['items'][0]['id']],{'shelf':'その他'})
        self.assertEqual(set(self.catalog.shelves()),{'AI画像','その他'})
    def test_invalid_root_and_initial_shelf_never_register_or_broaden(self):
        for bad in (None,True,81*'a',[] ):
            with self.assertRaises(ValueError):self.catalog.add_root(str(self.a),default_shelf=bad)
        self.assertEqual(self.catalog.index.roots(),[])
        for bad in (True,0,-1,10**30,'1',999):
            with self.assertRaises(ValueError):self.catalog.search(root_id=bad)
    def test_related_and_partial_fallback_stay_within_selected_root(self):
        self.file(self.a,'reimu.png');self.file(self.b,'東方-巫女.png')
        a=self.catalog.add_root(str(self.a));b=self.catalog.add_root(str(self.b));self.scan(a);self.scan(b)
        row=self.catalog.search(root_id=a)['items'][0];self.catalog.update([row['id']],{'tags':['博麗霊夢']})
        self.catalog.terms.upsert({'term':'博麗霊夢','aliases':[],'related':['東方','巫女']})
        result=self.catalog.search('東方 巫女',root_id=a)
        self.assertEqual(result['items'][0]['match'],'related');self.assertEqual(result['total'],1)
        result=self.catalog.search('東方 宇宙',root_id=a)
        self.assertEqual(result['items'][0]['match'],'partial');self.assertTrue(all(r['root_id']==a for r in result['items']))
    def test_unregister_hides_search_and_preview_then_restores_metadata(self):
        file=self.file(self.a);before=(file.stat().st_mtime_ns,hashlib.sha256(file.read_bytes()).hexdigest())
        root=self.catalog.add_root(str(self.a),default_shelf='AI画像');self.scan(root);row=self.catalog.search()['items'][0]
        self.catalog.update([row['id']],{'tags':['手動'],'shelf':'保存棚','favorite':True})
        reader=PreviewReader(self.catalog);reader.read(row['id'])
        self.catalog.unregister_root(root)
        self.assertEqual(self.catalog.index.roots(),[]);self.assertEqual(self.catalog.search()['total'],0)
        with self.assertRaises(PreviewUnavailable):reader.read(row['id'])
        with self.assertRaises(ValueError):self.catalog.search(root_id=root)
        self.assertEqual(self.catalog.add_root(str(self.a),default_shelf='別の初期棚'),root);self.scan(root)
        restored=self.catalog.search()['items'][0]
        self.assertEqual((restored['id'],restored['tags'],restored['shelf'],restored['favorite']),(row['id'],['手動'],'保存棚',True))
        self.assertEqual((file.stat().st_mtime_ns,hashlib.sha256(file.read_bytes()).hexdigest()),before)
    def test_unregister_rejected_while_scanning_and_restore_checks_overlap(self):
        root=self.catalog.add_root(str(self.a));worker=Mock();worker.is_alive.return_value=True;self.catalog._worker=worker
        with self.assertRaises(ScanBusyError):self.catalog.unregister_root(root)
        self.assertEqual(len(self.catalog.index.roots()),1)
        self.catalog._worker=None;self.catalog.unregister_root(root);child=self.a/'child';child.mkdir();self.catalog.add_root(str(child))
        with self.assertRaises(ValueError):self.catalog.add_root(str(self.a))
        self.assertEqual(len(self.catalog.index.roots()),1)
    def test_shelf_edit_requires_explicit_fill_and_preserves_nonempty_metadata(self):
        self.file(self.a,'one.png');self.file(self.a,'two.png');self.file(self.b)
        a=self.catalog.add_root(str(self.a));b=self.catalog.add_root(str(self.b));self.scan(a);self.scan(b)
        rows=self.catalog.search(root_id=a)['items'];self.catalog.update([rows[0]['id']],{'shelf':'個別棚','tags':['手動'],'favorite':True})
        self.assertEqual(self.catalog.set_root_shelf(a,'AI画像')['updated'],0)
        self.assertEqual(self.catalog.get(rows[1]['id'])['shelf'],'')
        self.assertEqual(self.catalog.set_root_shelf(a,'AI画像',True)['updated'],1)
        self.assertEqual(self.catalog.get(rows[0]['id'])['shelf'],'個別棚')
        self.assertEqual(self.catalog.search(root_id=b)['items'][0]['shelf'],'')
        self.file(self.a,'three.png');self.scan(a)
        self.assertEqual(next(r for r in self.catalog.search(root_id=a)['items'] if r['title']=='three.png')['shelf'],'AI画像')
        with self.assertRaises(ValueError):self.catalog.set_root_shelf(a,'x',1)
        self.catalog.unregister_root(a)
        with self.assertRaises(ValueError):self.catalog.set_root_shelf(a,'x')
        active=self.catalog.index.roots();history=self.catalog.index.roots(include_inactive=True)
        self.assertEqual((len(active),len(history)),(1,2));self.assertEqual(next(r for r in history if r['id']==a)['enabled'],0)
    def test_shelf_and_inactive_routes_keep_authentication(self):
        self.file(self.a);root=self.catalog.add_root(str(self.a));self.scan(root)
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'test-token',ai=DisabledAI()))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        origin=f'http://127.0.0.1:{server.server_port}'
        req=urllib.request.Request(origin+'/api/library/roots/shelf',json.dumps({'root_id':root,'shelf':'AI画像','fill_unset':True}).encode(),headers={'Origin':origin,'X-Aredoko-Token':'test-token'})
        with urllib.request.urlopen(req) as response:self.assertEqual(json.load(response)['updated'],1)
        self.catalog.unregister_root(root)
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(origin+'/api/library/roots?include_inactive=1')
        self.assertEqual(error.exception.code,403);error.exception.close()
        req=urllib.request.Request(origin+'/api/library/roots?include_inactive=1',headers={'X-Aredoko-Token':'test-token'})
        with urllib.request.urlopen(req) as response:self.assertEqual(json.load(response)['items'][0]['enabled'],0)

    def test_old_schema_is_additively_migrated(self):
        import sqlite3
        old=self.base/'old.sqlite'
        with closing(sqlite3.connect(old)) as db:
            db.execute('CREATE TABLE library_roots(id INTEGER PRIMARY KEY,path TEXT UNIQUE,excludes_json TEXT,created_at TEXT,last_scanned_at TEXT)')
            db.execute('INSERT INTO library_roots VALUES(1,?,\'[]\',\'old\',NULL)',(str(self.a),))
            db.commit()
        migrated=ProductionCatalog(old)
        try:self.assertEqual(migrated.index.roots()[0]['default_shelf'],'');self.assertEqual(migrated.index.roots()[0]['enabled'],1)
        finally:migrated.close()
    def test_http_root_filter_shelf_and_unregister_auth(self):
        self.file(self.a);self.file(self.b);a=self.catalog.add_root(str(self.a));b=self.catalog.add_root(str(self.b));self.scan(a);self.scan(b)
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'test-token',ai=DisabledAI()))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        origin=f'http://127.0.0.1:{server.server_port}'
        with urllib.request.urlopen(origin+f'/api/items?root_id={a}') as response:self.assertEqual(json.load(response)['total'],1)
        for query in ('root_id=','root_id=0','root_id=1&root_id=2','root_id=999','root_id=9999999999999999999'):
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(origin+'/api/items?'+query)
            self.assertEqual(error.exception.code,400);error.exception.close()
        body=json.dumps({'root_id':a}).encode()
        req=urllib.request.Request(origin+'/api/library/roots/unregister',body,headers={'Origin':origin,'X-Aredoko-Token':'wrong'})
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
        self.assertEqual(error.exception.code,403);error.exception.close();self.assertEqual(self.catalog.search()['total'],2)
        req.headers['X-aredoko-token']='test-token'
        with urllib.request.urlopen(req) as response:self.assertEqual(json.load(response)['unregistered'],a)
        self.assertEqual(self.catalog.search()['total'],1)

if __name__=='__main__':unittest.main()
