"""Unit tests for representative asset evaluation harness and security bounds."""
from dataclasses import replace
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / 'app'))
sys.path.insert(0, str(ROOT / 'tools'))

from ai_profiles import DEFAULT_PROFILE
from create_preview_fixture import png
from evaluate_representative_assets import (
    CANONICAL_SPECS,
    EVALUATION_QUERIES,
    generate_placeholder_assets,
    match_asset_key,
    load_assets_from_zip,
    load_assets_from_dir,
    build_evaluation_library,
    evaluate,
)


class MockEncoder:
    available = True
    device = 'cpu'

    def __init__(self, dimension=8):
        self.profile = replace(DEFAULT_PROFILE, dimension=dimension)
        self.calls = []

    def encode(self, operation, value):
        self.calls.append((operation, value))
        # Return deterministic unit vectors
        val = [0.0] * self.profile.dimension
        val[0] = 1.0
        return val

    def close(self):
        pass


class RepresentativeAssetEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='aredoko-test-rep-')
        self.output_base = ROOT / 'data/representative-eval'
        self.output_base.mkdir(parents=True, exist_ok=True)
        self.run_dir = self.output_base / f'test-run-{Path(self.temp_dir).name}'

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def test_asset_key_matching_exact_prefix_and_case_insensitive(self):
        self.assertEqual(match_asset_key('bookA_p01_cover.png'), 'bookA_p01')
        self.assertEqual(match_asset_key('BOOKA_P02_CLASSROOM.PNG'), 'bookA_p02')
        self.assertEqual(match_asset_key('bookB_p03_chapter.webp'), 'bookB_p03')
        self.assertEqual(match_asset_key('asset_04_anything.jpg'), 'asset_04')
        self.assertEqual(match_asset_key('asset_01.png'), 'asset_01')

        # Non-matching or invalid extension
        self.assertIsNone(match_asset_key('unknown.png'))
        self.assertIsNone(match_asset_key('bookA_p01.txt'))
        self.assertIsNone(match_asset_key('asset_99.png'))

    def test_generate_placeholder_assets_produces_all_14_keys(self):
        placeholders = generate_placeholder_assets()
        self.assertEqual(set(placeholders.keys()), set(CANONICAL_SPECS.keys()))
        self.assertEqual(len(placeholders), 14)
        for key, item in placeholders.items():
            self.assertTrue(item['data'].startswith(b'\x89PNG\r\n\x1a\n'))
            self.assertEqual(item['filename'], CANONICAL_SPECS[key]['file'])

    def test_load_assets_from_zip_and_dir_safety(self):
        # 1. Path traversal in zip
        bad_zip = Path(self.temp_dir) / 'traversal.zip'
        with zipfile.ZipFile(bad_zip, 'w') as zf:
            zf.writestr('../evil.png', b'bad')
        with self.assertRaises(ValueError) as ctx:
            load_assets_from_zip(bad_zip)
        self.assertIn('Path traversal', str(ctx.exception))

        # 2. Missing assets in zip
        partial_zip = Path(self.temp_dir) / 'partial.zip'
        with zipfile.ZipFile(partial_zip, 'w') as zf:
            zf.writestr('bookA_p01_cover.png', png(color=(10, 10, 10)))
        with self.assertRaises(ValueError) as ctx:
            load_assets_from_zip(partial_zip)
        self.assertIn('Missing required assets', str(ctx.exception))

        # 3. Valid zip with all 14 images
        placeholders = generate_placeholder_assets()
        good_zip = Path(self.temp_dir) / 'valid_14.zip'
        with zipfile.ZipFile(good_zip, 'w') as zf:
            for key, p in placeholders.items():
                zf.writestr(p['filename'], p['data'])
        loaded_zip = load_assets_from_zip(good_zip)
        self.assertEqual(set(loaded_zip.keys()), set(CANONICAL_SPECS.keys()))

        # 4. Valid dir with all 14 images
        good_dir = Path(self.temp_dir) / 'valid_dir'
        good_dir.mkdir()
        for key, p in placeholders.items():
            (good_dir / p['filename']).write_bytes(p['data'])
        loaded_dir = load_assets_from_dir(good_dir)
        self.assertEqual(set(loaded_dir.keys()), set(CANONICAL_SPECS.keys()))

    def test_build_evaluation_library_structure(self):
        placeholders = generate_placeholder_assets()
        lib_dir = Path(self.temp_dir) / 'lib'
        lib = build_evaluation_library(lib_dir, placeholders)

        # Check bookA.cbz contents
        bookA_path = lib['cbz_dir'] / 'bookA.cbz'
        self.assertTrue(bookA_path.is_file())
        with zipfile.ZipFile(bookA_path, 'r') as zf:
            names = zf.namelist()
            self.assertEqual(len(names), 6)
            self.assertEqual(names[0], 'bookA_p01_cover.png')
            self.assertEqual(names[5], 'bookA_p06_bubble_promise.png')

        # Check bookB folder contents
        bookB_path = lib['folder_dir'] / 'bookB'
        self.assertTrue(bookB_path.is_dir())
        folder_files = sorted(f.name for f in bookB_path.iterdir())
        self.assertEqual(len(folder_files), 4)
        self.assertEqual(folder_files[0], 'bookB_p01_shrine.png')
        self.assertEqual(folder_files[3], 'bookB_p04_blackboard_text.png')

        # Check assets folder contents
        assets_path = lib['assets_dir']
        self.assertTrue(assets_path.is_dir())
        asset_files = sorted(f.name for f in assets_path.iterdir())
        self.assertEqual(len(asset_files), 4)
        self.assertEqual(asset_files[0], 'asset_01_glasses_girl.png')
        self.assertEqual(asset_files[3], 'asset_04_english_sign.png')

    def test_evaluate_synthetic_placeholder_end_to_end(self):
        encoder = MockEncoder()
        report = evaluate(
            output_dir=self.run_dir,
            generate_placeholder=True,
            encoder=encoder,
            skip_wd=True,
        )

        self.assertTrue(report['passed'])
        self.assertTrue(report['synthetic_placeholder'])
        self.assertEqual(report['catalog_items'], 6)

        # Output receipts
        proto_file = self.run_dir / 'frozen-protocol.json'
        report_file = self.run_dir / 'report.json'
        self.assertTrue(proto_file.is_file())
        self.assertTrue(report_file.is_file())

        # Category summaries
        cat_summaries = report['category_summaries']
        self.assertIn('visual_scene', cat_summaries)
        self.assertIn('visual_text_ja', cat_summaries)
        self.assertIn('visual_text_en', cat_summaries)

        self.assertEqual(cat_summaries['visual_scene']['queries'], 6)
        self.assertEqual(cat_summaries['visual_text_ja']['queries'], 5)
        self.assertEqual(cat_summaries['visual_text_en']['queries'], 2)

        self.assertEqual(report['overall_summary']['total_queries'], 13)
        self.assertIn('top1_mean', report['overall_summary'])
        self.assertIn('mrr_mean', report['overall_summary'])

        # Verify cases count
        self.assertEqual(len(report['cases']), 13)
        first_case = report['cases'][0]
        self.assertIn('ranked_keys', first_case)
        self.assertIn('hit_at_1', first_case)
        self.assertIn('mrr', first_case)


if __name__ == '__main__':
    unittest.main()
