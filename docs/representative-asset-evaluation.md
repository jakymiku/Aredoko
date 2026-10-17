# 代表的疑似同人誌・画像内文字認識（Visual-OCR）評価

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

### 実素材ZIP受領後の実行
```powershell
python tools/evaluate_representative_assets.py --zip path/to/assets.zip
```

### 実素材フォルダからの実行
```powershell
python tools/evaluate_representative_assets.py --input-dir path/to/assets_dir
```

---

## 5. 安全性・境界と注意事項

- プレースホルダー実行（`--generate-placeholder`）は、コード契約・ライブラリ構築・パイプライン整合を検証する合成テストであり、**実モデルの検索精度や文字認識能力を主張するものではない**。
- 素材読み込み時は、パストラバーサル（`..`）、絶対パス、シンボリックリンク、50MB超の過大ファイルを厳格に拒絶する。macOSリソースフォーク（`__MACOSX/`）、隠しファイル（`.*`）、`Thumbs.db`は安全に無視される。
- ファイル名照合は正規名（`bookA_p01_cover.png`）に加え、一般的な番号ゆらぎ（`bookA_p1`, `bookA_01`, `bookA_1`, `asset_1`, `asset01`等）および大文字小文字の違いに柔軟に対応する。
- `--input-dir` は展開後のネストされたサブディレクトリも再帰的に走査して素材を検出する。
- 本文ページ索引は、16ページ以下の場合は既存の16ページ原子的トランザクション（`start`）、16ページ超の場合は分割トランザクション（`start_chunked`）を自動適用し、版・プロファイル束縛と中断時保護を厳格に維持する。
