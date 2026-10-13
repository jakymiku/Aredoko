"""Read-only archive paging through production paths, using temporary fiction."""
import json
import os
import struct
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import warnings
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
sys.path.insert(0, str(ROOT / 'tools'))
from production import ProductionCatalog
from production_server import production_handler, DisabledAI
from previews import PreviewReader, PreviewUnavailable, PreviewBusyError, ReaderChanged
from create_preview_fixture import png


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.media = self.base / 'media'
        self.media.mkdir()
        self.catalog = ProductionCatalog(self.base / 'catalog.sqlite')
        self.addCleanup(self.catalog.close)
        self.root = self.catalog.add_root(str(self.media))
        self.reader = PreviewReader(self.catalog)

    def index(self):
        self.catalog.index.scan(self.root)
        self.catalog.sync_index()
        return {r['title']: r['id'] for r in self.catalog.search()['items']}

    def book(self, name='book.cbz', entries=None):
        path = self.media / name
        if entries is None:
            entries = [('page10.png', png(color=(10, 20, 30))),
                       ('page2.png', png(color=(60, 70, 80))),
                       ('__MACOSX/page1.png', png()), ('readme.txt', b'fiction')]
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for filename, data in entries:
                    archive.writestr(filename, data)
        return path, self.index()[name]

    def page(self, item, number=0):
        return self.reader.read_page(item, number, self.reader.manifest(item)['revision'])

    def test_pages_order_legacy_cover_restart_and_readonly(self):
        for extension in ('cbz', 'zip'):
            path, item = self.book('book.' + extension)
            before = path.read_bytes(), path.stat().st_mtime_ns
            names = sorted(p.name for p in self.media.iterdir())
            self.catalog.update([item], {'tags':['keep'], 'shelf':'shelf', 'favorite':True})
            manifest = self.reader.manifest(item)
            self.assertEqual(manifest['page_count'], 2)
            self.assertEqual(manifest['item_id'], item)
            self.assertEqual(self.page(item), self.reader.read(item))
            self.assertEqual(self.page(item, 1), (png(color=(10, 20, 30)), 'image/png'))
            restarted = ProductionCatalog(self.catalog.path)
            try:
                other = PreviewReader(restarted)
                self.assertEqual(other.manifest(item), manifest)
                self.assertEqual(other.read_page(item, 0, manifest['revision']), self.page(item))
                self.assertEqual(restarted.get(item)['tags'], ['keep'])
            finally:
                restarted.close()
            self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))
            self.assertEqual(names, sorted(p.name for p in self.media.iterdir()))

    def test_manifest_never_decompresses_and_duplicates_keep_directory_order(self):
        first, second = png(color=(1, 2, 3)), png(color=(4, 5, 6))
        _, item = self.book(entries=[('same.png', first), ('same.png', second)])
        with patch.object(zipfile.ZipFile, 'open', side_effect=AssertionError('decompressed')):
            manifest = self.reader.manifest(item)
        self.assertEqual(manifest['page_count'], 2)
        self.assertEqual(self.page(item, 0)[0], first)
        self.assertEqual(self.page(item, 1)[0], second)

    def test_invalid_page_revision_and_missing_page(self):
        _, item = self.book()
        revision = self.reader.manifest(item)['revision']
        for page in (-1, True, 1.0, '0', 10000):
            with self.assertRaises(ValueError): self.reader.read_page(item, page, revision)
        for revision in (None, '', 'a' * 63, 'z' * 64, True):
            with self.assertRaises(ValueError): self.reader.read_page(item, 0, revision)
        with self.assertRaises(PreviewUnavailable): self.page(item, 2)

    def test_changed_archive_requires_rescan_and_new_manifest(self):
        path, item = self.book()
        revision = self.reader.manifest(item)['revision']
        with zipfile.ZipFile(path, 'a') as archive:
            archive.writestr('page1.png', png())
        with self.assertRaises(ReaderChanged): self.reader.manifest(item)
        with self.assertRaises(ReaderChanged): self.reader.read_page(item, 0, revision)
        self.index()
        with self.assertRaises(ReaderChanged): self.reader.read_page(item, 0, revision)
        self.assertEqual(self.reader.manifest(item)['page_count'], 3)
        self.assertEqual(self.page(item)[0], png())

    def test_replacement_with_same_indexed_metadata_changes_revision(self):
        path, item = self.book()
        info = path.stat()
        revision = self.reader.manifest(item)['revision']
        replacement = self.media / 'replacement.tmp'
        replacement.write_bytes(path.read_bytes())
        os.utime(replacement, ns=(info.st_atime_ns, info.st_mtime_ns))
        replacement.replace(path)
        with self.assertRaises(ReaderChanged): self.reader.read_page(item, 0, revision)

    def test_change_during_read_is_rejected_and_slot_released(self):
        path, item = self.book()
        revision = self.reader.manifest(item)['revision']
        original = zipfile.ZipFile.open
        def mutate(archive, *args, **kwargs):
            image = original(archive, *args, **kwargs)
            info = path.stat()
            os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))
            return image
        with patch.object(zipfile.ZipFile, 'open', mutate):
            with self.assertRaises(ReaderChanged): self.reader.read_page(item, 0, revision)
        self.index()
        self.assertEqual(self.page(item)[1], 'image/png')

    def test_nonfirst_page_limits_and_corruption(self):
        _, item = self.book(entries=[('1.png', png()), ('2.png', b'0' * 500000)])
        self.assertEqual(self.reader.manifest(item)['page_count'], 2)
        self.assertEqual(self.page(item, 0)[0], png())
        with self.assertRaises(PreviewUnavailable): self.page(item, 1)
        (self.media / 'bad.cbz').write_bytes(b'not a zip')
        bad = self.index()['bad.cbz']
        with self.assertRaises(PreviewUnavailable): self.reader.manifest(bad)

    def test_directory_archive_and_image_limits_shared(self):
        _, item = self.book()
        with patch('previews.MAX_DIRECTORY_BYTES', 1):
            with patch.object(zipfile, 'ZipFile', side_effect=AssertionError('parsed')):
                with self.assertRaises(PreviewUnavailable): self.reader.manifest(item)
        with patch('previews.MAX_ARCHIVE_BYTES', 1):
            with self.assertRaises(PreviewUnavailable): self.reader.manifest(item)
        with patch('previews.MAX_IMAGE_BYTES', 1):
            with self.assertRaises(PreviewUnavailable): self.page(item, 1)

    def test_encrypted_and_crc_broken_pages_fail_without_hiding_other_pages(self):
        for encrypted in (True, False):
            path = self.media / 'broken.cbz'
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as archive:
                archive.writestr('1.png', png())
                archive.writestr('2.png', png(color=(2, 3, 4)))
            raw = bytearray(path.read_bytes())
            if encrypted:
                central = raw.index(b'PK\x01\x02')
                central = raw.index(b'PK\x01\x02', central + 4)
                flags = struct.unpack_from('<H', raw, central + 8)[0]
                struct.pack_into('<H', raw, central + 8, flags | 1)
            else:
                header = raw.index(b'PK\x03\x04')
                header = raw.index(b'PK\x03\x04', header + 4)
                name, extra = struct.unpack_from('<HH', raw, header + 26)
                raw[header + 30 + name + extra] ^= 1
            path.write_bytes(raw)
            item = self.index()['broken.cbz']
            self.assertEqual(self.reader.manifest(item)['page_count'], 2)
            self.assertEqual(self.page(item, 0)[0], png())
            with self.assertRaises(PreviewUnavailable): self.page(item, 1)

    def test_exclusions_missing_unsupported_and_reparse(self):
        path, item = self.book()
        revision = self.reader.manifest(item)['revision']
        self.catalog.set_excludes(self.root, ['*.cbz'])
        with self.assertRaises(PreviewUnavailable): self.reader.manifest(item)
        with self.assertRaises(PreviewUnavailable): self.reader.read_page(item, 0, revision)
        self.catalog.set_excludes(self.root, [])
        (self.media / 'image.png').write_bytes(png())
        with self.assertRaises(PreviewUnavailable): self.reader.manifest(self.index()['image.png'])
        outside = self.base / 'outside.cbz'
        path.rename(outside)
        with self.assertRaises(OSError): self.reader.manifest(item)
        try: path.symlink_to(outside)
        except OSError: self.skipTest('symlink privilege unavailable')
        with self.assertRaises(PreviewUnavailable): self.reader.manifest(item)

    def test_empty_archive_and_traversal_name_never_extract(self):
        _, empty = self.book('empty.zip', [('readme.txt', b'fiction')])
        with self.assertRaises(PreviewUnavailable): self.reader.manifest(empty)
        _, item = self.book(entries=[('../../outside.png', png())])
        self.assertEqual(self.page(item)[0], png())
        self.assertFalse((self.base / 'outside.png').exists())

    def test_shared_worker_limit_and_no_leak_on_failure(self):
        _, item = self.book()
        revision = self.reader.manifest(item)['revision']
        self.reader.slots.acquire()
        self.reader.slots.acquire()
        try:
            for action in (lambda: self.reader.manifest(item), lambda: self.reader.read_page(item, 0, revision), lambda: self.reader.read(item)):
                with self.assertRaises(PreviewBusyError): action()
        finally:
            self.reader.slots.release()
            self.reader.slots.release()
        for _ in range(3):
            with self.assertRaises(PreviewUnavailable): self.page(item, 9)
        self.assertEqual(self.page(item)[1], 'image/png')

    def test_http_auth_routes_paging_stale_busy_and_legacy(self):
        path, item = self.book()
        server = ThreadingHTTPServer(('127.0.0.1', 0), production_handler(self.catalog, 'reader-token', ai=DisabledAI()))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(worker.join, 5)
        self.addCleanup(server.shutdown)
        prefix = f'/api/library/reader/{item}'
        def request(route, token='reader-token', host=None):
            headers = {'X-Aredoko-Token':token}
            if host: headers['Host'] = host
            req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}' + route, headers=headers)
            try:
                with urllib.request.urlopen(req) as response:
                    return response.status, response.read(), response.headers['Content-Type'], response.headers['Cache-Control']
            except urllib.error.HTTPError as error:
                with error: return error.code, error.read(), error.headers['Content-Type'], error.headers['Cache-Control']
        self.assertEqual(request(prefix, token='wrong')[0], 403)
        self.assertEqual(request(prefix, host='example.com')[0], 403)
        status, body, _, cache = request(prefix)
        self.assertEqual(status, 200)
        self.assertEqual(cache, 'no-store')
        revision = json.loads(body)['revision']
        route = prefix + '/pages/1?revision=' + revision
        status, body, mime, cache = request(route)
        self.assertEqual((status, body, mime, cache), (200, png(color=(10, 20, 30)), 'image/png', 'no-store'))
        self.assertEqual(request(route, token='wrong')[0], 403)
        for bad in (prefix+'?path=secret', prefix+'/pages/-1?revision='+revision,
                    prefix+'/pages/10000?revision='+revision, prefix+'/pages/0',
                    route+'&revision='+revision, route+'&path=secret', prefix+'/pages/0?revision=bad',
                    '/api/library/reader/9999999999999999999', prefix+'/extra'):
            self.assertEqual(request(bad)[0], 400, bad)
        self.assertEqual(request(prefix+'/pages/2?revision='+revision)[0], 404)
        with patch.object(PreviewReader, 'manifest', side_effect=PreviewBusyError):
            self.assertEqual(request(prefix)[0], 503)
        with patch.object(PreviewReader, 'read_page', side_effect=PreviewBusyError):
            self.assertEqual(request(route)[0], 503)
        self.assertEqual(request(f'/api/library/preview/{item}')[0], 200)
        with zipfile.ZipFile(path, 'a') as archive: archive.writestr('page1.png', png())
        self.assertEqual(request(prefix)[0], 409)
        self.index()
        self.assertEqual(request(route)[0], 409)
        self.assertEqual(request(prefix)[0], 200)


if __name__ == '__main__':
    unittest.main()
