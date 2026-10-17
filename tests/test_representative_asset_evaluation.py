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


class MockTagger:
    def __init__(self):
        from tag_suggestions import TaggerInfo
        self.info = TaggerInfo('mock-wd', '1.0', 'mock-wd-model', 'rev1', 'preprocessing1')
        self._available = True
        self.closed = False

    def status(self):
        return {'available': self._available, 'reason': '', 'profile': 'mock', 'device': 'cpu'}

    def suggest(self, source, cancelled):
        from tag_suggestions import TagProposal
        return [
            TagProposal('sailor_uniform', 'mock proposal'),
            TagProposal('miko', 'mock proposal'),
            TagProposal('glasses', 'mock proposal'),
            TagProposal('cyberpunk', 'mock proposal'),
        ]

    def close(self):
        self.closed = True


class RepresentativeAssetEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='aredoko-test-rep-')
        self.output_base = ROOT / 'data/representative-eval'
        self.output_base.mkdir(parents=True, exist_ok=True)
        self.run_dir = self.output_base / f'test-run-{Path(self.temp_dir).name}'
        self.run_dir_wd = self.output_base / f'test-run-wd-{Path(self.temp_dir).name}'

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.run_dir, ignore_errors=True)
        shutil.rmtree(self.run_dir_wd, ignore_errors=True)

    def test_asset_key_matching_exact_prefix_and_case_insensitive(self):
        self.assertEqual(match_asset_key('bookA_p01_cover.png'), 'bookA_p01')
        self.assertEqual(match_asset_key('BOOKA_P02_CLASSROOM.PNG'), 'bookA_p02')
        self.assertEqual(match_asset_key('bookB_p03_chapter.webp'), 'bookB_p03')
        self.assertEqual(match_asset_key('asset_04_anything.jpg'), 'asset_04')
        self.assertEqual(match_asset_key('asset_01.png'), 'asset_01')

        # Flexible variants (bookA_p1, bookA_01, asset_1, asset01)
        self.assertEqual(match_asset_key('bookA_p1_cover.png'), 'bookA_p01')
        self.assertEqual(match_asset_key('bookA_01_cover.png'), 'bookA_p01')
        self.assertEqual(match_asset_key('bookA_1_cover.png'), 'bookA_p01')
        self.assertEqual(match_asset_key('bookA_p6.png'), 'bookA_p06')
        self.assertEqual(match_asset_key('bookB_p1.png'), 'bookB_p01')
        self.assertEqual(match_asset_key('bookB_4.png'), 'bookB_p04')
        self.assertEqual(match_asset_key('asset_1.png'), 'asset_01')
        self.assertEqual(match_asset_key('asset01.png'), 'asset_01')
        self.assertEqual(match_asset_key('asset_4_english_sign.png'), 'asset_04')

        # macOS resource forks and dotfiles rejected
        self.assertIsNone(match_asset_key('._bookA_p01_cover.png'))
        self.assertIsNone(match_asset_key('.DS_Store'))
        self.assertIsNone(match_asset_key('Thumbs.db'))

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

        # 3. Valid zip with all 14 images + macosx dotfiles (skipped safely)
        placeholders = generate_placeholder_assets()
        good_zip = Path(self.temp_dir) / 'valid_14.zip'
        with zipfile.ZipFile(good_zip, 'w') as zf:
            zf.writestr('__MACOSX/._bookA_p01_cover.png', b'mac resource fork')
            zf.writestr('.DS_Store', b'mac metadata')
            for key, p in placeholders.items():
                zf.writestr(p['filename'], p['data'])
        loaded_zip = load_assets_from_zip(good_zip)
        self.assertEqual(set(loaded_zip.keys()), set(CANONICAL_SPECS.keys()))

        # 3b. Valid split across multiple zips (8 + 6)
        keys_list = list(CANONICAL_SPECS.keys())
        keys_8, keys_6 = keys_list[:8], keys_list[8:]
        zip_8 = Path(self.temp_dir) / 'split_8.zip'
        zip_6 = Path(self.temp_dir) / 'split_6.zip'
        with zipfile.ZipFile(zip_8, 'w') as zf:
            for k in keys_8:
                zf.writestr(placeholders[k]['filename'], placeholders[k]['data'])
        with zipfile.ZipFile(zip_6, 'w') as zf:
            for k in keys_6:
                zf.writestr(placeholders[k]['filename'], placeholders[k]['data'])
        loaded_multi = load_assets_from_zip([zip_8, zip_6])
        self.assertEqual(set(loaded_multi.keys()), set(CANONICAL_SPECS.keys()))
        self.assertTrue(loaded_multi[keys_8[0]]['origin'].startswith('split_8.zip:'))
        self.assertTrue(loaded_multi[keys_6[0]]['origin'].startswith('split_6.zip:'))

        # 3c. Duplicate across multiple zips rejected
        dup_zip = Path(self.temp_dir) / 'dup.zip'
        with zipfile.ZipFile(dup_zip, 'w') as zf:
            zf.writestr(placeholders[keys_8[0]]['filename'], placeholders[keys_8[0]]['data'])
        with self.assertRaises(ValueError) as ctx:
            load_assets_from_zip([zip_8, dup_zip])
        self.assertIn('Duplicate file match', str(ctx.exception))

        # 4. Valid dir with nested folders
        nested_dir = Path(self.temp_dir) / 'nested_dir'
        sub = nested_dir / 'subfolder'
        sub.mkdir(parents=True)
        (nested_dir / '.DS_Store').write_bytes(b'dummy')
        for key, p in placeholders.items():
            (sub / p['filename']).write_bytes(p['data'])
        loaded_dir = load_assets_from_dir(nested_dir)
        self.assertEqual(set(loaded_dir.keys()), set(CANONICAL_SPECS.keys()))

        # 5. Oversized file in zip rejected
        big_file = Path(self.temp_dir) / 'big.png'
        with open(big_file, 'wb') as f:
            f.seek(51 * 1024 * 1024)
            f.write(b'x')
        oversized_zip = Path(self.temp_dir) / 'oversized.zip'
        with zipfile.ZipFile(oversized_zip, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(big_file, arcname='bookA_p01_cover.png')
        with self.assertRaises(ValueError) as ctx:
            load_assets_from_zip(oversized_zip)
        self.assertIn('exceeds 50MB', str(ctx.exception))

        # 6. Oversized file in dir rejected
        oversized_dir = Path(self.temp_dir) / 'oversized_dir'
        oversized_dir.mkdir()
        shutil.copy(big_file, oversized_dir / 'asset_01.png')
        with self.assertRaises(ValueError) as ctx:
            load_assets_from_dir(oversized_dir)
        self.assertIn('File exceeds 50MB', str(ctx.exception))

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
        self.assertIn('combined_top1_mean', cat_summaries['visual_scene'])

        self.assertEqual(report['overall_summary']['total_queries'], 13)
        self.assertIn('top1_mean', report['overall_summary'])
        self.assertIn('mrr_mean', report['overall_summary'])
        self.assertIn('combined_top1_mean', report['overall_summary'])

        # Verify cases count and combined details
        self.assertEqual(len(report['cases']), 13)
        first_case = report['cases'][0]
        self.assertIn('ranked_keys', first_case)
        self.assertIn('hit_at_1', first_case)
        self.assertIn('mrr', first_case)
        self.assertIn('combined', first_case)
        self.assertIn('hit_at_1', first_case['combined'])

    def test_evaluate_synthetic_placeholder_with_mock_wd(self):
        encoder = MockEncoder()
        tagger = MockTagger()
        report = evaluate(
            output_dir=self.run_dir_wd,
            generate_placeholder=True,
            encoder=encoder,
            tagger=tagger,
            skip_wd=False,
        )

        self.assertTrue(report['passed'])
        self.assertTrue(report['wd_tag_evaluation']['enabled'])
        self.assertEqual(len(report['wd_cases']), 4)
        self.assertIn('wd_tag_semantic', report['category_summaries'])
        self.assertEqual(report['category_summaries']['wd_tag_semantic']['queries'], 4)
        # Total queries now includes WD queries consistently
        self.assertEqual(report['overall_summary']['total_queries'], 17)
        self.assertIn('generated_tags', report['wd_tag_evaluation'])
        self.assertEqual(len(report['wd_tag_evaluation']['generated_tags']), 6)

    def test_evaluate_invalid_output_directory_rejected(self):
        bad_output = ROOT / 'data/other_unauthorized_dir'
        with self.assertRaises(ValueError) as ctx:
            evaluate(
                output_dir=bad_output,
                generate_placeholder=True,
                encoder=MockEncoder(),
                skip_wd=True,
            )
        self.assertIn('Fresh output directory must be below', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
