# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- ブランチ / PR：`feat/winui3-production-mvp-20261011` / Draft [PR #5](https://github.com/jakymiku/Aredoko/pull/5)
- 直近基準コミット：`c2de24e6cee7ef4e8fc927789d7039d7014ef1f4`（候補16記録。本更新コミットで `HEAD` 前進）
- 最新配布候補：**候補16** `dist/portable-managed-20261115-16/Aredoko/Aredoko.exe`（source `d1367f88d687b02ac05aeb53cea152072e35c7aa`、`663` files / `500,325,890` bytes、ZIP `215,199,578` bytes SHA-256 `1e6ddfb48c36e285e5089b6ab3d9bcdbfa4b790e8c70c43e29a1f261131ee826`）
  - 下記「設定往復導線整理」の UI 変更・`tools/prepare_portable.py` 更新は `frontend-product16` 反映済み・候補16未同梱（次回 P6 再梱包時に反映）。ホスト Smart App Control オフ後、候補16のオフライン Windows Sandbox 再確認は未実施。
- 受入済み直前予備：**候補15** `dist/portable-managed-20261115-15/Aredoko/Aredoko.exe`（source `921060675a42c9d9b9aefde94c613c35569d76d5`、同日 03:40 オフライン Sandbox PASS）
- 現行 frontend / 保持証拠：`data/development-tools/frontend-product16`（`portable-build.json` 再生成済み）、証拠候補 `05` / `06` / `09`
- 削除済み（安全確認後）：`data/development-tools/frontend-product15`＋`dist/portable-managed-20261114-14` 計 `1,050` files / `881,159,779` bytes（[記録](data/capacity-20261113/cleanup-candidate14-frontend15.json)）

## 最近確認した変更
- **設定〜各サブダイアログ・管理画面の往復導線整理**（[UI記録](docs/p3-continuous-browse.md)）：`SettingsTools`（5行）に「登録フォルダを管理」（`BtnSettingsOpenFolders`）・「棚一覧を管理」（`BtnSettingsOpenShelves`）を追加し、設定から開いた各サブダイアログへ `BtnBackToSettings`（「設定へ戻る」）、バックアップから開いた復旧ガイド／復元へ `BtnBackToBackup`（「バックアップと復元へ戻る」）を実装（`MainPage.Settings.cs` / `Backup` / `Restore` / `RuntimeCache` / `AIAutoEnvironment` / `GettingStarted`）。
- **テスト・起動検証**：ホスト Smart App Control オフ（`VerifiedAndReputablePolicyState = 0`）後に `Aredoko.Core.Tests`（終了0）、`frontend-product16` publish・`portable-build.json` 再生成・`tests/test_portable_startup.py` 19件（`33.190s` OK）、`tools/prepare_portable.py` への展開後 `Aredoko.exe --self-test` 追加と候補16 `--self-test`（終了0）、独立GUI試験 `data/gui-settings-roundtrip01/run01/result.json`（6経路・`exit_code: 0`・`sqlite_integrity_ok: true`・`originals_sha_match: true`・`passed: true`）が PASS。
- **Smart App Control 要因切り分け**：2026-11-14 の Antigravity 自動更新で `$KERNEL.SMARTLOCKER.ORIGINCLAIM` がビルド子プロセス生成物へ継承され、11-15 `14:45:26` JST に SAC が評価 (`2`)→強制 (`1`) へ切替（`EventID 3099`/`5007`）。`16:17:55` のオフ設定でホスト試験ブロックは解消。

## 利用者にできること
- 設定から診断・バックアップ/復元/復旧ガイド・キャッシュ・初回案内・フォルダ管理・棚一覧へ迷わず往復でき、複数棚スコープ・作品からの棚ジャンプ・3棚要約・ページ跨ぎ範囲選択・棚ピッカー内新規作成を利用可能。

## 未受入・未検証
- 候補16以降（または次候補17）のオフライン／オンライン（`data/ai-ui/managed-candidate16-online-manual/Aredoko.wsb`）Windows Sandbox クリーンゲスト実起動。
- UI未確認：`AIAutoEnvironmentDialog` の「設定へ戻る」GUIクリック、`SelectRangeTo{id}` 右クリック実機操作、実日本語IME、物理DPI・ハイコントラスト。コード署名・実機配布受入。
- AI専用テスト：専用OCR（引き続き保留）、新規環境からの自動AI構築オンライン一連。

## 次の1件（P6 / UI）
- **P6**：オフライン Windows Sandbox 起動再確認（SAC オフ後のゲスト挙動切り分け／設定往復含む再梱包または候補16再試行）と、承認範囲内での新規基本環境テスト手順の整理。
- **UI（[現行優先表](docs/polish-roadmap-20261022.md#ux-priority-20261029)）**：詳細ペイン長文タグ・操作時のスクロールとフォーカス復帰など、一覧・詳細・整理の残余使いやすさ改善を進める。
