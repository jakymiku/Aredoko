# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- ブランチ / PR：`feat/winui3-production-mvp-20261011` / Draft [PR #5](https://github.com/jakymiku/Aredoko/pull/5)
- 直近機能コミット：`f4f3cd3`（**62項目 UI文言・導線改善 `A01`〜`F06`**・`frontend-product21`＋`bootstrap22.exe`）、`7eb7f3e`（**UI-A〜UI-D**・`frontend-product20`）
- 最新配布候補：**候補22** `dist/portable-managed-20261118-22/Aredoko/Aredoko.exe`（source `f4f3cd3aacf7a527bf827102d97aa8e8eb548e60`、`675` files / `501,318,494` bytes、ZIP `215,457,790` bytes SHA-256 `3d4b14a8...`、`--self-test`・`preflight.json`・`validation-kit.zip` PASS；Sandbox E2E は候補22では未実施）
- 受入済み直前予備：**候補21**（P6 Sandbox E2E PASS）、**候補19**（P6 Sandbox E2E PASS）
- 現行 frontend / 保持証拠：`data/development-tools/frontend-product21`（直前予備 `frontend-product20`；候補20・`frontend-product19`・`run06_light_sandbox` は `data/_cleanup_candidates/20261118-candidate22/` へ隔離）、証拠候補 `05` / `06` / `09`、`data/ai-ui/managed-candidate21-p6-e2e`

## 最近確認した変更
- **UI文言・導線・情報階層改善 `A01`〜`F06`（`f4f3cd3`、`frontend-product21`・候補22）**：[Bootstrap.cs](src/Aredoko.Bootstrap/Bootstrap.cs) の初回準備案内整理、`GettingStarted` 3手順化、`AISetupPlan` 一括可否/10進GB表示、`CmbSearchMode` 全10項目/範囲表示/診断情報（実件数・共有前確認）・詳細 `ChkFavorite` 配置＆タグ保存/取消・設定グループ見出し＆未保存3択バー・肯定文言「AI検索用データも復元」を反映。`Aredoko.Core.Tests` 終了コード `0`、Python単体 `15`件＋`31`件 OK、[gui-ui-polish02](data/gui-ui-polish02/run07_dark/summary.json)（Light `run06_light`・Dark `run07_dark`）PASS。
- **候補22 再梱包・事前検証（2026-11-18）**：`frontend-product21`＋`bootstrap22.exe`＋`LICENSE`/`THIRD_PARTY_LICENSES/` で `dist/portable-managed-20261118-22` を生成し、`Aredoko.exe --self-test`（`0`）と `preflight.json`（`pass: true`、`frontend_activation: "portable"`）を確認。

## 利用者にできること
- 候補22（[Aredoko.exe](dist/portable-managed-20261118-22/Aredoko/Aredoko.exe)）で改善後の日本語UI・導線・診断/設定・`LICENSE`/`THIRD_PARTY_LICENSES/` 同梱構成をそのまま試用・ZIP展開・別配置できる（クリーンSandbox E2E確認済みの予備は候補21）。

## 未受入・未検証
- 候補22 のオフライン Windows Sandbox E2E、`Bootstrap.exe` 初回DL文言の実クリーン環境表示、ユーザー実機試用フィードバック反映、P6-3（`cp313-cu128-draft.json` 供給元レビュー・実 immutable host・`TRUSTED_CATALOGS` 登録）。
- UI未確認：登録直後 `PromptPostRegistrationScanAsync` 実操作、`CmbSearchMode` 全10項目実切替・関連性/復元AIデータ切替、未保存バー実クリック、実日本語IME、物理DPI、ハイコントラスト。専用OCR（引き続き保留）。

## 次の1件（P6 / UI）
- **候補22のユーザー実機試用／P6 オフライン Sandbox E2E または P6-3 外部条件整備**：必要に応じ候補22（`bootstrap22.exe` 含む）で P6 Sandbox E2E または実利用テストを実施し、違和感があれば UI 改善、なければ P6-3（`cp313-cu128` 供給元レビュー・immutable host）へ進む。
