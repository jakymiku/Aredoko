"""Audit controls, not proof that product large-library gates pass."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from audit_large_library_boundary import run


class BoundaryAuditTests(unittest.TestCase):
    def test_small_fully_eligible_fixture_has_no_false_cap_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run(Path(tmp) / 'generated-audit', 31)
            self.assertTrue(result['audit_passed'])
            self.assertTrue(result['completion_gate_passed'], result['known_misses'])
            self.assertEqual(result['known_misses'], [])
            self.assertEqual(result['coverage']['candidate_total'], 31)
            self.assertEqual(result['real_model_calls'], 0)
            self.assertEqual(result['build_selection']['count'], 31)
            self.assertTrue(result['build_selection']['worker_mocked'])
            self.assertEqual(len(result['sources']), result['physical_control_files'])
            self.assertTrue(all(check['passed'] for check in result['checks']))
            cases = {case['case']: case for case in result['cases']}
            self.assertEqual(cases['all/cover']['page_evidence_ids'], result['page_control_ids'])
            self.assertIn(31, cases['all/similar']['returned_ids'])
            self.assertTrue(cases['scoped-favorites/text']['returned_final'])
            self.assertFalse(cases['excluded-final/text']['returned_final'])
            self.assertFalse(cases['unregistered-root/text']['returned_final'])

    def test_existing_directory_is_refused_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'existing'; output.mkdir()
            marker = output / 'keep.txt'; marker.write_bytes(b'keep')
            with self.assertRaises(FileExistsError): run(output, 31)
            self.assertEqual(list(output.iterdir()), [marker])
            self.assertEqual(marker.read_bytes(), b'keep')

    def test_invalid_sizes_do_not_create_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'absent'
            for count in (True, 7, 50_002, 31., '31'):
                with self.subTest(count=count), self.assertRaises(ValueError): run(output, count)
            self.assertFalse(output.exists())


if __name__ == '__main__': unittest.main()
