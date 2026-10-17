# 代表的疑似同人誌・画像内文字認識（Visual-OCR）評価

> **combinedの後続改善（2026-10-17）**：下の58.82%等は旧等重みRRFの観測値。新しい固定質問で検証したスコア幅重み付きRRFを採用し、直接視覚13問は7/13→13/13、新しい正解あり22問は16/22→20/22、旧Top1正解の悪化0。[方式・新旧評価・残失敗](combined-fusion-evaluation.md)。元17問には別のWD4問を含むため、今回RRF比較13問と混ぜない。元reportは変更せずWD再推論もしていない。OCR保留を維持。

## 目的

本書は、EmbeddingGemma 2による**本文ページの直接画像embedding検索**、画像内に描かれた文字（フキダシ・章扉・黒板・看板・英語プレート）の**直接文字認識（専用OCRなしでの検索）**、およびWD taggerによる**未承認WD英語タグに対する日本語意味検索**の評価手順・素材仕様・計測ツールを定義する。

ユーザー確定方針に基づき、専用OCRの導入は**本代表素材を用いた直接画像・本文ページ検索を評価し、見落とし（検索漏れ）が多く確認された場合のみ検討**する。

---

## 1. 評価用14素材の定義

素材は14枚の画像から構成され、CBZ書庫本（1冊）、画像フォルダ本（1冊）、および単体画像アセット（4点）として独立したライブラリへ登録される。

| ファイル名 / キー | 役割・種別 | 描画内容・目的 |
|---|---|---|
| `bookA_p01_cover.png` | `bookA` 表紙 (page 0) | 桜咲く高校校門、黒髪ロングのセーラー服女子（表紙） |
| `bookA_p02_classroom.png` | `bookA` 本文 (page 1) | 夕焼けの教室、窓際の机と椅子、黒板 |
| `bookA_p03_library.png` | `bookA` 本文 (page 2) | 静かな図書館の本棚、分厚い本を読む黒髪女子 |
| `bookA_p04_rain.png` | `bookA` 本文 (page 3) | 雨の夕暮れの街角、赤い傘を差したセーラー服女子 |
| `bookA_p05_bubble_secret.png` | `bookA` 本文 (page 4) | モノクロ漫画コマ、白背景、驚く黒髪女子アップ、フキダシ文字『秘密のパスワード』（PC/鍵等の物体描画なし） |
| `bookA_p06_bubble_promise.png` | `bookA` 本文 (page 5) | モノクロ漫画コマ、眼鏡女子バストアップ・集中線、フキダシ文字『水曜日のプラネタリウム』（星/ドーム描画なし） |
| `bookB_p01_shrine.png` | `bookB` 表紙 (page 0) | 赤い鳥居の境内、赤白巫女装束の黒髪ポニーテール巫女 |
| `bookB_p02_forest_magic.png` | `bookB` 本文 (page 1) | 夜の森、青く光る魔法陣と杖を構える銀髪/白髪の魔女 |
| `bookB_p03_chapter_title.png` | `bookB` 本文 (page 2) | 黒枠装飾の章扉、ゴシック体『第三章　黄金の砂時計』（砂時計の絵なし） |
| `bookB_p04_blackboard_text.png` | `bookB` 本文 (page 3) | 緑の黒板アップ、白チョーク文字『文化祭のカレーライス』（料理/人物描画なし） |
| `asset_01_glasses_girl.png` | 単体アセット | 白髪ボブカット、赤フレーム眼鏡、白パーカー女子（立ち絵） |
| `asset_02_neon_street.png` | 単体アセット | 雨上がりの夜のサイバーパンク路地裏、青く光るネオン看板（人物なし） |
| `asset_03_signboard_onsen.png` | 単体アセット | 青空を背景にした白い案内看板、黒ゴシック体『銀河ステーション行』（電車/宇宙描画なし） |
| `asset_04_english_sign.png` | 単体アセット | レンガ壁の白プレート、黒アルファベット『MIDNIGHT COFFEE SHOP』（コーヒーカップ描画なし） |

---

## 2. ライブラリ構成と登録仕様

評価ツール（`tools/evaluate_representative_assets.py`）は、指定されたZIPまたは入力フォルダから14枚を検出し、`data/representative-eval/<run>/` 配下に以下の構造で隔離ライブラリを自動構築する：

1. `books_cbz/bookA.cbz`：
   - 内部に `bookA_p01`〜`bookA_p06` を自然順（natural sort）で格納（page 0〜5）。
   - 通常の書庫ルート（`folder_books=False`）として登録。
2. `books_folder/bookB/`：
   - フォルダ内に `bookB_p01`〜`bookB_p04` を格納（page 0〜3）。
   - フォルダ本ルート（`folder_books=True`）として登録。
