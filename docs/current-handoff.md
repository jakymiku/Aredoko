# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- ブランチ / PR：`feat/winui3-production-mvp-20261011` / Draft [PR #5](https://github.com/jakymiku/Aredoko/pull/5)
- 直近UI改修：**UI/UX ブラッシュアップ第1〜3弾 `UB-1`〜`UB-16` 完了**（[ui-brushup-plan-20261118.md](docs/ui-brushup-plan-20261118.md)、ソース `fd3ca9d`、`data/development-tools/frontend-product25`）
- 最新配布候補：**候補25** `dist/portable-managed-20261119-25/Aredoko/Aredoko.exe`（`UB-1`〜`UB-15` 全収録・source `fd3ca9d5074ff690afd7d7b55b70710733b2bb9c`、`676` payload / `501,609,748` bytes、`Aredoko.exe --self-test`・`preflight.json`・`Aredoko-windows-x64.zip`・`validation-kit.zip` PASS）
- 受入済み直前予備：**候補21**（P6 Sandbox E2E PASS）、**候補19**（P6 Sandbox E2E PASS）
- 現行 frontend / 保持証拠：`data/development-tools/frontend-product25`（直前予備 `frontend-product24`）、証拠 [run15d_light](data/gui-ui-polish02/run15d_light/summary.json) / [run16_dark](data/gui-ui-polish02/run16_dark/summary.json)（旧候補24・`frontend-product22`/`23` は退避済み）

## 最近確認した変更
- **`UB-13`〜`UB-15`（日常クイック導線・補助ダイアログ整理・文言修正）**：リスト行にクイック詳細ボタン `✎`（`ItemDetailsQuick{id}`、U1単クリック非自動展開は維持）、空状態「📁 登録フォルダを開く」（`BtnEmptyOpenFolders`）、右詳細 `DetailSaveBar` 上境界線・`FileProperties` 2列ボタン、`Folder_Drop`/`RestoreRootAsync`/`SearchModeDescription` 文言バグ修正を実施。さらに Backup・Restore・RuntimeCache・Diagnostics・RelatedTerms・TagSuggestions・AIAutoEnvironment の7ダイアログを `AredokoSurfaceStyle` カード整理、待機時 `ProgressBar` 非表示、`ScrollViewer` 保護、`AccentButtonStyle` 主CTA化、関連語「＋ 新規」＆削除無効ガードへ刷新。
- **UB-16 総合テスト結果**：最終編集後に `Aredoko.Core.Tests`（`-c Release --no-restore` exit 0）、Python 単体 `46` 件全 PASS（`test_winui_compile_stub`＋`test_native_combo_selection` 7件、`test_ai_setup_plan` 8件、`test_portable_startup`＋`test_windows_sandbox` 31件）、`frontend-product25` Portable publish（`373` entries、`inspect_portable` PASS）、[check.py](data/gui-ui-polish02/check.py)（`BypassSandbox: true`）Light（`run15d_light`）・Dark（`run16_dark`）全15項目 PASS（`exit_code: 0`・`db_intact: true`・`originals_sha_match: true`）＋主要画面＆新設ダイアログの Light/Dark スクリーンショット目視確認、および**候補25**再梱包・`--self-test`・`preflight.json`・`validation-kit.zip` 整合照合 PASS。

## 利用者にできること
- 最新配布候補25（[Aredoko.exe](dist/portable-managed-20261119-25/Aredoko/Aredoko.exe) または `dist/portable-managed-20261119-25/Aredoko-windows-x64.zip`）で `UB-1`〜`UB-15` 全改善を含むネイティブ WinUI 3 UI 一式を利用・検証できる。

## 未受入・未検証
- **候補25のオフライン Windows Sandbox E2E**（配布候補21以前の E2E を候補25の合格とみなさない）。
- `RestoreDialog` / `RuntimeCacheDialog` / `TagSuggestionsView` / `OpenAISettingsAsync` / `BtnEmptyOpenFolders` / 複数ページ移動 / 改修後ビューアの個別実UI確認、実AIモデル接続下表示、実日本語IME・物理DPI・ハイコントラスト。
- P6-3（`cp313-cu128-draft.json` 供給元レビュー・immutable host・`TRUSTED_CATALOGS` 登録）。専用OCRは保留。

## 次の1件（P6 / UI）
- **候補25の P6 オフライン Windows Sandbox E2E（保持済み `runtime-artifacts` 利用）＋並行して P6-3（`cp313-cu128` 供給元レビュー・immutable host）または残UI個別実機確認**：`dist/portable-managed-20261119-25` と `validation-kit.zip` で別Windows起動→登録→検索→閲覧→保存→再起動を確認する。
