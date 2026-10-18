# 音声・音楽内容検索の方式設計と契約 (R06)

2026-10-19 凍結。M2マイルストーン（全媒体の製品版候補）における音声・音楽機能の基本設計書。
本設計は [completion-roadmap.md](completion-roadmap.md) の R06完了条件および [product-vision.md](product-vision.md) に基づき、音声・音楽の入力能力、候補アーキテクチャの比較評価、ベクトル空間の厳格な分離、および時間区間根拠の契約を固定する。

---

## 1. 背景と目的

Aredokoは画像・本・動画に続き、音声・音楽メディア（`.mp3`, `.flac`, `.wav`, `.ogg`, `.opus`, `.m4a`, `.aac`, `.wma`）の内容検索と類似検索をM2で実現する。
音声・音楽の検索要求は本質的に異なる2つの次元から構成される：
1. **言語的・意味的内容（発話・会話・歌詞・ナレーション）**：ユーザーが日本語テキストクエリ（例：「おはよう」「会議の報告」「事件の真相」）で検索し、該当する音声ファイル内の発話箇所（秒単位の時刻）へ直接シークして再生する。
2. **音響的・音楽的特徴（効果音・環境音・音楽の雰囲気・楽器・音同士の類似）**：発話を含まない雨音、爆発音、ジャズピアノ、アコースティックギター、BGMの雰囲気検索、および「この曲に似た曲」「この効果音に似た素材」というアイテム起点類似検索。

これらを混同して単一の空間で扱おうとすると、無音やノイズがテキストクエリに誤ヒットする「意味の捏造（Hallucination）」や、逆に発話の文字情報が音楽類似を狂わせる問題が発生する。本設計書ではこの分離契約を工学的に確定する。

---

## 2. ローカルモデル・プロセッサの調査結果（実機CPU検証）

`.venv-ai`（transformers 5.19.0, sentence-transformers 6.1.0）およびローカルモデルディレクトリ `models/embeddinggemma-2` の設定・重み構造をGPUロードなしのCPU静的検査により実地確認した：

1. **EmbeddingGemma 2 の音声構成**:
   - `models/embeddinggemma-2/config.json` には `audio_config`（`model_type: "gemma4_audio"`, 12 hidden layers, hidden_size 1024, 8 attention heads, output_proj_dims 1536）が定義されている。
   - `models/embeddinggemma-2/model.safetensors` を検査した結果、全1,376キー中、**752キーが `audio_tower.*` の音声Conformer/Transformer重み**として実際に同梱されている。
   - `processor_config.json` および `preprocessor_config.json` には `Gemma4AudioFeatureExtractor`（サンプリングレート 16,000Hz, 128 mel bins, 40ms/token, hop_length 160）が存在する。
2. **アダプターとランタイム制約**:
   - `app/ai_adapters.py` において、`EmbeddingGemma2Adapter` は現在 `config={'audio_config': None}` として明示的に音声タワーをロード対象外としている。
   - 音声タワーをロードした場合、safetensorsの半分以上のパラメータがVRAM上に展開され、推論時メモリフットプリントが約1.5GB〜2.0GB増加する。
   - Transformersの `EmbeddingGemma2Processor` は、音声入力時にプロンプト文字列内の `<|audio|>` プレースホルダトークン数と音声入力数の一致を強制する設計となっており、`sentence-transformers` の汎用 `encode({'audio': ...})` 呼び出しとはそのままでは整合しない。
   - 最も重要な点として、`EmbeddingGemma 2` の音声タワーはマルチモーダル対話向けの**音声言語認識（Speech-to-Text Conformer）**として事前学習されており、**環境音（SFX）や音楽構造（メロディ・コード・テンポ・楽器構成）の音響類似度を測る能力を持たない**。

---

## 3. 2つの候補アーキテクチャの比較評価

R06の要件に基づき、以下の2案を4つの必須観点で評価した。

### 候補案A：単一マルチモーダル直接埋め込み（End-to-End）
`EmbeddingGemma 2` の `audio_tower` を有効化し、生音声波形（16kHz mel-spectrogram）から直接768次元埋め込みを算出して既存のテキスト・画像空間と同一のベクトル空間へ写像する案。

