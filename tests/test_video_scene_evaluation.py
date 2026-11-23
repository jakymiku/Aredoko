"""CPU truth/metric contracts, never a model accuracy claim or GPU invocation."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tools')]
from evaluate_video_scene_assets import LAYOUTS,QUERIES,assess,fixture


class VideoSceneEvaluationTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        (self.root/'media').mkdir();rows=[]
        for name,layout in LAYOUTS.items():
            data=('CPU fixture only '+name).encode();(self.root/'media'/name).write_bytes(data);segments=[];cursor=0
            for scene,seconds in layout:segments.append({'scene':scene,'start_ms':cursor,'end_ms':cursor+seconds*1000});cursor+=seconds*1000
            rows.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'segments':segments,'duration_ms':cursor})
        self.value={'format':'aredoko-video-scene-fixture-v1','videos':rows,'queries':[{'query':q,'scene':s} for q,s in QUERIES]}
        self.ids={1:'scenes-ordered.mp4',2:'scenes-reversed.mp4',3:'scene-control.mp4'};self.save()
    def save(self):(self.root/'fixture.json').write_text(json.dumps(self.value))
    def test_order_and_one_second_tail_are_both_scored_as_exact_intervals(self):
        items=[{'id':1,'video_match_ms':0,'video_match_end_ms':16000},{'id':2,'video_match_ms':48000,'video_match_end_ms':49000}]
        result=assess(self.value,'bookA_p02',items,self.ids)
        self.assertTrue(result['top1']);self.assertEqual(result['reciprocal_rank'],1);self.assertEqual(result['recall_at3'],1)
        self.assertEqual(result['interval_matches'],2);self.assertEqual(result['expected_intervals'],2)
    def test_wrong_rank_and_wrong_interval_are_not_hidden_by_correct_item_ids(self):
        items=[{'id':3,'video_match_ms':0,'video_match_end_ms':4000},{'id':1,'video_match_ms':16000,'video_match_end_ms':32000},
            {'id':2,'video_match_ms':48000,'video_match_end_ms':49000}]
        result=assess(self.value,'bookA_p02',items,self.ids)
        self.assertFalse(result['top1']);self.assertEqual(result['reciprocal_rank'],.5);self.assertEqual(result['interval_matches'],1)
        self.assertEqual(result['recall_at3'],1)
    def test_empty_retrieval_stays_zero_and_unknown_scene_is_rejected(self):
        result=assess(self.value,'bookA_p02',[],self.ids)
        self.assertFalse(result['top1']);self.assertEqual(result['recall_at3'],0);self.assertEqual(result['reciprocal_rank'],0)
        self.assertEqual(result['interval_matches'],0);self.assertEqual(result['expected_intervals'],2)
        with self.assertRaises(ValueError):assess(self.value,'unlabelled',[],self.ids)
    def test_duplicate_unknown_ids_or_invalid_ranges_cannot_inflate_recall(self):
        valid={'id':1,'video_match_ms':0,'video_match_end_ms':16000}
        for rows in ([valid,valid.copy()],[dict(valid,id=999)],[dict(valid,id=True)],[dict(valid,video_match_ms=-1)],
            [dict(valid,video_match_end_ms=50000)],[dict(valid,video_match_ms='0')]):
            with self.subTest(rows=rows),self.assertRaises(ValueError):assess(self.value,'bookA_p02',rows,self.ids)
    def test_sealed_fixture_and_equal_size_byte_tampering_are_checked(self):
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()};value,sha=fixture(self.root)
        self.assertEqual(len(value['videos']),3);self.assertEqual(len(sha),64)
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        p=self.root/'media/scenes-ordered.mp4';p.write_bytes(b'x'*p.stat().st_size)
        with self.assertRaisesRegex(ValueError,'bytes or boundaries'):fixture(self.root)
    def test_changed_tail_truth_query_or_duplicate_and_escape_are_rejected(self):
        original=json.loads(json.dumps(self.value))
        operations=[lambda v:v['videos'][0]['segments'][-1].update(end_ms=50000),lambda v:v['queries'][0].update(query='easier revised query'),
            lambda v:v['videos'][0].update(path='../private.mp4'),lambda v:v['videos'].__setitem__(0,v['videos'][1].copy())]
        for operation in operations:
            self.value=json.loads(json.dumps(original));operation(self.value);self.save()
            with self.subTest(operation=operation),self.assertRaises(ValueError):fixture(self.root)
    def test_unexpected_media_file_is_not_silently_scanned(self):
        (self.root/'media/extra.png').write_bytes(b'not included')
        with self.assertRaisesRegex(ValueError,'Unexpected file'):fixture(self.root)


if __name__=='__main__':unittest.main()
