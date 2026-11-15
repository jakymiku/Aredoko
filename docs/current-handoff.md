# Aredoko — 現行の単一引き継ぎ（2026-11-15）

本書は常に最新の1状態のみを保持する。過去の詳細は Git 履歴および [履歴目録](history-index.md) を参照。

## 現行HEAD・最新候補/予備

- **作業ブランチ / PR**: `feat/winui3-production-mvp-20261011` / Draft PR #5（最新コード `1f573d2b5d63754a1fd973821e46ca103ec6baa6`、最新開発フロントエンド `data/development-tools/frontend-product15`、本書・記録更新を次コミットで反映）。
- **最新配布候補**: 候補15 `dist/portable-managed-20261115-15/Aredoko/Aredoko.exe`（`alpha-managed-20261115-15`、`source_revision: 9210606`、Python非同梱 `663` payload / `500,265,116` bytes、WinUI は `frontend-product14` 同梱、ZIP `215,173,933` bytes）。`1f573d2` の再梱包は未実施。
- **直前予備**: 候補14 `dist/portable-managed-20261114-14/Aredoko/Aredoko.exe`（`c068248`）。証拠用候補05/06/09を保持。

## 最近確認した変更

- **ページ跨ぎ範囲選択・棚ピッカーその場作成・ルート初期棚ダイアログ**（`1f573d2`、`LibrarySelection.cs` / `MainPage.{xaml,Selection,ShelfPicker}.cs`）：`LibrarySelection.PreviousAnchor` を追加し、`BrowseActionsFlyout` に `BtnSelectRangeSpan`（「直前の選択からここまで選択（N 件）」／256件超過時は無効化＋上限表記）を、行右クリック `SimilarityMenu` に `SelectRangeTo{id}` を追加。また `LoadAsync` で `librarySelection.Count > 0` 時の `Details.IsPaneOpen` 維持、`PickShelfIdsAsync` での `{prefix}NewName`/`{prefix}CreateNew` その場新規棚作成（棚解除除く）を実装。
- **単体・実機GUI・容量整理**：`Aredoko.Core.Tests` exit 0（`PreviousAnchor` 8項目含む）、`frontend-product15` publish + `portable-build.json`（373 entries）照合完了。ホストGUI `data/gui-range-root-shelf01/run03/summary.json`（300件）でルート初期棚ダイアログ＋「初期新規棚B」その場作成・600件棚反映、1–60→61–120ページ跨ぎ65件選択（一覧外60件）と詳細維持、300件上限ガード、`db_intact: true`・`originals_sha_match: true`・`exit_code: 0` を確認。旧 `frontend-product14`（`376` files / `165,482,663` bytes）を削除し `data/capacity-20261113/cleanup-frontend14.json` へ記録。詳細証拠は [UI記録](p3-continuous-browse.md)。
- **候補15 オフライン Windows Sandbox 受入 PASS**（`ccb34ca`、`data/ai-ui/managed-candidate15-offline/evidence/result.json`）：未導入ゲストで保持済み公式 artifact からの `basic_runtime` `cpython 3.13.17` 64bit `venv` 構築と `normal_exit: 0` を確認。詳細は [配布設計](lightweight-distribution.md)。

## 利用者にできること

- **基本起動・管理Python環境**：初回同意・取消/再開・オフライン保持済み公式 artifact からの検証構築、診断画面での Python 版/venv 確認、メディア再生/CBZ閲覧・動画音声の星操作。
- **整理・比較・複数選択・AI検索**：`920×700` 以上での一覧/詳細 `Inline` 比較、棚・お気に入り即時反映、棚ピッカー上での新規棚作成、ルート初期棚の一括選択保存、ページ跨ぎ含む範囲選択（最大256件）・先頭256件一括選択・検索条件一括解除、設定からの AI 環境自動構築・速度上限・キャッシュ削除。

## 未受入・未検証

- `1f573d2`（`frontend-product15`）を含む配布候補の次回区切り再梱包、右クリック `SelectRangeTo{id}` の対話デスクトップ上での実UI操作（`run02` はロック画面 `SendInput` 不可のためスキップ）、候補15オンライン Sandbox 手動起動（`managed-candidate15-online-manual/Aredoko.wsb` 生成済み）、AI依存・モデルの新規オンライン自動構築一連、実日本語IME、HC・物理DPI、署名・正式公開。試験は専用設定/DBと生成素材のみ使用し、通常版・私物・`Aredoko-test/`・OS設定は未変更。

## 次の1件

1. **P6**：複数UI単位の区切りまたは起動/配布変更時に `frontend-product15` 同梱の次期配布候補を再梱包し、`test_portable_startup.py`／オフライン Sandbox で確認する（オンライン再取得は同一構成反復しない方針）。
2. **UI**：中央の一覧・検索・詳細の残課題を小単位で継続（結果カード情報密度・詳細編集の細部改善、および対話デスクトップ上での `SelectRangeTo{id}` 右クリック導線確認）。
