# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- ブランチ / PR：`feat/winui3-production-mvp-20261011` / Draft [PR #5](https://github.com/jakymiku/Aredoko/pull/5)
- 直近機能・試験コミット：`2499ab8`（以降にライセンス収集・MIT `LICENSE`・未署名配布方針確定を追加）
- 最新配布候補：**候補19** `dist/portable-managed-20261115-19/Aredoko/Aredoko.exe`（source `b8d703e07a9ed37de5eeb70eec1623fc90555c27`、`663` files / `500,421,635` bytes、ZIP `215,238,401` bytes SHA-256 `d2fcdbe7...`、`--self-test`・`preflight.json` PASS）
  - ※ 新規追加した `LICENSE` と `THIRD_PARTY_LICENSES/` の同梱は次回の P6 / 区切り再梱包で反映する。
- 受入済み直前予備：**候補15** `dist/portable-managed-20261115-15/Aredoko/Aredoko.exe`（2026-11-15 03:40 オフライン Sandbox PASS）
- 現行 frontend / 保持証拠：`data/development-tools/frontend-product18`、証拠候補 `05` / `06` / `09`、`data/ai-ui/managed-candidate17-offline/evidence`

## 最近確認した変更
- **ライセンス整備・未署名配布方針確定（2026-11-16）**：Aredoko 本体の [LICENSE](LICENSE)（MIT License）を追加し、[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) と通知群を更新。基本 ZIP 同梱物（FFmpeg/ffprobe `n8.1.3-34-ga35157abb9-20261109` GPLv3・§6注記、`.NET 10.0.14` / `WindowsAppSDK 2.5.1` / `WinML 2.1.74` / `WebView2 1.0.3719.77` BSD-3-Clause 原文 9件を [config/desktop-notices/](config/desktop-notices/manifest.json) へ格納）、基本環境（CPython `3.13.17` ＋ Pillow `12.3.0` を [basic-cp313-20261116](config/runtime-notices/basic-cp313-20261116/sources.json) へ収集）、現行 AI 環境（`cp313-cu128` 全 `44` パッケージ、`tokenizers==0.23.3` 補完付きで `collect_ai_runtime_notices.py` / `validate_for_source` `44/44` 完了、`redistribution_approved: false`）、モデル 2 件（Apache-2.0 収集済み）を監査。[package_release.py](tools/package_release.py) が `LICENSE` と `THIRD_PARTY_LICENSES/` を配布出力へ同梱し、`README.md` / `docs/user-guide.md` / `はじめに.txt` へ**未署名配布**と Windows Smart App Control 制約を明記。
- **実AI日本語検索＋カード右クリック確定タグ併用（`2499ab8`）**：[gui-ai-tag-scope01](data/gui-ai-tag-scope01/run02/result.json) `run02` で `EmbeddingGemma 2` + `ai-cu128` による日本語 AI 検索→カード右クリック確定タグ→`×` 解除→履歴「戻る」復元まで全通過（`exit_code: 0`・DB `ok`・原本SHA不変）。
- **P6-1/P6-2 候補19 実ZIP解凍〜別フォルダ再配置 E2E**：ゲスト内 SAC 無効化下で実 ZIP 解凍→登録・閲覧・タグ/お気に入り/棚保存→別パス再解凍→全保持（[P6 E2E 試験](data/ai-ui/managed-candidate19-p6-e2e/evidence/runs/run-20261116-002755-fbc67e/result.json) PASS、`normal_exit: 0`）。

## 利用者にできること
- 日本語AI検索と右クリック確定タグ絞り込み・解除・履歴復元の併用、実配布 ZIP の任意フォルダ展開と別場所への移行（SAC 無効環境、未署名配布）。同梱ライセンス・第三者通知の参照。

## 未受入・未検証
- 未署名配布を前提とした公開・配布ノート最終確認（コード署名は実施しない方針。Windows SAC `1` 環境では OS ポリシーによりブロックされる制約あり）。
- 候補19以降のライセンス同梱版での再梱包・オンライン初回ダウンロード Sandbox 一連、P6-3（`cp313-cu128-draft.json` の適用条項/供給元レビュー・実 immutable host・trusted registry）。
- UI未確認：未確認ビュー実UI操作、カード右クリック `SelectRangeTo{id}`、音声選択時 `BtnDetailFindSimilar`、長文タグ/棚スクロール、`AIAutoEnvironmentDialog` の「設定へ戻る」、実日本語IME、物理DPI、ハイコントラスト。専用OCR（引き続き保留）。

## 次の1件（P6 / UI）
- **UI（[現行優先表](docs/polish-roadmap-20261022.md#ux-priority-20261029)）** または **P6**：ライセンス確認・未署名配布方針が完了したため、次は P6（`LICENSE`/`THIRD_PARTY_LICENSES` 同梱後の再梱包やオンライン Sandbox / P6-3 整備）と並行して、残る UI 改善・実操作確認（`SelectRangeTo{id}`・音声類似・長文タグ/棚スクロール等）を進める。
