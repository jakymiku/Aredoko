# 本の内部ページを画像のままAI検索

2026-10-17の最初の縦切り。EmbeddingGemma 2へ本文ページ画像を直接渡し、作品単位の検索と一致ページへの読書を接続した。**OCRによる文字起こし、全文の厳密一致、複数ページの物語理解・自動タグ付けは行わない。** モデルは既存profileで交換可能。

## 操作

1. 設定 →「AI検索の準備」で、本の登録フォルダを含むAI対象範囲を保存する。
2. ライブラリのCBZ/ZIPまたはフォルダ本を右クリック → **「本のページをAI検索に追加…」**。
3. 開始ページとページ数を指定し「選んだページを追加」。**1要求1冊・最大16ページ**。別の範囲を追加すれば同じ本に蓄積でき、同版の準備済みページは再利用する。
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

## 実測と検証境界

- `tools/evaluate_page_images.py`は既存の[固定日本語ページ](ocr-evaluation.md)8枚を**画像のまま**使用。7冊に無地の表紙を付け、予告した8問＋診断用2問を実行。入力画像hash/日本語font receiptを照合し、質問・期待作品/ページ・条件を推論前に`frozen-protocol.json`へ保存した。新規P0 holdoutではなく、人工的に同一表紙にした内容索引の到達確認。OCRは起動しない。
- 実EG2/CUDAの一度の比較：表紙のみHit@1 **0.125**／MRR **0.4033**／Recall@5 **0.75**、内部ページ追加後はそれぞれ**1.0**、作品とページの同時Top1 **8/8**。意味検索であり、厳密な文字起こし・私物/代表素材の精度・漫画の人物関係理解を証明しない。
- 索引8ページの追加 **1.601秒**、vector本体**24,576 bytes**（768次元float32、DB/索引/metadataの容量は別）。cover初回準備13.627秒はモデルload等を含み、load済みpage追加と単純な速度比較をしない。診断の正解なし質問にも近い候補が返る（top0.598093/0.696851）。自動拒否の成功とは数えない。順位/重み/閾値調整なし、P0累積1/2は不変。
- report：`data/page-images/v1-20261017-01/report.json`。protocol SHA `f46195453026c2c1a3655e0e19d9b101f7eb904c95bcde6733571f946b4f7319`。生成本bytes/mtime不変、owned worker終了。
- native `page-images-20261017-02`：**37 checks PASS / Light・Darkの10 PNG全目視 / 正常終了2 / worker終了**。GUIから範囲追加→日本語「教室の机」→2/3へ読書、狭幅、編集中タグ保持、再起動後同版3ページ再利用、原本/設定不変を確認。初回01は狭幅で閉じた詳細paneを参照して停止しFAILEDのまま保持。テストの詳細を開く操作だけ修正して一度再実行。初回4 PNGも全目視。全体テストの最終数値は[最新handoff](codex-handoff.md)に記録する。
- WinUI設計/API確認・コードレビューを実施。WinUIAnalyzer未導入/未実行、High Contrast/Narrator/Native AOT/大量本・ページの性能/私物検索品質は未検証。新download・依存追加・私物scan・CI dispatchは0。

## 続き

まず索引済みページ数・未処理範囲・次の範囲への再開を本ごとに分かるようにし、複数本を明示選択した総ページ上限付きjobへ進める。現状は一度に1冊16ページの手動指定であり、1TB全体の一括内容索引は完成していない。多数ページの検索/物理版検査の費用と長い本の最大値の傾向を測定し、代表素材の内容検索漏れを記録する。OCR専用処理は直接索引済みの範囲でも漏れが多い場合に限って検討する。
