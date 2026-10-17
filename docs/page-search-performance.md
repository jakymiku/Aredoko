# 多数本のページ検索：CPU測定・同値な計算省略・物理版確認/guard削減（2026-10-17）

1,024冊×64ページ＝65,536本の768次元vectorで、ページ検索は変更前 **17.560037秒 → 第1回（`optimized`）13.551148秒 → 今回（`guard-source-opt`）10.800774秒**（変更前比38.49%短縮、第1回比20.30%短縮）。さらに物理版確認とcatalog guardの合計保持時間は **6.333872秒 → 6.158373秒 → 3.345448秒**（第1回比45.68%短縮、256冊では1.608299秒→0.369745秒）へ削減した。

第1回は保存float32の検査と正規化で重複していたfinite確認・二乗和を省いた。今回は以下を追加した：
1. **中間list生成・generator frameの省略（`_score_packed`）**：`rank()`で768要素のPython `list`を65,536回生成せず、`map(math.isfinite, ...)` / `map(operator.mul, ...)` / `map(operator.truediv, ...)`で元の`sum → sqrt → division → dot product`と同じIEEE-754 float64演算を直接計算。64hex検証も正規表現を事前コンパイルし、256冊batch間で`ai.store.connect()`を1接続共有。
2. **候補本の位置SQL 256冊一括取得（catalog guardは1冊1回を維持、`_state_epoch`による即時無効化）**：候補1,024冊ごとに`catalog.connect()`して`item_locations` / `library_locations` / `library_roots`を1,024回個別SELECTしていた処理を、256冊chunk先頭のguard保持内で1回まとめて取得。**`catalog._guard`のouter_holdsは1冊1回（1,024回、最大単一保持0.011250秒）を維持**し、編集や他操作を256冊まとめてブロックしない。guard解放の合間に`set_excludes`、`unregister_root`、`purge_inactive_root`、`add_root`、`sync_index`などの変更が発生した場合は、`ProductionCatalog._state_epoch`により位置情報キャッシュと`root_cache`を即座に破棄・再取得する。
3. **`tag_source`時のZIP central directory一括読取と`ZipInfo`生成省略**：`_zip_directory_limit`で上限検査済みのcentral directory（最大4MiB）を1回の`file.read(cd_size)`で走査し、画像エントリの有無も同ループ内で判定。`operation == 'tag_source'`では`zipfile.ZipFile`による64個の`ZipInfo`オブジェクト生成を省略。また256冊batch内で登録rootの`Path.resolve(strict=True)`結果を共有しつつ、各構成要素の`stat(follow_symlinks=False)`（junction/symlink検査）と`source.resolve(strict=True).is_relative_to(resolved_root)`は従来通り毎回実行する。

**sum / sqrt / divisionの順序・閾値・順位・同点処理・一致ページ・根拠・scope・即時の物理版変更/除外検出は一切変更していない**。まだ1,024冊で10.8秒（うちguard/物理版確認約3.35秒、Pythonループでの65,536×768内積約7.45秒）かかるため、大規模検索の完成/速度保証とはしない。

## 固定条件と再現

- Windows / Core i7-13700K / Python 3.14.4。CPUのみ、モデル推論0、GPU不使用。既存profileの契約（768次元）を利用するだけで、EmbeddingGemma 2やWD/OCRのloadはしない。
- 測定前にprotocolを固定。SHA256 `caa35b6abc2e3e680b1dc3282dfad7b92c7623743e7018e43da6ab381afae311`。生成した小さなCBZ 1,024冊、各64ページ、2 rootに半分ずつ。元ファイルは生成物のみ。128種類のseed固定dense normalized float32 vectorを繰り返し、固定dense float64 queryを直接渡す。実画像の意味/検索精度を測るデータではない。
- 同一fixture/DBで変更前（`baseline`）、第1回（`optimized`）、今回（`guard-source-opt`）を比較。各64/256/1024冊を昇順に**各1回**、通常のページrank（SQL読取/復号/内積/作品集約/物理版確認）を計時。通常modality mergerは別途結果一致を検査するが計時区間外。自然語query推論、HTTP、UI、index作成は計時対象外。
- OS/SQLite cache・他プロセス・cold/warm差・試行順の影響を分離していない。統計的な速度保証や他機種の比較値には使わない。tracemallocは通常計時の後の独立pass（trace時間67.650950→64.019513→85.278788秒、これは速度比較用ではない）。
- vector DB `274,837,504` bytes（262.11MiB）。原本bytes/mtime_ns/SHA256とvector DBのSHA256を前後で照合し不変。catalogは生成snapshotと読取stateを含む専用DB、実ライブラリを走査しない。生成物/DB/logはgitignoreのdata内に保持、コミットしない。

