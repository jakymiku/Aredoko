import json
import hashlib
import math
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
from search_quality import metrics,summary
from create_search_quality_fixture import create

class SearchQualityTests(unittest.TestCase):
    def test_graded_metrics_and_truncated_recall(self):
        result=metrics(['noise','related','best'],{'best':2,'related':1})
        self.assertEqual(result['hit_at_1'],0)
        self.assertEqual(result['mrr'],0.5)
        self.assertEqual(result['recall_at_5'],1)
        self.assertAlmostEqual(result['precision_at_5'],2/3)
        expected=(1/math.log2(3)+3/math.log2(4))/(3+1/math.log2(3))
        self.assertAlmostEqual(result['ndcg_at_5'],expected)
        self.assertEqual(metrics(['related'],{'best':2,'related':1})['recall_at_5'],0.5)
        self.assertEqual(metrics(['related'],{'best':2,'related':1})['precision_at_5'],1)
        self.assertEqual(metrics(['related'],{'best':2,'related':1})['best_grade_at_1'],0)
    def test_missing_result_and_no_answer_separate(self):
        self.assertEqual(metrics([],{'x':2})['ndcg_at_5'],0)
        self.assertEqual(metrics([],{'x':2})['precision_at_5'],0)
        self.assertIsNone(metrics(['anything'],{}))
        with self.assertRaises(ValueError):metrics(['x','x'],{'x':2})
        with self.assertRaises(ValueError):metrics(['x'],{'x':True})
    def test_summary_keeps_modes_and_controls_separate(self):
        rows=[{'group':group,'source':source,'filter':'all-kinds','metrics':metrics(['x'],rel)}
              for group,source,rel in [('semantic','text',{'x':2}),('visual','cover',{'x':2}),('no-answer','text',{})]]
        result=summary(rows)
        self.assertEqual(len(result),3)
        self.assertEqual(result[0]['scored_cases'],0)
        self.assertIsNone(result[0]['means'])
    def test_frozen_manifest_keys_qrels_and_sources(self):
        self.assertEqual(hashlib.sha256((REPO/'tests/fixtures/search-quality-v1.json').read_bytes()).hexdigest(),
                         '94260e45459d539285d7cde257214cddc9c39263b454a15b8e3c3b1e2e15afa8')
        manifest=json.loads((REPO/'tests/fixtures/search-quality-v1.json').read_text(encoding='utf-8'))
        items={item['key']:item for item in manifest['items']}
        self.assertEqual(len(items),len(manifest['items']))
        self.assertEqual(len({case['id'] for case in manifest['cases']}),len(manifest['cases']))
        for case in manifest['cases']:
            self.assertTrue(set(case['relevance'])<=items.keys())
            self.assertEqual(bool(case['relevance']),case['group']!='no-answer')
            for key,grade in case['relevance'].items():self.assertIn(grade,(1,2))
            if 'cover' in case['sources']:
                self.assertTrue(all(items[key]['kind'] in ('image','book') for key in case['relevance']))
    def test_sources_are_real_minimal_formats_and_neutral_names(self):
        manifest=json.loads((REPO/'tests/fixtures/search-quality-v1.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as tmp:
            folder=create(Path(tmp)/'generated',manifest['items'])
            self.assertEqual(len(list(folder.iterdir())),26)
            self.assertTrue((folder/'v01.png').read_bytes().startswith(b'\x89PNG'))
            with zipfile.ZipFile(folder/'b01.cbz') as archive:
                self.assertEqual(archive.namelist(),['page01.png'])
            self.assertTrue((folder/'a01.wav').read_bytes().startswith(b'RIFF'))
            self.assertNotIn('下着',(folder/'m01.svg').read_text(encoding='utf-8'))
            with self.assertRaises(FileExistsError):create(folder,manifest['items'])

if __name__=='__main__':unittest.main()
