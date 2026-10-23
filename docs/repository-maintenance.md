# Aredoko リポジトリ整理と main 昇格方針（2026-10-24）

## 役割
- `main`：2026-10-09の旧Webデモのコード。**最新WinUI製品版ではない**。訪問者向けREADMEだけ現行開発先を案内する。旧README原文も `README.history-initial-20261024.md` に保持。
- `feat/winui3-production-mvp-20261011`：唯一の現行製品開発ブランチ。[Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5)を継続。P5/P6/P7・M1/M2の未完は [現行handoff](current-handoff.md) / [P0–P7](polish-roadmap-20261022.md) / [R01–R14](completion-roadmap.md) で管理する。
- PR #1はWeb試作、#2は別系統の索引基盤、#3はGUI比較、#6は製品ブランチ向け旧ビジョン文書。**未マージ/既存の依存を確認せずマージ/削除/閉鎖しない。**
- mainへ2026-10-24に行った文書のみの更新は、開発版のGit履歴にも安全に統合し、将来のFast-forward昇格を妨げない構成とする。製品コードのmain昇格ではない。

## 原本保全とアーカイブの判定
- 旧入口・セッションhandoff・比較用の**文章**で現行方針と矛盾するものは、原文を同じGit blob SHAで `*.history-*.md` へ移し、旧パスには薄い案内を残す。現行導線は [docs/README.md](README.md)、旧原文は [history-index](history-index.md)。
- 簡潔な [AGENTS](../AGENTS.md) / [単一の引き継ぎ](current-handoff.md) は増殖させず、毎回の全文追加を禁止。各専門設計書（AI/セキュリティ/配布/失敗記録）は、今後のデータ互換性や再発防止に使うので残す。
- `src/`, `app/`, `tools/`, `tests/`, `experiments/` の削除は文書の重複とは違い実行経路/将来の回帰に影響する。依存探索・テストと担当PRの統合が済むまで安易に削除しない。

## mainに製品コードを昇格する条件
1. Draft PR #5が未完成なのを前提に、P5 backup/restoreのデータ保全、P6 ZIP通常起動と再配置、実機GUI・通常DB再起動・既存機能の主要操作、最低限のP7受入を記録。未確認を成功としない。**現在は未達成。**
2. `main`・開発ブランチ両方の最新HEAD/差分を確認。PR #1/#2/#3/#5/#6のbaseと依存重複を監査し、過去のPR #6を重複適用しない。
3. 現行開発ブランチの変更をレビューし、`main`へ統合。既存のGit履歴を消さない。`main`をforce updateしない。将来の統合時に競合があれば先に解消。主用途に影響する回帰やデータ移行は事前に関連確認。
4. その後、必要ならデフォルトブランチ/PR base/README/配布先を整備。**今回このステップは実施しない。**

## CI
初期mainの `.github/workflows/checks.yml` はもともと `push, pull_request` だったが2026-10-24に `workflow_dispatch` 専用へ切り替えた。開発ブランチの3 workflowも手動のみ。残枠が使えない間はActions 0回。通常のdocs整頓のためにCIを起動しない。
