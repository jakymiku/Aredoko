"""Generated video only. Native tool tests skip explicitly if tools are absent."""
import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
sys.path.insert(0, str(ROOT / 'tools'))
from create_preview_fixture import png
from production import ProductionCatalog
from production_server import production_handler
from previews import PreviewReader, PreviewUnavailable, PreviewBusyError
import video_previews as video

# Write raw bytes: print() in a Windows child translates "\n" to "\r\n".
RAW_PRINT = 'import os, sys; sys.stdout.buffer.write(%s); sys.stdout.flush()'


class VideoToolTests(unittest.TestCase):
    def test_probe_rejects_missing_invalid_multiple_or_huge_dimensions(self):
        for value in (None, [], {}, {'streams': []}, {'streams': [{}, {}]},
                      {'streams': [{'width': True, 'height': 1}]},
                      {'streams': [{'width': 0, 'height': 1}]},
                      {'streams': [{'width': 10000, 'height': 10000}]}):
            with self.subTest(value=value), self.assertRaises(video.VideoPreviewUnavailable):
                video._dimensions(json.dumps(value).encode())
        video._dimensions(b'{"streams":[{"width":4000,"height":4000}]}')

    def test_png_output_limits(self):
        video._validate_png(png())
        for data in (b'bad', png() + b'0' * video.MAX_FRAME_BYTES, png(257, 2)):
            with self.assertRaises(video.VideoPreviewUnavailable): video._validate_png(data)

    def test_missing_tools_and_windows_batch_wrappers_are_not_run(self):
        # This case exercises PATH lookup, independently of a test runner's
        # explicit bundled-tool location used by native generated-media cases.
        with patch.dict(os.environ):
            os.environ.pop('AREDOKO_MEDIA_TOOLS',None)
            for found in (None, 'ffmpeg.cmd', 'ffmpeg.BAT'):
                with patch.object(video.shutil, 'which', return_value=found):
                    with self.assertRaises(video.VideoPreviewUnavailable): video._executable('ffmpeg')

    def test_cache_is_bounded_by_revision_and_does_not_cache_failures(self):
        thumbnailer = video.VideoThumbnailer()
        with patch.object(video, '_executable', return_value='unused'), patch.object(video, '_run') as run:
            run.side_effect = [b'{"streams":[{"width":1,"height":1}]}', png()] * (video.VIDEO_CACHE_ENTRIES + 1)
            for i in range(video.VIDEO_CACHE_ENTRIES + 1): thumbnailer.read(io.BytesIO(), str(i))
            self.assertEqual(len(thumbnailer.cache), video.VIDEO_CACHE_ENTRIES)
            self.assertNotIn('0', thumbnailer.cache)
            self.assertEqual(thumbnailer.read(io.BytesIO(), '1'), png())
            self.assertEqual(run.call_count, 2 * (video.VIDEO_CACHE_ENTRIES + 1))
            run.side_effect = video.VideoPreviewUnavailable('fixture error')
            with self.assertRaises(video.VideoPreviewUnavailable): thumbnailer.read(io.BytesIO(), 'bad')
            self.assertNotIn('bad', thumbnailer.cache)

    def test_tool_arguments_use_only_handle_and_pipe_protocol(self):
        with patch.object(video, '_executable', side_effect=['probe', 'decode']), patch.object(video, '_run') as run:
            run.side_effect = [b'{"streams":[{"width":320,"height":180}]}', png()]
            file = io.BytesIO(b'fictional')
            video.VideoThumbnailer().read(file, 'revision')
            for call in run.call_args_list:
                args, source, limit, deadline = call.args
                self.assertIs(source, file)
                self.assertEqual(args[args.index('-i') + 1], 'pipe:0')
                self.assertEqual(args[args.index('-protocol_whitelist') + 1], 'pipe')
                self.assertNotIn('concat', args[args.index('-format_whitelist') + 1])
                self.assertEqual(args[args.index('-threads') + 1], '1')
                self.assertEqual(args[args.index('-max_pixels') + 1], str(video.MAX_VIDEO_PIXELS))
            self.assertEqual(run.call_args_list[0].args[3], run.call_args_list[1].args[3])

    def run_child(self, script, limit=64, seconds=3):
        with tempfile.TemporaryFile() as source:
            return video._run([sys.executable, '-c', script], source, limit, time.monotonic() + seconds)

    def test_bounded_output_kills_and_reaps_child(self):
        with self.assertRaisesRegex(video.VideoPreviewUnavailable, 'output exceeds'):
            self.run_child('import sys; sys.stdout.buffer.write(b"x"*1000000); sys.stdout.flush()')
        self.assertEqual(self.run_child(RAW_PRINT % 'b"ok\\n"'), b'ok\n')

    def test_deadline_kills_child_and_does_not_keep_a_worker(self):
        started = time.monotonic()
        with self.assertRaisesRegex(video.VideoPreviewUnavailable, 'deadline'):
            self.run_child('import time; time.sleep(60)', seconds=0.15)
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(self.run_child(RAW_PRINT % 'b"next\\n"'), b'next\n')

    def test_nonzero_exit_and_expired_deadline(self):
        with self.assertRaises(video.VideoPreviewUnavailable): self.run_child('raise SystemExit(7)')
        with self.assertRaises(video.VideoPreviewUnavailable): self.run_child('print("not run")', seconds=-1)

    def test_report_environment_is_not_inherited(self):
        with patch.dict(os.environ, {'FFREPORT': 'file=must-not-write.log'}):
            self.assertEqual(self.run_child(RAW_PRINT % 'str("FFREPORT" in os.environ).encode() + b"\\n"'), b'False\n')


class VideoBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.media = self.base / 'media'; self.media.mkdir()
        self.path = self.media / '動画 ; $(not-a-command).mp4'; self.path.write_bytes(b'generated placeholder')
        self.catalog = ProductionCatalog(self.base / 'catalog.sqlite'); self.addCleanup(self.catalog.close)
        self.root = self.catalog.add_root(str(self.media)); self.scan()
        self.item = self.catalog.search()['items'][0]['id']; self.reader = PreviewReader(self.catalog)

    def scan(self):
        self.catalog.index.scan(self.root); self.catalog.sync_index()

    def test_oversized_video_rejected_before_native_tools(self):
        # Exercise the boundary without allocating a real 32 GiB fixture.
        with self.path.open('wb') as file: file.truncate(1025)
        self.scan()
        with patch('previews.MAX_VIDEO_BYTES',1024),patch.object(self.reader.videos, 'read') as read:
            with self.assertRaises(PreviewUnavailable): self.reader.read(self.item)
            read.assert_not_called()

    def test_stale_excluded_disabled_and_missing_sources_not_sent_to_tools(self):
        with patch.object(self.reader.videos, 'read') as read:
            self.path.write_bytes(b'changed size')
            with self.assertRaises(PreviewUnavailable): self.reader.read(self.item)
            self.scan(); self.catalog.set_excludes(self.root, ['*.mp4'])
            with self.assertRaises(PreviewUnavailable): self.reader.read(self.item)
            self.catalog.set_excludes(self.root, []); self.catalog.unregister_root(self.root)
            with self.assertRaises(PreviewUnavailable): self.reader.read(self.item)
            self.catalog.add_root(str(self.media)); self.path.unlink()
            with self.assertRaises(OSError): self.reader.read(self.item)
            read.assert_not_called()

    def test_cached_video_revalidates_source_and_root(self):
        with patch.object(video, '_executable', return_value='unused'), patch.object(video, '_run') as run:
            run.side_effect = [b'{"streams":[{"width":1,"height":1}]}', png()]
            self.assertEqual(self.reader.read(self.item), (png(), 'image/png'))
            self.assertEqual(self.reader.read(self.item), (png(), 'image/png'))
            self.assertEqual(run.call_count, 2)
            self.catalog.set_excludes(self.root, ['*.mp4'])
            with self.assertRaises(PreviewUnavailable): self.reader.read(self.item)
            self.catalog.set_excludes(self.root, []); self.path.write_bytes(b'new')
            with self.assertRaises(PreviewUnavailable): self.reader.read(self.item)
            self.assertEqual(run.call_count, 2)

    def test_link_replacement_is_never_read(self):
        outside = self.base / 'outside.mp4'; outside.write_bytes(b'private fixture')
        self.path.unlink()
        try: self.path.symlink_to(outside)
        except OSError: self.skipTest('Symlink privilege unavailable')
        with patch.object(self.reader.videos, 'read') as read:
            with self.assertRaises(PreviewUnavailable): self.reader.read(self.item)
            read.assert_not_called()

    def test_mutation_during_decode_rejects_frame_and_releases_shared_slot(self):
        def mutate(file, revision): self.path.write_bytes(b'changed fixture'); return png()
        with patch.object(self.reader.videos, 'read', side_effect=mutate):
            with self.assertRaises(PreviewUnavailable): self.reader.read(self.item)
        self.assertTrue(self.reader.slots.acquire(blocking=False)); self.reader.slots.release()

    def test_handle_keeps_old_source_but_replacement_is_not_published(self):
        blocked = []
        def replace(file, revision):
            try: self.path.rename(self.media / 'old.mp4')
            except PermissionError:
                if os.name != 'nt': raise
                blocked.append(True)  # Windows: the open handle denies rename, so no swap occurs.
            else: self.path.write_bytes(b'new source')
            self.assertEqual(file.read(), b'generated placeholder')
            return png()
        with patch.object(self.reader.videos, 'read', side_effect=replace):
            if os.name == 'nt':
                self.assertEqual(self.reader.read(self.item), (png(), 'image/png'))
                self.assertEqual(blocked, [True])
                self.assertEqual(self.path.read_bytes(), b'generated placeholder')
            else:
                with self.assertRaises(PreviewUnavailable): self.reader.read(self.item)

    def test_busy_shared_with_reader_and_video_not_a_book(self):
        self.reader.slots.acquire(); self.reader.slots.acquire()
        try:
            with patch.object(self.reader.videos, 'read') as read:
                with self.assertRaises(PreviewBusyError): self.reader.read(self.item)
                read.assert_not_called()
        finally: self.reader.slots.release(); self.reader.slots.release()
        with self.assertRaises(PreviewUnavailable): self.reader.manifest(self.item)

    def test_http_auth_success_failure_and_busy_keep_existing_contract(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), production_handler(self.catalog, 'fixture-token'))
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        def request(token):
            return urllib.request.urlopen(urllib.request.Request(
                f'http://127.0.0.1:{server.server_port}/api/library/preview/{self.item}',
                headers={'X-Aredoko-Token': token}), timeout=5)
        with patch.object(video.VideoThumbnailer, 'read', return_value=png()) as read:
            with self.assertRaises(urllib.error.HTTPError) as caught: request('wrong')
            self.assertEqual(caught.exception.code, 403); caught.exception.close(); read.assert_not_called()
            with request('fixture-token') as response:
                self.assertEqual(response.headers['Content-Type'], 'image/png')
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertEqual(response.read(), png())
        for error, expected in ((video.VideoPreviewUnavailable('fixture'), 404), (PreviewBusyError('fixture'), 503)):
            with patch.object(video.VideoThumbnailer, 'read', side_effect=error):
                with self.assertRaises(urllib.error.HTTPError) as caught: request('fixture-token')
                self.assertEqual(caught.exception.code, expected); caught.exception.close()

    def test_video_playback_route_enforces_auth_boundaries_and_rejects_playlists_or_changes(self):
        image_path = self.media / 'still.png'; image_path.write_bytes(png())
        playlist_path = self.media / 'list.mp4'; playlist_path.write_bytes(b'#EXTM3U\nhttp://127.0.0.1/a.ts\n')
        self.catalog.index.scan(self.root); self.catalog.sync_index()
        items = {x['title']: x['id'] for x in self.catalog.search()['items']}
        server = ThreadingHTTPServer(('127.0.0.1', 0), production_handler(self.catalog, 'fixture-token'))
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        def get_video(suffix, token='fixture-token'):
            return urllib.request.urlopen(urllib.request.Request(
                f'http://127.0.0.1:{server.server_port}/api/library/video/{suffix}',
                headers={'X-Aredoko-Token': token}), timeout=5)
        with self.assertRaises(urllib.error.HTTPError) as caught: get_video(self.item, 'wrong')
        self.assertEqual(caught.exception.code, 403); caught.exception.close()
        for bad in ('0', '-1', str(2**63), f'{self.item}?x=1', f'{self.item}/extra'):
            with self.assertRaises(urllib.error.HTTPError) as caught: get_video(bad)
            self.assertEqual(caught.exception.code, 400); caught.exception.close()
        with get_video(self.item) as response:
            self.assertEqual(response.headers['Content-Type'], 'video/mp4')
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertEqual(response.read(), b'generated placeholder')
        for denied in (items['still.png'], items['list.mp4'], 999999):
            with self.assertRaises(urllib.error.HTTPError) as caught: get_video(denied)
            self.assertEqual(caught.exception.code, 404); caught.exception.close()
        self.path.write_bytes(b'modified after scan')
        with self.assertRaises(urllib.error.HTTPError) as caught: get_video(self.item)
        self.assertEqual(caught.exception.code, 409); caught.exception.close()


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Native FFmpeg tools unavailable')
class NativeVideoTests(unittest.TestCase):
    def test_anamorphic_small_portrait_and_unknown_sar_keep_display_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            for index, (size, sar, expected) in enumerate([
                    ('720x480', '8/9', (256, 192)),
                    ('80x60', '1/2', (40, 60)),
                    ('16x12', '2/1', (32, 12)),
                    ('360x720', '1/1', (128, 256)),
                    ('320x180', '0/1', (256, 144))]):
                with self.subTest(size=size, sar=sar):
                    path = Path(directory) / f'geometry-{index}.mp4'
                    subprocess.run([shutil.which('ffmpeg'), '-nostdin', '-v', 'error',
                        '-f', 'lavfi', '-i', f'color=c=red:s={size}:d=0.2',
                        '-vf', 'setsar=' + sar, '-threads', '1', '-c:v', 'mpeg4',
                        '-movflags', '+faststart', str(path)], check=True, timeout=10)
                    before = (path.read_bytes(), path.stat().st_mtime_ns)
                    with path.open('rb') as source: frame = video.VideoThumbnailer().read(source, str(index))
                    video._validate_png(frame)
                    self.assertEqual(struct.unpack_from('>II', frame, 16), expected)
                    self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)

    def test_generated_mp4_mkv_and_webm_first_frames_are_readonly(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); media = base / 'media'; media.mkdir()
            for suffix, codec, extra in (('.mp4', 'mpeg4', ['-movflags', '+faststart']),
                                         ('.mkv', 'ffv1', []), ('.webm', 'libvpx', [])):
                path = media / ('generated' + suffix)
                subprocess.run([shutil.which('ffmpeg'), '-nostdin', '-v', 'error',
                    '-f', 'lavfi', '-i', 'color=c=red:s=320x180:d=0.2', '-threads', '1',
                    '-c:v', codec, *extra, str(path)], check=True, timeout=10)
            before = {p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in media.iterdir()}
            catalog = ProductionCatalog(base / 'catalog.sqlite')
            try:
                root = catalog.add_root(str(media)); catalog.index.scan(root); catalog.sync_index()
                reader = PreviewReader(catalog)
                for item in catalog.search()['items']:
                    with self.subTest(title=item['title']):
                        frame, mime = reader.read(item['id']); video._validate_png(frame)
                        self.assertEqual(mime, 'image/png')
                        self.assertEqual(struct.unpack_from('>II', frame, 16), (256, 144))
                        self.assertEqual(frame[24:26], b'\x08\x02')  # RGB8; first pixel predictors are zero.
                        offset = 8; packed = b''
                        while offset < len(frame):
                            size = struct.unpack_from('>I', frame, offset)[0]
                            if frame[offset+4:offset+8] == b'IDAT': packed += frame[offset+8:offset+8+size]
                            offset += size + 12
                        pixel = zlib.decompress(packed)[1:4]
                        self.assertGreater(pixel[0], 240); self.assertLess(max(pixel[1:]), 10)
                self.assertEqual(before, {p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in media.iterdir()})
            finally: catalog.close()

    def test_corrupt_and_playlist_disguised_as_video_fail_without_fetching(self):
        requests = []
        class Sentinel(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                requests.append(self.path); self.send_response(200); self.end_headers()
        server = ThreadingHTTPServer(('127.0.0.1', 0), Sentinel)
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        with tempfile.TemporaryFile() as source:
            source.write(f'#EXTM3U\nhttp://127.0.0.1:{server.server_port}/must-not-fetch.ts\n'.encode()); source.seek(0)
            with self.assertRaises(video.VideoPreviewUnavailable): video.VideoThumbnailer().read(source, 'playlist')
        self.assertEqual(requests, [])
        with tempfile.TemporaryFile() as source:
            source.write(b'not a video'); source.seek(0)
            with self.assertRaises(video.VideoPreviewUnavailable): video.VideoThumbnailer().read(source, 'corrupt')


if __name__ == '__main__': unittest.main()
