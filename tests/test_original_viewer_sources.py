"""Viewer-original reads preserve bytes, scopes and freshness independently of AI limits."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import zipfile
from http.server import ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'));sys.path.insert(0,str(ROOT/'tools'))
from production import ProductionCatalog
from production_server import production_handler,DisabledAI
from previews import PreviewReader,PreviewUnavailable,ReaderChanged,MAX_IMAGE_BYTES,MAX_LARGE_IMAGE_BYTES
from create_preview_fixture import png

class OriginalViewerSources(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.media=self.base/'media';self.media.mkdir()
        self.catalog=ProductionCatalog(self.base/'catalog.sqlite');self.root=self.catalog.add_root(str(self.media));self.reader=PreviewReader(self.catalog)
    def tearDown(self):self.catalog.close();self.temp.cleanup()
    def scan(self):
        self.catalog.index.scan(self.root);self.catalog.sync_index()
        return {row['title']:row['id'] for row in self.catalog.search()['items']}
    def test_original_bytes_and_old_preview_contract(self):
        # Large transport fixture, not a quality/decoding claim.
        data=png()+b'\0'*(MAX_IMAGE_BYTES+1)
        source=self.media/'large.png';source.write_bytes(data);before=(source.read_bytes(),source.stat().st_mtime_ns)
        item=self.scan()['large.png']
        self.assertEqual(self.reader.read_original(item),(data,'image/png'))
        self.assertEqual(before,(source.read_bytes(),source.stat().st_mtime_ns))
        self.assertEqual(len(list(self.media.iterdir())),1)
    def test_original_budget_rejects_before_read(self):
        p=self.media/'too-big.png'
        with p.open('wb') as stream:stream.truncate(MAX_LARGE_IMAGE_BYTES+1)
        with self.assertRaises(PreviewUnavailable):self.reader.read_original(self.scan()['too-big.png'])
    def test_original_source_freshness_and_exclusion(self):
        p=self.media/'image.png';p.write_bytes(png());item=self.scan()['image.png']
        self.catalog.set_excludes(self.root,['*.png'])
        with self.assertRaises(PreviewUnavailable):self.reader.read_original(item)
        self.catalog.set_excludes(self.root,[]);p.write_bytes(png(color=(1,2,3))+b'changed')
        with self.assertRaises(ReaderChanged):self.reader.read_original(item)
    def test_original_archive_page_and_unchanged_legacy_budget(self):
        data=png()+b'\0'*(MAX_IMAGE_BYTES+1)
        with zipfile.ZipFile(self.media/'book.cbz','w',compression=zipfile.ZIP_STORED) as book:book.writestr('p1.png',data)
        item=self.scan()['book.cbz'];revision=self.reader.manifest(item)['revision']
        with self.assertRaises(PreviewUnavailable):self.reader.read_page(item,0,revision)
        self.assertEqual(self.reader.read_page(item,0,revision,original=True),(data,'image/png'))
        with self.assertRaises(ReaderChanged):self.reader.read_page(item,0,'0'*64,original=True)
    def test_original_folder_book(self):
        p=self.media/'p1.png';data=png()+b'\0'*(MAX_IMAGE_BYTES+1);p.write_bytes(data)
        self.catalog.unregister_root(self.root)
        self.catalog.add_root(str(self.media),folder_books=True)
        items=self.scan();item=next(iter(items.values()));revision=self.reader.manifest(item)['revision']
        self.assertEqual(self.reader.read_page(item,0,revision,original=True),(data,'image/png'))
        with self.assertRaises(PreviewUnavailable):self.reader.read_page(item,0,revision)
    def test_original_api_auth_and_revision(self):
        p=self.media/'image.png';data=png();p.write_bytes(data)
        with zipfile.ZipFile(self.media/'book.cbz','w') as book:book.writestr('p.png',data)
        ids=self.scan();revision=self.reader.manifest(ids['book.cbz'])['revision']
        handler=production_handler(self.catalog,'generated-test-token',ai=DisabledAI());handler.log_message=lambda *args:None
        server=ThreadingHTTPServer(('127.0.0.1',0),handler);worker=threading.Thread(target=server.serve_forever);worker.start()
        def request(path,token='generated-test-token'):
            req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,headers={'X-Aredoko-Token':token})
            return urllib.request.urlopen(req,timeout=10)
        try:
            image=f"/api/library/preview/{ids['image.png']}/original"
            page=f"/api/library/reader/{ids['book.cbz']}/original/0"
            with request(image) as response:self.assertEqual(response.read(),data)
            with request(page+'?revision='+revision) as response:self.assertEqual(response.read(),data)
            for path,token,code in ((image,'wrong',403),(image+'?unexpected=1','generated-test-token',400),(page,'generated-test-token',400),(page+'?revision='+'0'*64,'generated-test-token',409)):
                with self.assertRaises(urllib.error.HTTPError) as caught:request(path,token)
                self.assertEqual(caught.exception.code,code);caught.exception.close()
            self.catalog.unregister_root(self.root)
            with self.assertRaises(urllib.error.HTTPError) as caught:request(image)
            self.assertEqual(caught.exception.code,404);caught.exception.close()
        finally:server.shutdown();server.server_close();worker.join(5)

if __name__=='__main__':unittest.main()
