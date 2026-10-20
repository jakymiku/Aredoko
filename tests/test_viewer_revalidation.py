"""Generated originals and conditional reads retain source/access guards."""
import io
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tools')]
from production import ProductionCatalog
from production_server import production_handler,DisabledAI
from previews import PreviewReader,PreviewUnavailable,ReaderChanged
from create_preview_fixture import png


class ViewerRevalidationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.media=self.base/'media';self.media.mkdir()
        self.catalog=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.catalog.close)
        self.root=self.catalog.add_root(str(self.media));self.reader=PreviewReader(self.catalog)
        (self.media/'image.png').write_bytes(png())
        with zipfile.ZipFile(self.media/'book.cbz','w') as book:
            book.writestr('p1.png',png());book.writestr('p2.png',png(color=(4,5,6)))
        self.ids=self.scan();self.item=self.ids['image.png'];self.book=self.ids['book.cbz']
        self.revision=self.reader.manifest(self.book)['revision']

    def scan(self):
        self.catalog.index.scan(self.root);self.catalog.sync_index()
        return {row['title']:row['id'] for row in self.catalog.search()['items']}

    def test_image_validator_is_stable_and_body_is_omitted_only_after_recheck(self):
        data,mime,tag=self.reader.original_source(self.item)
        self.assertEqual((data,mime),(png(),'image/png'));self.assertRegex(tag,r'^W/"[0-9a-f]{64}"$')
        self.assertEqual(self.reader.original_source(self.item,tag),(None,mime,tag))
        self.assertEqual(self.reader.original_source(self.item,'W/"'+'0'*64+'"'),(data,mime,tag))

    def test_archive_304_skips_decompression_but_validates_directory_and_bounds(self):
        data,mime,tag=self.reader.page_source(self.book,0,self.revision)
        with patch.object(zipfile.ZipFile,'open',side_effect=AssertionError('must not decompress')):
            self.assertEqual(self.reader.page_source(self.book,0,self.revision,tag),(None,mime,tag))
        other,_,other_tag=self.reader.page_source(self.book,1,self.revision,tag)
        self.assertEqual(other,png(color=(4,5,6)));self.assertNotEqual(other_tag,tag)
        with self.assertRaises(PreviewUnavailable):self.reader.page_source(self.book,9,self.revision,tag)
        with self.assertRaises(ReaderChanged):self.reader.page_source(self.book,0,'0'*64,tag)

    def test_unchanged_size_mtime_still_detects_replaced_image(self):
        original=self.media/'image.png';info=original.stat();_,_,tag=self.reader.original_source(self.item)
        replacement=self.media/'replacement.tmp';replacement.write_bytes(original.read_bytes());replacement.replace(original)
        os.utime(original,ns=(info.st_atime_ns,info.st_mtime_ns))
        data,_,current=self.reader.original_source(self.item,tag)
        self.assertEqual(data,png());self.assertNotEqual(current,tag)

    def test_cached_validator_does_not_authorize_excluded_or_unregistered_source(self):
        _,_,tag=self.reader.original_source(self.item)
        self.catalog.set_excludes(self.root,['*.png'])
        with self.assertRaises(PreviewUnavailable):self.reader.original_source(self.item,tag)
        self.catalog.set_excludes(self.root,[]);self.catalog.unregister_root(self.root)
        with self.assertRaises(PreviewUnavailable):self.reader.original_source(self.item,tag)

    def test_missing_and_modified_source_do_not_return_304(self):
        _,_,tag=self.reader.original_source(self.item)
        (self.media/'image.png').write_bytes(png()+b'changed')
        with self.assertRaises(ReaderChanged):self.reader.original_source(self.item,tag)
        (self.media/'image.png').unlink()
        with self.assertRaises((PreviewUnavailable,OSError)):self.reader.original_source(self.item,tag)

    def test_post_read_ancestor_check_runs_for_304(self):
        _,_,tag=self.reader.original_source(self.item)
        original=Path.stat;calls=0
        def swapped(path,*args,**kwargs):
            nonlocal calls
            if path==self.media and kwargs.get('follow_symlinks') is False:
                calls+=1
                if calls>=2:return SimpleNamespace(st_mode=0o40700,st_file_attributes=0x400)
            return original(path,*args,**kwargs)
        with patch.object(Path,'stat',new=swapped):
            with self.assertRaises(ReaderChanged):self.reader.original_source(self.item,tag)

    def folder_book(self):
        self.catalog.unregister_root(self.root)
        folder=self.base/'folder';folder.mkdir();(folder/'p1.png').write_bytes(png())
        self.root=self.catalog.add_root(str(folder),folder_books=True);self.media=folder
        item=next(iter(self.scan().values()))
        return item,self.reader.manifest(item)['revision']

    def test_folder_page_replacement_invalidates_even_when_book_signature_matches(self):
        item,revision=self.folder_book();data,mime,tag=self.reader.page_source(item,0,revision)
        self.assertEqual(self.reader.page_source(item,0,revision,tag),(None,mime,tag))
        original=self.media/'p1.png';info=original.stat()
        replacement=self.media/'replacement.tmp';replacement.write_bytes(data);replacement.replace(original)
        os.utime(original,ns=(info.st_atime_ns,info.st_mtime_ns))
        self.assertEqual(self.reader.manifest(item)['revision'],revision)
        current,_,new_tag=self.reader.page_source(item,0,revision,tag)
        self.assertEqual(current,data);self.assertNotEqual(new_tag,tag)

    def test_folder_post_check_and_unregistration_are_not_cached(self):
        item,revision=self.folder_book();_,_,tag=self.reader.page_source(item,0,revision)
        with patch('previews._check_folder',side_effect=ReaderChanged('generated race')):
            with self.assertRaises(ReaderChanged):self.reader.page_source(item,0,revision,tag)
        self.catalog.unregister_root(self.root)
        with self.assertRaises(PreviewUnavailable):self.reader.page_source(item,0,revision,tag)

    def test_invalid_validators_are_rejected_before_source_open(self):
        for tag in ('*','"'+'a'*64+'"','W/"'+'A'*64+'"','W/"short"','W/"'+'a'*64+'", W/"'+'b'*64+'"'):
            with self.subTest(tag=tag),patch('previews._safe_path',side_effect=AssertionError('must not open')):
                with self.assertRaises(ValueError):self.reader.original_source(self.item,tag)

    def test_http_contract_auth_and_stale_checks_on_conditional_reads(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'fixture-token',ai=DisabledAI()))
        worker=threading.Thread(target=server.serve_forever);worker.start()
        def request(path,tag=None,token='fixture-token'):
            headers={'X-Aredoko-Token':token}
            if tag is not None:headers['If-None-Match']=tag
            return urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,headers=headers),timeout=5)
        try:
            for route in (f'/api/library/preview/{self.item}/original',f'/api/library/reader/{self.book}/original/0?revision={self.revision}'):
                with request(route) as response:
                    self.assertEqual(response.read(),png());tag=response.headers['ETag']
                with self.assertRaises(urllib.error.HTTPError) as caught:request(route,tag)
                with caught.exception as response:
                    self.assertEqual(response.code,304);self.assertEqual(response.read(),b'');self.assertEqual(response.headers['ETag'],tag)
                    self.assertIsNone(response.headers.get('Content-Length'))
                for token,validator,expected in [('wrong',tag,403),('fixture-token','invalid',400)]:
                    with self.assertRaises(urllib.error.HTTPError) as caught:request(route,validator,token)
                    with caught.exception as response:self.assertEqual(response.code,expected)
            self.catalog.unregister_root(self.root)
            with self.assertRaises(urllib.error.HTTPError) as caught:request(route,tag)
            with caught.exception as response:self.assertEqual(response.code,404)
        finally:server.shutdown();server.server_close();worker.join(5)

    def test_apng_library_preview_uses_playback_frame_and_keeps_original(self):
        from PIL import Image
        output=io.BytesIO()
        Image.new('RGBA',(32,24),'black').save(output,format='PNG',save_all=True,
            append_images=[Image.new('RGBA',(32,24),'red'),Image.new('RGBA',(32,24),'blue')],
            default_image=True,duration=[80,120],loop=0)
        raw=output.getvalue();path=self.media/'poster.png';path.write_bytes(raw)
        item=self.scan()['poster.png'];before=path.stat().st_mtime_ns
        preview,_=self.reader.read(item)
        with Image.open(io.BytesIO(preview)) as image:
            self.assertEqual(image.getpixel((16,12)),(255,0,0,255))
            self.assertFalse(getattr(image,'is_animated',False))
        self.assertEqual(self.reader.read_original(item)[0],raw)
        self.assertEqual(path.read_bytes(),raw);self.assertEqual(path.stat().st_mtime_ns,before)


if __name__=='__main__':unittest.main()
