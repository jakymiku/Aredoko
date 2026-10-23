# AIエージェント開始ガイド（簡略版）

最新の作業手順と制約は [AGENTS.md](../AGENTS.md)、実装と次の1件は [docs/current-handoff.md](current-handoff.md) に集約している。**以前の長い開始ガイドは[履歴索引](history-index.md)へ保存した。**

1. `git fetch` し、作業ブランチ・HEAD・`git status`・[Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5)と未反映の差分を確かめる。
2. [現行の引き継ぎ](current-handoff.md)、[製品ビジョン](product-vision.md)、[統合ロードマップ](polish-roadmap-20261022.md)を読み、**今の1件**に関係する技術文書だけ追加で読む。
3. 前回実装済みのコード/証拠を再作成しない。実装→関連最小テスト→次の縦切りの順。CI、不要PR、全回帰、実機検証の無断再試行はしない。
4. 実HEAD・コミット・新たに使える機能・正確な未検証・次の1件を [current-handoff.md](current-handoff.md) に置換更新する。長文の履歴を入口へ積まない。

優先度の衝突時：**製品の目的は product-vision、作業順は polish-roadmap、最新実装と次の具体タスクは current-handoff とコード、禁止事項は AGENTS**を正とする。過去記録は証拠・事故調査時だけ参照する。
