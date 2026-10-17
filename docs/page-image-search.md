# 本の内部ページを画像のままAI検索

2026-10-17の最初の縦切り。EmbeddingGemma 2へ本文ページ画像を直接渡し、作品単位の検索と一致ページへの読書を接続した。**OCRによる文字起こし、全文の厳密一致、複数ページの物語理解・自動タグ付けは行わない。** モデルは既存profileで交換可能。

## 操作

1. 設定 →「AI検索の準備」で、本の登録フォルダを含むAI対象範囲を保存する。
2. ライブラリのCBZ/ZIPまたはフォルダ本を右クリック → **「本のページをAI検索に追加…」**。
3. **準備済みページ数と残り数**を確認し、開始ページとページ数を指定して「選んだページを追加」。**1要求1冊・最大16ページ**。画面を開くと次の未処理範囲が初期選択され、追加成功後はさらに次の範囲へ進む。「次の未準備範囲を選ぶ」でも選び直せる。この操作だけで索引を開始しない。手動指定と同版の再利用も維持する。
4. **「画像の見た目（AI）」**、または「両方で探す（AI）」で検索する。本を一つの結果として表示し、ページ画像が最良の根拠なら「内部ページの意味一致（nページ）」とモデル・類似度を表示する。
5. その本を開くと、一致した版のページから読書する。検索後に本が変わった場合は古いページ番号を使わず、通常の読書位置復元へ戻る。

通常の「AI検索の準備」の一括索引は引き続き名前/タグ・表紙・画像・動画代表frame・未承認タグ候補が対象。**内部ページは上記の明示操作をした範囲だけ**。起動・検索・通常の再索引・タグ生成をきっかけに全ページを自動処理しない。今回の画面は日常の検索方法を増やさず、既存メニューへ一操作だけ追加する。編集中のタグを保存/破棄しない。

## 保存と検索の契約

- `PageIndex`のopaque page ID、物理`source_revision`、自然順の0始まりpage番号を再利用。ページ入力は既存の検査済みread-only経路を使う。画像8MiB/16M画素、ZIP512MiB/中央directory4MiB/10000候補・圧縮比・リンク拒否等の既存上限を広げない。未対応/過大ページは今回の要求を失敗とし、以前の索引を保持する。
- profile別sidecarの`ai_page_vectors(item_id,source_revision,page_id,page,vector,contract)`へ正規化float32を保存。前処理contractは`book-page-image:v1`。元ファイル版とタグ/タイトルのmetadata版を分離し、手動タグ変更だけではページvectorを捨てない。モデルprofileが異なれば別DB。通常cover/text/video/proposal索引と混ぜない。
- 明示scope内・present・有効root・除外外の本のみ。推論中はcatalog lockを持たず、既存共有inference lockとworker/lazy load/解放を使う。保存直前にroot/scope/head/page IDs/物理版/取消を再確認して**選択範囲全体をtransactionで公開**。途中の失敗・取消では今回の未完了範囲を公開せず、前回の保存を保持する。再実行は完了済み要求のページを再利用する（未完了要求内の途中vectorの保存ではない）。
- 検索対象itemは既存のscope・root・kind・棚・favorite・上限10000件に従う。ページvectorを候補IDのbatch256単位で読み、各本の最大cosineを一つ保持する。原画像をdecodeせず、物理版をmetadataで確認してstale/unavailable/unverifiedはページ候補から除外する。表紙・動画と同じ画像モダリティ内の最大値として集約し、既存の順位統合・閾値・上位/参考候補の方針は変えない。
- 最良ページの`ai_page_match`にはpage ID/番号、元版・状態、model/model revision/profile/前処理/ページcosineを含む。「名前・タグの意味（AI）」にはページ画像を混ぜない。混合検索の作品scoreとページcosineは異なりうる。類似度は正解率ではない。
- CoreはJSON-DOMで根拠形式・長さ・範囲・有限scoreを検証。reader manifestと元版が完全一致するときだけジャンプし、既存見開きのanchor規則を適用する。元ファイルや利用者の整理情報を変更しない。
- 解除済みrootの完全削除では、既存の検査済みprofile DBとcatalog本体のページvectorも削除。他rootを保持し、複数DB間の一括atomicとは扱わない。

## API

既存loopback認証・Origin・JSON本文上限を維持。公開APIに任意path/model/画像bytesの注入口を追加しない。

