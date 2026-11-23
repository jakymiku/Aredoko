"""Bit-exact scalar score optimization; supplied vectors only, no AI runtime."""
from array import array
import random
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from ai_vectors import dot


class ExactDotTests(unittest.TestCase):
    def test_seeded_float64_vectors_keep_every_score_bit(self):
        rng=random.Random(20261028)
        for size in (1,3,128,512,768):
            for number in range(40):
                left=array('d',(rng.uniform(-1,1) for _ in range(size)))
                right=array('d',(rng.uniform(-1,1) for _ in range(size)))
                with self.subTest(size=size,pair=number):
                    self.assertEqual(struct.pack('<d',dot(left,right)),struct.pack('<d',sum(a*b for a,b in zip(left,right))))

    def test_cancellation_sensitive_magnitudes_and_signed_zero_keep_sum_order(self):
        for left,right in (([1.,1e-16,-1.],[1.,1.,1.]),([1e-300,-1e-300,0.],[-1e-300,1e-300,-0.]),
                           ([-0.,0.,-0.],[1.,-1.,-1.]),([1.,-1.,1e-12],[1.,1.,1e-12])):
            with self.subTest(left=left):
                self.assertEqual(dot(left,right).hex(),sum(a*b for a,b in zip(left,right)).hex())


if __name__=='__main__':unittest.main()
