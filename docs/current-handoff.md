# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- ブランチ / PR：`feat/winui3-production-mvp-20261011` / Draft [PR #5](https://github.com/jakymiku/Aredoko/pull/5)
- 直近UI改修：**UI/UX 直感性改善第2弾 `UB-8`〜`UB-12`**（[ui-brushup-plan-20261118.md](docs/ui-brushup-plan-20261118.md#L657)、`data/development-tools/frontend-product24`）
- 最新配布候補：**候補24** `dist/portable-managed-20261119-24/Aredoko/Aredoko.exe`（`UB-1`〜`UB-7` 版 source `e7464ad`、`675` payload / `501,472,265` bytes、`preflight.json`・`validation-kit.zip` PASS；`UB-8`〜`UB-12` は次回の区切りで再梱包予定）
- 受入済み直前予備：**候補21**（P6 Sandbox E2E PASS）、**候補19**（P6 Sandbox E2E PASS）
- 現行 frontend / 保持証拠：`data/development-tools/frontend-product24`（直前予備 `frontend-product23`）、証拠 [run13_light](data/gui-ui-polish02/run13_light/summary.json) / [run14_dark](data/gui-ui-polish02/run14_dark/summary.json)

## 最近確認した変更
- **`UB-8`〜`UB-12` 直感性・視覚階層改善（`frontend-product24`）**：選択中トグルの枠強調＋主CTA専用青（`SelectedSegmentButtonStyle`）、AI未設定時の検索バー直下インライン案内、条件ピル統一、リスト行右端クイック操作（`ItemFavToggle{id}` / `ItemOpenQuick{id}`）、簡潔フッター＆直接移動、右詳細の種別バッジ・星 `ToggleButton`・タグ二重表示解消＆追加専用欄（`draftTags`＋`BtnCommitTagInput`）・クリック棚チップ・未編集時保存バー自動格納、棚レイアウトアイコン上書きバグ修正（`MainPage.Shelves.cs:225`）、フォルダカード「作品を見る」＋「⟳ 更新」・D&Dヒント、設定2列アクションカード＋`BtnAISetupPlan`＋AI準備ウィザード自動確認・AI設定カード化、ビューア位置表示・失敗時限定リトライを実装。
- **検証結果**：最終編集後に `Aredoko.Core.Tests`（`-c Release --no-restore` exit 0）、`tests.test_winui_compile_stub`（`3` 件 OK）、`frontend-product24` Portable publish（`portable-build.json` `373` entries、`inspect_portable` PASS）、および [check.py](data/gui-ui-polish02/check.py)（`BypassSandbox: true`）Light（`run13_light`）・Dark（`run14_dark`）全項目 PASS（`exit_code: 0`・`db_intact: true`・`originals_sha_match: true`）＋各スクリーンショット目視確認済み。

## 利用者にできること
- [frontend-product24](data/development-tools/frontend-product24/Aredoko.WinUI.exe) で `UB-8`〜`UB-12` を含む最新 WinUI UI 一式を専用検証環境で確認できる。通常同梱版の試用は候補24（[Aredoko.exe](dist/portable-managed-20261119-24/Aredoko/Aredoko.exe)）を利用する。

## 未受入・未検証
- 複数ページ時の直接ページ移動ボタン、`AISetupPlanDialog` 自動確認・`OpenAISettingsAsync` 実UI、`ImageViewerView` / `ArchiveReaderView` / `VideoPlayerView` 今回の改修後実表示、実AIモデル下 `NavAIStatus` / 3ステップ表示。
- 候補25以降の再梱包＋オフライン Windows Sandbox E2E、実日本語IME、物理DPI、ハイコントラスト、P6-3（`cp313-cu128-draft.json` 供給元レビュー・immutable host・`TRUSTED_CATALOGS` 登録）。専用OCRは保留。

## 次の1件（P6 / UI）
- **配布候補の再梱包＋P6 オフライン Windows Sandbox E2E（または P6-3）**：`UB-8`〜`UB-12`（`frontend-product24`）を含めた次期配布候補を `prepare_portable.py` 等で再梱包してオフライン Sandbox E2E で確認し、並行して P6-3（`cp313-cu128` 供給元レビュー・immutable host）へ進む。
