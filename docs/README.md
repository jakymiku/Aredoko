# Aredoko ドキュメント案内（2026-10-24）

ここは**現在の開発を始めるための索引**であり、古い記録を逐一読む必要はない。作業に関係する節だけ読む。リンク先には未実装/未検証/履歴もあるので本文の状態表記を守る。

## まず読む
- [ルートAGENTS](../AGENTS.md) / [現行引き継ぎ](current-handoff.md) / [製品ビジョン](product-vision.md)
- [現行P0–P7統合ロードマップ](polish-roadmap-20261022.md) / [R01–R14・M1/M2完成台帳](completion-roadmap.md)
- [開発優先順位](development-priorities.md) / [開始ガイド](agent-start.md) / [仕様の方向性](spec.md)

## 機能別の現行仕様と根拠（対象のときのみ）
- 検索/AI: [AI検索](ai-search-plan.md)、[モデルprofile](model-profiles.md)、[検索品質](search-quality-baseline.md)、[ページ画像](page-image-search.md)、[媒体内容索引](media-content-plan.md)、[タグ候補](tag-suggestions.md)
- 登録/整理: [フォルダ管理](folder-library-management.md)、[複数棚](multi-shelf-storage.md)、[棚UI](shelf-ui-20261023.md)
- UI/閲覧: [WinUIデザイン](design-vision-winui.md)、[連続閲覧](result-session-native-connection.md)、[サムネイル](thumbnail-derivatives.md)、[読書位置](reader-progress.md)、[利用ガイド](user-guide.md)
- バックアップ/配布: [P5復元](restore-review-20261024.md)、[取得](ai-acquisition.md)、[P6軽量配布](lightweight-distribution.md)、[Portable ZIP候補](portable-refresh-20261024.md)、[基本の復旧](backup-recovery.md)
- 安全/データ: [原本パス検証](source-path-validation.md)、[大規模契約](large-library-contract.md)、[検索取消](search-cancellation.md)

## 過去の比較・実験・セッション記録
- [過去の原文と互換リンク一覧](history-index.md)
- [旧GUI比較の案内](gui-comparison.md)、[旧比較キット案内](gui-compare.md)、[初期状況記録](status.md)、[以前のスキル記録](development-skills.md)
- 日別の引き継ぎは [current-handoff.md](current-handoff.md) ではなく古い時点の証拠。[2026-10-23昼](daytime-handoff-20261023.md)、[同夜](overnight-handoff-20261023.md)
- `experiments/` の旧比較コードや旧Webデモは**現在のWinUI製品実装ではない**。安易に削除せず、具体的な参照と依存を確認してから別件として整理する。

## 運用ルール
新しい引き継ぎは `current-handoff.md` を短く**更新**し、入口に長い履歴を継ぎ足さない。技術上の検証証拠は対応する専門文書へ追加する。毎回CI/全回帰や済んだ調査を反復しない。旧文書の「最新」「次」はこの索引の現行文書へ置き換えた。