3. `assets/`：
   - `asset_01`〜`asset_04` を格納。
   - 通常の画像ルートとして登録。

---

## 3. 評価クエリと採点基準

### カテゴリ 1: `visual_scene`（視覚的情景・人物の直接検索）
- 「夕焼けの教室」 → 期待正解: `bookA` (page 1, `bookA_p02`)
- 「赤い傘 雨」 → 期待正解: `bookA` (page 3, `bookA_p04`)
- 「神社 巫女」 → 期待正解: `bookB` (page 0, `bookB_p01`)
- 「魔法陣 杖 白髪」 → 期待正解: `bookB` (page 1, `bookB_p02`)
- 「白髪 赤い眼鏡 パーカー」 → 期待正解: `asset_01`
- 「サイバーパンク ネオン 路地裏」 → 期待正解: `asset_02`

### カテゴリ 2: `visual_text_ja`（画像内日本語文字の直接認識・非OCR）
絵柄ではなく、画像内に書かれた日本語テキストを手がかりに検索可能かを検証する：
- 「秘密のパスワード」 → 期待正解: `bookA` (page 4, `bookA_p05`)
- 「水曜日のプラネタリウム」 → 期待正解: `bookA` (page 5, `bookA_p06`)
- 「黄金の砂時計」 → 期待正解: `bookB` (page 2, `bookB_p03`)
- 「文化祭のカレーライス」 → 期待正解: `bookB` (page 3, `bookB_p04`)
- 「銀河ステーション」 → 期待正解: `asset_03`

### カテゴリ 3: `visual_text_en`（画像内英語文字の直接認識および日英意味検索）
- 「MIDNIGHT COFFEE SHOP」 → 期待正解: `asset_04`（英字そのままの検索）
- 「深夜のコーヒーショップ」 → 期待正解: `asset_04`（日本語の意味検索によるクロスリンガル合致）

### カテゴリ 4: `wd_tag_semantic`（未承認WD英語タグに対する日本語意味検索）
WD taggerが有効な場合、生成された英語タグ候補（`ai.pending_tags`）に対して日本語クエリで検索：
- 「セーラー服」 → `bookA`
- 「巫女」 → `bookB`
- 「赤い眼鏡」 → `asset_01`
- 「サイバーパンク」 → `asset_02`

### 採点指標
- **Top1 Hit Rate**：最上位に正解作品がヒットした割合。
- **Recall@3 / Recall@5**：上位3件/5件以内に正解が含まれる割合。
- **MRR (Mean Reciprocal Rank)**：正解の順位の逆数平均。
- **Exact Page Hit @ 1**：本の内部ページをターゲットとするクエリにおいて、Top1作品の一致ページ（`ai_page_match.page`）が期待ページと完全に一致した割合。

---

## 4. 実行コマンド

### 合成プレースホルダーによる高速契約検証（CPU、モデルロードなし）
```powershell
python tools/evaluate_representative_assets.py --generate-placeholder --skip-wd
```

### 実素材ZIP（複数ZIP対応）での実行
```powershell
# 単一ZIP
.venv-ai\Scripts\python.exe tools/evaluate_representative_assets.py --zip path/to/assets.zip

# 複数ZIP（分割ZIPの自動マージ）
.venv-ai\Scripts\python.exe tools/evaluate_representative_assets.py --zip C:\AI\Aredoko-test\Aredoko_search_test_images_8.zip C:\AI\Aredoko-test\Aredoko_text_recognition_test_images_6.zip --output data/representative-eval/real-v1-20261017
```

### 実素材フォルダからの実行
```powershell
.venv-ai\Scripts\python.exe tools/evaluate_representative_assets.py --input-dir path/to/assets_dir
```

---

## 5. 安全性・境界と注意事項

- プレースホルダー実行（`--generate-placeholder`）は、コード契約・ライブラリ構築・パイプライン整合を検証する合成テストであり、**実モデルの検索精度や文字認識能力を主張するものではない**。
- 素材読み込み時は、パストラバーサル（`..`）、絶対パス、シンボリックリンク、50MB超の過大ファイルを厳格に拒絶する。macOSリソースフォーク（`__MACOSX/`）、隠しファイル（`.*`）、`Thumbs.db`は安全に無視される。
- ファイル名照合は正規名（`bookA_p01_cover.png`）に加え、一般的な番号ゆらぎ（`bookA_p1`, `bookA_01`, `bookA_1`, `asset_1`, `asset01`等）および大文字小文字の違いに柔軟に対応する。
- `--input-dir` は展開後のネストされたサブディレクトリも再帰的に走査して素材を検出する。
- 本文ページ索引は、16ページ以下の場合は既存の16ページ原子的トランザクション（`start`）、16ページ超の場合は分割トランザクション（`start_chunked`）を自動適用し、版・プロファイル束縛と中断時保護を厳格に維持する。

