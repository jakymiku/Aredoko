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


## 製品MVPのAI検索（2026-10-12）

上記のデモAPIと区別し、製品は `/api/library/...` を使う。loopback限定。GETにもX-Aredoko-Token、更新/検索POSTには同一Originとtokenが必要。

- GET /api/library/ai/status: state/processed/total/indexed/skipped、available、profile/modalities/dimension、limit=10000。
- POST /api/library/ai/index: `{}` で既定10,000件まで。`{"limit":2000}` 等1..10000の整数も有効。bool/範囲外は400、進行中は409、AI未導入は503。
- POST /api/library/ai/cancel: 実行中の作品処理の後に中断。vectorは1作品ごと、進捗は16作品間隔＋最後に保存。表示は最大15件遅れ、再実行はfresh revisionを再利用。
- POST /api/library/ai/search: query、任意kind/view/page/source/ranking。coverage_limit=10000は対象枠上限、totalは対象中のfresh vector件数。itemsは既定60件。current除外とmanual filter適用後、eligible item ID順の先頭10,000件から検索。索引作成中はAI検索409だが文字検索は利用可能。

この段階は全ライブラリ無制限検索ではない。詳細と生成データ測定は[index-scaling.md](index-scaling.md)。
