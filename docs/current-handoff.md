# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- ブランチ / PR：`feat/winui3-production-mvp-20261011` / Draft [PR #5](https://github.com/jakymiku/Aredoko/pull/5)
- 最新実装コミット：`d1367f88d687b02ac05aeb53cea152072e35c7aa`（最新ドキュメント更新コミットで `HEAD` 前進）
- 最新配布候補：**候補16** `dist/portable-managed-20261115-16/Aredoko/Aredoko.exe`（`alpha-managed-20261115-16`、source `d1367f88d687b02ac05aeb53cea152072e35c7aa`、`663` files / `500,325,890` bytes、ZIP `215,199,578` bytes SHA-256 `1e6ddfb48c36e285e5089b6ab3d9bcdbfa4b790e8c70c43e29a1f261131ee826`）
  - 事前検証・ホストGUI・単体テストは PASS、**オフライン Windows Sandbox ゲスト起動は Application Control ポリシーにより BLOCKED**（1回試行で停止）。
- 受入済み直前予備：**候補15** `dist/portable-managed-20261115-15/Aredoko/Aredoko.exe`（source `921060675a42c9d9b9aefde94c613c35569d76d5`、同日 03:40 オフライン Sandbox PASS）
- 現行 frontend / 保持証拠：`data/development-tools/frontend-product16`（`373` entries）、証拠候補 `05` / `06` / `09`
- 削除済み（安全確認後）：`data/development-tools/frontend-product15`＋`dist/portable-managed-20261114-14` 計 `1,050` files / `881,159,779` bytes（[記録](data/capacity-20261113/cleanup-candidate14-frontend15.json)）

## 最近確認した変更
- **複数棚スコープ・棚ジャンプ・3棚要約**（`d1367f8`、[UI記録](docs/p3-continuous-browse.md)）：`ShelfProtocol.SummarizeNames` 追加＋`Aredoko.Core.Tests`（`-c Release --no-restore`、終了0、`SummarizeNames` 4件追加）PASS。棚ハブ「複数棚を開く」・スコープバー「棚を変更」・詳細「開く」／右クリック「所属する棚を開く」・スコープ中 `NavShelf` 再押下で棚ハブ復帰（`Navigation_ItemInvoked`）を実装し、`data/gui-shelf-scope01/run03/summary.json`（5シナリオ・`db_intact: true`・`exit_code: 0`・`originals_sha_match: true`）で PASS。
- **配布梱包・事前検証**（[配布設計](docs/lightweight-distribution.md)）：`dist/portable-managed-20261115-16/preflight.json`（`pass: true`、`readiness: "staging-only"`）、`tests/test_portable_startup.py` 19件＋`tests/test_windows_sandbox.py` 8件（計27件、32.075s OK）、`validation-kit.zip`（`3,601` bytes）・`data/ai-ui/managed-candidate16-online-manual/Aredoko.wsb` 生成。
- **オフラインSandbox BLOCKED**：`data/ai-ui/managed-candidate16-offline/run_trial.py` がゲスト内 `Start-Process C:\Aredoko\Aredoko.exe` で `"An Application Control policy has blocked this file."` により終了1（[failure.json](data/ai-ui/managed-candidate16-offline/evidence/failure.json)）。

## 利用者にできること
- 一覧・検索・詳細・棚からの複数棚スコープ絞込と切り替え、作品詳細／右クリックからの所属棚スコープ遷移、4棚以上の3棚要約＋ツールチップ確認。
- 検索全範囲選択・一括整理、`Shift`／右クリック範囲選択、棚ピッカー内新規棚作成と即時チェック維持、事前検証済み配布構成の生成（候補15まではオフラインSandbox起動確認済み）。

## 未受入・未検証
- **候補16 オフライン Windows Sandbox ゲスト実起動**：ゲスト Application Control ポリシーによるブロック（要因切り分け・対策待ち）。
- 候補16 オンライン新規基本環境ダウンロード Sandbox 実測（設定 `Aredoko.wsb` は生成済み、未起動）。
- UI未確認：`SelectRangeTo{id}` 右クリック実機操作、実日本語IME、物理DPI・ハイコントラスト。コード署名・実機配布受入。
- AI専用テスト：専用OCR（引き続き保留）、新規環境からの自動AI構築オンライン一連。

## 次の1件（P6 / UI）
- **P6（原因切り分け／ユーザー判断）**：Windows Sandbox 内で未署名 `Aredoko.exe` が Application Control ポリシーで拒否された要因（ホスト側 Smart App Control / CI ポリシー状態や署名要否）をユーザー環境で確認し、方針決定後に候補16のクリーンゲスト起動を再確認する。
- **UI（[現行優先表](docs/polish-roadmap-20261022.md#ux-priority-20261029)）**：一覧・検索／詳細／設定の残余使いやすさ改善（詳細パネル長文タグ・操作時のスクロールとフォーカス復帰、一覧・検索〜設定往復の導線整理）を進める。
