"""Reading progress contracts using generated archives and isolated DBs only."""
import json,threading,unittest,urllib.request,urllib.error,zipfile
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import test_reader as fixtures
from production import ProductionCatalog,ScanBusyError
from production_server import production_handler,DisabledAI
from previews import PreviewReader,ReaderChanged,PreviewUnavailable,PreviewBusyError
from create_preview_fixture import png

class ProgressTests(unittest.TestCase):
    setUp=fixtures.ReaderTests.setUp
    index=fixtures.ReaderTests.index
    book=fixtures.ReaderTests.book
    def saved(self,item,page=1,mode='rtl'):
        return {'revision':self.reader.manifest(item)['revision'],'page':page,'mode':mode}
    def test_restart_isolation_metadata_source_unchanged(self):
        source,item=self.book();_,other=self.book('other.zip')
        before=source.read_bytes(),source.stat().st_mtime_ns
        self.catalog.update([item],{'tags':['keep'],'favorite':True,'shelf':'keep'})
        value=self.saved(item);self.assertEqual(self.catalog.reader_progress(item),{'progress':None})
        self.assertEqual(self.catalog.save_reader_progress(item,value,self.reader),{'saved':True})
        restarted=ProductionCatalog(self.catalog.path)
        try:
            self.assertEqual(restarted.reader_progress(item),{'progress':value})
            self.assertEqual(restarted.reader_progress(other),{'progress':None})
            self.assertEqual(restarted.get(item)['tags'],['keep']);self.assertEqual(restarted.get(item)['shelf'],'keep')
        finally:restarted.close()
        self.assertEqual(before,(source.read_bytes(),source.stat().st_mtime_ns))
    def test_bad_payload_does_not_replace_saved(self):
        _,item=self.book();value=self.saved(item);self.catalog.save_reader_progress(item,value,self.reader)
        for bad in [None,[],{},dict(value,extra=True),dict(value,page=True),dict(value,page=-1),dict(value,page=10000),dict(value,page=2),dict(value,page=1.5),dict(value,mode='unknown'),dict(value,revision='z'*64)]:
            with self.assertRaises(ValueError):self.catalog.save_reader_progress(item,bad,self.reader)
            self.assertEqual(self.catalog.reader_progress(item),{'progress':value})
        for bad in [True,0,-1,9223372036854775808]:
            with self.assertRaises(ValueError):self.catalog.reader_progress(bad)
            with self.assertRaises(ValueError):self.catalog.save_reader_progress(bad,value,self.reader)
    def test_revision_replacement_and_stale_write_rejected(self):
        source,item=self.book();old=self.saved(item);self.catalog.save_reader_progress(item,old,self.reader)
        with zipfile.ZipFile(source,'a') as z:z.writestr('page1.png',png())
        with self.assertRaises(ReaderChanged):self.catalog.save_reader_progress(item,old,self.reader)
        self.index();new=self.saved(item,page=2,mode='ltr');self.catalog.save_reader_progress(item,new,self.reader)
        with self.assertRaises(ReaderChanged):self.catalog.save_reader_progress(item,old,self.reader)
        self.assertEqual(self.catalog.reader_progress(item),{'progress':new})
    def test_inactive_and_excluded_root_retains_state_for_restore(self):
        _,item=self.book();value=self.saved(item);self.catalog.save_reader_progress(item,value,self.reader)
        self.catalog.unregister_root(self.root)
        with self.assertRaises(KeyError):self.catalog.reader_progress(item)
        with self.assertRaises(PreviewUnavailable):self.catalog.save_reader_progress(item,value,self.reader)
        self.root=self.catalog.add_root(str(self.media));self.index();self.assertEqual(self.catalog.reader_progress(item),{'progress':value})
        self.catalog.set_excludes(self.root,['*.cbz'])
        with self.assertRaises(KeyError):self.catalog.reader_progress(item)
        with self.assertRaises(PreviewUnavailable):self.catalog.save_reader_progress(item,value,self.reader)
    def test_scan_and_worker_busy_preserve_old(self):
        _,item=self.book();value=self.saved(item);self.catalog.save_reader_progress(item,value,self.reader)
        with patch.object(self.catalog,'_require_idle',side_effect=ScanBusyError):
            with self.assertRaises(ScanBusyError):self.catalog.save_reader_progress(item,dict(value,page=0),self.reader)
        with patch.object(self.reader,'manifest',side_effect=PreviewBusyError):
            with self.assertRaises(PreviewBusyError):self.catalog.save_reader_progress(item,dict(value,page=0),self.reader)
        self.assertEqual(self.catalog.reader_progress(item),{'progress':value})
    def test_non_archive_missing_and_legacy_db(self):
        (self.media/'image.png').write_bytes(png());item=self.index()['image.png']
        with self.assertRaises(KeyError):self.catalog.reader_progress(item)
        with self.assertRaises(KeyError):self.catalog.reader_progress(9223372036854775807)
        with self.catalog.connect() as db:db.execute('DROP TABLE reader_progress')
        restarted=ProductionCatalog(self.catalog.path)
        try:
            _,book=self.book();self.assertEqual(restarted.reader_progress(book),{'progress':None})
        finally:restarted.close()
    def test_http_token_origin_routes_body_stale_and_busy(self):
        _,item=self.book();value=self.saved(item);server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'progress-token',ai=DisabledAI()))
        t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
        self.addCleanup(server.server_close);self.addCleanup(t.join,5);self.addCleanup(server.shutdown)
        origin=f'http://127.0.0.1:{server.server_port}';route=f'/api/library/reader/{item}/progress'
        def request(path=route,body=None,token='progress-token',given_origin=origin,host=None):
            headers={'X-Aredoko-Token':token,'Origin':given_origin,'Content-Type':'application/json'}
            if host:headers['Host']=host
            req=urllib.request.Request(origin+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
            try:
                with urllib.request.urlopen(req) as reply:return reply.status,json.load(reply),reply.headers['Cache-Control']
            except urllib.error.HTTPError as ex:
                with ex:return ex.code,json.load(ex),ex.headers['Cache-Control']
        self.assertEqual(request()[1],{'progress':None});self.assertEqual(request(body=value)[0],200)
        self.assertEqual(request()[1],{'progress':value});self.assertEqual(request()[2],'no-store')
        self.assertEqual(request(token='wrong')[0],403);self.assertEqual(request(body=value,token='wrong')[0],403)
        self.assertEqual(request(body=value,given_origin='https://example.com')[0],403);self.assertEqual(request(host='example.com')[0],403)
        for path in [route+'?x=y','/api/library/reader/9999999999999999999/progress','/api/library/reader/0/progress',route+'/extra']:
            self.assertEqual(request(path,body=value)[0],400,path)
        self.assertEqual(request(body=dict(value,page=True))[0],400)
        self.assertEqual(request(body=dict(value,revision='a'*64))[0],409)
        with patch.object(PreviewReader,'manifest',side_effect=PreviewBusyError):self.assertEqual(request(body=value)[0],503)
        with patch.object(self.catalog,'_require_idle',side_effect=ScanBusyError):self.assertEqual(request(body=value)[0],409)
        self.assertEqual(request()[1],{'progress':value})

if __name__=='__main__':unittest.main()
