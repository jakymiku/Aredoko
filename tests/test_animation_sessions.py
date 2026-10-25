"""Generated-only streaming, composition, ownership and authenticated API tests."""
import io
import json
import os
from pathlib import Path
import struct
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch, PropertyMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from animation_sessions import AnimationSessions, AnimationGone, AnimationBusy, IDLE_SECONDS
from previews import PreviewUnavailable, ReaderChanged
from production_server import production_handler, DisabledAI
from PIL import Image, GifImagePlugin
import test_image_formats as formats


def unpack(data):
    length = struct.unpack_from('<I', data)[0]
    header = json.loads(data[4:4 + length])
    body = memoryview(data)[4 + length:]
    frames = []
    for frame in header['frames']:
        size = frame['byte_length']
        frames.append((frame, bytes(body[:size])))
        body = body[size:]
    assert not body
    return header, frames


def generated(kind='PNG', count=3, loop=2, poster=False):
    frames = [Image.new('RGBA', (12, 8), (i * 3 % 256, i * 7 % 256, i * 11 % 256, 128 if kind == 'PNG' else 255))
              for i in range(count)]
    output = io.BytesIO()
    options = dict(format=kind, save_all=True, append_images=frames[1:], duration=[40 + i % 5 * 20 for i in range(count)])
    if loop is not None: options['loop'] = loop
    if poster:
        options['default_image'] = True
        options['append_images'] = frames
        Image.new('RGBA', (12, 8), 'white').save(output, **options)
    else: frames[0].save(output, **options)
    return output.getvalue()


