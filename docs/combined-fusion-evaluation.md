# combined/RRF改善：固定評価 v8と実測結果

ユーザーの2026-10-17指示により、P0の残る1試行（累積2/2）を使う。仮説は **モードごとの候補スコア幅（max-min）でmean RRFを重み付けし、差が小さい文字順位が強い視覚根拠を薄める問題を抑える** の1件のみ。重み/閾値の探索はしない。各モード内の順位は平均同順位を維持し、差がない/比較不能なpoolは安全にfallbackする。採用判断はまだ行っていない。

新規固定[fixture](../tests/fixtures/combined-fusion-v8.json) SHA256 `1ad69335c9d1889efb017f48028f5eb860e980b7d1b4a9fa47e31d3c7c5556ef`。新24問（視覚8・metadata6・filename4・両方一致4・正解なし2）、既存14画像由来の6作品と新しい生成metadata/filename10素材。新しい質問・対照を使うが、画像の一部は既に観測したもの。同じ作者が仮説と質問を作成した開発寄りのholdoutであり、独立した実私物の精度とは呼ばない。新24問の予測を見る前にfixtureとこの計画をcommitする。

採用条件：新セットでbaselineが正しかったanswerableケースを悪化させないこと、metadata/filenameを含む全体Top1が低下しないこと、既存13問の直接視覚combinedが改善すること。正解なし2問は最近傍の観測のみでaccuracy平均へ入れず、拒否閾値を作らない。text/coverモードの順序・スコア、scope・candidate集合・元ファイル/vector不変を別途検査する。合格しなければ既定へ採用せず、理由と累積2/2を記録してこの改善枠を区切る。

既存17問のうち4問は未承認WDタグ意味検索であり、combined/coverの直接比較対象13問へ混ぜない。WDは今回変更せず、従来の総合17問の集計と直接視覚13問を区別して報告する。専用OCR・自動query routing・新モデル/依存取得・私物走査・CIは実施しない。

診断では既存の完全同点は既に平均順位だった。実評価と同じPython3.11で、失敗例の文字スコア幅約0.037..0.074に対し視覚側約0.188..0.336を確認。最初のsystem Python3.14のコピー診断はWindows物理stat token差により本文版がstaleとなったため、性能/精度のbaselineに使わない。保存queryを3.11でCPU再生して本文版current・元の順位を確認。鮮度判定を迂回しない。このホスト差は別の移行課題として記録する。

## 実測・採用結果（2026-10-17）

固定commit **`9855263e39bb4c81d7e65008c1d85f878c0e2ace`** の後、ランキング変更前に既存offline CUDA EmbeddingGemma 2 768Dでスコアを一度取得。**同じスコアをCPUで再生して旧mean-RRFと候補1案だけを比較**した。新24問は46条件（正解あり22×全root/対象root + 正解なし2）。13問の既存直接視覚developmentは元のcatalog/vector DBをread-only backupしたコピーを使用し、Python3.11で全bookの版がcurrent、変更前の全順位が既存reportと一致することを確認した。

採用条件は合格。**P0改善試行は累積2/2としてこの枠を終了**。追加の重み/閾値探索はせず、残る誤候補と新しい独立素材での実運用評価はbacklogへ。以前の「採用判断はまだ」の段落は観測前計画の記録。

| 新しい固定質問・全root | 問数 | 旧Top1 | 新Top1 | 旧MRR | 新MRR |
| --- | ---: | ---: | ---: | ---: | ---: |
| visual | 8 | 0.625000 | 0.750000 | 0.709524 | 0.837500 |
| metadata | 6 | 0.833333 | 1.000000 | 0.916667 | 1.000000 |
| filename | 4 | 0.500000 | 1.000000 | 0.750000 | 1.000000 |
| agreement | 4 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| overall | 22 | 0.727273 | 0.909091 | 0.826190 | 0.940909 |

- 正解あり全22問：**16/22（72.73%）→20/22（90.91%）**、Recall@3 **20/22→21/22**、MRR **0.826190→0.940909**。正解なし2問を分母に入れない。
- root限定22条件は **22/22→22/22**。全46条件で旧Top1正解からの悪化0。text/cover明示モードはraw scoreと順位の全一致、candidate集合・scope・元ZIP/元DB/report・生成原本bytes/mtime・索引vector DB hash不変を確認。scope条件を独立した追加の質問数として数えない。
- 既存直接視覚development13問はcombined **7/13（53.85%）→13/13（100%）**、Recall@3 **12/13→13/13**、MRR **0.750000→1.000000**。既存17問総合には別モードのWD4問（3/4正解）が混ざっていたため、RRF部分13問を分離した。今回WDの再推論/意味検索はしておらず、新たな17問全体実測とは呼ばない。WD旧3/4を単純併記した換算なら総合10/17→16/17だが、これは新規全17問runではない。
- 残る新問の失敗：`r8_visual_04`（魔法使いの言い換え）はbookBが7位→5位で、text-onlyの雨音素材が1位。`r8_visual_07`（文化祭の献立）はbookBが5位→2位で、献立テンプレートが1位。metadataと視覚の意図の競合・queryの多義性は残る。観測後に正解を書き換えたり、これだけへ重みを追加調整しない。
- 正解なし2問にも近い候補を返す。今回の改善は正解不在の判定/自動拒否ではなく、確率の校正でもない。明示text/coverの使い分けと既存の結果グループ/文字一致フィルターを保持する。