- `POST /api/library/page-index {"item_id":id}`でmetadata snapshotを更新し、既存GETでID/版を取得。
- `POST /api/library/ai/pages`：`{"item_id":id,"page_ids":["64hex",...],"revision":"64hex","scope":{...}}`。全field必須、未知field/重複ID/空/17ページ以上/bool IDは拒否。scope不在を全体へ拡大しない。状態応答は既存`ai/status`形式に`job:"book-pages"`、32hex`job_id`、item/source revision、`reused`を付加。processed/indexed/totalの単位はページ。
- `GET /api/library/ai/status`で状態を取得。`complete`のindexedは公開済みページ数。cancelled/failedでは今回indexed=0、processedは推論/再利用を進めた数。
- `POST /api/library/ai/pages/cancel {"job_id":"32hex"}`は一致する実行中のjobだけ中断。別job/完了jobでは`cancel_requested:false`。既存の管理用`ai/cancel`も保持。GUIの閉じる操作は所有jobの中断を要求し、終了後に閉じる。
- `POST /api/library/ai/search`の`source:"cover"`/`"all"`結果に、最良の画像根拠が内部ページなら`ai_page_match`を付加。作品ごとに最大1結果・最大1ページ根拠。

## ページごとの準備状況と再開（2026-10-17）

- `POST /api/library/ai/pages/coverage`：`{"item_id":id,"revision":"64hex","scope":{...}}`の3field必須。未知field/bool ID/無効版/未知scopeは拒否。ページheadが指定版と異なれば409、有効scope内の本でなければ拒否。任意path/model/元画像を受け取らない。
- 応答はitem/source revision/source state/profile/model、画像対応`supported`・実行環境`available`、`page_count/indexed_pages/remaining_pages`、`indexed_ranges:[{"start":0,"count":16},...]`、`next_range`。範囲は0始まりで、GUIでは1始まりへ表示する。全準備済みならnext=null。次範囲は**最初の欠けから、次の準備済みページの直前まで、最大16ページ**。たとえば17〜32ページが準備済みなら、先に1〜16、次に33以降を選ぶ。
- 同版/同前処理・page IDと番号がsnapshotに一致し、現在profileの次元/有限値/単位normを満たすvectorだけ数える。破損cache/旧版/違うpage番号は未準備。sourceがstale/unavailable/unverifiedなら準備済み0・next=nullで警告する。画像非対応profileも準備済み0・next=null。実行環境が未導入でも保存済みの同profile索引の件数は読め、準備ボタンは無効になる。
- **読み取り専用CPU処理**。ページsnapshotを自動refreshせず、画像bytesの取得/decode・GPU/model load・索引・job変更をしない。他の推論が共有lockを使用中でもstatusを読める。source/root/exclusions/headを確認し、手動タグの変更だけではpage索引を無効化しない。
- 「準備済みの範囲」は折りたたみ表示。準備状況・進捗/結果・追加/中断操作はスクロール外に固定し、狭幅では範囲入力だけスクロールする。処理中の保存済み数と、今回処理中のページ数を区別する。完了後は状態を再取得し、取消/失敗時も以前の範囲を維持。manual再確認は全準備済みでも使える。別profile/版の応答・不整合な件数/範囲をCoreで拒否し、確認失敗時は操作を止めて開き直しを案内する。
- この件数は**明示した内部ページvectorだけ**を数える。通常の表紙vector/AI coverageの作品件数や、未承認タグvectorとは別。全ページを自動解析したという表示にはしない。

### 準備状況の規模計測

`tools/benchmark_page_coverage.py`で生成した1冊10000ページ・768次元の保存済みvectorを使い、一度ずつCPUで計測（モデル実行環境は無効、推論0回）。空索引 **0.058秒**、1ページおき5000ページ/5000範囲 **0.688秒**、全10000ページ準備済み **1.765秒**。最大応答144861 bytesでCoreの1MiB上限内。tracemallocを別途有効にした全件のPython peakは8437722 bytes（約8.0MiB、SQLite native/OS/GPUのメモリは含まない）。traceありの10.242秒を通常の応答時間へ混ぜない。vector DBは41926656 bytes。生成原本bytes/mtime不変。`data/page-coverage/scale-20261017-01/report.json`。

これは1冊の状態集計の計測で、10000冊の検索・全ライブラリjob性能や実素材精度ではない。多数ページでのCPU検査中はcatalog guardを持つため、複数本へ広げる前に集計/物理版検査/guard時間を測定して分割を検討する。人工的に埋めたvectorでありEmbeddingGemmaの推論速度/精度ではない。

### 準備状況のWindows確認

**全Python444件実行：441 PASS / 3 Windows platform SKIP（239.668秒）／Core424 PASS／Windows x64 SelfContained Release警告0・エラー0（10.78秒）**。新規Python8件とCore27checksで、飛び飛びの範囲/完成/破損/旧版/非対応profile/未導入runtime/取消/除外/原本変更/共有lock中のCPU読取・HTTP認証/厳密field・応答矛盾/byte上限を検証した。

