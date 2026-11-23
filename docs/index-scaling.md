# 1万件までのAI索引拡張（2026-10-12）

> **更新（2026-10-18）**：[R02-B](full-library-search.md)で検索/similar/pending候補の1万件打切りを解消。索引jobの最大1万件と明示継続の未完は維持。以下は2026-10-12の実装/測定履歴で、現在の検索上限や資源使用量ではない。

AI索引・検索の対象上限を2,000→10,000件へ拡張。旧モデルidentity/vector schemaを変えず、保存済みの現行revisionを再利用する。単なる上限変更と区別して、候補・metadata・vectorの読出しを制限した。数万件全体/1TBの実ライブラリに対応済みとは扱わない。

## 実装

- 対象はpresentかつ現行root除外に一致しない作品。kind/viewを先に適用し、eligibleなitem ID昇順の先頭10,000件。除外済み行が先頭に多くても対象枠を消費しない。検索APIのcoverage_limit、statusのlimitは10,000（実際の索引済み件数ではなく対象上限）。検索totalは選んだ対象中のfresh vector件数。
- 候補列挙は最大IDを開始時に固定し、256行ずつkeyset取得。新しいIDの追加で無限に伸びない。大量除外時は10,000件を得るまで更にページを読むため、走査量まで10,000行以内とは限らない。
- buildは候補IDのリストだけ固定し、metadataは256件ずつ現在値を取得。後続batchのタグ変更は取得時点の最新値を採用する。推論中にpresence/revision/除外が変わった作品はpublish直前に再確認してskip。catalog全体の同一時点snapshot/複数DBのatomic transactionを保証する設計ではない。
- vectorは従来通り1作品ごとにatomic commit。進捗は16件間隔と最後に保存し、表示は最大15件遅れる。cancelは実行中の1作品処理後に終了。次回は保存済みrevisionを調べ、fresh分を再推論しない。起動時のrunning/cancelling→interrupted復旧を保持。
- 検索vectorは候補IDの256件IN batchだけ読む。1vectorずつ扱い、無関係な保存済みBLOBの全走査を避ける。mean-rrfの順位は全batchのscoreを集めてから一度だけ計算し、batch内順位を融合しない。
- 検索時のmetadata/score/rankは最大10,000件保持する。buildのIDリストも件数に比例する。constant-memory/ANN索引ではない。60件paging・明示text/cover・max rollbackを維持。
- GUIはサーバー既定値で索引を作成し、APIが返す上限を表示する。古いliteral応答にcoverage_limitがなくてもC#は受け取れる。APIの明示limit=2000は引き続き有効。

## 生成データの測定

`python tools/test_index_scaling.py --output data/index-scaling/<fresh-folder>` は新しい出力先だけ受け付ける。生成10,010個の小さいWAV名ファイルを製品scannerで登録し、うち10,000件を索引化。音声としては読まず、768次元text-onlyの決定論vectorを返すテストencoderを使う。actual_model=false / gpu_used=false / native_gui_run=false。EG2/Layaをロードしない。

smoke-01は **14 checks PASS**。2,300件でcancel→別AISearchへ再起動→残り7,700件だけdocument encode、全10,000件完了、最後の対象作品がtop1、60件/最後40件paging、お気に入りfilter、再起動後document encode 0で再利用。対象外10件は文字検索に含まれる。生成元の全byte/size/mtime digest一致。

| 測定 | この実行の値 |
| --- | ---: |
| scanner 10,010件 | 3.15秒 |
| start候補ID収集 | 0.33秒 |
| 初回2,300件まで＋cancel | 28.50秒 |
| 再起動＋残り7,700件 | 97.40秒 |
| 10,000件検索 | 1.23秒 |
| 再起動後fresh 10,000件のbuild | 9.72秒 |
| 全測定processのpeak working set | 53.34MiB |

Windows processをHidden/BelowNormalで起動しゲームの前面操作を避けた。上記はこの負荷下の1回測定で、768次元BLOBのcatalog/SQLite/ranking plumbingの値。実EG2推論、画像/CBZ読込み、2modality、GPU/GUI/1TBの速度・総メモリ・精度を示さない。vectorの多数のatomic commit/接続は今後も測定対象。既存の画像byte/pixel/並列数制限は維持し、新しいGPU使用率制限やidle検出は実装していない。

