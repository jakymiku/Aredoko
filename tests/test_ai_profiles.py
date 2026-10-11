"""Model changes must never reinterpret an existing vector space."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from ai_profiles import DEFAULT_PROFILE, ModelProfile, load_profile, LEGACY_PROFILE
from ai_search import AISearch, VectorStore, revision
from ai_process import EncoderProcess, AIUnavailable
from production import ProductionCatalog
from production_server import create_ai
from ai_adapters import load_adapter

class ProfilesTests(unittest.TestCase):
    def test_existing_default_and_cosmetic_changes_reuse_legacy_index(self):
        p=DEFAULT_PROFILE
        self.assertEqual(p.key,LEGACY_PROFILE)
        self.assertEqual(str(p.store_path('catalog')), 'catalog.ai.sqlite')
        self.assertEqual(replace(p,label='Display label',directory='relocated').key,p.key)
        self.assertEqual(ModelProfile.from_dict(p.to_dict()).key,p.key)

    def test_every_vector_space_change_gets_a_separate_index(self):
        p=DEFAULT_PROFILE
        variants=[replace(p,model_id='test/other'),replace(p,revision='a'*40),
                  replace(p,dimension=384),replace(p,modalities=('text',)),
                  replace(p,query_prompt_name='Other'),replace(p,document_prompt_name=None,document_prefix='passage: '),
                  replace(p,precision='float32'),
                  replace(p,adapter='sentence-transformers',modalities=('text',))]
        self.assertEqual(len({v.store_path('catalog') for v in variants}),len(variants))
        self.assertTrue(all(v.key!=p.key for v in variants))

    def test_bad_config_is_rejected_and_literal_catalog_still_opens(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'profile.json'
            bad=[{'trust_remote_code':True},{'dimension':True},{'dimension':0},{'dimension':5000},
                 {'revision':'main'},{'directory':'../private'},{'directory':'C:/private'},
                 {'directory':'x\\private'},{'adapter':'custom.py'},{'query_prefix':'query: '},
                 {'modalities':['cover']},{'adapter':'sentence-transformers','modalities':['text','cover']},
                 {'precision':'float16'}]
            for data in bad:
                path.write_text(json.dumps(data))
                with self.subTest(data=data),self.assertRaises(ValueError): load_profile(path)
            path.write_text('{' )
            catalog=ProductionCatalog(Path(tmp)/'catalog.sqlite')
            try:
                self.assertFalse(create_ai(catalog,path).status()['available'])
                self.assertEqual(catalog.search()['total'],0)
            finally: catalog.close()

    def test_dimension_and_same_dimension_revision_isolation_and_switch_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog=Path(tmp)/'catalog'
            row={'id':1,'root_id':1,'relative_path':'generated.wav','size_bytes':1,'mtime_ns':1,'title':'generated','tags':[]}
            p=DEFAULT_PROFILE
            original=VectorStore(p.store_path(catalog),p)
            original.put(1,revision(row),{'text':[1.0]+[0.0]*767})
            for other in (replace(p,dimension=3),replace(p,revision='b'*40)):
                store=VectorStore(other.store_path(catalog),other)
                self.assertEqual(store.rank([row],[1.0]+[0.0]*(other.dimension-1)),[])
                store.put(1,revision(row),{'text':[0.0,1.0]+[0.0]*(other.dimension-2)})
                self.assertTrue(store.fresh(1,revision(row)))
                with self.assertRaises(AIUnavailable): VectorStore(original.path,other)
            reopened=VectorStore(p.store_path(catalog),p)
            self.assertEqual(reopened.rank([row],[1.0]+[0.0]*767),[(1,1.0)])
            with self.assertRaises(ValueError): reopened.put(1,revision(row),{'text':[1.0]*3})
            self.assertTrue(reopened.fresh(1,revision(row)))

    def test_text_only_index_never_reads_covers_and_reports_capabilities(self):
        p=replace(DEFAULT_PROFILE,dimension=3,modalities=('text',))
        class Encoder:
            profile=p;available=True;device='test-only'
            def encode(self,op,val): return [1.,0.,0.]
            def close(self): pass
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'media';folder.mkdir();(folder/'image.png').write_bytes(b'generated')
            cat=ProductionCatalog(Path(tmp)/'catalog.sqlite')
            try:
                root=cat.add_root(str(folder));cat.start_scan(root);cat._worker.join(10)
                ai=AISearch(cat,Encoder())
                try:
                    with patch.object(ai.previews,'read',side_effect=AssertionError('Cover read')):
                        ai.start();ai.worker.join(10)
                    self.assertEqual(ai.status()['state'],'complete')
                    self.assertEqual(ai.status()['dimension'],3)
                    self.assertEqual(ai.status()['modalities'],['text'])
                    self.assertEqual(ai.search('image')['total'],1)
                    with self.assertRaises(AIUnavailable): ai.search('image',source='cover')
                finally: ai.close()
            finally: cat.close()

    def test_marker_and_worker_handshake_must_match_selected_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            model=Path(tmp);(model/'aredoko-revision.txt').write_text(DEFAULT_PROFILE.revision)
            p=replace(DEFAULT_PROFILE,revision='a'*40)
            encoder=EncoderProcess(sys.executable,model,p)
            self.assertFalse(encoder.available)
            encoder=EncoderProcess(sys.executable,model)
            process=MagicMock();process.poll.return_value=None
            with patch('ai_process.subprocess.Popen',return_value=process),patch('ai_process.threading.Thread'),patch.object(encoder,'_response',return_value={'dimension':768,'profile':p.key,'device':'test-only'}):
                with self.assertRaises(AIUnavailable): encoder._start()
            process.kill.assert_called_once()

    def test_adapter_respects_local_loading_prompt_and_input_contract(self):
        model=MagicMock();model.get_embedding_dimension.return_value=768
        ctor=MagicMock(return_value=model)
        with patch.dict(sys.modules,{'sentence_transformers':types.SimpleNamespace(SentenceTransformer=ctor)}):
            adapter=load_adapter(DEFAULT_PROFILE,'local-model','cpu','float32')
            self.assertTrue(ctor.call_args.kwargs['local_files_only'])
            self.assertFalse(ctor.call_args.kwargs['trust_remote_code'])
            self.assertEqual(ctor.call_args.kwargs['config_kwargs'],{'audio_config':None})
            adapter.encode_text('query','test')
            self.assertEqual(model.encode.call_args.kwargs['prompt_name'],'SearchQuery')
            image=object();adapter.encode_image(image)
            self.assertEqual(model.encode.call_args.args[0],{'image':image})
            generic=replace(DEFAULT_PROFILE,adapter='sentence-transformers',modalities=('text',),query_prompt_name=None,query_prefix='query: ')
            adapter=load_adapter(generic,'local-model','cpu','float32')
            self.assertEqual(ctor.call_args.kwargs['config_kwargs'],{})
            adapter.encode_text('query','test')
            self.assertEqual(model.encode.call_args.kwargs['prompt'],'query: ')
            with self.assertRaises(ValueError): adapter.encode_image(image)
            model.get_embedding_dimension.return_value=384
            with self.assertRaises(ValueError): load_adapter(generic,'local-model','cpu','float32')

    def test_interrupted_download_resumes_but_cannot_overwrite_other_revision(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('test_profile_downloader',Path(__file__).resolve().parents[1]/'tools/download-ai-model.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'model'
            download=MagicMock(side_effect=RuntimeError('simulated interruption'))
            with patch.object(ModelProfile,'model_path',return_value=target),patch.object(sys,'argv',['download']),patch.dict(sys.modules,{'huggingface_hub':types.SimpleNamespace(snapshot_download=download)}):
                with self.assertRaises(RuntimeError): module.main()
                self.assertTrue((target/'aredoko-source.json').is_file())
                self.assertFalse((target/'aredoko-revision.txt').exists())
                download.side_effect=None
                module.main()
                self.assertEqual((target/'aredoko-revision.txt').read_text(),DEFAULT_PROFILE.revision)
                before=(target/'aredoko-source.json').read_bytes()
                changed=replace(DEFAULT_PROFILE,revision='a'*40)
                with patch.object(module,'load_profile',return_value=changed),self.assertRaises(ValueError):
                    module.main()
                self.assertEqual((target/'aredoko-source.json').read_bytes(),before)
                self.assertEqual(download.call_count,2)

    def test_profile_size_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'profile.json';path.write_text(' '*8193)
            with self.assertRaises(ValueError): load_profile(path)
