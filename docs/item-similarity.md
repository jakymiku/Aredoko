# 画像・表紙からの類似検索

> **2026-10-18**：[R02-B](full-library-search.md)で全scopeの保存済みcoverをbatch検索し、候補上限1万件を撤廃。`search_complete/search_candidate_total/indexed_total`を追加。全体回帰/Core/Releaseは更新済み、今回native/GPUは未実行。

2026-10-15：P1のAPI・Core・WinUI導線を追加。Python生成fixtureで検証済み。今回の環境に.NET SDK/Windowsはなく、Coreテストの実行・Windows Release/native GUIは未検証。実モデルでの検索品質は未評価。

続行で取消/復帰、破損vector、応答境界を補強し、[Windows一括テストと再開手順](windows-similarity-handoff.md)を追加。最終Python全300 PASS/34.080秒/skip0。`Check-Similarity.cmd`は既存環境でPython→Core→Release→生成nativeを一度ずつ実行する入口（Windows実行はここでは未検証）。

## 操作

一覧/グリッドの画像・本・ZIP、または詳細のプレビューを右クリックし「似た画像・素材を探す」を選ぶ。現在の選択とは別の行を右クリックしても、その行を起点にする。動画/音声の内容類似検索は対象外。

未保存の編集があれば既存の破棄確認を使う。「編集を続ける」で中止した場合は索引要求も画面遷移もしない。結果には起点の名前と「起点の画像・表紙に似た候補」、cosine類似度を示す。数値は正解率ではない。画像・CBZ/ZIP・動画ビューアは従来どおり。

「元の検索に戻る（取得中は取消）」で元の検索語・種類・方法・root・候補表示条件・view・ページを復元する。起点の行が同じページに残っていればfocusを戻す。復帰時にも未保存編集の確認を行う。取得中の復帰はクライアント要求を取り消し、request versionで遅延結果を無視する。サーバー側の既に始まったCPUランキングは継続する場合がある。request-ownedサーバー取消APIはR02-Cで未実装（クライアント要求の取消とは別）。

種類・フォルダ・お気に入り等の切替は類似検索を絞り込む。検索語/検索方法の変更、または「検索」で従来の文字/AI検索に戻る。通常のAI候補区切り・全語一致の設定は類似検索中には適用せず非表示とし、元に戻る際に復元する。

## API

`POST /api/library/ai/similar`。Host・session token・Origin・既存32KiB body制限を維持。

```json
{"item_id":7,"kind":"image","view":"all","page":0,"limit":60,"scope":{"root_ids":[1],"kind":"","shelf":null}}
```

- `item_id`は正のInt64。bool/string/超過IDを拒否。`page`は0以上の整数、`limit`は1〜120（既定60）。未知のフィールドを拒否する。
- `scope`省略時は保存済みAI scopeを使用。明示nullは拒否。UIでは保存済みscopeと選択rootの積集合を送る。空集合を全体検索へ広げない。root IDもInt64境界を検査する。
- 起点は有効な登録root・present・非除外・scope内の画像/本/ZIPに限定。result-onlyの`kind`/`view`には起点が一致しなくてもよい。対象外の起点は404、無効な条件は400、scan/索引/検索との競合は409、AIサービス自体の初期化失敗は503。
- 同一profileのvector DBだけを使い、起点と各候補の保存revisionを現カタログに照合する。画像/表紙の`cover` vectorのみでcosine順位を作り、同点はID順。text vectorを混ぜず、起点自身を除外する。
- scope・kind/view・自己除外後の全対象を256作品batchで読み、同profile/版のcoverを全体順位で比較する。索引jobの最大1万件は検索候補へ適用しない。容量不足等を部分成功にせずエラーとし、pageは全順位から切り出す。
- 処理中はcatalog/profile DB版・epoch/scopeを監視し、公開前に返すpageと起点を再確認する。途中の登録/除外/タグ/棚/favorite/索引更新は409で再試行を案内し、異なる状態の部分順位を返さない。索引のsource revisionは既存のカタログstat/title/tags由来。実ファイルの未スキャン変更を自動検出する機能ではない。
- 推論・source画像読み直し・モデル起動・自動索引作成・vector書込は行わない。保存済みvectorがあればencoder未導入/未ロードでも利用可能。

Coreの類似検索クライアントは10秒deadline、JSON MIME、最大2MiB・受信長を検査し、起点/モード/source/ページ/件数・自己混入/重複/非画像・cosine範囲の不整合を拒否する。通常の文字/AI検索の応答方式は変更しない。破損した非unitベクトルは起点ならunindexed、候補ならskip。クライアント取消による切断には応答の再送や不要なサーバーエラーを出さない。

