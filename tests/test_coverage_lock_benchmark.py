"""CPU-only coverage evidence keeps identical responses and read-only receipts."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import benchmark_coverage_lock as bench


class CoverageLockBenchmarkTests(unittest.TestCase):
    def test_same_fixture_receipts_comparison_and_overwrite_refusal(self):
        parent=ROOT/'data/page-coverage';parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as tmp:
            self.assertTrue(Path(tmp).resolve().is_relative_to(parent.resolve()))
            output=Path(tmp)/'run'
            with contextlib.redirect_stdout(io.StringIO()):
                bench.prepare(output,6)
                bench.measure(output,'before');bench.measure(output,'after')
                comparison=bench.compare(output,'before','after')
            self.assertTrue(comparison['passed'])
            self.assertEqual([r['operation'] for r in comparison['cases']],['coverage','plan'])
            self.assertTrue(all(r['exact_response'] for r in comparison['cases']))
            report_path=output/'after.json';report=json.loads(report_path.read_text(encoding='utf-8'))
            self.assertEqual(report['encoder_calls'],0)
            self.assertTrue(report['source_and_vectors_unchanged'] and report['snapshot_unchanged'])
            original=report_path.read_bytes()
            with self.assertRaisesRegex(ValueError,'Never overwrite'):bench.measure(output,'after')
            self.assertEqual(report_path.read_bytes(),original)
            receipt=json.loads((output/'lock-receipt.json').read_text())
            (output/'generated/book.cbz').write_bytes(b'changed generated fixture')
            with self.assertRaises(AssertionError):bench.measure(output,'changed')
            failed=json.loads((output/'changed.json').read_text())
            self.assertFalse(failed['passed'])
            self.assertEqual(receipt,json.loads((output/'lock-receipt.json').read_text()))


if __name__=='__main__':unittest.main()
