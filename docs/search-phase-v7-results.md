# P0 v7 実GPU baseline と有限な改善の結果（2026-10-15）

## 入力と条件

24素材/24query・2root、5条件×2範囲＝240結果行。凍結commit `9dd32b0`、入力SHA `8212da5d4c146c8ac1086e04c95a3514d3564a1171cb3f9fe66498389f7e499b`。旧v1/v2/v6は変更なし。 [事前仕様](search-phase-v7.md)・[固定入力](../tests/fixtures/search-phase-v7.json)。

EG2固定revision `914f7f89142e33e77833254d9c9b90c3cef7303b`/auto-bf16、combined mean-RRF。各queryのkindを指定し、all-roots（A+B）とroot-Aを各条件で同じ意味で適用。正解は範囲とsourceに射影し、対象外の正解・cover非対応・真正no-answerを区別する。literalは辞書なし、relatedは固定の架空alias辞書あり。他AI条件では辞書を保持するが、これだけでAIの辞書利用・固有名詞理解を証明しない。

## 主な結果（all-roots）

| 根拠 / 問数 | 条件 | Top1 | Recall@5 | MRR | Precision@5 |
| --- | --- | ---: | ---: | ---: | ---: |
| metadata / 8 | literal | 0.000 | 0.000 | 0.000 | 0.000 |
| metadata / 8 | related | 0.000 | 0.000 | 0.000 | 0.000 |
| metadata / 8 | text | 1.000 | 1.000 | 1.000 | 0.250 |
| metadata / 2 | cover | 0.000 | 1.000 | 0.375 | 0.250 |
| metadata / 8 | all | 0.875 | 1.000 | 0.938 | 0.250 |
| pixels / 6 | literal | 0.000 | 0.000 | 0.000 | 0.000 |
| pixels / 6 | related | 0.000 | 0.000 | 0.000 | 0.000 |
| pixels / 6 | text | 0.000 | 0.167 | 0.136 | 0.033 |
| pixels / 6 | cover | 1.000 | 1.000 | 1.000 | 0.200 |
| pixels / 6 | all | 0.000 | 0.667 | 0.302 | 0.133 |
| agreement / 2 | literal | 0.000 | 0.000 | 0.000 | 0.000 |
| agreement / 2 | related | 0.000 | 0.000 | 0.000 | 0.000 |
| agreement / 2 | text | 1.000 | 1.000 | 1.000 | 0.200 |
| agreement / 2 | cover | 1.000 | 1.000 | 1.000 | 0.200 |
| agreement / 2 | all | 1.000 | 1.000 | 1.000 | 0.200 |
| conflict-pixels / 2 | literal | 0.000 | 0.000 | 0.000 | 0.000 |
| conflict-pixels / 2 | related | 0.000 | 0.000 | 0.000 | 0.000 |
| conflict-pixels / 2 | text | 0.000 | 1.000 | 0.225 | 0.200 |
| conflict-pixels / 2 | cover | 1.000 | 1.000 | 1.000 | 0.200 |
| conflict-pixels / 2 | all | 1.000 | 1.000 | 1.000 | 0.200 |
| conflict-metadata / 2 | literal | 0.000 | 0.000 | 0.000 | 0.000 |
| conflict-metadata / 2 | related | 0.000 | 0.000 | 0.000 | 0.000 |
| conflict-metadata / 2 | text | 1.000 | 1.000 | 1.000 | 0.200 |
| conflict-metadata / 2 | cover | 0.000 | 0.000 | 0.095 | 0.000 |
| conflict-metadata / 2 | all | 0.000 | 1.000 | 0.225 | 0.200 |
| alias / 2 | literal | 0.000 | 0.000 | 0.000 | 0.000 |
| alias / 2 | related | 1.000 | 1.000 | 1.000 | 1.000 |
| alias / 2 | text | 1.000 | 1.000 | 1.000 | 0.250 |
| alias / 2 | cover | 0.500 | 1.000 | 0.667 | 0.250 |
| alias / 2 | all | 1.000 | 1.000 | 1.000 | 0.250 |

metadataのcoverは8問中、画像入力対象のbook2問だけが採点対象。WAVは無音・SVGは灰色・CBZは幾何図形なので、音声理解/本の本文理解ではない。Precision@5は返された最大5件に対する厳密qrelsの比率。各visual queryは正解1件のため、全5件を返す完全Top1でも0.2になる。これは一般的な関連性判定や正解確率ではない。

## 誤りの分析と今回見送る変更

