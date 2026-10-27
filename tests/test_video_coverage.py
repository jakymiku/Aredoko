"""Duration probe, coverage plan and full-interval decode. Generated MP4s only."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_video_window_decode as fixture
from video_coverage import probe_video_duration_ms,plan_video_coverage,read_video_coverage,VideoCoverageUnavailable
from video_input import VideoWindow
from video_previews import _executable,VideoPreviewUnavailable,MediaDecodeCancelled
from video_window_decode import VideoWindowUnavailable


def probe_json(stream=None,format_duration=None):
    document={'streams':[{} if stream is None else {'duration':stream}]}
    if format_duration is not None:document['format']={'duration':format_duration}
    return json.dumps(document).encode()


class ProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.VideoWindowTests.setUpClass()
    @classmethod
    def tearDownClass(cls):fixture.VideoWindowTests.tearDownClass()

    def test_real_handle_probe_reports_the_container_duration(self):
        with fixture.VideoWindowTests.path.open('rb') as source:
            self.assertEqual(probe_video_duration_ms(source),3300)
            self.assertFalse(source.closed)

    def test_stream_duration_wins_and_format_duration_is_the_only_fallback(self):
        with patch('video_coverage._run',return_value=probe_json('2.5','9.5')) as run:
            self.assertEqual(probe_video_duration_ms(None),2500)
        with patch('video_coverage._run',return_value=probe_json(None,'2.5')):
            self.assertEqual(probe_video_duration_ms(None),2500)
        command=run.call_args.args[0]
        self.assertEqual(command[command.index('-i')+1],'fd:')
        self.assertEqual(command[command.index('-protocol_whitelist')+1],'fd,pipe')
        self.assertNotIn(str(fixture.VideoWindowTests.path),command)

    def test_unknown_or_implausible_duration_is_never_guessed(self):
        bad=[probe_json(None),probe_json('N/A'),probe_json('0'),probe_json('-3'),
             probe_json('86400.001'),b'not json',json.dumps({'streams':[]}).encode(),
             json.dumps({'streams':[{'duration':'1'},{'duration':'2'}]}).encode()]
        for payload in bad:
            with patch('video_coverage._run',return_value=payload),self.assertRaises(VideoCoverageUnavailable):
                probe_video_duration_ms(None)
        with patch('video_coverage._run',side_effect=VideoPreviewUnavailable('no probe')):
            with self.assertRaises(VideoCoverageUnavailable):probe_video_duration_ms(None)

    def test_cancel_and_guard_change_do_not_publish_a_duration(self):
        stop=threading.Event();stop.set()
        with patch('video_coverage._run') as run:
            with self.assertRaises(MediaDecodeCancelled):probe_video_duration_ms(None,cancel=stop)
            run.assert_not_called()
        count=0
        def changed():
            nonlocal count
            count+=1
            if count==2:raise RuntimeError('Generated source changed')
        with patch('video_coverage._run',return_value=probe_json('3.3')):
            with self.assertRaisesRegex(RuntimeError,'source changed'):probe_video_duration_ms(None,guard=changed)


class PlanTests(unittest.TestCase):
    def test_windows_are_contiguous_bounded_and_cover_the_tail(self):
        self.assertEqual(plan_video_coverage(1),((0,1),))
        self.assertEqual(plan_video_coverage(3300),((0,3300),))
        self.assertEqual(plan_video_coverage(16000),((0,16000),))
        self.assertEqual(plan_video_coverage(16001),((0,16000),(16000,1)))
        self.assertEqual(plan_video_coverage(40000),((0,16000),(16000,16000),(32000,8000)))
        plan=plan_video_coverage(86400000)
        self.assertEqual((len(plan),plan[-1]),(5400,(86384000,16000)))

    def test_plan_rejects_anything_but_a_known_int_duration(self):
        for value in (0,-1,True,1.5,'3300',None,86400001):
            with self.assertRaises(ValueError):plan_video_coverage(value)


class CoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.VideoWindowTests.setUpClass()
        cls.temporary=tempfile.TemporaryDirectory();cls.long_path=Path(cls.temporary.name)/'generated-long.mp4'
        try:subprocess.run([_executable('ffmpeg'),'-nostdin','-v','error','-f','lavfi','-i',
                            'color=c=green:s=160x90:r=10:d=17.5','-an','-r','10','-c:v','mpeg4','-threads','1',
                            '-movflags','+faststart',str(cls.long_path)],check=True,timeout=15,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except BaseException:cls.temporary.cleanup();raise

    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup();fixture.VideoWindowTests.tearDownClass()

    def test_short_video_decodes_as_one_window_with_guards(self):
        guards=[]
        with fixture.VideoWindowTests.path.open('rb') as source:
            windows=read_video_coverage(source,guard=lambda:guards.append(True))
        self.assertEqual(len(windows),1)
        self.assertEqual((windows[0].start_ms,windows[0].end_ms,len(windows[0].frames)),(0,3300,4))
        self.assertEqual(len(guards),4)  # Probe before/after plus decode before/after.

    def test_long_video_decodes_every_planned_window_in_order(self):
        with self.long_path.open('rb') as source:windows=read_video_coverage(source)
        self.assertEqual([(w.start_ms,w.end_ms,len(w.frames)) for w in windows],
                         [(0,16000,16),(16000,17500,2)])

    def test_any_failed_window_discards_the_whole_coverage(self):
        window=VideoWindow(0,16000,1,1,tuple(b'\0'*3 for _ in range(16)))
        with patch('video_coverage.probe_video_duration_ms',return_value=17500),\
             patch('video_coverage.read_video_window',side_effect=[window,VideoWindowUnavailable('failed')]) as decode:
            with self.assertRaises(VideoWindowUnavailable):read_video_coverage(None)
        self.assertEqual(decode.call_count,2)

    def test_probe_failure_never_reaches_the_decoder(self):
        with patch('video_coverage._run',side_effect=VideoPreviewUnavailable('no probe')),\
             patch('video_coverage.read_video_window') as decode:
            with self.assertRaises(VideoCoverageUnavailable):read_video_coverage(None)
            decode.assert_not_called()


if __name__=='__main__':unittest.main()