## 回帰確認と残件

生成2,105件で旧2,000件cache→105件追加、タグ1件変更だけ再生成、stale除外、再起動再利用。先頭300除外、256件境界を越えたcancel/checkpoint、推論中の除外変更、270作品/2modalityのglobal fusionも単体テストで確認。認証付きHTTPの既定10,000/明示2,000/不正limit、C# optional coverage互換を追加。

最終Python103 tests/C#15 checks/WinUI x64 SelfContained Release PASS（既存IL2104 2警告）。

ユーザーがゲーム中のため、製品GUI起動/Activate/クリック/キーボード入力/OS設定変更は今回行わない。GUIの新しい上限文と前回のContentDialogテーマ修正はRelease build/code reviewまで。前回appearance-03はUIA68 PASS / visual FAILのままで、今回のCPU検証によって視覚合格へ変更しない。WinUI analyzer未導入、既存SDK IL2104 2警告は抑制しない。

次は前面操作が可能なときLight/Dark dialogと新上限表示のnative確認、ゲームとGPUを共有しない時に生成素材で実EG2の段階的な負荷/メモリ測定、10,000件超の対象選択・進捗/資源設定の設計。私物は明示指定された小サンプルから。Layaは引き続き既定無効の実験APIのみ。


## 後続GUI確認（2026-10-12）
通常テストを許可された後、明暗dialogの10,000上限と固定status/start/cancel、Lightで17件の実CUDA索引・日本語検索後の上限文を確認。小画面で隠れていたindex actionsをmodel設定scrollから分離した。appearance-06全体はDark fresh cacheにcudaを要求したテスト条件でFAIL、修正はnative未再実行。全13 captured states目視、全17vector revisionのread-only確認を記録。[ui-polish.md](ui-polish.md)末尾の再開手順を使う。実GPU1万件の測定ではなく、上記CPU synthetic性能値もそのまま区別する。


## 生成素材での実GPU段階測定（2026-10-12）
既存EmbeddingGemma 2/default text+cover/auto-bf16/768 profile、生成**2,304件**（メタデータだけの架空WAV 2,088/PNG 144/CBZ 72、画像96×128px）で、**gpu-02: 86 checks PASS**。実CUDA/製品scanner/AISearch/VectorStoreを使用。GUI/HTTPの大規模負荷ではなくPython製品層＋所有GPU workerの測定。

64→256→1,024→2,304と同じcatalogを増分拡張。最後は1,024既存＋96新規で中断（1,120保存済み）し、新しいencoder/AISearchから残り1,184だけ推論。全text 2,304/cover 216 vectorを確認。別のfresh再起動でcached buildはdocument/image/queryすべて0・worker未ロード、その後の実queryだけでCUDAをロード。累計document 2,304/image 216/query 15、document/imageの重複推論なし。全source bytes/size/mtime digest不変、所有workerとvenv launcher/実Python等のprocess-instance handle全終了。

| 段階 | 対象合計 | 新規文字推論 | 新規表紙推論 | 秒 |
| --- | ---: | ---: | ---: | ---: |
| index-64 | 64 | 64 | 6 | 22.07 |
| index-256 | 256 | 192 | 18 | 24.27 |
| index-1024 | 1,024 | 768 | 72 | 96.83 |
| cancel-2304 | 1,120 | 96 | 9 | 13.61 |
| resume-2304 | 2,304 | 1,184 | 111 | 165.46 |
| fresh-restart-cache | 2,304 | 0 | 0 | 2.78 |

2,304件時のtext/cover/combined検索は0.23〜0.44秒。生成した雨の街並みがtext/combinedのtop候補だったが、チェックは結果有無/件数/CUDA/上限であり、一般的な精度合格率の証明ではない。

