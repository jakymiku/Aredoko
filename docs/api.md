# 共通API（操作試作 v0）

## 長い本の分割plan/start/resume（2026-10-17）

`POST /api/library/ai/pages/chunked/plan`（item/revision/scope/profile/max_pages）でCPU確認し、明示`chunked`（item/revision/page_ids/scope/profile）で1冊最大128ページを16ページ以下ずつatomic公開。最新保存jobだけを`chunked/resume`（job_id/scope/profile）で固定同範囲へ再開。profile別stateに選択を保存し、解除/変更/別scope/profile/置換jobでは拒否。旧単範囲/batchとstatus/所有cancelを共有。**GUIクライアント接続は後続**。[HTTP・状態・旧jobの扱い・検証の境界](page-chunked-indexing.md)。

## 複数本のページ索引（2026-10-17）

`POST /api/library/ai/pages/batch`（items/scope/page_limit/profile全必須、8冊・16page/冊・128page/要求）と、保存した最後のジョブだけの明示`batch/resume`を追加。状態は既存`ai/status`、ID一致の`ai/pages/cancel`を共有。scope/profile/revisionを固定し、1冊ごとにatomic公開・失敗した本を記録して継続。通常AI buildの対象は不変。[要求・再開・部分失敗と保持の境界](page-batch-indexing.md)。

## 本ごとのページ準備状況（2026-10-17）

`POST /api/library/ai/pages/coverage`はitem_id/revision/明示scopeを受け、同profileの検査済みpage vector件数・連続範囲・最大16ページの次の欠けを返す読み取り専用CPU API。画像取得/decode・snapshot更新・model load・索引なし。古い/確認できないsourceを準備済みとしない。GUIの範囲指定と次範囲への再開へ接続済み。[正確な契約・上限・生成1万ページの計測](page-image-search.md)。

## 本の内部ページ画像のAI索引（2026-10-17）

`POST /api/library/ai/pages`は既存page-indexのitem ID・page IDs（1〜16）・revision・明示scopeを受け、共有AI workerで範囲全体を原子的に保存する。`ai/status`で進捗、`POST /api/library/ai/pages/cancel {"job_id":"32hex"}`で所有jobだけ中断。既存`ai/search`のcover/allへ作品単位の最大ページscoreと`ai_page_match`を追加。通常AI buildやtext searchに内部ページを混ぜない。[正確な契約・制限](page-image-search.md)。

> **2026-10-17 未承認タグの意味検索**：`POST /api/library/tag-suggestions/search`の任意bool `semantic:true`で専用の意味索引を検索する。省略/falseは既存の文字一致を維持。索引不足件数とモデル/根拠/類似度を返し、検索から索引作成はしない。[完全な契約](tag-semantic-search.md)。


## P2/P3：ページ根拠索引と明示的な本文検索（2026-10-16 続行）

- `POST /api/library/page-index`、`GET /api/library/page-index/{item_id}` と `/pages/{page_id}?revision=...`：画像・ZIP/CBZ・フォルダ本のページID/版/順序を保存し、根拠画像を変更検査付きで取得。
- `GET /api/library/page-text/status` と `/{item_id}`、`POST /api/library/page-text/generate` / `cancel` / `search`：任意extractorの原子的な本文保存/再利用/取消、作品単位・同一ページ内ANDの明示検索。通常文字/AI/未承認タグ候補検索は維持。
- **実OCR adapter・WinUI本文画面は未接続**。既定生成503、保存済み本文はモデル不在でも検索可能。全Python383 PASS、Windows/.NET未検証。上限・認証・版・stale・adapter契約は[page-evidence.md](page-evidence.md)。

## P2：由来付きタグ候補・承認APIと未承認候補の明示検索（2026-10-16）