---

## 6. 実モデル（EmbeddingGemma 2 + WD Tagger）実機評価結果（2026-10-17）

- **実行環境**: CUDA (`device: "cuda"`), Google EmbeddingGemma 2 (`google/embeddinggemma-2`, 768D auto-bf16), WD Tagger (`wd-swinv2-v3` CPU).
- **出力ディレクトリ**: `data/representative-eval/real-v1-20261017/`
- **使用素材**:
  - `Aredoko_search_test_images_8.zip`: `bookA_p01_cover.png`, `bookA_p02_classroom.png`, `bookA_p03_library.png`, `bookA_p04_rain.png`, `bookB_p01_shrine.png`, `bookB_p02_forest_magic.png`, `asset_01_glasses_girl.png`, `asset_02_neon_street.png` (8枚)
  - `Aredoko_text_recognition_test_images_6.zip`: `bookA_p05_bubble_secret.png`, `bookA_p06_bubble_promise.png`, `bookB_p03_chapter_title.png`, `bookB_p04_blackboard_text.png`, `asset_03_signboard_onsen.png`, `asset_04_english_sign.png` (6枚)
  - 合計 14枚（`bookA.cbz` page 0..5, `bookB` フォルダ本 page 0..3, 単体画像 `asset_01`..`asset_04`）
- **索引処理時間**:
  - 表紙索引（6点）: **23.862秒** (GPU推論 + SQLite永続化)
  - 本文ページ索引（10ページ）: **3.680秒** (bookA 6ページ + bookB 4ページ)

### カテゴリ別集計結果

| カテゴリ | クエリ数 | cover Top1 | cover Rec@3 | cover Rec@5 | cover MRR | Exact Page@1 | combined Top1 | combined MRR |
|---|---|---|---|---|---|---|---|---|
| `visual_scene`（情景・人物直接検索） | 6 | **1.0000 (6/6)** | 1.0000 | 1.0000 | 1.0000 | 0.8333 (5/6)* | 0.6667 (4/6) | 0.7917 |
| `visual_text_ja`（画像内日本語文字認識） | 5 | **1.0000 (5/5)** | 1.0000 | 1.0000 | 1.0000 | **1.0000 (5/5)** | 0.6000 (3/5) | 0.8000 |
| `visual_text_en`（画像内英語文字・日英意味） | 2 | **1.0000 (2/2)** | 1.0000 | 1.0000 | 1.0000 | 1.0000 (2/2) | 0.0000 (0/2) | 0.5000 |
| `wd_tag_semantic`（未承認WDタグ意味検索） | 4 | **0.7500 (3/4)** | 1.0000 | 1.0000 | 0.8750 | - | - | - |
| **全体（Total）** | **17** | **0.9412 (16/17)** | **1.0000** | **1.0000** | **0.9706** | - | **0.5882 (10/17)** | **0.7794** |

\* `scene_03`（「神社 巫女」）は期待正解が `bookB` page 0（表紙）であり、作品集約において表紙一致（`actual_page=null`）として最上位ヒットしたため、アイテムTop1は100%正解。

### クエリ別実測値

#### 1. `visual_scene`（6問）
1. `scene_01`「夕焼けの教室」: **Top1** (`bookA`, page 1), score: `0.787370` [combined: 1位]
2. `scene_02`「赤い傘 雨」: **Top1** (`bookA`, page 3), score: `0.719651` [combined: 1位]
3. `scene_03`「神社 巫女」: **Top1** (`bookB`, cover), score: `0.743070` [combined: 4位]
4. `scene_04`「魔法陣 杖 白髪」: **Top1** (`bookB`, page 1), score: `0.723746` [combined: 2位]
5. `scene_05`「白髪 赤い眼鏡 パーカー」: **Top1** (`asset_01`), score: `0.750023` [combined: 1位]
6. `scene_06`「サイバーパンク ネオン 路地裏」: **Top1** (`asset_02`), score: `0.744290` [combined: 1位]

#### 2. `visual_text_ja`（5問、専用OCRなしでの直接画像内文字認識）
1. `text_ja_01`「秘密のパスワード」: **Top1** (`bookA`, page 4, フキダシ文字), score: `0.764421` [combined: 1位]
2. `text_ja_02`「水曜日のプラネタリウム」: **Top1** (`bookA`, page 5, フキダシ文字), score: `0.736971` [combined: 1位]
3. `text_ja_03`「黄金の砂時計」: **Top1** (`bookB`, page 2, 章扉ゴシック体), score: `0.759173` [combined: 2位]
4. `text_ja_04`「文化祭のカレーライス」: **Top1** (`bookB`, page 3, 黒板白チョーク文字), score: `0.793053` [combined: 2位]
5. `text_ja_05`「銀河ステーション」: **Top1** (`asset_03`, 案内看板ゴシック体), score: `0.727627` [combined: 1位]

