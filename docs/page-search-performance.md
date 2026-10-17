# 多数本のページ検索：CPU測定・同値な計算省略・物理版確認/guard削減（2026-10-17/18）

## 最新：CPU内訳の計測と同値なfinite検査の省略（2026-10-18）

今回の同一fixture・同日の通常計測では、**1,024冊/65,536ページが13.481350秒→12.205678秒（9.46%短縮）**。前回の10.800774秒を更新したとはしない。変更前コードの再測定自体が前回より遅く、OS/SQLite cache・実行順・他プロセスの影響を分離していないため、前回10.80秒と今回12.21秒を直接の退行/改善判定には使わない。**各規模1回ずつの生成CPU検索**であり、実モデル・私物・HTTP/GUI・1TB全体の速度保証ではない。

### 今回選んだ変更は1件だけ

`app/page_semantics.py::_score_packed`で、各成分の`all(map(math.isfinite, value))`走査を、既に必要な二乗和の`math.isfinite(squared_norm)`確認へ置換した。float32のNaN/±Infは非負の二乗和を必ずNaN/Infにするため同様に拒否できる。長さ検査、単位長許容差`1e-4`、**sum→sqrt→division→dotの演算と順序**は保持。`unpack`・重み/閾値/候補/同点・全件stream・profile/namespace・物理版/除外/登録解除の確認・`_state_epoch`・1冊1回guardは変更していない。新依存・索引schema変更・再索引不要。P0品質枠は2/2で閉じたまま。

### 通常計測（traceなし、各規模1回、秒）

| 冊数 | 今回の変更前 | 今回の変更後 | 短縮率 |
| ---: | ---: | ---: | ---: |
| 64 | 0.476502 | 0.426647 | 10.46% |
| 256 | 2.744156 | 2.154090 | 21.50% |
| 1,024 | 13.481350 | 12.205678 | 9.46% |

1,024冊のguard保持合計は4.805746→4.745808秒、outer_holdsは双方1,024、単一保持最大は0.012305→0.012835秒。今回原本確認を高速化したとは主張しない。別tracemalloc passのPython割当peakは1,028,803→1,028,803 bytes（SQLite native/OS/アプリ全RSSを含まない）、その所要97.626496→83.719710秒は速度比較に使わない。

### 内訳（別cProfile pass、計器あり）

新しい`profile`モードで同じ全件rankを計測。**以下は累積時間が重なり、通常計測と比較・合算しない**。SQLはAI vector接続のexecuteとcursor nextだけの壁時計で、catalog SQL・接続全体ではない。row変換を含む。

| 区間 | 変更前 | 変更後 | 読み方 |
| --- | ---: | ---: | --- |
| rank全体 | 13.760014 | 12.298541 | instrumentation overheadを含む |
| `_score_packed` | 7.035375 | 5.806894 | 復号/検査/正規化/内積を含む |
| `builtins.sum`（2回/page） | 5.613080 | 5.503730 | 上のscorerの内数、二乗和と内積を合わせた値 |
| 原本`_read` | 5.456360 | 5.269984 | guard内、path/stat/ZIP等を含む |
| `_safe_path`（3回/冊） | 4.434832 | 4.279810 | `_read`の内数。前後の鮮度確認を省略しない |
| vector SQL execute | 0.003828 | 0.004178 | 各4 batch |
| vector cursor fetch | 0.872032 | 0.838454 | 各65,540 next（終端4含む） |

旧文書の「guard外約7.45秒＝内積」は未分離の差分値だったため訂正。実際には復号/成分検査/正規化/内積・SQL/row loop等を含む。今回の診断ではfinite全成分走査の省略を選んだ。残る物理path確認は3回/冊あり、単にcache/skipして鮮度を弱めない。

### 同値性・再現・検証範囲

- 同じprotocol SHA `caa35b6abc2e3e680b1dc3282dfad7b92c7623743e7018e43da6ab381afae311`、fixture `data/page-search-scale/v1-20261017-01/`、system Python3.14.4。既存baseline/optimized/guard-source-optは上書きせず、`finite-before-20261018` / `finite-after-20261018` / `finite-profile-before-20261018` / `finite-profile-after-20261018`を保存。HEADと製品source SHAを各reportへ記録。
- 64/256/1024冊のraw score.hex/ページID/版/model根拠とcover/max merger後の順位/score/根拠、root限定512冊、空集合が既存baselineおよび今回前後で完全一致。full raw digest `cd3cc7170b5c11c80d4779272caf0cfebd478d0c7a063ebb6503b2f1f229ad29`を保持。生成原本bytes/mtime/hash・vector DB SHA不変、全計測のモデル呼出0。
- `profile`はJSONと`.pstats`を新labelでのみ保存、通常baselineのraw/merged digest・protocol/profile/dimension・原本/DB不変・guard回数を照合。未合格reportを成功として使わず、既存結果を上書きしない。計測器は製品HTTP/GUIへ接続しない。
- 追加回帰：非finite成分の先頭/中間/末尾、NaN/両符号Inf混在、最大float32/最小subnormal/signed zero、既存unit tolerance・全bit/順位。新profile生成fixture回帰はmodel呼出0・SQL/guard計器・raw/merged/source不変・label再利用拒否・source変更拒否を検証。最新の対象/全Python・Core・Release結果は[最新handoff](codex-handoff.md)へ記録する。
- 私物scan/元データ変更/新DL/依存/GPU/OCR/WD/CIなし。GUI未変更・新native検証なし。前回取消静止PNG1枚は未確認のまま。実ライブラリ・cold/warm分離・並行UI応答・音声/音楽内容は未検証。

