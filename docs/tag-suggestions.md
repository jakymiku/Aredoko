# P2：由来付きタグ候補・承認APIの最初の縦切り

> **2026-10-16 続行**：[ページ根拠索引・本文保存/明示検索の独立API](page-evidence.md)を追加。実OCRと複数ページタグ候補への接続は後続。本書の既存タグ候補は引き続き画像/表紙のみの由来で、本文解析済みとは扱わない。

2026-10-16。[製品ビジョン](product-vision.md)・[開発優先順位](development-priorities.md)に沿うバックエンドとWinUIの基盤。**P2全体の完成ではない。WD画像分類adapterの接続コードを追加（[導入・検証状況](wd-tagger.md)）。WinUI候補/根拠・修正承認/却下・履歴・取消画面（通常/狭幅/live resize）と、確定タグとは分離した「未承認タグ候補」の明示検索モード（`POST /api/library/tag-suggestions/search` / `ModeTagCandidates`）までWindows実機で確認済み。OCR/複数ページ解析、および代表素材での実タグ品質評価は未実施。** EmbeddingGemmaの既存埋め込み処理をタグ生成モデルとして扱わず、固定の偽アダプタによる契約テストと実モデルの品質を区別する。

## 保存と承認

- 通常起動時、既存DBに `tag_proposal_batches` / `tag_proposals` / 参照用indexを追加する非破壊の `CREATE IF NOT EXISTS`。元ファイルや既存 `items` の値を移行・書換しない。
- batchにitem、物理source revision、adapter/version、model/model revision、前処理version、画像/表紙の区別、根拠page（0始まり）、作成時刻を保存。proposalに元の候補タグ、説明、pending/accepted/rejected、修正確定タグ、review version、日時を保存する。数値スコア専用columnや正解確率はこのsliceでは作らない。WD adapterは説明に分類出力を併記し、正解確率と区別する。
- 候補は `items.tags` に自動投入しない。**承認時だけ、現在保存されているタグとの和集合を同一SQLite transactionで保存**。修正承認も可。却下は整理情報を変更しない。タグは既存同様最大30個/60文字。上限超過・stale・競合・末尾のsource再確認失敗はタグと承認を両方rollback。
- 元の候補と修正内容を別に保持。既存の棚・お気に入り・確認済み・読書位置を変更しない。通常の文字検索が使うのは保存済みの確定タグで、未承認/却下候補は混ぜない。
- source revisionはreader同様のroot/相対位置・file identity・size/mtime/ctimeによる**メタデータtokenであり全内容のhashではない**。手動タグ/タイトルとは独立。タグを1個承認しても残り候補をstaleにしない。元ファイル変更後は再scan/再解析が必要。source不在・root解除/除外中は候補の操作不可、DB履歴は保持する。再登録後も履歴を確認できる。
- 同じitem/source/producerは一つのbatchに制約。生成再実行は既存batchを返し、承認/却下を消さない。「未判定」は候補0件の完了batch。source/producer版が変われば新batch、過去の決定は履歴として残る。別モデルの新提案を自動的に過去の却下へ同一視する仕組みは未実装。

## ローカルアダプタ契約

`TagSuggestions(catalog, adapter=None)` が入口。公開APIから任意path/model/proposalを注入できない。製品serverは設定したローカルWD adapterを利用し、未導入/不正な場合は生成要求に503と未接続理由を返す。起動から自動取得しない。検索・手動タグは利用可能。

将来の信頼されたローカルadapterは、固定の `TaggerInfo(adapter, version, model, model_revision, preprocessing)` と `suggest(payload, cancelled)` を提供する。payloadは検査済みの最大8MiB画像またはCBZ/ZIPの自然順先頭画像のbytes/mime/source tokenだけ。パスは渡さない。現在は根拠page=0のみ、最大30個の `TagProposal(tag, explanation, page=0)` を返す。未取得のページを根拠にしない。人物関係/物語タグを表紙から断定する設計ではない。

登録/在席/除外/reparse・リンク/サイズ・handle identity/変更確認は既存 `PreviewReader` を再利用。ZIPは既存の512MiB archive、4MiB directory、8MiB画像、圧縮比/暗号化等の制限を継承する。[明示登録した画像フォルダ本](folder-books.md)も自然順先頭ページを入力にできる（本文/複数ページ解析ではない）。フォルダ本では画像候補10000件の上限と、読み取り前後のディレクトリ/ページ差し替え・ページ一覧の再確認を適用する。動画・音声・PDFは入力対象外。

