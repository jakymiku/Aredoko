# 現在の引き継ぎ・次の1件

**唯一の正本**。古い完了報告・計画の「次の作業」よりこの文書を優先する。

## 現行HEAD・最新候補/予備
- GitHub の `main` は Windows 製品版の現行ソース。開発ブランチの `8a32934` と Build 58 までの変更をまとめて統合。開発ブランチと [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5) は Build 56 時点の開発記録。
- 最新試用候補は **Build 58** `dist/portable-managed-20261123-58`。Windows x64 ZIP の SHA-256 は `1fd9092e7079a203c2103d90d5c8c7837fa8cb44bf50d557779ab4c60ff5b66a`。`8a32934` を基点としたローカル差分を梱包したため、マニフェストの `source_revision` は未設定。起動 EXE のセルフテスト、preflight、ZIP・検証キット照合は合格、状態は `staging-only`。
- Build 57 は過去の試験証拠。友人試用には配布物とビルド出力を見直した Build 58 を使用する。
- 友人試用セットは `dist/aredoko-build58-friend-trial`。Build 58 ZIP、試用案内、生成素材、FFmpeg対応ソースをまとめた。2,243,239,039 bytes の依存ソースキャッシュは固定BtbN実行の公式 SHA-256 と照合済み。共有時はフォルダ全体を同じ配布先から取得できるようにする。

## 最近確認した変更・利用者にできること
- CBZ 全ページ一括 AI 索引、動画の一時停止場面からの類似検索、画像・本・動画の横断類似、フローティング操作バー付きビューアを利用できる。
- 後続の安定化では一覧の仮想化・スクロール・サムネイルと詳細の自動保存、Rust による検索処理、CPU/CUDA 自動選択、Windows での AI 取得時の WinHTTP フォールバックを実装した。
- Build 56 の FFmpeg と ffprobe は、BtbN の日付固定 ZIP から取得した両実行ファイルと SHA-256 が一致。固定版のソース・ビルドスクリプトの情報と第三者提供条件は [同梱物の通知](../THIRD_PARTY_NOTICES.md) に記録。
- Build 56 のライセンス監査で WinUI・Windows App SDK ML・Rust の個別原文を補い、次回の梱包入力へ追加した。既存 ZIP は監査対象として保持。梱包試験は20件合格・1件スキップ。
- Build 56 のオンライン Sandbox GUI で、SAC をゲスト内で無効にし、公式 Visual C++ x64 `14.52.37029.0` を入れた条件で、初回起動・CPU AI 環境と EmbeddingGemma 2 の取得・設定保存・再起動・生成素材3件の AI 索引・「青い画像」で `blue-image.png` が先頭に出るまで合格。[配布設計](lightweight-distribution.md) に証拠を記録。
- Build 57 で導入済み CPU/CUDA を「この実行環境を使う」で選び直せる。現在・再起動後・実推論デバイスを区別して表示する。開発用 `data/development-tools/frontend-product-runtime-switch` で生成fixtureの GUI 切り替えと関連単体テスト 68 件合格・1 件スキップ。ライセンス監査で追加した原文も Build 57 ZIP に同梱済み。
- Build 57 は新規オフライン Sandbox で、ゲスト内のみ SAC を無効化し、保持済み基本ランタイムで起動、登録、検索、閲覧、タグ・棚・お気に入りの別パス起動後保持まで合格。RTX 4070 Ti の実梱包バックエンドで、導入済み環境の CUDA 索引2件と日本語検索も合格。[検証記録](lightweight-distribution.md#build-57-の友人試用前の起動確認)
- Build 58 は利用ガイドと関連3文書だけを配布し、WinUI/Core/Rustを開発パスなしで再ビルドした。梱包試験は20件合格・1件スキップ、Build 58のオフラインSandboxで基本起動・検索・再配置時の保存保持に合格。Build 58のRTX検索試験は未実施。

## 未受入・未検証
- Build 56 のオフライン Sandbox は、SAC 有効時に未署名 EXE が起動前に **BLOCKED**。Visual C++ 未導入のオンラインゲストでは初回起動・GUI 登録・文字検索まで合格し、CPU AI 自動設定は PyTorch の DLL ロードで失敗。製品だけでの AI 初回設定と配布先での前提案内は未受入。
- 友人試用セットの外部共有、RTX 30シリーズ実機での新規CUDA取得と実環境での CPU/CUDA 両方向の切り替え・推論は未実施。FFmpeg対応ソースは試用セットに保持済み。GitHub Releases 等の外部配布先は未設定。
- 実 AI モデルでの CBZ 一括索引・動画場面類似・横断ランキング、物理マウス・日本語 IME・DPI・ハイコントラスト。P6-3 の `cp313-cu128` 供給元レビュー・immutable host・`TRUSTED_CATALOGS` 登録。専用 OCR は保留。

## 次の1件（P6 / UI）
- **Build 58 の友人試用セットで RTX 30シリーズ実機の初回 CUDA セットアップと AI 検索を確認する**。試用案内に Visual C++ x64・対応 NVIDIA ドライバー・未署名起動の前提を記載済み。