- `GET /api/library/tag-suggestions/{item_id}?limit=10&before=<batch_id>`：候補/確定/却下の履歴とmodel/version・物理revision・根拠ページ・stale・生成available。通常タグ検索に候補を混ぜない。
- `GET /api/library/tag-suggestions/{item_id}/evidence?revision=<64hex>`：根拠画像（単体画像またはCBZ/ZIP自然順先頭ページ）を物理revision照合付きで返却。
- `POST /api/library/tag-suggestions/generate` / `cancel` / `review`：信頼された設定済みadapterのみ、原子的な候補公開、request IDによる協調取消、現source/version一致時だけ既存タグへ追加または修正承認/却下。
- `POST /api/library/tag-suggestions/search`：`{query, kind, view, page, root_ids?, shelf?, model?}`。各作品の**最新バッチにある未承認（`pending`）候補だけ**をNFKC/大小/かな正規化・複数語ANDで検索し、`proposal_match:{batch_id, source_revision, source_state, state:'pending', tags, producer, evidence}` を付加して返す（推論やモデル起動は行わない）。WinUIの検索方法「未承認タグ候補」（`ModeTagCandidates`）と一覧行 `ProposalEvidence<id>` に接続済み。
- **ローカルWD CPU分類adapterはユーザー許可による導入・実CPU/API35checks確認済み（[実測・限界](wd-tagger.md)）。未導入環境なら生成503。WinUIレビュー（59 checks / 15 PNGs）および未承認候補の明示検索（24 checks / 4 PNGs）をWindows実機で確認済み。OCR/複数ページ解析・代表素材のタグ品質評価は後続**。[詳細仕様・制限](tag-suggestions.md)。

## 製品MVP：複数登録フォルダの和集合検索とアイテム起点類似検索のWindows検証（2026-10-15 Windows続行）

- `GET /api/items?root_ids=<id1>,<id2>,...`：1〜256件の有効な登録root ID（正のInt64・重複不可）の和集合（OR）で通常文字検索・関連語展開・partial fallbackを実行。既存の単一`root_id`も互換維持（両方同時指定や空指定`root_ids=`・未登録/解除済みrootは400で拒否し、全件検索へ拡大しない）。
- `POST /api/library/roots` は任意の `folder_books: true|false`（画像フォルダを一冊として扱う、スキャン後は変更不可）。`GET` の各rootに `folder_books`。詳細は[folder-books.md](folder-books.md)。
- `GET /api/library/roots?include_inactive=0|1`：各rootに索引済みpresent件数`present_count`を付加（新たなファイル走査は行わない）。
- `POST /api/library/ai/similar`・`POST /api/library/ai/search`：Coreの`FolderSearch.RestrictAIMulti`により、UIで選択した複数root集合と保存済み`aiScope`の積集合を送信（空集合を全体へ拡大しない）。詳細：[登録フォルダ管理](folder-library-management.md)・[類似検索](item-similarity.md)。全Python 301 PASS、Core 280 PASS、Windows x64 Release・native GUI確認済み。

- `GET /api/library/video/{id}/frame?revision=<64hex>&at_ms=<integer>`：時刻付きPNG、最大24時間/512KiB、active root・現revision検査。詳細：[シークpreview](video-seek-preview.md)。

## 製品MVP：読み取り専用動画ストリームAPIと語別根拠のWinUI接続（2026-10-14 Windows続行）

- `GET /api/library/video/{id}/manifest`・`/range?revision=<64hex>`：通常再生用の認証付き範囲取得。最大2TiB、単一明示Range 1MiB以下、成功206/更新409/範囲外416。詳細：[動画範囲再生](video-streaming.md)。
- `GET /api/library/video/{id}`：登録・索引済みのpresentな動画（`.mp4/.mkv/.webm/.avi/.mov/.wmv/.m4v/.ts`、最大64MiB）を、active root・除外・symlink/reparse・open handle前後のstat一致・playlist偽装拒否（`#EXTM3U`/`[playlist]`/`<asx`）を検査したうえで返す。Hostと`X-Aredoko-Token`必須、`Cache-Control: no-store`。未対応/欠損/超過/playlist偽装は404、索引後の変更は409、共通2枠使用中は503、不正ID/URLは400。
- `search_evidence`はCoreの`Protocol.DescribeEvidence`とWinUI一覧の`SearchEvidence<id>`で表示接続・Windows実機確認済み。全Python 264 PASS、Core 168 PASS、x64 Release PASS。

## 製品MVP：通常検索の語ごとの根拠（2026-10-14 夜）

