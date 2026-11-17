# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- ブランチ / PR：`feat/winui3-production-mvp-20261011` / Draft [PR #5](https://github.com/jakymiku/Aredoko/pull/5)
- 直近機能コミット：`a14d61f`（UI仕上げ・GUI検証）、`49fd1de`（MIT `LICENSE`・第三者ライセンス・未署名配布方針）
- 最新配布候補：**候補20** `dist/portable-managed-20261117-20/Aredoko/Aredoko.exe`（source `a14d61f3201efcc4f029f066f7e2b49a2bf7cdfb`、`675` files / `501,227,184` bytes、ZIP `215,414,749` bytes SHA-256 `9ff6cf59...`、`--self-test`・`preflight.json`・`validation-kit.zip`・オフライン Sandbox E2E PASS）
- 受入済み直前予備：**候補19** `dist/portable-managed-20261115-19/Aredoko/Aredoko.exe`（P6 E2E PASS）、**候補15**（旧基準 Sandbox PASS）
- 現行 frontend / 保持証拠：`data/development-tools/frontend-product19`（直前予備 `frontend-product18`）、証拠候補 `05` / `06` / `09`、`data/ai-ui/managed-candidate17-offline/evidence`、`data/ai-ui/managed-candidate20-p6-e2e`

## 最近確認した変更
- **候補20 P6 再梱包・オフライン Windows Sandbox E2E・ダークテーマ確認（2026-11-17）**：[package_release.py](tools/package_release.py) で `frontend-product19`＋`LICENSE`（MIT）＋`THIRD_PARTY_LICENSES/`（`11` files）を候補20へ統合し、[managed-candidate20-p6-e2e](data/ai-ui/managed-candidate20-p6-e2e/evidence/runs/run-20261117-213938-348f3a/result.json) で `<Networking>Disable</Networking>`・ゲスト内SAC無効化下の実ZIP展開→同梱ライセンス確認→登録/閲覧/保存→別フォルダ再配置→保持/検索/DB・原本SHA整合まで PASS（ホストSAC `0` 不変）。あわせて [gui-ui-polish01](data/gui-ui-polish01/run07_dark/summary.json) `run07_dark` でダークテーマ 5 項目と画像4枚を目視確認。関連単体テスト `tests.test_release_activation`（直結 Python）`17/17 OK`。
- **WinUI 仕上げ・Light GUI 検証（`a14d61f`、`frontend-product19`）**：[MainPage.xaml](src/Aredoko.WinUI/MainPage.xaml)（`TagScopeBar` / `ShelfScopeBar` レスポンシブ `Grid`化）と [MainPage.xaml.cs](src/Aredoko.WinUI/MainPage.xaml.cs)（`AddSimilarityMenuItems` 共通化＋音声音響類似ラベル明確化）。`Aredoko.Core.Tests` 終了コード `0`、[gui-ui-polish01](data/gui-ui-polish01/run06/summary.json) `run06` PASS。
- **実AI日本語検索＋カード右クリック確定タグ併用（`2499ab8`）**：[gui-ai-tag-scope01](data/gui-ai-tag-scope01/run02/result.json) `run02` PASS。

## 利用者にできること
- `LICENSE` / `THIRD_PARTY_LICENSES/` 同梱の最新配布 ZIP（候補20）を任意フォルダへ展開し別フォルダへ無損失で移行できる（未署名・SAC無効環境）。Light/Dark の `1200px` 詳細展開時でも見切れずタグ/棚スコープ・音声類似（AI内容 vs 直接音響）・設定往復を使える。

## 未受入・未検証
- 更新版配布での再オンライン初回ダウンロード確認（候補12でオンライン受入済み・新規ダウンロード試験は要事前確認）、P6-3（`cp313-cu128-draft.json` 供給元レビュー・実 immutable host・`TRUSTED_CATALOGS` 登録）。
- UI未確認：通常デスクトップ右クリック項目（単一タグ `FilterByItemTag{id}_0`・範囲選択 `SelectRangeTo{id}`）、未確認ビュー実UI操作、実日本語IME、物理DPI、ハイコントラスト。専用OCR（引き続き保留）。

## 次の1件（P6 / UI）
- **P6-3 外部条件整備または UI 残項目確認**：P6 は候補20でローカル再梱包・オフライン Sandbox 検証まで完了したため、次はユーザー確認が必要なオンライン/P6-3（`cp313-cu128` 供給元レビュー・immutable host）を進めるか、通常デスクトップ操作で残る右クリック項目（`FilterByItemTag{id}_0` / `SelectRangeTo{id}`）・物理DPI・IME等の残UI確認へ進む。
