"""Explicit setup must preserve package/model provenance and resumability."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import laya_config as config
import setup_laya as setup

class LayaSetupTests(unittest.TestCase):
    def test_exact_inventory_and_rate_plan_without_install(self):
        self.assertEqual(config.MODEL_BYTES,678201614)
        with patch.object(sys,'argv',['setup']),patch.object(setup.subprocess,'run') as run:
            setup.main()
            run.assert_not_called()
        with patch.object(sys,'argv',['setup','--rate','6000001']),self.assertRaises(SystemExit):setup.main()

    def test_interrupted_download_resumes_and_other_revision_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'checkpoint'
            with self.assertRaises(OSError):setup.download_model(target,lambda *a,**k: (_ for _ in ()).throw(OSError()))
            self.assertFalse((target/'aredoko-revision.txt').exists())
            calls=[]
            with patch.object(setup,'validate_artifacts'):
                setup.download_model(target,lambda *a,**k:calls.append((a,k)))
            self.assertEqual(calls[0][1]['revision'],config.REVISION)
            self.assertEqual(set(calls[0][1]['allow_patterns']),set(config.ARTIFACTS))
            self.assertEqual((target/'aredoko-revision.txt').read_text(),config.REVISION)
            (target/'aredoko-source.json').write_text('{}')
            with self.assertRaises(ValueError):setup.download_model(target,lambda *a,**k:self.fail('Unexpected download'))

    def test_integrity_rejects_size_or_digest_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'model.safetensors';path.write_bytes(b'fixture')
            artifacts={'model.safetensors':(7,hashlib.sha256(b'fixture').hexdigest())}
            with patch.object(config,'ARTIFACTS',artifacts):
                config.validate_artifacts(tmp)
                path.write_bytes(b'badsize!')
                with self.assertRaises(ValueError):config.validate_artifacts(tmp)
                path.write_bytes(b'changed')
                with self.assertRaises(ValueError):config.validate_artifacts(tmp)

    def test_normalized_tokenizer_config_must_match_entire_pinned_object(self):
        original={'extra_special_tokens':['<start_of_turn>','<end_of_turn>'],'tokenizer_class':'PreTrainedTokenizerFast'}
        raw=(json.dumps(original,indent=2)+'\n').encode()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'tokenizer/tokenizer_config.json';path.parent.mkdir()
            path.write_bytes(raw)
            artifacts={'tokenizer/tokenizer_config.json':(len(raw),hashlib.sha256(raw).hexdigest())}
            with patch.object(config,'ARTIFACTS',artifacts):
                config.validate_artifacts(tmp,allow_tokenizer_fix=True)
                patched={**original,'extra_special_tokens':{'extra_0':'<start_of_turn>','extra_1':'<end_of_turn>'}}
                path.write_text(json.dumps(patched,indent=2))
                config.validate_artifacts(tmp,allow_tokenizer_fix=True)
                patched['tokenizer_class']='UnexpectedTokenizer'
                path.write_text(json.dumps(patched))
                with self.assertRaises(ValueError):config.validate_artifacts(tmp,allow_tokenizer_fix=True)
