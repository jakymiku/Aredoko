# Aredoko — 現行の単一引き継ぎ（2026-11-15）

本書は常に最新の1状態のみを保持する。過去の詳細は Git 履歴および [履歴目録](history-index.md) を参照。

## 現行HEAD・最新候補/予備

- **作業ブランチ / PR**: `feat/winui3-production-mvp-20261011` / Draft PR #5（WinUI修正 `921060675a42c9d9b9aefde94c613c35569d76d5`、本書・記録更新を最終更新コミットで反映）。
- **最新配布候補**: 候補15 `dist/portable-managed-20261115-15/Aredoko/Aredoko.exe`（`alpha-managed-20261115-15`、`source_revision: 9210606`、Python非同梱 `663` payload / `500,265,116` bytes、WinUI `data/development-tools/frontend-product14`、ZIP `215,173,933` bytes）。
- **直前予備**: 候補14 `dist/portable-managed-20261114-14/Aredoko/Aredoko.exe`（`c068248`）。証拠用候補05/06/09を保持。

## 最近確認した変更

- **選択上限ガード・先頭256件一括選択・多棚表示改善**（`6fefe0e` + `9210606`、`MainPage.xaml` / `MainPage.Selection.cs` / `MainPage.xaml.cs`）：256件超過時は `BtnSelectVisibleItems` を無効化し「上限 256 件」明示＋`BrowseActionsFlyout` に `BtnSelectFirstMaxItems`（「読み込み済みの先頭 256 件を選択」）を追加（`SelectLoadedRowsAsync` で共通化）。右サマリーを `SelectionSummaryScroll` 化し「一覧外 X 件」表示を追加、一覧行 `FormatRowMetadata` を3棚＋`ほかN棚` に要約しタグ表示維持と全量Tooltip化を実施。ホスト実機GUI `data/gui-search-reset-select01/quick-run02/summary.json`（`frontend-product14`）で32棚+タグ行要約・3件選択+32棚サマリースクロール解除・363件時上限無効→256件一括選択→解除・DB整合・原本不変・通常終了0を確認。
- **候補15 オフライン Windows Sandbox 受入 PASS**（`data/ai-ui/managed-candidate15-offline/evidence/result.json`）：未導入ゲスト（`WDAGUtilityAccount`、`baseline_was_clean: true`、`<Networking>Disable</Networking>`）へ保持済み公式 artifact を事前配置して起動し、`Official package verified and extracted`、`mode: "production"`、`basic_runtime` `cpython 3.13.17`（64bit `venv`）、`normal_exit: 0` を確認。`managed-candidate15-online-manual/Aredoko.wsb` も生成済み。
- **単体・事前検証・容量整理**：`Aredoko.Core.Tests` exit 0、`tests/test_portable_startup.py` 19件（`36.527s OK`）、`tests/test_windows_sandbox.py` 8件（`0.146s OK`）、`dist/portable-managed-20261115-15/preflight.json` (`pass: true`)。Git非追跡・リンク/プロセスなし確認後、候補13と `frontend-product12`/`13`（計 `1,425` files / `1,046,498,535` bytes）を削除（`data/capacity-20261113/cleanup-candidate13-frontend12-13.json`）。詳細証拠は [配布設計](lightweight-distribution.md)・[UI記録](p3-continuous-browse.md)。

## 利用者にできること

- **基本起動・管理Python環境**：初回同意・取消/再開・オフライン保持済み公式 artifact からの検証構築、診断画面での Python 版/venv 確認、メディア再生/CBZ閲覧・動画音声の星操作。
- **整理・比較・複数選択・AI検索**：`920×700` 以上での一覧/詳細 `Inline` 比較（`1080px` 未満で左ナビ優先折り畳み）、棚・お気に入り即時反映、複数選択の一括整理とスクロール可能サマリー、表示中全選択・256件超過時の先頭256件一括選択・検索条件一括解除、設定からの AI 環境自動構築・速度上限・キャッシュ削除。

## 未受入・未検証

- 候補15での新規オンライン Windows Sandbox 起動（`data/ai-ui/managed-candidate15-online-manual/Aredoko.wsb` 生成済み；同一構成の再ダウンロード不要方針により手動/必要時のみ）、257件超のページ跨ぎ範囲選択（Shift選択）、AI依存・モデルの新規オンライン自動構築一連、ルート棚ダイアログ単体GUI、実日本語IME、HC・物理DPI、署名・正式公開。試験は専用設定/DBと生成素材のみ使用し、通常版・私物・`Aredoko-test/`・OS設定は未変更。

## 次の1件

1. **P6**：配布・基本環境導入や互換性確認を進める（新規オンライン取得が必要な変更が入った場合のみ `managed-candidate15-online-manual/Aredoko.wsb` 等で確認、AI構築オンライン取得の受入要件整理）。
2. **UI**：中央の一覧・検索・詳細の残課題を小単位で継続（例：257件超／ページ跨ぎを含む Shift 範囲選択の実GUI確認、結果カードの情報密度・詳細編集の細部改善）。
