# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- GitHub の `main` は Windows 製品版の現行ソース（旧開発ブランチ 7 本を削除し `main` のみに整理済み）。
- 最新公開候補は **Build 60（`v0.1.1-alpha`）** `dist/portable-managed-20261125-60`（`source_revision: 2c0b7e814169c8d2091990911d01f0b3a9c078d0`、Windows x64 ZIP SHA-256 `eb4a86c632f433becd3ef4f7a39df499828c623df65b93f07ea737ee1c7a7618`）。`Aredoko.WinUI` Portable・`Bootstrap.cs`・`aredoko_native.dll` を再発行し、セルフテスト・`preflight.json`・ZIP・検証キット照合に合格（状態 `staging-only`）。
- GitHub Releases `v0.1.1-alpha` 添付用一式は `dist/github-release-build60` に配置（Build 60 ZIP、`validation-kit.zip`、FFmpeg ソース＋2分割済み BtbN 依存キャッシュ `.part001`/`.part002`、`SHA256SUMS.txt`）。
- 直前予備は **Build 59（`v0.1.0-alpha`）**（`dist/portable-managed-20261124-59` / `dist/github-release-build59`）。Build 58 は旧予備。

## 最近確認した変更・利用者にできること
- 日本語／英語 UI 対応（Windows の表示言語に自動追従、設定から再起動なしで切替可能、ランチャー `Aredoko.exe`・`README.md` / `README.ja.md` も対応）。
- ドライブ丸ごと（例：`D:\`）スキャン時の長いパス対応（`\\?\`）・`$RECYCLE.BIN` 既定除外・配下のアクセス拒否スキップ＆既存レコード保持・「登録フォルダ」からのアクセス拒否ログ確認・コピー機能を追加。
- CBZ 全ページ一括 AI 索引、動画の一時停止場面からの類似検索、画像・本・動画の横断類似、フローティング操作バー付きビューアを利用できる。
- 後続の安定化では一覧の仮想化・スクロール・サムネイルと詳細の自動保存、Rust による検索処理、CPU/CUDA 自動選択、Windows での AI 取得時の WinHTTP フォールバックを実装した。
- Build 56 の FFmpeg と ffprobe は、BtbN の日付固定 ZIP から取得した両実行ファイルと SHA-256 が一致。固定版のソース・ビルドスクリプトの情報と第三者提供条件は [同梱物の通知](../THIRD_PARTY_NOTICES.md) に記録。
- Build 57 で導入済み CPU/CUDA を「この実行環境を使う」で選び直し可能にし、オフライン Sandbox（SAC 無効）＋RTX 4070 Ti 実梱包バックエンド試験に合格。Build 58 でもオフライン Sandbox 基本起動・検索・再配置時保存保持を確認。

## 未受入・未検証
- Build 56 のオフライン Sandbox は、SAC 有効時に未署名 EXE が起動前に **BLOCKED**。Visual C++ 未導入のオンラインゲストでは CPU AI 自動設定が PyTorch DLL ロードで失敗。製品だけでの AI 初回設定と配布先での前提案内は未受入。
- 友人試用セット・RTX 30 シリーズ実機での新規 CUDA 取得と実環境での CPU/CUDA 両方向切り替え・推論、Build 60（英語切替・ドライブ丸ごと実環境）の別 PC 検証は継続確認対象。
- 実 AI モデルでの CBZ 一括索引・動画場面類似・横断ランキング、物理マウス・日本語 IME・DPI・ハイコントラスト。P6-3 の `cp313-cu128` 供給元レビュー・immutable host・`TRUSTED_CATALOGS` 登録。専用 OCR は保留。

## 次の1件（P6 / UI）
- **GitHub Releases `v0.1.1-alpha`（`dist/github-release-build60`）の実環境導入確認と、RTX 30 シリーズ実機等での CUDA 新規取得確認**。
