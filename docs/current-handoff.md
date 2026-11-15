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
- **Sandbox fail-closed 化・旧スクリプト統一・候補19梱包**（[配布記録](docs/lightweight-distribution.md)）：[sandbox_trial.py](tools/sandbox_trial.py) で CIM 列挙失敗時は `SandboxProbeError` で即中止し、起動直前にのみ実行別 `evidence/runs/run-*` ＋一時 `.wsb` を生成して過去結果の削除を廃止、`managed-candidate12/14/15/16/17` の `run_trial.py` を `run_wsb_cli` へ統一。`tests/test_windows_sandbox.py`・`tests/test_tag_scope.py` `16` 件（`1.189s` OK）、実 CIM 拒否時の `SandboxProbeError` 送出、候補19の `--self-test` / `preflight.json` / ZIP が PASS。

## 利用者にできること
- 詳細欄やカード右クリックの保存タグ（最大30件・空白含む）から `「タグ：{tag}」×` チップで対象を完全一致絞り込みでき、先に入力した検索語（`海` 等）・AI検索モード・お気に入り等のビューや履歴戻る/進む・一括解除と組み合わせて利用可能。棚作成時のキャンセル挙動も作成前後で確認可能。

## 未受入・未検証
- 候補19のクリーンゲスト環境（オフライン／オンライン）および未署名・ゲスト側 Smart App Control 環境での起動検証（候補16後段 `probe_release_runtime.py` 失敗切り分けを含む）。
- UI未確認：実AIモデル環境でのタグ絞り込み併用、未確認ビュー実UI操作、カード右クリック `FilterByItemTags{id}` / `FilterByItemTag{id}_0` / `SelectRangeTo{id}`、音声選択時 `BtnDetailFindSimilar`、長文タグ/棚スクロール、`AIAutoEnvironmentDialog` の「設定へ戻る」、実日本語IME、物理DPI、ハイコントラスト。
- AI専用テスト：専用OCR（引き続き保留）、新規環境からの自動AI構築オンライン一連。

## 次の1件（P6 / UI）
- **P6**：安全化された `run_trial.py` による候補19クリーン起動確認および候補16後段 `probe_release_runtime.py` 詳細ログ切り分け（未署名/SACゲスト条件の整理を含む）。
- **UI（[現行優先表](docs/polish-roadmap-20261022.md#ux-priority-20261029)）**：インタラクティブセッション下でのカード右クリック操作（`FilterByItemTags{id}` / `SelectRangeTo{id}`）・音声類似フライアウト・長文タグ/棚スクロール確認と残余使いやすさ改善を進める。
