"""Ranking must preserve missing-modality candidates, ties and explicit policy semantics."""
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from ai_ranking import fuse_modalities

class FusionTests(unittest.TestCase):
    def test_legacy_max_keeps_best_cosine_and_id_tiebreak(self):
        self.assertEqual(fuse_modalities({2:{'text':.8,'cover':.3},1:{'cover':.8},3:{'text':-.2}}),[(1,.8),(2,.8),(3,-.2)])
    def test_agreement_can_outrank_a_single_dominant_cosine(self):
        rows={1:{'text':.98,'cover':.01},2:{'text':.96,'cover':.8},3:{'text':.95,'cover':.7}}
        self.assertEqual(fuse_modalities(rows)[0][0],1)
        self.assertEqual(fuse_modalities(rows,'mean-rrf')[0][0],2)
    def test_missing_cover_is_not_penalized_by_vector_count(self):
        rows={1:{'text':.99},2:{'text':.5,'cover':.95},3:{'text':.45,'cover':.94}}
        self.assertEqual(fuse_modalities(rows,'mean-rrf')[0][0],1)
        self.assertEqual({i for i,_ in fuse_modalities(rows,'mean-rrf')},{1,2,3})
    def test_equal_scores_receive_equal_ranks_not_id_preference(self):
        scores=fuse_modalities({9:{'text':.2,'cover':.7},1:{'text':.2,'cover':.7}},'mean-rrf')
        self.assertEqual(scores[0][1],scores[1][1]);self.assertEqual([r[0] for r in scores],[1,9])
        reordered=fuse_modalities({1:{'cover':.7,'text':.2},9:{'cover':.7,'text':.2}},'mean-rrf')
        self.assertEqual(scores,reordered)
    def test_one_modality_keeps_order_and_negative_cosines_are_valid(self):
        rows={1:{'text':-.1},2:{'text':-.5},3:{'text':-.9}}
        self.assertEqual([i for i,_ in fuse_modalities(rows,'mean-rrf')],[1,2,3])
        self.assertTrue(all(0<score<=1/61 for _,score in fuse_modalities(rows,'mean-rrf')))
    def test_bad_policy_and_nonfinite_scores_are_rejected(self):
        for bad in ({1:{}},{1:{'text':math.nan}},{1:{'cover':math.inf}}):
            with self.assertRaises(ValueError):fuse_modalities(bad,'mean-rrf')
        with self.assertRaises(ValueError):fuse_modalities({},'auto')
        self.assertEqual(fuse_modalities({},'mean-rrf'),[])
