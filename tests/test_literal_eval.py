"""Frozen literal-related v3 manifest and evaluator contract (generated files only)."""
import hashlib, json, sys, unittest
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools')); sys.path.insert(0, str(REPO / 'app'))
import evaluate_literal_search as evaluator
from term_relations import validate_entry


class LiteralEvalTests(unittest.TestCase):
    def test_manifest_is_frozen_and_consistent(self):
        raw = evaluator.MANIFEST.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), evaluator.SHA256)
        self.assertNotIn(b'\r\n', raw)
        manifest = json.loads(raw)
        keys = {item['key'] for item in manifest['items']}
        self.assertEqual(len(keys), len(manifest['items']))
        self.assertEqual(len({item['file'] for item in manifest['items']}), len(keys))
        for entry in manifest['dictionary']:
            validate_entry(entry)
        for case in manifest['cases']:
            self.assertLessEqual(set(case['relevance']), keys, case['id'])
            self.assertIn(case['group'], {'exact-control', 'variant', 'multiword', 'related', 'no-answer'})
            self.assertEqual(case['group'] == 'no-answer', not case['relevance'])

    def test_evaluator_runs_and_current_search_is_a_superset_of_legacy(self):
        result = evaluator.evaluate()
        cases = len(json.loads(evaluator.MANIFEST.read_text(encoding='utf-8'))['cases'])
        self.assertEqual(len(result['rows']), cases * len(evaluator.CONDITIONS))
        by = {(row['source'], row['case']): set(row['ranked']) for row in result['rows']}
        for (source, case), ranked in by.items():
            if source == 'legacy':
                self.assertLessEqual(ranked, by[('normalized', case)], case)
                self.assertLessEqual(by[('normalized', case)], by[('dictionary', case)], case)
        self.assertTrue(all(entry['scored_cases'] == 0 for entry in result['summary'] if entry['group'] == 'no-answer'))


if __name__ == '__main__':
    unittest.main()
