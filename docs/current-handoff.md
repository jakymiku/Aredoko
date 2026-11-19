# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- ブランチ / PR：`feat/winui3-production-mvp-20261011` / Draft [PR #5](https://github.com/jakymiku/Aredoko/pull/5)
- 直近UI・再生・AI改修：**候補26 実機要望13項目対応完了**（[ui-brushup-plan-20261118.md](docs/ui-brushup-plan-20261118.md)、コード `cdf17b6`、`data/development-tools/frontend-product26`）
- 最新配布候補：**候補26** `dist/portable-managed-20261120-26/Aredoko/Aredoko.exe`（source `cdf17b625b128504473c28cc3012588aaf66e1c9`、`677` payload / `501,747,883` bytes、`Aredoko.exe --self-test`・`preflight.json`・`Aredoko-windows-x64.zip` (`215,615,894` bytes)・`validation-kit.zip` PASS、`__pycache__` 0件）
- 受入済み/直前予備：**候補25**（`fd3ca9d`）、**候補21**（P6 Sandbox E2E PASS）、**候補19**（P6 Sandbox E2E PASS）
- 現行 frontend / 保持証拠：`data/development-tools/frontend-product26`（直前予備 `frontend-product25`）、証拠 [run17f_light](data/gui-ui-polish02/run17f_light/summary.json) / [run18_dark](data/gui-ui-polish02/run18_dark/summary.json)（`frontend-product24` は退避済み）

## 最近確認した変更
- **動画サムネイル・互換再生・ビューア改善**：`fd:` シーク可能入力＋`ThumbnailDisk` 動画永続キャッシュ、`VideoCompatCache`（H.264 `yuv420p` faststart MP4 変換・`playback_slots(4)`・`VideoRandomAccessStream.ReadAsync` IBuffer 修正・失敗時「外部アプリで開く」）、`ThumbnailService` セッション内 256 件 LRU キャッシュ、各ビューア内ダブルクリック最大化・復元を実装。
- **CBZ 連続閲覧・ページ類似・選択式 AI 範囲・設定整理**：`ArchiveReaderView` / `ImageViewerView` の右クリック類似検索（`origin_page`）、`result_sessions` 横断遷移（`include_books`＋`ViewerWindow.SwapContent`）、`book_pages`（`cover_only` / `all_pages`）、文字/AI切替時の手動検索維持（`PendingAutoSearch`）、設定 960px コンパクション、AI設定固定幅＆「動画・音声」セクション直結 CTA（`BtnAIMediaPrep`）を実装。
- **候補26 総合テスト結果**：最終編集後に `Aredoko.Core.Tests`（`1,467` PASS / `0` FAIL、exit 0）、Python `171` 件（`125` 件 skipped=5＋`39` 件＋`7` 件 OK）、`frontend-product26`（`373` entries、`inspect_portable` PASS）、[check.py](data/gui-ui-polish02/check.py) Light（`run17f_light`）・Dark（`run18_dark`）全項目 PASS＋Light/Dark 各7枚スクリーンショット目視確認、および**候補26**再梱包・整合照合 PASS。

## 利用者にできること
- 最新配布候補26（[Aredoko.exe](dist/portable-managed-20261120-26/Aredoko/Aredoko.exe) または `dist/portable-managed-20261120-26/Aredoko-windows-x64.zip`）で動画サムネ・互換再生、CBZ 右クリック類似検索・連続閲覧、CBZ 内部ページ選択式 AI、手動検索切替、ダブルクリック最大化、整理済み設定画面を利用できる。

## 未受入・未検証
- **候補26のオフライン Windows Sandbox E2E**（候補21以前の E2E を候補26の合格とみなさない）。
- 実 AI モデル導入環境での `all_pages` 索引作成＋ページ類似検索スコア検証、物理マウスでのビューア内ダブルクリック最大化、実日本語 IME・物理 DPI・ハイコントラスト。
- P6-3（`cp313-cu128-draft.json` 供給元レビュー・immutable host・`TRUSTED_CATALOGS` 登録）。専用OCRは保留。

## 次の1件（P6 / UI）
- **候補26の P6 オフライン Windows Sandbox E2E（保持済み `runtime-artifacts` 利用）＋並行して P6-3（`cp313-cu128` 供給元レビュー）または実AI環境での `book_pages=all_pages` 確認**。
