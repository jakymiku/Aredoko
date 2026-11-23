# Aredoko リポジトリの構成

- `main` はWindows製品版のソースです。現在の受入状況と次の作業は [現在の引き継ぎ](current-handoff.md) に記録します。
- `feat/winui3-production-mvp-20261011` と [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5) は統合前の開発記録です。PR #1〜#3と#6には旧Web試作、索引基盤、GUI比較、旧ビジョンの履歴があります。
- Windows製品版の統合では、開発内容とBuild 58までの変更を1コミットにまとめました。時点別の作業記録の複製とテストの生ログは開発側で保管し、`main` には技術文書の検証要約を収録しています。
- 旧Webデモと比較コードのうち共有依存のあるものは製品と同じリポジトリに置いています。変更前には [旧実験コードの依存監査](legacy-dependency-audit-20261024.md) を参照してください。
- GitHub Actionsの3ワークフローは手動実行です。普段の変更は関係するローカルテストで確認します。
