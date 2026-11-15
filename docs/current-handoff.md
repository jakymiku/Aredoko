# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- ブランチ / PR：`feat/winui3-production-mvp-20261011` / Draft [PR #5](https://github.com/jakymiku/Aredoko/pull/5)
- 直近実装コミット：`b8d703e07a9ed37de5eeb70eec1623fc90555c27`（タグ選択時の検索条件保持・Sandbox fail-closed＋実行別証拠隔離。以降に P6-1/P6-2 実績追記と実AI日本語検索＋カード右クリック確定タグ併用GUI検証を追加）
- 最新配布候補：**候補19** `dist/portable-managed-20261115-19/Aredoko/Aredoko.exe`（source `b8d703e07a9ed37de5eeb70eec1623fc90555c27`、`663` files / `500,421,635` bytes、ZIP `215,238,401` bytes SHA-256 `d2fcdbe700e1f26e7a68e90ac170328cf220102aad42a3f06f05069cdf50f631`、`validation-kit.zip` `6` files SHA-256 `55d3b5368b20863a5c446ba06122634379ea546d8686ca489d94ee08ed8b9e6d`）
  - `--self-test`（終了0）・`preflight.json`（`pass: true`、`readiness: "staging-only"`）が PASS。
- 受入済み直前予備：**候補15** `dist/portable-managed-20261115-15/Aredoko/Aredoko.exe`（source `921060675a42c9d9b9aefde94c613c35569d76d5`、2026-11-15 03:40 オフライン Sandbox PASS）
- 現行 frontend / 保持証拠：`data/development-tools/frontend-product18`（`portable-build.json` 照合済み）、証拠候補 `05` / `06` / `09`、`data/ai-ui/managed-candidate17-offline/evidence`
- 削除済み（安全確認後）：`dist/portable-managed-20261115-18`・`data/development-tools/frontend-product17`（計 `1,050` files / `881,455,755` bytes、[記録](data/capacity-20261113/cleanup-candidate18-frontend17.json)）

## 最近確認した変更
- **タグ選択時の検索条件保持（`b8d703e`）**（[UI記録](docs/p3-continuous-browse.md)）：`FilterByTagAsync` から `Query.Text = ""`、`SearchMode.SelectedIndex = 0`、`view == "history" || view == "unreviewed"` 上書き、`ClearSimilarity()` を除去し、先に入力した検索語・検索方法（AI検索含む）・表示ビュー・類似検索へ確定タグ絞り込みを追加できるようにした。`Aredoko.Core.Tests`（終了0）、[gui-tag-scope01](data/gui-tag-scope01/run02/result.json) `run02`（スタブ `AISearch` 併用、`query_before_tag_preserves_query` / `ai_search_preserves_mode_and_query_on_tag_pick` / `favorites_view_preserved_on_tag_pick` 含む全10項目、`exit_code: 0`・`sqlite_integrity_ok: true`・`originals_sha_match: true`・`passed: true`）が PASS。
- **実AI日本語検索＋カード右クリック確定タグ併用（2026-11-16）**（[UI記録](docs/p3-continuous-browse.md)）：既存検証済み `EmbeddingGemma 2` + `ai-cu128` と生成 PNG 4件（`indexed: 4`）・`frontend-product18` を用い、ホスト通常デスクトップ（`WinSta0\Default`）上で [gui-ai-tag-scope01](data/gui-ai-tag-scope01/run02/result.json) `run02` を実行。`両方で探す（AI）` ＋ `"空や森や海などの風景"`（`4 件`）→ `Item1` 右クリック `FilterByItemTags1` → `「青空」で絞り込む` で検索語・AIモード保持のまま `1 件`（`タグ：青空`）→ `×` で元の `4 件` 復帰 → 履歴「戻る」で `タグ：青空`・検索語・AIモード・`1 件` 復元（[final-after-back.png](data/gui-ai-tag-scope01/run02/final-after-back.png)）まで全通過（`exit_code: 0`・DB `ok`・原本SHA不変・`passed: true`）。
- **P6-1/P6-2 候補19 実ZIP解凍〜再配置 E2E＋ゲストSAC切り分け**（[配布記録](docs/lightweight-distribution.md)）：[sandbox_trial.py](tools/sandbox_trial.py) で CIM 失敗即中止・実行別証拠隔離と旧 `run_trial.py` 統一を実施（`tests/test_windows_sandbox.py`・`tests/test_tag_scope.py` `16` 件 `OK`）。候補19の既定クリーン Sandbox はゲスト `verified_and_reputable_policy_state: 1` のため `NotSigned` `Aredoko.exe`（パッケージ内未署名PE計 `55` 本）が `ID 3033/3077/3118` でブロックされたが、ゲスト内のみで `VerifiedAndReputablePolicyState=0` ＋ `CiTool.exe -r` を実行する [オフライン本試験](data/ai-ui/managed-candidate19-offline/evidence/runs/run-20261115-234859-d57272/result.json) と、`Aredoko-windows-x64.zip` 解凍（`Desktop\AredokoV1`）→UI登録・検索・プレビュー/CBZ閲覧・タグ/お気に入り/棚保存→削除→別パス `Desktop\AredokoV2` 再解凍起動→全保持・`after-restart.png`・DB `ok`・原本SHA不変を検証する [P6 E2E 試験](data/ai-ui/managed-candidate19-p6-e2e/evidence/runs/run-20261116-002755-fbc67e/result.json) が PASS（いずれも `normal_exit: 0`、ホスト無変更）。

## 利用者にできること
- 詳細欄やカード右クリックの保存タグ（最大30件・空白含む）から `「タグ：{tag}」×` チップで対象を完全一致絞り込みでき、先に入力した検索語（日本語AI検索含む）・AI検索モード・お気に入り等のビューや履歴戻る/進む・一括解除と組み合わせて利用可能。実配布 ZIP を任意フォルダへ展開し別場所へ更新・移動しても登録/タグ/棚/設定を保持する（SAC 無効環境またはゲスト解除時）。

## 未受入・未検証
- 未署名 `Aredoko.exe` 他 `55` 本に対する SAC 有効（`1`）実機環境でのコード署名・起動受け入れ、候補19のオンライン Sandbox 初回ダウンロード一連、および P6-3（`cp313-cu128-draft.json` の適用条項/供給元レビュー・実 immutable host・trusted registry・新規オンライン AI 構築一連）。
- UI未確認：未確認ビュー実UI操作、カード右クリック `SelectRangeTo{id}`、音声選択時 `BtnDetailFindSimilar`、長文タグ/棚スクロール、`AIAutoEnvironmentDialog` の「設定へ戻る」、実日本語IME、物理DPI、ハイコントラスト。
- AI専用テスト：専用OCR（引き続き保留）、新規環境からの自動AI構築オンライン一連。

## 次の1件（P6 / UI）
- **P6（外部/公開側整理・任意確認）**：候補19でのオンライン初回取得（要ユーザー事前確認）の要否判断、未署名 `55` 本の署名方針、または P6-3 AI配布レシピの供給元/条項/registry 条件整理を進める。
- **UI（[現行優先表](docs/polish-roadmap-20261022.md#ux-priority-20261029)）**：基本 ZIP のクリーン起動〜再配置 E2E および実AI検索×右クリック確定タグ併用・解除・戻る復元が確認できたため、残るインタラクティブ UI 未確認項目（`SelectRangeTo{id}`・音声類似・長文タグ/棚スクロール等）と使いやすさ改善へ進む。
