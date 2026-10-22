"""Generated derived thumbnails, source authorization and shared ownership."""
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from unittest.mock import patch, PropertyMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from PIL import Image, GifImagePlugin
from production import ProductionCatalog
from production_server import production_handler, DisabledAI
from previews import PreviewReader, PreviewUnavailable, ReaderChanged
from thumbnail_cache import ThumbnailCache, ThumbnailCancelled


def png(color='red', size=(300, 180)):
    with io.BytesIO() as out:
        Image.new('RGB', size, color).save(out, format='PNG')
        return out.getvalue()


class ThumbnailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.media = self.base / 'media'; self.media.mkdir()
        (self.media / 'image.png').write_bytes(png())
        with zipfile.ZipFile(self.media / 'book.cbz', 'w') as book:
            book.writestr('01.png', png('blue')); book.writestr('02.png', png('green'))
        self.catalog = ProductionCatalog(self.base / 'library.sqlite'); self.addCleanup(self.catalog.close)
        self.root = self.catalog.add_root(str(self.media)); self.scan()
        self.previews = PreviewReader(self.catalog)
        self.owner = ThumbnailCache(self.previews); self.addCleanup(self.owner.close)

    def scan(self):
        self.catalog.index.scan(self.root); self.catalog.sync_index()
        self.ids = {r['title']: r['id'] for r in self.catalog.search()['items']}

    def image(self, data):
        path = self.media / 'other.png'; path.write_bytes(data); self.scan()
        return self.ids['other.png']

    def read(self, item=None, edge=128, **kwargs):
        return self.owner.read(item or self.ids['image.png'], edge, **kwargs)

    def test_sizes_and_hit_do_not_decode_again_or_modify_sources(self):
        before = {p: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in self.media.iterdir()}
        with patch.object(self.owner, '_decode', wraps=self.owner._decode) as decode:
            for edge in (128, 256, 512, 1024):
                data = self.read(edge=edge)
                with Image.open(io.BytesIO(data)) as result:
                    self.assertEqual(result.format, 'PNG'); self.assertLessEqual(max(result.size), edge)
                    self.assertEqual(result.mode, 'RGBA')
                self.assertEqual(self.read(edge=edge), data)
            self.assertEqual(decode.call_count, 4)
        self.assertEqual(before, {p: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in self.media.iterdir()})

    def test_cover_hit_revalidates_without_decompressing_zip(self):
        data = self.read(self.ids['book.cbz'])
        with Image.open(io.BytesIO(data)) as cover:
            self.assertEqual(cover.getpixel((0, 0)), (0, 0, 255, 255))
        with patch.object(zipfile.ZipFile, 'open', side_effect=AssertionError('hit decompressed')):
            self.assertEqual(self.read(self.ids['book.cbz']), data)
        self.catalog.set_excludes(self.root, ['*.cbz'])
        with self.assertRaises(PreviewUnavailable): self.read(self.ids['book.cbz'])

    def test_cache_never_authorizes_excluded_unregistered_or_missing_source(self):
        self.read(); self.catalog.set_excludes(self.root, ['*.png'])
        with self.assertRaises(PreviewUnavailable): self.read()
        self.catalog.set_excludes(self.root, []); (self.media / 'image.png').unlink()
        with self.assertRaises((PreviewUnavailable, OSError)): self.read()
        self.catalog.unregister_root(self.root)
        with self.assertRaises(PreviewUnavailable): self.read()

    def test_same_metadata_replacement_uses_new_revision(self):
        first = self.read(); path = self.media / 'image.png'; info = path.stat()
        # Swap an identical-sized valid image while retaining catalog metadata.
        replacement = self.media / 'replacement.tmp'; replacement.write_bytes(path.read_bytes())
        os.utime(replacement, ns=(info.st_atime_ns, info.st_mtime_ns)); os.replace(replacement, path)
        with patch.object(self.owner, '_decode', wraps=self.owner._decode) as decode:
            self.assertEqual(self.read(), first); self.assertEqual(decode.call_count, 1)

    def test_change_during_cached_delivery_is_rejected(self):
        self.read(); original = self.owner._probe; calls = 0
        def probe(item):
            nonlocal calls
            calls += 1
            if calls == 2: self.catalog.set_excludes(self.root, ['*.png'])
            return original(item)
        with patch.object(self.owner, '_probe', side_effect=probe):
            with self.assertRaises(PreviewUnavailable): self.read()

    def test_apng_uses_first_visible_frame_and_gif_never_enumerates(self):
        out = io.BytesIO()
        Image.new('RGBA', (4, 4), 'white').save(out, format='PNG', save_all=True, default_image=True,
            append_images=[Image.new('RGBA', (4, 4), 'blue'), Image.new('RGBA', (4, 4), 'green')], duration=50)
        item = self.image(out.getvalue())
        with Image.open(io.BytesIO(self.read(item))) as result:
            self.assertEqual(result.getpixel((0, 0)), (0, 0, 255, 255))
        out = io.BytesIO(); Image.new('RGB', (4, 4), 'red').save(out, format='GIF', save_all=True,
            append_images=[Image.new('RGB', (4, 4), 'blue')], duration=50)
        item = self.image(out.getvalue())
        with patch.object(GifImagePlugin.GifImageFile, 'n_frames', new_callable=PropertyMock, side_effect=AssertionError('whole GIF scan')):
            self.assertTrue(self.read(item).startswith(b'\x89PNG'))

    def test_exif_rotation_preserves_orientation(self):
        out = io.BytesIO(); source = Image.new('RGB', (10, 20), 'red'); exif = source.getexif(); exif[274] = 6
        source.save(out, format='JPEG', exif=exif)
        item = self.image(out.getvalue())
        with Image.open(io.BytesIO(self.read(item))) as result: self.assertEqual(result.size, (20, 10))

    def test_encoded_byte_and_entry_limits_evict_without_stopping_reading(self):
        self.owner.max_bytes = 1
        self.assertTrue(self.read()); self.assertEqual(self.owner.bytes, 0)
        self.owner.max_bytes = 100000; self.owner.max_entries = 1
        self.read(); self.read(edge=256)
        self.assertEqual(len(self.owner.cache), 1); self.assertLessEqual(self.owner.bytes, self.owner.max_bytes)

    def run_shared(self, cancel_leader):
        entered = threading.Event(); release = threading.Event(); cancel = threading.Event()
        outcomes = {}; original = self.owner._decode
        def decode(*args):
            entered.set(); self.assertTrue(release.wait(3)); return original(*args)
        def run(name, cancelled):
            try: outcomes[name] = self.read(cancelled=cancelled)
            except Exception as error: outcomes[name] = error
        with patch.object(self.owner, '_decode', side_effect=decode) as decoding:
            a = threading.Thread(target=run, args=('a', cancel.is_set if cancel_leader else lambda: False)); a.start()
            self.assertTrue(entered.wait(3))
            # Observe the actual job join rather than relying on scheduling sleeps.
            joined = threading.Event(); original_wait = next(iter(self.owner.jobs.values())).ready.wait
            def wait(timeout): joined.set(); return original_wait(timeout)
            with patch.object(next(iter(self.owner.jobs.values())).ready, 'wait', side_effect=wait):
                b = threading.Thread(target=run, args=('b', (lambda: False) if cancel_leader else cancel.is_set)); b.start()
                self.assertTrue(joined.wait(3)); cancel.set(); release.set()
                a.join(4); b.join(4)
            self.assertFalse(a.is_alive()); self.assertFalse(b.is_alive()); self.assertEqual(decoding.call_count, 1)
        cancelled_name, survivor = ('a', 'b') if cancel_leader else ('b', 'a')
        self.assertIsInstance(outcomes[cancelled_name], ThumbnailCancelled)
        self.assertTrue(outcomes[survivor].startswith(b'\x89PNG')); self.assertEqual(self.owner.jobs, {})

    def test_leader_disconnect_does_not_cancel_shared_waiter(self): self.run_shared(True)
    def test_waiter_disconnect_does_not_cancel_leader(self): self.run_shared(False)

    def test_close_during_decode_does_not_publish_late_cache(self):
        original = self.owner._decode
        def decode(*args):
            data = original(*args); self.owner.close(); return data
        with patch.object(self.owner, '_decode', side_effect=decode):
            with self.assertRaises(ThumbnailCancelled): self.read()
        self.assertEqual(self.owner.bytes, 0); self.assertEqual(self.owner.jobs, {})

    def test_two_build_limit_and_cancelled_queue_never_decode(self):
        entered = threading.Barrier(3); release = threading.Event(); cancel = threading.Event()
        outcomes = {}; active = 0; maximum = 0; lock = threading.Lock(); original = self.owner._decode
        def decode(*args):
            nonlocal active, maximum
            with lock: active += 1; maximum = max(maximum, active)
            try:
                entered.wait(3); self.assertTrue(release.wait(3)); return original(*args)
            finally:
                with lock: active -= 1
        def run(edge, cancelled=lambda: False):
            try: outcomes[edge] = self.read(edge=edge, cancelled=cancelled)
            except Exception as error: outcomes[edge] = error
        with patch.object(self.owner, '_decode', side_effect=decode):
            a = threading.Thread(target=run, args=(128,)); b = threading.Thread(target=run, args=(256,))
            a.start(); b.start(); entered.wait(3)
            queued = threading.Event(); acquire = self.owner._acquire
            def acquiring(*args, **kwargs): queued.set(); return acquire(*args, **kwargs)
            with patch.object(self.owner, '_acquire', side_effect=acquiring):
                c = threading.Thread(target=run, args=(512, cancel.is_set)); c.start()
                self.assertTrue(queued.wait(3)); cancel.set(); c.join(3)
            release.set(); a.join(3); b.join(3)
        self.assertIsInstance(outcomes[512], ThumbnailCancelled)
        self.assertEqual(maximum, 2); self.assertTrue(outcomes[128].startswith(b'\x89PNG'))
        self.assertTrue(outcomes[256].startswith(b'\x89PNG')); self.assertEqual(self.owner.jobs, {})

    def test_decode_failure_is_shared_and_next_request_can_retry(self):
        with patch.object(self.owner, '_decode', side_effect=OSError('generated bad codec')):
            with self.assertRaises(OSError): self.read()
        self.assertEqual(self.owner.jobs, {}); self.assertEqual(self.owner.bytes, 0)
        self.assertTrue(self.read().startswith(b'\x89PNG'))

    def test_disk_tier_avoids_decode_after_ram_eviction_and_checks_scope(self):
        self.owner.max_entries = 1
        first = self.read(); self.read(edge=256)
        with patch.object(self.owner, '_decode', side_effect=AssertionError('disk hit decoded')):
            self.assertEqual(self.read(), first)
            self.catalog.set_excludes(self.root, ['*.png'])
            with self.assertRaises(PreviewUnavailable): self.read()

    def test_corrupt_cache_and_disk_full_fall_back_to_original(self):
        first = self.read(); self.owner.cache.clear(); self.owner.bytes = 0
        self.owner.disk.db.execute("UPDATE thumbs SET png=x'01'"); self.owner.disk.db.commit()
        with patch.object(self.owner, '_decode', wraps=self.owner._decode) as decode:
            self.assertEqual(self.read(), first); self.assertEqual(decode.call_count, 1)
        self.owner.cache.clear(); self.owner.bytes = 0
        # SQLite's hard page cap produces SQLITE_FULL on the derived write.
        self.owner.disk.db.execute('DELETE FROM thumbs'); self.owner.disk.db.commit()
        self.owner.disk.db.execute('PRAGMA max_page_count=3')
        noisy = Image.frombytes('RGB', (300, 180), os.urandom(300 * 180 * 3)); out = io.BytesIO(); noisy.save(out, format='PNG')
        item = self.image(out.getvalue())
        self.assertTrue(self.read(item).startswith(b'\x89PNG'))
        self.assertTrue(self.owner.disk.disabled)
        self.assertTrue(self.read(item).startswith(b'\x89PNG'))

    def test_corrupt_book_cache_validator_is_miss_not_broken_listing(self):
        first = self.read(self.ids['book.cbz']); self.owner.cache.clear(); self.owner.bytes = 0
        self.owner.disk.db.execute("UPDATE thumbs SET tag='bad'"); self.owner.disk.db.commit()
        with patch.object(self.owner, '_decode', wraps=self.owner._decode) as decode:
            self.assertEqual(self.read(self.ids['book.cbz']), first); self.assertEqual(decode.call_count, 1)

    def test_pillow_rejection_is_unavailable_not_unhandled_http_error(self):
        with patch('PIL.Image.open', side_effect=Image.DecompressionBombError('generated header')):
            with self.assertRaises(PreviewUnavailable): self.read()
        self.assertEqual(self.owner.jobs, {})
        self.assertTrue(self.read().startswith(b'\x89PNG'))

    def test_disk_capacity_and_owned_cleanup(self):
        from thumbnail_disk import ThumbnailDisk
        self.owner.disk.close(); self.owner.disk = ThumbnailDisk(max_bytes=32768, parent=self.base)
        self.read(); directory = Path(self.owner.disk.directory.name)
        for edge in (256, 512, 1024): self.read(edge=edge)
        self.assertLessEqual((directory / 'derived.sqlite').stat().st_size, 32768)
        self.owner.close(); self.assertFalse(directory.exists())

    def test_folder_book_cover_revalidation(self):
        books = self.base / 'books'; cover = books / 'first' / '01.png'; cover.parent.mkdir(parents=True); cover.write_bytes(png('blue'))
        root = self.catalog.add_root(str(books), folder_books=True); self.catalog.index.scan(root); self.catalog.sync_index()
        item = self.catalog.search(root_id=root)['items'][0]['id']
        data = self.read(item)
        with patch.object(self.owner, '_decode', side_effect=AssertionError('folder hit decoded')):
            self.assertEqual(self.read(item), data)
        cover.unlink()
        with self.assertRaises((PreviewUnavailable, ReaderChanged, OSError)): self.read(item)

    def test_invalid_size_and_cancel_do_no_decode(self):
        with patch.object(self.owner, '_decode', side_effect=AssertionError('must not decode')):
            for edge in (0, 255, True, '256'):
                with self.assertRaises(ValueError): self.read(edge=edge)
            with self.assertRaises(ThumbnailCancelled): self.read(cancelled=lambda: True)