サービスは一度に一生成、推論中にcatalog guardを握らず手動保存を妨げない。32桁hex request IDで取消。adapterは取消関数を定期確認する必要があり、サービス共通部分は協調取消。接続したWD adapterは90秒timeout/取消/closeで所有workerを終了する。完了時に全候補を一括検証してから原子的に公開する。失敗・取消・source/adapter変更時は部分batchを保存せず、再実行可能。完了後の取消はfalse。クラッシュ時の途中進捗や永続job queueはまだない。

[WD adapter](wd-tagger.md)に共有推論lock・timeout・worker解放・固定profile/入力前処理の接続コードを追加。実モデルの導入/CPU実行・小規模な固定品質評価は別gateとして最新handoffを参照。新モデル/依存を黙って取得しない。

## API（loopback・session token）

| Method / route | 入力 / 動作 |
|---|---|
| `GET /api/library/tag-suggestions/{item_id}` | 履歴/由来/状態と現在source revision、各batchのstale、生成available/reason。`limit`既定10・最大20、`before`で古いbatchを取得、`next_before`を返す。item固有の履歴であり全体検索ではない。 |
| `GET /api/library/tag-suggestions/{item_id}/evidence?revision=<64hex>` | 同一handleで読んだ画像/自然順先頭表紙の物理revisionを照合し返す。変更409/不在404/不正400。旧版画像は表示しない。 |
| `POST /api/library/tag-suggestions/generate` | `{item_id, request_id}`。設定済みadapterだけを実行、または既存同一batchを再利用。未接続503。 |
| `POST /api/library/tag-suggestions/cancel` | `{request_id}`。対応する実行中要求だけを取消。 |
| `POST /api/library/tag-suggestions/review` | `{item_id, proposal_id, version, decision}`。decisionは`accept`/`reject`、acceptだけ任意`tag`で修正。pending/version一致・現在source一致が必須。再承認/古い状態409、他itemのproposal404。 |
| `POST /api/library/tag-suggestions/search` | `{query, kind, view, page, root_ids?, shelf?, model?}`。有効な登録root（非除外）のうち、各itemの**最新batch**に`pending`候補が存在する作品を検索。`query`空欄なら全未承認候補付き作品、入力時は正規化語のAND照合。各行に`proposal_match:{batch_id, source_revision, source_state, state:'pending', tags, producer, evidence}`を付加。モデル推論は行わない。 |

すべて正のInt64 ID（bool不可）、余分/重複queryや余分body keyを拒否。POSTは既存のHost/Origin/tokenと32KiB body上限を継承。GETも正しいHost/tokenが必要。busy/scan/変更競合409、source不在404、不正入力400、adapter障害503。未設定/モデル障害を候補成功として返さない。

## 検証境界

`tests/test_tag_suggestions.py`：生成PNG/自然順2ページCBZ・一時DB・偽adapterだけ。由来/未承認非混入、修正承認/却下、manual edit後の承認、再起動/版変更/再解析/未判定、source変更/差替え/rollback、30タグ上限/重複、cancel/再試行/並行manual edit、2 service同時生成、入力上限、scan/除外/root解除復元、履歴pagination/ID、HTTP認証/厳密引数/409/503を確認。

これは**保存・承認・境界の契約検証**。実AIタグ精度・GPU推論・OCR・WinUI操作・実ライブラリ・大規模性能の検証ではない。C#は既存ErrorText辞書への日本語エラー追加のみ。XAML/GUI構造は未変更。Core契約テストとWindows x64 SelfContained Release buildを実施、native GUI操作/WinUIAnalyzerは今回未実行（既存projectにanalyzer参照なし、新依存は追加しない）。具体的な最終テスト結果と失敗履歴は[最新handoff](codex-handoff.md)参照。

WD adapterは明示許可による導入・実CPU/API35checks確認済み（実タグ品質は未評価）。次は (1)WinUIの候補/根拠表示・修正承認/却下・draft保持とWindows実機確認、(2)候補を明示選択した検索、(3)代表素材の品質評価とOCR/複数ページ根拠への拡張。P0 baseline済み・改善累積1/2は維持する。

## WinUIレビュー接続（2026-10-16）

画像/CBZ/ZIPの詳細「AIタグ候補」から専用ダイアログを開く。最大10batchずつ履歴・30候補、元候補/修正確定タグ/状態、model版/前処理/根拠を表示。本文解析はなくCBZ/ZIPは先頭ページだけ。未接続は生成のみ禁止、保存済みの新しいpendingは承認可能。staleは操作禁止。既存の検索・scope・選択・詳細のdraftを維持する。

