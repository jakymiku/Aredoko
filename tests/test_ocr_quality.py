"""Scoring controls and backend parity; never represents OCR accuracy."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
from ocr_quality import control, digest, distance, evaluate, read_json, validate_fixture


class OCRQualityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = read_json(REPO/'tests/fixtures/ocr-eval-v1.json')

    def test_perfect_control_has_zero_error_and_full_reach(self):
        report = evaluate(self.fixture,control(self.fixture,'perfect'))
        self.assertEqual(report['summary']['cer'],0)
        self.assertEqual(report['summary']['retrieval_means']['recall_at_5'],1)
        self.assertEqual(report['summary']['retrieval_means']['mrr'],1)
        self.assertEqual(report['summary']['no_answer_false_positive_rate'],0)
        self.assertIn('no OCR inference',report['measurement_kind'])
        self.assertEqual(next(q for q in report['queries'] if q['id']=='q07')['ranked_items'],[])

    def test_empty_control_and_missing_pages_are_distinct(self):
        predictions = control(self.fixture,'empty')
        report = evaluate(self.fixture,predictions)
        self.assertEqual(report['summary']['cer'],1)
        self.assertEqual(report['summary']['missing_pages'],0)
        self.assertEqual(report['summary']['retrieval_means']['recall_at_5'],0)
        predictions['pages'] = []
        self.assertEqual(evaluate(self.fixture,predictions)['summary']['missing_pages'],8)

    def test_width_case_kana_normalized_error_keeps_raw_error(self):
        predictions = control(self.fixture,'perfect')
        predictions['pages'][-1]['text'] = 'AI素材 png/webp\n背景せっと VOL.2'
        report = evaluate(self.fixture,predictions)
        self.assertGreater(report['summary']['cer'],0)
        self.assertEqual(report['summary']['normalized_cer'],0)
        self.assertEqual(report['summary']['retrieval_means']['recall_at_5'],1)

    def test_blank_hallucination_and_false_answer_are_measured(self):
        predictions = control(self.fixture,'perfect')
        predictions['pages'][5]['text'] = '宇宙船 地下室'
        report = evaluate(self.fixture,predictions)
        self.assertEqual(report['summary']['blank_false_positives'],1)
        self.assertAlmostEqual(report['summary']['no_answer_false_positive_rate'],1/3)
        self.assertIsNone(report['pages'][5]['cer'])
        self.assertGreater(report['pages'][5]['errors'],0)

    def test_levenshtein_codepoints_and_insertions(self):
        self.assertEqual(distance('青い傘','青い空'),1)
        self.assertEqual(distance('','追加'),2)
        self.assertEqual(distance('a','bbbb'),4)

    def test_wrong_hash_unknown_duplicate_and_oversized_outputs_rejected(self):
        good = control(self.fixture,'perfect')
        invalid = []
        p = copy.deepcopy(good); p['fixture_sha256'] = '0'*64; invalid.append(p)
        p = copy.deepcopy(good); p['pages'][0]['page_id'] = 'unknown'; invalid.append(p)
        p = copy.deepcopy(good); p['pages'].append(p['pages'][0]); invalid.append(p)
        p = copy.deepcopy(good); p['pages'][0]['text'] = 'x'*2049; invalid.append(p)
        p = copy.deepcopy(good); p['pages'][0]['text'] = '\ud800'; invalid.append(p)
        p = copy.deepcopy(good); p['producer']['command'] = 'arbitrary'; invalid.append(p)
        for value in invalid:
            with self.subTest(value=str(value)[:80]),self.assertRaises(ValueError): evaluate(self.fixture,value)
        fixture = copy.deepcopy(self.fixture); fixture['queries'][0]['expected_items'] = []
        with self.assertRaisesRegex(ValueError,'Ground-truth'): validate_fixture(fixture)

    def test_json_duplicate_keys_and_size_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp)/'input.json'; file.write_text('{"version":1,"version":2}')
            with self.assertRaisesRegex(ValueError,'Duplicate'): read_json(file)
            file.write_bytes(b' '*(512*1024+1))
            with self.assertRaisesRegex(ValueError,'exceeds'): read_json(file)

    def test_offline_hit_sets_match_real_page_text_contract(self):
        from production import ProductionCatalog
        from page_index import PageIndex
        from page_text import PageTextIndex
        from create_preview_fixture import png
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); media = base/'generated'; media.mkdir()
            grouped = {}
            for page in self.fixture['pages']:
                folder = media/page['item']; folder.mkdir(exist_ok=True)
                (folder/(page['id']+'.png')).write_bytes(png())
                grouped.setdefault(page['item'],[]).append(page['text'])
            catalog = ProductionCatalog(base/'catalog.sqlite')
            try:
                root = catalog.add_root(str(media),folder_books=True)
                catalog.index.scan(root); catalog.sync_index()
                rows = catalog.search()['items']; values = {row['id']:grouped[row['title']] for row in rows}
                class Extractor:
                    class info:
                        @staticmethod
                        def record(): return {'adapter':'contract-fixture','version':'1','model':'reference','model_revision':'1','preprocessing':'none'}
                    def extract(self,payload,cancelled):
                        source=payload['source']; return values[source['item_id']][source['page']]
                pages = PageIndex(catalog); texts = PageTextIndex(catalog,pages,Extractor())
                for row in rows:
                    pages.refresh(row['id']); manifest = pages.list(row['id'])
                    texts.generate(row['id'],[p['page_id'] for p in manifest['pages']],manifest['source_revision'],uuid.uuid4().hex)
                report = evaluate(self.fixture,control(self.fixture,'perfect'))
                for query, expected in zip(self.fixture['queries'],report['queries']):
                    actual = texts.search(query['query'])
                    self.assertEqual(sorted(row['title'] for row in actual['items']),expected['ranked_items'])
            finally: catalog.close()


if __name__ == '__main__': unittest.main()
