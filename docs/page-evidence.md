# ページ単位の根拠索引と本文検索（2026-10-16）

画像・ZIP/CBZ・明示登録したフォルダ本について、作品/版/ページを区別して根拠を保存するバックエンド。元ファイル・確定タグ・棚・お気に入り・読書位置を書き換えない。ページ索引はメタデータだけで作れ、本文抽出は任意の信頼されたローカルadapterを必要とする。

**実OCRモデルとWinUI画面は未接続。** 製品起動時の本文抽出は503で、架空のOCR結果を返さない。保存済み本文の一覧/明示検索はモデル不在でも使える。生成画像と偽adapterの契約テストはOCR精度や実ライブラリの検索品質を示さない。既存の表紙のみのタグ候補・候補レビュー・通常/AI検索は維持する。

## 識別・版・保存

- `page_id`：作品ID・source種別・内部ページlocator・同名出現番号から生成する64文字小文字SHA-256。ファイル名/pathはAPIへ出さない。同じファイル名の前に別ページが増えてもIDを維持し、ページ番号はその版での0始まり位置として別保存する。rename/moveの推測や内容による同一性判定はしない。
- ZIPの同名entryは中央directoryの出現番号で区別する。自然順tieは既存readerと同じ中央directory順。再packで同名entryが入れ替わった場合の永続同一性は保証しない。フォルダ本のtieはファイル名のUnicode順。
- `source_revision`：既存reader/taggerと同じ物理revision。内容hashではなくファイルidentity/size/時刻、フォルダならページinventoryから導く変更検知token。保存・抽出・画像取得時に再検査する。完全なfilesystem snapshotの保証ではない。
- 追加テーブル：`page_snapshots` / `page_entries` / `page_heads`、`page_texts` / `page_text_heads`。本文はsnapshot・page ID・producer（adapter/version/model/model_revision/preprocessing）の組に保存する。同一版・同一producerは空文字も処理済みとして再利用する。
- 各作品の現在のpage snapshot、各ページの選択producerをheadで指定する。過去の版/producerの記録は残すが、現在の検索へ自動混入しない。旧producerの再選択も推論なしで可能。版を更新した後は、同じpage IDでも旧版の本文を自動移植しない。
- 現段階では履歴の自動削除・一括GC・全root自動索引・永続job queueはない。繰り返し再解析したDBの容量管理は後続。既存DBへ追加schemaを適用するだけで既存レコードを破壊しない。

## API

すべてloopbackの既存Host/session-token検証、POSTは同一Originと32KiB上限を使用。任意path・本文・モデル設定をクライアントから注入できない。作品IDは正のInt64、bool不可。`revision`と`page_id`は64文字小文字hex、`request_id`は毎回新しい32文字小文字hex。余分/重複query・余分body fieldを拒否する。

| Method / route | 入力・返却 |
| --- | --- |
| `POST /api/library/page-index` | `{item_id}`。対応ページのメタデータsnapshotを作成/再利用。`item_id, source_revision, source_kind, page_count, reused`。source_kindは`image/archive/folder`。 |
| `GET /api/library/page-index/{item_id}` | `offset`既定0・最大10000、`limit`既定60・最大100、任意`revision`。`source_revision, source_state, page_count, pages:[{page_id,page,mime,size_bytes}]`。 |
| `GET /api/library/page-index/{item_id}/pages/{page_id}?revision=<64hex>` | 指定版に属するページの画像bytes。ページIDと現物理revisionを両方照合。旧版画像は保管/表示しない。 |
| `GET /api/library/page-text/status` | `{available,reason}`。既定はモデル未接続。 |
| `POST /api/library/page-text/generate` | `{item_id,page_ids,revision,request_id}`。重複なし1〜16ページを明示選択して同期抽出。`processed/reused`を返す。先にpage-indexを作る。 |
| `POST /api/library/page-text/cancel` | `{request_id}`。対応する実行中要求だけ協調取消、`cancel_requested`。完了後/別要求はfalse。 |
| `GET /api/library/page-text/{item_id}` | `offset`既定0・最大10000、`limit`既定10・最大10、任意`revision`。現在snapshotの処理済み本文だけをページ順で返す。`total, pages:[{page_id,page,text,producer}]`と版/状態。空本文は未処理と区別する。 |
| `POST /api/library/page-text/search` | 必須`query`、任意`kind,view,page,root_ids,shelf,model`。本文だけの明示検索、`search_mode:'page-text'`。 |

