"""Generated Portable inventory only; no real Python/model/GUI/GPU startup."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import release_runtime as runtime
import startup_validation as cache
from startup_progress import StartupCancelled, StartupProgress


class StartupValidationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='aredoko-startup-cache-')
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / 'portable 日本語'
        self.root.mkdir()
        self.cache = self.base / 'validation'
        names = runtime.REQUIRED_FILES | {
            'Aredoko.exe', 'bin/portable-build.json', 'tools/portable_frontend.py',
            'tools/startup_progress.py', 'tools/startup_ipc.py',
            'runtime/python/python.exe', 'runtime/python/python311.dll',
            'runtime/python/Lib/site-packages/torch/lib/generated.dll',
            'runtime/media/ffmpeg.exe', 'runtime/media/ffprobe.exe'}
        for name in names:
            path=self.root/name;path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('fixture '+name).encode())
        self.bulk=self.root/'runtime/python/Lib/site-packages/torch/lib/generated.dll'
        self.rebuild()
        self.calls=0

    def rebuild(self):
        entries=[{'path':p.relative_to(self.root).as_posix(),'bytes':p.stat().st_size,
                  'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                 for p in sorted(self.root.rglob('*')) if p.is_file() and p.name not in ('manifest.json','sha256sums.txt')]
        self.manifest={'format':'aredoko-release-manifest','platform':'windows-x64',
            'frontend_activation':'portable','python_bundled':True,'media_tools_bundled':True,
            'entries':entries,'files_count':len(entries),'total_bytes':sum(e['bytes'] for e in entries)}
        (self.root/'manifest.json').write_text(json.dumps(self.manifest),encoding='utf-8')
        (self.root/'sha256sums.txt').write_text(''.join(f"{e['sha256']}  {e['path']}\n" for e in entries),encoding='utf-8')

    def full(self):
        self.calls+=1
        return runtime.verify_release(self.root)

    def run_check(self, **kwargs):
        return cache.startup_preflight(self.root,self.cache,self.full,**kwargs)

    def receipt(self):return next(self.cache.glob('*.json'))

    def test_first_full_then_warm_hashes_critical_not_bulk_and_preserves_payload(self):
        before={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(self.run_check(),self.manifest)
        with patch.object(runtime,'_verify_file',wraps=runtime._verify_file) as hashed:
            self.assertEqual(self.run_check(),self.manifest)
        names={call.args[1]['path'] for call in hashed.call_args_list}
        self.assertIn('bin/Aredoko.WinUI.dll',names)
        self.assertIn('backend/app/production_server.py',names)
        self.assertIn('runtime/python/python311.dll',names)
        self.assertNotIn(self.bulk.relative_to(self.root).as_posix(),names)
        self.assertEqual(self.calls,1)
        self.assertEqual(before,{p:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()})

    def test_changed_bulk_forces_full_and_rejects_corruption_without_replacing_receipt(self):
        self.run_check();path=self.receipt();original=path.read_bytes()
        self.bulk.write_bytes(b'x'*self.bulk.stat().st_size)
        info=self.bulk.stat();os.utime(self.bulk,ns=(info.st_atime_ns,info.st_mtime_ns+2_000_000_000))
        with self.assertRaisesRegex(ValueError,'file changed'):self.run_check()
        self.assertEqual(self.calls,2);self.assertEqual(path.read_bytes(),original)

    def test_valid_update_requires_new_full_receipt(self):
        self.run_check();self.bulk.write_bytes(b'valid new release');self.rebuild()
        self.run_check();self.run_check()
        self.assertEqual(self.calls,2);self.assertEqual(len(list(self.cache.glob('*.json'))),2)

    def test_unknown_or_missing_file_never_passes_cached_inventory(self):
        self.run_check();unknown=self.root/'accidental.pyc';unknown.write_bytes(b'generated')
        with self.assertRaisesRegex(ValueError,'Unlisted'):self.run_check()
        unknown.unlink();self.bulk.unlink()
        with self.assertRaisesRegex(ValueError,'missing'):self.run_check()

    def test_damaged_or_wrong_contract_receipt_forces_full(self):
        self.run_check();self.receipt().write_text('{',encoding='utf-8');self.run_check()
        self.assertEqual(self.calls,2)
        value=json.loads(self.receipt().read_text());value['contract']='other'
        self.receipt().write_text(json.dumps(value));self.run_check()
        self.assertEqual(self.calls,3)

    def test_critical_hash_still_rejects_if_metadata_receipt_is_forged(self):
        self.run_check();target=self.root/'bin/Aredoko.WinUI.dll'
        target.write_bytes(b'x'*target.stat().st_size)
        path=self.receipt();value=json.loads(path.read_text())
        value['files']['bin/Aredoko.WinUI.dll']=cache._fingerprint(target)
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'file changed'):self.run_check()
        self.assertEqual(self.calls,1)

    def test_explicit_full_rechecks_even_unchanged_release(self):
        self.run_check();self.run_check(force_full=True)
        self.assertEqual(self.calls,2)

    def test_release_changed_during_full_does_not_publish_receipt(self):
        def moving():
            result=self.full();info=self.bulk.stat()
            os.utime(self.bulk,ns=(info.st_atime_ns,info.st_mtime_ns+2_000_000_000))
            return result
        with self.assertRaisesRegex(ValueError,'changed during'):
            cache.startup_preflight(self.root,self.cache,moving)
        self.assertEqual(list(self.cache.glob('*.json')),[])

    def test_failed_probe_does_not_publish_receipt(self):
        def failed():self.full();raise RuntimeError('generated probe failure')
        with self.assertRaisesRegex(RuntimeError,'probe failure'):
            cache.startup_preflight(self.root,self.cache,failed)
        self.assertEqual(list(self.cache.glob('*.json')),[])

    def test_relocation_and_probe_contract_do_not_reuse_old_receipt(self):
        self.run_check();relocated=self.base/'relocated';shutil.copytree(self.root,relocated)
        old=self.root;self.root=relocated
        self.run_check();self.root=old
        self.run_check(contract='changed-probe-contract')
        self.assertEqual(self.calls,3)

    def test_cache_cannot_be_written_inside_payload(self):
        with self.assertRaisesRegex(ValueError,'outside'):
            cache.startup_preflight(self.root,self.root/'cache',self.full)
        self.assertFalse((self.root/'cache').exists())

    def test_cancel_before_start_creates_nothing(self):
        control=StartupProgress();control.cancel()
        with self.assertRaises(StartupCancelled):self.run_check(progress=control)
        self.assertFalse(self.cache.exists());self.assertEqual(self.calls,0)

    def test_cancel_during_warm_hash_keeps_existing_receipt(self):
        self.run_check();before=self.receipt().read_bytes()
        def sink(value):
            if value['stage']=='file_hashes' and value['state']=='running':control.cancel()
        control=StartupProgress(sink)
        with self.assertRaises(StartupCancelled):self.run_check(progress=control)
        self.assertEqual(before,self.receipt().read_bytes());self.assertEqual(self.calls,1)

    def test_hardlinked_payload_is_rejected_on_warm_start(self):
        self.run_check();os.link(self.bulk,self.base/'alias')
        with self.assertRaisesRegex(ValueError,'Hardlinked'):self.run_check()

    def test_directory_reparse_is_rejected_on_warm_start(self):
        self.run_check();outside=self.base/'outside';outside.mkdir()
        link=self.root/'unexpected-link'
        try:link.symlink_to(outside,target_is_directory=True)
        except OSError:self.skipTest('Directory symlink privilege unavailable')
        with self.assertRaisesRegex(ValueError,'Linked'):self.run_check()

    def test_leaf_changed_to_link_after_tree_guard_is_rejected(self):
        self.run_check();outside=self.base/'outside.dat';outside.write_bytes(b'outside')
        probe=self.base/'symlink-probe'
        try:probe.symlink_to(outside);probe.unlink()
        except OSError:self.skipTest('File symlink privilege unavailable')
        original=runtime._parallel_tree
        def moving(root,**kwargs):
            for path in original(root,**kwargs):
                if path==self.bulk:
                    path.unlink();path.symlink_to(outside)
                yield path
        with patch.object(runtime,'_parallel_tree',moving):
            with self.assertRaisesRegex(ValueError,'ordinary validation'):self.run_check()

    def test_hardlinked_receipt_is_rejected(self):
        self.run_check();os.link(self.receipt(),self.base/'receipt-alias')
        with self.assertRaisesRegex(ValueError,'Hardlinked'):self.run_check()
        self.assertEqual(self.calls,1)

    def test_cancel_during_atomic_receipt_save_keeps_old_receipt(self):
        self.run_check();before=self.receipt().read_bytes();control=StartupProgress()
        original=json.dump
        def cancelled(*args,**kwargs):
            result=original(*args,**kwargs);control.cancel();return result
        with patch.object(cache.json,'dump',cancelled):
            with self.assertRaises(StartupCancelled):self.run_check(force_full=True,progress=control)
        self.assertEqual(self.receipt().read_bytes(),before)
        self.assertEqual(list(self.cache.glob('*.tmp')),[])

    def test_nonportable_channel_preserves_full_preflight(self):
        self.manifest['frontend_activation']='unconfigured'
        (self.root/'manifest.json').write_text(json.dumps(self.manifest))
        self.run_check();self.run_check()
        self.assertEqual(self.calls,2);self.assertFalse(self.cache.exists())

    def test_managed_python_never_reuses_release_only_receipt(self):
        # Full preflight owns the external runtime check. Even a warm release
        # receipt must not skip that callback for an external runtime candidate.
        self.run_check()
        self.manifest['managed_python'] = runtime.MANAGED_PYTHON
        (self.root/'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')
        calls = []
        for _ in range(2):
            result = cache.startup_preflight(self.root, self.cache,
                lambda: calls.append('full external check') or self.manifest)
            self.assertEqual(result, self.manifest)
        self.assertEqual(len(calls), 2)


if __name__=='__main__':unittest.main()