```powershell
python tools/benchmark_page_search.py prepare --output data/page-search-scale/<fresh-run>
python tools/benchmark_page_search.py measure --output data/page-search-scale/<fresh-run> --label baseline
# 比較対象のコードへ変更後、同じfixtureを使う。prepareや既存結果の上書きはしない。
python tools/benchmark_page_search.py measure --output data/page-search-scale/<fresh-run> --label optimized
python tools/benchmark_page_search.py measure --output data/page-search-scale/<fresh-run> --label guard-source-opt
python tools/benchmark_page_search.py compare --output data/page-search-scale/<fresh-run> --before optimized --after guard-source-opt
python tools/benchmark_page_search.py compare --output data/page-search-scale/<fresh-run> --before baseline --after guard-source-opt
```

変更前は`9e69da83a610f9bc13166443a4eb12786239bf4c`のdecoder、第1回は`1978673ef1307f8dc889df5c3ebb34191bd96cdc`、今回は`7ffb5a26a00ab1343371d926835905a250e55740`（`_state_epoch`キャッシュ即時破棄追補は`1612513081292a75386ae4bf296c1811e5c6c9ea`、正常完了時アトミック増分・直接例外マッピング追補は`0807a239d3916538a5c94fb69539ba66c332758a`）。今回fixtureは`data/page-search-scale/v1-20261017-01/`。prepareは新規dir必須・最大1024冊/64ページ、measureは同label上書き拒否。再生成時はopaque page ID/revisionが変わるため、公開digestを別fixtureの正解値として比較しない。protocol/receipt/raw JSONを残し、同一fixture内で比較する。各JSONに測定開始時のHEADと`page_semantics.py` SHA256も記録（同じ開始HEADでも作業差分はsource hashで識別）。

## 実測（traceなし、秒）

| 冊数 | ページvector数 | 変更前 (`baseline`) | 第1回 (`optimized`) | 今回 (`guard-source-opt`) | 第1回比短縮率 | 変更前比短縮率 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 64 | 4,096 | 0.919427 | 0.684381 | **0.390823** | 42.89% | 57.49% |
| 256 | 16,384 | 3.938155 | 3.222464 | **1.445857** | 55.13% | 63.29% |
| 1,024 | 65,536 | 17.560037 | 13.551148 | **10.800774** | 20.30% | 38.49% |

| 冊数 | guard保持合計 (`baseline`) | guard保持合計 (`optimized`) | guard保持合計 (`guard-source-opt`) | 単一保持最大 (`guard-source-opt`) | `outer_holds` |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 64 | 0.339549 | 0.293672 | **0.110751** | 0.005925 | 64 |
| 256 | 1.432088 | 1.608299 | **0.369745** | 0.006066 | 256 |
| 1,024 | 6.333872 | 6.158373 | **3.345448** | 0.011250 | 1,024 |

catalog guardは引き続き1冊ずつ取得（`outer_holds == calls`）。1,024冊時の合計保持 **6.333872→6.158373→3.345448秒**、単一保持の最大 **0.012877→0.013034→0.011250秒**。これはbenchmark threadの実測値で、UI待ち時間の上限ではない。8冊のcoverage合計は **0.248460→0.188721→0.267902秒**（各64ページ、CPU検査のみ）。1冊10000ページや全冊coverageの値へ外挿しない。

