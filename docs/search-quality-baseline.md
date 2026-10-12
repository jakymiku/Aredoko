# 架空日本語の検索品質ベースライン v1（2026-10-12）

今回追加した固定評価セットと実測結果。**実行・境界検査の成功と検索品質は別**で、製品の品質gateはまだ定義しない。モデルや順位、qrelsを測定後に調整していない。既存EmbeddingGemma 2 / auto-bf16、combinedはmean-rrf、text/coverは単一cosine。Layaは使わない。

## 再実行と入力

```powershell
python -m unittest discover -s tests -p test_search_quality.py -v
python tools/evaluate_search_quality.py --output data/ai-ui/search-quality-new
```

Windows、既存専用venvと重みが必要。outputは新規のdata/ai-ui配下だけ。既存結果を上書きせず、ダウンロード/依存追加/私物フォルダ引数なし。結果のmanifest.json/result.jsonはignored outputだけに保存し、ソース/DB/モデル/パス/process IDはコミットしない。

[固定manifest](../tests/fixtures/search-quality-v1.json)は実行前に凍結。SHA256 **94260e45459d539285d7cde257214cddc9c39263b454a15b8e3c3b1e2e15afa8**。26素材（PNG8/CBZ6/SVG8/WAV4）、20文（用途の言い換え12/見た目4/名前一致対照2/正解なし2）。種類あり/なし、literal/text/cover/allの対応する条件で**130結果行・90実query推論**。同じ文の条件違いは独立した130問ではない。

ファイル名はv01/b01/m01/a01等の中立ID。PNG/CBZは実際の単純な幾何図形。表紙14件を画像入力に使う。SVGは同じ灰色矩形で、タグが架空の用途設定を表す。WAVは実際の0.1秒無音で、音源内容の設定はタグだけ。テキスト入力は現行製品通り名前/相対パス/タグで、物語の本文、SVG内部、音声の理解ではない。タグ未設定の画像を含め、metadataの有無を区別する。

## 正解と集計

primary=2、関連候補=1、その他=0の固定graded qrels。検索結果に合わせて正解を書き換えない。種類/cover対応を満たす候補に正解を射影してから集計する。Hit@1は関連候補も正解、Best-grade@1は最大gradeの候補のみ。Recall@5は正解候補のうち上位5件に入った割合、MRRは最初の関連候補の逆順位、nDCG@5はgain=2^grade-1、log2(rank+1)でdiscountし理想順位に正規化。confidenceや正解確率は出さない。

正解なし2文は平均の分母から除外し、返却候補・件数・scoreを別に残す。どのmodeでも空のqrelsを0点にするような集計はしない。filename-controlもsemanticとは別集計。各集計のscored_casesとfilter/sourceを記録する。

## 今回の結果

| 用途の言い換え12問 | 関連Top1 | primary Top1 | Recall@5 | MRR | nDCG@5 |
| --- | --- | --- | --- | --- | --- |
| 文字列一致・種類なし | 0/12 | 0/12 | 0.000 | 0.000 | 0.000 |
| AI text・種類なし | 12/12 | 11/12 | 1.000 | 1.000 | 0.983 |
| AI combined・種類なし | 10/12 | 10/12 | 0.972 | 0.917 | 0.921 |
| AI text・種類あり | 12/12 | 12/12 | 1.000 | 1.000 | 1.000 |
| AI combined・種類あり | 12/12 | 12/12 | 1.000 | 1.000 | 1.000 |

「ランジェリーを作るときのデザインのたたき台」は指定あり/なしtext/combinedでm01が1位。「敷き詰めてもつなぎ目が目立たない植物の柄」もm03が1位。assigned metadataからの意味検索が、この小さいセットでは文字列一致より用途の言い換えを拾った。

種類未指定combinedでは「事件の真相を追う都会の夜の話」が本b03の前に音源a01、「家でさっと作れる朝ごはんの手順」が料理本b04の前に服飾本b06を出し、期待primaryが2位になった。textは関連候補がすべてTop1だがprimaryは11/12。単純図形の表紙は物語の説明を描いていないため、これは今回の入力で混合順位がずれる観測であり、実同人誌すべてでtextが優れるという結論ではない。

| 見た目4問・画像種類を指定 | 関連/primary Top1 | Recall@5 | MRR | nDCG@5 |
| --- | --- | --- | --- | --- |
| 文字列一致 | 0/4 | 0.000 | 0.000 | 0.000 |
| AI text | 2/4 | 0.500 | 0.571 | 0.500 |
| AI cover | 4/4 | 1.000 | 1.000 | 1.000 |
| AI combined | 2/4 | 1.000 | 0.633 | 0.722 |

「白い背景に赤い丸」「青い正方形」「緑の三角」「黄色い三角」はcoverで画像種類指定時すべて1位。画像textには色/形のmetadataがないのでtext順位を視覚理解と扱わない。種類なしcoverも関連Top1は4/4だがprimary Top1は0/4：同一PNGをCBZ表紙にも使っており、同点をitem IDで安定化すると関連の本が先に出る。この人工的な同一図形のgrade差は失敗率と混同しない。

名前一致対照は文字列一致2/2、AI text/combinedは1/2がTop1。既知ファイル名の厳密検索には文字検索の意味がある。正解なし2問でもAIは近い順の候補を返す（種類なしtext/combinedは26件、coverは14件）；関連候補が存在すると保証する機能は未実装。scoreの尺度がmodeで違うため、この2問から共通閾値を作らない。

## 実行証拠と限界

実GPU `search-quality-01`: runtime_pass=true、164境界/入力検査、索引19.802秒、document26/image14/query90。保持した所有process-instance handle3件は全終了。source byte/mtime/hash、検索前後vector bytes、manifest bytesは不変。PyTorch peak allocated 931.8MiBはdriver全VRAMでも1TB性能でもない。26件・この1回の観測で、数万件の難しい候補集合に一般化しない。

新規metrics/fixture契約5tests PASS / 0.161秒。全Python **147tests PASS / 86.923秒**。構文/CLI help/diff checkもPASS。私物・別checkpoint・GUI/C#/Releaseを今回は変更/再実行していない（前回WinUI/CUDA133checksとReleaseは別の証拠）。高DPI/HighContrast・reader/Komga・Laya gateは今回未評価。

visual qrelsのprimary PNG4枚を目視し、色/形/白背景がqueryの定義と合うことを確認。PNG8/CBZ6すべての美観や実表紙の品質を目視評価したとは扱わない。

次は入力として不足している情報と混合順位の観測を分けて評価する。ここで見た20文は今後development probesとして扱い、新しい改善候補を判定する際は別に凍結したholdoutと、text/coverのどちらに根拠があるかを記録する。種類選択や既存画像・表紙モードは手動で使えるが、自動mode/routingはこの結果だけで有効化しない。
