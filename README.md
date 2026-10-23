# Aredoko

> **mainは旧プロトタイプの保存地点（2026-10-24時点）。現在の製品コード・起動方法・開発状況はここではない。**

## 最新の開発先
- [Windows製品版の開発ブランチ](https://github.com/jakymiku/Aredoko/tree/feat/winui3-production-mvp-20261011) — WinUI 3 + Python/SQLite、まだ正式安定版ではない
- [現在の引き継ぎ](https://github.com/jakymiku/Aredoko/blob/feat/winui3-production-mvp-20261011/docs/current-handoff.md) — 次の実装1件と未検証
- [開発ロードマップ](https://github.com/jakymiku/Aredoko/blob/feat/winui3-production-mvp-20261011/docs/polish-roadmap-20261022.md) — P0–P7
- [長期完成台帳](https://github.com/jakymiku/Aredoko/blob/feat/winui3-production-mvp-20261011/docs/completion-roadmap.md) — R01–R14、M1/M2
- [開発中のDraft PR #5](https://github.com/jakymiku/Aredoko/pull/5) — 未マージ・未完成

## mainにあるもの
このブランチは2026年10月9日時点の小規模なWebデモを残している。起動するなら `start-demo.cmd`、または `python app/server.py --open`。これは**生成データ中心の旧試作**であり、現在のWinUI 3製品版ではない。古い操作・当時の機能については[初期README原文](README.history-initial-20261024.md)を参照してね。

**mainに最新製品実装を取り込むのは、配布版の起動・データ保全・主要機能を受入確認してから。** 現行開発ブランチは476コミット以上進んでいるが、未確認機能を正式安定版として扱わず、Draft PRや他の比較用PRを勝手に統合しない。次回の正式統合時にはPR依存関係・保護ルール・競合・Actionsを再確認する。

GitHub Actionsはクォータ保護のため手動起動（`workflow_dispatch`）に限定。通常のPush/PRでは自動実行しない。