class AnimationSessionTests(unittest.TestCase):
    setUp = formats.ImageFormatTests.setUp
    add = formats.ImageFormatTests.add

    def tearDown(self):
        if hasattr(self, 'owner'): self.owner.close()
        formats.ImageFormatTests.tearDown(self)

    def start(self, data=None, name='sample.png'):
        self.source, self.item = self.add(name, data or generated())
        self.info = self.reader.image_info(self.item)
        self.owner = AnimationSessions(self.reader)
        self.sid = 'a' * 32
        self.owner.open(self.item, self.info['revision'], self.sid)
        return self.owner.sessions[self.sid]

    def test_large_gif_probe_thumbnail_and_stream_do_not_require_original_byte_array(self):
        from thumbnail_cache import ThumbnailCache
        from image_animations import MAX_STREAM_IMAGE_BYTES
        source,item=self.add('large.gif',generated('GIF'))
        # Valid GIF comment sub-blocks make a real >72MiB source while retaining
        # tiny decoded frames. This proves source routing, not high-res FPS.
        with source.open('r+b') as file:
            file.seek(-1,os.SEEK_END);file.write(b'\x21\xfe')
            block=(b'\xff'+b'x'*255)*4096
            for _ in range(73):file.write(block)
            file.write(b'\x00;')
        self.catalog.index.scan(self.root);self.catalog.sync_index()
        before=source.stat()
        with patch.object(GifImagePlugin.GifImageFile,'n_frames',new_callable=PropertyMock,side_effect=AssertionError('whole animation scan')):
            info=self.reader.image_info(item)
            self.assertGreater(info['size_bytes'],72*1024*1024)
            with self.assertRaises(PreviewUnavailable):self.reader.read_original(item)
            thumbnails=ThumbnailCache(self.reader)
            try:self.assertTrue(thumbnails.read(item,128).startswith(b'\x89PNG'))
            finally:thumbnails.close()
            self.owner=AnimationSessions(self.reader)
            header,frames=unpack(self.owner.open_first(item,info['revision'],'c'*32))
            self.assertEqual(len(frames),1);self.assertEqual(frames[0][0]['index'],0)
            self.assertEqual(header['width'],12);self.assertEqual(header['height'],8)
        self.assertEqual(source.stat().st_mtime_ns,before.st_mtime_ns)
        self.owner.close()
        with source.open('r+b') as file:file.truncate(MAX_STREAM_IMAGE_BYTES+1)
        self.catalog.index.scan(self.root);self.catalog.sync_index()
        with self.assertRaises(PreviewUnavailable):self.reader.image_info(item)

    def test_combined_open_first_retains_ownership_and_sequential_cursor(self):
        self.start(generated('PNG',count=70,loop=2,poster=True))
        first,frames=unpack(self.owner.open_first(self.item,self.info['revision'],'b'*32))
        self.assertEqual([(m['sequence'],m['index'],m['cycle']) for m,_ in frames],[(0,0,0)])
        _,following=unpack(self.owner.pull('b'*32,2))
        self.assertEqual([m['sequence'] for m,_ in following],[1,2])
        with self.assertRaises(AnimationGone):self.owner.open_first(self.item,self.info['revision'],'b'*32)
        self.assertIn('b'*32,self.owner.sessions)  # Duplicate must not destroy old owner.
        self.owner.cancel('c'*32)
        with self.assertRaises(AnimationGone):self.owner.open_first(self.item,self.info['revision'],'c'*32)
        self.assertNotIn('c'*32,self.owner.sessions)
        with patch.object(self.reader,'validate_animation',side_effect=ReaderChanged('generated change')):
            with self.assertRaises(ReaderChanged):self.owner.open_first(self.item,self.info['revision'],'d'*32)
        self.assertNotIn('d'*32,self.owner.sessions)

    def test_first_pull_does_not_enumerate_or_reopen_decoder(self):
        data = generated('GIF', count=70, loop=1)
        with patch.object(GifImagePlugin.GifImageFile, 'n_frames', new_callable=PropertyMock, side_effect=AssertionError('whole animation scan')):
            with patch('PIL.Image.open', wraps=Image.open) as opened:
                decoder = self.start(data, 'renamed.webp')
                first, frames = unpack(self.owner.pull(self.sid, 1))
                self.assertEqual(len(frames), 1)
                self.assertEqual(decoder.sequence, 1)
                self.assertEqual(opened.call_count, 1)
                self.assertEqual(first['pixel_format'], 'bgra8')
                with patch('pathlib.Path.open', side_effect=AssertionError('source reopened')):
                    self.owner.pull(self.sid, 4)
                self.assertEqual(opened.call_count, 1)

    def test_more_than_64_frames_and_format_specific_two_plays(self):
        for kind, loop in [('PNG', 2), ('GIF', 1), ('WEBP', 2)]:
            with self.subTest(kind=kind):
                self.start(generated(kind, 70, loop), 'sample.' + kind.lower())
                frames = []
                for _ in range(40):
                    header, batch = unpack(self.owner.pull(self.sid, 4)); frames.extend(batch)
                    if header['done']: break
                self.assertTrue(header['done'])
                self.assertEqual(len(frames), 140)
                self.assertEqual([f[0]['sequence'] for f in frames], list(range(140)))
                self.assertEqual(frames[69][0]['index'], 69)
                self.assertEqual(frames[70][0]['index'], 0)
                self.assertEqual(frames[70][0]['cycle'], 1)
                self.owner.close()

    def test_apng_poster_alpha_durations_and_source_invariance(self):
        data = generated(poster=True)
        decoder = self.start(data)
        before = self.source.stat()
        header, frames = unpack(self.owner.pull(self.sid, 4))
        self.assertEqual(header['alpha'], 'premultiplied')
        self.assertEqual(header['stride'], 48)
        with Image.open(io.BytesIO(data)) as expected:
            for i, (meta, pixels) in enumerate(frames):
                expected.seek(i % 3 + 1)
                self.assertEqual(pixels, expected.convert('RGBA').convert('RGBa').tobytes('raw', 'BGRa'))
                self.assertEqual(meta['duration_ms'], [40, 60, 80][i % 3])
        self.assertEqual(self.source.read_bytes(), data)
        self.assertEqual(self.source.stat().st_mtime_ns, before.st_mtime_ns)
        self.owner.cancel(self.sid)
        self.assertTrue(decoder.file.closed)

    def test_apng_disposal_blend_matches_pillow_composited_pixels(self):
        frames = [Image.new('RGBA', (12, 8), (100, 20, 30, 255))]
        for color in [(0, 200, 0, 128), (0, 0, 200, 128)]:
            frame = Image.new('RGBA', (12, 8)); frame.paste(color, (2, 2, 6, 6)); frames.append(frame)
        out = io.BytesIO()
        frames[0].save(out, format='PNG', save_all=True, append_images=frames[1:], loop=1,
                       duration=[40, 60, 80], disposal=[0, 1, 2], blend=[0, 1, 1])
        data = out.getvalue(); self.start(data)
        _, actual = unpack(self.owner.pull(self.sid, 4))
        with Image.open(io.BytesIO(data)) as expected:
            for index, (_, pixels) in enumerate(actual):
                expected.seek(index)
                self.assertEqual(pixels, expected.convert('RGBA').convert('RGBa').tobytes('raw', 'BGRa'))

    def test_missing_loop_plays_once_and_infinite_loop_stays_bounded(self):
        self.start(generated('GIF', 3, None), 'sample.gif')
        header, frames = unpack(self.owner.pull(self.sid, 4))
        self.assertTrue(header['done']); self.assertEqual(len(frames), 3)
        self.owner.close()
        self.start(generated('PNG', 3, 0))
        for _ in range(10):
            header, frames = unpack(self.owner.pull(self.sid, 4))
            self.assertFalse(header['done']); self.assertEqual(len(frames), 4)
            self.assertLessEqual(sum(len(p) for _, p in frames), 128 * 1024 * 1024)
        self.assertFalse(hasattr(self.owner.sessions[self.sid], 'frames'))

    def test_scope_revocation_and_revision_change_close_owned_handle(self):
        for change in ('exclude', 'unregister', 'replace'):
            with self.subTest(change=change):
                # A new isolated catalog/root per change is unnecessary; restore root after test.
                decoder = self.start()
                if change == 'exclude': self.catalog.set_excludes(self.root, ['*.png'])
                elif change == 'unregister': self.catalog.unregister_root(self.root)
                else: self.source.write_bytes(generated(count=4))
                with self.assertRaises((PreviewUnavailable, ReaderChanged, AnimationGone)):
                    self.owner.pull(self.sid, 1)
                self.assertTrue(decoder.file.closed)
                self.assertNotIn(self.sid, self.owner.sessions)
                if change == 'exclude': self.catalog.set_excludes(self.root, [])
                if change == 'unregister':
                    with self.catalog.connect() as db: db.execute('UPDATE library_roots SET enabled=1 WHERE id=?', (self.root,))

    def test_cancel_in_flight_never_publishes_and_closes_handle(self):
        decoder = self.start(); entered = threading.Event(); release = threading.Event(); errors = []
        original = decoder.validate
        def delayed(revision):
            entered.set(); release.wait(3); original(revision)
        decoder.validate = delayed
        def pull():
            try: self.owner.pull(self.sid, 4)
            except Exception as ex: errors.append(ex)
        thread = threading.Thread(target=pull); thread.start(); self.assertTrue(entered.wait(2))
        self.owner.cancel(self.sid); release.set(); thread.join(5)
        self.assertFalse(thread.is_alive()); self.assertTrue(errors)
        self.assertTrue(decoder.file.closed)

    def test_concurrent_pull_rejected_without_destroying_session(self):
        decoder = self.start(); decoder.lock.acquire()
        try:
            with self.assertRaises(AnimationBusy): self.owner.pull(self.sid, 1)
            self.assertIn(self.sid, self.owner.sessions)
        finally: decoder.lock.release()

    def test_close_before_open_rejects_late_publication(self):
        self.start(); self.owner.cancel('b' * 32)
        with self.assertRaises(AnimationGone): self.owner.open(self.item, self.info['revision'], 'b' * 32)

    def test_idle_expiry_capacity_validation_and_shutdown(self):
        decoder = self.start()
        for sid in ('b' * 32, 'c' * 32): self.owner.open(self.item, self.info['revision'], sid)
        with self.assertRaises(AnimationBusy): self.owner.open(self.item, self.info['revision'], 'd' * 32)
        for invalid in (0, 5, True, '4'):
            with self.assertRaises(ValueError): self.owner.pull(self.sid, invalid)
        decoder.last_used -= IDLE_SECONDS + 1
        with self.assertRaises(AnimationGone): self.owner.pull(self.sid, 1)
        self.assertTrue(decoder.file.closed)
        self.owner.close()
        with self.assertRaises(AnimationGone): self.owner.open(self.item, self.info['revision'], 'e' * 32)

    def test_http_auth_strict_json_binary_order_and_close(self):
        self.start()
        handler = production_handler(self.catalog, 'fixture', ai=DisabledAI())
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        def post(action, body, token='fixture', raw=None):
            return urllib.request.urlopen(urllib.request.Request(origin + '/api/library/animation/' + action,
                data=(json.dumps(body).encode() if raw is None else raw),
                headers={'Origin': origin, 'X-Aredoko-Token': token, 'Content-Type': 'application/json'}), timeout=5)
        sid = 'f' * 32
        try:
            with post('open', {'item_id': self.item, 'revision': self.info['revision'], 'session_id': sid}) as response:
                self.assertEqual(json.load(response)['session_id'], sid)
            with post('next', {'session_id': sid, 'count': 1}) as response:
                self.assertEqual(response.headers.get_content_type(), 'application/vnd.aredoko.animation-frame-batch')
                self.assertEqual(unpack(response.read())[1][0][0]['sequence'], 0)
            for token, raw, expected in [('bad', None, 403), ('fixture', b'{"count":1,"count":2}', 400)]:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    post('next', {'session_id': sid, 'count': 1}, token, raw)
                self.assertEqual(error.exception.code, expected); error.exception.close()
            with post('close', {'session_id': sid}) as response: self.assertTrue(json.load(response)['closed'])
            with self.assertRaises(urllib.error.HTTPError) as error:
                post('open-first',{'item_id':self.item,'revision':self.info['revision'],'session_id':'e'*32},token='bad')
            self.assertEqual(error.exception.code,403);error.exception.close()
            self.assertNotIn('e'*32,handler.animations.sessions)
            with post('open-first',{'item_id':self.item,'revision':self.info['revision'],'session_id':'e'*32}) as response:
                header,frames=unpack(response.read());self.assertEqual(len(frames),1);self.assertEqual(frames[0][0]['sequence'],0)
                self.assertEqual(response.headers.get_content_type(),'application/vnd.aredoko.animation-frame-batch')
            with post('next',{'session_id':'e'*32,'count':1}) as response:self.assertEqual(unpack(response.read())[1][0][0]['sequence'],1)
            with post('close',{'session_id':'e'*32}) as response:self.assertTrue(json.load(response)['closed'])
            with self.assertRaises(urllib.error.HTTPError) as error: post('next', {'session_id': sid, 'count': 1})
            self.assertEqual(error.exception.code, 409); error.exception.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(5); handler.animations.close(); handler.setup_jobs.close()


if __name__ == '__main__': unittest.main()
