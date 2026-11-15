# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- ブランチ / PR：`feat/winui3-production-mvp-20261011` / Draft [PR #5](https://github.com/jakymiku/Aredoko/pull/5)
- 直近基準コミット：`cceb746e93ca4cad1391de4d3b020d26172693f5`（設定往復導線・SAC要因記録。本更新コミットで `HEAD` 前進）
- 最新配布候補：**候補16** `dist/portable-managed-20261115-16/Aredoko/Aredoko.exe`（source `d1367f88d687b02ac05aeb53cea152072e35c7aa`、`663` files / `500,325,890` bytes、ZIP `215,199,578` bytes SHA-256 `1e6ddfb48c36e285e5089b6ab3d9bcdbfa4b790e8c70c43e29a1f261131ee826`）
  - 設定往復導線・詳細ペインUI改善・`tools/prepare_portable.py` 更新は `frontend-product16` 反映済み・候補16未同梱（次回 P6 再梱包時に反映）。ホスト SAC オフ後の候補16オフライン Sandbox 再確認は `Aredoko.exe` 起動通過後、`prepare_basic_runtime.py:108` の `probe_release_runtime.py` が終了コード `1` で失敗。
- 受入済み直前予備：**候補15** `dist/portable-managed-20261115-15/Aredoko/Aredoko.exe`（source `921060675a42c9d9b9aefde94c613c35569d76d5`、同日 03:40 オフライン Sandbox PASS）
- 現行 frontend / 保持証拠：`data/development-tools/frontend-product16`（`portable-build.json` 再生成済み）、証拠候補 `05` / `06` / `09`
- 削除済み（安全確認後）：`data/development-tools/frontend-product15`＋`dist/portable-managed-20261114-14` 計 `1,050` files / `881,159,779` bytes（[記録](data/capacity-20261113/cleanup-candidate14-frontend15.json)）

## 最近確認した変更
- **詳細ペインの編集取消・タグジャンプ・類似検索導線改善**（[UI記録](docs/p3-continuous-browse.md)）：`MainPage.xaml` / `MainPage.xaml.cs` に「元に戻す」（`BtnRevertEdits` + `revertStatusActive` で状態表示上書き抑止）・「保存タグで絞り込む」（`BtnFilterByActiveTag` + `FilterByActiveTag0`.. 20件・`FilterByTagAsync`）・「類似を検索」（`BtnDetailFindSimilar`、画像は即検索・動画/音声はフライアウト）を追加。`Aredoko.Core.Tests`（終了0、`revertStatusActive` 修正前は全件PASS・以降 `Core` 無変更）・`frontend-product16` publish ＆ `receipt_ok`・独立 GUI 試験 `data/gui-detail-actions02/run01/result.json`（6項目・`exit_code: 0`・`sqlite_integrity_ok: true`・`originals_sha_match: true`・`passed: true`）が PASS。
- **候補16 オフライン Windows Sandbox 再確認（SACオフ後）**（[配布記録](docs/lightweight-distribution.md)）：`py -3 -B data/ai-ui/managed-candidate16-offline/run_trial.py` を1回再実行し、ホスト SAC オフ後は `Start-Process C:\Aredoko\Aredoko.exe` の Application Control ブロックが解消し `cpython-3.13.17` 展開まで完了。直後の `tools/prepare_basic_runtime.py:108` による `probe_release_runtime.py` 呼び出しが終了コード `1`（`capture_output=True` により JSON エラー未記録、`failure.json` は `ui=False ready=False session=False`）で失敗。
- **設定往復導線・SAC 要因切り分け**（`cceb746`）：`SettingsTools` と各サブダイアログの往復導線（`data/gui-settings-roundtrip01/run01/result.json` 6経路 PASS）および SAC 強制切替要因（2026-11-14 Antigravity 更新由来 EA 継承・11-15 オフでホストブロック解消）を確認済み。

## 利用者にできること
- 詳細ペインから未保存変更を「元に戻す」、保存タグクリックで一覧絞り込み、詳細操作から画像「類似を検索」を実行でき、設定〜各サブダイアログ・フォルダ/棚管理の往復や複数棚スコープも利用可能。

## 未受入・未検証
- 候補16のオフライン Sandbox 後段失敗（`prepare_basic_runtime.py:108` の `probe_release_runtime.py` 終了コード `1` 原因特定待ち）および次候補17のオフライン／オンライン（`data/ai-ui/managed-candidate16-online-manual/Aredoko.wsb`）Windows Sandbox クリーンゲスト起動。
- UI未確認：`BtnDetailFindSimilar` の動画／音声フライアウト実機操作、`AIAutoEnvironmentDialog` の「設定へ戻る」GUIクリック、`SelectRangeTo{id}` 右クリック実機操作、実日本語IME、物理DPI・ハイコントラスト。コード署名・実機配布受入。
- AI専用テスト：専用OCR（引き続き保留）、新規環境からの自動AI構築オンライン一連。

## 次の1件（P6 / UI）
- **P6**：`tools/prepare_basic_runtime.py:108` で `probe_release_runtime.py` 失敗時の `stdout`/`stderr` をログ出力して Sandbox 終了コード `1` 原因を特定・修正し、設定往復＋詳細ペインUIを含む候補17を再梱包してオフライン Sandbox 再検証を行う。
- **UI（[現行優先表](docs/polish-roadmap-20261022.md#ux-priority-20261029)）**：詳細ペイン長文タグ・操作時のスクロールとフォーカス復帰、`BtnDetailFindSimilar` 動画/音声フライアウト実機確認など残余の使いやすさ改善を進める。
