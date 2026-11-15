# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- ブランチ / PR：`feat/winui3-production-mvp-20261011` / Draft [PR #5](https://github.com/jakymiku/Aredoko/pull/5)
- 直近実装コミット：`e29310c1635eec4f70631b566e4a0eeb05ed0fd2`（起動診断詳細化・カードタグ検索・詳細導線整理。本ドキュメント更新コミットで `HEAD` 前進）
- 最新配布候補：**候補17** `dist/portable-managed-20261115-17/Aredoko/Aredoko.exe`（source `e29310c1635eec4f70631b566e4a0eeb05ed0fd2`、`663` files / `500,397,856` bytes、ZIP `215,229,832` bytes SHA-256 `e110f523c4f4874c46ad6d3fb418846ba7b498ebbc8e4b9db36d938b4f707498`）
  - `--self-test`（終了0）・`preflight.json`（`pass: true`、`readiness: "staging-only"`）・単体試験 `34` 件 PASS。オフライン Sandbox（`data/ai-ui/managed-candidate17-offline/evidence/failure.json`）は、ホスト SAC `0` 一方でゲスト側 `verified_and_reputable_policy_state: 1` の App Control 拒否により **BLOCKED**。
- 受入済み直前予備：**候補15** `dist/portable-managed-20261115-15/Aredoko/Aredoko.exe`（source `921060675a42c9d9b9aefde94c613c35569d76d5`、2026-11-15 03:40 オフライン Sandbox PASS）
- 現行 frontend / 保持証拠：`data/development-tools/frontend-product16`（`portable-build.json` 再生成済み）、証拠候補 `05` / `06` / `09`、`data/ai-ui/managed-candidate16-offline/evidence`
- 削除済み（安全確認後）：`dist/portable-managed-20261115-16`（`674` files / `715,718,153` bytes、[記録](data/capacity-20261113/cleanup-candidate16.json)）

## 最近確認した変更
- **詳細ペイン・タグ検索と動画類似フライアウトの実機確認**（[UI記録](docs/p3-continuous-browse.md)）：`Tags` / `Shelf` に縦スクロールバー追加、`BtnFilterByActiveTag` の静的 `AutomationProperties.Name` を削除して動的件数・タグ名ラベル（1件時 `タグ「{tag}」で検索…` / 複数時 `この作品のタグで検索（N 件）…`）を修正、`SimilarityMenu` へ `FilterByItemTag{id}_0` / `FilterByItemTags{id}` を追加、`SaveAsync` のフォーカス復帰対象・`RevertEditsButton` 再同期・`DetailPreview.ContextFlyout` 再構築を更新。`Aredoko.Core.Tests`（終了0、以降 `Core` 無変更）・`frontend-product16` publish & `receipt_ok`・[gui-detail-actions03](data/gui-detail-actions03/run04/result.json) `run04` 4項目（`detail_tag_button_count_label` / `single_tag_detail_filter_search` / `video_detail_similarity_flyout` / `save_resets_revert_and_updates_tag_label`、`exit_code: 0`・`sqlite_integrity_ok: true`・`originals_sha_match: true`・`passed: true`）が PASS。
- **P6 起動診断強化・候補17梱包・オフライン Sandbox 検証**（[配布記録](docs/lightweight-distribution.md)）：`probe_release_runtime.py` に `'detail': str(error)`、`prepare_basic_runtime.py`・`launch_release.py` に非0終了時の `stdout`/`stderr` 送出を追加し、`test_basic_runtime.py`・`test_portable_startup.py`・`test_windows_sandbox.py` `34` 件 PASS（`38.629s`）。候補17は `Aredoko.exe --self-test` と `preflight.json` が PASS、オフライン Sandbox はゲスト `verified_and_reputable_policy_state: 1` により `Start-Process` で `"An Application Control policy has blocked this file."`（`startup-*.log` 生成前）となり BLOCKED。

## 利用者にできること
- 詳細ペインの保存済みタグから単一タグ直接表記／件数表記で一覧絞り込み、動画選択時の詳細ペイン「似た動画を探す…」3種検索、編集・保存後の取り消し状態・プレビュー右クリック即時同期、`SettingsDialog` ⇔ 各サブダイアログ・フォルダ/棚管理の往復が利用可能。

## 未受入・未検証
- コード署名／未署名に対するゲスト側 Smart App Control（`verified_and_reputable_policy_state: 1`）環境での実行（候補16の後段 `probe_release_runtime.py` 失敗再現、候補17オフライン／オンライン `managed-candidate17-online-manual/Aredoko.wsb` クリーン起動を含む）。
- UI未確認：ロック中セッションで `BLOCKED` となったカード右クリック項目（`FilterByItemTags{id}`・`FilterByItemTag{id}_0`・`SelectRangeTo{id}`）、音声選択時 `BtnDetailFindSimilar`、`TxtTags` / `TxtShelf` 長文スクロール実機操作、`AIAutoEnvironmentDialog` の「設定へ戻る」クリック、実日本語IME、物理DPI・ハイコントラスト。
- AI専用テスト：専用OCR（引き続き保留）、新規環境からの自動AI構築オンライン一連。

## 次の1件（P6 / UI）
- **P6**：署名済み／SAC許容可能な実環境またはゲスト条件での候補17クリーン起動確認と、候補16で見られた `prepare_basic_runtime.py` の `probe_release_runtime.py` 後段エラー切り分け（新規エラー詳細ログ出力を活用）。
- **UI（[現行優先表](docs/polish-roadmap-20261022.md#ux-priority-20261029)）**：インタラクティブセッション下でのカード右クリックタグ検索（`FilterByItemTags{id}` / `FilterByItemTag{id}_0`）・`SelectRangeTo{id}`・`TxtTags`/`TxtShelf` 長文スクロール・音声類似フライアウト実機確認と残余使いやすさ改善を進める。
