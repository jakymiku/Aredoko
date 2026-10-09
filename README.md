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
- UI操作テスト: PlaywrightとEdgeを用意し、デモ起動中に `node tools/check-ui.cjs`

UIテストは専用デモDBで使用してください。架空レコードを編集して元に戻します。

## 文書
- [仕様](docs/spec.md)
- [GUI比較計画](docs/gui-comparison.md)
- [作業状況・次の作業](docs/status.md)
- [共通API](docs/api.md)

## 保存先
デモDBは `data/demo.sqlite`、画面検証画像は `cache/qa/`。
実ファイル、購入作品、AIモデル、個人設定、検索DBはGit管理しません。
サーバーは127.0.0.1にのみ接続待機し、外部公開する設計ではありません。
GUI方式はTauri + ReactとWinUI 3 + C#を比較して決定し、Python側のデータ処理を共用する方針です。

## ローカルファイルのインデックス基盤（実験的、UI未接続）

架空データのWeb試作とは別に、明示したローカルフォルダを読み取り専用で列挙してSQLiteへメタデータだけ記録するバックエンドを追加しました。**何も指定しなければ実ファイルは走査しません**。ファイル内容は読み込まず、削除・移動・変換しません。通常のデモUIは従来どおり `data/demo.sqlite` の架空データだけを使用します。

```powershell
python tools/index_library.py add "D:\Media" --exclude "cache"
python tools/index_library.py roots
python tools/index_library.py scan 1 --dry-run
python tools/index_library.py scan 1
```

データは `data/library-index.sqlite` に保存します。`--dry-run` は記録を更新しません。未接続のドライブや走査失敗は `missing` 判定にせず、以前の記録を保護します。実装範囲・対応拡張子・注意点は [インデックス基盤](docs/library-index.md) を参照してください。
