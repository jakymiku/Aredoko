"""Native-video private contract, supplied RGB frames; no model or GPU."""
import contextlib
from dataclasses import replace
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from ai_profiles import DEFAULT_PROFILE,LEGACY_PROFILE,video_profile_for,audio_profile_for,ModelProfile,VIDEO_VECTOR_CONTRACT
from video_input import VideoWindow,validate_video,MAX_FRAMES,MAX_EDGE
from video_protocol import video_request,parse_video_request
from ai_process import EncoderProcess,AIUnavailable
from ai_adapters import load_adapter
import ai_worker


def clip():return VideoWindow(12000,15000,2,1,(b'\xff\0\0'*2,b'\0\xff\0'*2,b'\0\0\xff'*2))


class VideoWorkerTests(unittest.TestCase):
    def test_native_video_has_a_separate_contract_and_preserves_old_namespaces(self):
        profile=video_profile_for()
        self.assertEqual(DEFAULT_PROFILE.key,LEGACY_PROFILE)
        self.assertEqual(profile.modalities,('text','video'));self.assertEqual(profile.vector_contract,VIDEO_VECTOR_CONTRACT)
        self.assertEqual(ModelProfile.from_dict(profile.to_dict()).key,profile.key)
        self.assertEqual(len({profile.key,DEFAULT_PROFILE.key,audio_profile_for().key}),3)
        self.assertNotEqual(profile.store_path('catalog'),DEFAULT_PROFILE.store_path('catalog'))
        self.assertEqual(replace(profile,label='Other',directory='moved').key,profile.key)
        with self.assertRaises(ValueError):replace(profile,adapter='sentence-transformers')

    def test_rgb_times_roundtrip_and_max_payload_fits_existing_private_line_limit(self):
        self.assertEqual(parse_video_request(video_request(clip())),clip())
        maximum=VideoWindow(0,16000,MAX_EDGE,MAX_EDGE,(b'\0'*(MAX_EDGE*MAX_EDGE*3),)*MAX_FRAMES)
        message=video_request(maximum)
        self.assertLess(len(json.dumps(message)),12*1024*1024)
        self.assertEqual(len(parse_video_request(message).frames),16)

    def test_malformed_messages_do_not_get_to_model_input(self):
        original=video_request(clip())
        for bad in ({**original,'path':'must-not-read.mp4'},{**original,'url':'https://must-not-fetch'},
                    {**original,'start_ms':True},{**original,'end_ms':12001},{**original,'width':True},
                    {**original,'width':385},{**original,'frames':original['frames']*6},
                    {**original,'frames':['bad']*3},{**original,'frames':['!!!!!!!!']*3},
                    {**original,'end_ms':86400001}):
            with self.subTest(keys=list(bad)),self.assertRaises(ValueError):parse_video_request(bad)
        for bad in (replace(clip(),frames=list(clip().frames)),replace(clip(),frames=(bytearray(b'\0'*6),)*3),
                    replace(clip(),height=0),replace(clip(),start_ms=-1),replace(clip(),end_ms=16000)):
            with self.assertRaises(ValueError):validate_video(bad)

    def test_untrusted_size_is_rejected_before_base64_allocation(self):
        message={**video_request(clip()),'frames':['A'*1000000]*3}
        with patch('video_protocol.base64.b64decode') as decode,self.assertRaises(ValueError):parse_video_request(message)
        decode.assert_not_called()

    def test_parent_rejects_bad_input_and_legacy_profile_before_launch(self):
        encoder=EncoderProcess('unused','unused',video_profile_for())
        with patch.object(encoder,'_start') as start:
            with self.assertRaises(ValueError):encoder.encode('video','must-not-open.mp4')
            start.assert_not_called()
        encoder=EncoderProcess('unused','unused')
        with patch.object(encoder,'_start') as start:
            with self.assertRaises(AIUnavailable):encoder.encode('video',clip())
            start.assert_not_called()

    def test_parent_sends_only_pixels_and_preserves_normalized_response(self):
        encoder=EncoderProcess('unused','unused',video_profile_for());encoder.process=types.SimpleNamespace(stdin=io.StringIO())
        with patch.object(encoder,'_start'),patch.object(encoder,'_response',return_value={'vector':[2.]+[0.]*767}):
            result=encoder.encode('video',clip())
        request=json.loads(encoder.process.stdin.getvalue())
        self.assertEqual(parse_video_request(request),clip());self.assertNotIn('text',request)
        self.assertEqual(result,[1.]+[0.]*767)

    def test_adapter_batches_frames_as_one_video_and_disables_resampling(self):
        model=MagicMock();model.get_embedding_dimension.return_value=768
        constructor=MagicMock(return_value=model);captured=[]
        def encoded(value,**kwargs):
            frames=value['video'];captured.extend(frames)
            self.assertEqual([frame.getpixel((0,0)) for frame in frames],[(255,0,0),(0,255,0),(0,0,255)])
            self.assertEqual(kwargs['processing_kwargs']['video'],{'do_sample_frames':False,'max_frames':16,'max_soft_tokens':140,'add_timestamps':False})
            return 'generated-vector'
        model.encode.side_effect=encoded
        with patch.dict(sys.modules,{'sentence_transformers':types.SimpleNamespace(SentenceTransformer=constructor)}):
            adapter=load_adapter(video_profile_for(),'unused','cpu','float32')
            self.assertEqual(constructor.call_args.kwargs['config_kwargs'],{'audio_config':None})
            self.assertEqual(adapter.encode_video(clip()),'generated-vector')
            for image in captured:
                with self.assertRaises(ValueError):image.getpixel((0,0))
            with self.assertRaises(ValueError):adapter.encode_image(object())

    def run_worker(self,requests,profile=None):
        profile=profile or video_profile_for();output=io.StringIO()
        model=types.SimpleNamespace(dimension=768,encode_video=MagicMock(return_value=types.SimpleNamespace(tolist=lambda:[1.]+[0.]*767)))
        torch=types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda:False),float32='float32',inference_mode=contextlib.nullcontext)
        stream=io.StringIO(''.join(json.dumps(row)+'\n' for row in requests))
        with patch.dict(sys.modules,{'torch':torch}),patch('ai_adapters.load_adapter',return_value=model),patch('ai_worker.threading.Thread'),\
             patch.object(sys,'argv',['worker','--model','unused','--profile-json',json.dumps(profile.to_dict())]),\
             patch.object(sys,'stdin',stream),patch.object(sys,'stdout',output),patch.object(sys,'stderr',io.StringIO()):ai_worker.main()
        return [json.loads(line) for line in output.getvalue().splitlines()],model

    def test_worker_validates_each_message_and_black_video_does_not_become_silence(self):
        message=video_request(replace(clip(),frames=(b'\0'*6,)*3))
        replies,model=self.run_worker([{**message,'path':'forbidden'},message])
        self.assertEqual(replies[1],{'error':'ValueError'});self.assertEqual(len(replies[2]['vector']),768)
        model.encode_video.assert_called_once()
        self.assertEqual(model.encode_video.call_args.args[0].frames,(b'\0'*6,)*3)

    def test_worker_rejects_video_on_legacy_image_profile(self):
        replies,model=self.run_worker([video_request(clip())],DEFAULT_PROFILE)
        self.assertEqual(replies[1],{'error':'ValueError'});model.encode_video.assert_not_called()


if __name__=='__main__':unittest.main()