## 実装契約

既存 `mean-rrf` の各modalityのrankはそのまま（同cosineは平均順位）。候補全体で各modalityのcosine幅 `span=max-min` を計算し、重みを `span / max_span` とする。候補のRRF寄与 `weight / (60+rank)` を、**その候補にあるmodalityの重み合計だけ**で平均する。モデル固有の閾値・検索語判定・固定の視覚優先率は追加しない。

- 有限極値のoverflow防止のため実装は `max/2-min/2`（全mode共通係数が相殺）を使う。スコア幅は信頼確率ではない。
- 単一mode、全mode同点、比較候補が1件しかないmodeがある場合は旧等重みRRFへfallback。2mode以上が比較可能で、一方の幅が厳密に0ならそのmodeの重みを0にする。差が小さいという理由だけでゼロにするepsilon/閾値はない。
- 存在するmodeの重みだけで正規化し、欠けた表紙を一律に半減しない。定数modeしかない候補はscore0だが**結果集合から削除しない**。負のcosineも許可。最後の同scoreはitem IDで安定化。
- `max`、明示text/coverのcosine、profile/768D/vector namespace/DB schema/再索引は変更なし。global rankで融合し、SQL batchやscope境界を越えて混ぜない。`ranking='mean-rrf'` / `score_kind='reciprocal-rank'` のAPI契約は維持する。スコア値/混合順位は意図的に変わるため旧threshold/品質観測と混同しない。
- GUI/自動routing/WD/専用OCRは変更なし。以前の10.80秒ページ検索はcover/max条件の既存測定で、今回の混合変更から新しいページ検索速度を主張しない。

## 証拠・再現・制限

`tools/evaluate_combined_fusion.py prepare --output data/combined-fusion/<fresh-run>` は評価前計画を照合し、固定の許可済み2 ZIPと旧隔離評価DBだけを使う。**元実評価と同じ専用Python3.11で実行する**。既存model/venvのみ、ダウンロードなし、生成media/DBは専用outputのみ。原本の物理版がstaleなら拒否し、検査を迂回しない。元DB/reportは書き換えずread-only backupでコピーする。

旧コードでprepare/`compare --label baseline`を保存し、新コードで同じcacheへ `compare --label candidate`、最終source SHA付き `compare --label validated`。各labelの上書きを拒否。compare時のモデル呼出0。同じraw scoresを使い、GPUの揺れで候補間の評価条件を変えない。データ/DB/cache/logはignoredでGitHubへ送らない。

今回output `data/combined-fusion/v8-20261017-01/`、最終source SHA256 `4edb898f331ced4264c045785d2c8c6e5d69c73d1c94097c7c8e144f355fc23d`、新fixture SHA256 `1ad69335c9d1889efb017f48028f5eb860e980b7d1b4a9fa47e31d3c7c5556ef`。ログ `data/combined-fusion-prepare-20261017.log` / `combined-fusion-baseline-20261017.log` / `combined-fusion-candidate-20261017.log` / `combined-fusion-validated-20261017.log`。元ファイル/モデル状態はfinallyで閉じた。GPU取得後の比較はCPUのみ。

新8 CPU回帰は文字/視覚の両方向、同点/定数/欠けmode/有限極値、固定SHA/既存質問との非重複、正解なしの分母、scope/種類/お気に入り/文字一致/ページ根拠/API形・text不変を検証。既存ranking/result groups/searchと合わせて **31件PASS /7.856秒**。全体/Core/Releaseは[最新handoff](codex-handoff.md)。WinUIは今回未変更・新native操作なし、既存取消1PNGの静止画レビューgateは未完のまま保持。

小集合・同じ作者の質問/qrels・再利用画像・単一GPU/モデルなので、実私物や多数の別モデルに対する一般精度ではない。スコア幅が誤根拠/外れ値で大きくなる場合や、text-only素材と画像の意図競合は解決しない。この限界を残して累積2/2を閉じ、さらなる調整は新しいユーザー指示/実運用の新根拠で独立に扱う。

最終検証：全Python493件（490 PASS /3 Windows platform SKIP、388.024秒）、Core449 PASS、Windows x64 Release0警告/0エラー（21.19秒）。同一score cacheをPython3.11/3.14で融合し、同じ採用条件/結果を確認。後者はGPU再取得や古い物理版を迂回した検索ではない。
