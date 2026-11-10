"""No model/GPU: audio namespace isolation and bounded private worker input."""
import base64,contextlib,io,json,struct,sys,tempfile,types,unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from ai_profiles import DEFAULT_PROFILE,LEGACY_PROFILE,AUDIO_VECTOR_CONTRACT,ModelProfile,audio_profile_for
from audio_input import PCMWindow,AudioInputUnavailable
from audio_protocol import audio_request,parse_audio_request,MAX_BASE64_CHARS
from ai_adapters import load_adapter
from ai_process import EncoderProcess,AIUnavailable
import ai_worker


def window():return PCMWindow(250,1,struct.pack('<f',.25)*16)


class AudioWorkerTests(unittest.TestCase):
    def test_optional_gpu_budget_is_checked_before_model_allocation(self):
        cuda=types.SimpleNamespace(mem_get_info=MagicMock(return_value=(4*1024**3,8*1024**3)),
                                   set_per_process_memory_fraction=MagicMock())
        torch=types.SimpleNamespace(cuda=cuda)
        ai_worker.configure_gpu_budget(torch,'cuda',3072)
        cuda.set_per_process_memory_fraction.assert_called_once_with(.375)
        cuda.set_per_process_memory_fraction.reset_mock()
        cuda.mem_get_info.return_value=(2*1024**3,8*1024**3)
        with self.assertRaisesRegex(RuntimeError,'Insufficient'):ai_worker.configure_gpu_budget(torch,'cuda',3072)
        with self.assertRaisesRegex(RuntimeError,'requires CUDA'):ai_worker.configure_gpu_budget(torch,'cpu',3072)
        cuda.mem_get_info.reset_mock()
        ai_worker.configure_gpu_budget(torch,'cpu',4096,budget_if_cuda=True)
        cuda.mem_get_info.assert_not_called()
        for value in (True,0,65537):
            with self.assertRaises(ValueError):EncoderProcess('unused','unused',gpu_budget_mib=value)
        cuda.set_per_process_memory_fraction.assert_not_called()
        ai_worker.configure_gpu_budget(torch,'cpu',None)

    def test_budget_reaches_the_private_worker_and_audio_owner(self):
        from audio_direct_feature import AudioDirectFeature
        from inference_ownership import InferenceOwnership
        image=EncoderProcess('unused-python','unused-model',gpu_budget_mib=3072)
        group=InferenceOwnership();group.for_encoder(image)
        feature=AudioDirectFeature(None,types.SimpleNamespace(profile=image.profile,encoder=image,inference_group=group))
        self.assertEqual(feature.encoder.gpu_budget_mib,3072)
        self.assertIsNone(image.process);self.assertIsNone(feature.encoder.process)
        ready={'dimension':768,'profile':image.profile.key,'device':'cuda'}
        with patch.object(EncoderProcess,'available',new_callable=unittest.mock.PropertyMock,return_value=True),\
             patch('ai_process.worker_command',return_value=['generated-command']) as command,\
             patch('ai_process.subprocess.Popen') as launch,patch('ai_process.threading.Thread'),\
             patch.object(image,'_response',return_value=ready):
            image._start()
            self.assertEqual(command.call_args.args[2][-2:],['--gpu-budget-mib','3072'])
            self.assertEqual(launch.call_args.args[0],['generated-command'])
        # The observed process is a mock, not an owned operating system child.
        image.process=None;feature.close();image.close()

    def test_explicit_audio_profile_preserves_the_default_and_gets_its_own_contract(self):
        audio=audio_profile_for()
        self.assertEqual(DEFAULT_PROFILE.modalities,('text','cover'));self.assertEqual(DEFAULT_PROFILE.key,LEGACY_PROFILE)
        self.assertEqual(audio.modalities,('text','audio'));self.assertEqual(audio.vector_contract,AUDIO_VECTOR_CONTRACT)
        self.assertNotEqual(audio.key,DEFAULT_PROFILE.key);self.assertNotEqual(audio.store_path('catalog'),DEFAULT_PROFILE.store_path('catalog'))
        self.assertEqual(ModelProfile.from_dict(audio.to_dict()).key,audio.key)
        self.assertEqual(replace(audio,label='Cosmetic',directory='moved').key,audio.key)
        generic=replace(DEFAULT_PROFILE,adapter='sentence-transformers',modalities=('text',))
        with self.assertRaises(ValueError):audio_profile_for(generic)
        with self.assertRaises(ValueError):replace(generic,modalities=('text','audio'))

    def test_audio_contract_changes_do_not_change_a_legacy_key(self):
        original=audio_profile_for().key
        with patch('ai_profiles.AUDIO_VECTOR_CONTRACT','changed-preprocessing'):
            self.assertNotEqual(audio_profile_for().key,original);self.assertEqual(DEFAULT_PROFILE.key,LEGACY_PROFILE)

    def test_pcm_roundtrip_has_no_path_and_no_implicit_rate(self):
        message=audio_request(window());self.assertEqual(parse_audio_request(message),window())
        self.assertNotIn('path',message);self.assertLess(len(json.dumps(message)),MAX_BASE64_CHARS+1000)

    def test_malformed_wire_values_and_unknown_fields_are_rejected(self):
        original=audio_request(window())
        variants=[{**original,'path':'must-not-open'},{k:v for k,v in original.items() if k!='sample_rate'},
                  {**original,'sample_rate':True},{**original,'sample_rate':44100},{**original,'channels':2},
                  {**original,'sample_format':'s16le'},{**original,'duration_ms':True},{**original,'start_ms':-1},
                  {**original,'audio':'not base64!'},{**original,'audio':'あ'},
                  {**original,'audio':'A'*(MAX_BASE64_CHARS+4)},
                  {**original,'audio':base64.b64encode(struct.pack('<f',float('nan'))).decode()}]
        for value in variants:
            with self.subTest(keys=list(value)),self.assertRaises(ValueError):parse_audio_request(value)

    def test_untrusted_pcm_is_rejected_before_starting_a_worker(self):
        encoder=EncoderProcess('unused-python','unused-model',audio_profile_for())
        with patch.object(encoder,'_start') as start:
            for value in [b'raw',replace(window(),data=bytearray(b'\0'*64)),replace(window(),sample_rate=True),replace(window(),data=b'')]:
                with self.assertRaises(AudioInputUnavailable):encoder.encode('audio',value)
            start.assert_not_called()
        encoder=EncoderProcess('unused-python','unused-model')
        with patch.object(encoder,'_start') as start:
            with self.assertRaises(AIUnavailable):encoder.encode('audio',window())
            start.assert_not_called()

    def test_parent_writes_a_bounded_typed_message_and_normalizes_output(self):
        encoder=EncoderProcess('unused-python','unused-model',audio_profile_for())
        encoder.process=types.SimpleNamespace(stdin=io.StringIO())
        with patch.object(encoder,'_start'),patch.object(encoder,'_response',return_value={'vector':[2.]+[0.]*767,'elapsed_ms':4}):
            vector=encoder.encode('audio',window())
        self.assertEqual(parse_audio_request(json.loads(encoder.process.stdin.getvalue())),window())
        self.assertEqual(vector,[1.]+[0.]*767);self.assertEqual(encoder.telemetry,{'elapsed_ms':4})

    def test_exact_positive_and_negative_zero_skip_before_model_start_but_quiet_sound_does_not(self):
        encoder=EncoderProcess('unused-python','unused-model',audio_profile_for());encoder.telemetry={'old':True}
        with patch.object(encoder,'_start') as start:
            for value in (0.,-0.):self.assertIsNone(encoder.encode('audio',replace(window(),data=struct.pack('<f',value)*16)))
            start.assert_not_called();self.assertEqual(encoder.telemetry,{})
            encoder._closed=True
            with self.assertRaises(AIUnavailable):encoder.encode('audio',replace(window(),data=b'\0'*64))
        encoder=EncoderProcess('unused-python','unused-model',audio_profile_for());encoder.process=types.SimpleNamespace(stdin=io.StringIO())
        with patch.object(encoder,'_start') as start,patch.object(encoder,'_response',return_value={'vector':[1.]+[0.]*767}):
            self.assertIsNotNone(encoder.encode('audio',replace(window(),data=struct.pack('<f',1e-12)*16)));start.assert_called_once()

    def test_unknown_audio_skip_reason_does_not_masquerade_as_silence(self):
        encoder=EncoderProcess('unused-python','unused-model',audio_profile_for());encoder.process=types.SimpleNamespace(stdin=io.StringIO())
        with patch.object(encoder,'_start'),patch.object(encoder,'_response',return_value={'skip':True,'reason':'unknown'}):
            with self.assertRaisesRegex(AIUnavailable,'Missing embedding'):encoder.encode('audio',window())

    def test_audio_adapter_enables_only_the_explicit_tower_and_passes_arrays(self):
        model=MagicMock();model.get_embedding_dimension.return_value=768;constructor=MagicMock(return_value=model)
        fake_numpy=types.SimpleNamespace(frombuffer=MagicMock(return_value='generated-array'))
        with patch.dict(sys.modules,{'sentence_transformers':types.SimpleNamespace(SentenceTransformer=constructor),'numpy':fake_numpy}):
            adapter=load_adapter(audio_profile_for(),'local-model','cpu','float32')
            self.assertEqual(constructor.call_args.kwargs['config_kwargs'],{'vision_config':None})
            adapter.encode_audio(window())
            fake_numpy.frombuffer.assert_called_once_with(window().data,dtype='<f4')
            self.assertEqual(model.encode.call_args.args[0],{'audio':{'array':'generated-array','sampling_rate':16000}})
            with self.assertRaises(ValueError):adapter.encode_image(object())
            default=load_adapter(DEFAULT_PROFILE,'local-model','cpu','float32')
            self.assertEqual(constructor.call_args.kwargs['config_kwargs'],{'audio_config':None})
            with self.assertRaises(ValueError):default.encode_audio(window())

    def run_worker(self,stream):
        profile=audio_profile_for();output=io.StringIO();fake_vector=types.SimpleNamespace(tolist=lambda:[1.]+[0.]*767)
        model=types.SimpleNamespace(dimension=768,encode_audio=MagicMock(return_value=fake_vector))
        torch=types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda:False),float32='fake-float32',inference_mode=contextlib.nullcontext)
        with patch.dict('os.environ'),patch.dict(sys.modules,{'torch':torch}),patch('ai_adapters.load_adapter',return_value=model),patch('ai_worker.threading.Thread'),\
             patch.object(sys,'argv',['ai_worker','--model','unused','--profile-json',json.dumps(profile.to_dict())]),\
             patch.object(sys,'stdin',stream),patch.object(sys,'stdout',output),patch.object(sys,'stderr',io.StringIO()):
            ai_worker.main()
        return [json.loads(line) for line in output.getvalue().splitlines()],model

    def test_worker_rejects_bad_audio_then_accepts_next_message_without_gpu(self):
        valid=audio_request(window());invalid={**valid,'channels':True}
        silent=audio_request(replace(window(),data=b'\0'*64))
        rows,model=self.run_worker(io.StringIO(json.dumps(invalid)+'\n'+json.dumps(silent)+'\n'+json.dumps(valid)+'\n'))
        self.assertEqual(rows[0]['profile'],audio_profile_for().key);self.assertIn('error',rows[1]);self.assertEqual(rows[2],{'skip':True,'reason':'digital_silence'});self.assertEqual(len(rows[3]['vector']),768)
        model.encode_audio.assert_called_once_with(window())

    def test_worker_rejects_oversized_lines_without_parsing_partial_messages(self):
        class TooLarge:
            requested=None
            def readline(self,size):self.requested=size;return 'x'*size
        stream=TooLarge();rows,model=self.run_worker(stream)
        self.assertEqual(stream.requested,12*1024*1024+1);self.assertEqual(rows[1],{'error':'SourceLimit'});model.encode_audio.assert_not_called()

    def test_real_private_pipe_carries_maximum_pcm_with_an_owned_cpu_fixture(self):
        # Real process/pipe/backpressure, but a fake torch/model inside that
        # process. No selected runtime, weights, CUDA or external code executes.
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'aredoko-revision.txt').write_text(DEFAULT_PROFILE.revision)
            shim=root/'owned_worker.py'
            shim.write_text('import sys,types,contextlib\nsys.path.insert(0,'+repr(str(Path(__file__).resolve().parents[1]/'app'))+')\n'+'''
sys.modules['torch']=types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda:False),float32='fake',inference_mode=contextlib.nullcontext)
import ai_adapters
class Model:
    dimension=768
    def encode_audio(self,window):
        assert window.frame_count==480000
        return types.SimpleNamespace(tolist=lambda:[1.]+[0.]*767)
ai_adapters.load_adapter=lambda *args:Model()
import ai_worker
ai_worker.main()
''',encoding='utf-8')
            encoder=EncoderProcess(sys.executable,root,audio_profile_for());worker=None
            response=encoder._response
            def command(python,script,arguments,**kwargs):return [sys.executable,'-X','utf8','-B',str(shim),*arguments]
            try:
                with patch('ai_process.worker_command',side_effect=command),patch.object(encoder,'_response',side_effect=lambda:response(timeout=10)):
                    result=encoder.encode('audio',PCMWindow(0,30000,struct.pack('<f',.25)*480000));worker=encoder.process
                self.assertEqual(result,[1.]+[0.]*767);self.assertEqual(encoder.device,'cpu');self.assertTrue(encoder.resident)
            finally:encoder.close()
            if worker is not None:self.assertIsNotNone(worker.poll())


if __name__=='__main__':unittest.main()