応答は従来の`total/items/page/limit`に`mode:similar`、`origin_id`、`origin_revision`、`profile`、`scope`、`source:cover`、`score_kind:cosine`、`coverage_limit`、`similarity_status`を追加。各候補の根拠は`similarity_origin_id`と`similarity_evidence:cover`。

| similarity_status | 動作 |
| --- | --- |
| ready | 検索成功。候補がなければ0件。別種類/未索引を似た結果として埋めない |
| unindexed | 起点のcoverが未索引・古い・不正。itemsは空、明示索引/文字検索を案内 |
| unsupported_profile | text-only profile。itemsは空、画像対応モデル/文字検索を案内 |

## 検証とWindows実機結果（2026-10-15 Windows続行）

`python -m unittest discover -s tests -p test_similarity_search.py -v`：16件。生成PNG/CBZ＋決定的な3次元contract encoderで類似順、text/非画像混入防止、自己除外、root/kind/shelf/view、profile/revision/前処理namespace、未索引/破損、cap/paging、競合/close、Host/token/Origin、保存scope、元bytes/mtime不変と検索中encode0を確認。実モデルの精度を示す評価ではない。別途`test_similarity_sandbox.py`5件で76件の生成fixture/ページ境界/実HTTP/未索引・text-only/409・503/取消済み応答を確認。

Windows実機で `.\Check-Similarity.cmd` および個別シナリオ・回帰バッチを実行し、すべてPASS・全PNG目視確認済み：
- **Coreテスト**：`dotnet run --project tests/Aredoko.Core.Tests -c Release --no-restore` **280 PASS**（類似検索契約51件＋複数root/フォルダ管理19件を含む）。
- **Windows Releaseビルド**：`dotnet build src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Release -p:Platform=x64 -p:SelfContained=true --no-restore` **PASS（0 warnings / 0 errors）**。
- **修正事項（2修正cycle内で解決）**：
  1. 初回`similarity-check-20261015-114301-4b31e2`で、類似検索から元ページ（2/2）へ戻った直後に`ListViewItem`のXAMLレイアウト未完了により`Item65`の`HasKeyboardFocus`が立たない問題と、Windowsの切断例外`ConnectionAbortedError`（WinError 10053）を確認。`MainPage.xaml.cs`に`FocusRowAsync`（レイアウト更新・ScrollIntoView・Loaded待機）を追加し、`SimilarityBar`を1行Grid化して狭幅700×620での一覧表示領域を確保。
  2. 2回目`similarity-check-20261015-115519-ea9b7d`で、Windowsの`ThreadingHTTPServer`既定backlog（5）がプレビュー並行要求バースト時に溢れてTCP接続拒否となる問題、および同日Windows Updateによる.NET SDK `10.0.402`更新時の`--no-restore`キャッシュ参照を確認。`app/server.py`で`ThreadingHTTPServer.request_queue_size = 128`と`Connection: close`を設定し、`Aredoko.WinUI.csproj`にローカルキャッシュ済みruntime pack fallbackを追加。
- **確定したWindows native結果（全PNG目視済み）**：
  - `similarity-check-20261015-120824-dbfe63`：**PASS（diff-check / Python 300 PASS / Core 264 PASS / Release PASS / native 41 checks PASS / PNG 10枚全目視 / graceful close 2）**。Light/Darkで2ページ目起点65からの類似検索（72件）・自己除外・scope外root除外、元ページ2/2と`Item65`キーボードfocus復帰、グリッド表示、詳細プレビュー右クリックのdirty取消（要求0・draft保持）、dirty破棄承認→遅延要求→取得中戻る取消（二重確認なし・ItemList有効化復帰）、お気に入りview＋自己除外0件、未索引fallback、busy(409)/unavailable(503)からの復帰、700×620狭幅表示、元bytes/mtime・設定不変、推論0回を確認。
  - `similarity-unindexed-01`（`--scenario unindexed`）：**PASS（9 checks / PNG 2枚全目視 / graceful close 2）**。
  - `similarity-text-only-01`（`--scenario text-only`）：**PASS（9 checks / PNG 2枚全目視 / graceful close 2）**。
  - `similarity-doubleclick-reg-01`（`tools/test_image_viewer_ui.py --double-click-only`）：**PASS（22 checks / keys 16 / skip 0 / PNG 8枚全目視 / graceful close 2）**。右クリックContextFlyout追加後も一覧・グリッド・詳細・CBZのダブルクリック起動と読書位置保存が退行していないことを確認。
  - `folder-hub-native-07`（`tools/test_folder_hub_ui.py`）：**PASS（37 checks / PNG 10枚全目視 / graceful close 2）**。複数登録root（A+B）選択状態での類似検索と元の複数root選択への復帰を確認。
- **未検証範囲**：Shift+F10等のキーボードのみでのコンテキストメニュー起動、実AIモデル/GPUを用いた視覚類似検索の主観的品質評価、高DPI/High Contrast/Narratorは別課題として残す。
