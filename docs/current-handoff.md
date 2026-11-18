# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- ブランチ / PR：`feat/winui3-production-mvp-20261011` / Draft [PR #5](https://github.com/jakymiku/Aredoko/pull/5)
- 直近UI改修：**全体 UI/UX ブラッシュアップ `UB-1`〜`UB-7`**（`6f205dc`、[ui-brushup-plan-20261118.md](docs/ui-brushup-plan-20261118.md) 完了、`data/development-tools/frontend-product23`）
- 最新配布候補：**候補24** `dist/portable-managed-20261119-24/Aredoko/Aredoko.exe`（source `6f205dc`、`675` payload / `501,472,265` bytes、ZIP `215,508,530` bytes SHA-256 `44766257...`、`--self-test`・`preflight.json`・`validation-kit.zip` PASS；Sandbox E2E 未実施）
- 受入済み直前予備：**候補21**（P6 Sandbox E2E PASS）、**候補19**（P6 Sandbox E2E PASS）
- 現行 frontend / 保持証拠：`data/development-tools/frontend-product23`（直前予備 `frontend-product22`；候補23・`frontend-product21` は `data/_cleanup_candidates/20261119-candidate24/` へ隔離）、証拠 [run11_light](data/gui-ui-polish02/run11_light/summary.json) / [run12_dark](data/gui-ui-polish02/run12_dark/summary.json)

## 最近確認した変更
- **`UB-1`〜`UB-7` 全体UI改善・候補24再梱包（`6f205dc`、`frontend-product23`）**：用語統一（「AI検索データ」「AI検索を設定」・説明短縮）、二段検索 `[文字｜AI ▾]`、セグメント `[☰｜▦]`、カード非重複メタ整理＆一覧3タグ/グリッド `#先頭+N`、右詳細プレビュー上配置・クリック絞込タグチップ＋統合入力、フォルダ0選択パネル非表示、設定の主画面化（カテゴリタブ＋3ステップAIカード＋即時反映）、初回案内3カード化を実装し、`bootstrap23.exe` とともに候補24へ収録。
- **検証結果**：`Aredoko.Core.Tests`（`-c Release --no-restore`）、`test_winui_compile_stub`（`3` 件）、`test_ai_setup_plan`（`8` 件）、`test_portable_startup`＋`test_windows_sandbox`（`31` 件 `BypassSandbox: true`）、候補24 `--self-test` / `preflight.json`、および `gui-ui-polish02` 拡張 Light（`run11_light`）・Dark（`run12_dark`：`detail_tag_chip_filter` / `settings_instant_and_categories` / `folder_hub_0sel_hidden` 含む）全 PASS（`exit_code: 0`・`db_intact: true`・`originals_sha_match: true`）。

## 利用者にできること
- 候補24（[Aredoko.exe](dist/portable-managed-20261119-24/Aredoko/Aredoko.exe)）で `UB-1`〜`UB-7` 刷新UI一式（二段検索切替、インライン設定＋即時反映、クリック絞込タグチップ、3ステップAI状況表示）をそのまま解凍・起動・別配置で試用できる。

## 未受入・未検証
- 候補24 のオフライン Windows Sandbox E2E、実機でのフォルダ登録解除確認ダイアログ・複数選択直押しボタン・実AIモデル存在時 `NavAIStatus` / 3ステップ表示確認。
- 引き続き未確認：実日本語IME、物理DPI、ハイコントラスト、P6-3（`cp313-cu128-draft.json` 供給元レビュー・実 immutable host・`TRUSTED_CATALOGS` 登録）。専用OCRは保留。

## 次の1件（P6 / UI）
- **候補24のユーザー実機試用／P6 Sandbox E2E または P6-3 整備**：候補24での新UI操作感と P6 配布動作（オフライン Sandbox E2E）を確認し、必要に応じ P6-3（`cp313-cu128` 供給元レビュー・immutable host）へ進む。