#### 3. `visual_text_en`（2問、英語プレート文字・日英クロスリンガル）
1. `text_en_01`「MIDNIGHT COFFEE SHOP」: **Top1** (`asset_04`, 英字そのまま), score: `0.753368` [combined: 2位]
2. `text_en_02`「深夜のコーヒーショップ」: **Top1** (`asset_04`, 日本語意味検索), score: `0.698992` [combined: 2位]

#### 4. `wd_tag_semantic`（4問、未承認WD英語タグに対する日本語意味検索）
- 自動生成されたWD英語タグ（`wd-swinv2-v3` CPU）:
  - `bookA`: `1girl`, `school_uniform`, `serafuku`, `cherry_blossoms`, `red_neckerchief`, `black_hair`, `black_serafuku`, `pleated_skirt`, etc. (30 tags)
  - `bookB`: `miko`, `japanese_clothes`, `shrine`, `torii`, `long_hair`, `hakama`, `ponytail`, `red_hakama`, `sandals`, `tabi`, `stone_lantern`, etc. (30 tags)
  - `asset_01`: `1girl`, `thighhighs`, `hoodie`, `glasses`, `white_hoodie`, `black_skirt`, `sneakers`, etc. (30 tags)
  - `asset_02`: `scenery`, `city`, `night`, `cityscape`, `neon_lights`, `alley`, etc. (20 tags)
  - `asset_03`: `no_humans`, `sign`, `road_sign`, `text_focus`, `blue_sky`, etc. (10 tags)
  - `asset_04`: `no_humans`, `english_text`, `brick_wall`, `brick`, `parody` (5 tags)
- 検索結果:
  1. `wd_01`「セーラー服」: **Top1** (`bookA`), score: `0.727379`
  2. `wd_02`「巫女」: **Top1** (`bookB`), score: `0.733411`
  3. `wd_03`「赤い眼鏡」: **2位** (`asset_01`), score: `0.651348` (1位は `bookA`: 赤いスカーフ等の赤色要素と眼鏡タグの近傍差)
  4. `wd_04`「サイバーパンク」: **Top1** (`asset_02`), score: `0.621963`

### 分析・エビデンスに基づく確定結論

1. **EmbeddingGemma 2の画像内文字認識能力（Visual-OCR）**:
   - 漫画コマのフキダシ文字（『秘密のパスワード』『水曜日のプラネタリウム』）、章扉のゴシック体タイトル（『第三章 黄金の砂時計』）、黒板の白チョーク文字（『文化祭のカレーライス』）、案内看板（『銀河ステーション行』）、および英語プレート（『MIDNIGHT COFFEE SHOP』）のすべてにおいて、**専用OCRなしで100%のTop1正解率を達成**した。
   - さらに、内部ページを含むクエリでは、**すべての一致ページ番号（`ai_page_match.page`）が期待ページと100%完全に合致**した。
2. **専用OCR保留（OCR Deferral）の妥当性**:
   - ユーザー確定方針: 「*EmbeddingGemma 2の直接画像・本文ページ索引でも内容を見つけられないケースが多く確認されたときだけ、実装を検討する*」。
   - 今回の実素材測定において、**直接画像・本文ページ検索における検索見落とし（content-search misses）は 0件** であった。
   - したがって、**ユーザーの「OCR専用処理は保留」という方針は極めて妥当であり、MVPにおいて専用OCRアダプタの接続は不要**であることが定量的に確認された。
3. **`cover`（視覚）モードと `combined`（混合）モードの順位差の理由**:
   - 視覚モード（`source='cover'`）では Top1 **0.9412 (16/17)**、MRR **0.9706** と極めて高精度であった。
   - 一方、混合モード（`source='all'`）では Top1 **0.5882 (10/17)**、MRR **0.7794** に低下した。
   - これは、アイテムに本文テキストのタグ・メタデータが存在しない場合（ファイル名のみの状態）、Reciprocal Rank Fusion（RRF）においてテキスト側の同点順位が視覚スコアを相対的に希釈するためである。既存の設計文書（`docs/winui-mvp.md`）にある通り、「*視覚的な特徴を手がかりに検索する場合は、視覚（cover）モードを選択する*」という運用原則が実測値によって裏付けられた。
4. **WD Tagger未承認候補の意味検索**:
   - WD Tagger（CPU）により、少女・巫女装束・鳥居・眼鏡・パーカー・サイバーパンク路地裏・看板・英字壁等の特徴的なDanbooruタグが正確に抽出された。
   - 日本語の曖昧なクエリ（「セーラー服」「巫女」「サイバーパンク」）から未承認英語タグの意味ベクトルを介して直接作品を特定でき、Top1 75%、Recall@3 100% を達成した。
