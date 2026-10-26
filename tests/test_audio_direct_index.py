"""Generated catalog + supplied PCM/vectors: atomicity, namespaces and backup.

These tests do not evaluate speech or music understanding and never use GPU.
"""
from contextlib import closing,contextmanager
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
from ai_profiles import DEFAULT_PROFILE,audio_profile_for
from ai_search import VectorStore,AIUnavailable
from audio_input import PCMWindow,MediaDecodeCancelled
from audio_direct_index import AudioDirectIndex,CONTRACT
from production import ProductionCatalog
from previews import PreviewReader,ReaderChanged,PreviewUnavailable
from live_backup import capture_live,BackupSelection
from storage_backup import backup,restore,RecoveryError,_database
from test_audio_input import wav_bytes


class Encoder:
    profile=replace(audio_profile_for(),dimension=3)
    vector=[1,0,0]
    def encode(self,operation,window):return list(self.vector)


class SuppliedWindows:
    def __init__(self,windows,fail=False):self.windows=windows;self.complete=False;self.fail=fail
    def __iter__(self):
        yield from self.windows
        if self.fail:raise ValueError('generated decoding failed after output')
        self.complete=True


class DirectAudioIndexTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.base=Path(self.temporary.name);self.media=self.base/'media';self.media.mkdir()
        self.path=self.media/'generated.wav';self.path.write_bytes(wav_bytes())
        self.catalog=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.catalog.close)
        self.root=self.catalog.add_root(str(self.media));self.catalog.index.scan(self.root);self.catalog.sync_index()
        self.item=self.catalog.search()['items'][0]['id'];self.reader=PreviewReader(self.catalog)
        self.revision=self.reader.audio_manifest(self.item)['revision'];self.encoder=Encoder()
        self.stage=self.base/'stages';self.stage.mkdir()
        self.index=AudioDirectIndex(self.catalog,self.encoder,reader=self.reader,stage_parent=self.stage)
        self.windows=[PCMWindow(0,30000,struct.pack('<f',.25)*480000),PCMWindow(30000,30000,struct.pack('<f',-.25)*16000)]

    @contextmanager
    def supplied(self,windows=None,fail=False):
        @contextmanager
        def source(*args,**kwargs):yield SuppliedWindows(self.windows if windows is None else windows,fail)
        with patch.object(self.reader,'audio_pcm_stream',side_effect=source):yield

    def snapshot(self):
        with self.index.store.connect() as db:
            return [db.execute('SELECT * FROM '+table+' ORDER BY item_id, rowid').fetchall()
                    for table in ('ai_audio_direct_sources','ai_audio_direct_windows')]

    def seed(self):
        with self.supplied():self.index.index_item(self.item,self.revision)
        return self.snapshot()

    def test_atomic_windows_timestamps_profile_and_success_marker(self):
        with self.supplied():report=self.index.index_item(self.item,self.revision)
        self.assertEqual((report['decoded_windows'],report['indexed_windows'],report['total_frames']),(2,2,496000))
        self.assertTrue(self.index.fresh(self.item,self.revision));self.assertFalse(self.index.fresh(self.item,'0'*64))
        with self.index.store.connect() as db:
            self.assertEqual(db.execute('SELECT start_ms,end_ms FROM ai_audio_direct_windows ORDER BY ordinal').fetchall(),[(0,30000),(30000,31000)])
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM ai_audio_segments').fetchone()[0],0)
        self.assertFalse(DEFAULT_PROFILE.store_path(self.catalog.path).exists())
        self.assertEqual(list(self.stage.iterdir()),[])
        reopened=AudioDirectIndex(self.catalog,self.encoder)
        self.assertTrue(reopened.fresh(self.item,self.revision))

    def test_wrong_encoder_namespace_is_rejected_before_creating_a_sidecar(self):
        encoder=Encoder();encoder.profile=DEFAULT_PROFILE
        with self.assertRaises(ValueError):AudioDirectIndex(self.catalog,encoder)
        self.assertFalse(DEFAULT_PROFILE.store_path(self.catalog.path).exists())

    def test_failed_decoder_or_embedding_preserves_prior_revision(self):
        previous=self.seed()
        with self.supplied(fail=True),self.assertRaises(ValueError):self.index.index_item(self.item,self.revision)
        self.assertEqual(self.snapshot(),previous)
        self.encoder.vector=[float('nan'),0,0]
        with self.supplied(),self.assertRaises(ValueError):self.index.index_item(self.item,self.revision)
        self.assertEqual(self.snapshot(),previous);self.assertEqual(list(self.stage.iterdir()),[])

    def test_all_silent_success_clears_old_windows_and_is_fresh(self):
        self.seed()
        silent=[PCMWindow(0,30000,b'\0'*(480000*4))]
        with self.supplied(silent),patch.object(self.encoder,'encode') as encode:
            report=self.index.index_item(self.item,self.revision);encode.assert_not_called()
        self.assertEqual(report['indexed_windows'],0);self.assertTrue(self.index.fresh(self.item,self.revision))
        self.assertEqual(self.snapshot()[1],[])

    def test_cancel_after_encoding_or_before_commit_keeps_old_data(self):
        previous=self.seed();event=threading.Event()
        def cancelled(*args):event.set();return [0,1,0]
        with self.supplied(),patch.object(self.encoder,'encode',side_effect=cancelled):
            with self.assertRaises(MediaDecodeCancelled):self.index.index_item(self.item,self.revision,cancel=event)
        self.assertEqual(self.snapshot(),previous)
        event.clear();real=self.reader.audio_manifest;calls=[]
        def late_cancel(*args):
            calls.append(True)
            if len(calls)==2:event.set()
            return real(*args)
        with self.supplied(),patch.object(self.reader,'audio_manifest',side_effect=late_cancel):
            with self.assertRaises(MediaDecodeCancelled):self.index.index_item(self.item,self.revision,cancel=event)
        self.assertEqual(self.snapshot(),previous)

    def test_source_change_or_unregister_before_publication_keeps_old_data(self):
        previous=self.seed()
        def changed(*args):self.path.write_bytes(b'changed generated input');return [0,1,0]
        with self.supplied(),patch.object(self.encoder,'encode',side_effect=changed):
            with self.assertRaises(PreviewUnavailable):self.index.index_item(self.item,self.revision)
        self.assertEqual(self.snapshot(),previous)
        self.path.write_bytes(wav_bytes());self.catalog.index.scan(self.root);self.catalog.sync_index()
        self.revision=self.reader.audio_manifest(self.item)['revision']
        removed_once=[]
        def removed(*args):
            if not removed_once:self.catalog.unregister_root(self.root);removed_once.append(True)
            return [0,1,0]
        with self.supplied(),patch.object(self.encoder,'encode',side_effect=removed):
            with self.assertRaises(PreviewUnavailable):self.index.index_item(self.item,self.revision)
        self.assertEqual(self.snapshot(),previous)

    def test_source_change_during_commit_rolls_back_both_tables(self):
        previous=self.seed();real=self.reader.audio_manifest;calls=[]
        def changed(*args):
            calls.append(True)
            if len(calls)==2:raise ReaderChanged('generated source changed at publication boundary')
            return real(*args)
        with self.supplied(),patch.object(self.reader,'audio_manifest',side_effect=changed),self.assertRaises(ReaderChanged):
            self.index.index_item(self.item,self.revision)
        self.assertEqual(self.snapshot(),previous)

    def test_disk_failure_rolls_back_and_private_stage_is_removed(self):
        previous=self.seed()
        with self.supplied(),patch('audio_direct_index.STAGE_BYTES',4096),self.assertRaises(sqlite3.Error):
            self.index.index_item(self.item,self.revision)
        self.assertEqual(self.snapshot(),previous);self.assertEqual(list(self.stage.iterdir()),[])

    def test_cancel_while_waiting_for_backup_fence_is_owned_and_safe(self):
        previous=self.seed();event=threading.Event();reached=threading.Event();errors=[]
        def work():
            try:
                with self.supplied(),patch.object(self.encoder,'encode',side_effect=lambda *a:(reached.set() or [0,1,0])):
                    self.index.index_item(self.item,self.revision,cancel=event)
            except Exception as error:errors.append(error)
        with self.catalog.writer_fence.pause():
            thread=threading.Thread(target=work);thread.start()
            self.assertTrue(reached.wait(3));event.set();thread.join(3)
            self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors),1);self.assertIsInstance(errors[0],MediaDecodeCancelled)
        self.assertEqual(self.snapshot(),previous)

    def test_new_and_old_namespaces_backup_restore_without_mixing(self):
        previous=self.seed()
        legacy=VectorStore(DEFAULT_PROFILE.store_path(self.catalog.path),DEFAULT_PROFILE,writer_fence=self.catalog.writer_fence)
        with legacy.connect() as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],0)
        bundle=self.base/'bundle'
        capture_live(self.catalog,bundle,quiesce=self.catalog.writer_fence.pause,
                     selection=BackupSelection(settings=False,history=True,reader_progress=True,vectors=True))
        destination=self.base/'restored';restore(bundle,destination)
        path=self.profile_path(destination/'catalog.sqlite')
        with closing(sqlite3.connect(path)) as db:
            restored=[db.execute('SELECT * FROM '+table+' ORDER BY item_id,rowid').fetchall()
                      for table in ('ai_audio_direct_sources','ai_audio_direct_windows')]
        self.assertEqual(restored,previous)
        self.assertTrue(DEFAULT_PROFILE.store_path(destination/'catalog.sqlite').is_file())

    def profile_path(self,path):return self.encoder.profile.store_path(path)

    def test_backup_rejects_new_tables_with_old_version_marker(self):
        self.seed()
        with self.index.store.connect() as db:db.execute('PRAGMA user_version=0')
        with self.assertRaises(RecoveryError):_database(self.index.store.path,'vectors')

    def test_future_vector_version_is_rejected_before_writing(self):
        previous=self.seed()
        with self.index.store.connect() as db:db.execute('PRAGMA user_version=2')
        with self.assertRaises(AIUnavailable):AudioDirectIndex(self.catalog,self.encoder)
        self.assertEqual(self.snapshot(),previous)

    def test_root_purge_cleans_both_direct_tables_and_keeps_generated_media(self):
        self.seed();before=self.path.read_bytes()
        self.catalog.unregister_root(self.root);self.catalog.purge_inactive_root(self.root,consent=True)
        self.assertEqual(self.snapshot(),[[],[]]);self.assertEqual(self.path.read_bytes(),before)

    def test_backup_during_encoding_sees_only_previous_complete_item(self):
        previous=self.seed();reached=threading.Event();release=threading.Event();errors=[]
        def encode(*args):
            reached.set()
            if not release.wait(10):raise RuntimeError('generated encode gate expired')
            return [0,1,0]
        def work():
            try:
                with self.supplied(),patch.object(self.encoder,'encode',side_effect=encode):
                    self.index.index_item(self.item,self.revision)
            except Exception as error:errors.append(error)
        thread=threading.Thread(target=work);thread.start()
        try:
            self.assertTrue(reached.wait(3))
            bundle=self.base/'during-encode'
            capture_live(self.catalog,bundle,quiesce=self.catalog.writer_fence.pause,
                         selection=BackupSelection(settings=False,history=True,reader_progress=True,vectors=True))
        finally:release.set();thread.join(5)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        self.assertNotEqual(self.snapshot(),previous)
        destination=self.base/'old-complete';restore(bundle,destination)
        with closing(sqlite3.connect(self.profile_path(destination/'catalog.sqlite'))) as db:
            self.assertEqual(db.execute('SELECT * FROM ai_audio_direct_windows ORDER BY item_id,rowid').fetchall(),previous[1])


if __name__=='__main__':unittest.main()