build中0.2秒間隔sampleのRAM peak: controller **40.1MiB**、所有worker process tree合計 **2062.2MiB**。PyTorchのCUDA max_memory_allocatedはworker lifetime peak **931.8MiB**。RAMはGUI/API込みの全アプリ使用量ではなく、sample間の瞬間peakを保証しない。CUDA値はreserved/context/他アプリ/ボード総VRAMを含まない。baseline `NVIDIA GeForce RTX 4070 Ti, 616.64, 12282 MiB, 6127 MiB, 48 %`、GPUの独占を保証しない単発測定であり、時間差・background負荷・小画像/短文に注意。初期lazy model loadを最初のbuild、再開後のlazy loadをresume、cache後のlazy loadを最初のqueryに含む。

gpu-01も索引/増分/検索/中断再開/推論回数/元source不変はPASSだが、CPU workerの値はvenv起動launcherだけで実モデルprocessを含まない。**gpu-01のworker RAM値を総メモリとして使用しない。**修正版gpu-02はToolhelpでlive owned Popen配下だけを列挙し、持続handleでPID再利用と区別して終了を確認。所有外process/OS設定は変更しない。

新toolのCLI guard 5 checks PASS: 範囲外output/既存output/逆順stages/重複stages/上限超を拒否。拒否先を作成せず既存result hash保持。syntax/help/diffも確認。モデル/依存/私物/個人設定/OS変更・新規取得なし。

実GPU1万件、768px等の大きめ表紙/長文metadata、実ライブラリ/1TB、GUI込み総メモリ、idle release/負荷制限は未確認・未実装。CPU synthetic1万件と今回の実GPU2,304件を区別する。Layaは精度未達の既定無効実験APIのみ。

再現（生成素材のみ／既存の専用Pythonとモデルが必要。新しい出力先だけ許可）:

    python tools/test_index_gpu_scaling.py --output data/index-scaling/<fresh-folder>

既定stagesは64 256 1024 2304。`--stages`は32..10000の厳密な昇順。重み・依存を取得せず、私物folder指定を受け付けない。実行ごとに専用catalog/生成素材を作り、result.jsonは途中の完了段階と最終結果を保存する。今回の証拠はgpu-02/result.json、gpu-02.out/err、gpu-tool-contract.json（全てignored）。途中pass=falseを最終失敗と混同せず、最終exit/resultを読む。

次の3手: (1) 生成768px表紙/長めの日本語metadataでメモリ・応答を測り1万件へ段階拡張、(2) 中断/負荷設定・不要時のworker解放と上限超の対象選択を設計/実装、(3) 明示指定された小実サンプルで検索品質を評価。全1TBへ勝手に走査しない。


## 大きめ生成素材で実GPU1万件・HTTP検索確認（2026-10-12）

開始HEAD **44ecd51**。同じfeature/Draft PR #5/baseを保持。`gpu-large-10k-01`は**126 checks PASS**、既存default EG2/text+cover/auto-bf16/768次元で実CUDA索引。生成10,000件（架空WAVメタデータ9,062、PNG625、1ページCBZ313）。cover938枚は768×768px、tag30個×60文字、実encoderの文字入力1865..1881文字とPNG寸法を記録・検証。

| 段階 | 保存済み件数 | 新規文字推論 | 新規表紙推論 | 秒 |
| --- | ---: | ---: | ---: | ---: |
| index-64 | 64 | 64 | 6 | 21.67 |
| index-256 | 256 | 192 | 18 | 24.71 |
| index-1024 | 1,024 | 768 | 72 | 94.12 |
| index-2304 | 2,304 | 1,280 | 120 | 156.50 |
| index-5000 | 5,000 | 2,696 | 254 | 300.62 |
| cancel-10000 | 5,096 | 96 | 9 | 14.51 |
| resume-10000 | 10,000 | 4,904 | 459 | 567.52 |
| fresh-restart-cache | 10,000 | 0 | 0 | 10.47 |

5,000既存+96新規で中断し、新encoder/AISearchから残り4,904件だけ推論。最終text10,000/cover938、累計document10,000/image938/query21で重複文字/表紙推論なし。fresh cache buildでは推論0・worker未起動、その後のqueryのみCUDAロード。元source bytes/size/mtime digest不変、所有9 process-instance handles全終了。