### 候補案B：分離型モジュラーアーキテクチャ（Selected）
音声の性質に応じてベクトル空間を完全に直交分離する案：
- **空間1（発話言語空間, `text/speech`）**：時間区間（`start_ms`, `end_ms`）ごとの発話内容（ASR/テキスト書き起こしアダプター）を抽出し、既存の768次元 `EmbeddingGemma 2` テキスト空間に投影。日本語クエリと同一空間で比較し、一致時刻（`audio_match_ms`）と文字根拠（`snippet`）を返す。
- **空間2（音響・音楽特徴空間, `audio/acoustic`）**：発話を含まない環境音・音楽特徴・曲同士の類似検索向けに、独立した音響埋め込み空間（専用音響アダプター、例: 512次元）を割り当てる。

### 4観点での評価マトリクス

| 評価観点 | 候補案A: 単一直接埋め込み | 候補案B: 分離型モジュラー（採用） |
| :--- | :--- | :--- |
| **1. 発話/会話 (`speech`)** | **△ 不安定**: 音声特徴からテキストへの直接射影は、日本語のアクセント・話者差・雑音に弱く、明示的なテキスト根拠（どの単語に一致したか）をユーザーに提示できない。 | **◎ 完璧**: 発話テキストを768次元テキスト埋め込みに写像するため、既存の日本語形態素・語彙・RRF順位統合の恩恵を100%享受可能。一致発話スニペットと開始時刻（ミリ秒）を正確に根拠表示。 |
| **2. 効果音/環境音 (`sfx/ambient`)** | **× 破綻**: 音声タワーが環境音（雨音、足音等）を無理やり言語空間へ射影するため、全く無関係な日本語テキスト（「こんにちは」等）に高類似度で誤マッチする幻覚が発生。 | **◎ 堅牢**: 言語空間と音響空間が分離されているため、環境音がテキスト検索を汚染しない。音響空間内で環境音タグや音響特徴による検索が可能。 |
| **3. 音楽の雰囲気/楽器 (`music`)** | **× 非対応**: Gemmaの音声タワーは音声言語用であり、和声・コード進行・テンポ・楽器音色を捉えられない。 | **◎ 明確**: 音楽専用の音響特徴空間（クロマ、スペクトル、音楽埋め込み）で独立して評価可能。 |
| **4. 音声/音楽同士の類似 (`similarity`)** | **△ 精度低・高コスト**: 音響的な類似度ではなく音素や話者特徴に引っ張られ、かつ1ファイルあたり数秒の推論に巨大なVRAMを消費。 | **◎ 理想的**: 純粋な音響特徴空間でのコサイン類似度により、曲調や効果音の波形類似度を高精度かつ高速に判定可能。 |
| **VRAM / リソース** | 常時+1.5GB〜2.0GB VRAM消費。VRAM 4GB〜6GB環境でOOMリスク。 | **追加VRAM 0MB**（発話テキストは既存テキストモデルを使用、音響特徴はCPU軽量抽出可能）。 |
| **ライセンス / 依存関係** | 追加パッケージなし（だが既存コードの大幅改造とGPU負荷増）。 | 新たな無断モデル取得を行わず、まずはCPUモックおよび既存テキスト埋め込みでR07を安全に完成可能。 |

---

## 4. 採用アーキテクチャと凍結決定

### 決定：候補案B（分離型モジュラーアーキテクチャ）を採用・凍結する。

1. **発話検索（R07）のベクトル空間**:
   - 既存の `EmbeddingGemma 2` 768次元テキスト空間（`modality='text'`）を共有。
   - テーブル：`ai_audio_segments`
   - 契約識別子：`contract = 'audio-speech-segment:v1'`
   - クエリ：ユーザーの入力クエリを通常の `query` プロンプトでエンコードした768次元ベクトル。
   - 候補：各音声ファイル内の時間区間ごとの発話スニペットテキストを `document` プロンプトでエンコードした768次元正規化ベクトル。
   - 類似度：内積（コサイン類似度）。全発話セグメント中の最大スコアをその音声ファイルの `text` モダリティスコアとし、最良セグメントの開始時刻を `audio_match_ms`、テキストをスニペット根拠として付与。

