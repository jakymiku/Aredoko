"""Guarded registered-video input. Generated MP4 only; no model or GUI."""
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_video_window_decode as fixture
from previews import PreviewReader,PreviewUnavailable,ReaderChanged
from production import ProductionCatalog
from video_input import VideoWindow
from video_previews import MediaDecodeCancelled


class VideoWindowSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.VideoWindowTests.setUpClass()
    @classmethod
    def tearDownClass(cls):fixture.VideoWindowTests.tearDownClass()
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.base=Path(self.temporary.name);self.media=self.base/'media';self.media.mkdir()
        self.path=self.media/'generated.mp4';shutil.copyfile(fixture.VideoWindowTests.path,self.path)
        self.catalog=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.catalog.close)
        self.root=self.catalog.add_root(str(self.media));self.catalog.index.scan(self.root);self.catalog.sync_index()
        self.item=self.catalog.search()['items'][0]['id'];self.reader=PreviewReader(self.catalog)
        self.revision=self.reader.video_manifest(self.item)['revision']
    def read(self,**options):return self.reader.video_input_window(self.item,0,3300,self.revision,total_duration_ms=3300,**options)

    def test_registered_source_yields_rgb_windows_with_verified_revision(self):
        result=self.read();self.assertIsInstance(result,VideoWindow)
        self.assertEqual((result.start_ms,result.end_ms,len(result.frames)),(0,3300,4))
        self.assertEqual(self.reader.video_manifest(self.item)['revision'],self.revision)

    def test_bad_interval_revision_or_cancel_does_not_decode(self):
        stop=threading.Event();stop.set()
        with patch('previews.read_video_window') as decoder:
            with self.assertRaises(MediaDecodeCancelled):self.read(cancel=stop)
            with self.assertRaises(ValueError):self.reader.video_input_window(self.item,0,16001,self.revision,total_duration_ms=20000)
            with self.assertRaises(ValueError):self.reader.video_input_window(self.item,0,1000,'bad',total_duration_ms=1000)
            with self.assertRaises(ReaderChanged):self.reader.video_input_window(self.item,0,1000,'0'*64,total_duration_ms=1000)
            decoder.assert_not_called()

    def test_scope_revoked_during_decode_discards_pixels(self):
        def excluded(*args,**kwargs):
            self.catalog.set_excludes(self.root,['*.mp4'])
            return VideoWindow(0,1000,1,1,(b'\0'*3,))
        with patch('previews.read_video_window',side_effect=excluded),self.assertRaises(ReaderChanged):self.read()

    def test_source_replaced_during_decode_discards_pixels(self):
        def changed(*args,**kwargs):
            self.path.write_bytes(b'changed generated source')
            return VideoWindow(0,1000,1,1,(b'\0'*3,))
        with patch('previews.read_video_window',side_effect=changed),self.assertRaises(PreviewUnavailable):self.read()

    def test_cancel_after_decode_discards_pixels_and_releases_slot(self):
        stop=threading.Event()
        def cancelled(*args,**kwargs):stop.set();return VideoWindow(0,1000,1,1,(b'\0'*3,))
        with patch('previews.read_video_window',side_effect=cancelled),self.assertRaises(MediaDecodeCancelled):self.read(cancel=stop)
        self.assertTrue(self.reader.slots.acquire(blocking=False));self.reader.slots.release()


if __name__=='__main__':unittest.main()