未保存編集がある場合は閲覧/生成/却下のみ許可し、承認は手動保存後に再度開く。承認要求後はitem再取得で詳細を同期し、失敗時は再確認まで当該itemの手動保存を禁止する。生成95秒deadline（transport100秒）・閉じるとserverへ取消を要求して終了待ち。通常検索用clientの40秒制限とは分ける。根拠画像は最大8MiB/16Mpixel、表示時に256pxへ縮小。

最新の全Python336 PASS・Core契約PASS・Release警告0/エラー0。`tools/test_tag_review_ui.py` は生成素材/一時DB/偽adapterだけで35 runtime checks PASS、PNG7枚を目視。通常幅の明暗・承認/却下・CBZ表紙は確認済みだが、開いたまま狭幅へ縮めると候補詳細が見えないvisual FAILがあり次の修正対象。上の「C#変更なし/GUI未変更」はbackend基盤導入時の履歴であり、現状はこの節と最新handoffを正とする。実WD GUI推論/実タグ品質/High Contrast/DPI拡大は今回未検証。

### 狭幅レイアウト修正と再検証

2026-10-16続行で、前節の狭幅visual FAILを解消。一覧/詳細は2列を維持し狭幅の一覧幅だけを縮める。詳細の行/列を移し替えて幅/高さ0を経由させない。未取得/staleの根拠画像は空枠を畳み、履歴変更時は詳細スクロールを先頭へ戻す。

`tag-review-resize-20261016-01` は59 native checks PASS・PNG15枚全目視PASS。通常→狭幅→通常、狭幅で開き直し、根拠/編集/承認ボタンが可視かつ非0bounds、狭幅修正承認のDB反映、明暗、既存取消/編集保持を確認。Release警告0/エラー0。実WD GUI推論/実タグ品質/High Contrast/DPI拡大は未検証。

### 未承認タグ候補の明示検索（2026-10-16 続行）

- **バックエンド (`app/tag_candidate_search.py`, `app/production_server.py`)**：`POST /api/library/tag-suggestions/search` を追加。通常の文字検索（`GET /api/items`）やAI検索に未承認候補を自動混入させず、明示的に選択したときだけ各作品の**最新batchの`pending`候補**を検索する。登録フォルダ選択（`root_ids` 1〜256件の和集合、空配列や未登録rootは400で拒否）、`kind`、`view`（`all`/`favorites`/`unreviewed`/`shelf`）、`shelf`、`model` フィルターに対応し、ページ内の最大60件について物理sourceの現在revisionと照合して `source_state`（`current` / `stale` / `unverified` / `unavailable`）を返す。推論・モデル起動は一切行わない。
- **Core / WinUI (`src/Aredoko.Core/SearchMethod.cs`, `Protocol.cs`, `TagReviewClient.cs`, `LibraryApi.cs`, `src/Aredoko.WinUI/MainPage.xaml`, `MainPage.xaml.cs`)**：検索方法コンボボックスに **「未承認タグ候補」 (`ModeTagCandidates`, index 4)** を追加。反射不要の `TagReviewProtocol.CandidateSearchRequest` / `ParseCandidateSearch` と `ProposalMatch` により、一覧/グリッドの各行に `ProposalEvidence<id>`（「未承認タグ候補: … / モデル: … · 根拠: 画像または本の先頭ページのみ · 元ファイル一致または変更あり（要再生成）」）を表示。
- **検証**：
  - 全Python **337 PASS / 173.064秒 / skip 0**（`test_tag_suggestions.py` **21 PASS**、`test_error_text_coverage.py` **2 PASS**）。
  - C# Core **305 PASS**、Windows x64 SelfContained Release **PASS（警告0・エラー0）**。
  - Windows native `python tools/test_tag_review_ui.py --candidate-search-only --output data/ai-ui/tag-candidate-search-20261016-02`：**24 checks PASS / PNG 4枚（Light/Dark・1200×820および700×620狭幅）全目視PASS / graceful close 2**。通常文字検索に未承認候補が出ないこと、「未承認タグ候補」モードに確定タグが出ないこと、モデル由来・本の先頭ページ根拠・stale表示、登録フォルダ絞り込み（`media-1`）、および全未承認候補を承認/却下した作品が未承認候補検索から消えて承認タグが通常文字検索で見つかることを確認。
