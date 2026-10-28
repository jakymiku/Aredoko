"""Generated video/audio only: guarded PCM extraction, no model or index."""
import hashlib
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
from production import ProductionCatalog
from previews import PreviewReader,PreviewUnavailable,PreviewBusyError,ReaderChanged
from audio_input import AudioInputUnavailable
from video_previews import _executable,MediaDecodeCancelled,FORMATS


class VideoAudioSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory();base=Path(cls.temporary.name)
        cls.sound=base/'generated-delayed.mkv';cls.silent=base/'generated-no-track.mkv'
        environment={k:v for k,v in os.environ.items() if k.upper()!='FFREPORT'}
        common=[_executable('ffmpeg'),'-nostdin','-v','error','-f','lavfi','-i','color=c=blue:s=160x90:r=10:d=3.2']
        try:
            subprocess.run([*common,'-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=1.2',
                            '-map','0:v:0','-map','1:a:0','-af','asetpts=PTS+1/TB','-c:v','mpeg4','-c:a','pcm_s16le',
                            '-threads','1',str(cls.sound)],check=True,timeout=15,env=environment,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            subprocess.run([*common,'-an','-c:v','mpeg4','-threads','1',str(cls.silent)],check=True,timeout=15,env=environment,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        except BaseException:cls.temporary.cleanup();raise

    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()

    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.base=Path(temporary.name)
        self.media=self.base/'generated';self.media.mkdir();self.path=self.media/'generated.mkv';shutil.copyfile(self.sound,self.path)
        self.catalog=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.catalog.close)
        self.root=self.catalog.add_root(str(self.media));self.catalog.index.scan(self.root);self.catalog.sync_index()
        self.item=self.catalog.search()['items'][0]['id'];self.reader=PreviewReader(self.catalog)
        self.revision=self.reader.video_manifest(self.item)['revision']

    def released(self,stream):
        self.assertFalse(stream.reader.is_alive());self.assertIsNotNone(stream.process.poll())
        self.assertTrue(self.reader.audio_stream_slot.acquire(blocking=False));self.reader.audio_stream_slot.release()

    def test_video_audio_keeps_leading_offset_and_real_track_eof_without_source_changes(self):
        before=(self.path.stat().st_mtime_ns,hashlib.sha256(self.path.read_bytes()).hexdigest())
        metadata=self.catalog.get(self.item);launch=subprocess.Popen
        with patch('audio_stream.subprocess.Popen',wraps=launch) as started:
            with self.reader.video_audio_pcm_stream(self.item,self.revision) as stream:windows=list(stream)
        self.assertTrue(stream.complete);self.released(stream)
        values=[v[0] for w in windows for v in struct.iter_unpack('<f',w.data)]
        self.assertEqual(windows[0].start_ms,0)
        self.assertGreaterEqual(len(values),int(2.1*16000));self.assertLess(len(values),3*16000)
        def energy(at):return sum(v*v for v in values[int(at*16000):int((at+.1)*16000)])
        self.assertLess(energy(.5),.001);self.assertGreater(energy(1.5),1)
        self.assertEqual(started.call_count,1);args=started.call_args.args[0]
        self.assertEqual(args[args.index('-i')+1],'fd:');self.assertNotIn(str(self.path),args)
        self.assertEqual(args[args.index('-format_whitelist')+1],FORMATS)
        self.assertEqual(args[args.index('-protocol_whitelist')+1],'fd,pipe')
        self.assertEqual(args[args.index('-map')+1],'0:a:0');self.assertIn('-vn',args);self.assertIn('-max_pixels',args)
        self.assertEqual(before,(self.path.stat().st_mtime_ns,hashlib.sha256(self.path.read_bytes()).hexdigest()))
        self.assertEqual(self.catalog.get(self.item),metadata)

    def test_video_without_audio_track_fails_instead_of_inventing_silence(self):
        shutil.copyfile(self.silent,self.path);self.catalog.index.scan(self.root);self.catalog.sync_index()
        revision=self.reader.video_manifest(self.item)['revision']
        with self.reader.video_audio_pcm_stream(self.item,revision) as stream,self.assertRaises(AudioInputUnavailable):list(stream)
        self.assertFalse(stream.complete);self.released(stream)

    def test_scope_change_discards_remaining_pcm_and_releases_owned_resources(self):
        with self.reader.video_audio_pcm_stream(self.item,self.revision) as stream:
            next(stream);self.catalog.set_excludes(self.root,['*.mkv'])
            with self.assertRaises(PreviewUnavailable):next(stream)
        self.assertFalse(stream.complete);self.released(stream)

    def test_early_close_does_not_claim_successful_whole_track(self):
        with self.reader.video_audio_pcm_stream(self.item,self.revision) as stream:
            next(stream);self.assertFalse(stream.complete)
        self.assertFalse(stream.complete);self.released(stream)

    def test_precancel_stale_revision_wrong_kind_and_busy_slot_start_no_decoder(self):
        stop=threading.Event();stop.set()
        with patch('audio_stream.subprocess.Popen') as started:
            with self.assertRaises(MediaDecodeCancelled):
                with self.reader.video_audio_pcm_stream(self.item,self.revision,cancel=stop):pass
            with self.assertRaises(ReaderChanged):
                with self.reader.video_audio_pcm_stream(self.item,'0'*64):pass
            with self.assertRaises(ValueError):
                with self.reader.video_audio_pcm_stream(self.item,'bad'):pass
            with self.reader.audio_stream_slot,self.assertRaises(PreviewBusyError):
                with self.reader.video_audio_pcm_stream(self.item,self.revision):pass
            started.assert_not_called()
        # The old audio-only API must still reject a video item.
        with self.assertRaises(PreviewUnavailable):self.reader.audio_manifest(self.item)

    def test_video_source_limit_failure_releases_the_pcm_slot(self):
        with patch('audio_stream.MAX_VIDEO_BYTES',1),patch('audio_stream.subprocess.Popen') as started:
            with self.assertRaises(AudioInputUnavailable):
                with self.reader.video_audio_pcm_stream(self.item,self.revision):pass
            started.assert_not_called()
        self.assertTrue(self.reader.audio_stream_slot.acquire(blocking=False));self.reader.audio_stream_slot.release()

    def test_track_probe_uses_guarded_fd_and_rejects_malformed_metadata(self):
        with patch('audio_stream._run',return_value=b'{"streams":[{"index":1}]}') as run:
            self.assertTrue(self.reader.video_audio_available(self.item,self.revision))
        args=run.call_args.args[0]
        self.assertEqual(args[args.index('-i')+1],'fd:');self.assertNotIn(str(self.path),args)
        self.assertEqual(args[args.index('-select_streams')+1],'a:0')
        for data in (b'{}',b'bad',b'{"streams":null}',b'{"streams":[null]}',
                     b'{"streams":[{"index":true}]}',b'{"streams":[{"index":16}]}',
                     b'{"streams":[{"index":1},{"index":2}]}'):
            with self.subTest(data=data),patch('audio_stream._run',return_value=data),self.assertRaises(AudioInputUnavailable):
                self.reader.video_audio_available(self.item,self.revision)
        def scope_change(*args,**kwargs):
            self.catalog.set_excludes(self.root,['*.mkv']);return b'{"streams":[]}'
        with patch('audio_stream._run',side_effect=scope_change),self.assertRaises(PreviewUnavailable):
            self.reader.video_audio_available(self.item,self.revision)
        self.assertTrue(self.reader.audio_stream_slot.acquire(blocking=False));self.reader.audio_stream_slot.release()

    def test_track_probe_cancellation_is_not_treated_as_no_track(self):
        stop=threading.Event()
        def cancel(*args,**kwargs):stop.set();return b'{"streams":[]}'
        with patch('audio_stream._run',side_effect=cancel),self.assertRaises(MediaDecodeCancelled):
            self.reader.video_audio_available(self.item,self.revision,cancel=stop)
        with patch('audio_stream._run') as run,self.assertRaises(MediaDecodeCancelled):
            self.reader.video_audio_available(self.item,self.revision,cancel=stop)
        run.assert_not_called()


if __name__=='__main__':unittest.main()
