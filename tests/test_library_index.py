"""All filesystem tests use small fictional temporary fixtures, never private media."""
import errno
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from library_index import LibraryIndex


class LibraryIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.media = self.base / 'fictional'
        self.media.mkdir()
        self.db = self.base / 'index.sqlite'
        self.index = LibraryIndex(self.db)

    def touch(self, name, contents=b'hello'):
        file = self.media / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(contents)
        return file

    def test_registration_does_not_scan_and_media_files_unchanged(self):
        file = self.touch('絵/空の写真.JPG')
        initial = file.read_bytes()
        root_id = self.index.add_root(self.media)
        self.assertEqual(self.index.locations(root_id)['total'], 0)
        self.assertEqual(len(self.index.roots()), 1)
        self.assertEqual(self.index.roots()[0]['last_scanned_at'], None)
        self.assertTrue(self.index.roots()[0]['online'])
        report = self.index.scan(root_id)
        self.assertEqual((report['added'], report['discovered']), (1, 1))
        result = self.index.locations(root_id)['items'][0]
        self.assertEqual(result['relative_path'], '絵/空の写真.JPG')
        self.assertEqual(result['kind'], 'image')
        self.assertEqual(result['status'], 'present')
        self.assertEqual(file.read_bytes(), initial)
        self.assertEqual(file.stat().st_size, len(initial))
        self.assertTrue(self.index.roots()[0]['last_scanned_at'])

    def test_second_scan_is_incremental_and_preserves_identity(self):
        file = self.touch('本/物語.cbz', b'v1')
        root = self.index.add_root(self.media)
        self.index.scan(root)
        first = self.index.locations(root)['items'][0]
        unchanged = self.index.scan(root)
        self.assertEqual(unchanged['unchanged'], 1)
        self.assertEqual(unchanged['added'], 0)
        file.write_bytes(b'v2 longer')
        modified = self.index.scan(root)
        self.assertEqual(modified['changed'], 1)
        second = self.index.locations(root)['items'][0]
        self.assertEqual(first['id'], second['id'])
        self.assertNotEqual(first['size_bytes'], second['size_bytes'])
        self.assertEqual(self.index.locations(root)['total'], 1)

    def test_delete_restore_retains_record_and_id(self):
        file = self.touch('title.mp3')
        root = self.index.add_root(self.media)
        self.index.scan(root)
        id_before = self.index.locations(root)['items'][0]['id']
        file.unlink()
        self.assertEqual(self.index.scan(root)['missing'], 1)
        self.assertEqual(self.index.locations(root, status='missing')['total'], 1)
        self.touch('title.mp3')
        self.assertEqual(self.index.scan(root)['changed'], 1)
        self.assertEqual(self.index.locations(root, status='present')['items'][0]['id'], id_before)

    def test_exclusions_and_ignored_extensions(self):
        self.touch('cache/work.png')
        self.touch('books/story.cbz')
        self.touch('bookmarks.txt')
        self.touch('work.PSD')
        self.touch('.git/icon.png')
        self.touch('nested/unwanted.tmp')
        root = self.index.add_root(self.media, excludes=['cache', '*.tmp'])
        report = self.index.scan(root)
        self.assertEqual(report['added'], 2)
        self.assertEqual(report['ignored_files'], 1)
        self.assertEqual({r['kind'] for r in self.index.locations(root)['items']}, {'book', 'material'})

    def test_reexcluded_records_keep_metadata(self):
        self.touch('cache/art.png')
        root = self.index.add_root(self.media)
        self.index.scan(root)
        row = self.index.locations(root)['items'][0]
        self.index.set_excludes(root, ['cache'])
        report = self.index.scan(root)
        self.assertEqual(report['excluded'], 1)
        after = self.index.locations(root, status='excluded')['items'][0]
        self.assertEqual(row['id'], after['id'])
        self.assertEqual(row['size_bytes'], after['size_bytes'])

    def test_rules_change_requires_rescan_and_can_be_reset(self):
        self.touch('cache/a.png')
        root = self.index.add_root(self.media, ['cache'])
        self.index.scan(root)
        self.assertEqual(self.index.locations(root)['total'], 0)
        self.index.set_excludes(root, [])
        self.assertEqual(self.index.locations(root)['total'], 0)
        self.assertEqual(self.index.scan(root, dry_run=True)['added'], 1)
        self.assertEqual(self.index.locations(root)['total'], 0)
        self.index.scan(root)
        self.assertEqual(self.index.locations(root, status='present')['total'], 1)
        self.index.set_excludes(root, ['cache'])
        self.index.scan(root)
        self.assertEqual(self.index.locations(root, status='excluded')['total'], 1)
        with self.assertRaises(KeyError):
            self.index.set_excludes(99999, ['anything'])

    def test_cli_fixture_roundtrip(self):
        import subprocess
        self.touch('illustration.avif')
        cli = Path(__file__).resolve().parents[1] / 'tools' / 'index_library.py'
        target_db = self.base / 'cli.sqlite'
        def call(*args):
            result = subprocess.run([sys.executable, str(cli), '--db', str(target_db), *map(str, args)],
                                    capture_output=True, text=True, check=True)
            return json.loads(result.stdout)
        added = call('add', self.media)
        root = added['root_id']
        self.assertEqual(call('scan', root, '--dry-run')['added'], 1)
        self.assertEqual(call('locations', root)['total'], 0)
        self.assertEqual(call('scan', root)['added'], 1)
        self.assertEqual(call('locations', root)['items'][0]['kind'], 'image')
        self.assertIn('.git', call('rules', root, '--exclude', 'cache')['excludes'])
        self.assertEqual(len(call('roots')), 1)

    def test_dry_run_never_persists_changes_or_scan_timestamp(self):
        root = self.index.add_root(self.media)
        self.touch('new.webm')
        report = self.index.scan(root, dry_run=True)
        self.assertEqual(report['added'], 1)
        self.assertEqual(self.index.locations(root)['total'], 0)
        self.assertIsNone(self.index.roots()[0]['last_scanned_at'])
        self.index.scan(root)
        self.touch('new.webm', b'modified')
        report = self.index.scan(root, dry_run=True)
        self.assertEqual(report['changed'], 1)
        self.assertEqual(self.index.locations(root)['items'][0]['size_bytes'], 5)

    def test_missing_root_preserves_all_records(self):
        self.touch('photo.png')
        root = self.index.add_root(self.media)
        self.index.scan(root)
        self.media.rename(self.base / 'offline')
        self.assertFalse(self.index.roots()[0]['online'])
        with self.assertRaises(OSError):
            self.index.scan(root)
        self.assertEqual(self.index.locations(root, status='present')['total'], 1)

    def test_walk_failure_rolls_back_partial_changes(self):
        self.touch('a.png')
        root = self.index.add_root(self.media)
        self.index.scan(root)
        original = self.index.locations(root)['items'][0]
        self.touch('a.png', b'larger data')
        self.touch('subdir/b.png')
        scandir = os.scandir
        def break_subdir(path):
            if Path(path).name == 'subdir':
                raise OSError(errno.EIO, 'simulated I/O failure')
            return scandir(path)
        with patch('library_index.os.scandir', side_effect=break_subdir):
            with self.assertRaises(OSError):
                self.index.scan(root)
        self.assertEqual(self.index.locations(root)['total'], 1)
        self.assertEqual(self.index.locations(root)['items'][0]['size_bytes'], original['size_bytes'])

    def test_permission_error_skips_subdir_and_file_keeps_accessible_and_preserves_existing(self):
        self.touch('open/ok.png')
        self.touch('locked_dir/already_known.png')
        locked_file = self.touch('open/locked_file.png')
        (self.media / 'locked_stat_dir').mkdir(exist_ok=True)
        root = self.index.add_root(self.media)
        self.index.scan(root)

        scandir = os.scandir
        orig_stat = Path.stat
        def guard_stat(path_self, *, follow_symlinks=True):
            if path_self.name == 'locked_stat_dir':
                raise PermissionError('simulated stat denied')
            return orig_stat(path_self, follow_symlinks=follow_symlinks)

        class WrappedEntry:
            def __init__(self, inner):
                self._inner = inner
                self.name = inner.name
                self.path = inner.path
            def stat(self, *, follow_symlinks=True):
                if self._inner.name == locked_file.name:
                    raise PermissionError('simulated file stat denied')
                return self._inner.stat(follow_symlinks=follow_symlinks)
            def is_dir(self, *, follow_symlinks=True):
                return self._inner.is_dir(follow_symlinks=follow_symlinks)

        def guard_scandir(path):
            if Path(path).name == 'locked_dir':
                raise PermissionError('simulated folder access denied')
            cm = scandir(path)
            class Context:
                def __enter__(self):
                    return [WrappedEntry(e) for e in cm.__enter__()]
                def __exit__(self, *args):
                    return cm.__exit__(*args)
            return Context()

        with patch('library_index.os.scandir', side_effect=guard_scandir), patch.object(Path, 'stat', guard_stat):
            report = self.index.scan(root)

        self.assertEqual(report['skipped_access_denied'], 3)
        self.assertFalse(report['access_denied_truncated'])
        self.assertEqual(
            report['access_denied_entries'],
            [
                {'relative_path': 'locked_dir', 'is_dir': True},
                {'relative_path': 'locked_stat_dir', 'is_dir': True},
                {'relative_path': 'open/locked_file.png', 'is_dir': False},
            ],
        )
        present = {r['relative_path']: r['status'] for r in self.index.locations(root)['items']}
        self.assertEqual(present['open/ok.png'], 'present')
        # Previously indexed item inside skipped folder remains present, not missing.
        self.assertEqual(present['locked_dir/already_known.png'], 'present')

    def test_permission_error_on_registered_root_still_fails(self):
        self.touch('a.png')
        root = self.index.add_root(self.media)
        self.index.scan(root)
        scandir = os.scandir
        def deny_root(path):
            if Path(path) == self.media:
                raise PermissionError('root denied')
            return scandir(path)
        with patch('library_index.os.scandir', side_effect=deny_root):
            with self.assertRaises(PermissionError):
                self.index.scan(root)
        self.assertEqual(self.index.locations(root, status='present')['total'], 1)

    def test_recycle_bin_excluded_by_default(self):
        self.touch('$RECYCLE.BIN/S-1-5-21/deleted.png')
        self.touch('kept.png')
        root = self.index.add_root(self.media)
        self.index.scan(root)
        paths = [r['relative_path'] for r in self.index.locations(root)['items']]
        self.assertEqual(paths, ['kept.png'])

    def test_symlink_files_and_directories_not_followed(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'hidden.jpg').write_bytes(b'private-like synthetic fixture')
        link = self.media / 'foreign'
        file_link = self.media / 'shortcut.jpg'
        try:
            link.symlink_to(outside, target_is_directory=True)
            file_link.symlink_to(outside / 'hidden.jpg')
        except (OSError, NotImplementedError):
            self.skipTest('Symlinks unavailable on this platform')
        self.touch('safe.png')
        root = self.index.add_root(self.media)
        scan = self.index.scan(root)
        self.assertEqual(scan['skipped_links'], 2)
        self.assertEqual(self.index.locations(root)['total'], 1)
        with self.assertRaises(ValueError):
            self.index.add_root(link)

    def test_overlapping_and_duplicate_roots_rejected(self):
        child = self.media / 'child'
        child.mkdir()
        self.index.add_root(self.media)
        with self.assertRaises(ValueError):
            self.index.add_root(self.media)
        with self.assertRaises(ValueError):
            self.index.add_root(child)

    def test_file_types_and_pagination(self):
        files = {'sample.zip': 'archive', 'first.cbz': 'book', 'second.PNG': 'image', 'movie.MKV': 'video',
                 'song.FLAC': 'audio', 'art.clip': 'material'}
        for name in files:
            self.touch(name)
        root = self.index.add_root(self.media)
        self.index.scan(root)
        records = self.index.locations(root, limit=2)
        self.assertEqual(records['total'], 6)
        self.assertEqual(len(records['items']), 2)
        self.assertEqual(len(self.index.locations(root, limit=2, offset=4)['items']), 2)
        self.assertEqual({i['relative_path']: i['kind'] for i in self.index.locations(root)['items']}, files)
        with self.assertRaises(ValueError):
            self.index.locations(root, limit=0)
        with self.assertRaises(KeyError):
            self.index.locations(99999)

    def test_invalid_patterns_rejected(self):
        for patterns in [['../*'], ['/tmp'], ['x\\y'], [''], ['x' * 201]]:
            with self.subTest(patterns=patterns), self.assertRaises(ValueError):
                self.index.add_root(self.media, patterns)
        self.assertEqual(self.index.roots(), [])


if __name__ == '__main__':
    unittest.main()
