# Aredoko
画像・本・動画・音楽を、あいまいな記憶から探す。

Windows向けローカルライブラリ。現在は **架空データを使った操作試作** です。

## 起動
Python 3.12以降を用意して `start-demo.cmd` をダブルクリックします。
または `python app/server.py --open` を実行します。
ブラウザに http://127.0.0.1:8765 が開きます。起動したコンソールで Ctrl+C を押すと終了します。
追加のPythonパッケージは不要です。初回は5万件の架空データを自動生成します。
ポート競合時は `python app/server.py --port 8766 --open` を使えます。

## 現在できること
- コンパクトな検索・広い一覧・右の詳細/タグ編集パネル（狭い画面ではスライド表示）
- 未保存変更の確認、検索の空結果・通信エラーからの復帰
- 5万件の一覧を60件ずつ表示
- タイトル・タグの文字検索、メディア種別で絞り込み
- お気に入り・未確認・棚に入れたものの表示
- 単体・一括でタグ、棚、お気に入り、確認済みを編集
- SQLiteに保存し、再起動後も編集を保持

実ファイルは読み取りません。AI検索、読書ビューア、フォルダ登録、Komga連携、Tauri/WinUI本体は未実装です。
今回のWeb UIは操作仕様を固める土台であり、Tauri版の性能測定結果ではありません。
一括編集は対象の値を置き換えます。棚は試作では1件のみです。

## 開発と検証
- `python -m unittest discover -s tests -v`
- `node --check web/app.js`
- UI操作テスト（自動で一時DBを作成・破棄）: Node版PlaywrightとMicrosoft Edgeを用意し、`node tools/run-ui-check.cjs`
- `node tools/check-ui.cjs` は既に起動しているデモを検査する従来コマンドです。必ず検証専用DBで使ってください。

UI自動テストは `--db` オプションを使用してシステム一時フォルダに5万件の架空レコードを作り、HTTPサーバーをランダムな空きポートで起動します。通常の `data/demo.sqlite` を読み書きしません。WindowsのGitHub ActionsでもEdge自動操作を実施します。手動でテスト用DBを作る場合は `python app/server.py --db data/ui-test.sqlite --port 8766` を利用できます。

## 文書
- [仕様](docs/spec.md)
- [GUI比較計画](docs/gui-comparison.md)
- [作業状況・次の作業](docs/status.md)
- [UI監査・今回の改修と検証](docs/ui-audit.md)
- [共通API](docs/api.md)

## 保存先
デモDBは `data/demo.sqlite`、画面検証画像は `cache/qa/`。
実ファイル、購入作品、AIモデル、個人設定、検索DBはGit管理しません。
サーバーは127.0.0.1にのみ接続待機し、外部公開する設計ではありません。
GUI方式はTauri + ReactとWinUI 3 + C#を比較して決定し、Python側のデータ処理を共用する方針です。
