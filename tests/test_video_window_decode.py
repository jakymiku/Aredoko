"""One generated short MP4 and bounded mocked failure cases. No GPU/models."""
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from video_window_decode import read_video_window,VideoWindowUnavailable
from video_input import MAX_EDGE
from video_previews import _executable,MediaDecodeCancelled


class VideoWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory();cls.path=Path(cls.temporary.name)/'generated.mp4'
        scene='color=c=red:s=160x90:r=10:d=1[first];color=c=blue:s=160x90:r=10:d=2.3[second];[first][second]concat=n=2:v=1:a=0'
        try:subprocess.run([_executable('ffmpeg'),'-nostdin','-v','error','-f','lavfi','-i',scene,
                            '-an','-r','10','-c:v','mpeg4','-threads','1','-movflags','+faststart',str(cls.path)],check=True,timeout=15,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except BaseException:cls.temporary.cleanup();raise

    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()

    def test_real_handle_decode_has_1fps_and_preserves_the_planned_partial_tail(self):
        guards=[]
        with self.path.open('rb') as source:
            clip=read_video_window(source,0,3300,total_duration_ms=3300,guard=lambda:guards.append(True))
            self.assertFalse(source.closed)
        self.assertEqual((clip.start_ms,clip.end_ms,len(clip.frames)),(0,3300,4))
        self.assertEqual(len(guards),2)
        frame=clip.frames[0];middle=(192*384+192)*3
        self.assertGreater(frame[middle],200);self.assertLess(frame[middle+1],20)
        self.assertEqual(frame[:3],b'\0\0\0')  # Letterbox, not stretched widescreen.

    def test_later_interval_uses_the_requested_start(self):
        with self.path.open('rb') as source:clip=read_video_window(source,1000,2000,total_duration_ms=3300)
        self.assertEqual((clip.start_ms,clip.end_ms,len(clip.frames)),(1000,3000,2))
        middle=(192*384+192)*3
        self.assertGreater(clip.frames[0][middle+2],200);self.assertLess(clip.frames[0][middle],20)

    def test_short_decode_is_not_silently_promoted_to_success(self):
        with self.path.open('rb') as source,self.assertRaises(VideoWindowUnavailable):read_video_window(source,0,10000,total_duration_ms=10000)

    def test_malformed_time_and_cancel_do_not_spawn_decoder(self):
        stop=threading.Event();stop.set()
        with patch('video_window_decode._run') as run:
            with self.assertRaises(MediaDecodeCancelled):read_video_window(None,0,1000,total_duration_ms=3300,cancel=stop)
            for start,duration in ((True,1000),(0,True),(-1,1000),(0,16001),(86400000,1)):
                with self.assertRaises(ValueError):read_video_window(None,start,duration,total_duration_ms=3300)
            with self.assertRaises(ValueError):read_video_window(None,0,4000,total_duration_ms=3300)
            run.assert_not_called()

    def test_guard_change_and_bad_raw_alignment_discard_output(self):
        with patch('video_window_decode._executable',return_value='generated-decoder'),patch('video_window_decode._run',return_value=b'bad'):
            with self.assertRaises(VideoWindowUnavailable):read_video_window(None,0,1000,total_duration_ms=3300)
        count=0
        def changed():
            nonlocal count
            count+=1
            if count==2:raise RuntimeError('Generated source changed')
        with patch('video_window_decode._executable',return_value='generated-decoder'),patch('video_window_decode._run',return_value=b'\0'*(MAX_EDGE*MAX_EDGE*3)):
            with self.assertRaisesRegex(RuntimeError,'source changed'):read_video_window(None,0,1000,total_duration_ms=3300,guard=changed)

    def test_decoder_command_never_carries_a_filename_or_network_protocol(self):
        with patch('video_window_decode._executable',return_value='generated-decoder'),patch('video_window_decode._run',return_value=b'\0'*(MAX_EDGE*MAX_EDGE*3)) as run:
            read_video_window(None,0,1000,total_duration_ms=3300)
        command=run.call_args.args[0]
        self.assertEqual(command[command.index('-i')+1],'fd:')
        self.assertEqual(command[command.index('-protocol_whitelist')+1],'fd,pipe')
        self.assertIn('-frames:v',command);self.assertEqual(run.call_args.args[2],MAX_EDGE*MAX_EDGE*3)


if __name__=='__main__':unittest.main()
