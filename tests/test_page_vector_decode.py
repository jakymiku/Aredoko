from array import array
import math
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

from ai_vectors import normalized
from page_semantics import _score_packed, unpack


def legacy_decode(data, dimension):
    """Frozen pre-optimization decoder: two validations and two norm sums."""
    try:
        value = array('f')
        value.frombytes(data)
        if (len(value) != dimension or any(not math.isfinite(x) for x in value)
                or abs(sum(x*x for x in value)-1) > 1e-4):
            return None
        return normalized(value, dimension)
    except (ValueError, TypeError, OverflowError):
        return None


class PageVectorDecodeTests(unittest.TestCase):
    def assert_legacy(self, data, dimension, query=None):
        expected = legacy_decode(data, dimension)
        actual = unpack(data, dimension)
        probe = query if query is not None else ([1.0] + [0.0] * max(0, dimension - 1) if dimension > 0 else [])
        scored = _score_packed(data, dimension, probe)
        if expected is None:
            self.assertIsNone(actual)
            self.assertIsNone(scored)
        else:
            self.assertIsInstance(actual, list)
            # hex retains signed zero and every float64 bit relevant to ranking.
            self.assertEqual([x.hex() for x in actual], [x.hex() for x in expected])
            expected_score = sum(a*b for a, b in zip(probe, expected))
            self.assertIsInstance(scored, float)
            self.assertEqual(scored.hex(), expected_score.hex())
        return actual

    def test_dense_stored_vectors_preserve_every_score_bit_and_page_order(self):
        rng = random.Random(20261017)
        for dimension in (1, 2, 8, 768):
            query = normalized([rng.uniform(-1, 1) for _ in range(dimension)], dimension)
            expected_scores = []
            actual_scores = []
            packed_scores = []
            for page in range(128):
                values = normalized([rng.uniform(-1, 1) for _ in range(dimension)], dimension)
                data = array('f', values).tobytes()
                actual = self.assert_legacy(data, dimension, query=query)
                expected = legacy_decode(data, dimension)
                expected_scores.append(sum(a*b for a, b in zip(query, expected)))
                actual_scores.append(sum(a*b for a, b in zip(query, actual)))
                packed_scores.append(_score_packed(data, dimension, query))
            self.assertEqual([x.hex() for x in actual_scores], [x.hex() for x in expected_scores])
            self.assertEqual([x.hex() for x in packed_scores], [x.hex() for x in expected_scores])
            self.assertEqual(sorted(range(128), key=actual_scores.__getitem__, reverse=True),
                             sorted(range(128), key=expected_scores.__getitem__, reverse=True))
            self.assertEqual(sorted(range(128), key=packed_scores.__getitem__, reverse=True),
                             sorted(range(128), key=expected_scores.__getitem__, reverse=True))

    def test_unit_tolerance_boundary_and_signed_zero_keep_legacy_decisions(self):
        for squared_delta in (-0.00011, -0.0001, -0.00009, 0, 0.00009, 0.0001, 0.00011):
            values = [math.sqrt(1+squared_delta), -0.0, 0.0, 0.0]
            self.assert_legacy(array('f', values).tobytes(), 4, query=[0.5, -0.5, 0.5, 0.5])
        self.assertIsNotNone(self.assert_legacy(array('f', [1.00004, -0.0]).tobytes(), 2, query=[0.6, -0.8]))
        self.assertIsNone(self.assert_legacy(array('f', [1.00006, 0]).tobytes(), 2, query=[0.6, -0.8]))

    def test_corrupt_nonfinite_wrong_dimension_and_zero_are_still_rejected(self):
        for values in ([0.0, 0.0], [float('nan'), 1.0], [float('inf'), 0.0],
                       [-float('inf'), 0.0], [3.4e38, 0.0], [0.5, 0.0]):
            self.assertIsNone(self.assert_legacy(array('f', values).tobytes(), 2))
        for data, dimension in ((b'', 0), (b'x', 1), (b'abc', 1),
                                (array('f', [1]).tobytes(), 2), (None, 2), ('text', 2)):
            self.assertIsNone(self.assert_legacy(data, dimension))


if __name__ == '__main__':
    unittest.main()