2. **音響・音楽検索およびアイテム起点類似（R08/R09プレビュー）**:
   - 発話テキスト空間とは**完全に独立した音響ベクトル空間**（`modality='acoustic'`, 例: 512次元）を導入する。
   - 契約識別子：`contract = 'audio-acoustic-feature:v1'`
   - 発話テキストと音響ベクトル間のコサイン計算はDBスキーマおよびAPIレベルで**厳格に禁止**する。

---

## 5. 発話区間データ契約とスキーマ設計 (R07仕様)

### 5.1 SQLiteスキーマ (`ai_audio_segments`)

```sql
CREATE TABLE IF NOT EXISTS ai_audio_segments(
    item_id INTEGER NOT NULL,
    source_revision TEXT NOT NULL,
    segment_id TEXT NOT NULL,
    start_ms INTEGER NOT NULL CHECK(start_ms >= 0 AND start_ms <= 86400000),
    end_ms INTEGER NOT NULL CHECK(end_ms >= start_ms AND end_ms <= 86400000),
    snippet TEXT NOT NULL,
    vector BLOB NOT NULL,
    contract TEXT NOT NULL,
    PRIMARY KEY(item_id, segment_id)
);
```

### 5.2 境界値と制約
- **最大継続時間**: 86,400,000 ms（24時間）。これを超える値はスキーマおよびバリデータで拒絶。
- **セグメント長**: 推奨3秒〜30秒（最大60秒）。過度に短い無音（<500ms）は破棄。
- **スニペット長**: 1文字〜1,024文字。空文字や空白のみのスニペットは登録しない。
- **ベクトル形式**: 768次元 float32（リトルエンディアン、3,072バイト）、$L_2$ 正規化済み（$\|v\|_2 = 1.0 \pm 10^{-4}$）。非有限値（NaN, $\pm\infty$）は除外。
- **最大ファイルサイズ**: 512 MiB（`MAX_AUDIO_BYTES = 512 * 1024 * 1024`）。

### 5.3 音声入力仕様
- サンプリングレート: 16,000 Hz
- チャンネル: 1 (Mono) float32
- 入力パイプライン: FFmpeg/fd 経由で安全にPCM抽出（一時ファイルへのパス出力や外部プロトコル読み込みを完全排除）。

### 5.4 原子性と中断・再開契約
- 音声1アイテムあたりのセグメント登録はSQLiteトランザクション内で不可分（Atomic）に実行。既存の同一 `item_id` の古いセグメントを全削除した上で一括挿入。
- 処理中のキャンセル（`cancel.is_set()` / `check()`）を各セグメント抽出間、候補バッチ間、および多数セグメント評価中（256セグメントごと）に監視し、キャンセル時は部分的な不完全セグメントを残さず即時中断。
- 元ファイルのハッシュ/更新日時が一致する（`source_revision` が等しい）場合は、既存の `ai_audio_segments` を再利用し、重複推論を防止。`get_segments(include_vectors=False)` により raw float32 BLOB を直接再利用可能とし、不要な再エンコードおよびリスト生成アロケーションを完全排除。
- 元ファイルが変更・削除された場合は、既存の `_current_rows` および鮮度検査により、旧セグメントは検索対象から自動除外される。破損ベクトルが含まれる場合は `fresh()` が False を返し安全に再索引へ誘導。

---

## 6. 時刻根拠（Timepoint Grounding）表示契約

検索結果（`MediaRow`）に `audio_match_ms`（開始ミリ秒）および `audio_match_snippet` が付与された場合の表示規則：

1. **時刻フォーマット**:
   `FormatVideoTimestamp(ms)`（例: `0:15`, `3:42`, `1:05:20`）
