# Aredoko

**名前や保存場所を忘れたローカルの画像・本・同人誌・動画・音声・素材を、曖昧な日本語から探すWindows向けアプリ。**

> **開発中 / 正式安定版ではない（2026-10-24）。** 現行ソースにはWinUI 3製品UIとPython/SQLiteの検索・整理・閲覧基盤がある一方、配布ZIPのGUI受入・clean Windows・実モデル自動取得・総合受入は未完了。ビルド成功と実機成功を混同しない。

## いま読むもの
- [現行の状態と次の作業](docs/current-handoff.md) — 現行HEADを照合してから再開
- [開発のルール](AGENTS.md) — 開発者・Codex・他エージェント共通
- [製品ビジョン](docs/product-vision.md) — 検索・整理・対象メディアの目標
- [現行P0–P7ロードマップ](docs/polish-roadmap-20261022.md) と [R01–R14・M1/M2台帳](docs/completion-roadmap.md) — 目標と未完
- [ドキュメント全体の案内](docs/README.md) — 実装契約・根拠・旧版の分類

## 開発・利用の状態
Windows製品フロントエンドは**ネイティブWinUI 3**、共通検索/索引/APIはPython＋SQLite。通常の検索/AI検索・画像/本/動画の閲覧・タグ/棚/バックアップ等は各段階で実装済みだが、すべての組み合わせや配布ZIPで完成済みではない。

通常利用の配布方式は今後 **ZIP解凍→Aredoko.exe** を目指す。2026-10-24の基本ZIP候補はローカルにのみ存在し、最新ソースではなく、最終受入未了。 [利用ガイド](docs/user-guide.md)、[配布状況](docs/portable-refresh-20261024.md)、[配布計画](docs/lightweight-distribution.md)を参照。

古いブラウザ/架空データのデモ（`start-demo.cmd`等）は引き続き比較・開発用のサンプルで、現在の製品WinUI版ではない。旧READMEの操作例は[履歴](README.history-20261024.md)へ移した。

## 安全と貢献
原本は原則読み取り専用で、ユーザーの私物を無断走査・移動・削除しない。認証情報・個人データ・DB・モデルをコミットしない。CIは手動起動のみ・残枠が使えない間は実行しない。既存の開発ブランチと[Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5)を継続する。

## ライセンスと配布形態
- **Aredoko 本体**：[MIT License](LICENSE)（Copyright (c) 2026 JAKYMIKU）。
- **同梱物・導入ランタイム・モデル**：FFmpeg/ffprobe（GPLv3）、.NET / Windows App SDK / WebView2 / WinML、基本 Python 3.13.17 / Pillow 12.3.0、任意 AI 環境（PyTorch / CUDA / Hugging Face 系 44 パッケージ）、および各モデルはそれぞれのライセンスに従います。詳細は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) と [config/desktop-notices/](config/desktop-notices/manifest.json) を参照してください。
- **未署名配布**：配布 ZIP 内の実行ファイル・DLL（約 55 本の非 Microsoft 製 PE）は Authenticode コード署名を行わず**未署名**で配布します。Windows のスマート アプリ コントロールが強制（オン）になっている環境では、OS ポリシーにより未署名 EXE の起動がブロックされる場合があります。
