# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- ブランチ / PR：`feat/winui3-production-mvp-20261011` / Draft [PR #5](https://github.com/jakymiku/Aredoko/pull/5)
- 直近UI改修：**全体 UI/UX ブラッシュアップ `UB-1`〜`UB-7`**（[ui-brushup-plan-20261118.md](docs/ui-brushup-plan-20261118.md) 完了、`data/development-tools/frontend-product23`）
- 最新配布候補：**候補23** `dist/portable-managed-20261118-23/Aredoko/Aredoko.exe`（source `a0cb221`、`RuntimeVerifyCard` 修正・`A01`〜`F06` 収録；`UB-1`〜`UB-7` 反映の新配布ZIP再梱包は次回区切り／P6時にまとめて実施）
- 受入済み直前予備：**候補21**（P6 Sandbox E2E PASS）、**候補19**（P6 Sandbox E2E PASS）
- 現行 frontend / 保持証拠：`data/development-tools/frontend-product23`（直前予備 `frontend-product22`、`frontend-product21`）、証拠 [run09_light](data/gui-ui-polish02/run09_light/summary.json) / [run10_dark](data/gui-ui-polish02/run10_dark/summary.json)

## 最近確認した変更
- **`UB-1`〜`UB-7` 全体UI改善（`frontend-product23`）**：用語統一（「AI検索データ」「AI検索を設定」・説明短縮）、検索バー二段選択 `[文字｜AI ▾]`、セグメント `[☰｜▦]`、カード余計な文言削減＆一覧3タグ/グリッド `#先頭+N` 要約、右詳細プレビュー上配置・統合タグ（クリック絞込チップ＋Enter確定＋`既存から`）、選択バー直押しアクション、フォルダ0件時選択パネル非表示、設定の主画面化（カテゴリタブ＋3ステップAI状況カード＋設定即時反映）、初回案内3カード化＆ガイド展開カード化を実装。
- **検証結果**：`Aredoko.Core.Tests`（`-c Release --no-restore`）、`test_winui_compile_stub`（`3` 件）、`test_ai_setup_plan`（`8` 件）、`frontend-product23` Portable publish＋`portable-build.json` 検査、および `gui-ui-polish02` Light（`run09_light`）・Dark（`run10_dark`）で `exit_code: 0`・`db_intact: true`・`originals_sha_match: true`・各5枚スクリーンショット目視確認 PASS。

## 利用者にできること
- `frontend-product23`（および次回の配布候補再梱包後）で、専門用語・説明文を抑えた主画面（二段検索切替、インライン設定＋即時反映、クリック絞込タグチップ、一目で状況が分かる3ステップAI表示）を試用できる。

## 未受入・未検証
- `frontend-product23` 同梱の配布候補24再梱包＋起動テスト全件＋オフライン Windows Sandbox E2E、および実機での登録解除ダイアログ・複数選択直押し・`NavAIStatus` クリック遷移・実AIモデル存在時の3ステップ表示確認。
- 引き続き未確認：実日本語IME、物理DPI、ハイコントラスト、P6-3（`cp313-cu128-draft.json` 供給元レビュー・実 immutable host・`TRUSTED_CATALOGS` 登録）。専用OCRは保留。

## 次の1件（P6 / UI）
- **配布候補24再梱包と実機／Sandbox試用、または P6-3 整備**：`frontend-product23` をベースに配布候補24を再梱包して `test_portable_startup`・Sandbox E2E または実機UI確認へ進む。
