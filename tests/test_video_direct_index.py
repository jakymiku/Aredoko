"""Generated catalog + supplied windows/vectors: atomicity and namespaces.

These tests do not evaluate video understanding and never use GPU or models.
"""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_video_window_decode as fixture
from test_video_coverage import generate
from ai_profiles import DEFAULT_PROFILE,video_profile_for
from production import ProductionCatalog
from previews import PreviewReader,ReaderChanged
from video_direct_index import VideoDirectIndex,CONTRACT
from video_input import VideoWindow
from video_previews import MediaDecodeCancelled


class Encoder:
    profile=replace(video_profile_for(),dimension=3)
    vector=[1,0,0]
    def encode(self,operation,window):return list(self.vector)


def window(start_ms,end_ms):
    count=(end_ms-start_ms+999)//1000
    return VideoWindow(start_ms,end_ms,1,1,tuple(b'\0'*3 for _ in range(count)))


class SuppliedIndexTests(unittest.TestCase):
    def setUp(self):
        fixture.VideoWindowTests.setUpClass();self.addCleanup(fixture.VideoWindowTests.tearDownClass)
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.base=Path(self.temporary.name);self.media=self.base/'media';self.media.mkdir()
        self.path=self.media/'generated.mp4';shutil.copyfile(fixture.VideoWindowTests.path,self.path)
        self.catalog=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.catalog.close)
        self.root=self.catalog.add_root(str(self.media));self.catalog.index.scan(self.root);self.catalog.sync_index()
        self.item=self.catalog.search()['items'][0]['id'];self.reader=PreviewReader(self.catalog)
        self.revision=self.reader.video_manifest(self.item)['revision'];self.encoder=Encoder()
        self.stage=self.base/'stages';self.stage.mkdir()
        self.index=VideoDirectIndex(self.catalog,self.encoder,reader=self.reader,stage_parent=self.stage)
        self.windows=[window(0,16000),window(16000,17500)]

    @contextmanager
    def supplied(self,windows=None,fail=False):
        def stream():
            yield from (self.windows if windows is None else windows)
            if fail:raise ValueError('generated decoding failed after output')
        @contextmanager
        def source(*args,**kwargs):yield stream()
        with patch.object(self.reader,'video_coverage_stream',side_effect=source):yield

    def snapshot(self):
        with self.index.store.connect() as db:
            return [db.execute('SELECT * FROM '+table+' ORDER BY item_id, rowid').fetchall()
                    for table in ('ai_video_direct_sources','ai_video_direct_windows')]

    def seed(self):
        with self.supplied():self.index.index_item(self.item,self.revision)
        return self.snapshot()

    def test_atomic_windows_timestamps_profile_and_success_marker(self):
        with self.supplied():report=self.index.index_item(self.item,self.revision)
        self.assertEqual((report['decoded_windows'],report['indexed_windows'],report['total_frames']),(2,2,18))
        self.assertEqual(report['contract'],CONTRACT)
        self.assertTrue(self.index.fresh(self.item,self.revision));self.assertFalse(self.index.fresh(self.item,'0'*64))
        with self.index.store.connect() as db:
            self.assertEqual(db.execute('SELECT start_ms,end_ms FROM ai_video_direct_windows ORDER BY ordinal').fetchall(),
                             [(0,16000),(16000,17500)])
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],1)
        self.assertFalse(DEFAULT_PROFILE.store_path(self.catalog.path).exists())
        self.assertEqual(list(self.stage.iterdir()),[])
        reopened=VideoDirectIndex(self.catalog,self.encoder)
        self.assertTrue(reopened.fresh(self.item,self.revision))

    def test_wrong_encoder_namespace_is_rejected_before_creating_a_sidecar(self):
        encoder=Encoder();encoder.profile=DEFAULT_PROFILE
        with self.assertRaises(ValueError):VideoDirectIndex(self.catalog,encoder)
        self.assertFalse(DEFAULT_PROFILE.store_path(self.catalog.path).exists())

    def test_failed_decoder_or_embedding_preserves_prior_revision(self):
        previous=self.seed()
        with self.supplied(fail=True),self.assertRaises(ValueError):self.index.index_item(self.item,self.revision)
        self.assertEqual(self.snapshot(),previous)
        self.encoder.vector=[float('nan'),0,0]
        with self.supplied(),self.assertRaises(ValueError):self.index.index_item(self.item,self.revision)
        self.assertEqual(self.snapshot(),previous);self.assertEqual(list(self.stage.iterdir()),[])

    def test_out_of_sequence_windows_are_rejected_and_publish_nothing(self):
        for windows in ([window(100,16100),window(16100,17500)],
                        [window(0,1000),window(1000,17500)],
                        [window(0,16000),window(15000,17500)]):
            with self.supplied(windows),self.assertRaises(ValueError):self.index.index_item(self.item,self.revision)
            self.assertEqual(self.snapshot(),[[],[]])

    def test_cancel_after_encoding_keeps_old_data(self):
        previous=self.seed();event=threading.Event()
        def cancelled(*args):event.set();return [0,1,0]
        with self.supplied(),patch.object(self.encoder,'encode',side_effect=cancelled):
            with self.assertRaises(MediaDecodeCancelled):self.index.index_item(self.item,self.revision,cancel=event)
        self.assertEqual(self.snapshot(),previous)

    def test_source_change_before_publication_keeps_old_data(self):
        previous=self.seed()
        with self.supplied(),patch.object(self.reader,'video_manifest',return_value={'revision':'0'*64}):
            with self.assertRaises(ReaderChanged):self.index.index_item(self.item,self.revision)
        self.assertEqual(self.snapshot(),previous)


