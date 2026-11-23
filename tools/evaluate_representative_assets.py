"""Representative pseudo-doujinshi and visual-OCR evaluation harness.

Evaluates direct page search, in-image visual text recognition via EmbeddingGemma 2,
and optional WD pending-tag semantic search on fixed representative assets.

Accepts --zip <path>, --input-dir <path>, or --generate-placeholder for synthetic
CPU contract validation. Never claims placeholder runs are real model accuracy.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import statistics
import sys
import time
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'app'))
sys.path.insert(0, str(REPO / 'tools'))

from ai_process import EncoderProcess
from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch
from create_preview_fixture import png
from page_index import PageIndex
from production import ProductionCatalog
from search_quality import metrics
from tag_semantics import semantic_candidates
from tag_suggestions import TagSuggestions
from wd_tagger import create_tagger

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp')
MAX_ASSET_FILE_BYTES = 50 * 1024 * 1024  # 50 MB

CANONICAL_SPECS = {
    'bookA_p01': {
        'file': 'bookA_p01_cover.png',
        'group': 'bookA',
        'page': 0,
        'description': 'Spring cherry-blossom high school gate, black long-haired girl in navy sailor uniform (cover)'
    },
    'bookA_p02': {
        'file': 'bookA_p02_classroom.png',
        'group': 'bookA',
        'page': 1,
        'description': 'Sunset orange classroom, desk/chair by window and blackboard'
    },
    'bookA_p03': {
        'file': 'bookA_p03_library.png',
        'group': 'bookA',
        'page': 2,
        'description': 'Quiet library bookshelf, black-haired girl reading a thick book'
    },
    'bookA_p04': {
        'file': 'bookA_p04_rain.png',
        'group': 'bookA',
        'page': 3,
        'description': 'Rainy evening street corner, sailor-uniform girl holding a red umbrella'
    },
    'bookA_p05': {
        'file': 'bookA_p05_bubble_secret.png',
        'group': 'bookA',
        'page': 4,
        'description': 'Monochrome manga panel, speech bubble with text 『秘密のパスワード』'
    },
    'bookA_p06': {
        'file': 'bookA_p06_bubble_promise.png',
        'group': 'bookA',
        'page': 5,
        'description': 'Monochrome manga panel, speech bubble with text 『水曜日のプラネタリウム』'
    },
    'bookB_p01': {
        'file': 'bookB_p01_shrine.png',
        'group': 'bookB',
        'page': 0,
        'description': 'Red torii shrine grounds, black-haired ponytail shrine maiden (miko) in red/white attire'
    },
    'bookB_p02': {
        'file': 'bookB_p02_forest_magic.png',
        'group': 'bookB',
        'page': 1,
        'description': 'Night forest, silver/white-haired mage girl holding glowing blue magic circle and staff'
    },
    'bookB_p03': {
        'file': 'bookB_p03_chapter_title.png',
        'group': 'bookB',
        'page': 2,
        'description': 'Chapter title page with gothic text 『第三章　黄金の砂時計』'
    },
    'bookB_p04': {
        'file': 'bookB_p04_blackboard_text.png',
        'group': 'bookB',
        'page': 3,
        'description': 'Green blackboard close-up with white chalk text 『文化祭のカレーライス』'
    },
    'asset_01': {
        'file': 'asset_01_glasses_girl.png',
        'group': 'assets',
        'page': None,
        'description': 'White-haired bob-cut girl wearing red-framed glasses and white hoodie'
    },
    'asset_02': {
        'file': 'asset_02_neon_street.png',
        'group': 'assets',
        'page': None,
        'description': 'Cyberpunk alley after rain at night with glowing blue neon signs'
    },
    'asset_03': {
        'file': 'asset_03_signboard_onsen.png',
        'group': 'assets',
        'page': None,
        'description': 'White guide signboard against blue sky with black gothic text 『銀河ステーション行』'
    },
    'asset_04': {
        'file': 'asset_04_english_sign.png',
        'group': 'assets',
        'page': None,
        'description': 'White plate on brick wall with black alphabet text 『MIDNIGHT COFFEE SHOP』'
    },
}

EVALUATION_QUERIES = [
    # Category 1: visual_scene
    {
        'id': 'scene_01',
        'category': 'visual_scene',
        'query': '夕焼けの教室',
        'target_item': 'bookA',
        'expected_page': 1,
        'description': 'Sunset classroom (bookA p02)'
    },
    {
        'id': 'scene_02',
        'category': 'visual_scene',
        'query': '赤い傘 雨',
        'target_item': 'bookA',
        'expected_page': 3,
        'description': 'Red umbrella in rain (bookA p04)'
    },
    {
        'id': 'scene_03',
        'category': 'visual_scene',
        'query': '神社 巫女',
        'target_item': 'bookB',
        'expected_page': 0,
        'description': 'Shrine maiden at red torii (bookB p01)'
    },
    {
        'id': 'scene_04',
        'category': 'visual_scene',
        'query': '魔法陣 杖 白髪',
        'target_item': 'bookB',
        'expected_page': 1,
        'description': 'White-haired mage with magic circle and staff (bookB p02)'
    },
    {
        'id': 'scene_05',
        'category': 'visual_scene',
        'query': '白髪 赤い眼鏡 パーカー',
        'target_item': 'asset_01',
        'expected_page': None,
        'description': 'White-haired girl with red glasses and hoodie (asset_01)'
    },
    {
        'id': 'scene_06',
        'category': 'visual_scene',
        'query': 'サイバーパンク ネオン 路地裏',
        'target_item': 'asset_02',
        'expected_page': None,
        'description': 'Cyberpunk neon rain alley (asset_02)'
    },

    # Category 2: visual_text_ja (in-image text via EmbeddingGemma 2 without dedicated OCR)
    {
        'id': 'text_ja_01',
        'category': 'visual_text_ja',
        'query': '秘密のパスワード',
        'target_item': 'bookA',
        'expected_page': 4,
        'description': 'Speech bubble text 秘密のパスワード (bookA p05)'
    },
    {
        'id': 'text_ja_02',
        'category': 'visual_text_ja',
        'query': '水曜日のプラネタリウム',
        'target_item': 'bookA',
        'expected_page': 5,
        'description': 'Speech bubble text 水曜日のプラネタリウム (bookA p06)'
    },
    {
        'id': 'text_ja_03',
        'category': 'visual_text_ja',
        'query': '黄金の砂時計',
        'target_item': 'bookB',
        'expected_page': 2,
        'description': 'Chapter title 黄金の砂時計 (bookB p03)'
    },
    {
        'id': 'text_ja_04',
        'category': 'visual_text_ja',
        'query': '文化祭のカレーライス',
        'target_item': 'bookB',
        'expected_page': 3,
        'description': 'Blackboard text 文化祭のカレーライス (bookB p04)'
    },
    {
        'id': 'text_ja_05',
        'category': 'visual_text_ja',
        'query': '銀河ステーション',
        'target_item': 'asset_03',
        'expected_page': None,
        'description': 'Signboard text 銀河ステーション行 (asset_03)'
    },

    # Category 3: visual_text_en (English visual text & cross-lingual query)
    {
        'id': 'text_en_01',
        'category': 'visual_text_en',
        'query': 'MIDNIGHT COFFEE SHOP',
        'target_item': 'asset_04',
        'expected_page': None,
        'description': 'Verbatim sign text MIDNIGHT COFFEE SHOP (asset_04)'
    },
    {
        'id': 'text_en_02',
        'category': 'visual_text_en',
        'query': '深夜のコーヒーショップ',
        'target_item': 'asset_04',
        'expected_page': None,
        'description': 'Japanese meaning query for MIDNIGHT COFFEE SHOP (asset_04)'
    },
]

WD_TAG_QUERIES = [
    {
        'id': 'wd_01',
        'category': 'wd_tag_semantic',
        'query': 'セーラー服',
        'target_item': 'bookA',
        'description': 'Sailor uniform WD pending tags (bookA cover)'
    },
    {
        'id': 'wd_02',
        'category': 'wd_tag_semantic',
        'query': '巫女',
        'target_item': 'bookB',
        'description': 'Miko / shrine maiden WD pending tags (bookB cover)'
    },
    {
        'id': 'wd_03',
        'category': 'wd_tag_semantic',
        'query': '赤い眼鏡',
        'target_item': 'asset_01',
        'description': 'Red glasses girl WD pending tags (asset_01)'
    },
    {
        'id': 'wd_04',
        'category': 'wd_tag_semantic',
        'query': 'サイバーパンク',
        'target_item': 'asset_02',
        'description': 'Cyberpunk neon WD pending tags (asset_02)'
    },
]


def match_asset_key(filename):
    """Match a filename to one of the 14 canonical keys by exact name or prefix."""
    name_clean = Path(filename).name
    if name_clean.startswith('.') or name_clean.casefold() in ('thumbs.db', 'desktop.ini'):
        return None
    stem = Path(name_clean).stem.casefold()
    suffix = Path(name_clean).suffix.casefold()
    if suffix not in IMAGE_EXTENSIONS:
        return None
    # 1. Exact match against canonical filename
    for key, spec in CANONICAL_SPECS.items():
        if name_clean.casefold() == spec['file'].casefold():
            return key
    # 2. Match standard keys (e.g. booka_p01, asset_01)
    for key in CANONICAL_SPECS:
        k = key.casefold()
        if stem == k or stem.startswith(k + '_') or stem.startswith(k + '-') or stem.startswith(k + '.'):
            return key
    # 3. Flexible variants: bookA_p1, bookA_01, bookA_1, asset_1, asset01
    for key in CANONICAL_SPECS:
        m_book = re.fullmatch(r'(book[a-z])_p0?([1-9]\d*)', key, re.IGNORECASE)
        if m_book:
            b_pfx, p_num = m_book.group(1).casefold(), int(m_book.group(2))
            patterns = [
                f'{b_pfx}_p{p_num:02d}',
                f'{b_pfx}_p{p_num}',
                f'{b_pfx}_{p_num:02d}',
                f'{b_pfx}_{p_num}',
                f'{b_pfx}p{p_num:02d}',
                f'{b_pfx}p{p_num}',
            ]
            for pat in patterns:
                if stem == pat or stem.startswith(pat + '_') or stem.startswith(pat + '-') or stem.startswith(pat + '.'):
                    return key
        m_asset = re.fullmatch(r'asset_0?([1-9]\d*)', key, re.IGNORECASE)
        if m_asset:
            a_num = int(m_asset.group(1))
            patterns = [
                f'asset_{a_num:02d}',
                f'asset_{a_num}',
                f'asset{a_num:02d}',
                f'asset{a_num}',
            ]
            for pat in patterns:
                if stem == pat or stem.startswith(pat + '_') or stem.startswith(pat + '-') or stem.startswith(pat + '.'):
                    return key
    return None


def generate_placeholder_assets():
    """Deterministic synthetic PNGs for the 14 keys without imaging dependencies."""
    colors = [
        (60, 80, 160), (200, 100, 40), (40, 120, 80), (70, 70, 100),
        (220, 220, 220), (200, 200, 200), (180, 40, 40), (60, 140, 180),
        (30, 30, 30), (40, 90, 50), (150, 150, 180), (20, 40, 120),
        (90, 140, 200), (140, 100, 60)
    ]
    assets = {}
    for (key, spec), color in zip(CANONICAL_SPECS.items(), colors):
        assets[key] = {
            'data': png(width=200, height=200, color=color),
            'filename': spec['file'],
            'origin': 'placeholder',
        }
    return assets


def load_assets_from_zip(zip_path):
    """Safely extract the 14 assets from one or more zip archives."""
    if zip_path is None:
        raise ValueError('No zip archive specified')

    def _flatten(val):
        if isinstance(val, (str, Path)):
            yield Path(val)
        elif hasattr(val, '__iter__'):
            for item in val:
                yield from _flatten(item)
        elif val is not None:
            yield Path(val)

    paths = list(_flatten(zip_path))
    if not paths:
        raise ValueError('No zip archive specified')

    assets = {}
    for zp in paths:
        zp = zp.resolve()
        if not zp.is_file():
            raise FileNotFoundError(f'Zip archive not found: {zp}')
        with zipfile.ZipFile(zp, 'r') as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                name = info.filename
                if '..' in name or name.startswith(('/', '\\')):
                    raise ValueError(f'Path traversal in zip: {name}')
                if (info.external_attr >> 16) & 0o120000 == 0o120000:
                    raise ValueError(f'Symlinks rejected in zip: {name}')
                if info.file_size > MAX_ASSET_FILE_BYTES:
                    raise ValueError(f'File in zip exceeds 50MB: {name}')
                clean_name = Path(name).name
                if name.startswith('__MACOSX/') or clean_name.startswith('.'):
                    continue
                key = match_asset_key(name)
                if key is not None:
                    if key in assets:
                        raise ValueError(f'Duplicate file match for key {key}: {name} vs {assets[key]["origin"]}')
                    data = archive.read(info)
                    suffix = Path(name).suffix.casefold()
                    filename = Path(CANONICAL_SPECS[key]['file']).stem + suffix
                    assets[key] = {
                        'data': data,
                        'filename': filename,
                        'origin': f'{zp.name}:{name}' if len(paths) > 1 else name,
                    }
    missing = set(CANONICAL_SPECS) - set(assets)
    if missing:
        raise ValueError(f'Missing required assets in zip: {sorted(missing)}')
    return assets


def load_assets_from_dir(input_dir):
    """Safely load the 14 assets from a directory."""
    input_dir = Path(input_dir).resolve()
    if not input_dir.is_dir():
        raise FileNotFoundError(f'Input directory not found: {input_dir}')
    assets = {}
    for entry in input_dir.rglob('*'):
        if entry.is_symlink():
            raise ValueError(f'Symlink rejected: {entry}')
        if not entry.is_file():
            continue
        if entry.name.startswith('.') or entry.name.casefold() in ('thumbs.db', 'desktop.ini'):
            continue
        if entry.stat().st_size > MAX_ASSET_FILE_BYTES:
            raise ValueError(f'File exceeds 50MB: {entry.name}')
        key = match_asset_key(entry.name)
        if key is not None:
            if key in assets:
                raise ValueError(f'Duplicate file match for key {key}: {entry} vs {assets[key]["origin"]}')
            suffix = entry.suffix.casefold()
            filename = Path(CANONICAL_SPECS[key]['file']).stem + suffix
            assets[key] = {
                'data': entry.read_bytes(),
                'filename': filename,
                'origin': str(entry),
            }
    missing = set(CANONICAL_SPECS) - set(assets)
    if missing:
        raise ValueError(f'Missing required assets in directory: {sorted(missing)}')
    return assets


def build_evaluation_library(output_dir, asset_data):
    """Create books_cbz/bookA.cbz, books_folder/bookB/, and assets/ in output_dir."""
    output_dir = Path(output_dir).resolve()
    books_cbz_dir = output_dir / 'books_cbz'
    books_folder_dir = output_dir / 'books_folder'
    assets_dir = output_dir / 'assets'

    books_cbz_dir.mkdir(parents=True, exist_ok=False)
    books_folder_dir.mkdir(parents=True, exist_ok=False)
    assets_dir.mkdir(parents=True, exist_ok=False)

    # 1. bookA.cbz containing bookA_p01..bookA_p06
    bookA_keys = ['bookA_p01', 'bookA_p02', 'bookA_p03', 'bookA_p04', 'bookA_p05', 'bookA_p06']
    with zipfile.ZipFile(books_cbz_dir / 'bookA.cbz', 'w') as bookA_zip:
        for key in bookA_keys:
            fname = asset_data[key]['filename']
            bookA_zip.writestr(fname, asset_data[key]['data'])

    # 2. books_folder/bookB/ containing bookB_p01..bookB_p04
    bookB_dir = books_folder_dir / 'bookB'
    bookB_dir.mkdir(parents=True, exist_ok=False)
    bookB_keys = ['bookB_p01', 'bookB_p02', 'bookB_p03', 'bookB_p04']
    for key in bookB_keys:
        fname = asset_data[key]['filename']
        (bookB_dir / fname).write_bytes(asset_data[key]['data'])

    # 3. assets/ containing asset_01..asset_04
    asset_keys = ['asset_01', 'asset_02', 'asset_03', 'asset_04']
    for key in asset_keys:
        fname = asset_data[key]['filename']
        (assets_dir / fname).write_bytes(asset_data[key]['data'])

    return {
        'cbz_dir': books_cbz_dir,
        'folder_dir': books_folder_dir,
        'assets_dir': assets_dir,
    }


def evaluate(output_dir, assets=None, zip_path=None, input_dir=None,
             generate_placeholder=False, encoder=None, tagger=None, skip_wd=False):
    """Run full evaluation suite over representative assets."""
    output_dir = Path(output_dir).resolve()
    allowed = (REPO / 'data/representative-eval').resolve()
    if not output_dir.is_relative_to(allowed) or output_dir == allowed:
        raise ValueError('Fresh output directory must be below project data/representative-eval')

    if assets is None:
        if generate_placeholder:
            assets = generate_placeholder_assets()
        elif zip_path:
            assets = load_assets_from_zip(zip_path)
        elif input_dir:
            assets = load_assets_from_dir(input_dir)
        else:
            raise ValueError('One of assets, zip_path, input_dir, or generate_placeholder must be specified')

    output_dir.mkdir(parents=True, exist_ok=False)
    lib = build_evaluation_library(output_dir, assets)

    # Save frozen protocol
    protocol = {
        'canonical_specs': CANONICAL_SPECS,
        'evaluation_queries': EVALUATION_QUERIES,
        'wd_tag_queries': WD_TAG_QUERIES,
        'library_layout': {
            'bookA': 'books_cbz/bookA.cbz (pages 0..5)',
            'bookB': 'books_folder/bookB/ (pages 0..3, folder_books=True)',
            'assets': 'assets/ (standalone images asset_01..asset_04)',
        },
        'scoring': 'Top1, Recall@3, Recall@5, MRR, exact_page_at_1',
    }
    raw_proto = json.dumps(protocol, ensure_ascii=False, indent=2, sort_keys=True).encode('utf-8')
    (output_dir / 'frozen-protocol.json').write_bytes(raw_proto)

    catalog = None
    ai = None
    tagger_to_close = None
    report = None

    try:
        catalog = ProductionCatalog(output_dir / 'catalog.sqlite')
        root_cbz = catalog.add_root(str(lib['cbz_dir']))
        root_folder = catalog.add_root(str(lib['folder_dir']), folder_books=True)
        root_assets = catalog.add_root(str(lib['assets_dir']))

        catalog.index.scan(root_cbz)
        catalog.index.scan(root_folder)
        catalog.index.scan(root_assets)
        catalog.sync_index()

        scope = {'root_ids': [root_cbz, root_folder, root_assets]}

        # Map catalog items to target keys
        items_raw = catalog.search(limit=60)['items']
        id_to_key = {}
        key_to_item = {}
        for item in items_raw:
            title = item['title']
            if title in ('bookA.cbz', 'bookA'):
                key = 'bookA'
            elif title == 'bookB':
                key = 'bookB'
            else:
                match = match_asset_key(title)
                key = match if match else title
            id_to_key[item['id']] = key
            key_to_item[key] = item

        expected_catalog_keys = {'bookA', 'bookB', 'asset_01', 'asset_02', 'asset_03', 'asset_04'}
        missing_catalog = expected_catalog_keys - set(key_to_item)
        if missing_catalog:
            raise RuntimeError(f'Required items missing from catalog scan: {sorted(missing_catalog)}')

        actual_encoder = encoder is None
        encoder_to_close = None
        if encoder is None:
            encoder = EncoderProcess(REPO / '.venv-ai/Scripts/python.exe', DEFAULT_PROFILE.model_path(REPO))
            encoder_to_close = encoder
        ai = AISearch(catalog, encoder)

        report = {
            'passed': False,
            'synthetic_placeholder': bool(generate_placeholder),
            'protocol_sha256': hashlib.sha256(raw_proto).hexdigest(),
            'profile': ai.profile.identity(),
            'device': getattr(encoder, 'device', '') or 'cpu',
            'catalog_items': len(items_raw),
            'cases': [],
            'category_summaries': {},
            'overall_summary': {},
            'wd_tag_evaluation': {'enabled': False, 'reason': ''},
        }

        # 1. Build normal AI cover index
        start_cover = time.perf_counter()
        ai.start(scope=scope)
        ai.worker.join(240)
        if ai.worker.is_alive() or ai.status()['state'] != 'complete':
            raise RuntimeError('Cover index build failed or timed out')
        report['cover_index_seconds'] = round(time.perf_counter() - start_cover, 3)
        report['device'] = getattr(encoder, 'device', '') or 'cpu'

        # 2. Build internal book page index
        start_pages = time.perf_counter()
        pindex = PageIndex(catalog)
        for book_key in ('bookA', 'bookB'):
            if book_key not in key_to_item:
                continue
            item_id = key_to_item[book_key]['id']
            pindex.refresh(item_id)
            snapshot = pindex.list(item_id)
            page_ids = [p['page_id'] for p in snapshot['pages']]
            if len(page_ids) <= 16:
                ai.pages.start(item_id, page_ids, snapshot['source_revision'], scope)
            else:
                ai.pages.start_chunked(item_id, page_ids, snapshot['source_revision'], scope)
            ai.worker.join(240)
            if ai.worker.is_alive() or ai.status()['state'] != 'complete':
                raise RuntimeError(f'Page index build failed for {book_key}')
        report['page_index_seconds'] = round(time.perf_counter() - start_pages, 3)

        # 3. Optional WD tagger proposals
        active_tagger = tagger
        if active_tagger is None and not skip_wd:
            active_tagger = create_tagger()
            tagger_to_close = active_tagger
        suggestions = None
        if active_tagger and active_tagger.status()['available']:
            report['wd_tag_evaluation']['enabled'] = True
            suggestions = TagSuggestions(catalog, adapter=active_tagger)
            generated_tags = {}
            for item in items_raw:
                gen_res = suggestions.generate(item['id'], secrets.token_hex(16))
                k = id_to_key.get(item['id'], str(item['id']))
                batch = gen_res.get('batch') or {}
                proposals = batch.get('proposals', [])
                generated_tags[k] = [p['tag'] for p in proposals]
            report['wd_tag_evaluation']['generated_tags'] = generated_tags
            # Refresh pending tag vectors
            ai.start(scope=scope)
            ai.worker.join(240)
            if ai.worker.is_alive() or ai.status()['state'] != 'complete':
                raise RuntimeError('Pending tag index build failed or timed out')
        else:
            reason = 'WD tagger skipped via flag' if skip_wd else (active_tagger.status().get('reason', '') if active_tagger else 'WD tagger not initialized')
            report['wd_tag_evaluation']['reason'] = reason

        # 4. Evaluate main queries
        all_cases = []
        for q in EVALUATION_QUERIES:
            target = q['target_item']
            exp_page = q.get('expected_page')

            # Cover mode
            res = ai.search(q['query'], source='cover', scope=scope)
            ranked_items = res['items']
            ranked_keys = [id_to_key.get(r['id'], str(r['id'])) for r in ranked_items]

            hit_1 = bool(ranked_keys and ranked_keys[0] == target)
            rec_3 = float(target in ranked_keys[:3])
            rec_5 = float(target in ranked_keys[:5])
            rank = (ranked_keys.index(target) + 1) if target in ranked_keys else None
            mrr = (1.0 / rank) if rank else 0.0

            target_row = next((r for r in ranked_items if id_to_key.get(r['id']) == target), None)
            actual_page = (target_row.get('ai_page_match') or {}).get('page') if target_row else None
            target_score = target_row.get('semantic_score') if target_row else None

            exact_page = (actual_page == exp_page) if exp_page is not None else True
            exact_page_at_1 = bool(hit_1 and exact_page)

            # Combined mode
            res_comb = ai.search(q['query'], source='all', scope=scope)
            ranked_items_comb = res_comb['items']
            ranked_keys_comb = [id_to_key.get(r['id'], str(r['id'])) for r in ranked_items_comb]

            hit_1_comb = bool(ranked_keys_comb and ranked_keys_comb[0] == target)
            rec_3_comb = float(target in ranked_keys_comb[:3])
            rec_5_comb = float(target in ranked_keys_comb[:5])
            rank_comb = (ranked_keys_comb.index(target) + 1) if target in ranked_keys_comb else None
            mrr_comb = (1.0 / rank_comb) if rank_comb else 0.0

            target_row_comb = next((r for r in ranked_items_comb if id_to_key.get(r['id']) == target), None)
            actual_page_comb = (target_row_comb.get('ai_page_match') or {}).get('page') if target_row_comb else None
            target_score_comb = target_row_comb.get('semantic_score') if target_row_comb else None

            exact_page_comb = (actual_page_comb == exp_page) if exp_page is not None else True
            exact_page_at_1_comb = bool(hit_1_comb and exact_page_comb)

            case_result = {
                'id': q['id'],
                'category': q['category'],
                'query': q['query'],
                'target_item': target,
                'expected_page': exp_page,
                'ranked_keys': ranked_keys,
                'target_rank': rank,
                'target_score': target_score,
                'hit_at_1': hit_1,
                'recall_at_3': rec_3,
                'recall_at_5': rec_5,
                'mrr': mrr,
                'actual_page': actual_page,
                'exact_page_hit': exact_page,
                'exact_page_at_1': exact_page_at_1,
                'combined': {
                    'ranked_keys': ranked_keys_comb,
                    'target_rank': rank_comb,
                    'target_score': target_score_comb,
                    'hit_at_1': hit_1_comb,
                    'recall_at_3': rec_3_comb,
                    'recall_at_5': rec_5_comb,
                    'mrr': mrr_comb,
                    'actual_page': actual_page_comb,
                    'exact_page_hit': exact_page_comb,
                    'exact_page_at_1': exact_page_at_1_comb,
                }
            }
            all_cases.append(case_result)
        report['cases'] = all_cases

        # 5. Evaluate WD tag queries if available
        wd_cases = []
        if report['wd_tag_evaluation']['enabled']:
            for q in WD_TAG_QUERIES:
                c_res = semantic_candidates(suggestions, ai, query=q['query'], root_ids=scope['root_ids'])
                ranked_items_wd = c_res['items']
                ranked_keys = [id_to_key.get(r['id'], str(r['id'])) for r in ranked_items_wd]
                target = q['target_item']
                hit_1 = bool(ranked_keys and ranked_keys[0] == target)
                rec_3 = float(target in ranked_keys[:3])
                rec_5 = float(target in ranked_keys[:5])
                rank = (ranked_keys.index(target) + 1) if target in ranked_keys else None
                mrr = (1.0 / rank) if rank else 0.0

                target_row_wd = next((r for r in ranked_items_wd if id_to_key.get(r['id']) == target), None)
                target_score_wd = target_row_wd.get('semantic_score') if target_row_wd else None

                wd_cases.append({
                    'id': q['id'],
                    'category': q['category'],
                    'query': q['query'],
                    'target_item': target,
                    'ranked_keys': ranked_keys,
                    'target_rank': rank,
                    'target_score': target_score_wd,
                    'hit_at_1': hit_1,
                    'recall_at_3': rec_3,
                    'recall_at_5': rec_5,
                    'mrr': mrr,
                })
            report['wd_cases'] = wd_cases

        # 6. Compute Category Summaries
        categories = sorted(list({c['category'] for c in all_cases}))
        cat_summaries = {}
        for cat in categories:
            cat_cases = [c for c in all_cases if c['category'] == cat]
            cat_summaries[cat] = {
                'queries': len(cat_cases),
                'top1_mean': round(statistics.mean(c['hit_at_1'] for c in cat_cases), 4),
                'recall3_mean': round(statistics.mean(c['recall_at_3'] for c in cat_cases), 4),
                'recall5_mean': round(statistics.mean(c['recall_at_5'] for c in cat_cases), 4),
                'mrr_mean': round(statistics.mean(c['mrr'] for c in cat_cases), 4),
                'exact_page_at_1_mean': round(statistics.mean(c['exact_page_at_1'] for c in cat_cases), 4),
                'combined_top1_mean': round(statistics.mean(c['combined']['hit_at_1'] for c in cat_cases), 4),
                'combined_recall3_mean': round(statistics.mean(c['combined']['recall_at_3'] for c in cat_cases), 4),
                'combined_recall5_mean': round(statistics.mean(c['combined']['recall_at_5'] for c in cat_cases), 4),
                'combined_mrr_mean': round(statistics.mean(c['combined']['mrr'] for c in cat_cases), 4),
                'combined_exact_page_at_1_mean': round(statistics.mean(c['combined']['exact_page_at_1'] for c in cat_cases), 4),
            }
        if wd_cases:
            cat_summaries['wd_tag_semantic'] = {
                'queries': len(wd_cases),
                'top1_mean': round(statistics.mean(c['hit_at_1'] for c in wd_cases), 4),
                'recall3_mean': round(statistics.mean(c['recall_at_3'] for c in wd_cases), 4),
                'recall5_mean': round(statistics.mean(c['recall_at_5'] for c in wd_cases), 4),
                'mrr_mean': round(statistics.mean(c['mrr'] for c in wd_cases), 4),
            }
        report['category_summaries'] = cat_summaries

        all_eval_cases = all_cases + wd_cases
        report['overall_summary'] = {
            'total_queries': len(all_eval_cases),
            'top1_mean': round(statistics.mean(c['hit_at_1'] for c in all_eval_cases), 4),
            'recall3_mean': round(statistics.mean(c['recall_at_3'] for c in all_eval_cases), 4),
            'recall5_mean': round(statistics.mean(c['recall_at_5'] for c in all_eval_cases), 4),
            'mrr_mean': round(statistics.mean(c['mrr'] for c in all_eval_cases), 4),
            'combined_top1_mean': round(statistics.mean((c.get('combined') or c)['hit_at_1'] for c in all_eval_cases), 4),
            'combined_recall3_mean': round(statistics.mean((c.get('combined') or c)['recall_at_3'] for c in all_eval_cases), 4),
            'combined_recall5_mean': round(statistics.mean((c.get('combined') or c)['recall_at_5'] for c in all_eval_cases), 4),
            'combined_mrr_mean': round(statistics.mean((c.get('combined') or c)['mrr'] for c in all_eval_cases), 4),
        }
        report['passed'] = True
    except Exception as ex:
        if report is not None:
            report['error'] = f'{type(ex).__name__}: {ex}'
        raise
    finally:
        if tagger_to_close is not None:
            try: tagger_to_close.close()
            except Exception: pass
        if ai is not None:
            try: ai.close()
            except Exception: pass
        elif encoder_to_close is not None:
            try: encoder_to_close.close()
            except Exception: pass
        if catalog is not None:
            try: catalog.close()
            except Exception: pass
        if report is not None and output_dir.is_dir():
            try:
                (output_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            except Exception: pass

    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--zip', type=Path, action='extend', nargs='+', help='Path(s) to zip archive(s) containing evaluation images')
    group.add_argument('--input-dir', type=Path, help='Path to directory containing 14 images')
    group.add_argument('--generate-placeholder', action='store_true', help='Use synthetic placeholder images')
    parser.add_argument('--output', type=Path, help='Output directory under data/representative-eval')
    parser.add_argument('--skip-wd', action='store_true', help='Skip WD tag suggestion generation/search')
    args = parser.parse_args()

    if args.output:
        output_dir = args.output
    else:
        timestamp = time.strftime('%Y%m%d-%H%M%S')
        output_dir = REPO / f'data/representative-eval/run-{timestamp}'

    report = evaluate(
        output_dir=output_dir,
        zip_path=args.zip,
        input_dir=args.input_dir,
        generate_placeholder=args.generate_placeholder,
        skip_wd=args.skip_wd,
    )
    print(json.dumps({
        'passed': report['passed'],
        'output_dir': str(output_dir),
        'synthetic_placeholder': report['synthetic_placeholder'],
        'device': report['device'],
        'category_summaries': report['category_summaries'],
        'overall_summary': report['overall_summary'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