class ThumbnailHTTPTests(unittest.TestCase):
    setUp = ThumbnailTests.setUp
    scan = ThumbnailTests.scan
    def test_authenticated_strict_derived_route(self):
        handler = production_handler(self.catalog, 'test-token', ai=DisabledAI())
        self.addCleanup(handler.results.close); self.addCleanup(handler.animations.close)
        self.addCleanup(handler.setup_jobs.close); self.addCleanup(handler.thumbnails.close)
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        self.addCleanup(lambda: (server.shutdown(), thread.join(), server.server_close()))
        base = f'http://127.0.0.1:{server.server_port}/api/library/thumbnail/{self.ids["image.png"]}'
        def request(suffix, token='test-token'):
            try:
                response = urllib.request.urlopen(urllib.request.Request(base + suffix, headers={'X-Aredoko-Token': token}))
                with response: return response.status, response.read(), response.headers
            except urllib.error.HTTPError as error:
                with error: return error.code, error.read(), error.headers
        status, data, headers = request('?edge=128')
        self.assertEqual(status, 200); self.assertTrue(data.startswith(b'\x89PNG'))
        self.assertEqual(headers['Content-Type'], 'image/png'); self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(request('?edge=128', 'bad-token')[0], 403)
        for suffix in ('', '?edge=129', '?edge=128&edge=256', '?edge=128&extra=1', '?edge=0128', '?edge=128&priority=urgent', '?edge=128&priority=visible&priority=nearby', '/extra?edge=128'):
            self.assertEqual(request(suffix)[0], 400)
        self.assertEqual(request('?edge=128&priority=nearby')[0], 200)
        self.catalog.set_excludes(self.root, ['*.png']); self.assertEqual(request('?edge=128&priority=visible')[0], 404)
