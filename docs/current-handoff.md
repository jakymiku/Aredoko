# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- ブランチ / PR：`feat/winui3-production-mvp-20261011` / Draft [PR #5](https://github.com/jakymiku/Aredoko/pull/5)
- 直近UI・再生・AI改修：**候補27 試用フィードバック4項目完了**（[ui-brushup-plan-20261118.md](docs/ui-brushup-plan-20261118.md)、コード `f785280`、`data/development-tools/frontend-product27`）
- 最新配布候補：**候補27** `dist/portable-managed-20261120-27/Aredoko/Aredoko.exe`（source `f785280869cd20646280c3e910ff137a9ff53e3b`、`677` payload / `501,976,746` bytes、`Aredoko.exe --self-test`・`preflight.json`・`Aredoko-windows-x64.zip` (`215,699,030` bytes)・`sandbox.zip` (`6` files) PASS、`__pycache__` 0件）
- 受入済み/直前予備：**候補26**（`cdf17b6`）、**候補21**（P6 Sandbox E2E PASS）、**候補19**（P6 Sandbox E2E PASS）
- 現行 frontend / 保持証拠：`data/development-tools/frontend-product27`（`373` entries、`portable-build.json` 照合済み、直前予備 `frontend-product26`）、証拠 [run20_light](data/gui-ui-polish02/run20_light/summary.json) / [run21_dark](data/gui-ui-polish02/run21_dark/summary.json)（候補25・`frontend-product25` は退避済み）

## 最近確認した変更
- **CBZ 全ページ一括AI索引＋100ページ超過警告**：`POST /api/library/ai/pages/all`（16ページ原子分割＋既存済ページスキップ＋中断対応）と、右クリック「全ページを一括でAI検索データに追加」（`IndexBookAllPages`）／ページ索引ダイアログ内一括登録ボタン（`PageAIAddAll`）、および 100 ページ超で実ページ数を示す確認ダイアログ（`LargeBookAIWarningDialog`）を実装。
- **一時停止中の動画右クリック場面類似＋横断類似＋ピル型ビューアUI**：`VideoPlayerView` の右クリック／`VideoSettings`（`VideoFindSimilarFrame`）から一時停止時刻 `origin_ms` を使って視覚類似検索を実行可能化。`AISearch.similar` を画像・本/CBZ内部ページ・動画代表フレーム横断対象へ統合し `Kind` 切替で即時再絞込（`PendingAutoSearch`）。`ViewerChromeController` を中央フローティングピル型へ刷新し、下部 72px ホバー 110ms 表示・140ms→160ms フェードアウト、ピン留めトグル（`\uE718`）、カプセル型シークバー（`ImageSequenceSeek` / `ReaderPageSeek` / `VideoSeek`）を実装。
- **候補27 総合テスト結果**：最終編集後に `Aredoko.Core.Tests`（`1,477` PASS / `0` FAIL、exit 0）、Python 単体（`test_winui_compile_stub`＋`test_native_combo_selection` `7` 件、`test_ai_setup_plan`＋`test_portable_startup`＋`test_windows_sandbox` `39` 件、`test_video_previews` ほか8モジュール `127` 件 OK skipped=5、加えて FFmpeg `PATH` 下の `test_video_previews`＋`test_video_frames` `25` 件 OK skipped=1）、[check.py](data/gui-ui-polish02/check.py) Light（`run20_light`）・Dark（`run21_dark`）全項目 PASS＋Light/Dark 各4画面スクリーンショット目視確認、および**候補27**再梱包・整合照合 PASS。

## 利用者にできること
- 最新配布候補27（[Aredoko.exe](dist/portable-managed-20261120-27/Aredoko/Aredoko.exe) または `dist/portable-managed-20261120-27/Aredoko-windows-x64.zip`）で CBZ 全ページ一括AI索引（100頁超警告付き）、動画の任意一時停止場面からの類似検索、画像・本・動画横断の見た目類似（種類フィルタ即時絞り込み）、中央フローティングピル＋高速自動収納＋カプセルシークバー付きビューアを利用できる。

## 未受入・未検証
- **候補27のオフライン Windows Sandbox E2E**（候補21以前の E2E を候補27の合格とみなさない）。
- 実 AI モデル導入環境での `pages/all` 一括索引・動画 `origin_ms` 類似・横断類似ランキング、物理マウス（非ロック画面）での 72px ホバー表示/離脱消灯・右クリック・ダブルクリック最大化、実日本語 IME・物理 DPI・ハイコントラスト。
- P6-3（`cp313-cu128-draft.json` 供給元レビュー・immutable host・`TRUSTED_CATALOGS` 登録）。専用OCRは保留。

## 次の1件（P6 / UI）
- **候補27の P6 オフライン Windows Sandbox E2E（保持済み `runtime-artifacts` 利用）＋並行して実AI環境での CBZ一括索引・動画場面類似・横断ランキング実機確認、または P6-3（`cp313-cu128` 供給元レビュー）**。
