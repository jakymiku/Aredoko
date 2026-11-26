# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- GitHub の `main` は Windows 製品版の現行ソース（旧開発ブランチ 7 本を削除し `main` のみに整理済み）。
- 最新公開候補は **Build 62（`v0.1.2-alpha`）** `dist/portable-managed-20261127-62`（`source_revision: 3dcb27b88738425b3161a9dc5817c6db1daa2edb`、Windows x64 ZIP `199,649,268` bytes、SHA-256 `77d59cbdb4e7e6d80a278946840571af1475dce9b30967dbe3809bb3e540d711`）。`Aredoko.WinUI` Portable（`frontend-product62`）とバックエンド高速化一式を再梱包し、セルフテスト・`verify_release`・`preflight.json`・ZIP 照合（536 ファイル）に合格（状態 `staging-only`）。
- GitHub Releases `v0.1.2-alpha` 添付用一式は `dist/github-release-build62` に配置（Build 62 ZIP、`validation-kit.zip`、FFmpeg ソース＋2分割済み BtbN 依存キャッシュ `.part001`/`.part002`、`SHA256SUMS.txt`）。
- 直前予備は **Build 61（`v0.1.1-alpha`）**（`dist/portable-managed-20261126-61` / `dist/github-release-build61`）。Build 60 は旧予備。

## 最近確認した変更・利用者にできること
- AI 索引作成の大幅高速化（テキスト/画像/表紙/動画代表フレームのバッチ推論、ワーカー内並列画像デコード、CBZ/フォルダ本のチャンク一括読み出しによる ZIP 再オープン削減、SQLite バッチコミット `put_many`、動画フレーム抽出時の重複 `ffprobe` 削減）。
- 初回バッチ索引時の GPU 性能自動計測（`_auto_tune_batch`）によるバッチサイズ自動調整と、**設定 → メモリと負荷** の **索引作成の速度モード**（普段使い `normal` ／ ターボ `turbo`）および自動調整結果表示（`AIAutoTuneSummary`）を追加。RTX 4070 Ti（CUDA）実機生成素材ベンチマークで、テキスト推論 `22.93x`（`460.3/s`）・画像推論 `1.98x`（`17.8/s`、`tuned_image_batch=4`）、32 PNG＋2×32p CBZ（破損 1 ページ安全スキップ、計 63 ページ＋34 表紙/テキスト）の E2E 全工程をコールドロード込み `20.88s`（普段使い）／`19.25s`（ターボ）で完了。
- CBZ・本の「内部のすべての画像を含む」AI 索引で 1,600 万画素超や破損ページ等がスキップ（`None`／利用不可）された際に `TypeError` で中断せず安全にスキップし、AI 構築失敗時のトレースバックを `backend-error.log`（`stderr`）へ記録するよう修正した（関連テスト追加・合格）。
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
