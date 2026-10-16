"""User-feedback contracts on generated media and isolated DBs only."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from production import ProductionCatalog
from production_server import production_handler


class LibraryFeedbackTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.media = self.base / 'media'
        (self.media / 'nested').mkdir(parents=True)
        for name in ('first.png', 'second.png', 'nested/third.png'):
            (self.media / name).write_bytes(b'generated index-only fixture')
        self.catalog = ProductionCatalog(self.base / 'catalog.sqlite')
        self.addCleanup(self.catalog.close)

    def index(self, root):
        self.catalog.index.scan(root)
        self.catalog.sync_index()
        return {i['relative_path']: i for i in self.catalog.search(root_id=root)['items']}

    def test_recursive_default_and_direct_only(self):
        root = self.catalog.add_root(str(self.media), recursive=False)
        self.assertFalse(self.catalog.index.roots()[0]['recursive'])
        self.assertEqual(set(self.index(root)), {'first.png', 'second.png'})
        self.catalog.unregister_root(root)
        self.assertEqual(self.catalog.add_root(str(self.media)), root)
        self.assertFalse(self.catalog.index.roots()[0]['recursive'])
        self.catalog.unregister_root(root)
        self.catalog.add_root(str(self.media), recursive=True)
        self.assertIn('nested/third.png', self.index(root))

    def test_recursive_restore_hides_nested_immediately_and_preserves_metadata(self):
        root = self.catalog.add_root(str(self.media))
        self.assertTrue(self.catalog.index.roots()[0]['recursive'])
        item = self.index(root)['nested/third.png']['id']
        self.catalog.update([item], {'tags': ['keep'], 'shelf': 'manual', 'favorite': True})
        self.catalog.record_view(item)
        self.catalog.unregister_root(root)
        self.catalog.add_root(str(self.media), recursive=False)
        self.assertEqual(self.catalog.search()['total'], 2)
        self.assertEqual(self.catalog.search(view='history')['total'], 0)
        self.assertEqual(set(self.index(root)), {'first.png', 'second.png'})
        self.catalog.unregister_root(root)
        self.catalog.add_root(str(self.media), recursive=True)
        restored = self.index(root)['nested/third.png']
        self.assertEqual((restored['id'], restored['tags'], restored['shelf'], restored['favorite']), (item, ['keep'], 'manual', True))
        self.assertEqual(self.catalog.search(view='history')['total'], 1)

    def test_direct_only_folder_book_keeps_root_book(self):
        root = self.catalog.add_root(str(self.media), recursive=False, folder_books=True)
        items = self.index(root)
        self.assertEqual(set(items), {'./'})
        self.assertEqual(items['./']['kind'], 'book')

    def test_recursive_migration_preserves_old_default(self):
        root = self.catalog.add_root(str(self.media))
        self.index(root)
        with self.catalog.index.connect() as db:
            db.execute('ALTER TABLE library_roots DROP COLUMN recursive')
        reopened = ProductionCatalog(self.base / 'catalog.sqlite')
        self.addCleanup(reopened.close)
        self.assertTrue(reopened.index.roots()[0]['recursive'])
        self.assertEqual(reopened.search()['total'], 3)

    def test_recursive_rejects_non_bool(self):
        for value in (0, 1, 'false', [], {}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Include subfolders'):
                self.catalog.add_root(str(self.media), recursive=value)
        self.assertEqual(self.catalog.index.roots(), [])

    def test_history_order_count_scope_restart_and_readonly(self):
        root = self.catalog.add_root(str(self.media))
        items = self.index(root)
        a, b = items['first.png']['id'], items['second.png']['id']
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.media.rglob('*.png')}
        self.catalog.update([a], {'tags': ['blue'], 'favorite': True})
        self.assertEqual(self.catalog.search(view='history')['total'], 0)
        with patch('time.time_ns', side_effect=[100, 200, 300]):
            self.catalog.record_view(a)
            self.catalog.record_view(b)
            self.catalog.record_view(a)
        self.assertEqual([i['id'] for i in self.catalog.search(view='history')['items']], [a, b])
        self.assertEqual(self.catalog.search(view='history', page=1, limit=1)['items'][0]['id'], b)
        self.assertEqual(self.catalog.search('blue', 'image', 'history', root_ids=[root])['items'][0]['id'], a)
        self.assertEqual(self.catalog.search('unknown', view='history')['total'], 0)
        with self.catalog.connect() as db:
            self.assertEqual(db.execute('SELECT open_count FROM view_history WHERE item_id=?', (a,)).fetchone()[0], 2)
        reopened = ProductionCatalog(self.base / 'catalog.sqlite')
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.search(view='history')['items'][0]['id'], a)
        self.assertEqual(reopened.get(a)['tags'], ['blue'])
        self.assertTrue(reopened.get(a)['favorite'])
        self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.media.rglob('*.png')})
        self.catalog.unregister_root(root)
        self.assertEqual(self.catalog.search(view='history')['total'], 0)
        with self.assertRaises(KeyError): self.catalog.record_view(a)
        self.catalog.add_root(str(self.media))
        self.assertEqual(self.catalog.search(view='history')['total'], 2)

    def test_history_current_exclusions_without_rescan(self):
        root = self.catalog.add_root(str(self.media))
        item = self.index(root)['nested/third.png']['id']
        self.catalog.record_view(item)
        self.catalog.set_excludes(root, ['nested/*'])
        self.assertEqual(self.catalog.search(view='history')['total'], 0)
        with self.assertRaises(KeyError): self.catalog.record_view(item)
        self.catalog.set_excludes(root, [])
        self.assertEqual(self.catalog.search(view='history')['total'], 1)

    def test_history_invalid_or_missing_never_creates_rows(self):
        root = self.catalog.add_root(str(self.media))
        item = self.index(root)['first.png']['id']
        for invalid in (True, None, 0, -1, 2**63, '1', []):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError): self.catalog.record_view(invalid)
        with self.assertRaises(KeyError): self.catalog.record_view(99999)
        (self.media / 'first.png').unlink()  # generated fixture only
        self.index(root)
        with self.assertRaises(KeyError): self.catalog.record_view(item)
        with self.catalog.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM view_history').fetchone()[0], 0)

    def test_http_history_and_registration_auth_contract(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), production_handler(self.catalog, 'fixture-token'))
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f'http://127.0.0.1:{server.server_port}'
        def post(path, data, token='fixture-token', request_origin=None):
            request = urllib.request.Request(origin+path, json.dumps(data).encode(), headers={'Content-Type':'application/json', 'Origin':request_origin or origin, 'X-Aredoko-Token':token})
            try:
                with urllib.request.urlopen(request) as response: return response.status, json.load(response)
            except urllib.error.HTTPError as error:
                with error: return error.code, json.load(error)
        self.assertEqual(post('/api/library/roots', {'path':str(self.media), 'recursive':False})[0], 400)
        self.assertEqual(post('/api/library/roots', {'path':str(self.media), 'consent':True, 'recursive':'false'})[0], 400)
        status, body = post('/api/library/roots', {'path':str(self.media), 'consent':True, 'recursive':False})
        self.assertEqual(status, 200)
        item = self.index(body['root_id'])['first.png']['id']
        endpoint = '/api/library/history'
        self.assertEqual(post(endpoint, {'item_id':item}, token='wrong')[0], 403)
        self.assertEqual(post(endpoint, {'item_id':item}, request_origin='https://example.invalid')[0], 403)
        self.assertEqual(post(endpoint, {'item_id':item, 'path':'injection'})[0], 400)
        self.assertEqual(post(endpoint, {'item_id':True})[0], 400)
        self.assertEqual(post(endpoint, {'item_id':99999})[0], 404)
        self.assertEqual(post(endpoint, {'item_id':item}), (200, {'recorded':item}))
        with urllib.request.urlopen(origin+'/api/items?view=history') as response:
            self.assertEqual(json.load(response)['items'][0]['id'], item)

    def test_purge_inactive_root_removes_all_dependents_preserves_files_and_never_reuses_root_id(self):
        import uuid
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
        from create_preview_fixture import png
        from page_index import PageIndex
        from page_text import PageTextIndex
        from tag_suggestions import TagSuggestions, TaggerInfo, TagProposal
        from ai_search import VectorStore

        media_b = self.base / 'media-b'
        media_b.mkdir()
        for p in (self.media / 'first.png', self.media / 'second.png', self.media / 'nested/third.png', media_b / 'keep.png'):
            p.write_bytes(png(color=(20, 40, 60)))
        before_files = {str(p.relative_to(self.base)): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.base.rglob('*.png')}

        root_a = self.catalog.add_root(str(self.media))
        root_b = self.catalog.add_root(str(media_b))
        items_a = self.index(root_a)
        items_b = self.index(root_b)
        item_a = items_a['first.png']['id']
        item_b = items_b['keep.png']['id']
        self.catalog.update([item_a], {'tags': ['purge-tag'], 'shelf': 'purge-shelf', 'favorite': True})
        self.catalog.update([item_b], {'tags': ['keep-tag'], 'shelf': 'keep-shelf', 'favorite': True})
        self.catalog.record_view(item_a)
        self.catalog.record_view(item_b)
        with self.catalog.connect() as db:
            db.execute("INSERT INTO reader_progress(item_id,revision,page,mode) VALUES(?,?,0,'single')", (item_a, 'a' * 64))
            db.execute("INSERT INTO reader_progress(item_id,revision,page,mode) VALUES(?,?,0,'single')", (item_b, 'b' * 64))

        vectors = VectorStore(self.base / 'catalog.sqlite')
        vectors.put(item_a, 'a' * 64, {'text': [1.0] + [0.0] * (vectors.dimension - 1)})
        vectors.put(item_b, 'b' * 64, {'text': [1.0] + [0.0] * (vectors.dimension - 1)})

        class FakeTagger:
            info = TaggerInfo('fake', '1', 'model', 'rev', 'prep')
            def suggest(self, source, cancelled):
                return [TagProposal('cand-tag', 'reason')]

        suggestions = TagSuggestions(self.catalog, FakeTagger())
        suggestions.generate(item_a, uuid.uuid4().hex)
        suggestions.generate(item_b, uuid.uuid4().hex)

        class FakeExtractor:
            class info:
                @staticmethod
                def record():
                    return {'adapter': 'fake', 'version': '1', 'model': 'm', 'model_revision': 'r', 'preprocessing': 'p'}
            def extract(self, payload, cancelled):
                return '抽出テキスト'

        pages = PageIndex(self.catalog)
        pages.refresh(item_a)
        pages.refresh(item_b)
        snap_a = pages.list(item_a)
        snap_b = pages.list(item_b)
        texts = PageTextIndex(self.catalog, pages, FakeExtractor())
        texts.generate(item_a, [snap_a['pages'][0]['page_id']], snap_a['source_revision'], uuid.uuid4().hex)
        texts.generate(item_b, [snap_b['pages'][0]['page_id']], snap_b['source_revision'], uuid.uuid4().hex)

        # Active root cannot be purged
        with self.assertRaisesRegex(ValueError, 'Unregister the root before purging'):
            self.catalog.purge_inactive_root(root_a, consent=True)
        # Missing consent rejected
        self.catalog.unregister_root(root_a)
        with self.assertRaisesRegex(ValueError, 'Explicit folder purge consent required'):
            self.catalog.purge_inactive_root(root_a, consent=False)

        purged = self.catalog.purge_inactive_root(root_a, consent=True)
        self.assertEqual(purged, {'purged': root_a, 'removed_items': 3, 'removed_locations': 3})
        with self.assertRaises(KeyError):
            self.catalog.get(item_a)
        # Active root B and its records remain intact
        self.assertEqual(self.catalog.get(item_b)['tags'], ['keep-tag'])
        self.assertEqual([r['id'] for r in self.catalog.search(view='history')['items']], [item_b])
        self.assertEqual(texts.search('抽出テキスト')['total'], 1)

        # Registering a new folder or re-adding self.media never reuses root_a's ID
        media_c = self.base / 'media-c'
        media_c.mkdir()
        root_c = self.catalog.add_root(str(media_c))
        self.assertGreater(root_c, max(root_a, root_b))
        root_a_readded = self.catalog.add_root(str(self.media))
        self.assertGreater(root_a_readded, root_c)
        # Any stale scope referencing old root_a is rejected, never broadened or mapped to root_c
        with self.assertRaisesRegex(ValueError, 'Unknown registered root'):
            self.catalog.search(root_ids=[root_a])

        after_files = {str(p.relative_to(self.base)): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.base.rglob('*.png')}
        self.assertEqual(before_files, after_files)

    def test_http_purge_inactive_root_contract(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), production_handler(self.catalog, 'fixture-token'))
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f'http://127.0.0.1:{server.server_port}'
        def post(path, data, token='fixture-token'):
            request = urllib.request.Request(origin+path, json.dumps(data).encode(), headers={'Content-Type':'application/json', 'Origin':origin, 'X-Aredoko-Token':token})
            try:
                with urllib.request.urlopen(request) as response: return response.status, json.load(response)
            except urllib.error.HTTPError as error:
                with error: return error.code, json.load(error)
        root = self.catalog.add_root(str(self.media))
        self.index(root)
        self.assertEqual(post('/api/library/roots/purge', {'root_id': root, 'consent': True}, token='bad')[0], 403)
        self.assertEqual(post('/api/library/roots/purge', {'root_id': root, 'consent': True})[0], 400)
        self.catalog.unregister_root(root)
        self.assertEqual(post('/api/library/roots/purge', {'root_id': root, 'consent': False})[0], 400)
        self.assertEqual(post('/api/library/roots/purge', {'root_id': root, 'consent': True, 'extra': 1})[0], 400)
        status, payload = post('/api/library/roots/purge', {'root_id': root, 'consent': True})
        self.assertEqual((status, payload['purged'], payload['removed_items']), (200, root, 3))
        self.assertEqual(post('/api/library/roots/purge', {'root_id': root, 'consent': True})[0], 404)

    def test_animated_gif_webp_apng_large_54mb_and_representative_frame_ai_indexing(self):
        import io
        import struct
        import zlib
        from PIL import Image
        from previews import PreviewReader, MAX_IMAGE_BYTES
        from ai_search import AISearch

        anim_dir = self.base / 'anim-media'
        anim_dir.mkdir()
        f0 = Image.new('RGBA', (64, 64), (220, 30, 30, 255))
        f1 = Image.new('RGBA', (64, 64), (30, 190, 40, 255))
        f2 = Image.new('RGBA', (64, 64), (30, 50, 220, 255))

        for name, fmt in [('sample.gif', 'GIF'), ('sample.webp', 'WEBP'), ('sample.png', 'PNG')]:
            f0.save(anim_dir / name, format=fmt, save_all=True, append_images=[f1, f2], duration=[120, 180, 240], loop=0)

        # Build a ~54,802KB (56,117,248+ bytes) APNG with 3 real frames
        apng_bytes = (anim_dir / 'sample.png').read_bytes()
        iend_pos = apng_bytes.rfind(b'\x00\x00\x00\x00IEND')
        pad_len = 54802 * 1024 - len(apng_bytes)
        pad_payload = b'A' * pad_len
        ancillary = struct.pack('>I4s', len(pad_payload), b'prIv') + pad_payload + struct.pack('>I', zlib.crc32(b'prIv' + pad_payload))
        large_apng = anim_dir / 'large-54mb.apng'
        large_apng.write_bytes(apng_bytes[:iend_pos] + ancillary + apng_bytes[iend_pos:])
        self.assertGreaterEqual(large_apng.stat().st_size, 54802 * 1024)

        before_files = {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in anim_dir.iterdir()}
        root = self.catalog.add_root(str(anim_dir))
        items = self.index(root)
        self.assertEqual(set(items), {'sample.gif', 'sample.webp', 'sample.png', 'large-54mb.apng'})

        reader = PreviewReader(self.catalog)
        for name in ('sample.gif', 'sample.webp', 'sample.png', 'large-54mb.apng'):
            item_id = items[name]['id']
            manifest = reader.image_manifest(item_id)
            self.assertTrue(manifest['animated'], name)
            self.assertEqual(manifest['frame_count'], 3, name)
            self.assertEqual(manifest['representative_frame'], 1, name)
            self.assertEqual(len(manifest['durations_ms']), 3, name)
            # Verify each frame decodes to the expected distinct color (red, green, blue)
            colors = []
            for idx in range(3):
                frame_png, frame_mime = reader.image_frame(item_id, idx, manifest['revision'])
                self.assertEqual(frame_mime, 'image/png')
                self.assertLessEqual(len(frame_png), MAX_IMAGE_BYTES)
                with Image.open(io.BytesIO(frame_png)) as decoded:
                    colors.append(decoded.convert('RGB').getpixel((32, 32)))
            self.assertGreater(colors[0][0], 180)  # Frame 0 is red
            self.assertGreater(colors[1][1], 150)  # Frame 1 (representative) is green
            self.assertGreater(colors[2][2], 180)  # Frame 2 is blue

            # Direct preview for the 54.8MB APNG stays bounded <= 8MiB
            preview_data, _ = reader.read(item_id)
            self.assertLessEqual(len(preview_data), MAX_IMAGE_BYTES)

            # Representative frame for AI cover / tag_input is frame 1 (green), not frame 0 (red)
            cover_bytes, cover_mime = reader.read_cover(item_id)
            self.assertEqual(cover_mime, 'image/png')
            with Image.open(io.BytesIO(cover_bytes)) as cov_img:
                r_val, g_val, b_val = cov_img.convert('RGB').getpixel((32, 32))
                self.assertGreater(g_val, max(r_val, b_val))

        # Verify AI indexing uses the representative frame for animated images
        seen_pixels = {}
        class ColorEncoder:
            available = True
            resident = False
            device = 'cpu'
            def encode(self, kind, value):
                dim = 768
                if kind in ('document', 'query'):
                    return [1.0] + [0.0] * (dim - 1)
                with Image.open(io.BytesIO(value)) as im:
                    px = im.convert('RGB').getpixel((32, 32))
                seen_pixels[len(seen_pixels)] = px
                # Vector points along axis 1 if green-dominant (representative frame 1)
                return ([0.0, 1.0] if px[1] > max(px[0], px[2]) else [1.0, 0.0]) + [0.0] * (dim - 2)
            def release(self):
                return {'released': False, 'resident': False}
            def close(self):
                pass

        ai = AISearch(self.catalog, ColorEncoder())
        self.addCleanup(ai.close)
        ai.start(scope={'root_ids': [root], 'kind': 'image', 'shelf': None})
        ai.worker.join(15)
        self.assertEqual(ai.status()['state'], 'complete')
        self.assertEqual(ai.status()['indexed'], 4)
        self.assertEqual(len(seen_pixels), 4)
        for px in seen_pixels.values():
            self.assertGreater(px[1], max(px[0], px[2]))

        # Verify HTTP routes for /manifest and /frames/<n>
        server = ThreadingHTTPServer(('127.0.0.1', 0), production_handler(self.catalog, 'fixture-token', ai=ai))
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f'http://127.0.0.1:{server.server_port}'
        large_id = items['large-54mb.apng']['id']
        req = urllib.request.Request(f'{origin}/api/library/preview/{large_id}/manifest', headers={'X-Aredoko-Token': 'fixture-token'})
        with urllib.request.urlopen(req) as resp:
            http_manifest = json.load(resp)
        self.assertTrue(http_manifest['animated'])
        self.assertEqual(http_manifest['frame_count'], 3)
        frame_req = urllib.request.Request(
            f"{origin}/api/library/preview/{large_id}/frames/2?revision={http_manifest['revision']}",
            headers={'X-Aredoko-Token': 'fixture-token'})
        with urllib.request.urlopen(frame_req) as resp:
            self.assertEqual(resp.headers['Content-Type'], 'image/png')
            frame2_bytes = resp.read()
        with Image.open(io.BytesIO(frame2_bytes)) as f2_img:
            self.assertGreater(f2_img.convert('RGB').getpixel((32, 32))[2], 180)

        after_files = {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in anim_dir.iterdir()}
        self.assertEqual(before_files, after_files)

    def test_video_content_ai_indexing_ranks_and_returns_timecoded_match(self):
        import io
        import shutil
        import subprocess
        from PIL import Image
        from ai_search import AISearch

        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg or not shutil.which('ffprobe'):
            self.skipTest('ffmpeg/ffprobe unavailable')

        vid_dir = self.base / 'video-ai'
        vid_dir.mkdir()
        clip_path = vid_dir / 'red_then_blue.mp4'
        # 0.0..1.0s is red, 1.0..2.0s is blue
        subprocess.run([
            ffmpeg, '-nostdin', '-v', 'error', '-f', 'lavfi',
            '-i', 'color=c=red:s=320x180:d=1[r];color=c=blue:s=320x180:d=1[b];[r][b]concat=n=2:v=1:a=0',
            '-threads', '1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
            str(clip_path)
        ], check=True, timeout=15)
        before_stat = (clip_path.stat().st_size, clip_path.stat().st_mtime_ns)

        root = self.catalog.add_root(str(vid_dir))
        items = self.index(root)
        vid_id = items['red_then_blue.mp4']['id']

        class VideoColorEncoder:
            available = True
            resident = False
            device = 'cpu'
            def encode(self, kind, value):
                dim = 768
                if kind == 'document':
                    return [0.0, 0.0, 1.0] + [0.0] * (dim - 3)
                if kind == 'query':
                    if '青' in value:
                        return [0.0, 1.0, 0.0] + [0.0] * (dim - 3)
                    return [1.0, 0.0, 0.0] + [0.0] * (dim - 3)
                with Image.open(io.BytesIO(value)) as im:
                    r_val, g_val, b_val = im.convert('RGB').getpixel((160, 90))
                if b_val > r_val:
                    return [0.0, 1.0, 0.0] + [0.0] * (dim - 3)
                return [1.0, 0.0, 0.0] + [0.0] * (dim - 3)
            def release(self):
                return {'released': False, 'resident': False}
            def close(self):
                pass

        ai = AISearch(self.catalog, VideoColorEncoder())
        self.addCleanup(ai.close)
        ai.start(scope={'root_ids': [root], 'kind': 'video', 'shelf': None})
        ai.worker.join(20)
        self.assertEqual(ai.status()['state'], 'complete')
        self.assertEqual(ai.status()['indexed'], 1)

        # Query for red ('赤') matches the early frame (0ms)
        red_res = ai.search('赤い場面', kind='video', source='cover', scope={'root_ids': [root], 'kind': '', 'shelf': None})
        self.assertEqual(red_res['total'], 1)
        self.assertEqual(red_res['items'][0]['id'], vid_id)
        self.assertEqual(red_res['items'][0]['video_match_ms'], 0)

        # Query for blue ('青') matches the later frame (>= 1000ms)
        blue_res = ai.search('青い場面', kind='video', source='cover', scope={'root_ids': [root], 'kind': '', 'shelf': None})
        self.assertEqual(blue_res['total'], 1)
        self.assertEqual(blue_res['items'][0]['id'], vid_id)
        self.assertGreaterEqual(blue_res['items'][0]['video_match_ms'], 1000)

        self.assertEqual(before_stat, (clip_path.stat().st_size, clip_path.stat().st_mtime_ns))


if __name__ == '__main__': unittest.main()
