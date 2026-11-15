# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- ブランチ / PR：`feat/winui3-production-mvp-20261011` / Draft [PR #5](https://github.com/jakymiku/Aredoko/pull/5)
- 直近実装コミット：`b8d703e07a9ed37de5eeb70eec1623fc90555c27`（タグ選択時の検索語/検索方法/ビュー保持・Sandbox fail-closed＋実行別証拠隔離・旧試験スクリプト統一。本ドキュメント更新コミットで `HEAD` 前進）
- 最新配布候補：**候補19** `dist/portable-managed-20261115-19/Aredoko/Aredoko.exe`（source `b8d703e07a9ed37de5eeb70eec1623fc90555c27`、`663` files / `500,421,635` bytes、ZIP `215,238,401` bytes SHA-256 `d2fcdbe700e1f26e7a68e90ac170328cf220102aad42a3f06f05069cdf50f631`、`validation-kit.zip` `6` files SHA-256 `55d3b5368b20863a5c446ba06122634379ea546d8686ca489d94ee08ed8b9e6d`）
  - `--self-test`（終了0）・`preflight.json`（`pass: true`、`readiness: "staging-only"`）が PASS。
- 受入済み直前予備：**候補15** `dist/portable-managed-20261115-15/Aredoko/Aredoko.exe`（source `921060675a42c9d9b9aefde94c613c35569d76d5`、2026-11-15 03:40 オフライン Sandbox PASS）
- 現行 frontend / 保持証拠：`data/development-tools/frontend-product18`（`portable-build.json` 照合済み）、証拠候補 `05` / `06` / `09`、`data/ai-ui/managed-candidate17-offline/evidence`
- 削除済み（安全確認後）：`dist/portable-managed-20261115-18`・`data/development-tools/frontend-product17`（計 `1,050` files / `881,455,755` bytes、[記録](data/capacity-20261113/cleanup-candidate18-frontend17.json)）

## 最近確認した変更
- **タグ選択時の検索条件保持（`b8d703e`）**（[UI記録](docs/p3-continuous-browse.md)）：`FilterByTagAsync` から `Query.Text = ""`、`SearchMode.SelectedIndex = 0`、`view == "history" || view == "unreviewed"` 上書き、`ClearSimilarity()` を除去し、先に入力した検索語・検索方法（AI検索含む）・表示ビュー・類似検索へ確定タグ絞り込みを追加できるようにした。`Aredoko.Core.Tests`（終了0）、[gui-tag-scope01](data/gui-tag-scope01/run02/result.json) `run02`（スタブ `AISearch` 併用、`query_before_tag_preserves_query` / `ai_search_preserves_mode_and_query_on_tag_pick` / `favorites_view_preserved_on_tag_pick` 含む全10項目、`exit_code: 0`・`sqlite_integrity_ok: true`・`originals_sha_match: true`・`passed: true`）が PASS。
- **Sandbox fail-closed 化・旧スクリプト統一・候補19梱包・オフラインSandbox通過（ゲストSAC解除併用）**（[配布記録](docs/lightweight-distribution.md)）：[sandbox_trial.py](tools/sandbox_trial.py) で CIM 失敗時は `SandboxProbeError` 即中止・実行別 `evidence/runs/run-*` 隔離とし、`managed-candidate12/14/15/16/17` を `run_wsb_cli` へ統一（`tests/test_windows_sandbox.py`・`tests/test_tag_scope.py` `16` 件 `OK`）。候補19の既定クリーン Sandbox はゲスト `verified_and_reputable_policy_state: 1` のため `NotSigned` `Aredoko.exe`（パッケージ内未署名PE計 `55` 本）が `CodeIntegrity` `ID 3033/3077/3118` で **BLOCKED**（[failure.json](data/ai-ui/managed-candidate19-offline/evidence/runs/run-20261115-225412-753c31/failure.json)）だったが、ゲスト内のみで `reg add VerifiedAndReputablePolicyState=0`＋`CiTool.exe -r`（`ID 3101→3102`、`6→4` ポリシー、再起動不要・ホスト無変更）を実行してから実施した [オフライン Sandbox 本試験](data/ai-ui/managed-candidate19-offline/evidence/runs/run-20261115-234859-d57272/result.json) では、`probe_release_runtime.py` PASS（`cpython 3.13.17` 64bit）・`WinUI ready_sent`・`mode: "production"`・`normal_exit: 0` を確認した。

## 利用者にできること
- 詳細欄やカード右クリックの保存タグ（最大30件・空白含む）から `「タグ：{tag}」×` チップで対象を完全一致絞り込みでき、先に入力した検索語（`海` 等）・AI検索モード・お気に入り等のビューや履歴戻る/進む・一括解除と組み合わせて利用可能。棚作成時のキャンセル挙動も作成前後で確認可能。

## 未受入・未検証
- 未署名 `Aredoko.exe` 他 `55` 本に対する SAC 有効（`1`）実機環境でのコード署名／起動受け入れ、および候補19のオンライン Sandbox 初回ダウンロード一連。
- UI未確認：実AIモデル環境でのタグ絞り込み併用、未確認ビュー実UI操作、カード右クリック `FilterByItemTags{id}` / `FilterByItemTag{id}_0` / `SelectRangeTo{id}`、音声選択時 `BtnDetailFindSimilar`、長文タグ/棚スクロール、`AIAutoEnvironmentDialog` の「設定へ戻る」、実日本語IME、物理DPI、ハイコントラスト。
- AI専用テスト：専用OCR（引き続き保留）、新規環境からの自動AI構築オンライン一連。

## 次の1件（P6 / UI）
- **UI（[現行優先表](docs/polish-roadmap-20261022.md#ux-priority-20261029)）**：インタラクティブセッション下でのカード右クリック操作（`FilterByItemTags{id}` / `SelectRangeTo{id}`）・音声類似フライアウト・長文タグ/棚スクロール確認と残余使いやすさ改善を進める。
- **P6**：ゲスト内 SAC 解除方式でのオンライン Sandbox 一連（初回公式取得確認）を必要に応じて実施し、公開配布に向けては未署名 `55` 本の署名方針（または SAC 無効環境前提）を別途整理する。
