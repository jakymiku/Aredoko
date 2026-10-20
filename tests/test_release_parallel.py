"""Inventory equivalence, bounded concurrency and fail-closed filesystem guards."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import release_runtime as runtime


class ParallelReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='aredoko-verify-parallel-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'release 日本語'
        self.root.mkdir()
        names=set(runtime.REQUIRED_FILES)
        names.update(f'payload/{group}/nested/file-{index}.dat' for group in range(4) for index in range(18))
        for name in names:
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(('generated fixture '+name).encode())
        (self.root/'empty folder').mkdir()
        entries=[{'path':name,'bytes':(self.root/name).stat().st_size,
                  'sha256':hashlib.sha256((self.root/name).read_bytes()).hexdigest()} for name in sorted(names)]
        self.manifest={'format':'aredoko-release-manifest','platform':'windows-x64','entries':entries,
                       'files_count':len(entries),'total_bytes':sum(e['bytes'] for e in entries)}
        (self.root/'manifest.json').write_text(json.dumps(self.manifest),encoding='utf-8')
        (self.root/'sha256sums.txt').write_text(''.join(f"{e['sha256']}  {e['path']}\n" for e in entries),encoding='utf-8')

    def test_tree_keeps_every_full_ancestor_guard_of_sequential_reference(self):
        original=runtime.plain_path
        counts=Counter();lock=threading.Lock()
        def trace(path,**kwargs):
            with lock:counts[(str(path),kwargs.get('directory',False))]+=1
            return original(path,**kwargs)
        with patch.object(runtime,'plain_path',trace):
            sequential=set(runtime.ordinary_tree(self.root))
            before=counts.copy();counts.clear()
            concurrent=set(runtime._parallel_tree(self.root))
        self.assertEqual(sequential,concurrent)
        self.assertEqual(before,counts)

    def test_every_file_is_rehashed_once_with_at_most_four_active_tasks(self):
        original=runtime.digest;calls=Counter();lock=threading.Lock()
        barrier=threading.Barrier(4);active=maximum=0
        def observed(path):
            nonlocal active,maximum
            with lock:
                calls[path]+=1;number=sum(calls.values());active+=1;maximum=max(maximum,active)
            try:
                if number<=4:barrier.wait(timeout=5)
                return original(path)
            finally:
                with lock:active-=1
        with patch.object(runtime,'digest',observed):
            result=runtime.verify_release(self.root)
        self.assertEqual(result,self.manifest)
        self.assertEqual(calls,Counter({self.root/e['path']:1 for e in self.manifest['entries']}))
        self.assertEqual(maximum,4)

    def test_same_size_corruption_and_unlisted_cache_are_not_ignored(self):
        path=self.root/'bin/Aredoko.WinUI.exe';source=path.read_bytes()
        path.write_bytes(bytes(b^1 for b in source))
        with self.assertRaisesRegex(ValueError,'file changed'):runtime.verify_release(self.root)
        path.write_bytes(source)
        cache=self.root/'tools/__pycache__/accidental.pyc';cache.parent.mkdir();cache.write_bytes(b'generated cache')
        with self.assertRaisesRegex(ValueError,'Unlisted'):runtime.verify_release(self.root)

    def test_hardlinks_are_rejected_before_any_hash_of_the_alias(self):
        source=self.root/'bin/Aredoko.WinUI.exe';outside=Path(self.temp.name)/'alias'
        try:os.link(source,outside)
        except OSError:self.skipTest('Hardlinks unavailable')
        with self.assertRaisesRegex(ValueError,'Hardlinked'):runtime.verify_release(self.root)

    def test_nested_directory_link_is_rejected_without_descending(self):
        outside=Path(self.temp.name)/'outside';outside.mkdir();(outside/'private fixture').write_bytes(b'never read')
        link=self.root/'payload/linked'
        try:link.symlink_to(outside,target_is_directory=True)
        except OSError:self.skipTest('Directory symlinks unavailable')
        with patch.object(runtime,'_checked_directory',wraps=runtime._checked_directory) as checked:
            with self.assertRaisesRegex(ValueError,'Linked'):list(runtime._parallel_tree(self.root))
        self.assertNotIn(link,[call.args[0] for call in checked.call_args_list])

    def test_directory_queued_then_replaced_by_link_is_rechecked(self):
        outside=Path(self.temp.name)/'outside';outside.mkdir()
        original=runtime._checked_directory;swapped=False
        def change_after_parent(path):
            nonlocal swapped
            directories,files=original(path)
            if path==self.root and not swapped:
                swapped=True
                directory=self.root/'empty folder'
                directory.rmdir()  # Only this known empty generated directory.
                try:directory.symlink_to(outside,target_is_directory=True)
                except OSError:self.skipTest('Directory symlinks unavailable')
            return directories,files
        with patch.object(runtime,'_checked_directory',change_after_parent):
            with self.assertRaisesRegex(ValueError,'Linked'):list(runtime._parallel_tree(self.root))


if __name__=='__main__':unittest.main()