Python割当peakはfull rankの別tracemalloc passで **938,771→938,747→1,026,619 bytes**（約0.98MiB、256冊分のlocation辞書キャッシュ約88KB増）。SQLite native memory、OS page cache、Python/アプリ全体RSS、RAM/VRAMは含まない。約262MiB DBを1MiBの総RAMで扱えるという意味ではない。streaming処理は保持し、全vectorをPythonへ一括展開していない。

## 同値性と検証

- 64/256/1024冊の**raw float score.hex() + item/page/revision/model根拠**をhash比較し、`baseline`・`optimized`・`guard-source-opt`の間で完全一致。通常の画像modality merger後の順位/score/根拠も完全一致。1,024冊のraw digest `cd3cc7170b5c11c80d4779272caf0cfebd478d0c7a063ebb6503b2f1f229ad29`、merged digest `03e3cca9eece08f96f8d7bf122e97d9c93f9b1c6b34165b09bccaedeefab73e2`。
- root限定512冊のdigest `ea5c2f91e98ac5339ca11ad58879bf0ddeb358b452eb9cadcf393e770f590003`も完全一致。空集合0件。scope選択処理は別途0.021252→0.026729→0.034979秒。実query生成や全API/並行登録の応答時間の測定ではない。
- `tests/test_page_vector_decode.py`で`unpack`と`_score_packed`の両方が1/2/8/768次元のdense vectors、raw内積の`float.hex()`と全順位、unit tolerance境界、signed zero、NaN/Inf/破損/次元違い/zeroで旧decoderと完全一致することを検証。さらに`tests/test_page_semantics.py`に、一括位置取得とZIP central directory直接確認の下でも未再スキャンのexclude変更・原本書き換えが即座に検索結果から除外されること、256冊chunk内のguard解放合間に動的除外（`InterleaveGuard`）や登録解除が発生しても`_state_epoch`により残余候補が即座に無効化・再取得されること、`tag_source`で`ZipInfo`を生成しないこと、`PageIndex.states`の一括状態判定、および`tests/test_production.py`で`_state_epoch`が正常変更時のみインクリメントされ失敗時には進まないことを検証する回帰テストを追加。全体459件（456 PASS / 3 Windows platform SKIP）、Core 449 PASS、x64 Release 0警告/0エラーの最終結果は[最新handoff](codex-handoff.md)へ記載する。
- データ取得・依存追加・モデル起動・私物scan・CI dispatchなし。検索閾値/重み/ランキング方針は不変、P0品質改善試行は累積1/2のまま。このCPU fixtureを精度改善や実モデル速度の成功として数えない。
- GUI変更/起動なし。前回複数本jobの取消直後1 PNGは静止画レビュー未完のまま保持する（runtime20項目とUIA位置は確認済み）。同じnative testは初回+修正再実行2回済みのため追加自動試行しない。[既存batchの検証と制約](page-batch-indexing.md)を参照。

## 次に解決すること

1. 残る約10.8秒（うち1,024冊×OSファイルopen/statの物理版確認約3.35秒、Pythonループでの65,536×768内積約7.45秒）を、版の安全性を弱めず改善する。上位候補への絞り込みやcacheを検討する場合も、元ファイル変更/解除/scope/profileを即時無効化できることとraw/merged順位への影響を先に整理する。warm単発値だけで完了判定しない。
2. 長い本は[既存の上限付きbatch](page-batch-indexing.md)を前提に、必要なbounded chunkと明示再開を小さく設計する。1冊16page atomic、総ページ/冊数制限、scope/profile/版/取消を維持。一般queue履歴・全冊自動chunk・1TB自動処理の完成とはしない。
3. 明示選択の代表素材で直接ページ検索/WD日英の漏れ・誤候補を記録する。直接索引でも漏れが多い場合だけOCRを検討。音声/音楽内容・複数ページ文脈タグ・数千pending性能は後続。
