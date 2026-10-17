# 多数本のページ検索：CPU測定と同値な計算省略（2026-10-17）

1,024冊×64ページ＝65,536本の768次元vectorで、ページ検索は **17.560037秒→13.551148秒**（今回の単発測定で22.83%短縮）。保存float32の検査と正規化で重複していたfinite確認・二乗和だけを省いた。**sum / sqrt / divisionの順序・閾値・順位・同点処理・一致ページ・根拠・scope・物理版確認は変更していない**。まだ13秒以上かかるため、大規模検索の完成/速度保証とはしない。

## 固定条件と再現

- Windows / Core i7-13700K / Python 3.14.4。CPUのみ、モデル推論0、GPU不使用。既存profileの契約（768次元）を利用するだけで、EmbeddingGemma 2やWD/OCRのloadはしない。
- 測定前にprotocolを固定。SHA256 `caa35b6abc2e3e680b1dc3282dfad7b92c7623743e7018e43da6ab381afae311`。生成した小さなCBZ 1,024冊、各64ページ、2 rootに半分ずつ。元ファイルは生成物のみ。128種類のseed固定dense normalized float32 vectorを繰り返し、固定dense float64 queryを直接渡す。実画像の意味/検索精度を測るデータではない。
- 同一fixture/DBで変更前と変更後を比較。各64/256/1024冊を昇順に**各1回**、通常のページrank（SQL読取/復号/内積/作品集約/物理版確認）を計時。通常modality mergerは別途結果一致を検査するが計時区間外。自然語query推論、HTTP、UI、index作成は計時対象外。
- OS/SQLite cache・他プロセス・cold/warm差・試行順の影響を分離していない。統計的な速度保証や他機種の比較値には使わない。tracemallocは通常計時の後の独立pass（trace時間67.650950→64.019513秒、これは速度比較用ではない）。変更後traceの末尾で全体テストを開始したため、その時間も直接比較しない。
- vector DB `274,837,504` bytes（262.11MiB）。原本bytes/mtime_ns/SHA256とvector DBのSHA256を前後で照合し不変。catalogは生成snapshotと読取stateを含む専用DB、実ライブラリを走査しない。生成物/DB/logはgitignoreのdata内に保持、コミットしない。

```powershell
python tools/benchmark_page_search.py prepare --output data/page-search-scale/<fresh-run>
python tools/benchmark_page_search.py measure --output data/page-search-scale/<fresh-run> --label baseline
# 比較対象のコードへ変更後、同じfixtureを使う。prepareや既存結果の上書きはしない。
python tools/benchmark_page_search.py measure --output data/page-search-scale/<fresh-run> --label optimized
python tools/benchmark_page_search.py compare --output data/page-search-scale/<fresh-run> --before baseline --after optimized
```

変更前は`9e69da83a610f9bc13166443a4eb12786239bf4c`のdecoder。今回fixtureは`data/page-search-scale/v1-20261017-01/`。prepareは新規dir必須・最大1024冊/64ページ、measureは同label上書き拒否。再生成時はopaque page ID/revisionが変わるため、公開digestを別fixtureの正解値として比較しない。protocol/receipt/raw JSONを残し、同一fixture内で比較する。baseline/optimized JSONに測定開始時のHEADと`page_semantics.py` SHA256も記録（同じ開始HEADでも作業差分はsource hashで識別）。

## 実測（traceなし、秒）

| 冊数 | ページvector数 | 変更前 | 変更後 | 今回の短縮率 |
| ---: | ---: | ---: | ---: | ---: |
| 64 | 4,096 | 0.919427 | 0.684381 | 25.56% |
| 256 | 16,384 | 3.938155 | 3.222464 | 18.17% |
| 1,024 | 65,536 | 17.560037 | 13.551148 | 22.83% |

catalog guardは1冊ずつ取得。1,024冊時の合計保持 **6.333872→6.158373秒**、単一保持の最大 **0.012877→0.013034秒**。これはbenchmark threadの実測値で、UI待ち時間の上限ではない。今回物理版確認やguardの構造は変更していない。今後の重要な費用として残る。8冊のcoverage合計は **0.248460→0.188721秒**（各64ページ、CPU検査のみ）。1冊10000ページや全冊coverageの値へ外挿しない。

Python割当peakはfull rankの別tracemalloc passで **938,771→938,747 bytes**（約0.90MiB、ほぼ不変）。SQLite native memory、OS page cache、Python/アプリ全体RSS、RAM/VRAMは含まない。約262MiB DBを0.90MiBの総RAMで扱えるという意味ではない。streaming処理は保持し、全vectorをPythonへ一括展開していない。

## 同値性と検証

- 64/256/1024冊の**raw float score.hex() + item/page/revision/model根拠**をhash比較し完全一致。通常の画像modality merger後の順位/score/根拠も完全一致。1,024冊のraw digest `cd3cc7170b5c11c80d4779272caf0cfebd478d0c7a063ebb6503b2f1f229ad29`、merged digest `03e3cca9eece08f96f8d7bf122e97d9c93f9b1c6b34165b09bccaedeefab73e2`。
- root限定512冊のdigest `ea5c2f91e98ac5339ca11ad58879bf0ddeb358b452eb9cadcf393e770f590003`も一致。空集合0件。scope選択処理は別途0.021252→0.026729秒。実query生成や全API/並行登録の応答時間の測定ではない。
- 新規decoder回帰3件は、1/2/8/768次元のdense vectors、raw内積と全順位、unit tolerance境界、signed zero、NaN/Inf/破損/次元違い/zeroを旧decoderと比較。既存の検索/provenance/変更/scope/coverage/batch取消再開を合わせた対象32件PASS（24.445秒）。全体/Core/Releaseの最終結果は[最新handoff](codex-handoff.md)へ記載する。
- データ取得・依存追加・モデル起動・私物scan・CI dispatchなし。検索閾値/重み/ランキング方針は不変、P0品質改善試行は累積1/2のまま。このCPU fixtureを精度改善や実モデル速度の成功として数えない。
- GUI変更/起動なし。前回複数本jobの取消直後1 PNGは静止画レビュー未完のまま保持する（runtime20項目とUIA位置は確認済み）。同じnative testは初回+修正再実行2回済みのため追加自動試行しない。[既存batchの検証と制約](page-batch-indexing.md)を参照。

## 次に解決すること

1. 物理版確認/SQLite/catalog guardの約6秒と全体13秒の内訳を、版の安全性を弱めず改善する。cacheを追加する場合も、元ファイル変更/解除/scope/profileを即時無効化できることを先に検証する。warm単発値だけで完了判定しない。
2. 長い本は[既存の上限付きbatch](page-batch-indexing.md)を前提に、必要なbounded chunkと明示再開を小さく設計する。1冊16page atomic、総ページ/冊数制限、scope/profile/版/取消を維持。一般queue履歴・全冊自動chunk・1TB自動処理の完成とはしない。
3. 明示選択の代表素材で直接ページ検索/WD日英の漏れ・誤候補を記録する。直接索引でも漏れが多い場合だけOCRを検討。音声/音楽内容・複数ページ文脈タグ・数千pending性能は後続。
