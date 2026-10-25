# Aredoko ビジュアル素材セット v1

## 今回採用するデザイン
ジャッキー提督が選んだ「**銀髪のSD魔法使いが本棚の光る本を見つける**」デザインをメインアプリアイコンとして採用する。
**実装向けの個別ファイルを含むZIP**。合成イメージの一覧表を切り貼りする必要はない。`PREVIEW.png` は確認用であり、アプリの画面にそのまま表示しないこと。

## ディレクトリ

| フォルダ | 用途 | 主要ファイル |
| --- | --- | --- |
| `app_icon/` | 正式アプリアイコン、各サイズPNG、マルチサイズICO | `aredoko_app_icon_1024.png`, `aredoko_app_icon.ico` |
| `msix_compatibility/` | MSIX/WinUI 3 パッケージ向け候補サイズ | `Square44x44Logo.png`, `Square150x150Logo.png` など |
| `status/` | 状態別の独立したキャラ透過PNG（512×512キャンバス） | `aredoko_state_searching_512.png` など |
| `mascot/` | 表情・ポーズ違いの独立した透過PNG（512×512キャンバス） | `aredoko_mascot_smile_512.png` など |
| `branding/` | ヘッダー、起動画面用の背景、魔法の本のシンボル | `aredoko_header_background_1920x640.png`、`aredoko_brand_mark.svg` |
| `ui_icons/` | ユーザー操作用の単純な線画SVG、PNG（任意採用） | `aredoko_ui_search.svg` など |
| `reference/` | 画像の原案（アプリからは参照しない） | `approved_base_image_original.png` |
| `PREVIEW.png` | 人間による視覚確認専用 | なし |
| `asset_manifest.json` | ファイル一覧・寸法・推奨用途 | なし |
| `CODEX_PROMPT.txt` | Codexへの導入依頼文 | なし |

## 状態別の使い分け

| ファイル | 表示すると効果的な場面 |
| --- | --- |
| `status/aredoko_state_searching_512.png` | AI検索中（処理中インジケーターを置き換える必要はない） |
| `status/aredoko_state_found_512.png` | 初回チュートリアルや検索成功の案内 |
| `status/aredoko_state_no_results_512.png` | 検索結果なしの空状態 |
| `status/aredoko_state_indexing_512.png` | ライブラリ作成・インデックス更新・モデル準備 |
| `status/aredoko_state_completed_512.png` | 索引完成・初期設定の完了 |
| `status/aredoko_state_error_512.png` | エラーの空状態（必ず原因と再試行ボタンも別途テキストで提示） |

`mascot/` はオンボーディング・軽いお知らせ・ヒント・ヘルプ等で適宜使う。検索結果の一覧や主操作パネルに常駐表示しないこと。**検索バーはコンパクト、一覧は広く、右パネルは詳細・タグ編集**という既存のAredoko UX方針を守る。

## 実装上の注意

- キャラの透過PNGは、生成した集合イラストから個別に抽出したもの。透明部分は存在するが、髪先・光のエフェクト周辺にはごく細い切り抜き跡が出る場合がある。背景色の異なるテーマで表示確認すること。
- 状態・キャラ絵の**元の描画ディテールは約130〜180px程度**。ファイルのキャンバスは配置のため512pxで統一してある。画面上は原則96〜220px程度を推奨し、巨大なヒーロー画像へ引き伸ばさないこと。
- アプリアイコンのPNGは実描画の高解像度版から生成。16〜24pxではキャラの細部が見えにくいことがあるので、`branding/aredoko_brand_mark.svg` を代替として使うか、実際のサイズで判断する。
- `branding/*background*` は**背景画像**であり、ロゴや操作ボタンは描き込まれていない。見出しや進捗、操作はネイティブUI側で重ねる。
- `ui_icons/` は任意。既存のFluent/WinUIのアイコンセットが整っていれば無理に置き換えない。
- **MSIX/WinUI 3のロゴ名・サイズ・縮尺別リソースは、実際の `Package.appxmanifest` や既存リソースを見て決定**。ファイルをそのままコピーして全て利用すると決めつけない。
- `*.ico` が必要かどうかも、パッケージ版か非パッケージ版かによる。`msix_compatibility/` の画像は候補であり、設定済みアセットの安全な移行を優先する。
- ZIPは成果物として保持し、ZIP内の `reference/`, `PREVIEW.png`, `CODEX_PROMPT.txt` をアプリ本体の配布リソースに同梱する必要はない。

## カラーの目安
- Midnight Navy: `#0B1830`
- Deep Navy: `#112344`
- Cyan: `#5DDFFD`
- Teal Glow: `#56DFFF`
- Soft White: `#EDF7FF`
- Warm Gold: `#FFF1D1`

## 画像の確認
各画像は既に実ファイルとして保存済み。Codexはファイル名のカタログ情報のみでなく、**画像の実サイズ・透過・描画内容を目視/コードで確認**し、導入すること。
