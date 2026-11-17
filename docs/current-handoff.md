# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- ブランチ / PR：`feat/winui3-production-mvp-20261011` / Draft [PR #5](https://github.com/jakymiku/Aredoko/pull/5)
- 直近確認済みコミット：`01eecad`（候補20 P6 E2E・ダーク確認；今回 **UI-A〜UI-D** と `frontend-product20` 検証を追加）
- 最新配布候補：**候補20** `dist/portable-managed-20261117-20/Aredoko/Aredoko.exe`（source `a14d61f...`、`--self-test`・`preflight.json`・オフライン Sandbox E2E PASS。今回の **UI-A〜UI-D** `frontend-product20` は次回区切り再梱包で反映）
- 受入済み直前予備：**候補19**（P6 E2E PASS）、**候補15**（旧基準 Sandbox PASS）
- 現行 frontend / 保持証拠：`data/development-tools/frontend-product20`（直前予備 `frontend-product19`、`frontend-product18` 整理済み）、証拠候補 `05` / `06` / `09`、`data/ai-ui/managed-candidate20-p6-e2e`

## 最近確認した変更
- **WinUI UI-A〜UI-D ブラッシュアップ（2026-11-18、`frontend-product20`）**：[polish-roadmap-20261022.md](docs/polish-roadmap-20261022.md#ux-priority-20261029) へタスク化し、[MainPage.xaml](src/Aredoko.WinUI/MainPage.xaml)・[MainPage.xaml.cs](src/Aredoko.WinUI/MainPage.xaml.cs)・[MainPage.ResultSessions.cs](src/Aredoko.WinUI/MainPage.ResultSessions.cs)・[MainPage.Settings.cs](src/Aredoko.WinUI/MainPage.Settings.cs) でボタンアイコン、サムネ背面プレート＋種別/棚/タグピルバッジ、グリッド時棚/タグ表示、詳細タグチップ削除・既存タグ追加・`Ctrl+Enter`保存、検索バー「タグ一覧…」（`BtnBrowseTags`）、設定3グループ整理を実装。`Aredoko.Core.Tests`（終了コード `0`）と [gui-ui-polish02](data/gui-ui-polish02/run04_light/summary.json)（Light `run04_light`・Dark [run05_dark](data/gui-ui-polish02/run05_dark/summary.json)、`exit_code: 0`・DB `ok`・原本SHA不変・画面各5枚）で PASS。
- **候補20 P6 再梱包・オフライン Sandbox E2E（`01eecad`）**：`LICENSE`（MIT）・`THIRD_PARTY_LICENSES/` 同梱 ZIP 展開→登録/閲覧/保存→別パス再配置→保持/検索/整合性 PASS。

## 利用者にできること
- Light/Dark とも角丸サムネ・種別/棚/タグバッジ付きカードを見やすく閲覧し（グリッド表示でも棚/タグ確認可）、検索バー「タグ一覧…」や詳細のタグチップ「×」・既存タグ追加で素早く整理できる。候補20 ZIP の任意展開・再配置・ライセンス参照対応。

## 未受入・未検証
- `frontend-product20` を反映した配布候補（候補21）再梱包、P6-3（`cp313-cu128-draft.json` 供給元レビュー・実 immutable host・`TRUSTED_CATALOGS` 登録）。
- UI未確認：通常デスクトップ右クリック項目（単一タグ `FilterByItemTag{id}_0`・範囲選択 `SelectRangeTo{id}`）、`Ctrl+Enter` 実キー入力、未確認ビュー、実日本語IME、物理DPI、ハイコントラスト。専用OCR（引き続き保留）。

## 次の1件（P6 / UI）
- **P6 候補21 再梱包・Sandbox 確認**（`frontend-product20` 反映）または **P6-3 外部条件整備**、あるいは必要に応じた **UI 追加磨き込み**（タグ一覧専用ビューや検索モード絞り込み整理など）。
