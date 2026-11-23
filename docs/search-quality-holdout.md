# text/pixel根拠別の新規固定評価 holdout v2

2026-10-13。v1を見た後に別の架空30素材/日本語30問を作成し、GPU推論の観測前に入力・qrels・SHAと評価コードをcommitした。既存モデル/順位/GUIとv1は維持。今回は**runtime成功と品質結果を分ける診断**で、製品の品質gateは定義しない。外部コーパスからの無作為holdoutではなく、モデル訓練への混入や実私物の精度は検証できない。観測済みなので今後v2もdevelopment evidenceとして扱う。

## 実行前の固定と入力

- 凍結commit **82427c528fcc273edb601cd62f69fe3c3251ab5e**。manifest v2 SHA256 **021e0984797727c6a79c97fb588165ce49db7c4e12fcdb1f265e02a7793b08fa**。現在のfileと凍結Git blobが同じSHA、Git LF属性とtestで固定。qrels/queries/itemsを観測後に変更していない。
- 30実ファイル：PNG12/CBZ6/灰SVG8/無音WAV4。中立のh_p/h_b/h_m/h_a名。PNGとCBZ表紙は18種類のunique geometric pixelsで、v1にあった同じPNGの表紙再利用を避けた。全18coverを推論前に一覧で目視し、色/数/配置・誤タグ2枚を確認。
- metadata-only12、pixel-only6、両方一致4、誤タグでpixelを探す2、誤タグでlabelを探す2、filename対照2、no-answer2。kindあり/なし、literal/text/cover/allで220相関条件・160query推論。30の独立した入力文であり220独立問ではない。SVG/audioのcover比較は非対応で行わず、metadata groupのcoverは本4問だけ。
- 正解は固定primary grade2（v2では関連grade1を設けない）。eligibilityへ射影してHit1/Best-grade1/Recall5/MRR/nDCG5を集計。no-answerはaccuracy平均から除く。metadata/pixelsの根拠もcase/resultへ保持する。accuracy観測後の融合重み/閾値変更、自動query routingはしない。
- SVGの用途・音源の設定・本の物語はassigned metadataだけ。SVGは灰矩形、WAVは0.1秒無音、本は抽象図形1ページなので、音源内容/物語/実表紙の理解の証拠ではない。

## 結果

| 根拠/種類なし | literal | text | cover | combined |
|---|---:|---:|---:|---:|
| タグmetadataのみ12問（coverは本4問） | 0/12 | 12/12 | 0/4 | 10/12 |
| pixelのみ6問 | 0/6 | 0/6 | 6/6 | 0/6 |
| タグとpixel一致4問 | 0/4 | 4/4 | 4/4 | 4/4 |
| 誤タグ・pixel優先2問 | 0/2 | 0/2 | 2/2 | 1/2 |
| 誤タグ・タグ優先2問 | 0/2 | 2/2 | 0/2 | 0/2 |
| filename対照2問 | 2/2 | 2/2 | — | 2/2 |

上表は正解primaryがTop1にある問数。metadata/画像が一致した4問は各AI modeで4/4。根拠が一方にしかない例や意図的な誤タグでは、混合のTop1が下がる。これを全実メディアの一般的な失敗率とは扱わない。

| 種類なしgroup/mode | Recall5 | MRR | nDCG5 |
|---|---:|---:|---:|
| metadata/text | 1.000 | 1.000 | 1.000 |
| metadata/all | 1.000 | 0.892 | 0.918 |
| pixels/cover | 1.000 | 1.000 | 1.000 |
| pixels/all | 0.833 | 0.394 | 0.485 |
| conflict-metadata/all | 0.500 | 0.171 | 0.193 |

- kind指定ではmetadata text12/12、combined11/12（種類なし10/12）。「島で地図を頼りにお宝を探す話」は種類なしcombinedでh_b02が5位、book指定でも2位。コーヒーの本は種類なし2位→book指定1位。抽象表紙に物語の根拠がないことと、混合が別の順位を選ぶことを区別する。
- pixel-onlyはkind指定でもcover6/6、combined0/6、text0/6。combinedの正解順位は種類なしで2/5/6/2/2/2、kind指定は2/2/6/4/3/2。情報がないtext側でも全候補に順位が付くため、純粋なpixel検索と同じ意味にはならない。
- 誤タグの赤い丸h_p11/青い三角h_p12を見た目で探すとcover2/2・text0/2・combined1/2。誤タグの分類として探すとtext2/2・cover0/2・combined0/2。タグ優先の正解は種類なしcombinedで7位/5位、image指定5位/3位。mode切替は意図を表す操作として意味がある。
- filename対照はliteral/text/combined2/2。この2問だけでexact filename全般の精度は保証しない。
- 正解なし2問でもAIは最近傍を返す。種類なしtext/combined30件・cover18件、literal0件。textの先頭cosine約0.643/0.653、cover約0.504/0.548、RRF約0.016で尺度が異なる。confidence/存在保証や共通の除外閾値はない。この2問から閾値を作らない。

## 実行証拠・再実行

```powershell
python -m unittest discover -s tests -p test_search_holdout.py -v
python tools/evaluate_search_quality.py --suite holdout-v2 --output data/ai-ui/search-holdout-new
```

existing dedicated venv/weightsだけ。outputはfresh data/ai-uiのignored directory、任意の私物/manifest/modelパス引数なし、downloadなし。CLIの既定baseline-v1を維持。baselineの実GPUは今回は再実行せず、既存CPU5 testsはPASS / 0.187秒。

- `search-holdout-01` **runtime PASS / 258入力・境界検査 / 220結果行**。実CUDA document30/image18/query160、index **27.155秒**。mean-RRF、EG2 default/auto-bf16、peak allocated931.8MiB（driver全VRAM/ゲーム影響ではない）。source bytes/mtime/hash、frozen manifest、検索前後vector bytes不変、所有process-instance handles3件全終了。No tuning/no Laya/no GUI。
- 新規CPU契約 **5 tests PASS / 0.570秒**：v1とのquery/file不重複、固定SHA、tamper拒否、不正qrels拒否、根拠分類、実pixel、unique covers。全Python **155 tests PASS / 106.705秒**。CLI/syntax/diff検査PASS。
- 既存C# Core **29 checks PASS**。x64 SelfContained Release **PASS / 40.75秒 / errors0 / 既存IL2104 2warnings（抑制なし）**。GUI sourceは今回未変更・native操作は再実行なし。前回root-picker native51/6PNGとkeyboard partialは別の履歴。
- 1TB/大候補集合/本本文/実音声/OCR/private library/高DPI/HighContrast/AOT/配布は今回評価しない。snapshot間の統計的有意差も算出しない。

## 次の3手

1. 製品GUIにAPIのtext-onlyを明示選択できる検索方法を設け、混合/画像との違いを説明する。勝手な自動routingや既定の順位変更はしない。既存scope/coverage/未保存規約を維持してnative確認する。
2. v1/v2はdevelopmentとして、次の品質判断には新しい入力とより実質的なtext/cover根拠を固定する。幾何図形の結果だけでfusion重みを最適化しない。
3. Laya日本語quality gate再評価は独立した実験で行い既定無効を維持。reader/Komga/フォルダ本集約、高DPI/全面keyboardは別slice。

2026-10-13後続：[GUIの明示AI文章検索](search-methods.md)を追加。上記固定入力/SHA/観測値・製品ランキングは維持。GUI契約のCPU/native検証とこの実CUDA品質観測を分けて記録。
