"""CPU-only generated audio and owned child lifecycle; no model or GUI."""
import contextlib
import io
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import wave

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import audio_stream as audio


@contextlib.contextmanager
def fake_decoder(code,**kwargs):
    original=subprocess.Popen
    processes=[]
    calls=[]
    def launch(args,**options):
        calls.append((args,options))
        process=original([sys.executable,'-c',code],**options)
        processes.append(process)
        return process
    with tempfile.TemporaryFile() as source:
        source.write(b'generated audio input');source.flush()
        with patch.object(audio,'_executable',return_value='fixed-ffmpeg'),patch.object(audio.subprocess,'Popen',side_effect=launch):
            stream=audio.PCMStream(source,**kwargs)
            try:yield stream,processes,calls
            finally:stream.close()


class AudioStreamTests(unittest.TestCase):
    def test_video_input_uses_video_limits_and_demuxers_without_loosening_audio_defaults(self):
        for kind in ('audio','video'):
            with self.subTest(kind=kind),fake_decoder('import sys;sys.stdout.buffer.write(b"\\0"*64)',window_ms=1,input_kind=kind) as (stream,_,calls):
                with stream:list(stream)
                args=calls[0][0]
                self.assertEqual(args[args.index('-format_whitelist')+1],audio.VIDEO_FORMATS if kind=='video' else audio.FORMATS)
                self.assertEqual('-max_pixels' in args,kind=='video')
                self.assertEqual(args[args.index('-map')+1],'0:a:0')
        with patch.object(audio,'MAX_AUDIO_BYTES',1),fake_decoder('import sys;sys.stdout.buffer.write(b"\\0"*64)',window_ms=1) as (stream,children,_):
            with self.assertRaises(audio.AudioInputUnavailable):stream.__enter__()
            self.assertEqual(children,[])
        with patch.object(audio,'MAX_AUDIO_BYTES',1),fake_decoder('import sys;sys.stdout.buffer.write(b"\\0"*64)',window_ms=1,input_kind='video') as (stream,_,__):
            with stream:list(stream)
            self.assertTrue(stream.complete)

    def test_reader_start_failure_preserves_original_error_and_closes_stdout(self):
        with fake_decoder('import time;time.sleep(20)') as (stream,children,_):
            with patch.object(audio.threading.Thread,'start',side_effect=RuntimeError('generated reader start failure')):
                with self.assertRaisesRegex(RuntimeError,'generated reader start failure'):stream.__enter__()
            self.assertEqual(len(children),1);self.assertIsNotNone(children[0].poll())
            self.assertTrue(children[0].stdout.closed);self.assertFalse(stream.complete)

    def test_one_pass_fd_only_and_explicit_successful_eof(self):
        with patch.dict(os.environ,{'FFREPORT':'file=forbidden.log'}),fake_decoder('import sys;sys.stdout.buffer.write(b"\\0"*128)',window_ms=1) as (stream,processes,calls):
            with stream:
                self.assertFalse(stream.complete)
                a=next(stream);b=next(stream)
                self.assertEqual((a.start_ms,b.start_ms,a.frame_count,b.frame_count),(0,1,16,16))
                self.assertFalse(stream.complete)
                with self.assertRaises(StopIteration):next(stream)
                self.assertTrue(stream.complete)
            self.assertEqual(len(processes),1);self.assertEqual(processes[0].returncode,0)
            args,options=calls[0]
            self.assertEqual(args[args.index('-protocol_whitelist')+1],'fd,pipe')
            self.assertEqual(args[args.index('-i')+1],'fd:');self.assertEqual(args[-1],'pipe:1')
            self.assertNotIn('-ss',args);self.assertNotIn('-t',args);self.assertNotIn('FFREPORT',options['env'])
            self.assertIn('first_pts=0',args[args.index('-af')+1])
            self.assertFalse(stream.source.closed);self.assertFalse(stream.reader.is_alive())

    def test_nonzero_exit_after_valid_pcm_never_marks_complete(self):
        with fake_decoder('import sys;sys.stdout.buffer.write(b"\\0"*64);sys.stdout.flush();sys.exit(3)',window_ms=1) as (stream,_,__):
            with stream:
                self.assertEqual(next(stream).frame_count,16)
                with self.assertRaises(audio.AudioInputUnavailable):next(stream)
                self.assertFalse(stream.complete)

    def test_empty_nonfinite_and_misaligned_pcm_fail(self):
        for code in ('pass','import sys;sys.stdout.buffer.write(b"x")','import sys,struct;sys.stdout.buffer.write(struct.pack("<f",float("nan")))'):
            with self.subTest(code=code),fake_decoder(code) as (stream,_,__):
                with stream,self.assertRaises(audio.AudioInputUnavailable):list(stream)
                self.assertFalse(stream.complete)

    def test_full_output_limit_rejects_instead_of_truncating(self):
        with patch.object(audio,'MAX_START_MS',1000),fake_decoder('import sys;sys.stdout.buffer.write(b"\\0"*128000)',window_ms=1000) as (stream,_,__):
            with stream,self.assertRaises(audio.AudioInputUnavailable):list(stream)
            self.assertFalse(stream.complete)

    def test_backpressure_and_early_break_reap_owned_process(self):
        with fake_decoder('import sys;sys.stdout.buffer.write(b"\\0"*6400000)',window_ms=1000) as (stream,processes,_):
            with stream:
                self.assertEqual(next(stream).frame_count,16000)
                time.sleep(.1)
                self.assertLessEqual(stream.messages.qsize(),1)
                self.assertIsNone(processes[0].poll())
            self.assertIsNotNone(processes[0].poll());self.assertFalse(stream.reader.is_alive())
            self.assertFalse(stream.complete)

    def test_precancel_starts_no_child(self):
        cancel=threading.Event();cancel.set()
        with tempfile.TemporaryFile() as source,patch.object(audio.subprocess,'Popen') as launch:
            with self.assertRaises(audio.MediaDecodeCancelled):
                with audio.PCMStream(source,cancel=cancel):pass
            launch.assert_not_called()

    def test_closed_stream_cannot_reopen_or_report_completion(self):
        with fake_decoder('pass') as (stream,processes,_):
            stream.close()
            with self.assertRaises(audio.AudioInputUnavailable):stream.__enter__()
            with self.assertRaises(audio.AudioInputUnavailable):next(stream)
            self.assertFalse(processes);self.assertFalse(stream.complete)

    def test_session_deadline_is_separate_from_decoder_idle(self):
        with patch.object(audio,'SESSION_SECONDS',.1),fake_decoder('import time;time.sleep(20)') as (stream,processes,_):
            with stream,self.assertRaisesRegex(audio.AudioInputUnavailable,'session deadline'):next(stream)
            self.assertFalse(stream.complete);self.assertIsNotNone(processes[0].poll())

    def test_blocked_decode_cancellation_and_idle_timeout_reap_child(self):
        for cancellation in (True,False):
            event=threading.Event();timer=threading.Timer(.15,event.set)
            with self.subTest(cancel=cancellation),fake_decoder('import time;time.sleep(20)',cancel=event if cancellation else None) as (stream,processes,_):
                try:
                    with patch.object(audio,'IDLE_SECONDS',.25):
                        with stream:
                            if cancellation:timer.start()
                            with self.assertRaises(audio.MediaDecodeCancelled if cancellation else audio.AudioInputUnavailable):next(stream)
                    self.assertIsNotNone(processes[0].poll());self.assertFalse(stream.reader.is_alive())
                finally:
                    timer.cancel()
                    if timer.ident is not None:timer.join()

    def test_source_changes_and_guard_failure_discard_remaining_stream(self):
        with fake_decoder('import sys;sys.stdout.buffer.write(b"\\0"*128)',window_ms=1) as (stream,_,__):
            with stream:
                next(stream);stream.source.seek(0);stream.source.write(b'changed size');stream.source.truncate();stream.source.flush()
                with self.assertRaises(audio.AudioInputUnavailable):next(stream)
            self.assertFalse(stream.complete)
        failure=RuntimeError('generated registration was removed')
        def guard():
            if stream.frames:raise failure
        with fake_decoder('import sys;sys.stdout.buffer.write(b"\\0"*128)',window_ms=1,guard=guard) as (stream,_,__):
            with stream:
                next(stream)
                with self.assertRaisesRegex(RuntimeError,'registration was removed'):next(stream)
            self.assertFalse(stream.complete)

    @unittest.skipUnless(os.environ.get('AREDOKO_MEDIA_TOOLS') or shutil.which('ffmpeg'),'Existing FFmpeg required')
    def test_real_65_seconds_exact_boundaries_partial_tail_and_silence(self):
        for seconds in (60,65):
            with self.subTest(seconds=seconds),tempfile.TemporaryFile() as source:
                with wave.open(source,'wb') as generated:
                    generated.setnchannels(1);generated.setsampwidth(2);generated.setframerate(16000)
                    # First window silent, second nonzero; silence must not end
                    # the stream or become a made-up transcript.
                    generated.writeframes(b'\0'*30*16000*2)
                    generated.writeframes(struct.pack('<h',8192)*30*16000)
                    if seconds==65:generated.writeframes(struct.pack('<h',-8192)*5*16000)
                with audio.PCMStream(source) as stream:
                    windows=list(stream)
                    self.assertTrue(stream.complete)
                self.assertEqual([w.start_ms for w in windows],[0,30000] if seconds==60 else [0,30000,60000])
                self.assertEqual(sum(w.frame_count for w in windows),seconds*16000)
                self.assertTrue(windows[0].is_digital_silence)
                self.assertFalse(windows[1].is_digital_silence)
                if seconds==65:
                    self.assertEqual(windows[-1].frame_count,5*16000)
                    self.assertAlmostEqual(struct.unpack_from('<f',windows[-1].data)[0],-.25)

    @unittest.skipUnless(os.environ.get('AREDOKO_MEDIA_TOOLS') or shutil.which('ffmpeg'),'Existing FFmpeg required')
    def test_real_timestamp_gap_is_silence_not_eof_or_compressed_time(self):
        buffer=io.BytesIO()
        with wave.open(buffer,'wb') as generated:
            generated.setnchannels(1);generated.setsampwidth(2);generated.setframerate(16000)
            generated.writeframes(b''.join(struct.pack('<h',int(8000*math.sin(i*2*math.pi*440/16000))) for i in range(3*16000)))
        # Remove packets between seconds 1 and 2 while retaining timestamps.
        # Fragmented MP4 permits an in-memory generated container, not a path.
        encoded=subprocess.run([audio._executable('ffmpeg'),'-nostdin','-v','error','-f','wav','-i','pipe:0',
            '-af',"aselect=not(between(t\\,1\\,2))",'-c:a','aac','-movflags','frag_keyframe+empty_moov','-f','mp4','pipe:1'],
            input=buffer.getvalue(),capture_output=True,timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.assertEqual(encoded.returncode,0,encoded.stderr.decode(errors='replace'))
        with tempfile.TemporaryFile() as source:
            source.write(encoded.stdout);source.flush()
            with audio.PCMStream(source,window_ms=1000) as stream:windows=list(stream)
            values=[v[0] for w in windows for v in struct.iter_unpack('<f',w.data)]
            self.assertTrue(stream.complete);self.assertGreaterEqual(len(values),int(2.8*16000))
            def energy(start):return sum(x*x for x in values[int(start*16000):int((start+.1)*16000)])
            self.assertGreater(energy(.5),1);self.assertLess(energy(1.5),.001);self.assertGreater(energy(2.5),1)


if __name__=='__main__':unittest.main()
