"""Frozen literal-related manifests and evaluator contract (generated files only)."""
import hashlib, json, sys, unittest
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools')); sys.path.insert(0, str(REPO / 'app'))
import evaluate_literal_search as evaluator
from term_relations import validate_entry

GROUPS = {'exact-control', 'variant', 'multiword', 'related', 'over-expansion', 'no-answer'}


class LiteralEvalTests(unittest.TestCase):
    def check_manifest(self, name, sha):
        raw = (evaluator.FIXTURES / name).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), sha)
        self.assertNotIn(b'\r\n', raw)
        manifest = json.loads(raw)
        keys = {item['key'] for item in manifest['items']}
        self.assertEqual(len(keys), len(manifest['items']))
        self.assertEqual(len({item['file'] for item in manifest['items']}), len(keys))
        for entry in manifest['dictionary']:
            validate_entry(entry)
        for case in manifest['cases']:
            self.assertLessEqual(set(case['relevance']), keys, case['id'])
            self.assertIn(case['group'], GROUPS)
            self.assertEqual(case['group'] == 'no-answer', not case['relevance'])
        return manifest

    def test_manifests_are_frozen_and_consistent(self):
        for version, (name, sha) in evaluator.FROZEN.items():
            with self.subTest(version=version):
                self.check_manifest(name, sha)

    def test_current_search_is_a_superset_of_legacy(self):
        for version, (name, sha) in evaluator.FROZEN.items():
            with self.subTest(version=version):
                cases = len(self.check_manifest(name, sha)['cases'])
                result = evaluator.evaluate(version)
                self.assertEqual(len(result['rows']), cases * len(evaluator.CONDITIONS))
                by = {(row['source'], row['case']): row for row in result['rows']}
                full = lambda source, case: (set() if by[(source, case)]['partial']
                                             else set(by[(source, case)]['ranked']))
                for (source, case), row in by.items():
                    if source == 'legacy':
                        # Full (all-word) matches only grow: legacy ⊆ normalized ⊆ dictionary.
                        # A partial fallback replaces an empty full match and is checked apart.
                        self.assertLessEqual(set(row['ranked']), full('normalized', case), case)
                        self.assertLessEqual(full('normalized', case), full('dictionary', case), case)
                        if by[('dictionary', case)]['partial']:
                            self.assertTrue(by[('normalized', case)]['partial'], case)
                self.assertTrue(all(entry['scored_cases'] == 0 for entry in result['summary']
                                    if entry['group'] == 'no-answer'))


if __name__ == '__main__':
    unittest.main()
