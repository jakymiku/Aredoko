# 日本語OCRの固定評価（v1）

> **2026-10-17 方針更新**：OCR実装はユーザーの指示で保留。EmbeddingGemma 2の直接画像/本文ページ索引でも内容が見つからないケースが多く確認された場合に再検討する。本評価素材と採点器は将来の比較用として保持するが、次の既定開発タスクにはしない。Windows内蔵OCRの試作は製品へ接続していない。


実OCRを接続する前に、認識誤りと「本文から目的の作品へ到達できるか」を別々に採点する土台。**OCRアダプタはまだ未接続**。正解コピー/空出力は採点器の検算であり、OCR精度・実ライブラリ品質・AIランキング改善の実測ではない。P0の改善試行数は消費しない。

## 固定する入力

正本は [ocr-eval-v1.json](../tests/fixtures/ocr-eval-v1.json)。合成日本語8ページ/7作品、検索10問（正解あり7、正解なし3）。横書き、簡易の縦書き（右列から読む）、全角/半角・英字、小さな薄い文字、空白ページを含む。漫画の複雑なレイアウトや手書き・ルビ・実作品の代表性はまだない。作者名・タグ・正解IDを画像へ埋め込まない。

同じ作品の別ページに「教室」「約束」が分かれている負例を含み、ページをまたいで語を合算した偽一致を検出する。空白ページの抽出済み空文字と、未処理/出力欠損も区別する。

- 正解/クエリ/レイアウトを含むcanonical JSONのSHA-256：`3e731b6bf17d1710b680a4c1b5b85c0c9e7997c5c6c63fc5551c23ee7f1814bd`。
- 生成時のreceiptへ、使用した既存フォント名・font SHA・各PNG SHAを保存する。OSフォントが違う結果を同じピクセルの再測定として扱わない。
- モデルを評価してから期待値や正解を都合よく書き換えない。追加評価は別版/別SHAで先に固定する。

## 生成と採点

既存Pillowとインストール済み日本語フォントのみを使用。自動ダウンロードやフォント置換はしない。出力ディレクトリ/レポートは新規作成のみで、既存ファイルを上書きしない。

```powershell
python tools/create_ocr_fixture.py --output data/ocr-eval/my-run
python tools/evaluate_ocr.py --predictions data/ocr-eval/my-run/perfect-control.json --output data/ocr-eval/my-run/perfect-report.json
python tools/evaluate_ocr.py --predictions data/ocr-eval/my-run/empty-control.json --output data/ocr-eval/my-run/empty-report.json
```

既定fontは既存の`meiryo.ttc`。存在しない環境では明示したローカルfontを`--font`で指定する（取得・インストールは別許可）。生成は8枚の1000×700画像で、すべて目視して欠け・レイアウトを確認する。生成物は`data/`内に置き、Gitへ入れない。

実アダプタの出力は次の形式で保存し、同じ採点コマンドへ渡す。任意command/pathを実行する口はない。producerの申告は記録するが、採点ツール単独では実際の推論実行やモデル由来を証明できない。アダプタ実行ログ・所要時間・言語・資源解放と一緒に報告する。

```json
{
  "version": 1,
  "fixture_sha256": "3e731b6bf17d1710b680a4c1b5b85c0c9e7997c5c6c63fc5551c23ee7f1814bd",
  "producer": {
    "adapter": "adapter-id", "version": "1", "model": "model-id",
    "model_revision": "fixed-revision", "preprocessing": "fixed-preprocessing"
  },
  "pages": [{"page_id": "page-01", "text": "抽出した本文"}]
}
```

出力欠損ページはmissingとして報告し、非空の正解に対しては空出力相当の誤りとして採点する。ページIDの重複/不明、fixture SHA不一致、producerの余分な項目、不正Unicode/制御文字、過大JSON/本文を拒否する。上限はJSON512KiB、32ページ、本文2048文字/ページ、64検索問。製品の本文上限とは別の**小規模評価用**の境界。

## 指標と限界

- **raw CER**：Unicode NFCと改行LFのみを正規化し、文字単位Levenshtein距離/正解文字数。挿入誤りにより1を超えることがあり、0〜1に丸めない。
- **normalized CER**：既存本文検索と同じNFKC/casefold/かな寄せに加え空白を除去。表記揺れ/改行由来の誤りと内容の誤りを分ける補助指標。実検索では空白を勝手に除去しないため、CERが低くても検索失敗はあり得る。
- **到達率**：同一ページ内で全語AND、作品単位に集約。Top1/Recall@5/Precision@5/MRRなどを計算する。オフラインの固定作品ID順による検索契約の評価で、製品内のDB ID順/AI融合順位の評価ではない。backendの`PageTextIndex.search`と全10問の一致集合を照合するテストがある。
- **正解なし/空白**：no-answer false-positive rate、空白ページの非空誤出力数、欠損ページ数を独立報告。正解が空のページのCERはnullとし、挿入文字数を誤り合計へ含める。

初回の検算結果：正解コピーはCER0/Recall@5=1、空出力はCER1/Recall@5=0。いずれも`measurement_kind: scoring-control; no OCR inference`。この数値をモデルの成績として引用しない。PNG8枚の目視は素材が正しく生成された確認であり、OCRが読めた証拠ではない。

## 次の接続

1. 許可範囲内のローカルOCRを選び、版固定・画像画素数/時間上限・取消・プロセス回収を持つ`PageTextIndex` adapterへ接続する。新モデル/依存取得は別途明示許可が必要。
2. このfixtureで実抽出し、producer・CER・検索到達率・誤例・処理時間を保存する。実行ログのない出力JSONだけで実OCR検証完了としない。
3. 生成データとは別に、ユーザーが明示選択した代表ページで品質を測る。表紙タグや本文の一語から複数ページの物語タグを断定しない。
