"""Bounded previews and mutation boundaries tested with fictional temp sources."""
import io
import json
import os
import stat
import struct
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'));sys.path.insert(0,str(ROOT/'tools'))
from production import ProductionCatalog, ScanBusyError
from previews import PreviewReader, PreviewUnavailable, ReaderChanged, _safe_path, MAX_IMAGE_BYTES, _zip_directory_limit
from production_server import production_handler
from create_preview_fixture import png

class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.media=self.base/'media';self.media.mkdir()
        self.catalog=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.catalog.close)
        self.root=self.catalog.add_root(str(self.media));self.reader=PreviewReader(self.catalog)
    def index(self):
        self.catalog.index.scan(self.root);self.catalog.sync_index()
        return {r['title']:r['id'] for r in self.catalog.search()['items']}
    def test_direct_image_is_readonly(self):
        path=self.media/'image.png';data=png();path.write_bytes(data)
        before=(path.read_bytes(),path.stat().st_mtime_ns)
        item=self.index()['image.png']
        self.assertEqual(self.reader.read(item),(data,'image/png'))
        self.assertEqual(before,(path.read_bytes(),path.stat().st_mtime_ns))
    def test_cbz_natural_first_page_and_no_extraction(self):
        path=self.media/'book.cbz';first=png(color=(30,80,120))
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('page10.png',png())
            archive.writestr('page2.png',first)
            archive.writestr('__MACOSX/page1.png',png())
        before=(path.read_bytes(),path.stat().st_mtime_ns)
        self.assertEqual(self.reader.read(self.index()['book.cbz']),(first,'image/png'))
        self.assertEqual(list(self.media.iterdir()),[path]);self.assertEqual(before,(path.read_bytes(),path.stat().st_mtime_ns))
    def test_zip_traversal_names_never_extract(self):
        path=self.media/'asset.zip'
        with zipfile.ZipFile(path,'w') as archive:archive.writestr('../../cover.png',png())
        self.reader.read(self.index()['asset.zip'])
        self.assertFalse((self.base/'cover.png').exists())
    def test_changed_file_requires_rescan(self):
        path=self.media/'image.png';path.write_bytes(png());item=self.index()['image.png']
        path.write_bytes(b'changed')
        with self.assertRaises(PreviewUnavailable):self.reader.read(item)
    def test_missing_excluded_and_unsupported(self):
        path=self.media/'image.png';path.write_bytes(png())
        (self.media/'file.pdf').write_bytes(b'fixture')
        ids=self.index()
        self.catalog.set_excludes(self.root,['*.png'])
        with self.assertRaises(PreviewUnavailable):self.reader.read(ids['image.png'])
        with self.assertRaises(PreviewUnavailable):self.reader.read(ids['file.pdf'])
        self.catalog.set_excludes(self.root,[]);path.unlink()
        with self.assertRaises(OSError):self.reader.read(ids['image.png'])
    def test_oversized_direct_image_rejected_before_read(self):
        from image_animations import MAX_LARGE_IMAGE_BYTES
        path=self.media/'big.png'
        with path.open('wb') as file:file.truncate(MAX_LARGE_IMAGE_BYTES+1)
        with self.assertRaises(PreviewUnavailable):self.reader.read(self.index()['big.png'])
        corrupt=self.media/'corrupt-10mb.png'
        with corrupt.open('wb') as file:file.truncate(MAX_IMAGE_BYTES+1)
        with self.assertRaises(PreviewUnavailable):self.reader.read(self.index()['corrupt-10mb.png'])
    def test_archive_bomb_is_rejected(self):
        with zipfile.ZipFile(self.media/'bomb.cbz','w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('page.png',b'0'*500000)
        with self.assertRaises(PreviewUnavailable):self.reader.read(self.index()['bomb.cbz'])
    def test_huge_directory_and_zip64_rejected_before_parse(self):
        for count,cd_size in [(1,5*1024*1024),(65535,0)]:
            end=struct.pack('<4s4H2IH',b'PK\x05\x06',0,0,count,count,cd_size,0,0)
            with self.assertRaises(PreviewUnavailable):_zip_directory_limit(io.BytesIO(end))
    def test_replaced_symlink_is_not_followed(self):
        path=self.media/'image.png';path.write_bytes(png());item=self.index()['image.png']
        outside=self.base/'private.png';outside.write_bytes(png())
        path.unlink()
        try:path.symlink_to(outside)
        except OSError:self.skipTest('symlink privilege unavailable')
        with self.assertRaises(PreviewUnavailable):self.reader.read(item)
    def test_concurrency_is_bounded(self):
        self.reader.slots.acquire();self.reader.slots.acquire()
        try:
            with self.assertRaises(PreviewUnavailable):self.reader.read(1)
        finally:self.reader.slots.release();self.reader.slots.release()
    def test_item_id_is_bounded_before_sqlite(self):
        for value in (True,0,-1,2**63,10**100,'1'):
            with self.subTest(value=value),self.assertRaises(PreviewUnavailable):self.reader.read(value)
    def test_http_preview_route_rejects_overflow_nested_and_ambiguous_ids(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'test-token'))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        prefix=f'http://127.0.0.1:{server.server_port}/api/library/preview/'
        for route in ('9223372036854775808','9'*40,'0','-1','01','nested/1','1/','1?path=elsewhere','%C2%B2'):
            request=urllib.request.Request(prefix+route,headers={'X-Aredoko-Token':'test-token'})
            with self.subTest(route=route),self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request,timeout=5)
            self.assertEqual(caught.exception.code,400)
            self.assertEqual(json.loads(caught.exception.read())['error'],'Invalid item');caught.exception.close()
    def test_scan_writes_fail_promptly_and_retry_preserves_annotation(self):
        (self.media/'image.png').write_bytes(png());item=self.index()['image.png']
        started=threading.Event();release=threading.Event();original=self.catalog.index.scan
        def slow(*args,**kwargs):
            started.set();release.wait(5);return original(*args,**kwargs)
        with patch.object(self.catalog.index,'scan',side_effect=slow):
            self.catalog.start_scan(self.root);self.assertTrue(started.wait(2))
            try:
                with self.assertRaises(ScanBusyError):self.catalog.update([item],{'tags':['retry']})
                with self.assertRaises(ScanBusyError):self.catalog.set_excludes(self.root,[])
                self.assertEqual(self.catalog.get(item)['tags'],[])
            finally:release.set();self.catalog._worker.join(5)
        self.catalog.update([item],{'tags':['retry']})
        self.assertEqual(self.catalog.get(item)['tags'],['retry'])
    def test_http_preview_requires_token_and_handles_corrupt_archive(self):
        (self.media/'image.png').write_bytes(png());(self.media/'bad.cbz').write_bytes(b'bad zip')
        ids=self.index();server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'test-token'))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        def request(item,token=None):
            headers={'X-Aredoko-Token':token} if token else {}
            return urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/library/preview/{item}',headers=headers))
        for item,token,status in [(ids['image.png'],None,403),(ids['bad.cbz'],'test-token',404)]:
            with self.assertRaises(urllib.error.HTTPError) as caught:request(item,token)
            self.assertEqual(caught.exception.code,status);caught.exception.close()
        with request(ids['image.png'],'test-token') as response:
            self.assertEqual(response.headers['Content-Type'],'image/png');self.assertEqual(response.read(),png())

    def test_safe_path_return_info_matches_stat(self):
        path = self.media / 'image.png'; path.write_bytes(png())
        source = _safe_path(str(self.media), 'image.png')
        self.assertEqual(source, path)
        source2, info = _safe_path(str(self.media), 'image.png', return_info=True)
        self.assertEqual(source2, path)
        expected = path.stat(follow_symlinks=False)
        self.assertEqual((info.st_ino, info.st_dev, info.st_size, info.st_mtime_ns),
                         (expected.st_ino, expected.st_dev, expected.st_size, expected.st_mtime_ns))

    def test_tag_source_calls_safe_path_once(self):
        path = self.media / 'book.cbz'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('p0.png', png())
        item = self.index()['book.cbz']
        import previews
        calls = 0
        orig_safe_path = previews._safe_path
        def counted_safe_path(*args, **kwargs):
            nonlocal calls
            calls += 1
            return orig_safe_path(*args, **kwargs)
        with patch('previews._safe_path', side_effect=counted_safe_path):
            source = self.reader.tag_source(item)
        self.assertEqual(source['item_id'], item)
        self.assertEqual(calls, 1)

    def test_replaced_leaf_during_read_detected_as_changed(self):
        path = self.media / 'book.cbz'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('p0.png', png())
        item = self.index()['book.cbz']
        orig_stat = Path.stat
        real = path.stat(follow_symlinks=False)
        replaced_stat = os.stat_result((real.st_mode, 9999999, real.st_dev, real.st_nlink, real.st_uid, real.st_gid, real.st_size, int(real.st_atime), int(real.st_mtime), int(real.st_ctime)), {'st_file_attributes': 0})
        calls = 0
        def fake_stat(self_path, *args, **kwargs):
            nonlocal calls
            if self_path == path and kwargs.get('follow_symlinks') is False:
                calls += 1
                if calls >= 2:
                    return replaced_stat
            return orig_stat(self_path, *args, **kwargs)
        with patch.object(Path, 'stat', new=fake_stat):
            with self.assertRaises(ReaderChanged):
                self.reader.tag_source(item)

    def test_replaced_root_during_read_detected_as_changed(self):
        path = self.media / 'book.cbz'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('p0.png', png())
        item = self.index()['book.cbz']
        orig_stat = Path.stat
        real_media_stat = self.media.stat(follow_symlinks=False)
        root_stat_calls = 0
        reparse_attr = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
        reparse_stat = os.stat_result((real_media_stat.st_mode, real_media_stat.st_ino, real_media_stat.st_dev, real_media_stat.st_nlink, real_media_stat.st_uid, real_media_stat.st_gid, real_media_stat.st_size, int(real_media_stat.st_atime), int(real_media_stat.st_mtime), int(real_media_stat.st_ctime)), {'st_file_attributes': reparse_attr})
        def fake_stat(self_path, *args, **kwargs):
            nonlocal root_stat_calls
            if self_path == self.media and kwargs.get('follow_symlinks') is False:
                root_stat_calls += 1
                if root_stat_calls >= 2:
                    return reparse_stat
            return orig_stat(self_path, *args, **kwargs)
        with patch.object(Path, 'stat', new=fake_stat):
            with self.assertRaises(ReaderChanged):
                self.reader.tag_source(item)

    def test_replaced_intermediate_directory_during_read_detected_as_changed(self):
        sub1 = self.media / 'sub1'
        sub2 = sub1 / 'sub2'
        sub2.mkdir(parents=True)
        path = sub2 / 'book.cbz'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('p0.png', png())
        item = self.index()['book.cbz']
        orig_stat = Path.stat
        real_sub1_stat = sub1.stat(follow_symlinks=False)
        sub1_stat_calls = 0
        reparse_attr = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
        reparse_stat = os.stat_result((real_sub1_stat.st_mode, real_sub1_stat.st_ino, real_sub1_stat.st_dev, real_sub1_stat.st_nlink, real_sub1_stat.st_uid, real_sub1_stat.st_gid, real_sub1_stat.st_size, int(real_sub1_stat.st_atime), int(real_sub1_stat.st_mtime), int(real_sub1_stat.st_ctime)), {'st_file_attributes': reparse_attr})
        def fake_stat(self_path, *args, **kwargs):
            nonlocal sub1_stat_calls
            if self_path == sub1 and kwargs.get('follow_symlinks') is False:
                sub1_stat_calls += 1
                if sub1_stat_calls >= 2:
                    return reparse_stat
            return orig_stat(self_path, *args, **kwargs)
        with patch.object(Path, 'stat', new=fake_stat):
            with self.assertRaises(ReaderChanged):
                self.reader.tag_source(item)

    def test_cached_root_rechecks_ancestor_links_before_open(self):
        path = self.media / 'image.png'; path.write_bytes(png())
        cache = {}; _safe_path(str(self.media), 'image.png', root_cache=cache)
        original = Path.stat
        real = self.base.stat(follow_symlinks=False)
        from types import SimpleNamespace
        for mode, attributes in ((real.st_mode, 0x400), (stat.S_IFLNK, 0)):
            changed = SimpleNamespace(st_mode=mode, st_file_attributes=attributes)
            def linked_ancestor(component, *args, **kwargs):
                if component == self.base and kwargs.get('follow_symlinks') is False:
                    return changed
                return original(component, *args, **kwargs)
            with self.subTest(mode=mode, attributes=attributes):
                with patch.object(Path, 'stat', new=linked_ancestor):
                    with self.assertRaises(PreviewUnavailable):
                        _safe_path(str(self.media), 'image.png', root_cache=cache)

    def test_ancestor_links_during_read_are_rejected_with_or_without_cache(self):
        path = self.media / 'book.cbz'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('p0.png', png())
        item = self.index()['book.cbz']
        original_stat, original_fstat = Path.stat, os.fstat
        from types import SimpleNamespace
        real = self.base.stat(follow_symlinks=False)
        for use_cache in (False, True):
            for operation in ('tag_source', 'preview', 'page_catalog'):
                for mode, attributes in ((real.st_mode, 0x400), (stat.S_IFLNK, 0)):
                    cache = {} if use_cache else None
                    if use_cache:
                        _safe_path(str(self.media), 'book.cbz', root_cache=cache)
                    handle_checks = 0
                    changed = SimpleNamespace(st_mode=mode, st_file_attributes=attributes)
                    def checked_handle(*args, **kwargs):
                        nonlocal handle_checks
                        handle_checks += 1
                        return original_fstat(*args, **kwargs)
                    def linked_after_read(component, *args, **kwargs):
                        if (component == self.base and handle_checks >= 2
                                and kwargs.get('follow_symlinks') is False):
                            return changed
                        return original_stat(component, *args, **kwargs)
                    expected = PreviewUnavailable if operation == 'preview' else ReaderChanged
                    with self.subTest(cache=use_cache, operation=operation, attributes=attributes):
                        with patch('previews.os.fstat', side_effect=checked_handle):
                            with patch.object(Path, 'stat', new=linked_after_read):
                                with self.assertRaises(expected):
                                    self.reader._read(item, operation=operation, root_cache=cache)
                        self.assertEqual(handle_checks, 2)

    def test_cached_root_reuses_resolution_but_rechecks_ancestors(self):
        path = self.media / 'image.png'
        path.write_bytes(png())
        root_cache = {}
        _safe_path(str(self.media), 'image.png', root_cache=root_cache)
        stat_paths = []
        orig_stat = Path.stat
        def recorded_stat(self_path, *args, **kwargs):
            stat_paths.append(self_path)
            return orig_stat(self_path, *args, **kwargs)
        original_resolve = Path.resolve
        resolutions = []
        def recorded_resolve(component, *args, **kwargs):
            resolutions.append(component)
            return original_resolve(component, *args, **kwargs)
        cached = root_cache[str(self.media)]
        with patch.object(Path, 'stat', new=recorded_stat):
            with patch.object(Path, 'resolve', new=recorded_resolve):
                _safe_path(str(self.media), 'image.png', root_cache=root_cache)
        self.assertIs(root_cache[str(self.media)], cached)
        self.assertEqual(resolutions, [path])
        # Cached resolution must not cache mutable ancestor link permissions.
        parents = set(self.media.parents)
        parent_stats = [p for p in stat_paths if p in parents]
        self.assertEqual(set(parent_stats), parents)
        self.assertIn(self.media, stat_paths)
        self.assertIn(path, stat_paths)

if __name__=='__main__':unittest.main()
