"""Generated PCM only: finite windows, fd-only decode and cancellation/scope."""
import io,json,os,shutil,struct,subprocess,sys,tempfile,threading,time,unittest,wave
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import audio_input as audio
import video_previews as native
from production import ProductionCatalog
from previews import PreviewReader,PreviewUnavailable,ReaderChanged


def wav_bytes():
    stream=io.BytesIO()
    with wave.open(stream,'wb') as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(16000)
        output.writeframes(struct.pack('<h',8192)*16000+struct.pack('<h',-16384)*16000)
    return stream.getvalue()


class AudioWindowTests(unittest.TestCase):
    def test_interval_is_strict_and_bounded(self):
        for pair in [(True,100),(0,True),(-1,10),(0,0),(0,30001),(86400000,1),(0,1.5),('0',100)]:
            with self.subTest(pair=pair),self.assertRaises(audio.AudioInputUnavailable):audio.validate_window(*pair)
        audio.validate_window(86400000-30000,30000)

    def test_only_open_handle_and_bounded_pcm_arguments_are_used(self):
        with patch.object(audio,'_executable',return_value='ffmpeg'),patch.object(audio,'_run',return_value=struct.pack('<ff',.25,-.5)) as run:
            source=io.BytesIO(b'generated');result=audio.read_window(source,1000,100)
        self.assertEqual((result.start_ms,result.requested_duration_ms,result.frame_count,result.sample_rate,result.channels,result.sample_format),(1000,100,2,16000,1,'f32le'))
        arguments,passed,limit,_=run.call_args.args
        self.assertIs(passed,source);self.assertEqual(limit,6400)
        self.assertEqual(arguments[arguments.index('-i')+1],'fd:')
        self.assertEqual(arguments[arguments.index('-protocol_whitelist')+1],'fd,pipe')
        self.assertEqual(arguments[-1],'pipe:1');self.assertNotIn('concat',arguments[arguments.index('-format_whitelist')+1])
        self.assertNotIn('file',arguments[arguments.index('-protocol_whitelist')+1]);self.assertIn('-nostdin',arguments)

    def test_empty_misaligned_nonfinite_and_excess_output_are_rejected(self):
        for data in [b'',b'x',struct.pack('<f',float('nan')),struct.pack('<f',float('inf')),b'\0'*68]:
            with self.subTest(length=len(data)),patch.object(audio,'_executable',return_value='unused'),patch.object(audio,'_run',return_value=data):
                with self.assertRaises(audio.AudioInputUnavailable):audio.read_window(io.BytesIO(),0,1)

    def test_silence_is_not_replaced_with_transcript_or_descriptors(self):
        with patch.object(audio,'_executable',return_value='unused'),patch.object(audio,'_run',return_value=b'\0'*64):
            window=audio.read_window(io.BytesIO(),0,1)
        self.assertEqual(window.data,b'\0'*64);self.assertFalse(hasattr(window,'transcript'))

    def test_precancel_starts_no_native_process(self):
        cancel=threading.Event();cancel.set()
        with patch.object(audio,'_executable') as executable:
            with self.assertRaises(audio.MediaDecodeCancelled):audio.read_window(io.BytesIO(),0,100,cancel)
            executable.assert_not_called()

    def test_running_native_process_is_cancelled_and_reaped(self):
        cancel=threading.Event();timer=threading.Timer(.15,cancel.set);processes=[];original=subprocess.Popen
        def start(*args,**kwargs):
            value=original(*args,**kwargs);processes.append(value);timer.start();return value
        try:
            began=time.monotonic()
            with tempfile.TemporaryFile() as source,patch.object(native.subprocess,'Popen',side_effect=start):
                with self.assertRaises(audio.MediaDecodeCancelled):
                    native._run([sys.executable,'-c','import time;time.sleep(20)'],source,64,time.monotonic()+10,cancel)
            self.assertLess(time.monotonic()-began,3);self.assertEqual(len(processes),1);self.assertIsNotNone(processes[0].poll())
        finally:
            timer.cancel()
            if timer.ident is not None:timer.join()

    def test_deadline_also_reaps_a_cancellable_child(self):
        with tempfile.TemporaryFile() as source:
            with self.assertRaisesRegex(native.VideoPreviewUnavailable,'deadline'):
                native._run([sys.executable,'-c','import time;time.sleep(20)'],source,64,time.monotonic()+.1,threading.Event())

    @unittest.skipUnless(os.environ.get('AREDOKO_MEDIA_TOOLS') or shutil.which('ffmpeg'),'Existing FFmpeg required; no download')
    def test_real_generated_wav_window_has_correct_time_rate_and_tail(self):
        with tempfile.TemporaryFile() as source:
            source.write(wav_bytes());source.flush()
            window=audio.read_window(source,500,750)
            self.assertEqual(window.frame_count,12000)
            values=[value[0] for value in struct.iter_unpack('<f',window.data)]
            self.assertAlmostEqual(values[100],.25,places=5);self.assertAlmostEqual(values[-100],-.5,places=5)
            tail=audio.read_window(source,1750,1000);self.assertEqual(tail.frame_count,4000)
            with self.assertRaises(audio.AudioInputUnavailable):audio.read_window(source,3000,100)


class AudioSourceBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);base=Path(temporary.name)
        media=base/'media';media.mkdir();self.path=media/'generated ; $(no-command).wav';self.path.write_bytes(wav_bytes())
        self.catalog=ProductionCatalog(base/'catalog.sqlite');self.addCleanup(self.catalog.close)
        self.root=self.catalog.add_root(str(media));self.catalog.index.scan(self.root);self.catalog.sync_index()
        self.item=self.catalog.search()['items'][0]['id'];self.reader=PreviewReader(self.catalog)
        self.revision=self.reader.audio_manifest(self.item)['revision']
        self.window=audio.PCMWindow(0,1,b'\0'*64)

    def read(self,cancel=None):return self.reader.audio_pcm_window(self.item,0,1,self.revision,cancel)

    def test_current_input_publishes_identity_and_releases_preview_slot(self):
        with patch.object(audio,'read_window',return_value=self.window) as decode:
            result=self.read();self.assertEqual(result,{'item_id':self.item,'revision':self.revision,'window':self.window})
            self.assertTrue(decode.call_args.args[0].closed)
            self.read()

    def test_stale_revision_and_unregistered_root_never_decode(self):
        with patch.object(audio,'read_window') as decode:
            with self.assertRaises(ReaderChanged):self.reader.audio_pcm_window(self.item,0,1,'0'*64)
            self.catalog.unregister_root(self.root)
            with self.assertRaises(PreviewUnavailable):self.read()
            decode.assert_not_called()

    def test_mid_decode_file_change_discards_pcm(self):
        def changed(*args,**kwargs):self.path.write_bytes(b'changed');return self.window
        with patch.object(audio,'read_window',side_effect=changed):
            with self.assertRaises(ReaderChanged):self.read()

    def test_mid_decode_unregister_and_exclusion_discard_pcm(self):
        def excluded(*args,**kwargs):self.catalog.set_excludes(self.root,['*.wav']);return self.window
        with patch.object(audio,'read_window',side_effect=excluded):
            with self.assertRaises(ReaderChanged):self.read()
        self.catalog.set_excludes(self.root,[])
        def removed(*args,**kwargs):self.catalog.unregister_root(self.root);return self.window
        with patch.object(audio,'read_window',side_effect=removed):
            with self.assertRaises(ReaderChanged):self.read()

    def test_late_cancel_discards_output_and_returns_worker_slot(self):
        cancel=threading.Event()
        def cancelled(*args,**kwargs):cancel.set();return self.window
        with patch.object(audio,'read_window',side_effect=cancelled):
            with self.assertRaises(audio.MediaDecodeCancelled):self.read(cancel)
        with patch.object(audio,'read_window',return_value=self.window):self.read()

    def test_precancel_does_not_enter_source_lookup(self):
        cancel=threading.Event();cancel.set()
        with patch.object(self.reader,'_read') as read:
            with self.assertRaises(audio.MediaDecodeCancelled):self.read(cancel)
            read.assert_not_called()


if __name__=='__main__':unittest.main()
