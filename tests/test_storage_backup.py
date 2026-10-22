"""Generated-only recovery fixtures. No user DB, model, media scan or GUI."""
from array import array
from contextlib import closing
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import threading
import types
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

from test_tag_suggestions import TagFixture
from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch,VectorStore
from ai_settings import AIProfileSettings
from page_index import PageIndex
from page_text import PageTextIndex
from page_semantics import CONTRACT
from previews import PreviewReader
from production import ProductionCatalog
from storage_backup import backup,restore,RecoveryError
from storage_lease import storage_lease,StorageBusyError,StoragePathError,plain_path
import storage_backup as recovery

ROOT=Path(__file__).resolve().parents[1]
class Encoder:
    profile=replace(DEFAULT_PROFILE,dimension=3)
    available=True
    def encode(self,*args):return [1.,0.,0.]
    def close(self):pass

def logical(path):
    with closing(sqlite3.connect(path)) as db:
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {table:db.execute('SELECT * FROM '+table+' ORDER BY rowid').fetchall() for table in tables}

class StorageBackupTests(TagFixture,unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.catalog.update([self.item],{'tags':['手動'],'shelf':'素材','favorite':True,'reviewed':True})
        batch=self.generate()['batch'];self.review(batch['proposals'][0],tag='承認済み');self.review(batch['proposals'][1],'reject')
        self.catalog.record_view(self.item)
        self.index=PageIndex(self.catalog);self.text=PageTextIndex(self.catalog,self.index)
        book=self.ids['fiction.cbz'];self.index.refresh(book);self.snapshot=self.index.list(book)
        reader=PreviewReader(self.catalog);manifest=reader.manifest(book)
        self.catalog.save_reader_progress(book,{'revision':manifest['revision'],'page':1,'mode':'rtl'},reader)
        with self.catalog.connect() as db:
            self.snapshot_id=db.execute('SELECT snapshot_id FROM page_heads WHERE item_id=?',(book,)).fetchone()[0]
            page=self.snapshot['pages'][0]
            db.execute('INSERT INTO page_texts(snapshot_id,page_id,producer_key,producer_json,text,normalized_text,created_at) VALUES(?,?,?,?,?,?,?)',
                       (self.snapshot_id,page['page_id'],'fixture','{}','保存した文章','保存した文章',1))
            text_id=db.execute('SELECT last_insert_rowid()').fetchone()[0]
            db.execute('INSERT INTO page_text_heads VALUES(?,?,?)',(self.snapshot_id,page['page_id'],text_id))
        self.ai=AISearch(self.catalog,Encoder());self.addCleanup(self.ai.close)
        self.ai.start();self.ai.worker.join(5);self.assertEqual(self.ai.status()['state'],'complete')
        with self.ai.store.connect() as db:
            db.execute('INSERT INTO ai_page_vectors VALUES(?,?,?,?,?,?)',(book,self.snapshot['source_revision'],self.snapshot['pages'][0]['page_id'],0,array('f',[1.,0.,0.]).tobytes(),CONTRACT))
        self.other_profile=replace(DEFAULT_PROFILE,dimension=4,modalities=('text',),directory='fixture-text')
        self.other_store=VectorStore(self.other_profile.store_path(self.catalog.path),self.other_profile)
        self.other_store.put(self.item,'0'*64,{'text':[1.,0.,0.,0.]})
        self.profiles=self.base/'profiles';self.profiles.mkdir()
        (self.profiles/'fixture.json').write_text(json.dumps(Encoder.profile.to_dict()),encoding='utf-8')
        (self.profiles/'text.json').write_text(json.dumps(self.other_profile.to_dict()),encoding='utf-8')
        self.settings=self.base/'settings.json';self.settings.write_text(json.dumps({'version':1,'profile':'local:fixture.json','scope':{'root_ids':[self.root],'kind':'','shelf':None},'resource':{'idle_release_seconds':0,'index_pause_ms':0}}),encoding='utf-8')
        self.viewer=self.base/'viewer-settings.json';self.viewer.write_text('{"version":1,"wheel_up_advances":true}',encoding='utf-8')
        self.bundle=self.base/'backup';self.output=self.base/'restored'
        self.originals={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in (self.path,self.book)}

    def create(self,**kwargs):return backup(self.catalog.path,self.bundle,settings=self.settings,viewer_settings=self.viewer,profiles=self.profiles,**kwargs)
    def unchanged(self):self.assertEqual(self.originals,{p:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.originals})
    def manifest(self,folder=None):return json.loads(((folder or self.bundle)/'manifest.json').read_text(encoding='utf-8'))
    def write_manifest(self,value,folder=None):((folder or self.bundle)/'manifest.json').write_text(json.dumps(value),encoding='utf-8')

    def test_roundtrip_all_stores_settings_provenance_history_and_reader(self):
        before={path:logical(path) for path in (self.catalog.path,self.ai.store.path,self.other_store.path)}
        with patch('previews.PreviewReader.tag_source',side_effect=AssertionError('must not read media')),patch('library_index.LibraryIndex.scan',side_effect=AssertionError('must not scan')):
            result=self.create();report=restore(self.bundle,self.output)
        self.assertEqual((result['files'],report['files']),(7,7))
        self.assertFalse(report['automatic_resume']);self.assertTrue(report['requires_source_revalidation'])
        self.assertEqual(before[self.catalog.path],logical(self.output/'catalog.sqlite'))
        for profile,source in ((Encoder.profile,self.ai.store.path),(self.other_profile,self.other_store.path)):
            self.assertEqual(before[source],logical(profile.store_path(self.output/'catalog.sqlite')))
        restored=ProductionCatalog(self.output/'catalog.sqlite');self.addCleanup(restored.close)
        row=restored.get(self.item);self.assertEqual((row['tags'],row['shelf'],row['favorite'],row['reviewed']),(['手動','承認済み'],'素材',True,True))
        self.assertEqual(restored.reader_progress(self.ids['fiction.cbz'])['progress']['page'],1)
        preferences=AIProfileSettings(ROOT,self.output/'settings/ai-settings.json',profile_directory=self.output/'profiles')
        self.assertEqual(preferences.active,'local:fixture.json');self.assertEqual(preferences.scope()['root_ids'],[self.root]);self.assertFalse(preferences.startup_error)
        self.assertTrue(json.loads((self.output/'settings/viewer-settings.json').read_text())['wheel_up_advances'])
        self.unchanged()

    def test_current_viewer_settings_roundtrip_preserves_all_fields_and_bytes(self):
        value={'version':1,'wheel_up_advances':True,'library_item_scale':180,'theme':'dark','enlarge_small_images':True}
        raw=json.dumps(value,indent=2).encode('utf-8');self.viewer.write_bytes(raw)
        self.create();restore(self.bundle,self.output)
        self.assertEqual((self.output/'settings/viewer-settings.json').read_bytes(),raw)
        self.assertEqual(self.viewer.read_bytes(),raw);self.unchanged()

    def test_rehashed_invalid_current_viewer_settings_are_rejected_before_restore(self):
        self.create();payload=self.bundle/'settings/viewer-settings.json'
        payload.write_text('{"version":1,"wheel_up_advances":true,"library_item_scale":200,"theme":"dark"}')
        manifest=self.manifest();entry=next(v for v in manifest['entries'] if v['role']=='viewer_settings')
        entry['bytes'],entry['sha256']=recovery._hash(payload);self.write_manifest(manifest)
        with self.assertRaises(RecoveryError):restore(self.bundle,self.output)
        self.assertFalse(self.output.exists());self.unchanged()

    def test_omitted_cache_needs_explicit_rebuild_without_losing_metadata(self):
        self.create(include_vectors=False);restore(self.bundle,self.output)
        restored=ProductionCatalog(self.output/'catalog.sqlite');self.addCleanup(restored.close)
        ai=AISearch(restored,Encoder());self.addCleanup(ai.close)
        self.assertEqual(ai.search('保存',source='text')['total'],0)
        self.assertEqual(restored.get(self.item)['tags'],['手動','承認済み'])
        ai.start();ai.worker.join(5);self.assertEqual(ai.status()['state'],'complete')
        self.assertGreater(ai.search('保存',source='text')['total'],0);self.unchanged()

    def test_missing_derived_file_requires_explicit_without_ai(self):
        self.create();entry=next(v for v in self.manifest()['entries'] if v['role']=='vectors');(self.bundle/entry['path']).unlink()
        with self.assertRaises((ValueError,OSError)):restore(self.bundle,self.output)
        self.assertFalse(self.output.exists());result=restore(self.bundle,self.output,without_vectors=True)
        self.assertEqual(result['cache_policy'],'omitted');self.assertFalse(list(self.output.glob('*.ai*.sqlite')));self.unchanged()

    def test_corrupt_payload_fails_before_destination_and_preserves_source(self):
        self.create();payload=self.bundle/'catalog.sqlite';data=bytearray(payload.read_bytes());data[-10]^=1;payload.write_bytes(data)
        with self.assertRaises(RecoveryError):restore(self.bundle,self.output)
        self.assertFalse(self.output.exists());self.unchanged()

    def test_old_invalid_duplicate_or_escaping_manifest_is_refused(self):
        self.create();original=self.manifest()
        for label,change in [('old',lambda m:m.update(version=0)),('bool',lambda m:m.update(version=True)),('escape',lambda m:m['entries'][0].update(path='../catalog.sqlite')),('absolute',lambda m:m['entries'][0].update(path='C:/catalog.sqlite')),('duplicate',lambda m:m['entries'].append(m['entries'][0].copy())),('role',lambda m:m['entries'][0].update(role='media')),('huge',lambda m:m['entries'][0].update(bytes=2**50)),('unknown',lambda m:m.update(future=True)),('missing_role',lambda m:m['entries'].__setitem__(slice(None),[v for v in m['entries'] if v['role']!='ai_settings']))]:
            value=json.loads(json.dumps(original));change(value);self.write_manifest(value)
            with self.subTest(label=label),self.assertRaises((ValueError,OSError)):restore(self.bundle,self.output)
            self.assertFalse(self.output.exists())
        (self.bundle/'manifest.json').write_text('{"version":1,"version":1}')
        with self.assertRaises(RecoveryError):restore(self.bundle,self.output)
        self.unchanged()

    def test_existing_destination_and_overlap_never_overwrite(self):
        self.create();self.output.mkdir();sentinel=self.output/'keep';sentinel.write_text('keep')
        for folder in (self.output,self.bundle,self.bundle/'inner',self.base):
            with self.subTest(folder=folder),self.assertRaises((ValueError,OSError)):restore(self.bundle,folder)
        with self.assertRaises((ValueError,OSError)):self.create()
        self.assertEqual(sentinel.read_text(),'keep');self.unchanged()

    def test_busy_db_and_host_lease_refuse_without_creating_output(self):
        with storage_lease(self.catalog.path):
            with self.assertRaises(StorageBusyError):self.create()
            result=subprocess.run([sys.executable,str(ROOT/'app/production_server.py'),'--db',str(self.catalog.path),'--port','0'],capture_output=True,text=True,timeout=10)
            self.assertNotEqual(result.returncode,0);self.assertIn('StorageBusyError',result.stderr)
        with closing(sqlite3.connect(self.other_store.path)) as writer:
            writer.execute('BEGIN IMMEDIATE')
            with self.assertRaises(StorageBusyError):self.create()
        self.assertFalse(self.bundle.exists());self.create();self.unchanged()

    def test_wal_commits_are_captured_without_copying_wal(self):
        with closing(sqlite3.connect(self.catalog.path)) as writer:
            writer.execute("UPDATE items SET shelf='WAL保存' WHERE id=?",(self.item,));writer.commit()
            self.assertTrue(Path(str(self.catalog.path)+'-wal').exists())
            self.create()
        self.assertEqual(logical(self.catalog.path),logical(self.bundle/'catalog.sqlite'))
        self.assertFalse(list(self.bundle.rglob('*-wal')));restore(self.bundle,self.output);self.unchanged()

    def test_configuration_change_during_capture_discards_partial_bundle(self):
        entry=recovery._entry;fired=[]
        def changed(*args,**kwargs):
            value=entry(*args,**kwargs)
            if not fired:fired.append(True);self.viewer.write_text('{"version":1,"wheel_up_advances":false}')
            return value
        with patch.object(recovery,'_entry',side_effect=changed),self.assertRaises(RecoveryError):self.create()
        self.assertFalse(self.bundle.exists());self.create();self.unchanged()

    def test_capacity_and_partial_copy_failure_cleanup(self):
        with patch.object(recovery.shutil,'disk_usage',return_value=types.SimpleNamespace(free=0)),self.assertRaises(RecoveryError):self.create()
        with self.assertRaises(RecoveryError):self.create(max_bytes=65536)
        self.assertFalse(self.bundle.exists());self.create()
        write=recovery._write
        def fail_marker(path,data):
            if path.name=='recovery.json':raise OSError('generated disk failure')
            return write(path,data)
        with patch.object(recovery,'_write',side_effect=fail_marker),self.assertRaises(OSError):restore(self.bundle,self.output)
        self.assertFalse(self.output.exists());restore(self.bundle,self.output);self.unchanged()

    def test_cancel_after_first_snapshot_cleans_only_owned_directory(self):
        stop=threading.Event();entry=recovery._entry
        def captured(*args,**kwargs):value=entry(*args,**kwargs);stop.set();return value
        with patch.object(recovery,'_entry',side_effect=captured),self.assertRaises(InterruptedError):self.create(cancelled=stop.is_set)
        self.assertFalse(self.bundle.exists());self.create();self.unchanged()

    def test_unknown_schema_and_namespace_mismatch_fail_closed(self):
        with self.catalog.connect() as db:db.execute('CREATE TABLE future_table(value TEXT)')
        with self.assertRaises(RecoveryError):self.create()
        with self.catalog.connect() as db:db.execute('DROP TABLE future_table')
        wrong=Path(str(self.catalog.path)+'.ai.'+'0'*24+'.sqlite');self.other_store.path.rename(wrong)
        with self.assertRaises(RecoveryError):self.create()
        self.assertFalse(self.bundle.exists());self.create(include_vectors=False);self.unchanged()

    def test_live_companions_are_not_silently_ignored_on_restore(self):
        self.create();companion=self.bundle/'catalog.sqlite-wal';companion.write_bytes(b'not a sealed snapshot')
        with self.assertRaises(RecoveryError):restore(self.bundle,self.output)
        self.assertFalse(self.output.exists());self.unchanged()

    def test_foreign_runtime_does_not_bypass_physical_page_freshness(self):
        self.create();manifest=self.manifest();manifest['runtime']={'python':'different-host','platform':'other'};self.write_manifest(manifest)
        restore(self.bundle,self.output);restored=ProductionCatalog(self.output/'catalog.sqlite');self.addCleanup(restored.close)
        ai=AISearch(restored,Encoder());self.addCleanup(ai.close)
        rows=list(ai._current_rows([self.ids['fiction.cbz']]).values())
        self.assertTrue(ai.pages.rank(rows,[1.,0.,0.]))
        read=ai.pages.index.previews._read
        def foreign(*args,**kwargs):value=read(*args,**kwargs);return {**value,'revision':'f'*64}
        with patch.object(ai.pages.index.previews,'_read',side_effect=foreign):self.assertEqual(ai.pages.rank(rows,[1.,0.,0.]),{})
        self.assertEqual(restored.get(self.item)['tags'],['手動','承認済み']);self.unchanged()

    def test_new_profile_store_during_capture_discards_mixed_set(self):
        entry=recovery._entry;fired=[]
        profile=replace(DEFAULT_PROFILE,dimension=5,directory='fixture-five')
        def added(*args,**kwargs):
            value=entry(*args,**kwargs)
            if not fired:fired.append(True);VectorStore(profile.store_path(self.catalog.path),profile)
            return value
        with patch.object(recovery,'_entry',side_effect=added),self.assertRaises(RecoveryError):self.create()
        self.assertFalse(self.bundle.exists());self.create();self.unchanged()

    def test_unclean_jobs_become_interrupted_on_open_not_auto_resumed(self):
        with self.catalog.connect() as db:
            db.execute("INSERT INTO scan_jobs(root_id,state) VALUES(?,'running')",(self.root,))
        self.ai.store.save_state({'state':'running','processed':1,'total':2,'indexed':1,'skipped':0,'error':'','scope':{'root_ids':[self.root]},'job_id':'a'*32})
        self.create();restore(self.bundle,self.output)
        raw=logical(self.output/'catalog.sqlite');self.assertEqual(raw['scan_jobs'][0][2],'running')
        restored=ProductionCatalog(self.output/'catalog.sqlite');self.addCleanup(restored.close)
        ai=AISearch(restored,Encoder());self.addCleanup(ai.close)
        with restored.connect() as db:self.assertEqual(db.execute('SELECT state FROM scan_jobs').fetchone()[0],'interrupted')
        self.assertEqual(ai.store.state()['state'],'interrupted');self.assertIsNone(ai.worker)
        self.assertEqual(ai.store.state()['job_id'],'a'*32);self.unchanged()

    def test_rehashed_future_schema_and_payload_growth_are_refused(self):
        self.create();payload=self.bundle/'catalog.sqlite'
        with closing(sqlite3.connect(payload)) as db:
            db.execute('CREATE TABLE future_schema(value TEXT)');db.commit()
        manifest=self.manifest();entry=next(v for v in manifest['entries'] if v['role']=='catalog')
        entry['bytes'],entry['sha256']=recovery._hash(payload);self.write_manifest(manifest)
        with self.assertRaises(RecoveryError):restore(self.bundle,self.output)
        self.assertFalse(self.output.exists())
        # A second untouched bundle is validated, then grows before copying.
        self.bundle=self.base/'second-backup';self.create();output=recovery._output
        from contextlib import contextmanager
        @contextmanager
        def changed(*args,**kwargs):
            with output(*args,**kwargs) as folder:
                with (self.bundle/'catalog.sqlite').open('ab') as stream:stream.write(b'growth')
                yield folder
        with patch.object(recovery,'_output',changed),self.assertRaises(RecoveryError):restore(self.bundle,self.output)
        self.assertFalse(self.output.exists());self.unchanged()

    def test_invalid_settings_and_metadata_only_recovery_remain_explicit(self):
        self.settings.write_text('{"version":2,"profile":"default"}')
        with self.assertRaises(RecoveryError):self.create()
        self.assertFalse(self.bundle.exists())
        backup(self.catalog.path,self.bundle,include_vectors=False)
        result=restore(self.bundle,self.output)
        self.assertEqual(set(self.manifest()['not_included']),{'ai_settings','viewer_settings','profiles','tagger_profiles'})
        self.assertEqual(result['cache_policy'],'omitted');self.unchanged()

    def test_legacy_namespace_and_explicit_tagger_profile_are_preserved(self):
        legacy=VectorStore(DEFAULT_PROFILE.store_path(self.catalog.path),DEFAULT_PROFILE)
        legacy.put(self.item,'a'*64,{'text':[1.]+[0.]*(DEFAULT_PROFILE.dimension-1)})
        profile=ROOT/'config/tagger-profiles/wd-swinv2-v3.json'
        self.create(tagger_profiles=[profile]);restore(self.bundle,self.output)
        self.assertEqual(logical(legacy.path),logical(DEFAULT_PROFILE.store_path(self.output/'catalog.sqlite')))
        self.assertEqual(profile.read_bytes(),(self.output/'tagger-profiles'/profile.name).read_bytes())
        self.assertNotIn('tagger_profiles',self.manifest()['not_included']);self.unchanged()

    def test_destination_is_leased_until_completion_marker(self):
        entry=recovery._entry;write=recovery._write;checks=[]
        def captured(folder,*args,**kwargs):
            value=entry(folder,*args,**kwargs)
            with self.assertRaises(StorageBusyError):
                with storage_lease(folder/'catalog.sqlite'):pass
            checks.append('backup');return value
        with patch.object(recovery,'_entry',side_effect=captured):self.create()
        def completed(path,data):
            if path.name=='recovery.json':
                with self.assertRaises(StorageBusyError):
                    with storage_lease(path.parent/'catalog.sqlite'):pass
                checks.append('restore')
            return write(path,data)
        with patch.object(recovery,'_write',side_effect=completed):restore(self.bundle,self.output)
        with storage_lease(self.output/'catalog.sqlite'):pass
        self.assertIn('backup',checks);self.assertIn('restore',checks);self.unchanged()

    def test_free_space_estimate_includes_uncheckpointed_wal_pages(self):
        with closing(sqlite3.connect(self.catalog.path)) as writer:
            writer.execute('UPDATE items SET title=? WHERE id=?',('x'*(1024*1024),self.item));writer.commit()
            free=2*self.catalog.path.stat().st_size+8*1024**2+1
            with patch.object(recovery.shutil,'disk_usage',return_value=types.SimpleNamespace(free=free)),self.assertRaises(RecoveryError):self.create()
        self.assertFalse(self.bundle.exists());self.unchanged()

    def test_cli_new_directory_only_and_invalid_version_exit(self):
        self.create()
        command=[sys.executable,str(ROOT/'tools/backup_library.py'),'restore','--bundle',str(self.bundle),'--output',str(self.output)]
        result=subprocess.run(command,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(json.loads(result.stdout)['requires_source_revalidation'])
        result=subprocess.run(command,capture_output=True,text=True,timeout=10);self.assertEqual(result.returncode,2)
        self.unchanged()

class StorageLeaseTests(unittest.TestCase):
    def test_production_main_holds_lease_and_releases_after_start_failure(self):
        import tempfile
        import production_server
        from storage_lease import storage_parent
        with tempfile.TemporaryDirectory() as folder:
            catalog=Path(folder)/'nested'/'state'/'catalog.sqlite';profiles=Path(folder)/'profiles'
            arguments=['production_server.py','--db',str(catalog),'--ai-profiles-dir',str(profiles),'--port','0']
            def serve(args):
                self.assertEqual(args.ai_profiles_dir,profiles)
                with self.assertRaises(StorageBusyError):
                    with storage_lease(catalog):pass
            with patch.object(sys,'argv',arguments),patch.object(production_server,'_serve',side_effect=serve):production_server.main()
            with storage_lease(catalog):pass
            with patch.object(sys,'argv',arguments),patch.object(production_server,'_serve',side_effect=OSError('startup failed')),self.assertRaises(OSError):production_server.main()
            with storage_lease(catalog):pass
            with patch.object(Path,'exists',return_value=False),self.assertRaises(StoragePathError):storage_parent(catalog)

    def test_kernel_release_after_crash_and_reparse_ancestor_rejection(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            catalog=Path(folder)/'catalog.sqlite'
            code="import os,sys;sys.path.insert(0,sys.argv[1]);from storage_lease import storage_lease;context=storage_lease(sys.argv[2]);context.__enter__();os._exit(0)"
            result=subprocess.run([sys.executable,'-c',code,str(ROOT/'app'),str(catalog)],capture_output=True,timeout=5)
            self.assertEqual(result.returncode,0)
            with storage_lease(catalog):
                with self.assertRaises(StorageBusyError):
                    with storage_lease(catalog):pass
            lstat=Path.lstat
            def linked(path,*args,**kwargs):
                info=lstat(path,*args,**kwargs)
                if path==Path(folder):return types.SimpleNamespace(st_mode=info.st_mode,st_file_attributes=0x400)
                return info
            with patch.object(Path,'lstat',linked),self.assertRaises(StoragePathError):plain_path(catalog,missing=True)

class ViewerSettingsCompatibilityTests(unittest.TestCase):
    def test_legacy_partial_and_current_version_one_values(self):
        base={'version':1,'wheel_up_advances':False}
        for extra in ({}, {'theme':'system'}, {'enlarge_small_images':False},
                      *({'library_item_scale':scale,'theme':theme,'enlarge_small_images':True}
                        for scale in range(60,181,20) for theme in ('system','light','dark'))):
            with self.subTest(extra=extra):
                recovery._configuration('viewer_settings',json.dumps({**base,**extra}).encode())

    def test_invalid_types_future_fields_versions_and_oversize_are_rejected(self):
        base={'version':1,'wheel_up_advances':True}
        for key,value in [('version',2),('version',True),('wheel_up_advances',1),('library_item_scale',True),
                          ('library_item_scale',60.0),('library_item_scale',61),('library_item_scale',200),
                          ('theme','future'),('theme',None),('enlarge_small_images',1),('future_setting',True)]:
            with self.subTest(key=key,value=value),self.assertRaises(RecoveryError):
                recovery._configuration('viewer_settings',json.dumps({**base,key:value}).encode())
        raw=json.dumps(base).encode()
        for data in (raw+b' '*(2049-len(raw)),b'{"version":1,"wheel_up_advances":true,"theme":"dark","theme":"light"}'):
            with self.assertRaises(RecoveryError):recovery._configuration('viewer_settings',data)


if __name__=='__main__':unittest.main()
