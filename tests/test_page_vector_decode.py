"""Exact compatibility of stored float32 page vectors with the original decoder."""
from array import array
import math
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

from ai_vectors import normalized
from page_semantics import _is_valid_packed, _score_packed, unpack


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
        self.assertEqual(unpack(data, dimension, False), expected is not None)
        self.assertEqual(_is_valid_packed(data, dimension), expected is not None)
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

    def test_nonfinite_anywhere_and_extreme_float32_keep_legacy_decisions(self):
        # Norm-sum validation must reject a nonfinite component anywhere, even
        # when a finite unit component precedes it or both infinities occur.
        for dimension in (2, 8, 768):
            for position in (0, dimension//2, dimension-1):
                for bad in (float('nan'), float('inf'), -float('inf')):
                    values = [0.0] * dimension
                    values[0] = 1.0; values[position] = bad
                    with self.subTest(dimension=dimension, position=position, bad=bad):
                        self.assertIsNone(self.assert_legacy(array('f', values).tobytes(), dimension))
        for values in ([float('inf'), -float('inf')], [float('nan'), float('inf')],
                       [3.4028234663852886e38, 1.0], [1.401298464324817e-45, -0.0],
                       [1.0, 1.401298464324817e-45], [-1.0, -1.401298464324817e-45]):
            self.assert_legacy(array('f', values).tobytes(), 2, query=[-0.0, 1.0])

    def test_corrupt_nonfinite_wrong_dimension_and_zero_are_still_rejected(self):
        for values in ([0.0, 0.0], [float('nan'), 1.0], [float('inf'), 0.0],
                       [-float('inf'), 0.0], [3.4e38, 0.0], [0.5, 0.0]):
            self.assertIsNone(self.assert_legacy(array('f', values).tobytes(), 2))
        for data, dimension in ((b'', 0), (b'x', 1), (b'abc', 1),
                                (array('f', [1]).tobytes(), 2), (None, 2), ('text', 2)):
            self.assertIsNone(self.assert_legacy(data, dimension))

    def test_buffer_protocols_and_unaligned_byte_lengths_match_legacy(self):
        valid_vec = [1.0, 0.0, 0.0, 0.0]
        valid_bytes = array('f', valid_vec).tobytes()
        # buffer protocols (memoryview, bytearray) must decode identically to bytes
        self.assert_legacy(memoryview(valid_bytes), 4)
        self.assert_legacy(bytearray(valid_bytes), 4)
        self.assertIsNone(self.assert_legacy(memoryview(b'bad'), 4))
        self.assertIsNone(self.assert_legacy(bytearray(b'bad'), 4))

        # Unaligned byte lengths (e.g. 15, 17, 18, 19 bytes for dimension 4) must be rejected
        for offset in (-3, -2, -1, 1, 2, 3):
            corrupt = valid_bytes[:max(0, len(valid_bytes) + offset)] if offset < 0 else valid_bytes + b'\x00' * offset
            self.assertIsNone(self.assert_legacy(corrupt, 4))

        # Dimension mismatches (extra or missing float)
        self.assertIsNone(self.assert_legacy(valid_bytes + array('f', [0.0]).tobytes(), 4))
        self.assertIsNone(self.assert_legacy(valid_bytes[:12], 4))

        # Negative and zero dimensions
        self.assertIsNone(self.assert_legacy(valid_bytes, -1))
        self.assertIsNone(self.assert_legacy(valid_bytes, 0))
        self.assertIsNone(self.assert_legacy(b'', 0))

    def test_mixed_nan_and_infinities_in_all_orders_are_rejected(self):
        combinations = [
            [float('nan'), float('inf')],
            [float('inf'), float('nan')],
            [-float('inf'), float('nan')],
            [float('nan'), -float('inf')],
            [float('nan'), float('nan')],
            [float('inf'), float('inf')],
            [-float('inf'), -float('inf')],
            [1.0, float('nan'), float('inf'), -float('inf')],
            [-1.0, -float('inf'), float('inf'), float('nan')],
            [float('nan')] * 8,
            [float('inf')] * 8,
            [-float('inf')] * 8,
        ]
        for vals in combinations:
            dim = len(vals)
            data = array('f', vals).tobytes()
            with self.subTest(vals=vals):
                self.assertIsNone(self.assert_legacy(data, dim))

    def test_tolerance_boundary_micro_steps_match_legacy(self):
        # Scan fine-grained steps across both sides of the 1e-4 tolerance boundary
        for base_delta in (-0.0001, 0.0001):
            for step in (-2e-6, -1e-6, 0.0, 1e-6, 2e-6):
                delta = base_delta + step
                val = math.sqrt(max(0.0, 1.0 + delta))
                data = array('f', [val, 0.0]).tobytes()
                self.assert_legacy(data, 2)


if __name__ == '__main__':
    unittest.main()