class RealVideoIndexTests(unittest.TestCase):
    def setUp(self):
        fixture.VideoWindowTests.setUpClass();self.addCleanup(fixture.VideoWindowTests.tearDownClass)
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.base=Path(self.temporary.name);self.media=self.base/'media';self.media.mkdir()
        self.catalog=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.catalog.close)
        self.root=self.catalog.add_root(str(self.media))

    def prepare(self):
        self.catalog.index.scan(self.root);self.catalog.sync_index()
        self.item=self.catalog.search()['items'][0]['id'];self.reader=PreviewReader(self.catalog)
        self.revision=self.reader.video_manifest(self.item)['revision'];self.encoder=Encoder()
        self.stage=self.base/'stages';self.stage.mkdir(exist_ok=True)
        self.index=VideoDirectIndex(self.catalog,self.encoder,reader=self.reader,stage_parent=self.stage)

    def test_real_short_video_indexes_atomically(self):
        shutil.copyfile(fixture.VideoWindowTests.path,self.media/'generated.mp4');self.prepare()
        report=self.index.index_item(self.item,self.revision)
        self.assertEqual((report['decoded_windows'],report['indexed_windows'],report['total_frames']),(1,1,4))
        with self.index.store.connect() as db:
            self.assertEqual(db.execute('SELECT start_ms,end_ms FROM ai_video_direct_windows ORDER BY ordinal').fetchall(),[(0,3300)])
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_real_long_video_and_cancel_between_windows(self):
        long_path=self.media/'generated-long.mp4'
        scene='color=c=red:s=160x90:r=10:d=16[first];color=c=blue:s=160x90:r=10:d=1.5[second];[first][second]concat=n=2:v=1:a=0'
        generate(long_path,scene);self.prepare()
        report=self.index.index_item(self.item,self.revision)
        self.assertEqual((report['decoded_windows'],report['indexed_windows'],report['total_frames']),(2,2,18))
        previous_rows=None
        with self.index.store.connect() as db:
            previous_rows=db.execute('SELECT * FROM ai_video_direct_windows ORDER BY ordinal').fetchall()
        event=threading.Event();calls=[]
        def cancelling(operation,window):
            calls.append(window.start_ms)
            if len(calls)==2:event.set()
            return [1,0,0]
        with patch.object(self.encoder,'encode',side_effect=cancelling):
            with self.assertRaises(MediaDecodeCancelled):self.index.index_item(self.item,self.revision,cancel=event)
        self.assertEqual(calls,[0,16000])
        with self.index.store.connect() as db:
            self.assertEqual(db.execute('SELECT * FROM ai_video_direct_windows ORDER BY ordinal').fetchall(),previous_rows)
        self.assertEqual(list(self.stage.iterdir()),[])


if __name__=='__main__':unittest.main()
