# Aredoko — 現行の単一引き継ぎ（2026-11-14）

本書は常に最新の1状態のみを保持する。過去の詳細は Git 履歴および [履歴目録](history-index.md) を参照。

## 現行HEAD・最新候補/予備

- **作業ブランチ / PR**: `feat/winui3-production-mvp-20261011` / Draft PR #5。今回の選択修正は本書の最終更新コミットに含む。
- **最新配布候補**: 候補14 `dist/portable-managed-20261114-14/Aredoko/Aredoko.exe`（`alpha-managed-20261114-14`、Python非同梱 `663` payload / `500,275,418` bytes、WinUI `data/development-tools/frontend-product12`、ZIP `215,177,771` bytes）
- **直前予備**: 候補13 `dist/portable-managed-20261113-13/Aredoko/Aredoko.exe`（`0e34708`）。証拠用候補05/06/09を保持。

## 最近確認した変更

- **選択上限とサマリーの修正**。読み込み済みが256件を超えると全選択を無効にし、上限をメニューに表示。右の選択サマリーをスクロールできるようにした。Portable frontend `data/development-tools/frontend-product13` のホストGUIで、363件時に部分選択されないこと、32棚のサマリーをスクロールして選択を解除できること、DB整合・原本SHA・通常終了0を確認。証拠 `data/gui-search-reset-select01/quick-run01/summary.json`。配布候補14は修正前の `c068248`。

- **検索・絞り込み条件の一括解除と表示中ページ全選択**（`MainPage.xaml` / `MainPage.xaml.cs` / `MainPage.Shelves.cs` / `MainPage.Selection.cs`）：`BtnClearSearchConditions`・0件時 `EmptyResetConditions`（未保存時は `ConfirmDiscardAsync()` で保護）と `BtnSelectVisibleItems`（表示中ページ一括選択）・`SelectionSummaryClear`・`BulkClearSelection` を追加。ホスト実機GUI `data/gui-search-reset-select01/run05/summary.json` で初期非表示・0件復元・破棄キャンセル保持/確定復元・3件選択/2経路解除・DB整合・原本不変・通常終了0を確認。
- **候補14 オフライン Windows Sandbox 受入 PASS**（`data/ai-ui/managed-candidate14-offline/evidence/result.json`）：未導入ゲスト（`WDAGUtilityAccount`、`baseline_was_clean: true`、`<Networking>Disable</Networking>`）へ保持済み公式 artifact を事前配置して起動し、`Official package verified and extracted`、`mode: "production"`、`basic_runtime` `cpython 3.13.17`（64bit `venv`）、`normal_exit: 0` を確認。`WindowsSandbox*` UI 0件（`vmmemWindowsSandbox` PID 17900 はホスト側で残存）。
- **単体・事前検証・文書整理**：`Aredoko.Core.Tests` exit 0、`tests/test_portable_startup.py` 19件（通常権限 `32.940s OK`）、`tests/test_windows_sandbox.py` 8件（`0.313s OK`）、`dist/portable-managed-20261114-14/preflight.json` (`pass: true`)。[AGENTS.md](../AGENTS.md) を簡潔化し、[対応待ち一覧](deferred-issues.md) の D01・D05 を解消済みへ更新（D02/D04/D06 は維持）。
- **容量整理**：Git非追跡・リンク/プロセスなし確認後、候補12と `frontend-product11`（計 `1,050` files / `881,047,471` bytes）を削除（`data/capacity-20261113/cleanup-candidate12-frontend11.json`）。詳細ログは [配布設計](lightweight-distribution.md)・[UI記録](p3-continuous-browse.md)。

## 利用者にできること

- **基本起動・管理Python環境**：初回同意・取消/再開・オフライン保持済み公式 artifact からの検証構築、診断画面での Python 版/venv 確認、メディア再生/CBZ閲覧・動画音声の星操作。
- **整理・比較・複数選択・AI検索**：`920×700` 以上での一覧/詳細 `Inline` 比較（`1080px` 未満で左ナビ優先折り畳み）、棚・お気に入り即時反映、複数選択の一括整理とサマリー操作、表示中ページ全選択・検索条件一括解除、設定からの AI 環境自動構築・速度上限・キャッシュ削除。

## 未受入・未検証

- 候補14での新規オンライン Windows Sandbox 起動（`data/ai-ui/managed-candidate14-online-manual/Aredoko.wsb` 生成済み；同一構成の再ダウンロード不要方針により手動/必要時のみ）、257件超のページ跨ぎ範囲選択、AI依存・モデルの新規オンライン自動構築一連、ルート棚ダイアログ単体GUI、実日本語IME、HC・物理DPI、署名・正式公開。試験は専用設定/DBと生成素材のみ使用し、通常版・私物・`Aredoko-test/`・OS設定は未変更。

## 次の1件

1. **P6**：基本環境導入や互換性確認を進める（新規オンライン取得が必要な変更が入った場合のみ `managed-candidate14-online-manual/Aredoko.wsb` 等で確認、AI構築オンライン取得の受入要件整理）。
2. **UI**：中央の一覧・検索・詳細の残課題を小単位で継続（例：257件超／ページ跨ぎを含む複数選択・範囲選択の明示導線や結果カードの情報密度確認）。