一覧の`offset>0`には初回応答の`revision`必須。途中でheadが変わると409、異なる版のページを混在させない。状態は`unindexed/current/stale/unverified/unavailable`。保存済み一覧/検索は元ファイルが欠損/古い場合もその状態を明記して返す。登録解除・除外した作品は取得不可、検索にも出ない。現在の除外ルールは再スキャン前にも適用する。

本文検索のqueryは1〜300文字・最大16語、空/空白だけは拒否。NFKC/大小/かな正規化後に**同じページ内で全語AND**。別ページの語を合算して一致にせず、関連語展開・意味ranking・タグ推測は行わない。結果は作品ID順、1ページ20作品、同じ作品の該当ページを集約する。各作品の`page_text_match`は`source_revision,source_state,matching_pages,pages`を含み、ページ根拠は先頭3件、本文抜粋は各ページ先頭240文字（必ずしも一致語の周辺ではない）、producerを返す。全文は本文一覧から取得できる。

`root_ids`は有効な登録root IDの1〜256件・重複不可・和集合。空配列/解除済み/不明IDは400で全体へ拡大しない。`view`は`all/favorites/unreviewed/shelf`、`shelf`は80文字以下、`model`は選択producerのmodel名で完全一致。省略だけが全有効root。検索pageは0〜1000000。

変更/索引・抽出競合/scan中/取消は409、source不在/未対応は404、不正指定400、adapter不在/故障・preview枠不足503。固定エラーの日本語を`ErrorText`へ追加しているが、専用GUIはまだない。

## 上限と公開タイミング

ページ索引は画像をdecode/decompressしない。既存readerの上限（画像8MiB、ZIP/CBZ512MiB・中央directory4MiB・10000entry、フォルダ10000画像候補）を継承。個々の根拠画像取得には暗号化・圧縮比200倍・リンク/ジャンクション拒否と前後のhandle/path/inventory確認を適用する。ZIP memberは展開先へ書かずZipInfoから読む。ページ索引に載っても、超過/未対応の画像bytesは取得できない場合がある。

本文は1ページ20000文字、新規抽出分は1要求100000文字まで。制御文字（改行/CR/tabを除く）・不正Unicode・非文字応答を拒否。長文の正規化は既存の短文LRUに保持しない。モデル処理中はcatalog/SQLiteのlockを保持せず手動編集を許し、保存直前にroot・head・producer・取消・現物理revisionを再検査する。失敗/取消なら要求全体をrollbackし、以前の本文と手動編集を保持する。

adapter契約は`.info.record()`（上記5項目）と`.extract({source,data,mime}, cancelled) -> str`。`source`はitem/revision/kind/page/page_idだけ、任意filesystem pathなし。信頼されたadapter側が画像decodeの画素数、timeout、共有推論lock、worker終了を実装し、取消callbackを監視すること。現段階はadapter接続口のみであり、OCRランタイム・モデル・自動ダウンロード・CLI設定は追加していない。

## 検証と次の接続

`tests/test_page_index.py` と `tests/test_page_text.py` は生成PNG/ZIP/フォルダと一時DB・偽extractorで識別、順序、重複entry、再起動、改版、rollback、取消、手動編集、root scope、pagination、auth、既定503を検証する。最新の件数/時間は[最新handoff](codex-handoff.md)を参照。Windows Release/XAML/native GUI、実OCRの日本語認識・検索品質、実ライブラリと大規模性能は未検証。

次は固定素材/正解本文の評価データと採点を準備し、その後に許可された日本語OCR adapterを接続する。さらに本文/複数ページ由来のタグ候補契約とWinUI根拠確認へ進む。現在の表紙だけの候補APIを、本文解析済みとして扱わない。
