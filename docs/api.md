# 共通API（操作試作 v0）

127.0.0.1限定。PythonのCatalogが永続化を担当し、GUIはSQLを直接扱わない。

- GET /api/session: デモ識別、全体件数、更新用セッショントークン。
- GET /api/items?q=&kind=&view=&page=: 60件単位の一覧。pageは0始まり。kindはbook/image/video/audio。viewはall/favorites/unreviewed/shelf。
- GET /api/items/{id}: 1件の詳細。
- POST /api/items/update: {ids:[1,2],changes:{tags:["tag"],shelf:"棚",favorite:true,reviewed:true}}

更新では同一OriginとX-Aredoko-Tokenが必要。最大120件。全IDが存在する場合のみまとめて更新する。
クライアントは検索結果の到着順の逆転を無視し、古い応答で新しい結果を上書きしない。
将来のGUI比較でも同じ応答データを使う。これはローカル試作APIで、リモートアクセス用の認証基盤ではない。
将来は複数棚、楽観ロック、作品と保存場所の分離、検索カーソルを追加する。

## 将来の共通バックエンド（現時点ではHTTP API未接続）

`app/library_index.py` へ `LibraryIndex(db_path)` を追加しました。登録、再走査、`roots()`、`locations()` はPython側から利用できます。こちらは別DBを使用し、試作の `/api/items` が返す5万件の架空データには混ぜません。詳細は [インデックス基盤](library-index.md) を参照してください。HTTP経由で実ファイルのパスを返すエンドポイントは追加していません。
