# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- ブランチ / PR：`feat/winui3-production-mvp-20261011` / Draft [PR #5](https://github.com/jakymiku/Aredoko/pull/5)
- 直近実装コミット：`1f1ef5948a82cfd5938d64be8cf274528fe307d9`（確定タグ完全一致絞り込み B案・全30タグ選択・棚作成キャンセル案内・安全 Sandbox ランナー。本ドキュメント更新コミットで `HEAD` 前進）
- 最新配布候補：**候補18** `dist/portable-managed-20261115-18/Aredoko/Aredoko.exe`（source `1f1ef5948a82cfd5938d64be8cf274528fe307d9`、`663` files / `500,415,918` bytes、ZIP `215,237,074` bytes SHA-256 `2a425f0a101b7992652dd8e246d9b2893a11c3f61cec4dcdf5d2c6555166ffba`、`validation-kit.zip` `6` files SHA-256 `18265900a59fd8d76a21ce6aaba3eb1e4d6098448024bbe7ceb04bcc7c1fca8f`）
  - `--self-test`（終了0）・`preflight.json`（`pass: true`、`readiness: "staging-only"`）が PASS。
- 受入済み直前予備：**候補15** `dist/portable-managed-20261115-15/Aredoko/Aredoko.exe`（source `921060675a42c9d9b9aefde94c613c35569d76d5`、2026-11-15 03:40 オフライン Sandbox PASS）
- 現行 frontend / 保持証拠：`data/development-tools/frontend-product17`（`portable-build.json` 照合済み）、証拠候補 `05` / `06` / `09`、`data/ai-ui/managed-candidate17-offline/evidence`
- 削除済み（安全確認後）：`dist/portable-managed-20261115-17`・`data/development-tools/frontend-product16`（計 `1,050` files / `881,420,467` bytes、[記録](data/capacity-20261113/cleanup-candidate17-frontend16.json)）

## 最近確認した変更
- **確定タグの独立絞り込み（B案）・全30タグ選択・棚作成キャンセル案内**（[UI記録](docs/p3-continuous-browse.md)）：`media_filters` / `ai_scope` / `ProductionCatalog` / `production_server` / 直接動画・音声検索類似 / `page_text` / `tag_candidate_search` / `tag_semantics` / `Aredoko.Core` へ `tag` スコープを統合し、WinUI へ `TagScopeBar`（`TxtTagScope`「タグ：{tag}」＋ `BtnClearTagScope`「×」）と履歴・条件解除・類似戻る連携を実装。20件打ち切りを撤廃して全30タグ選択と「〜で絞り込む」表記へ改め、`MainPage.ShelfPicker.cs` に「キャンセルしても棚は残る」案内（`ChooseShelfCreateNote`）を追加。`Aredoko.Core.Tests`（終了0）、バックエンド/起動 `98` 件（`70.405s` OK）、直接動画/音声 `58` 件（`38.003s` OK）、[gui-tag-scope01](data/gui-tag-scope01/run01/result.json) `run01` 全7項目（`exit_code: 0`・`sqlite_integrity_ok: true`・`originals_sha_match: true`・`passed: true`）が PASS。
- **P6 安全 Sandbox 終了処理・候補18梱包**（[配布記録](docs/lightweight-distribution.md)）：[sandbox_trial.py](tools/sandbox_trial.py) で既存 Sandbox 検出時は起動拒否（終了2）し自起動プロセス群のみ終了するよう修正（`tests/test_windows_sandbox.py` 2件追加・上記 `98` 件に含め PASS）。候補18の梱包・ZIP・validation-kit・`--self-test`・`preflight.json` が PASS。

## 利用者にできること
- 詳細欄やカード右クリックの保存タグ（最大30件・空白含む）から `「タグ：{tag}」×` チップで対象を完全一致絞り込みし、文字検索・履歴戻る/進む・一括解除と併用可能。棚作成時のキャンセル挙動も作成前後で確認可能。

## 未受入・未検証
- 候補18のクリーンゲスト環境（オフライン／オンライン）および未署名・ゲスト側 Smart App Control（`verified_and_reputable_policy_state: 1`）環境での起動検証（候補16後段 `probe_release_runtime.py` 失敗切り分けを含む）。
- UI未確認：AI有効時のUI操作上でのタグ絞り込み併用、カード右クリック `FilterByItemTags{id}` / `FilterByItemTag{id}_0` / `SelectRangeTo{id}`、音声選択時 `BtnDetailFindSimilar`、長文タグ/棚スクロール、`AIAutoEnvironmentDialog` の「設定へ戻る」、実日本語IME、物理DPI、ハイコントラスト。
- AI専用テスト：専用OCR（引き続き保留）、新規環境からの自動AI構築オンライン一連。

## 次の1件（P6 / UI）
- **P6**：署名済み／SAC許容可能な環境での候補18クリーン起動確認（候補16後段 `probe_release_runtime.py` 詳細ログ切り分けを含む）。
- **UI（[現行優先表](docs/polish-roadmap-20261022.md#ux-priority-20261029)）**：インタラクティブセッション下でのカード右クリック操作（`FilterByItemTags{id}` / `SelectRangeTo{id}`）・音声類似フライアウト・長文タグ/棚スクロール確認と残余使いやすさ改善を進める。