queryありの`GET /api/items`は各itemに`search_evidence:{direct_words,related_words,missing_words}`を追加。正規化・重複除去した各query語を、直接文字一致/辞書による一致/未一致へ分ける。最大16語。既存match/partial/expansions・順位・filter・root・pagingは保持し、queryなし一覧・個別GET・AI検索にはこの新fieldを追加しない。タグ/DB schema/model/vector変更なし。[正確な意味と評価結果](literal-search-v6.md)。

## 製品MVP：タグ値の照合とID境界の安定化（2026-10-14 続行）

名前・タグ検索とAI検索の文字一致表示/フィルターは、保存JSONのエスケープや区切り記号ではなく実際のタグ値を使う。引用符・バックスラッシュ入りのタグ、Unicode escapeで保存されたタグも検索し、保存値の書き換えはしない。[詳細](related-terms.md)。

`GET /api/items/{id}`、`POST /api/items/update`の各id、登録rootの除外/スキャン等はpositive Int64のIDを事前検証する。範囲外・bool・0・負数は400、範囲内の未登録作品は404。前者が含まれる一括更新は全体を拒否し、タグ/棚/お気に入りを一部だけ更新しない。無効なrootでscan jobを作らない。認証/Origin/loopback制約は従来と同じ。全Python256 PASS、今回Windows/.NET/native未検証。

## 製品MVP：動画先頭フレームとプレビューID検証（2026-10-14）

`GET /api/library/preview/{id}`は既存の画像/CBZ/ZIPに加え、任意導入済みffmpeg/ffprobeで動画の先頭frameをPNGとして返す。Hostとtoken必須、no-store。動画の10秒・32GiB入力・16M画素・256px出力・512KiB本文・共通2枠・memory LRUと制限は[video-thumbnails.md](video-thumbnails.md)。ツール不在/破損/非対応は404、枠不足は503。

idは1..9223372036854775807のASCII十進数、先頭0・負数・余分なpath/queryは禁止。不正要求は400 `Invalid item`。従来の超過値はSQLite `OverflowError`で応答できなかったため修正した。全Python246 PASS（Linux）。Windows Release/nativeは今回未検証。

## 製品MVP：文字検索の正規化・複数語AND・関連語辞書（2026-10-13）

`GET /api/items?q=` は語ごとのAND・NFKC/大小/かな正規化になり、ユーザー辞書の展開があった時だけ`expansions`と各item`match`を返す。`GET /api/items`の検証失敗は400で具体的な`error`（`Use at most 16 search words`、`Invalid paging`、`Invalid filter`）。WinUIは`ErrorText`で日本語表示。全語一致0件・2語以上のときは1語欠けの作品を`match:"partial"`と応答`partial:{words,required}`で返す。辞書は`GET /api/library/terms`、`POST /api/library/terms`、`POST /api/library/terms/delete`、`GET /api/library/terms/export`、`POST /api/library/terms/import`。詳細・制限・未検証範囲は[related-terms.md](related-terms.md)。最新全Python205件PASS（Linux）。


## 製品MVP：読み取り専用CBZ/ZIPページAPI（2026-10-13）

WinUI読書画面への接続は後続Windowsの生成素材で検証済み（[専用windowの検証範囲](viewer-reader-validation.md)と最新handoffを参照、今回Linuxでは再実行していない）。登録・索引済みitem IDだけを受け付け、元ファイルや展開ファイルを書き込まない。GETはHost検証とX-Aredoko-Token必須、応答はCache-Control: no-store。

| GET | 応答 |
| --- | --- |
| `/api/library/reader/{id}` | `{item_id,page_count,revision}` |
| `/api/library/reader/{id}/pages/{page}?revision={revision}` | 指定ページの画像bytesとContent-Type |

pageは0始まり、0..9999かつpage_count未満。revisionはmanifestの64文字小文字hexをそのまま送る。未知query・重複revision・任意path・負の値・不正IDは400、Host/token不正は403。対象/ページがない・未対応・破損・制限超過は404、metadata変更/古いrevisionは409（再scanとreader再open）、共通preview枠使用中は503。

画像は既存previewと同じ拡張子・自然順、`__MACOSX/`を除外。数字は整数化せず桁数と文字列で比較し、長い数字名・Unicode decimal・先頭0も扱う。同順位・同名はZIP directory順を保持しZipInfoで読む。manifestは画像を展開せず候補数だけ返すため、各ページのdecode成功や暗号化/破損なしを保証しない。非先頭ページのエラーでもページ番号を詰めたり別ページへ代替したりしない。

