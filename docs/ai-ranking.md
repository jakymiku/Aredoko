# 名前・タグと表紙の混合順位（2026-10-12）

WinUIの「AI意味検索」は既定で `mean-rrf` を使う。「AI画像・表紙」、明示 `source=text/cover`、text-only profileは従来のcosine順位を使う。文字検索は独立している。Layaを起動・適用する必要はない。

## 計算と互換性

旧方式 `max` は各候補のtext/cover cosineの最大値で順位を付けていた。新方式は各modalityでcosine順位を作り、`1/(60 + rank)` を候補が持つmodality数で平均する。同値cosineには平均順位を使い、最後の同点だけitem IDで安定化する。単一modalityの候補を一律に半減せず、2本のvectorを持つことだけで加点しない。これは通常のsum RRFとは異なる、今回固定した平均方式である。

候補は現在の種類・棚・お気に入り・除外・source/metadata fingerprint条件で先に選ぶ。順位値はconfidenceではない。負のcosineを含む候補も保持し、隠す閾値は設けない。種類絞込みが変わると各modalityの順位も変わる。

モデルprofile、vector次元、SQLite schema、index namespaceは変更しない。索引の再作成なしで両方式を比較できる。モデル交換の分離は [model-profiles.md](model-profiles.md) のまま。

- 従来方式で起動: `pwsh -File tools/start-winui.ps1 -AIRanking max`。
- API起動: `python app/production_server.py --db <test-db> --ai-ranking max`。
- 検索単位の比較: `/api/library/ai/search` のJSONに `"ranking":"max"` または `"ranking":"mean-rrf"`。省略時は起動設定。既存token/Origin保護を使う。
- 応答の `ranking` は実際の方式、`score_kind` は `cosine` / `reciprocal-rank`。`semantic_score` の尺度は方式で異なり、confidenceとして扱わない。現GUIは数値を表示していない。

## 実GPU評価

`tools/evaluate_ranking.py --output <new-ignored-directory>` で架空23ファイルを生成し、固定EmbeddingGemma 2/CUDAを使って14文を種類指定あり／なしの28条件で比較した。従来6文・12条件はdevelopment、追加8文・16条件はvalidationとして区別し、新条件を見てkや重みを調整していない。

| 条件 | max top1 | mean-rrf top1 |
| --- | --- | --- |
| development 12 | 10 | 12 |
| validation 16 | 15 | 15 |
| 合計28 | 25 | 27 |

改善2条件はいずれも「赤い表紙の本」の種類指定あり／なしで、期待CBZが2位→1位。青い表紙の本は1位を維持。期待候補の順位が悪化する条件はなかった。全23件のsource hashは不変。

「下着のデザインテンプレート」は、架空PSDの名前・タグ入力から種類指定あり／なしで1位。実PSD画像・内部レイヤーを読んだ結果ではない。「ランジェリーの制作に使えるひな形」は、種類未指定で期待PSDが2位、関連する縫製PDFが1位で、両方式とも同じ。内容拒否処理は追加していないが、どんな表現でも正解するとは主張しない。

warm検索はこの小集合で約100–110ms、PyTorch peak allocated GPU 931.8MiB。これはdriver全使用量・1TB検索性能・私物精度を表さない。音声/動画/PDF/PSD/SVGは今回名前・タグのみ。OCR/本文・実音声動画・素材内部の理解は未実装。上限2,000件も継続。

## ネイティブGUI回帰

別の新規17件生成素材DBでWinUI Release/CUDAを操作し、新規索引、意味検索、タグ保存、dirty keep、文字検索復帰、赤表紙の既定混合順位、max override、青い画像のcover検索とタイル表示がPASS。4枚の実スクリーンショットを目視確認。保存タグを変えた1件は既存fingerprint仕様でAI結果から外れ、再索引まで古いvectorを出さない。私物フォルダは走査していない。

`tools/test-ai-ui-local.ps1 -AppPid <owned-pid> -FixtureDirectory <generated-root> -ArtifactDirectory <new-directory> -CheckFusion` が比較証拠を保存する。Sandboxが利用できずlocalで実行した。高DPI/Light/High Contrast/スクリーンリーダー/AOT/配布は今回未検証。検証用API/アプリ/workerは終了済み。
