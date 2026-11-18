# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- ブランチ / PR：`feat/winui3-production-mvp-20261011` / Draft [PR #5](https://github.com/jakymiku/Aredoko/pull/5)
- 直近機能コミット：`a0cb221`（**`RuntimeVerifyCard` 不透明化・フッターバー配置**・`frontend-product22`）、`f4f3cd3`（**62項目 UI文言・導線改善 `A01`〜`F06`**・`frontend-product21`）
- 最新配布候補：**候補23** `dist/portable-managed-20261118-23/Aredoko/Aredoko.exe`（source `a0cb22112aeea0438520063b8e846d4d58b5d7d7`、`675` files / `501,326,439` bytes、ZIP `215,460,516` bytes SHA-256 `1006cced...`、`--self-test`・`preflight.json`・`validation-kit.zip` PASS；Sandbox E2E は候補23では未実施）
- 受入済み直前予備：**候補21**（P6 Sandbox E2E PASS）、**候補19**（P6 Sandbox E2E PASS）
- 現行 frontend / 保持証拠：`data/development-tools/frontend-product22`（直前予備 `frontend-product21`；候補22・`frontend-product20` は `data/_cleanup_candidates/20261118-candidate23/` へ隔離）、証拠候補 `05` / `06` / `09`、`data/ai-ui/managed-candidate21-p6-e2e`

## 最近確認した変更
- **`RuntimeVerifyCard` 不透明化・フッター配置修正（`a0cb221`、`frontend-product22`・候補23）**：実機試用スクリーンショットの「右下の検証中が半透明で見づらくカード/一覧ボタンに重なる」指摘を受け、[MainPage.xaml](src/Aredoko.WinUI/MainPage.xaml) の `RuntimeVerifyCard` を右下フローティングオーバーレイ（`CardBackgroundFillColorDefaultBrush`）から `Grid.Row="4"` 内 `ItemPagerRow` 直上の独立バー（`SolidBackgroundFillColorTertiaryBrush`＋`SurfaceStrokeColorDefaultBrush` 枠線、3列横並び、`AutomationId` 維持）へ変更。`test_winui_compile_stub`（`3` 件 OK）・`frontend-product22`（`373` entries）・[run08_light](data/gui-ui-polish02/run08_light/summary.json) PASS。
- **候補23 再梱包・事前検証＋`A01`〜`F06` 改善（`f4f3cd3`〜`a0cb221`）**：`frontend-product22`＋`bootstrap22.exe` で `dist/portable-managed-20261118-23` を梱包し、`Aredoko.exe --self-test`（`0`）・`preflight.json`（`pass: true`, `frontend_activation: "portable"`）PASS。

## 利用者にできること
- 候補23（[Aredoko.exe](dist/portable-managed-20261118-23/Aredoko/Aredoko.exe)）で `RuntimeVerifyCard` 位置・不透明化修正と `A01`〜`F06` 改善一式をそのまま試用・ZIP展開・別配置できる（クリーンSandbox E2E確認済みの予備は候補21）。

## 未受入・未検証
- 候補23 のオフライン Windows Sandbox E2E、`RuntimeVerifyCard` 表示状態（AI検証 `verifying` 発生中）の Dark/Light 実表示再撮影、ユーザー実機試用フィードバック反映、P6-3（`cp313-cu128-draft.json` 供給元レビュー・実 immutable host・`TRUSTED_CATALOGS` 登録）。
- UI未確認：登録直後 `PromptPostRegistrationScanAsync`、`CmbSearchMode` 全10項目実切替・復元AIデータ切替、未保存バー実クリック、実日本語IME、物理DPI、ハイコントラスト。専用OCR（引き続き保留）。

## 次の1件（P6 / UI）
- **候補23のユーザー実機試用（AI検証バー表示含む）／P6 Sandbox E2E または P6-3 整備**：候補23での実機表示・操作を確認し、追加修正がなければ必要に応じ P6 Sandbox E2E または P6-3（`cp313-cu128` 供給元レビュー・immutable host）へ進む。
