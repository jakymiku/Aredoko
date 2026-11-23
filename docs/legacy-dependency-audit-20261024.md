# Aredoko 旧実験コードの依存監査・縮約（2026-10-24）

> 調査対象: `feat/winui3-production-mvp-20261011`、文書整理後の `f33f6eac621f`。**今回の確認は主要な起動経路とCI/GUI比較用コードの参照調査であり、全645ファイルの完全な静的依存解析やWinUI実機テストではない。**

## 判定と処置

| 対象 | 確認できた参照/実態 | 今回の処置 |
| --- | --- | --- |
| `experiments/gui-compare/` (約30ファイル) | Tauri/ReactとWinUIの以前の比較試作。旧 `.github/workflows/checks.yml` からユニットテスト、JSON smoke、UIA driver、PowerShell構文、Reactビルドを起動していた。比較キットには専用のbat起動手順がある。 | **凍結・常設CI対象から除外**。既存の `feat/gui-framework-comparison-20261010`（PR #3）と現行作業tree上の旧素材は残す。比較の再計測は現行製品の受入とは扱わない。 |
| `tools/check-gui-bench.cjs` | `experiments/gui-compare/tauri-react/dist` を使うEdgeでのReact比較専用のテスト。旧CIのブラウザジョブから呼び出されていた。 | **製品CI対象から除外**。ファイルは比較実験を復元する場合のため保持。 |
| `tools/run-ui-check.cjs` と `tools/check-ui.cjs`、`web/` | `app/server.py` による旧WebデモのEdgeテスト。旧CIのbrowser-smokeジョブでPlaywrightやnpm/Reactビルドが起動していた。 | **製品CI対象から除外**。旧mainには旧デモが残っている。テスト手順は履歴として保持。 |
| `app/catalog.py` | `app/production.py` が `from catalog import Catalog` を使い `ProductionCatalog(Catalog)` として継承。 | **削除不可**。製品バックエンドの共有実装。 |
| `app/server.py` | `app/production_server.py` が `from server import handler_for` を使う。 `tests/test_catalog.py` / `tests/test_benchmark_frontend.py` も参照。 | **削除不可**。旧HTTPハンドラの参照を解消せず移動・削除すると製品/API/回帰を壊す。 |
| `tests/test_production.py` | 製品の一時ファイルを使ったテストで旧デモDBを拒否するガードにも依存。 | **残す**。旧デモの存在が即座に不要を意味しない。 |
| `tools/launch_release.py` | `backend/app/production_server.py` で製品backendを起動。旧 `app/server.py` の `--open` でのデモとは別の製品経路。 | **残す**。製品配布に関係する。 |

## CIを軽くする実変更
- `.github/workflows/checks.yml` から **Tauri/React・Web/Playwright・GUI比較テスト・GUIドライバーのビルド・ブラウザsmokeのジョブを撤去**。
- 主な製品契約だけを**手動 `workflow_dispatch` 1ジョブ**へ変更。明示的な生成fixture系Pythonの範囲とCore C#契約に限定する。
- 旧CIの原文はこの変更の**親コミット**から `git show <親SHA>:.github/workflows/checks.yml` で復元できる。旧比較コード自体は削除しない。
- 実行は **0回**。Actionsの枠が使えない間は手動でも起動しない。今回のworkflowの構文・Windowsでの実行成否は未確認。

## 今回削除しなかった理由と次の減量
現在の製品コードは旧Catalog/HTTPクラスへ実際に依存するため、実験由来だからと `app/`、`web/`、`tools/`、`experiments/` をまとめて消すのは危険。

将来本当に削除するなら、まず `ProductionCatalog` の共通部・`production_server` が旧 `handler_for` に依存する箇所を対象に切り離し、既存の検索/認証/デモDB拒否/範囲guardを生成データで確認する。それから実験コードへの参照と文書・テスト・手動起動の要否を再評価し、旧PR/コミットに戻れる状態を保って削除する。

現在は、**製品完成が先**。この依存解消だけの大きなリファクタや実験コード一斉削除を、P5/P6の次の実装より優先しない。

## mainへ統合できるか
`main` は旧Web試作のコード、開発ブランチはDraft PR #5として未完。P5のactive/pending復元、P6のZIP再配置/通常起動、実機GUIと通常DB再起動、P7の主要な受入は完了していない。**現時点では製品コードをmainへマージしない。** 双方のREADMEは最新への導線を持ち、mainの自動Actionsは手動のみに変更済み。受入条件を満たしたら [統合方針](repository-maintenance.md)に従い、mainを安全なFast-forward/通常mergeで更新する。mainへの強制Pushや旧PRの無断mergeは行わない。