coverage単独のnative **`page-coverage-20261017-03`：46 checks PASS / Light・Darkの8 PNG全目視PASS / 正常終了2**。生成35ページと模擬vectorだけを使用。17–32のみ準備済み→1–16を追加→33–35を選択→取消で32/35保持→再開して35/35→app再起動→manual再確認は再利用、という操作をGUIで確認。未保存タグ/原本bytes・mtime/設定保持、準備状況を開く/次範囲選択では推論0回。今回実モデルの品質を再測定したわけではない。

初回01はNumberBox本体のget-valueで「33」を得られずFAILED。画像/内部Editの値は正しく、テストを内部EditのUIA値検査へ修正（3 PNG全確認、FAILED/所有process cleanupを保持）。02は操作43checks成功/8 PNG確認だが、狭幅で進捗/結果がスクロール外へ隠れる点を発見した中間版。状態/結果/取消を固定する製品修正後、一度だけ03を実行して上記合格。初回＋修正再検証2回の上限内。WinUIAnalyzerは未導入/未実行、High Contrast/Narrator/Native AOT/今回の新規キーボード網羅は未検証。新download/依存/私物scan/CIなし。

### フォームの文字切れ・スクロールバー余白（同日、ユーザー追加指摘）

フォームの内側contentに共通`FormScrollGutter`（右24DIP）を設け、右端のoverlay scrollbarと入力/ボタンが重ならないようにした。詳細・フォルダ設定・AI設定/root選択・関連語・タグ候補・検索結果の説明へ適用。画像/読書canvasのベゼルを増やす全体style変更ではない。ページ入力は開始/枚数を横並びにし、次の未準備範囲ボタンを状態/追加/中断と同じ固定領域へ移した。ダイアログ幅を現在のwindowに合わせて固定し、長い取消結果による急な幅変更/途中frameでの文字切れも抑えた。

`python tools/test_tag_review_ui.py --page-coverage-only --check-scroll-gutters --output data/ai-ui/<new-run>`：**`page-scroll-20261017-03`は76 checks PASS / Light・Darkの16 PNG全目視PASS / 正常終了2**。範囲追加/取消/再開/再起動/未保存タグ保持に加え、狭幅でpage入力・次範囲ボタン、詳細/AI設定/関連語/タグ候補の操作右端とviewport右端の20px以上の間隔をUIAで確認。元生成素材bytes/mtimeとAI設定は不変。実モデル/WD/OCRは使わない。フォルダ編集と説明flyoutは共通余白の適用をsource reviewしたが、このbatchで開く操作は再検証していない。

ユーザー追加指摘に対する初回01はAI設定dialogのasync待機不足でFAILED（7 PNG全確認、所有app強制cleanupを記録）。02はAI設定を閉じた再読込で選択が消えた後にテストが無効な「詳細」を開こうとしてFAILED（9 PNG全確認、正常終了1）。dialog待機と明示再選択をテストへ追加し、02の取消shotに見られたwidth変更中のframeは製品の幅固定とshot前compositor待機で解消。追加指摘の検証は初回＋修正再実行2回で終了し、旧FAILEDを成功へ変更しない。余白修正後のReleaseは警告0/エラー0（10.18秒、`data/page-scroll-release-20261017.log`）。Python/CoreはこのUI変更では未変更で、上の全体結果を使用する。

### 詳細パネル端の短い線（青い矢印の追加指摘）

矢印の短い縦線はスクロールバーではなく、背後の検索ボタン右端がoverlay pane境界から見える描画不具合だった。右側の長い線は実際の縦scrollbar。`LibraryLayout.Clip`で、狭幅の詳細overlayが開いているときだけ背後のcontentをpaneの手前までclipし、pane開閉・window/layout resizeで更新する。閉じたとき/広幅inlineではclipを解除する。SplitView/control templateや検索機能を作り直さず、閲覧canvasに余白を加えない。APIはrestored WinUI projectの`UIElement.Clip`/`RectangleGeometry.Rect`/`SplitView.PaneOpened/PaneClosed`と照合した。

`python tools/test_tag_review_ui.py --pane-boundary-only --output data/ai-ui/<new-run>`：**`pane-boundary-20261017-02`は39 checks PASS / Light・Darkの8 PNG全目視PASS / app正常終了2**。700/820pxのoverlayでは背後の検索ボタンがUIAでもoffscreen、閉じた後/1200pxのinlineでは表示/検索が復帰。resize中の未保存タグとcatalogの手動metadata保持、生成原本bytes/mtime/AI設定不変、推論0回を確認。初回01はdisplay mode変更で既存SplitViewがpaneを閉じた後に、テストが存在しないclose buttonを呼んでFAILED（2 PNG全確認・所有app強制cleanup）。paneが閉じた場合に既存「詳細」を明示的に開く手順へテストを合わせ、一度だけ再実行した。clip修正時点のRelease警告0/エラー0 **11.12秒**（`data/pane-boundary-release-20261017.log`）。先の76checks/16PNGはこの最後のclip修正前の検証で、最後の変更はこの対象batchで検証した。全過去GUIを再実行したという主張にはしない。