```powershell
# 変更前に新labelでmeasureとprofile、その後同fixtureで変更後を取得する。
python tools/benchmark_page_search.py measure --output data/page-search-scale/v1-20261017-01 --label finite-before-20261018
python tools/benchmark_page_search.py profile --output data/page-search-scale/v1-20261017-01 --label finite-profile-before-20261018 --before finite-before-20261018
python tools/benchmark_page_search.py measure --output data/page-search-scale/v1-20261017-01 --label finite-after-20261018
python tools/benchmark_page_search.py profile --output data/page-search-scale/v1-20261017-01 --label finite-profile-after-20261018 --before finite-before-20261018
python tools/benchmark_page_search.py compare --output data/page-search-scale/v1-20261017-01 --before finite-before-20261018 --after finite-after-20261018
python tools/benchmark_page_search.py compare --output data/page-search-scale/v1-20261017-01 --before guard-source-opt --after finite-after-20261018
```

## 履歴：2026-10-17の2段階改善

1,024冊×64ページ＝65,536本の768次元vectorで、ページ検索は変更前 **17.560037秒 → 第1回（`optimized`）13.551148秒 → 今回（`guard-source-opt`）10.800774秒**（変更前比38.49%短縮、第1回比20.30%短縮）。さらに物理版確認とcatalog guardの合計保持時間は **6.333872秒 → 6.158373秒 → 3.345448秒**（第1回比45.68%短縮、256冊では1.608299秒→0.369745秒）へ削減した。

第1回は保存float32の検査と正規化で重複していたfinite確認・二乗和を省いた。今回は以下を追加した：
1. **中間list生成・generator frameの省略（`_score_packed`）**：`rank()`で768要素のPython `list`を65,536回生成せず、`map(math.isfinite, ...)` / `map(operator.mul, ...)` / `map(operator.truediv, ...)`で元の`sum → sqrt → division → dot product`と同じIEEE-754 float64演算を直接計算。64hex検証も正規表現を事前コンパイルし、256冊batch間で`ai.store.connect()`を1接続共有。
2. **候補本の位置SQL 256冊一括取得（catalog guardは1冊1回を維持、`_state_epoch`による即時無効化）**：候補1,024冊ごとに`catalog.connect()`して`item_locations` / `library_locations` / `library_roots`を1,024回個別SELECTしていた処理を、256冊chunk先頭のguard保持内で1回まとめて取得。**`catalog._guard`のouter_holdsは1冊1回（1,024回、最大単一保持0.011250秒）を維持**し、編集や他操作を256冊まとめてブロックしない。guard解放の合間に`set_excludes`、`unregister_root`、`purge_inactive_root`、`add_root`、`sync_index`などの変更が発生した場合は、`ProductionCatalog._state_epoch`により位置情報キャッシュと`root_cache`を即座に破棄・再取得する。
3. **`tag_source`時のZIP central directory一括読取と`ZipInfo`生成省略**：`_zip_directory_limit`で上限検査済みのcentral directory（最大4MiB）を1回の`file.read(cd_size)`で走査し、画像エントリの有無も同ループ内で判定。`operation == 'tag_source'`では`zipfile.ZipFile`による64個の`ZipInfo`オブジェクト生成を省略。また256冊batch内で登録rootの`Path.resolve(strict=True)`結果を共有しつつ、各構成要素の`stat(follow_symlinks=False)`（junction/symlink検査）と`source.resolve(strict=True).is_relative_to(resolved_root)`は従来通り毎回実行する。

**sum / sqrt / divisionの順序・閾値・順位・同点処理・一致ページ・根拠・scope・即時の物理版変更/除外検出は一切変更していない**。まだ1,024冊で10.8秒（うちguard/物理版確認約3.35秒、guard外の復号/内積/SQL等を含む未分離値約7.45秒）かかるため、大規模検索の完成/速度保証とはしない。

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

## 履歴：当時の次課題（現行は最新handoffを優先）

1. 残る約10.8秒（うち1,024冊×OSファイルopen/statの物理版確認約3.35秒、guard外の復号/内積/SQL等を含む未分離値約7.45秒）を、版の安全性を弱めず改善する。上位候補への絞り込みやcacheを検討する場合も、元ファイル変更/解除/scope/profileを即時無効化できることとraw/merged順位への影響を先に整理する。warm単発値だけで完了判定しない。
2. 長い本は[既存の上限付きbatch](page-batch-indexing.md)を前提に、必要なbounded chunkと明示再開を小さく設計する。1冊16page atomic、総ページ/冊数制限、scope/profile/版/取消を維持。一般queue履歴・全冊自動chunk・1TB自動処理の完成とはしない。
3. 明示選択の代表素材で直接ページ検索/WD日英の漏れ・誤候補を記録する。直接索引でも漏れが多い場合だけOCRを検討。音声/音楽内容・複数ページ文脈タグ・数千pending性能は後続。
