"""Tool preflight sequencing only; never imports torch or launches inference."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from check_direct_audio_pipeline import verify_before_gpu


class AudioPipelinePreflightTests(unittest.TestCase):
    def test_full_verifier_is_used_and_progress_is_separate_from_gpu_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            def verify(python,*,cancelled):
                self.assertFalse(cancelled());return {'manifest_sha256':'a'*64,'files':3,'bytes':20}
            with patch('runtime_paths.verify_runtime_pack',side_effect=verify) as checker,\
                 patch('runtime_paths.runtime_verification_status',return_value={'state':'verified'}),\
                 patch('runtime_paths.configure_runtime_verification') as disable:
                value=verify_before_gpu('generated-python',root)
                checker.assert_called_once();disable.assert_not_called()
            self.assertEqual(value['state'],'verified');self.assertFalse(value['verification_disabled'])
            self.assertEqual(json.loads((root/'runtime-verification.log').read_text()),{'state':'verified'})

    def test_failure_stops_progress_observer_and_preserves_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with patch('runtime_paths.verify_runtime_pack',side_effect=RuntimeError('generated failure')),\
                 patch('runtime_paths.runtime_verification_status',return_value={'state':'failed'}),self.assertRaises(RuntimeError):
                verify_before_gpu('generated-python',root)
            self.assertEqual(json.loads((root/'runtime-verification.log').read_text()),{'state':'failed'})
            with self.assertRaises(FileExistsError):verify_before_gpu('generated-python',root)

    def test_a_skipped_integrity_check_cannot_be_reported_as_verified(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch('runtime_paths.verify_runtime_pack',return_value={'files':3}),\
                 patch('runtime_paths.runtime_verification_status',return_value={'state':'skipped'}),\
                 self.assertRaisesRegex(RuntimeError,'must not be skipped'):
                verify_before_gpu('generated-python',Path(temporary))


if __name__=='__main__':unittest.main()