登録root/除外/present/reparse/symlink/索引size・mtime/open handleの再確認と、既存のarchive512MiB/directory4MiB/entries10000/image8MiB/圧縮比200を共有。ZIP64/multidisk非対応。readerとpreviewで同じ2処理枠。画像/CBZ/ZIPではサーバーは元画像をdecodeせず、GUI側でも既存ThumbnailCodec同等のpixel/byte/decode制限が必要。動画thumbnailのみサーバーで先頭frameをdecodeする。

revisionはfile identity・size・mtime・ctimeから作る変更検出tokenであり、内容hash・不変snapshot・悪意ある同一metadata書換えの保証ではない。各要求で同じhandleを使って前後metadataを確認。409を受けたclientは古いpage要求の自動retryをせず、新しいmanifestを取得して明示的に開き直す。フォルダ本/Komgaは未実装。読書位置と表示方向は[progress API](reader-progress.md)で保存・復元する。ページ取得APIは従来通り1ページずつ返す。

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


## 読書位置 API

GET/POST `/api/library/reader/{id}/progress` を追加。revision・0始まりpage・single/rtl/ltrを本ごとに保存する。Host/token/Origin、現manifest検査・scan guard・非本/解除/除外拒否、stale write拒否を維持。[操作・契約・検証](reader-progress.md)。

## アイテム起点の類似検索（2026-10-15）

`POST /api/library/ai/similar`：同profile/current revisionの保存済み画像・表紙vectorから類似順に返す。scope・自己除外・未索引fallback・認証を含む詳細は [item-similarity.md](item-similarity.md)。動画/音声の内容類似検索は未実装。今回のWinUI導線はソース追加済み、Windows実機未検証。

- P2根拠読取：`GET /api/library/tag-suggestions/{id}/evidence?revision=<64hex>`。Host/token必須、登録中sourceの同一handle画像と物理版を照合。変更409・不在404・不正400、8MiB画像の既存上限を継承。詳細は[tag候補仕様](tag-suggestions.md)。

## 2026-10-16 閲覧履歴・サブフォルダ指定

- `POST /api/library/roots` の任意 `recursive: boolean`：新規/既存移行は省略時true、解除済み再登録では省略時保存値を保持。falseは直下だけを索引。`consent:true`と既存の認証は必要。再登録でfalseへ狭めると下位locationを即時excluded、再びtrueならrescanで復元。
- `POST /api/library/history` は厳密に`{"item_id": positive int64}`のみ。既存Host/Origin/session-token/body上限を適用。presentかつenabled、現在の除外対象でないアイテムを記録し`{"recorded":id}`。不正400/認証403/対象不在404。元ファイルは読まず、`view_history(item_id,opened_ns,open_count)`のupsertだけを行う。
- `GET /api/items?view=history`：最近開いた順、同じアイテムは一件。既存q/kind/root_idまたはroot_ids/page/limitを保持し、解除root/現在の除外を隠す。通常の文字・関連語検索が対象。GUIでは画像/本/動画の表示成功時に記録し、履歴中のAI/未承認候補検索は無効化。音声を外部アプリで開いた履歴は今回未接続。


## 2026-10-17 DB完全削除のプロファイル別索引

`POST /api/library/roots/purge`のbody/成功応答は従来どおり。解除済みrootのcatalog内依存に加え、同じcatalog由来の厳密な命名/内部profile keyを照合した`*.ai.sqlite` / `*.ai.<24hex>.sqlite`の`ai_vectors`・`ai_video_frames`・`ai_source_contracts`も削除する。無関係なDBやリンク先は削除しない。大量件数でも全item IDをSQL引数へ展開しない。

複数DBは一つの完全atomic transactionにはできないため、派生AIデータをprofile DBごとのtransactionで先に削除し、その後catalog内の手動記録をcommitする。途中失敗では登録/タグ等の手動記録と解除済みrootを保持し、日本語エラーを返して再試行可能にする。先に消えた派生AI索引は、必要なら再作成する。元メディアの削除・改変は行わない。
