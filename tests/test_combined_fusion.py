"""Fusion invariants and frozen evaluation contracts; no actual model in tests."""
import hashlib
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'));sys.path.insert(0,str(REPO/'tools'))
from ai_ranking import fuse_modalities
from ai_search import AISearch,revision
from evaluate_combined_fusion import load_manifest,metrics,summary,SHA256
from evaluate_representative_assets import EVALUATION_QUERIES,WD_TAG_QUERIES
from test_page_index import PageFixture
from test_page_semantics import Encoder


class SpanFusionTests(unittest.TestCase):
    def test_weak_text_contrast_cannot_override_separated_visual_evidence(self):
        rows={1:{'text':.65,'cover':.52},2:{'text':.64,'cover':.51},3:{'text':.63,'cover':.8}}
        self.assertEqual(fuse_modalities(rows,'mean-rrf')[0][0],3)

    def test_informative_text_wins_against_nearly_constant_images(self):
        rows={1:{'text':.55,'cover':.65},2:{'text':.54,'cover':.64},3:{'text':.9,'cover':.63}}
        self.assertEqual(fuse_modalities(rows,'mean-rrf')[0][0],3)

    def test_constant_mode_cannot_shift_order_and_candidate_membership_is_kept(self):
        scores={9:{'text':.6,'cover':.9},1:{'text':.6,'cover':.3},5:{'text':.6}}
        ranked=fuse_modalities(scores,'mean-rrf')
        self.assertEqual([i for i,_ in ranked],[9,1,5])
        self.assertEqual(ranked[-1][1],0)
        self.assertEqual({i for i,_ in ranked},set(scores))

    def test_all_tied_or_singleton_modality_pool_preserves_legacy_mean(self):
        tied=fuse_modalities({9:{'text':.6,'cover':.7},1:{'text':.6,'cover':.7}},'mean-rrf')
        self.assertEqual(tied,[(1,1/61.5),(9,1/61.5)])
        rows={1:{'text':.8},2:{'text':.6,'cover':.9}}
        self.assertEqual(fuse_modalities(rows,'mean-rrf'),[(1,1/61),(2,(1/62+1/61)/2)])

    def test_finite_extreme_values_and_signed_zero_stay_deterministic(self):
        scores={1:{'text':1.7e308,'cover':-1.7e308},2:{'text':-1.7e308,'cover':1.7e308}}
        ranked=fuse_modalities(scores,'mean-rrf')
        self.assertTrue(all(math.isfinite(s) for _,s in ranked))
        self.assertEqual(ranked,fuse_modalities(dict(reversed(list(scores.items()))),'mean-rrf'))
        self.assertEqual(fuse_modalities({1:{'text':0.,'cover':-0.}},'mean-rrf'),[(1,1/61)])

    def test_fixed_holdout_is_distinct_and_fails_before_inference_on_tamper(self):
        data=load_manifest();self.assertEqual(len(data['cases']),24)
        self.assertEqual(hashlib.sha256((REPO/'tests/fixtures/combined-fusion-v8.json').read_bytes()).hexdigest(),SHA256)
        queries={c['query'] for c in data['cases']}
        self.assertEqual(len(queries),24)
        self.assertTrue(queries.isdisjoint(c['query'] for c in EVALUATION_QUERIES+WD_TAG_QUERIES))
        for name in ('search-quality-v1.json','search-quality-v2.json','search-phase-v7.json'):
            old=json.loads((REPO/'tests/fixtures'/name).read_text(encoding='utf-8'))
            self.assertTrue(queries.isdisjoint(c['query'] for c in old['cases']))
        with patch('evaluate_combined_fusion.Path.read_bytes',return_value=b'{}'):
            with self.assertRaisesRegex(ValueError,'Frozen'):load_manifest()

    def test_noanswer_is_excluded_from_accuracy_and_rank_change_is_scored(self):
        self.assertIsNone(metrics(['a'],None))
        rows=[{'group':'text','target':'b','metric':metrics(['a','b'],'b')},
              {'group':'no-answer','target':None,'metric':None}]
        result=summary(rows,'metric')
        self.assertEqual(result['overall'],{'count':1,'top1':0,'recall3':1,'mrr':.5})


class CombinedScopeTests(PageFixture,unittest.TestCase):
    def setUp(self):
        super().setUp();self.encoder=Encoder();self.ai=AISearch(self.catalog,self.encoder)
        self.addCleanup(self.ai.close)
        self.book=self.ids['comic.cbz'];self.asset=self.ids['asset.png']
        self.catalog.update([self.book],{'tags':['manual'],'shelf':'keep','favorite':True})
        for row in self.ai._rows('','all'):
            values=(.60,.90) if row['id']==self.book else (.61,.30)
            vectors={name:[value,math.sqrt(1-value*value)]+[0.]*6 for name,value in zip(('text','cover'),values)}
            self.ai.store.put(row['id'],revision(row),vectors)
        self.encoder.encode=lambda *args:[1.]+[0.]*7

    def test_api_shape_explicit_modes_scope_filters_and_page_evidence_survive(self):
        scope={'root_ids':[self.root]};source_revision=self.ai.pages.index.previews.tag_source(self.book)['revision']
        evidence={'page':1,'page_id':'a'*64,'source_revision':source_revision,'source_state':'current'}
        before=self.ai.search('manual',source='text',scope=scope)
        with patch.object(self.ai.pages,'rank',return_value={self.book:(.95,evidence)}):
            result=self.ai.search('manual',source='all',scope=scope)
            self.assertEqual(result['items'][0]['id'],self.book)
            self.assertEqual(result['items'][0]['ai_page_match'],evidence)
            self.assertEqual(result['score_kind'],'reciprocal-rank')
            self.assertEqual(result['ranking'],'mean-rrf')
            self.assertEqual({r['id'] for r in result['items']},{self.book,self.asset})
            literal=self.ai.search('manual',source='all',scope=scope,literal_only=True)
            self.assertEqual([r['id'] for r in literal['items']],[self.book])
            self.assertEqual(self.ai.search('manual',source='all',scope={'root_ids':[]})['total'],0)
            self.assertEqual([r['id'] for r in self.ai.search('manual',source='all',scope=scope,kind='image')['items']],[self.asset])
            self.assertEqual([r['id'] for r in self.ai.search('manual',source='all',scope=scope,view='favorites')['items']],[self.book])
        after=self.ai.search('manual',source='text',scope=scope)
        self.assertEqual(before,after)
        self.assertEqual(self.catalog.get(self.book)['tags'],['manual'])


if __name__=='__main__':unittest.main()