10,000件の単発検索: text 1.98秒（10,000候補） / cover 0.99秒（938候補） / all 1.89秒（10,000候補）。warm/cold等の条件はresult phasesで区別する。最初のbuildと再開buildはlazy model load込み、cached後最初のqueryは再ロード込み。一般的な検索精度の合格率ではない。

build RAMの0.2秒sample peak: controller **101.2MiB working set**、所有worker tree **2049.9MiB working set**、同tree private commit **5330.1MiB**。private commitを全て物理RAMとして足さない。torch CUDA lifetime max allocated **994.0MiB**（reserved/context/他アプリ/ボード総VRAMを含まない）。baseline `NVIDIA GeForce RTX 4070 Ti, 616.64, 12282 MiB, 3069 MiB, 15 %`。単発・他GPU利用ありで独占benchmarkではない。

`test_index_gpu_api.py`で完了済みの生成1万件のみを受け付け、製品loopback/token/Origin APIを専用processで確認。**28 checks PASS**: 60/60/40/0件のページ0/1/166/167、重複しないページID、画像625件、cover938件、ID1と10000のお気に入りをHTTP更新→検索で2件。変更はfinallyで元に戻し、vector/source/benchmark result digest不変。query7回のみ、文書/画像推論0、所有3 process-instance handles全終了。HTTP controllerのprocess lifetime peak working set **116.0MiB**（API/検証処理込み、GUI除外）。各request単発: first 15.31秒 / second 1.78秒 / last 1.79秒 / beyond 1.81秒 / images 0.28秒 / covers 1.91秒 / favorites 0.12秒。HTTP初回はmodel再ロード込み。HTTP試験終了後の所有worker停止を確認し、native GUI1万件負荷は未実行。

preflightは768×768/30tag/128件で49 checks PASS。CLI guardはbenchmark9/API5 checks PASS: 範囲外/既存/未完了/1万件でない入力、寸法/tag上限等を拒否し既存証拠を保護。新しいtoolのsyntax/help/diff checks PASS。Python103 tests/C#15 checks/WinUI x64 SelfContained Releaseも再確認（実行logはdata/index-scaling/gpu-large-*）。WinUI code reviewは変更差分とnative Items/60 paging、async/dirty、DOM JSON、theme/profile/auth境界を確認。WinUI analyzer未導入。今回GUIは変更・再実行なし、前回appearance-09の105 checks/17 PNG目視PASSと区別する。

画像は単純図柄でPNG約6KB、生成source全体は**5.9MiB**。768px画像decodeと現行processorによるresize/280 soft-token上限を通る測定であり、大きな実ZIP/JPEGのI/Oや最大byte/pixel限界を網羅しない。tag内容は共通の架空負荷文で、品質コーパスではない。実1TB/多数root/実作品・GUI込み総資源/一般検索品質/別checkpoint/Laya精度改善/reader/Komga/HC/高DPI/AOT/配布は未確認。私物・個人設定・OS・依存・モデルは変更/取得なし。

再現（生成素材のみ、新規output）:

    python tools/test_index_gpu_scaling.py --output data/index-scaling/<fresh-folder> --stages 64 256 1024 2304 5000 10000 --cover-width 768 --cover-height 768 --metadata-tags 30
    python tools/test_index_gpu_api.py --fixture data/index-scaling/<same-completed-folder>

既定の小素材/stagesを保持。cover各32..768、metadata-tags0..30、tag長60。build1phaseは測定toolだけ最大3600秒、製品timeoutは変更なし。APItoolは生成/合格/実GPU10000/生成rootを確認し、api-result.jsonがない時だけ実行する。全result/DB/生成素材/logはignored。途中pass=falseを失敗と混同せず最終exit/resultを確認。

次の3手: (1) [ai-resource-policy.md](ai-resource-policy.md)の明示worker解放を実装し生成実GPUで停止/再ロード/競合を検証、(2) 選択式idle解放/索引待機と上限超の対象選択をGUIへ、(3) 明示指定の小実サンプルで意味/表紙の検索品質を評価。Layaは精度gate未達の既定無効実験APIを保持。