### 一覧と詳細の間の余白（同日、横並び画面の追加指摘）

検索ボタン/フォルダ管理/検索範囲欄が右詳細へ密着するため、inlineで詳細が開いている間だけ一覧の右に**16DIP**の余白を確保する。閉じた後とoverlay表示では解除し、一覧の幅を戻す。共通のpane開閉/layout resize処理で更新し、項目や機能を隠して空ける処理ではない。

最終native **`inline-gap-20261017-01`：43 checks PASS / Light・Dark8 PNG全目視PASS / 正常終了2、初回成功・修正再実行0**。横並びの検索/フォルダ管理と詳細入力間隔、700/820pxのoverlay非漏出、1200pxへの復帰、閉じた後の検索、未保存タグ/手動metadata/原本bytes・mtime/設定保持を確認。モデル推論なし。最終Release **警告0/エラー0、9.76秒**（`data/inline-gap-release-20261017.log`）。39checksの直前の境界batchに加え、最後の余白変更をこの対象batchで確認した。

## 実測と検証境界

- `tools/evaluate_page_images.py`は既存の[固定日本語ページ](ocr-evaluation.md)8枚を**画像のまま**使用。7冊に無地の表紙を付け、予告した8問＋診断用2問を実行。入力画像hash/日本語font receiptを照合し、質問・期待作品/ページ・条件を推論前に`frozen-protocol.json`へ保存した。新規P0 holdoutではなく、人工的に同一表紙にした内容索引の到達確認。OCRは起動しない。
- 実EG2/CUDAの一度の比較：表紙のみHit@1 **0.125**／MRR **0.4033**／Recall@5 **0.75**、内部ページ追加後はそれぞれ**1.0**、作品とページの同時Top1 **8/8**。意味検索であり、厳密な文字起こし・私物/代表素材の精度・漫画の人物関係理解を証明しない。
- 索引8ページの追加 **1.601秒**、vector本体**24,576 bytes**（768次元float32、DB/索引/metadataの容量は別）。cover初回準備13.627秒はモデルload等を含み、load済みpage追加と単純な速度比較をしない。診断の正解なし質問にも近い候補が返る（top0.598093/0.696851）。自動拒否の成功とは数えない。順位/重み/閾値調整なし、P0累積1/2は不変。
- report：`data/page-images/v1-20261017-01/report.json`。protocol SHA `f46195453026c2c1a3655e0e19d9b101f7eb904c95bcde6733571f946b4f7319`。生成本bytes/mtime不変、owned worker終了。
- native `page-images-20261017-02`：**37 checks PASS / Light・Darkの10 PNG全目視 / 正常終了2 / worker終了**。GUIから範囲追加→日本語「教室の机」→2/3へ読書、狭幅、編集中タグ保持、再起動後同版3ページ再利用、原本/設定不変を確認。初回01は狭幅で閉じた詳細paneを参照して停止しFAILEDのまま保持。テストの詳細を開く操作だけ修正して一度再実行。初回4 PNGも全目視。全体テストの最終数値は[最新handoff](codex-handoff.md)に記録する。
- WinUI設計/API確認・コードレビューを実施。WinUIAnalyzer未導入/未実行、High Contrast/Narrator/Native AOT/大量本・ページの性能/私物検索品質は未検証。新download・依存追加・私物scan・CI dispatchは0。

## 続き

本ごとの準備済み数/範囲と次の欠けの選択に加え、[明示複数本ジョブ](page-batch-indexing.md)まで実装した。最大8冊・各本の次の欠けを16ページずつ・合計128ページ。最新ジョブは同範囲を再開できるが、1冊全体の自動分割や1TB一括索引は未完成。多数本の検索/状態確認の費用と、代表素材の内容検索漏れを測定する。OCR専用処理は直接索引済み範囲でも漏れが多い場合だけ検討する。

多数本のCPU検索費用は[固定測定と同値な計算省略](page-search-performance.md)を追加（生成1024冊/65536page、17.560→13.551秒、raw/merged/root限定一致）。約6秒の物理版/guard費用と実品質・全RAM・全冊応答の検証は残る。

[長い本の分割plan/start/resume API](page-chunked-indexing.md)を追加。1冊最大128ページ・保存単位16ページ・固定選択の明示再開までバックエンド実装済み。GUIへの接続は後続で、既存の単範囲/複数本操作は変更しない。
