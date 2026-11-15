# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- ブランチ / PR：`feat/winui3-production-mvp-20261011` / Draft [PR #5](https://github.com/jakymiku/Aredoko/pull/5)
- 直近確認済みコミット：`49fd1de`（MIT `LICENSE`・第三者ライセンス通知・未署名配布方針確定；今回 UI 仕上げと検証を追加）
- 最新配布候補：**候補19** `dist/portable-managed-20261115-19/Aredoko/Aredoko.exe`（`--self-test`・`preflight.json`・Sandbox E2E PASS）
  - ※ 新規追加した `LICENSE` / `THIRD_PARTY_LICENSES/` および `frontend-product19`（UI仕上げ）は次回の P6 / 区切り再梱包で反映する。
- 受入済み直前予備：**候補15** `dist/portable-managed-20261115-15/Aredoko/Aredoko.exe`（2026-11-15 03:40 オフライン Sandbox PASS）
- 現行 frontend / 保持証拠：`data/development-tools/frontend-product19`（直前予備 `frontend-product18`）、証拠候補 `05` / `06` / `09`、`data/ai-ui/managed-candidate17-offline/evidence`

## 最近確認した変更
- **WinUI 仕上げ・狭幅/音声類似/設定往復 GUI 検証（2026-11-16、`frontend-product19`）**：[MainPage.xaml](src/Aredoko.WinUI/MainPage.xaml) で `TagScopeBar` / `ShelfScopeBar` の `MaxWidth="360"` ＋ `StackPanel` を `*` / `Auto` の `Grid` へ刷新し、[MainPage.xaml.cs](src/Aredoko.WinUI/MainPage.xaml.cs) で `AddSimilarityMenuItems` を共通化して音声直接音響類似ラベルを「音の響き・音響が似た音声・曲を探す」へ明確化＋ツールチップ付与。`Aredoko.Core.Tests`（終了コード `0`）と [gui-ui-polish01](data/gui-ui-polish01/run06/summary.json) `run06`（`1200×800` 詳細展開中 `TagScopeBar`/`ShelfScopeBar` 無見切れ、30タグ `120px` スクロール、音声類似フライアウト、`Settings -> AIAutoEnvironment -> BtnBackToSettings` 往復、`exit_code: 0`・DB `ok`・原本SHA不変、画像5枚確認）で PASS。
- **ライセンス整備・未署名配布方針確定（`49fd1de`）**：[LICENSE](LICENSE)（MIT）・[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)・[desktop-notices](config/desktop-notices/manifest.json)（9件）・[basic-cp313-20261116](config/runtime-notices/basic-cp313-20261116/sources.json)・`cp313-cu128` `44/44`・モデル2件監査・[package_release.py](tools/package_release.py) の `LICENSE` / `THIRD_PARTY_LICENSES/` 同梱と未署名案内を完了。
- **実AI日本語検索＋カード右クリック確定タグ併用（`2499ab8`）**：[gui-ai-tag-scope01](data/gui-ai-tag-scope01/run02/result.json) `run02` PASS；[候補19 P6 実ZIP E2E](data/ai-ui/managed-candidate19-p6-e2e/evidence/runs/run-20261116-002755-fbc67e/result.json) PASS。

## 利用者にできること
- 詳細ペイン展開中の `1200px` 幅でも見切れずに長文タグ・複数棚スコープを操作・解除でき、音声の「内容が似た音声・曲」と「音の響き・音響が似た音声・曲」を区別して探し、「設定 ↔ AI環境を自動構築」を往復できる。日本語AI検索＋右クリック確定タグ併用、同梱ライセンス参照。

## 未受入・未検証
- 候補19以降の `LICENSE` / `THIRD_PARTY_LICENSES/` / `frontend-product19` 同梱版の再梱包、オンライン初回ダウンロード Sandbox、P6-3（`cp313-cu128-draft.json` 供給元レビュー・実 immutable host・trusted registry）。
- UI未確認：通常デスクトップ右クリック項目（単一タグ `FilterByItemTag{id}_0`・範囲選択 `SelectRangeTo{id}`）、未確認ビュー実UI操作、実日本語IME、物理DPI、ハイコントラスト。専用OCR（引き続き保留）。

## 次の1件（P6 / UI）
- **P6 再梱包・Sandbox確認**：今回の UI 仕上げ（`frontend-product19`）と `LICENSE` / `THIRD_PARTY_LICENSES/` を含めた配布候補（候補20）を再梱包し、`--self-test`・オフライン Sandbox / 必要に応じたオンライン Sandbox と P6-3 整備へ進む。
