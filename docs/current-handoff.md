# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- ブランチ / PR：`feat/winui3-production-mvp-20261011` / Draft [PR #5](https://github.com/jakymiku/Aredoko/pull/5)
- 直近機能コミット：`7eb7f3e`（**UI-A〜UI-D**・`frontend-product20`）、`01eecad`（候補20 E2E）
- 最新配布候補：**候補21** `dist/portable-managed-20261118-21/Aredoko/Aredoko.exe`（source `7eb7f3e64fbe1521177ae3bd0245acf50be48db9`、`675` files / `501,291,470` bytes、ZIP `215,442,877` bytes SHA-256 `dd4659f5...`、`--self-test`・`preflight.json`・`validation-kit.zip`・オフライン Sandbox E2E PASS）
- 受入済み直前予備：**候補20**（P6 E2E PASS）、**候補19**（P6 E2E PASS）、**候補15**（旧基準 Sandbox PASS）
- 現行 frontend / 保持証拠：`data/development-tools/frontend-product20`（直前予備 `frontend-product19`、`frontend-product18` 整理済み）、証拠候補 `05` / `06` / `09`、`data/ai-ui/managed-candidate21-p6-e2e`

## 最近確認した変更
- **候補21 P6 再梱包・オフライン Windows Sandbox E2E（2026-11-18）**：`UI-A〜UI-D` を含む `frontend-product20`＋`LICENSE`＋`THIRD_PARTY_LICENSES/` を候補21へ再梱包し、[managed-candidate21-p6-e2e](data/ai-ui/managed-candidate21-p6-e2e/evidence/runs/run-20261118-002809-b1bbe8/result.json)（`<Networking>Disable</Networking>`・ゲスト内SAC無効化下）で ZIP 展開→登録/閲覧/保存→別パス再配置→保持/検索（[after-restart.png](data/ai-ui/managed-candidate21-p6-e2e/evidence/runs/run-20261118-002809-b1bbe8/after-restart.png)）・DB・原本SHA整合まで PASS。
- **WinUI UI-A〜UI-D ブラッシュアップ（`7eb7f3e`、`frontend-product20`）**：カード背景プレート＋種別/棚/タグバッジ、グリッド時棚/タグ表示、詳細タグチップ削除・既存タグ追加・`Ctrl+Enter`保存、検索バー「タグ一覧…」（`BtnBrowseTags`）、設定3グループ整理。`Aredoko.Core.Tests` 終了コード `0` と [gui-ui-polish02](data/gui-ui-polish02/run04_light/summary.json)（Light `run04_light`・Dark `run05_dark`）PASS。

## 利用者にできること
- 候補21（[Aredoko.exe](dist/portable-managed-20261118-21/Aredoko/Aredoko.exe)）をそのまま試用・ZIP展開・別配置でき、新UI（見やすいカード・タグチップ整理・「タグ一覧…」・設定グループ化・`LICENSE`/`THIRD_PARTY_LICENSES/`同梱）を一通り利用できる。

## 未受入・未検証
- ユーザー実機での試用フィードバック反映、P6-3（`cp313-cu128-draft.json` 供給元レビュー・実 immutable host・`TRUSTED_CATALOGS` 登録）。
- UI未確認：通常デスクトップ右クリック項目（`FilterByItemTag{id}_0` 単一タグ・`SelectRangeTo{id}`）、`Ctrl+Enter` 実キー入力、未確認ビュー、実日本語IME、物理DPI、ハイコントラスト。専用OCR（引き続き保留）。

## 次の1件（P6 / UI）
- **ユーザー試用フィードバック対応または P6-3 外部条件整備**：候補21一式の実利用テストの結果（違和感・改善希望）があれば UI タスクとして対応し、なければ P6-3（`cp313-cu128` 供給元レビュー・immutable host）または残UI確認へ進む。
