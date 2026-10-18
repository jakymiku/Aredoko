# R05 — 動画起点の類似検索と時刻根拠・既存UI接続

2026-10-19。R05として、保存済みの時間付き動画代表フレームvectorを活用した動画起点・動画候補の類似検索、時刻根拠（timepoint grounding）、自己除外、および既存WinUIビューア接続を実装完了（CPU_DONE）。
実機GUI/GPU受入はユーザー方針に従いR14で一括検証（`tools/test_video_similarity_acceptance.py`）。次はR06（音声/音楽の入力能力・モデル/契約/評価設計）。

## 1. 類似検索アーキテクチャと集約契約

- **動画代表フレームの取得 (`VectorStore.video_frames`)**:
  - `ai_video_frames` テーブルから指定アイテムの全代表フレーム `(at_ms, vector_blob)` を `at_ms` 昇順で取得。
  - 代表フレームが未索引で `cover` ベクトルのみ保存されている場合は、時刻 0ms の1フレームとして安全にフォールバック。
  - 保存された blob は長さチェック（`dim * 4` バイト）、および非負二乗ノルム `isfinite` チェックにより、不正・破損・非有限（NaN/Inf）ベクトルを割り当てなしで除外。
- **マルチフレーム最大類似度集約 (`VectorStore.scores_with_content`)**:
  - 動画が起点または候補となる場合、フレーム単位のコサイン類似度 $\cos(\mathbf{v}_{orig}, \mathbf{w}_{cand})$ を比較し、最大の類似度を採用。最初の1フレームだけの比較を「動画全体」と偽らない。
  - 最大類似度を達成した候補フレームのタイムスタンプ `video_hits[cand_id] = cand_ms`、および起点フレームのタイムスタンプ `origin_hits[cand_id] = orig_ms` を正確に記録（Timepoint Grounding）。
  - 起点と候補の組み合わせ:
    1. **動画 → 動画**: 起点フレーム時刻 `origin_match_ms` と候補フレーム時刻 `video_match_ms` の双方を記録。
    2. **画像/本 → 動画**: 候補フレーム時刻 `video_match_ms` を記録。
    3. **動画 → 画像/本**: 起点フレーム時刻 `origin_match_ms` を記録。
- **自己除外と範囲制御 (`AISearch.similar`)**:
  - 起点アイテム（動画・画像・本）は結果リストから確実に除外 (`exclude_id=item_id`)。
  - 起点アイテムの種別 `origin_kind` を検索レスポンスに明示的に含め、UI側で適切な説明や案内を表示可能に。
  - 候補の対象種別として `('image', 'book', 'archive', 'video')` を許可（`audio` はR06/R08まで対象外）。
  - 各候補アイテムに `video_match_ms`、`origin_match_ms`、`similarity_origin_id` を付与。
  - 起点・候補ともにファイル原本の変更・再エンコード・モデル推論は行わず、保存済みベクトルのみを使用。

## 2. Coreプロトコルと根拠表示 (`Aredoko.Core`)

- **`SimilaritySearch.CanStart(row)`**:
  - `video` 種別を許可 (`row.Kind is "image" or "book" or "archive" or "video"`、`audio` は拒否)。
- **`SimilaritySearch.Guidance(status, originKind = "")`**:
  - `originKind == "video"` の場合、「この動画の代表フレームはまだAI索引に含まれていません。設定の「AI検索の準備」から索引を作成してください。」等の動画特化メッセージを提供。
- **`MediaRow.AIEvidence`**:
  - 動画起点と動画候補の組み合わせに応じたタイムスタンプ根拠表示:
    - 動画 → 動画: `動画一致（起点 M:SS → 候補 M:SS）\n類似度 0.xxx`
    - 画像 → 動画: `動画フレーム一致（M:SS）\n類似度 0.xxx`
    - 動画 → 画像: `起点の動画（M:SS）に似た候補\n類似度 0.xxx`
    - 画像 → 画像: `起点の画像・表紙に似た候補\n類似度 0.xxx`

## 3. WinUI 3 UI接続 (`Aredoko.WinUI`)

- **右クリックコンテキストメニュー (`SimilarityMenu`)**:
  - 動画行の右クリックメニュー項目を `似た動画・素材を探す`（AutomationId: `FindSimilar{row.Id}`）に変更。
  - 画像・本は従来の `似た画像・素材を探す` を維持。
- **類似検索バナー・ガイダンス**:
  - 動画起点の類似検索時、情報バナータイトルを `似た動画・素材`、ヒントを `動画の代表フレームから似た候補を探しています。検索語の入力や「検索」で通常の検索に戻ります。` に更新。
- **動画プレイヤー自動シーク (`VideoPlayerView`)**:
  - 検索結果をクリックして動画を開いた際、`row.VideoMatchMs` が存在すれば自動的に該当時刻（`Math.Min(startMs, duration - 50ms)`）へシーク。
  - ステータスバーに `該当時刻（M:SS）に移動しました。再生ボタンまたはスペースキーで再生できます。` と通知。

## 4. 検証と品質記録

- **Python単体テスト (`tests/test_similarity_search.py`)**: 21 PASS (16 既存 + 5 新規 `VideoSimilarityTests`)
  - `test_video_to_video_multi_frame_max_aggregation_and_grounding`
  - `test_image_to_video_timepoint_grounding`
  - `test_video_search_kind_filtering`
  - `test_video_unindexed_and_corrupt_frame_fallback`
  - `test_video_similarity_zero_inference_and_sources_unchanged`
- **C# Coreテスト (`tests/Aredoko.Core.Tests`)**: 595 PASS, 0 failure
  - `SimilarityTests.cs`: `CanStart` による video 許可 / audio 拒否、`VideoMatchMs` / `OriginMatchMs` のパース、`AIEvidence` 複合時刻表示、厳格な動画候補検証。
- **WinUIビルド**: x64 Release 0 warnings / 0 errors
- **受入ハーネス (`tools/test_video_similarity_acceptance.py`)**:
  - `--stage cpu`: 全単体テスト、Coreテスト、WinUIビルド、プログラムによる動画類似検索実証（2動画・1画像によるコサイン1.0最大集約と時刻記録）に合格。
  - `--stage gpu` / `--stage gui`: R14 バッチ実行用に準備完了。
