# 共通API（操作試作 v0）

## 製品MVP：文字検索の正規化・複数語AND・関連語辞書（2026-10-13）

`GET /api/items?q=` は語ごとのAND・NFKC/大小/かな正規化になり、ユーザー辞書の展開があった時だけ`expansions`と各item`match`を返す。全語一致0件・2語以上のときは1語欠けの作品を`match:"partial"`と応答`partial:{words,required}`で返す。辞書は`GET /api/library/terms`、`POST /api/library/terms`、`POST /api/library/terms/delete`、`GET /api/library/terms/export`、`POST /api/library/terms/import`。詳細・制限・未検証範囲は[related-terms.md](related-terms.md)。最新全Python204件PASS（Linux）。


## 製品MVP：読み取り専用CBZ/ZIPページAPI（2026-10-13）

WinUI読書画面への接続実装を追加（Windowsビルド/実GUIは未検証、[確認手順](archive-reader.md)）。登録・索引済みitem IDだけを受け付け、元ファイルや展開ファイルを書き込まない。GETはHost検証とX-Aredoko-Token必須、応答はCache-Control: no-store。

| GET | 応答 |
| --- | --- |
| `/api/library/reader/{id}` | `{item_id,page_count,revision}` |
| `/api/library/reader/{id}/pages/{page}?revision={revision}` | 指定ページの画像bytesとContent-Type |

pageは0始まり、0..9999かつpage_count未満。revisionはmanifestの64文字小文字hexをそのまま送る。未知query・重複revision・任意path・負の値・不正IDは400、Host/token不正は403。対象/ページがない・未対応・破損・制限超過は404、metadata変更/古いrevisionは409（再scanとreader再open）、共通preview枠使用中は503。

画像は既存previewと同じ拡張子・自然順、`__MACOSX/`を除外。数字は整数化せず桁数と文字列で比較し、長い数字名・Unicode decimal・先頭0も扱う。同順位・同名はZIP directory順を保持しZipInfoで読む。manifestは画像を展開せず候補数だけ返すため、各ページのdecode成功や暗号化/破損なしを保証しない。非先頭ページのエラーでもページ番号を詰めたり別ページへ代替したりしない。

登録root/除外/present/reparse/symlink/索引size・mtime/open handleの再確認と、既存のarchive512MiB/directory4MiB/entries10000/image8MiB/圧縮比200を共有。ZIP64/multidisk非対応。readerとpreviewで同じ2処理枠。サーバーは画像をdecodeしないため、GUI側でも既存ThumbnailCodec同等のpixel/byte/decode制限が必要。

revisionはfile identity・size・mtime・ctimeから作る変更検出tokenであり、内容hash・不変snapshot・悪意ある同一metadata書換えの保証ではない。各要求で同じhandleを使って前後metadataを確認。409を受けたclientは古いpage要求の自動retryをせず、新しいmanifestを取得して明示的に開き直す。フォルダ本/Komga/見開き/読書位置保存は未実装。

ZipFile構築前にZIP64 locatorを拒否し、central directoryの固定headerを走査して実件数/申告件数一致と可変長field境界を確認。entry内のZIP64 sentinel/multidiskも拒否する。件数やサイズの自己申告だけを信用してZipInfoを生成しない。

生成素材での再現：`python -m unittest discover -s tests -p 'test_reader.py' -v`（16件）。ZIP preflight7件は`test_zip_limits.py`、旧preview12件・production6件も同じ形式で実行。当時の全Python178件PASS（最新は上記節）。Windows native/GPU検証ではない。

## 既存のデモAPI

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

## AIリソース設定（2026-10-12）

- POST /api/library/ai/release: 本文 `{}`。所有idle workerだけ停止し、検索/索引処理中は即時409。次のAI検索は同一profileでlazy reload。vectors/sourceは変更しない。
- GET /api/library/ai/resource: 保存済みpolicy。POSTは `{"idle_release_seconds":0,"index_pause_ms":0}`。整数0..3600秒 / 0..2000ms、両項目必須。初期は無効、保存成功後すぐ適用。設定JSON破損/保存失敗は409、動作中の設定を維持。型/範囲不正は400。
- statusにはresident/worker_state/device/telemetry/resource_policy。解放後はresident=false、device空、telemetry空。profile/vector identityは維持。token/Origin規約は他のlibrary APIと共通。

## AI対象scope（GUI・設定保存・CPU/API、2026-10-12）

index/searchは任意 `scope:{root_ids:[1,2],kind:"image",shelf:"素材"}` を受け付ける。登録rootだけ、配列最大256・正整数・重複不可、nullは全登録root、空配列はゼロ件。kindは既存TYPESまたは空文字、shelfは完全一致80文字まで、nullは指定なし・空文字は未整理。未知キー/不正型/削除済みID/明示scope:nullは400。scope省略は既存の互換経路。

- POST `/api/library/ai/coverage`: `{}` または `{"scope":{...},"limit":10000}`。未知本文キーは400、limitは1..10000の整数、scan中は409。モデル推論やworker起動をしない。戻り値は `scope,candidate_total,target_total,fresh_total,remaining_total,coverage_limit:10000,index_limit,refresh_required_on_change:true`。candidateは上限前、targetはlimit後、freshは同一profile/revisionのtextレコード、remainingはtarget-fresh。表紙の成功/品質/破損検査とは別。
- POST index: scopeで絞ってpresent/除外後のID順を選ぶ。job scopeをコピーしてai_stateに保持、restart後もstatus.scopeで取得。範囲を切り替えてもvector store/model identityは変えず、他範囲を削除しない。
- POST search: 明示scope内の共通先頭10000件に追加kind/viewを適用し、対象枠を検索側だけ選び直さない。省略scopeは旧manual filter適用後の先頭10000互換経路。custom index limitはjob量だけで、search対象枠は10000のまま。

件数と検索枠はcatalog変更後に更新が必要。jobは開始時ID/範囲を固定してpublish前に再検査。Host/token/Origin規約を維持。GUIは保存済みuser scopeをindex/searchへ明示送信する。job scopeとは独立に次回起動へ永続化。scope省略APIの挙動を暗黙変更しない。詳細は [対象選択の契約](ai-coverage-selection.md)。

- GET `/api/library/ai/scope`: `{scope,valid,missing_root_ids,error}`。削除済みrootはIDを保持してvalid=false。設定破損は409でAI利用を止め、文字検索は独立。scope単体の不正値はPOSTで修復可能だが、JSON全体/基礎設定破損はモデル選択保存または設定ファイル修復が必要。
- POST同route: `{"scope":{...}}` のみ。型/未登録ID/未知キーは400、scan/AI索引busyまたはatomic保存失敗は409。成功応答はGETと同じshape、valid=true。既存profile/resource保存を保持し、モデル起動・索引削除なし。認証は他のlibrary APIと共通。

