"""Parity, security-invariant and fallback tests for `app/native_accel.py` + `aredoko_native.dll`."""
from array import array
import hashlib
import io
import json
import math
import operator
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))

from PIL import Image, ImageOps
import ai_runtime
from ai_profiles import DEFAULT_PROFILE
from ai_vectors import normalized
from library_index import LibraryIndex
import managed_ai_runtime as managed
import native_accel
from previews import PreviewReader, PreviewUnavailable
from storage_lease import StoragePathError
import test_ai_runtime as runtime_fixtures
from thumbnail_cache import ThumbnailCache


def _quadrant_image():
    # Asymmetric 24x12 pixels with 4 distinct colored corners to catch any EXIF flip/rotate mistake.
    img = Image.new('RGB', (24, 12), (255, 0, 0))
    for y in range(12):
        for x in range(24):
            if y < 6 and x >= 12:
                img.putpixel((x, y), (0, 255, 0))
            elif y >= 6 and x < 12:
                img.putpixel((x, y), (0, 0, 255))
            elif y >= 6 and x >= 12:
                img.putpixel((x, y), (255, 255, 0))
    return img


class NativeAccelTests(unittest.TestCase):
    def setUp(self):
        if not native_accel.available():
            self.skipTest('aredoko_native.dll is not built')

    def test_availability_and_disable_env_toggle(self):
        self.assertTrue(native_accel.available())
        self.assertIsNotNone(native_accel.loaded_path())
        with patch.dict(os.environ, {'AREDOKO_DISABLE_NATIVE_ACCEL': '1'}):
            self.assertFalse(native_accel.available())
        self.assertTrue(native_accel.available())

    def test_vector_scoring_bit_for_bit_parity_and_rejection(self):
        rng = random.Random(20261121)
        dim = 768
        queries = [normalized([rng.uniform(-1.0, 1.0) for _ in range(dim)], dim) for _ in range(4)]
        raw_vecs = []
        expected_no_norm = []
        expected_norm = []
        for idx in range(600):
            if idx == 10:
                vals = [0.0] * dim  # zero norm -> invalid
            elif idx == 20:
                vals = [1.0] + [0.0] * (dim - 2) + [float('nan')]
            elif idx == 30:
                vals = [float('inf'), -float('inf')] + [0.0] * (dim - 2)
            elif idx == 40:
                vals = [0.5] + [0.0] * (dim - 1)  # bad norm -> invalid
            else:
                base = normalized([rng.uniform(-1.0, 1.0) for _ in range(dim)], dim)
                if idx % 3 == 0:
                    # Slightly off-unit within 1e-4 so normalize_vec=True divides by norm.
                    base = [x * 1.00003 for x in base]
                vals = base
            blob = array('f', vals).tobytes()
            raw_vecs.append(blob)

            arr = array('f'); arr.frombytes(blob)
            sq = sum(map(operator.mul, arr, arr))
            is_valid = math.isfinite(sq) and abs(sq - 1.0) <= 1e-4
            if not is_valid:
                expected_no_norm.append((0, 0.0, 0))
                expected_norm.append((0, 0.0, 0))
            else:
                best_s = None; best_q = 0
                for qi, q in enumerate(queries):
                    s = sum(map(operator.mul, q, arr))
                    if best_s is None or s > best_s:
                        best_s = s; best_q = qi
                expected_no_norm.append((1, best_s, best_q))

                norm = math.sqrt(sq)
                normed = [v / norm for v in arr]
                s0 = sum(map(operator.mul, queries[0], normed))
                expected_norm.append((1, s0, 0))

        packed = b''.join(raw_vecs)
        scores, best_q, valid = native_accel.score_f32_batch(queries, packed, len(raw_vecs), dim, normalize_vec=False)
        for idx, (ev, es, eq) in enumerate(expected_no_norm):
            self.assertEqual(valid[idx], ev, idx)
            if ev:
                self.assertEqual(best_q[idx], eq, idx)
                self.assertEqual(scores[idx].hex(), es.hex(), idx)

        scores_n, _, valid_n = native_accel.score_f32_batch([queries[0]], packed, len(raw_vecs), dim, normalize_vec=True)
        for idx, (ev, es, _) in enumerate(expected_norm):
            self.assertEqual(valid_n[idx], ev, idx)
            if ev:
                self.assertEqual(scores_n[idx].hex(), es.hex(), idx)

    def test_thumbnail_formats_exif_orientations_and_fallbacks(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td); media = base / 'media'; media.mkdir()
            src_img = _quadrant_image()
            for fmt, ext in (('JPEG', '.jpg'), ('PNG', '.png'), ('WEBP', '.webp'), ('BMP', '.bmp')):
                buf = io.BytesIO(); src_img.save(buf, format=fmt)
                (media / f'sample{ext}').write_bytes(buf.getvalue())
            for orient in range(1, 9):
                buf = io.BytesIO(); exif = src_img.getexif(); exif[274] = orient
                src_img.save(buf, format='JPEG', exif=exif, quality=95)
                (media / f'exif_{orient}.jpg').write_bytes(buf.getvalue())

            from production import ProductionCatalog
            cat = ProductionCatalog(base / 'cat.sqlite'); self.addCleanup(cat.close)
            root = cat.add_root(str(media)); cat.index.scan(root); cat.sync_index()
            items = {r['title']: r['id'] for r in cat.search()['items']}
            cache = ThumbnailCache(PreviewReader(cat)); self.addCleanup(cache.close)

            # Check formats & no-upscale
            for name in ('sample.jpg', 'sample.png', 'sample.webp', 'sample.bmp'):
                out_png = cache.read(items[name], edge=128)
                with Image.open(io.BytesIO(out_png)) as im:
                    self.assertEqual(im.format, 'PNG')
                    self.assertEqual(im.mode, 'RGBA')
                    self.assertEqual(im.size, (24, 12))

            # Check ALL 8 EXIF orientations match Pillow exif_transpose pixel corner dominance & dimensions
            for orient in range(1, 9):
                key = f'exif_{orient}.jpg'
                rust_png = cache.read(items[key], edge=128)
                cache.cache.clear(); cache.bytes = 0
                with patch.dict(os.environ, {'AREDOKO_DISABLE_NATIVE_ACCEL': '1'}):
                    py_png = cache.read(items[key], edge=128)
                with Image.open(io.BytesIO(rust_png)) as r_im, Image.open(io.BytesIO(py_png)) as p_im:
                    self.assertEqual(r_im.size, p_im.size, f'orientation {orient} size')
                    for px, py in ((2, 2), (r_im.width - 3, 2), (2, r_im.height - 3), (r_im.width - 3, r_im.height - 3)):
                        rp = r_im.getpixel((px, py)); pp = p_im.getpixel((px, py))
                        diff = sum(abs(a - b) for a, b in zip(rp, pp))
                        self.assertLess(diff, 24, f'orientation {orient} pixel ({px},{py}) rust={rp} py={pp}')

            # Downscale test
            big = Image.new('RGB', (800, 400), (10, 80, 200))
            big_buf = io.BytesIO(); big.save(big_buf, format='JPEG')
            (media / 'big.jpg').write_bytes(big_buf.getvalue())
            cat.index.scan(root); cat.sync_index()
            big_id = next(r['id'] for r in cat.search()['items'] if r['title'] == 'big.jpg')
            rendered = cache.read(big_id, edge=256)
            with Image.open(io.BytesIO(rendered)) as rim:
                self.assertEqual(rim.size, (256, 128))
                self.assertEqual(rim.mode, 'RGBA')

            # Decompression bomb rejection
            with self.assertRaises(native_accel.NativeImageTooLarge):
                native_accel.render_thumbnail(big_buf.getvalue(), 256, 1000, 8 * 1024 * 1024)

            # 200 iterations repeated call stability check
            raw_big = big_buf.getvalue()
            for _ in range(200):
                out = native_accel.render_thumbnail(raw_big, 256, 16_000_000, 8 * 1024 * 1024)
                self.assertTrue(out.startswith(b'\x89PNG'))

    def test_scanner_parity_with_python_and_cancellation(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            media = base / '日本語フォルダ'
            (media / 'sub/deep').mkdir(parents=True)
            (media / 'ignored_dir').mkdir()
            (media / 'a.png').write_bytes(b'png1')
            (media / 'sub/b.jpg').write_bytes(b'jpg22')
            (media / 'sub/deep/c.cbz').write_bytes(b'cbz333')
            (media / 'ignored_dir/skip.png').write_bytes(b'x')
            (media / 'notes.txt').write_bytes(b'ignore me')
            books = base / 'books'
            (books / 'vol1').mkdir(parents=True)
            (books / 'vol1/01.png').write_bytes(b'p1')
            (books / 'vol1/02.png').write_bytes(b'p2')

            outside = base / 'outside'; outside.mkdir()
            (outside / 'secret.jpg').write_bytes(b'never')
            linked = 0
            try:
                (media / 'link_dir').symlink_to(outside, target_is_directory=True)
                linked += 1
            except OSError:
                pass

            rust_db = LibraryIndex(base / 'rust.sqlite')
            py_db = LibraryIndex(base / 'py.sqlite')
            r1 = rust_db.add_root(media, excludes=['ignored_dir'])
            r2 = py_db.add_root(media, excludes=['ignored_dir'])
            b1 = rust_db.add_root(books, folder_books=True)
            b2 = py_db.add_root(books, folder_books=True)

            rep_rust = rust_db.scan(r1)
            rep_rust_b = rust_db.scan(b1)
            with patch.dict(os.environ, {'AREDOKO_DISABLE_NATIVE_ACCEL': '1'}):
                rep_py = py_db.scan(r2)
                rep_py_b = py_db.scan(b2)

            self.assertEqual(rep_rust['added'], rep_py['added'])
            self.assertEqual(rep_rust['ignored_files'], rep_py['ignored_files'])
            self.assertEqual(rep_rust['skipped_links'], linked)
            self.assertEqual(rep_rust['skipped_links'], rep_py['skipped_links'])
            self.assertEqual(rep_rust_b['added'], rep_py_b['added'])

            rust_rows = [(x['relative_path'], x['kind'], x['size_bytes'], x['mtime_ns']) for x in rust_db.locations(r1)['items']]
            py_rows = [(x['relative_path'], x['kind'], x['size_bytes'], x['mtime_ns']) for x in py_db.locations(r2)['items']]
            self.assertEqual(rust_rows, py_rows)

            rust_brows = [(x['relative_path'], x['kind'], x['size_bytes'], x['mtime_ns']) for x in rust_db.locations(b1)['items']]
            py_brows = [(x['relative_path'], x['kind'], x['size_bytes'], x['mtime_ns']) for x in py_db.locations(b2)['items']]
            self.assertEqual(rust_brows, py_brows)

            with self.assertRaises(InterruptedError):
                rust_db.scan(r1, cancelled=lambda: True)

    def test_scanner_skips_real_windows_access_denied_and_supports_long_paths(self):
        if os.name != 'nt':
            self.skipTest('Windows ACL and \\\\?\\ path test is Windows-only')
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            media = base / 'drive_root'
            media.mkdir()
            (media / 'visible.png').write_bytes(b'ok')

            # Create a path > 265 chars using \\?\ so native scanner exercises extended wide paths.
            seg = 'd' * 75
            deep_dir_str = str(media / seg / seg / seg / seg)
            ext_deep_dir = '\\\\?\\' + os.path.abspath(deep_dir_str)
            os.makedirs(ext_deep_dir, exist_ok=True)
            ext_deep_file = ext_deep_dir + '\\deep.png'
            with open(ext_deep_file, 'wb') as fh:
                fh.write(b'deep')
            self.assertGreater(len(os.path.abspath(deep_dir_str) + '\\deep.png'), 260)

            def _cleanup_deep():
                try:
                    os.remove(ext_deep_file)
                except OSError:
                    pass
                cur = ext_deep_dir
                for _ in range(4):
                    try:
                        os.rmdir(cur)
                    except OSError:
                        break
                    cur = cur.rsplit('\\', 1)[0]
            self.addCleanup(_cleanup_deep)

            locked = media / 'System Volume Information'
            locked.mkdir()
            (locked / 'hidden.png').write_bytes(b'secret')

            # Deny read/list permission on `locked` for Everyone (*S-1-1-0).
            acl_applied = subprocess.run(
                ['icacls', str(locked), '/deny', '*S-1-1-0:(OI)(CI)(R)'],
                capture_output=True, text=True, check=False,
            )
            def _restore_acl():
                subprocess.run(
                    ['icacls', str(locked), '/remove:d', '*S-1-1-0'],
                    capture_output=True, text=True, check=False,
                )
            self.addCleanup(_restore_acl)

            native_res = native_accel.scan_tree(
                media, None, (), recursive=True, folder_books=False,
            )
            native_rels = {rel for rel, _, _, _ in native_res.items}
            self.assertIn('visible.png', native_rels)
            expected_deep_rel = f'{seg}/{seg}/{seg}/{seg}/deep.png'
            self.assertIn(expected_deep_rel, native_rels)

            if acl_applied.returncode == 0:
                try:
                    os.listdir(locked)
                    acl_enforced = False
                except PermissionError:
                    acl_enforced = True
                if acl_enforced:
                    self.assertIn(('System Volume Information', True), native_res.skipped_access_denied)
                    self.assertNotIn('System Volume Information/hidden.png', native_rels)

                    rust_db = LibraryIndex(base / 'rust.sqlite')
                    py_db = LibraryIndex(base / 'py.sqlite')
                    r1 = rust_db.add_root(media)
                    r2 = py_db.add_root(media)
                    rep_rust = rust_db.scan(r1)
                    with patch.dict(os.environ, {'AREDOKO_DISABLE_NATIVE_ACCEL': '1'}):
                        try:
                            rep_py = py_db.scan(r2)
                        except OSError:
                            rep_py = None
                    self.assertEqual(rep_rust['skipped_access_denied'], 1)
                    self.assertEqual(
                        rep_rust['access_denied_entries'],
                        [{'relative_path': 'System Volume Information', 'is_dir': True}],
                    )
                    if rep_py is not None:
                        self.assertEqual(rep_rust['skipped_access_denied'], rep_py['skipped_access_denied'])
                        self.assertEqual(rep_rust['access_denied_entries'], rep_py['access_denied_entries'])

    def test_runtime_verification_parity_callbacks_and_security_guards(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            pack = runtime_fixtures.fixture(base / 'pack')
            extra = pack / 'Lib/site-packages/generated'
            extra.mkdir()
            for i in range(80):
                (extra / f'{i:03}.py').write_bytes(b'Generated content ' + str(i).encode())
            (extra / 'large.bin').write_bytes(b'Generated data' * 100000)
            manifest = runtime_fixtures.seal(pack)

            owner = threading.get_ident()
            calls = []
            def progress(val):
                calls.append((threading.get_ident(), val.copy()))

            info = ai_runtime.inspect_runtime(pack, verify=True, progress=progress)
            self.assertEqual(info['verification'], 'full')
            self.assertTrue(all(tid == owner for tid, _ in calls))
            self.assertEqual(calls[0][1]['files_done'], 0)
            self.assertEqual(calls[-1][1]['files_done'], len(manifest['entries']))
            self.assertEqual(calls[-1][1]['bytes_done'], manifest['total_bytes'])
            self.assertEqual([v['files_done'] for _, v in calls], sorted(v['files_done'] for _, v in calls))
            self.assertEqual([v['bytes_done'] for _, v in calls], sorted(v['bytes_done'] for _, v in calls))

            # Observer error preserved
            def fail_progress(val):
                if val['files_done'] >= 1:
                    raise LookupError('observer boom')
            with self.assertRaisesRegex(LookupError, 'observer boom'):
                ai_runtime.inspect_runtime(pack, verify=True, progress=fail_progress)

            # Cancellation works cleanly
            stop = threading.Event()
            def stop_on_one(val):
                if val['files_done'] >= 1:
                    stop.set()
            with self.assertRaisesRegex(RuntimeError, 'cancelled'):
                ai_runtime.inspect_runtime(pack, verify=True, cancelled=stop.is_set, progress=stop_on_one)

            # Corruption rejected
            target = extra / '040.py'
            orig = target.read_bytes()
            target.write_bytes(b'z' * len(orig))
            with self.assertRaisesRegex(ValueError, 'file changed'):
                ai_runtime.inspect_runtime(pack, verify=True)
            target.write_bytes(orig)

            # Hardlink rejected
            alias = base / 'hardlink_alias.py'
            try:
                os.link(target, alias)
            except OSError:
                alias = None
            if alias is not None:
                with self.assertRaisesRegex(StoragePathError, 'Hardlinked'):
                    ai_runtime.inspect_runtime(pack, verify=True)
                alias.unlink()

            # Unlisted file rejected
            rogue = pack / 'unlisted_native_test.py'
            rogue.write_bytes(b'rogue')
            with self.assertRaisesRegex(ValueError, 'Unlisted'):
                ai_runtime.inspect_runtime(pack, verify=True)
            rogue.unlink()

            # Re-verify still passes cleanly
            self.assertEqual(ai_runtime.inspect_runtime(pack, verify=True)['verification'], 'full')

    def test_portable_package_places_native_dll_outside_bin_inventory(self):
        import test_portable_startup as portable_tests
        import test_release_staging as staging
        import portable_frontend as portable
        import release_runtime as runtime

        fixture = portable_tests.PortableStagingTests()
        staging.ReleaseStagingTests.setUp(fixture)
        self.addCleanup(fixture.temp.cleanup)
        frontend, bootstrap = portable_tests.PortableStagingTests.source(fixture)
        _, media = staging.ReleaseStagingTests.runtime(fixture)
        helper = fixture.base / 'PythonSetup.exe'
        helper.write_bytes(portable_tests.pe_fixture())
        (fixture.repo / 'tools/prepare_basic_runtime.py').write_text('# generated setup fixture')
        fake_dll = fixture.base / 'aredoko_native.dll'
        fake_dll.write_bytes(b'MZ-generated-native-fixture')

        manifest = staging.release.package(
            fixture.output, skip_build=True, media_tools=media,
            portable_frontend=frontend, bootstrap=bootstrap,
            managed_python_setup=helper, native_dll=fake_dll,
        )
        paths = {row['path'] for row in manifest['entries']}
        self.assertIn('backend/native/aredoko_native.dll', paths)
        self.assertNotIn('bin/aredoko_native.dll', paths)
        self.assertFalse((fixture.output / 'bin/aredoko_native.dll').exists())
        runtime.verify_release(fixture.output)
        portable.inspect_portable(fixture.output / 'bin')
        pf = portable.PortableFrontend(fixture.output, manifest, 'selftest')
        self.assertTrue(pf.executable.is_file())


if __name__ == '__main__':
    unittest.main()