- 視覚のみ6問：cover Top1 6/6、combined 0/6（Recall@5 4/6、MRR約0.302）。タグなしのtext順位と混合すると視覚の良い順位が下がる観測を、v1/v2とは別の新入力で確認した。
- metadata8問：text Top1 8/8、combined 7/8。例：「文化祭をきっかけに幼なじみと結ばれる高校の恋愛もの」の本はtext1位、combined2位。幾何図形のcoverは物語を描いていない。
- label/pixel矛盾の4問は、期待する根拠によって正解が変わる。視覚根拠2問はcover/combined Top1 2/2、登録タグ根拠2問はtext2/2・combined0/2。自動routing/重み変更の根拠として単一セットへ最適化しない。
- 本物のno-answer2問：literal/relatedは2/2空、text/combinedは0/2空。coverは画像query1問のみ有効で0/1空（audio側は候補pool自体が0）。AIは近い候補を返す現仕様。閾値をこの2問へ合わせて作らない。
- 架空alias2問はrelatedでTop1/Precision 2/2・1.0。辞書とqueryを同じ作者が作った機構controlであり、未知キャラクター理解ではない。

root-A限定を含む240行すべてでscope・modality逸脱0。root-Bだけに正解があるケースを、root-Aの失敗点へ加えていない。詳細240行はignored出力に保存し、私物/DB/生のprocess情報をGitへ載せない。

## 改善試行1（資源の無駄のみ）

cover検索でaudio/materialしか残らない場合にもquery推論をしていたため、shared cap/明示scope・kind・viewの後で現cover対応kind（image/book）へ限定し、空なら既存の空結果経路を使う。非画像へ紛れたcover vectorも候補にしない。重み/score/threshold/自動routing・combinedのaudio対象は変更なし。

確認入力は `cover-empty-v1.json`（5生成素材・6query）、事前凍結commit `c5ca371`、SHA `f7a734f3a720732dfa93e491c358d95f6157222395ce2780e728e6ab1b4aa78a`。実GPU before/after各1回で6件すべて結果ID/順序不変、query推論 **6→2**。空cover4件の検索時間中央値 **89.591ms→11.132ms**。残る2回は正常image coverとaudio combined control。source/vector不変、全owned worker終了。品質スコアの改善とは呼ばない。

## 実行証拠と限界

baseline `search-phase-v7-baseline-01`：runtime PASS、273入力/境界checks、document24/image16/query144、index40.889秒、peak allocated931.8MiB（driver全VRAMではない）。source bytes/mtime/hashとvector bytes、凍結入力不変、所有process-instance handle3件全終了。confirmation before/afterもruntime PASS・source/vector不変・所有worker終了。新依存/モデルDL・私物scan・GUI操作・CIなし。

検索時間の中央値（all-roots）：literal3.246ms、related3.490ms、text95.889ms、cover88.269ms、combined87.852ms。ローカル回帰テストと一部同時実行しておりhost負荷は隔離していない。単発診断であり性能保証・1TB/数万件の比較ではない。UI到達時間・操作回数、多DPI/実GPUのUI連携、実ライブラリ精度は未測定としてnull/課題を保持。

## P0の区切り

新baseline済み、改善試行累積 **1/2**、採用1件（query推論省略）、品質重み変更0件で今回のP0を閉じる。残り1枠を使うためだけの追加試行はしない。混合順位/no-answer/文字の日本語分割・UI到達手数はbacklog。新しいユーザー指示/実運用の失敗/新しい退行の根拠なしに同じP0を再開せず、P1既済を維持してP2の由来付き候補タグ/承認へ進む。

## 再現と回帰の記録

```powershell
# 既存の専用環境・重みが必要。必ず新しいignored出力へ。既知の課題だけでP0を再開しない。
python tools/evaluate_search_phase.py --output data/ai-ui/search-phase-new
python tools/check_cover_empty.py --output data/ai-ui/cover-empty-new
python -m unittest discover -s tests -p test_search_phase.py -v
python -m unittest discover -s tests -p test_empty_cover_search.py -v
```

新評価契約3 tests PASS、empty-cover境界2 tests PASS、既存AI検索13 tests PASS。試行前全Python304 PASS/166.427秒。試行後初回全306では、古いvisual/text独立性テストがaudio placeholderへcover vectorを手動投入していたため1error。PNG2件を明示生成する対応kindのfixtureへ直し、逆向きのtext/cover vectorと元の順位・source/不正modeの検証意図を維持した。非画像stray cover拒否は別の新テストで保持。最終全Python **306 PASS/158.807秒/skip0**。C#/XAML/GUI未変更につき今回Core/Release/nativeは再実行しておらず、前回OpenCodeの実機合格と区別する。
