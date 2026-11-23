<p align="center">
  <img src="design/visual-assets/v2/branding/aredoko-readme-banner.png" alt="Aredokoのキャラクターと光る本" width="100%" />
</p>

<h1 align="center">Aredoko（あれどこ）</h1>

<p align="center">
  <strong>名前を忘れたファイルを、覚えていることから探せる。</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%20x64-0078D6?logo=windows&logoColor=white" alt="Windows x64" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-2ea44f" alt="MIT License" /></a>
  <a href="https://ko-fi.com/jakymikudev"><img src="https://img.shields.io/badge/Ko--fi-Support%20Aredoko-FF5E5B?logo=ko-fi&logoColor=white" alt="Ko-fiで支援する" /></a>
</p>

<p align="center">
  <a href="README.md">English</a> | <strong>日本語</strong>
</p>

---

**Aredoko** は、PCにある画像・本・同人誌・動画・音声をまとめて探し、閲覧・整理できる Windows 向けのローカル検索アプリです。

まずは AI なしでファイル名やタグからすぐに検索できます。必要に応じてローカル AI 検索を有効にすると、「青い夜空のイラスト」のような曖昧な日本語や、画像の見た目・本のページ・動画の一場面・音声の内容からも探せるようになります。

## 特長

- **完全ローカル動作** — 検索も AI 推論も PC 内で完結し、ファイルや検索内容が外部サーバーへ送信されることはありません。
- **原本はそのまま保護** — 元のファイルは読み取り専用として扱います。タグ・棚・お気に入り・読書位置は PC 内のカタログ（既定 `%LOCALAPPDATA%\Aredoko`）に保存されます。
- **AI は完全任意・無断取得なし** — GPU がない環境でも、通常検索・閲覧・整理はそのまま利用できます。AI 実行環境（CPU / CUDA）やモデルは、明示的に準備を選んだときだけ取得します。
- **既存環境を汚さない構成** — 初回起動時に取得する基本 Python はアプリ専用フォルダへ配置され、PC に既存の Python 環境を書き換えません。

## できること

- **探す**
  - 登録フォルダを横断したファイル名・タグ検索。
  - AI 検索（任意）による、画像の見た目・本の表紙や索引済みページ・動画の場面（一致時刻付き）・音声や動画内音声の内容・ファイル名やタグの意味からの検索。
  - 任意のファイルから見た目や音が似た素材を探す類似検索。
- **見る・再生する**
  - 画像（GIF / WebP / APNG アニメーション対応）、本（CBZ / ZIP・画像フォルダ、見開き方向や読書位置の復元に対応）、動画、音声を内蔵ビューア・プレイヤーで閲覧・再生。
  - 検索結果から一致ページや動画・音声の一致時刻へそのままジャンプ。
  - 必要に応じて、ダブルクリックで Windows の既定アプリを開く設定にも切り替え可能。
- **整理する・守る**
  - タグ・棚・お気に入り・除外ルール・複数選択からの一括整理に対応。
  - アプリ起動中のライブバックアップと、既存ライブラリを上書きしない新規先への検証付き復元に対応。

## はじめ方

> **お知らせ:** 公開版の配布パッケージは現在準備中です。公開後は [GitHub Releases](https://github.com/jakymiku/Aredoko/releases) から Windows x64 版 ZIP をダウンロードできます。

1. [GitHub Releases](https://github.com/jakymiku/Aredoko/releases) から最新の Windows x64 版 ZIP をダウンロードします。
2. **ZIP 全体を解凍**し（`Aredoko.exe` だけ移動せず、同梱フォルダを一緒に保持してください）、`Aredoko.exe` を開きます。初回は案内に沿って基本環境（専用 Python）をダウンロードします。
3. 探したいフォルダを登録し、**アイテム一覧だけ取得**を選ぶと、ファイル名・タグ検索をすぐに使えます。
4. AI 検索を使う場合は、**設定 → 使い方・初回設定**から AI 環境（CPU / CUDA）とモデルを自動構築し、Aredoko を再起動して登録フォルダの AI 索引を作成します。

詳しい操作方法やトラブルシューティングは [利用ガイド](docs/user-guide.md) をご覧ください。

## 動作環境・ご注意

| 項目 | 内容 |
| --- | --- |
| **対応 OS** | Windows 10 / 11（x64） |
| **未署名ファイルについて** | 配布 ZIP 内の実行ファイルは未署名（コード署名なし）です。Windows の**スマート アプリ コントロール**がオン（強制）の環境では、起動がブロックされる場合があります。 |
| **AI 自動構築の容量目安（任意）** | 取得量は最大約 4.5GB、構築時は約 15GB の空き容量が目安です。導入完了後は**設定 → ストレージとキャッシュ**から取得キャッシュ（約 3GB）を削除できます。 |

## 不具合報告・要望

不具合の報告や機能のご要望は [GitHub Issues](https://github.com/jakymiku/Aredoko/issues) までお寄せください。  
不具合報告の際は、**設定 → 診断情報**に表示されるバージョン・環境情報を添えていただけると確認がスムーズです。

## 開発を支援する

Aredoko は MIT ライセンスの無料オープンソースソフトウェアです。もし気に入っていただけたら、Ko-fi からの任意のご支援で開発を応援していただけると励みになります。

<a href="https://ko-fi.com/jakymikudev"><img src="https://img.shields.io/badge/Support%20on-Ko--fi-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Ko-fiで支援する" /></a>

## ライセンス

Aredoko 本体は [MIT ライセンス](LICENSE) です。  
同梱する FFmpeg やその他の依存ソフトウェアについては、[第三者ライセンス通知](THIRD_PARTY_NOTICES.md) および配布 ZIP 内の `THIRD_PARTY_LICENSES` をご覧ください。
