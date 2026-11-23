"""Generated CPU profiling preserves the benchmark's exact read-only contract."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import benchmark_page_search as bench


class PageSearchProfileTests(unittest.TestCase):
    def test_profile_checks_same_results_sources_and_zero_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'generated-run'
            with contextlib.redirect_stdout(io.StringIO()):
                bench.prepare(output, books=2, pages=2)
                bench.measure(output, 'baseline')
                summary = bench.profile(output, 'profile', 'baseline')
            report_path = output/'profile.json'
            report = json.loads(report_path.read_text(encoding='utf-8'))
            baseline = json.loads((output/'baseline.json').read_text(encoding='utf-8'))
            self.assertTrue(summary['passed'])
            self.assertTrue(report['instrumented'])
            self.assertEqual(report['books'], 2)
            self.assertEqual(report['guard']['outer_holds'], 2)
            self.assertEqual(report['result_sha256'], baseline['cases'][-1]['result_sha256'])
            self.assertEqual(report['merged_sha256'], baseline['cases'][-1]['merged_sha256'])
            self.assertEqual(report['encoder_calls'], 0)
            self.assertTrue(report['source_unchanged'] and report['vectors_unchanged'])
            self.assertEqual(report['vector_sql']['execute_calls'], 1)
            self.assertEqual(report['vector_sql']['fetch_calls'], 5)  # four rows plus StopIteration
            self.assertTrue(any(f['name']=='_score_packed' for f in report['functions']))
            self.assertGreater((output/'profile.pstats').stat().st_size, 0)
            # Existing JSON and binary statistics must survive a repeated label.
            saved = report_path.read_bytes(), (output/'profile.pstats').read_bytes()
            with self.assertRaisesRegex(ValueError, 'Never overwrite'):
                bench.profile(output, 'profile', 'baseline')
            self.assertEqual(saved, (report_path.read_bytes(), (output/'profile.pstats').read_bytes()))
            # A changed generated source must fail before a new profile is recorded.
            archive = next((output/'generated').rglob('*.cbz'))
            archive.write_bytes(archive.read_bytes()+b'changed')
            with self.assertRaises(AssertionError):
                bench.profile(output, 'changed', 'baseline')
            self.assertFalse((output/'changed.json').exists())
            self.assertFalse((output/'changed.pstats').exists())


if __name__ == '__main__':
    unittest.main()
