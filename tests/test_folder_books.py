"""Image folders registered as books: explicit opt-in only, read-only paging."""
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
sys.path.insert(0, str(ROOT / 'tools'))
from production import ProductionCatalog
from previews import PreviewReader, PreviewUnavailable, ReaderChanged
from create_preview_fixture import png


class FolderBookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.media = base / 'books'
        (self.media / '作品A').mkdir(parents=True)
        (self.media / '作品B' / 'おまけ').mkdir(parents=True)
        for name, color in (('p10.png', (1, 2, 3)), ('p2.png', (4, 5, 6)), ('p1.jpg', (7, 8, 9))):
            (self.media / '作品A' / name).write_bytes(png(color=color))
        (self.media / '作品A' / 'note.txt').write_bytes(b'fiction')
        (self.media / '作品A' / 'cover.psd').write_bytes(b'8BPS')
        (self.media / '作品B' / '01.png').write_bytes(png())
        (self.media / '作品B' / 'おまけ' / 'extra.webp').write_bytes(png())
        (self.media / '作品B' / 'clip.mp4').write_bytes(b'\0' * 16)
        self.catalog = ProductionCatalog(base / 'catalog.sqlite')
        self.addCleanup(self.catalog.close)
        self.reader = PreviewReader(self.catalog)

    def index(self, root):
        counts = self.catalog.index.scan(root)
        self.catalog.sync_index()
        return counts, {r['relative_path']: r for r in self.catalog.search(root_id=root)['items']}

    def test_default_root_keeps_one_item_per_image(self):
        root = self.catalog.add_root(str(self.media))
        self.assertFalse(self.catalog.index.roots()[0]['folder_books'])
        _, items = self.index(root)
        self.assertIn('作品A/p10.png', items)
        self.assertFalse(any(path.endswith('/') for path in items))

    def test_opted_in_root_groups_direct_images_per_folder(self):
        root = self.catalog.add_root(str(self.media), folder_books=True)
        self.assertTrue(self.catalog.index.roots()[0]['folder_books'])
        counts, items = self.index(root)
        self.assertEqual(sorted(items), ['作品A/', '作品A/cover.psd', '作品B/', '作品B/clip.mp4', '作品B/おまけ/'])
        self.assertEqual(counts['discovered'], 5)
        book = items['作品A/']
        self.assertEqual((book['kind'], book['title']), ('book', '作品A'))
        self.assertEqual(items['作品B/おまけ/']['title'], 'おまけ')
        # Natural page order over displayable images; text/PSD/video stay out.
        manifest = self.reader.manifest(book['id'])
        self.assertEqual(manifest['page_count'], 3)
        pages = [self.reader.read_page(book['id'], i, manifest['revision'])[0] for i in range(3)]
        expected = [(self.media / '作品A' / n).read_bytes() for n in ('p1.jpg', 'p2.png', 'p10.png')]
        self.assertEqual(pages, expected)
        self.assertEqual(self.reader.read(book['id'])[0], expected[0])
        self.assertEqual(self.reader.tag_source(book['id'])['revision'], manifest['revision'])
        self.assertEqual(self.reader.tag_input(book['id'])['data'], expected[0])
        self.assertEqual(self.catalog.reader_progress(book['id']), {'progress': None})
        with self.assertRaises(PreviewUnavailable):
            self.reader.read_page(book['id'], 3, manifest['revision'])
        with self.assertRaises(PreviewUnavailable):
            self.reader.read_video(book['id'])

    def test_loose_images_in_root_become_a_book_named_after_the_root(self):
        (self.media / 'loose.png').write_bytes(png())
        root = self.catalog.add_root(str(self.media), folder_books=True)
        _, items = self.index(root)
        self.assertEqual(items['./']['title'], 'books')
        self.assertEqual(self.reader.manifest(items['./']['id'])['page_count'], 1)

    def test_page_changes_need_rescan_and_keep_metadata(self):
        root = self.catalog.add_root(str(self.media), folder_books=True)
        _, items = self.index(root)
        book = items['作品A/']
        self.catalog.update([book['id']], {'tags': ['お気に入り作家'], 'shelf': '読む'})
        old = self.reader.manifest(book['id'])['revision']
        (self.media / '作品A' / 'p3.png').write_bytes(png(color=(9, 9, 9)))
        with self.assertRaises(ReaderChanged):
            self.reader.manifest(book['id'])
        with self.assertRaises(PreviewUnavailable):
            self.reader.read(book['id'])
        counts, items = self.index(root)
        self.assertEqual(counts['changed'], 1)
        same = items['作品A/']
        self.assertEqual(same['id'], book['id'])
        self.assertEqual((same['tags'], same['shelf']), (['お気に入り作家'], '読む'))
        manifest = self.reader.manifest(same['id'])
        self.assertEqual(manifest['page_count'], 4)
        self.assertNotEqual(manifest['revision'], old)
        with self.assertRaises(ReaderChanged):
            self.reader.read_page(same['id'], 0, old)
        # Removing every image marks the book missing; records are kept.
        for page in (self.media / '作品A').glob('*.*'):
            if page.suffix in ('.png', '.jpg'):
                page.unlink()
        counts, _ = self.index(root)
        self.assertEqual(counts['missing'], 1)

    def test_exclusions_apply_to_pages(self):
        root = self.catalog.add_root(str(self.media), ['作品A/p2.png', 'おまけ'], folder_books=True)
        _, items = self.index(root)
        self.assertNotIn('作品B/おまけ/', items)
        self.assertEqual(self.reader.manifest(items['作品A/']['id'])['page_count'], 2)

    def test_mode_is_fixed_after_scanning(self):
        root = self.catalog.add_root(str(self.media), folder_books=True)
        self.index(root)
        self.catalog.index.unregister(root)
        with self.assertRaisesRegex(ValueError, 'cannot change'):
            self.catalog.add_root(str(self.media), folder_books=False)
        self.assertEqual(self.catalog.add_root(str(self.media)), root)
        self.assertTrue(self.catalog.index.roots()[0]['folder_books'])
        with self.assertRaises(ValueError):
            self.catalog.add_root(str(self.media / 'x'), folder_books='yes')

    def test_http_registration_reader_and_specific_errors(self):
        import json, threading, urllib.error, urllib.request
        from http.server import ThreadingHTTPServer
        from production_server import production_handler, DisabledAI
        server = ThreadingHTTPServer(('127.0.0.1', 0), production_handler(self.catalog, 'tok', ai=DisabledAI()))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        origin = f'http://127.0.0.1:{server.server_port}'
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def call(route, body=None):
            data = None if body is None else json.dumps(body).encode()
            request = urllib.request.Request(origin + route, data, headers={
                'Origin': origin, 'X-Aredoko-Token': 'tok', 'Content-Type': 'application/json'})
            try:
                with opener.open(request) as response:
                    return response.status, json.loads(response.read())
            except urllib.error.HTTPError as error:
                with error: return error.code, json.loads(error.read())

        base = {'path': str(self.media), 'consent': True}
        self.assertEqual(call('/api/library/roots', {**base, 'folder_books': 'yes'}),
                         (400, {'error': 'folder_books must be true or false'}))
        self.assertEqual(call('/api/library/roots', {'path': str(self.media)}),
                         (400, {'error': 'Explicit folder consent required'}))
        status, body = call('/api/library/roots', {**base, 'folder_books': True})
        self.assertEqual(status, 200)
        self.assertEqual(call('/api/library/roots', base), (400, {'error': 'This root is already registered'}))
        self.assertEqual(call('/api/library/roots', {**base, 'path': str(self.media / '作品A')}),
                         (400, {'error': 'Overlapping roots are not supported'}))
        self.assertTrue(call('/api/library/roots')[1]['items'][0]['folder_books'])
        _, items = self.index(body['root_id'])
        book = items['作品A/']['id']
        status, manifest = call(f'/api/library/reader/{book}')
        self.assertEqual((status, manifest['page_count']), (200, 3))

    @unittest.skipIf(os.name == 'nt', 'symlink creation needs privileges on Windows')
    def test_linked_pages_are_not_read(self):
        outside = Path(self.tmp.name) / 'outside.png'
        outside.write_bytes(png())
        os.symlink(outside, self.media / '作品A' / 'p0.png')
        root = self.catalog.add_root(str(self.media), folder_books=True)
        _, items = self.index(root)
        self.assertEqual(self.reader.manifest(items['作品A/']['id'])['page_count'], 3)

    def test_equal_numeric_page_names_keep_order_across_directory_enumerations(self):
        import previews
        directory = self.media / '同番号'
        directory.mkdir()
        names = ['p1.png', 'p01.png', 'p001.png']
        for i, name in enumerate(names):
            (directory / name).write_bytes(png(color=(i + 10, 20, 30)))
        root = self.catalog.add_root(str(self.media), folder_books=True)
        _, items = self.index(root)
        book = items['同番号/']['id']
        revision = self.reader.manifest(book)['revision']
        pages = previews.folder_pages(directory, '同番号/', ())
        with patch('previews.folder_pages', return_value=pages):
            first = self.reader.read_page(book, 0, revision)[0]
        with patch('previews.folder_pages', return_value=list(reversed(pages))):
            self.assertEqual(self.reader.read_page(book, 0, revision)[0], first)
        self.assertEqual(first, (directory / 'p001.png').read_bytes())

    def test_old_folder_token_requires_rescan_without_losing_metadata(self):
        import hashlib
        import json
        from previews import folder_pages
        root = self.catalog.add_root(str(self.media), folder_books=True)
        _, items = self.index(root)
        book = items['作品A/']['id']
        self.catalog.update([book], {'tags': ['維持'], 'shelf': '読む', 'favorite': True})
        pages = sorted(folder_pages(self.media / '作品A', '作品A/', ()))
        legacy = int.from_bytes(hashlib.sha256(json.dumps(pages, ensure_ascii=False).encode()).digest()[:8], 'big') >> 1
        with self.catalog.index.connect() as db:
            db.execute('UPDATE library_locations SET mtime_ns=? WHERE root_id=? AND relative_path=?',
                       (legacy, root, '作品A/'))
        with self.assertRaises(ReaderChanged):
            self.reader.manifest(book)
        _, after = self.index(root)
        self.assertEqual(after['作品A/']['id'], book)
        self.assertEqual(after['作品A/']['tags'], ['維持'])
        self.assertEqual(after['作品A/']['shelf'], '読む')
        self.assertTrue(after['作品A/']['favorite'])
        self.assertEqual(self.reader.manifest(book)['page_count'], 3)

    def _after_page_read(self, target, action):
        """Change real generated sources at the point a page has been read."""
        original = Path.open

        @contextmanager
        def opening(path, *args, **kwargs):
            with original(path, *args, **kwargs) as file:
                if path == target and args == ('rb',):
                    def read(*read_args):
                        data = file.read(*read_args)
                        action()
                        return data
                    yield SimpleNamespace(read=read, fileno=file.fileno)
                else:
                    yield file
        return patch.object(Path, 'open', opening)

    def test_page_list_changes_during_read_do_not_publish_old_revision(self):
        root = self.catalog.add_root(str(self.media), folder_books=True)
        _, items = self.index(root)
        book = items['作品A/']['id']
        revision = self.reader.manifest(book)['revision']
        extra = self.media / '作品A' / 'p0.png'
        for operation in ('page', 'tag_input', 'preview'):
            with self.subTest(operation=operation):
                def add_cover():
                    extra.write_bytes(png(color=(99, 88, 77)))
                try:
                    with self._after_page_read(self.media / '作品A' / 'p1.jpg', add_cover):
                        with self.assertRaises(PreviewUnavailable):
                            if operation == 'page':
                                self.reader.read_page(book, 0, revision)
                            elif operation == 'tag_input':
                                self.reader.tag_input(book)
                            else:
                                self.reader.read(book)
                finally:
                    extra.unlink(missing_ok=True)
        self.assertEqual(self.reader.manifest(book)['revision'], revision)

    @unittest.skipIf(os.name == 'nt', 'open-file replacement is platform-specific')
    def test_page_replaced_during_read_is_not_returned(self):
        root = self.catalog.add_root(str(self.media), folder_books=True)
        _, items = self.index(root)
        book = items['作品A/']['id']
        revision = self.reader.manifest(book)['revision']
        page = self.media / '作品A' / 'p1.jpg'
        replacement = Path(self.tmp.name) / 'replacement.png'
        replacement.write_bytes(page.read_bytes())
        info = page.stat()
        os.utime(replacement, ns=(info.st_atime_ns, info.st_mtime_ns))
        with self._after_page_read(page, lambda: replacement.replace(page)):
            with self.assertRaises(ReaderChanged):
                self.reader.read_page(book, 0, revision)

    @unittest.skipIf(os.name == 'nt', 'symlink creation needs privileges on Windows')
    def test_folder_replaced_by_link_after_inventory_is_not_followed(self):
        import previews
        root = self.catalog.add_root(str(self.media), folder_books=True)
        _, items = self.index(root)
        book = items['作品A/']['id']
        directory = self.media / '作品A'
        outside = Path(self.tmp.name) / 'outside'
        outside.mkdir()
        for page in directory.iterdir():
            if page.is_file():
                copy = outside / page.name
                copy.write_bytes(page.read_bytes())
                info = page.stat()
                os.utime(copy, ns=(info.st_atime_ns, info.st_mtime_ns))
        original = previews.folder_pages

        def replace_folder(*args):
            pages = original(*args)
            directory.rename(self.media / 'saved')
            directory.symlink_to(outside, target_is_directory=True)
            return pages

        with patch('previews.folder_pages', side_effect=replace_folder):
            with self.assertRaises(PreviewUnavailable):
                self.reader.tag_input(book)

    def test_page_limit_applies_to_preview_and_tagging_too(self):
        directory = self.media / '大冊'
        directory.mkdir()
        for i in range(10001):
            (directory / f'{i}.png').touch()
        root = self.catalog.add_root(str(self.media), folder_books=True)
        _, items = self.index(root)
        book = items['大冊/']['id']
        for read in (self.reader.manifest, self.reader.read, self.reader.tag_source, self.reader.tag_input):
            with self.subTest(operation=read.__name__), self.assertRaises(PreviewUnavailable):
                read(book)

    def test_failed_or_cancelled_folder_scan_rolls_back_and_keeps_annotations(self):
        (self.media / 'cover.png').write_bytes(png())
        root = self.catalog.add_root(str(self.media), folder_books=True)
        _, items = self.index(root)
        book = items['./']['id']
        self.catalog.update([book], {'tags': ['維持'], 'favorite': True})
        with self.catalog.index.connect() as db:
            before = [tuple(r) for r in db.execute('SELECT * FROM library_locations ORDER BY id')]
        # The root book is recorded before a later child directory fails.
        (self.media / 'new.png').write_bytes(png())
        original = os.scandir

        def break_child(path):
            if Path(path) != self.media:
                raise PermissionError('generated failure')
            return original(path)

        with patch('library_index.os.scandir', side_effect=break_child):
            with self.assertRaises(PermissionError):
                self.catalog.index.scan(root)
        # Cancel after the first newly encountered book has reached _record.
        record = self.catalog.index._record
        cancelled = False

        def record_and_cancel(*args):
            nonlocal cancelled
            record(*args)
            cancelled = True

        with patch.object(self.catalog.index, '_record', side_effect=record_and_cancel):
            with self.assertRaises(InterruptedError):
                self.catalog.index.scan(root, cancelled=lambda: cancelled)
        self.catalog.index.scan(root, dry_run=True)
        with self.catalog.index.connect() as db:
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM library_locations ORDER BY id')], before)
        self.catalog.sync_index()
        self.assertEqual(self.catalog.get(book)['tags'], ['維持'])
        self.assertTrue(self.catalog.get(book)['favorite'])


if __name__ == '__main__':
    unittest.main()
