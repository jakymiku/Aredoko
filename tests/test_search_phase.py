"""Evaluator contracts only; doubles never count as model quality."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
import evaluate_search_phase as phase


class FakeEncoder:
    available = True
    def __init__(self): self.calls = []
    def encode(self, operation, value):
        self.calls.append(operation)
        return [1.0] + [0.0] * 767
    def close(self): pass


class PhaseTests(unittest.TestCase):
    def test_frozen_inputs_unique_and_separate_from_old_suites(self):
        raw, data = phase.load_manifest()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), phase.SHA256)
        self.assertEqual(len(data['cases']), 24)
        self.assertEqual(len({c['id'] for c in data['cases']}), 24)
        self.assertEqual({i['root'] for i in data['items']}, {'A', 'B'})
        for name in ['search-quality-v1.json', 'search-quality-v2.json', 'literal-related-v6.json']:
            previous = json.loads((REPO / 'tests/fixtures' / name).read_text(encoding='utf-8'))
            self.assertTrue({c['query'] for c in data['cases']}.isdisjoint(c['query'] for c in previous['cases']))
            self.assertTrue({i['file'] for i in data['items']}.isdisjoint(i['file'] for i in previous['items']))

    def test_tampering_fails_before_creating_output_or_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'new'; encoder = FakeEncoder()
            with patch.object(phase.Path, 'read_bytes', return_value=b'{}'):
                with self.assertRaisesRegex(ValueError, 'Frozen'):
                    phase.evaluate(output, encoder)
            self.assertFalse(output.exists()); self.assertEqual(encoder.calls, [])

    def test_full_generated_contract_keeps_scope_noanswer_and_source_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'new'; encoder = FakeEncoder()
            report = phase.evaluate(target, encoder)
            self.assertTrue(report['runtime_pass'], report.get('error'))
            self.assertFalse(report['actual_cuda'])
            self.assertEqual(report['quality_gate'], 'test_double_not_model_quality')
            self.assertTrue(report['source_unchanged'])
            self.assertEqual(len(report['cases']), 240)
            self.assertIsNone(report['ui_time_to_find_ms'])
            scoped = next(r for r in report['cases'] if r['id'] == 'n7_q02' and r['scope'] == 'root-A' and r['condition'] == 'text')
            self.assertTrue(scoped['scope_excludes_relevance']); self.assertIsNone(scoped['metrics'])
            self.assertFalse(scoped['no_answer_probe'])
            unsupported = next(r for r in report['cases'] if r['kind'] == 'audio' and r['condition'] == 'cover')
            self.assertTrue(unsupported['source_ineligible']); self.assertEqual(unsupported['returned_count'], 0)
            alias = next(r for r in report['cases'] if r['id'] == 'n7_q21' and r['scope'] == 'all-roots' and r['condition'] == 'related')
            self.assertEqual(alias['top_5'], ['n7_b03'])
            noanswer = next(r for r in report['summary'] if r['group'] == 'no-answer' and r['scope'] == 'all-roots' and r['condition'] == 'cover')
            self.assertEqual(noanswer['no_answer_cases'], 1)  # Audio has no eligible cover pool.
            with self.assertRaises(FileExistsError): phase.evaluate(target, encoder)


if __name__ == '__main__': unittest.main()
