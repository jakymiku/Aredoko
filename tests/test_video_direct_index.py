"""Generated catalog + supplied windows/vectors: atomicity and namespaces.

These tests do not evaluate video understanding and never use GPU or models.
"""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import shutil
import subprocess
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


class SuppliedCoverage:
    """Iterator double that declares its probed total like the real stream."""
    def __init__(self,windows,total,fail=False):
        self._windows=windows;self.total_duration_ms=total;self._fail=fail
    def __iter__(self):
        yield from self._windows
        if self._fail:raise ValueError('generated decoding failed after output')


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
    def supplied(self,windows=None,fail=False,total=None):
        chosen=self.windows if windows is None else windows
        coverage=SuppliedCoverage(chosen,chosen[-1].end_ms if total is None else total,fail)
        @contextmanager
        def source(*args,**kwargs):yield coverage
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

    def test_progress_describes_private_preparation_and_never_claims_publication(self):
        previous=self.seed();events=[]
        def progress(value):
            events.append(value)
            self.assertEqual(self.snapshot(),previous)
        with self.supplied(),patch.object(self.encoder,'encode',return_value=[0,1,0]):
            self.index.index_item(self.item,self.revision,progress=progress)
        self.assertEqual([(v['phase'],v['prepared_ms'],v['prepared_windows']) for v in events],
            [('decoding',0,0),('encoding',0,0),('decoding',16000,1),('encoding',16000,1),('decoding',17500,2),('saving',17500,2)])
        self.assertTrue(all(v['total_ms']==17500 and v['item_id']==self.item for v in events))
        self.assertNotEqual(self.snapshot(),previous);self.assertEqual(list(self.stage.iterdir()),[])

    def test_cancel_from_progress_before_encoding_keeps_previous_index(self):
        previous=self.seed();stop=threading.Event()
        def progress(value):
            if value['phase']=='encoding':stop.set()
        with self.supplied(),patch.object(self.encoder,'encode') as encode,self.assertRaises(MediaDecodeCancelled):
            self.index.index_item(self.item,self.revision,cancel=stop,progress=progress)
        encode.assert_not_called();self.assertEqual(self.snapshot(),previous)
        self.assertEqual(list(self.stage.iterdir()),[])

    def test_wrong_encoder_namespace_is_rejected_before_creating_a_sidecar(self):
        encoder=Encoder();encoder.profile=DEFAULT_PROFILE
        with self.assertRaises(ValueError):VideoDirectIndex(self.catalog,encoder)
        self.assertFalse(DEFAULT_PROFILE.store_path(self.catalog.path).exists())

    def test_corrupt_coverage_is_not_reused_as_fresh(self):
        mutations=[
            'DELETE FROM ai_video_direct_windows WHERE item_id=? AND ordinal=1',
            "UPDATE ai_video_direct_windows SET vector=x'000000000000000000000000' WHERE item_id=? AND ordinal=1",
            'UPDATE ai_video_direct_sources SET total_frames=17 WHERE item_id=?',
            "UPDATE ai_video_direct_sources SET indexed_windows='invalid' WHERE item_id=?",
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.seed()
                with self.index.store.connect() as db:db.execute(mutation,(self.item,))
                self.assertFalse(self.index.fresh(self.item,self.revision))
                with self.supplied():self.index.index_item(self.item,self.revision)
                self.assertTrue(self.index.fresh(self.item,self.revision))

    def test_fresh_check_observes_cancellation_without_loading_the_encoder(self):
        self.seed();cancel=threading.Event();cancel.set()
        with patch.object(self.encoder,'encode',side_effect=AssertionError('Unexpected inference')):
            with self.assertRaises(MediaDecodeCancelled):self.index.fresh(self.item,self.revision,cancel=cancel)

    def test_failed_decoder_or_embedding_preserves_prior_revision(self):
        previous=self.seed()
        with self.supplied(fail=True),self.assertRaises(ValueError):self.index.index_item(self.item,self.revision)
        self.assertEqual(self.snapshot(),previous)
        self.encoder.vector=[float('nan'),0,0]
        with self.supplied(),self.assertRaises(ValueError):self.index.index_item(self.item,self.revision)
        self.assertEqual(self.snapshot(),previous);self.assertEqual(list(self.stage.iterdir()),[])

    def test_owned_decoder_failure_after_complete_pixels_cannot_publish(self):
        from video_stream import FRAME_BYTES
        from video_window_decode import VideoWindowUnavailable
        previous=self.seed();launch=subprocess.Popen;children=[]
        def failed(args,**options):
            code=f"import sys;sys.stdout.buffer.write(b'x'*{FRAME_BYTES*4});sys.exit(7)"
            child=launch([sys.executable,'-c',code],**options);children.append(child);return child
        with patch('video_stream.probe_video_duration_ms',return_value=3300),patch('video_stream.subprocess.Popen',side_effect=failed):
            with self.assertRaises(VideoWindowUnavailable):self.index.index_item(self.item,self.revision)
        self.assertEqual(self.snapshot(),previous);self.assertEqual(list(self.stage.iterdir()),[])
        self.assertTrue(children);self.assertTrue(all(child.poll() is not None for child in children))
        self.assertTrue(self.reader.video_stream_slot.acquire(blocking=False));self.reader.video_stream_slot.release()

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

    def test_stream_ending_before_its_declared_total_publishes_nothing(self):
        with self.supplied(total=33000),self.assertRaises(ValueError):self.index.index_item(self.item,self.revision)
        self.assertEqual(self.snapshot(),[[],[]])
        with self.supplied([window(0,16000)],total=17500),self.assertRaises(ValueError):
            self.index.index_item(self.item,self.revision)
        self.assertEqual(self.snapshot(),[[],[]])

    def test_failure_after_copy_rolls_back_to_prior_publication(self):
        previous=self.seed();calls=[]
        def validator():
            calls.append(True)
            if len(calls)==3:raise MediaDecodeCancelled('cancelled after copy')
        with self.supplied():
            with self.assertRaises(MediaDecodeCancelled):self.index.index_item(self.item,self.revision,validate=validator)
        self.assertEqual(len(calls),3)  # Start, pre-copy and post-copy checks.
        self.assertEqual(self.snapshot(),previous);self.assertEqual(list(self.stage.iterdir()),[])

    def test_insert_abort_mid_copy_rolls_back_to_prior_publication(self):
        import sqlite3
        previous=self.seed()
        with self.index.store.connect() as db:
            db.execute("CREATE TRIGGER fail_copy BEFORE INSERT ON ai_video_direct_windows "
                       "WHEN NEW.ordinal>=2 BEGIN SELECT RAISE(ABORT,'copy failed'); END")
        try:
            with self.supplied([window(0,16000),window(16000,32000),window(32000,33000)]):
                with self.assertRaises(sqlite3.Error):self.index.index_item(self.item,self.revision)
        finally:
            with self.index.store.connect() as db:db.execute('DROP TRIGGER IF EXISTS fail_copy')
        self.assertEqual(self.snapshot(),previous);self.assertEqual(list(self.stage.iterdir()),[])


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
        launch=subprocess.Popen
        with patch('video_stream.subprocess.Popen',wraps=launch) as started:
            report=self.index.index_item(self.item,self.revision)
        self.assertEqual(sum('-vf' in call.args[0] for call in started.call_args_list),1)
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
