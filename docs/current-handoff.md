# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- GitHub の `main` は Windows 製品版の現行ソース（旧開発ブランチ 7 本を削除し `main` のみに整理済み）。
- 最新公開候補は **Build 67（`v0.1.3-alpha`）** `dist/portable-managed-20261128-67`（`source_revision: 168cdd24e28349d5d160bda4218d7af74308ce4d`、Windows x64 ZIP `217,091,935` bytes、SHA-256 `c3265f22fd0dfe71485a9ee017fac4fc625b58323d1ee98e0d04d0ea2c18aa1c`）。`Aredoko.WinUI` Portable（`frontend-product67`）で再梱包し、セルフテスト・`verify_release`（536 ファイル、`__pycache__`/ユーザーパス混入 0 件）・`preflight.json`・ZIP 照合・分離 `--startup-check`（`ready_sent` / `initial_search_completed` `7.92s`・終了コード `0`）に合格（状態 `staging-only`）。
- GitHub Releases `v0.1.3-alpha` 添付用一式は `dist/github-release-build67` に配置（Build 67 ZIP、`validation-kit.zip`、FFmpeg ソース＋2分割済み BtbN 依存キャッシュ `.part001`/`.part002`、`SHA256SUMS.txt`）。
- 直前予備は **Build 63（`v0.1.2-alpha`）**（`dist/portable-managed-20261127-63` / `dist/github-release-build63`、`source_revision: ad2bece7f530315cac33fa4036f935d870f355d9`）。旧 Build 59–62 / 64–66 および旧 `frontend-product*` は `cleanup-20261128-67.txt` 記録の上で整理済み。

## 最近確認した変更・利用者にできること
- **大規模ライブラリ（95,000 件超）向け索引作成・閲覧体験の抜本改善**:
  - AI 索引作成・継続索引・`coverage()` の 10,000 件 / 1,000 件上限を撤廃し（上限 `1,000,000` 件）、95k+ 件をチャンク単位の定数メモリで一括索引・再開できるよう改善。
  - `FrozenResult` の一覧セッション作成時に 95k 件分の物理 `_safe_path` 検査を一括実行する処理をページ読み出し時の遅延検証へ移行し、`FIELDS_NO_SHELVES` 高速パスや `_exclude_matcher` キャッシュと合わせて一覧初期作成を大幅短縮。非 AI 一覧セッションは AI ベクトル更新で無効化されないよう `IndexStamp` を分離し、AI 索引作成中の 409 競合では専用ガイダンス（`ai_indexing: True`）を表示。
  - `設定`・`登録フォルダ`・`棚` ⇄ `すべて` の画面往復で有効な一覧セッション（`CanRestoreLoadedResultSession` / `RestoreLoadedLibraryView`）を即時再利用し、復帰時の「詳細」ボタン有効化と無変更時の不要リロード抑止を実装。
  - `登録フォルダ` 画面上部に AI 検索データ状況バー・進捗バー・ワンクリック作成/中止ボタンを統合し、`設定` → AI カードにも進捗バー＋作成ボタン＋生成ガード（古い `coverage()` 応答による上書き防止）を実装。
  - `AI search coverage()` の単一接続・軽量クエリ化（10k 計測 `0.024s`–`0.062s`・95k 換算 `0.23s`–`0.59s`）と `AISearch.start()` のロック外カウント、`AIScopeEditor` の `CBZ・ZIP・本の内部ページ`（`book_pages`）即保存対応・`all_pages` 時の内部ページ未作成冊数判定・通常ビルドでの既作成分スキップ数（`reused`）可視化を実装。
- **Build 63 までに実装済み**: GPU 自動ベンチマーク＋速度モード（普段使い/ターボ）、CBZ 全ページ一括索引、起動時 `Initial screen timed out` 解消、起動時 AI チェック任意化、日英 UI 自動追従・切替、長いパス/`$RECYCLE.BIN` 除外・アクセス拒否ログ、動画/画像/本横断類似、CPU/CUDA 再選択、BtbN FFmpeg（SHA-256 一致・[同梱物の通知](../THIRD_PARTY_NOTICES.md) 記録済み）。

## 未受入・未検証
- Build 56 のオフライン Sandbox（SAC 有効時未署名 EXE ブロック）、VC++ 未導入ゲストでの CPU AI 自動設定。
- Build 67（95k 実機での一括 AI 索引、`book_pages=all_pages` 追加作成、UI 操作一式）・RTX 30 シリーズ実機 CUDA 取得・英語切替・別 PC 検証。P6-3 `cp313-cu128` 供給元レビュー・`TRUSTED_CATALOGS` 登録。専用 OCR は保留。

## 次の1件（P6 / UI）
- **GitHub Releases `v0.1.3-alpha`（Build 67、`dist/github-release-build67`）の実機（約 9.5 万件ライブラリ）での起動・一覧往復・AI 検索設定保存・一括 AI 索引作成の実地確認**。
