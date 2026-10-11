"""Decisions must abstain on unstable/unsupported hints and bind exact questions."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from intent_questions import get_questions,question_key,QUESTION_SETS,reversed_questions
from search_intent import SearchIntent,validate_decision
from laya_config import IDENTITY,CONTRACT
from laya_process import LayaProcess

class Provider:
    available=True;device='test-only'
    def __init__(self,intent='cover',kind='material',stable=None):
        self.questions=get_questions('v2-hybrid')
        self.result={'answers':{key:{'type':'choice','choice':choice,
            'probabilities':{label:float(label==choice) for label in self.questions[key]['criteria']}}
            for key,choice in (('intent',intent),('kind',kind))}}
        if stable is not None:self.result['order_consistent']=stable
    def decide(self,query):return self.result

class IntentV2Tests(unittest.TestCase):
    def test_unstable_answers_abstain_independently_and_keep_manual_settings(self):
        p=Provider('text','book',{'intent':False,'kind':True})
        result=SearchIntent(p).suggest('generated','cover','image')
        self.assertEqual(result['requested'],{'source':'cover','kind':'image'})
        self.assertEqual(result['suggestion']['intent'],'mixed');self.assertEqual(result['suggestion']['kind'],'book')
        self.assertEqual(result['suggestion']['abstained'],['intent'])
        p=Provider('cover','book',{'intent':True,'kind':False})
        result=SearchIntent(p).suggest('generated')['suggestion']
        self.assertEqual(result['intent'],'cover');self.assertEqual(result['kind'],'any')
        self.assertFalse(result['scores_calibrated'])

    def test_cover_for_unencoded_media_falls_back_without_content_filter(self):
        for kind in ('material','audio','video'):
            s=SearchIntent(Provider('cover',kind,{'intent':True,'kind':True}))
            result=s.suggest('下着のデザインテンプレート','text','material')
            self.assertEqual(result['state'],'suggested');self.assertEqual(result['suggestion']['source'],'all')
            self.assertEqual(result['suggestion']['abstention_reasons']['intent'],'no-cover-for-suggested-kind')
            self.assertEqual(result['requested'],{'source':'text','kind':'material'})

    def test_material_is_valid_for_new_questions_but_rejected_under_legacy_contract(self):
        p=Provider('text','material');self.assertEqual(validate_decision(p.result,p.questions)['kind']['choice'],'material')
        with self.assertRaises(ValueError):validate_decision(p.result,get_questions('v1'))

    def test_invalid_stability_returns_no_suggestion(self):
        for stable in ({'intent':'true','kind':True},{'kind':False},[],{'intent':True,'kind':True,'extra':False}):
            p=Provider();p.result['order_consistent']=stable
            self.assertEqual(SearchIntent(p).suggest('generated')['state'],'unavailable')

    def test_question_hash_includes_option_order_and_registry_is_not_mutated_by_callers(self):
        original=question_key('v2-hybrid');q=get_questions('v2-hybrid')
        q['kind']['criteria']['any']='changed'
        self.assertEqual(question_key('v2-hybrid'),original)
        with patch.dict(QUESTION_SETS,{'v2-hybrid':reversed_questions(get_questions('v2-hybrid'))}):
            self.assertNotEqual(question_key('v2-hybrid'),original)
        with self.assertRaises(ValueError):get_questions('arbitrary.py')

    def test_mismatched_question_hello_and_missing_order_evidence_kill_child(self):
        for wrong_key in (True,False):
            p=LayaProcess('fake-python','fake-model',question_set='v2-hybrid',check_order=True)
            process=MagicMock();process.poll.return_value=None
            hello={'ready':True,'identity':IDENTITY,'contract':CONTRACT,'device':'cpu','worker_pid':123,
                   'question_key':'wrong' if wrong_key else p.question_key,'check_order':True}
            result={'result':Provider('text','material').result}
            with patch.object(LayaProcess,'available',new_callable=lambda:property(lambda self:True)),                 patch('laya_process.subprocess.Popen',return_value=process),patch('laya_process.threading.Thread'),                 patch.object(p,'_response',side_effect=[hello,result]):
                self.assertEqual(SearchIntent(p).suggest('generated')['state'],'unavailable')
                process.kill.assert_called_once();self.assertIsNone(p.process)

    def test_new_holdout_is_separate_and_frozen_before_selection(self):
        rows=json.loads((Path(__file__).parent/'fixtures/laya-ja-v2.json').read_text(encoding='utf-8'))
        self.assertEqual(len(rows),68)
        self.assertEqual(sum(r['split']=='development' for r in rows),32)
        self.assertEqual(sum(r['split']=='legacy-regression' for r in rows),12)
        self.assertEqual(sum(r['split']=='held-out-v2' for r in rows),24)
        old=json.loads((Path(__file__).parent/'fixtures/laya-ja-queries.json').read_text(encoding='utf-8'))
        self.assertFalse({r['query'] for r in rows if r['split']=='held-out-v2'} & {r['query'] for r in old})
