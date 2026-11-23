"""Generated video and owned fake decoders: coverage, backpressure and cleanup."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
from video_stream import VideoCoverageStream,FRAME_BYTES
from video_coverage import iter_video_coverage,VideoCoverageUnavailable
from video_window_decode import VideoWindowUnavailable
from video_previews import MediaDecodeCancelled
import test_video_coverage as fixture


class GeneratedVideoStreamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.CoverageTests.setUpClass()
    @classmethod
    def tearDownClass(cls):fixture.CoverageTests.tearDownClass()

    def test_single_decoder_matches_existing_boundary_windows_and_tail(self):
        path=fixture.CoverageTests.boundary_path
        before=(path.stat().st_mtime_ns,hashlib.sha256(path.read_bytes()).hexdigest())
        with path.open('rb') as source:old=list(iter_video_coverage(source))
        children=[];launch=subprocess.Popen
        def start(args,**options):
            child=launch(args,**options);children.append((args,options,child));return child
        with path.open('rb') as source,patch('video_stream.subprocess.Popen',side_effect=start):
            with VideoCoverageStream(source) as stream:
                self.assertIsNone(stream.total_duration_ms);self.assertEqual(children,[])
                current=list(stream)
            self.assertFalse(source.closed)
        self.assertTrue(stream.complete);self.assertEqual(stream.total_duration_ms,17500)
        self.assertEqual([(w.start_ms,w.end_ms,len(w.frames)) for w in current],[(0,16000,16),(16000,17500,2)])
        self.assertEqual([w.frames for w in current],[w.frames for w in old])
        decoders=[(args,options,child) for args,options,child in children if '-vf' in args]
        self.assertEqual(len(decoders),1);args,options,child=decoders[0]
        self.assertEqual(args[args.index('-i')+1],'fd:');self.assertNotIn(str(path),args)
        self.assertEqual(args[args.index('-protocol_whitelist')+1],'fd,pipe')
        self.assertFalse(options['shell']);self.assertNotIn('FFREPORT',options['env'])
        self.assertIsNotNone(child.poll());self.assertFalse(stream.reader.is_alive())
        self.assertEqual(before,(path.stat().st_mtime_ns,hashlib.sha256(path.read_bytes()).hexdigest()))

    def test_early_close_and_cancel_reap_the_backpressured_decoder(self):
        for cancel_next in (False,True):
            with self.subTest(cancel_next=cancel_next),fixture.CoverageTests.long_path.open('rb') as source:
                stop=threading.Event()
                with VideoCoverageStream(source,cancel=stop) as stream:
                    self.assertEqual(len(next(stream).frames),16)
                    if cancel_next:
                        stop.set()
                        with self.assertRaises(MediaDecodeCancelled):next(stream)
                self.assertFalse(stream.complete);self.assertTrue(stream.closed)
                self.assertIsNotNone(stream.process.poll());self.assertFalse(stream.reader.is_alive())
                self.assertLessEqual(stream.messages.qsize(),1);self.assertFalse(source.closed)

    def test_continuous_sampling_preserves_existing_pixels_for_moving_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'generated-moving.mp4'
            fixture.generate(path,'testsrc2=s=160x90:r=10:d=17.5')
            with path.open('rb') as source:old=list(iter_video_coverage(source))
            with path.open('rb') as source,VideoCoverageStream(source) as stream:current=list(stream)
            self.assertTrue(stream.complete)
            self.assertEqual([w.frames for w in current],[w.frames for w in old])

    def test_source_scope_revocation_discards_next_window_and_releases_decoder(self):
        revoked=threading.Event()
        def guard():
            if revoked.is_set():raise RuntimeError('generated scope revoked')
        with fixture.CoverageTests.long_path.open('rb') as source,VideoCoverageStream(source,guard=guard) as stream:
            next(stream);revoked.set()
            with self.assertRaisesRegex(RuntimeError,'scope revoked'):next(stream)
        self.assertFalse(stream.complete);self.assertIsNotNone(stream.process.poll())
        self.assertFalse(stream.reader.is_alive())


class DecoderFailureTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.path=Path(self.temporary.name)/'generated.mp4';self.path.write_bytes(b'generated-only')

    def decoder(self,code):
        launch=subprocess.Popen;children=[]
        def start(args,**options):
            child=launch([sys.executable,'-c',code],**options);children.append(child);return child
        return patch('video_stream.subprocess.Popen',side_effect=start),children

    def test_short_partial_extra_and_failed_output_never_complete(self):
        cases=[(1000,"import sys;sys.stdout.buffer.write(b'x'*12)"),
               (2000,f"import sys;sys.stdout.buffer.write(b'x'*{FRAME_BYTES})"),
               (1000,f"import sys;sys.stdout.buffer.write(b'x'*{FRAME_BYTES*2})"),
               (1000,f"import sys;sys.stdout.buffer.write(b'x'*{FRAME_BYTES});sys.exit(7)")]
        for duration,code in cases:
            mocked,children=self.decoder(code)
            with self.subTest(duration=duration,code=code),self.path.open('rb') as source,\
                 patch('video_stream.probe_video_duration_ms',return_value=duration),mocked:
                with VideoCoverageStream(source) as stream,self.assertRaises(VideoWindowUnavailable):list(stream)
                self.assertFalse(stream.complete);self.assertTrue(stream.closed)
                self.assertTrue(all(child.poll() is not None for child in children));self.assertFalse(stream.reader.is_alive())
                self.assertFalse(source.closed)

    def test_no_progress_deadline_kills_and_reaps_owned_process(self):
        mocked,children=self.decoder('import time;time.sleep(20)');began=time.monotonic()
        with self.path.open('rb') as source,patch('video_stream.probe_video_duration_ms',return_value=1000),\
             patch('video_stream.WINDOW_SECONDS',.05),mocked:
            with VideoCoverageStream(source) as stream,self.assertRaises(VideoWindowUnavailable):next(stream)
        self.assertLess(time.monotonic()-began,3);self.assertTrue(all(child.poll() is not None for child in children))
        self.assertFalse(stream.reader.is_alive());self.assertFalse(stream.complete)

    def test_reader_start_failure_still_reaps_the_decoder(self):
        mocked,children=self.decoder('import time;time.sleep(20)')
        with self.path.open('rb') as source,patch('video_stream.probe_video_duration_ms',return_value=1000),\
             mocked,patch('video_stream.threading.Thread.start',side_effect=RuntimeError('generated thread failure')):
            with VideoCoverageStream(source) as stream,self.assertRaisesRegex(RuntimeError,'thread failure'):next(stream)
        self.assertTrue(all(child.poll() is not None for child in children));self.assertFalse(stream.complete)

    def test_unknown_duration_and_precancel_do_not_start_a_decoder(self):
        with self.path.open('rb') as source,patch('video_stream.probe_video_duration_ms',side_effect=VideoCoverageUnavailable('no duration')),\
             patch('video_stream.subprocess.Popen') as start:
            with VideoCoverageStream(source) as stream,self.assertRaises(VideoCoverageUnavailable):next(stream)
            start.assert_not_called()
        stop=threading.Event();stop.set()
        with self.path.open('rb') as source,patch('video_stream.probe_video_duration_ms') as probe,patch('video_stream.subprocess.Popen') as start:
            with VideoCoverageStream(source,cancel=stop) as stream,self.assertRaises(MediaDecodeCancelled):next(stream)
            probe.assert_not_called();start.assert_not_called()

    def test_open_handle_change_during_decode_is_rejected(self):
        mocked,children=self.decoder(f"import sys,time;sys.stdout.buffer.write(b'x'*{FRAME_BYTES*16});sys.stdout.buffer.flush();time.sleep(20)")
        with self.path.open('rb') as source,patch('video_stream.probe_video_duration_ms',return_value=17000),mocked:
            with VideoCoverageStream(source) as stream:
                self.assertEqual(len(next(stream).frames),16);self.path.write_bytes(b'changed generated source')
                with self.assertRaises(VideoWindowUnavailable):next(stream)
        self.assertTrue(all(child.poll() is not None for child in children));self.assertFalse(stream.reader.is_alive())


if __name__=='__main__':unittest.main()