2. **根拠ラベル (`AIEvidence`)**:
   `音声発話一致（0:15 · 「おはようございます」）\n類似度 0.892`
   文字一致がある場合：
   `音声発話一致（0:15 · 「おはようございます」） · 文字一致1/1語\n類似度 0.892`
3. **無音・破損・未索引時の保護**:
   無音ファイル、破損した音声、発話が検出されなかったファイルは `ai_audio_segments` に行が作られず、`audio_match_ms` は `null` となる。0件のセグメントを無理やり0:00にフォールバックさせて偽の一致を起こしてはならない。

---

## 7. 決定事項まとめ

1. **R06完了**: 本設計書により、EmbeddingGemma 2の直接音声入力の限界、分離型モジュラーアーキテクチャの優位性、768D発話テキスト空間と将来の音響特徴空間の厳格な分離、および `ai_audio_segments` のデータ契約を凍結した。
2. **R07完了 (CPU_DONE)**: 発話区間索引契約（`CONTRACT = 'audio-speech-segment:v1'`、SQLite `ai_audio_segments`）と時刻根拠検索アダプタを実装。CoreプロトコルおよびCPU受入ハーネス（17件PASS）を完了。
3. **R08完了 (CPU_DONE)**: 独立した512D音響特徴空間（`CONTRACT = 'audio-acoustic-feature:v1'`、SQLite `ai_audio_acoustics`）を導入。日本語音響記述子マッチング（効果音・BGM検索、無音WAV幻覚防止）、音声・音楽同士のアイテム起点類似検索（マルチフレーム最大集約、候補 `audio_match_ms`・起点 `origin_match_ms` 時刻根拠、自己除外、空間分離拒絶）を実装。
4. **R09完了 (CPU_DONE)**: WinUIへの日常操作統合。`AudioPlayerPolicy`、ストリーミング範囲再生HTTP API `/api/library/audio/{item}/...`、`VideoPlayerView` 音声対応と自動シーク、右クリックコンテキストメニュー「似た音声・曲を探す」を配線完了。

---

## 8. R08/R09 音響特徴・類似検索・GUI統合仕様

### 8.1 SQLiteスキーマ (`ai_audio_acoustics`)

```sql
CREATE TABLE IF NOT EXISTS ai_audio_acoustics(
    item_id INTEGER NOT NULL,
    source_revision TEXT NOT NULL,
    at_ms INTEGER NOT NULL CHECK(at_ms >= 0 AND at_ms <= 86400000),
    vector BLOB NOT NULL,
    descriptors TEXT NOT NULL,
    contract TEXT NOT NULL,
    PRIMARY KEY(item_id, at_ms)
);
```

- **空間分離契約**: 512次元 float32（リトルエンディアン、2,048バイト）、$L_2$ 正規化済み。768D発話/テキストベクトルや視覚ベクトルとの照合は `score_candidates` で明示的に `ValueError` 拒絶。
- **日本語音響記述子**: `descriptors` カラムに最大64件の音響・音楽タグ（例: 雨音、ピアノ、ジャズ、環境音、爆発音）をJSON配列で保持。無音ファイルには記述子が付与されないため、幻覚的なヒットを完全防止。
- **音響類似検索**: `AISearch.similar(item_id)` で `origin['kind'] == 'audio'` の場合、`source='acoustic'`、`origin_kind='audio'` で512Dマルチフレーム最大類似度集約を実行。起点自身は自己除外し、最も類似度の高かった候補側時刻 `audio_match_ms` と起点側時刻 `origin_match_ms` を付与。
- **WinUI連携**:
  - `AudioPlayerPolicy`: 8種類の拡張子（.mp3, .flac, .wav, .ogg, .opus, .m4a, .aac, .wma）を安全に検証。
  - `ArchiveReaderClient.OpenAudioRangeAsync`: バックエンドの `/api/library/audio/{item}/...` からバイト範囲を安全に取得。
  - `VideoPlayerView`: `isAudio=true` モードでサムネイルホバープレビューを隠し、シークバー・再生・一時停止・音量コントロールを提供。一致時刻へ自動シーク。
  - 文脈メニュー: 音声アイテム選択時に「似た音声・曲を探す」を表示。
