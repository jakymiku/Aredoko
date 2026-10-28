# R05 — 動画起点の類似検索と時刻根拠・既存UI接続

2026-10-19。R05として、保存済みの時間付き動画代表フレームvectorを活用した動画起点・動画候補の類似検索、時刻根拠（timepoint grounding）、自己除外、および既存WinUIビューア接続を実装完了（CPU_DONE）。
実機GUI/GPU受入はユーザー方針に従いR14で一括検証（`tools/test_video_similarity_acceptance.py`）。次はR06（音声/音楽の入力能力・モデル/契約/評価設計）。

## 1. 類似検索アーキテクチャと集約契約

- **動画代表フレームの取得 (`VectorStore.video_frames`)**:
  - `ai_video_frames` テーブルから指定アイテムの全代表フレーム `(at_ms, vector_blob)` を `at_ms` 昇順で取得。
  - 代表フレームが未索引で `cover` ベクトルのみ保存されている場合は、時刻 0ms の1フレームとして安全にフォールバック。
  - 保存された blob は長さチェック（`dim * 4` バイト）、および非負二乗ノルム `isfinite` チェックにより、不正・破損・非有限（NaN/Inf）ベクトルを割り当てなしで除外。
- **マルチフレーム最大類似度集約 (`VectorStore.scores_with_content`)**:
  - 動画が起点または候補となる場合、フレーム単位のコサイン類似度 $\cos(\mathbf{v}_{orig}, \mathbf{w}_{cand})$ を比較し、最大の類似度を採用。最初の1フレームだけの比較を「動画全体」と偽らない。
  - 最大類似度を達成した候補フレームのタイムスタンプ `video_hits[cand_id] = cand_ms`、および起点フレームのタイムスタンプ `origin_hits[cand_id] = orig_ms` を正確に記録（Timepoint Grounding）。
  - 起点と候補の組み合わせ（厳格な4通り契約）:
    1. **動画 → 動画**: 起点フレーム時刻 `origin_match_ms` と候補フレーム時刻 `video_match_ms` の双方を記録。
    2. **画像/本 → 動画**: 候補フレーム時刻 `video_match_ms` を記録（起点時刻 `origin_match_ms` は付与せず null）。
    3. **動画 → 画像/本**: 起点フレーム時刻 `origin_match_ms` を記録（候補時刻 `video_match_ms` は付与せず null）。
    4. **画像/本 → 画像/本**: 時刻根拠なし（双方が null、「起点の画像・表紙に似た候補」を表示）。
  - フォールバックと堅牢性境界:
    - 代表フレーム未作成で `cover` のみ存在する動画候補は `video_match_ms = 0`（0:00）として安全にフォールバック。
    - タイムスタンプは `0 <= at_ms <= 86_400_000`（24時間以内）を厳格検証し、破損・負値を安全に除外。
    - 空の `query_frames` に対する防御と `SimilaritySearch.Parse` による `origin_kind` の厳格なプロトコル検証。
- **自己除外と範囲制御 (`AISearch.similar`)**:
  - 起点アイテム（動画・画像・本）は結果リストから確実に除外 (`exclude_id=item_id`)。
  - 起点アイテムの種別 `origin_kind` を検索レスポンスに明示的に含め、UI側で適切な説明や案内を表示可能に。
  - 候補の対象種別として `('image', 'book', 'archive', 'video')` を許可（`audio` はR06/R08まで対象外）。
  - 起点・候補ともにファイル原本の変更・再エンコード・モデル推論は行わず、保存済みベクトルのみを使用。

## 2. Coreプロトコルと根拠表示 (`Aredoko.Core`)

- **`SimilaritySearch.CanStart(row)`**:
  - `video` 種別を許可 (`row.Kind is "image" or "book" or "archive" or "video"`、`audio` は拒否)。
- **`SimilaritySearch.Guidance(status, originKind = "")`**:
  - `originKind == "video"` の場合、「この動画の代表フレームはまだAI索引に含まれていません。設定の「AI検索の準備」から索引を作成してください。」等の動画特化メッセージを提供。
- **`MediaRow.AIEvidence`**:
  - 動画起点と動画候補の組み合わせに応じたタイムスタンプ根拠表示:
    - 動画 → 動画: `動画一致（起点 M:SS → 候補 M:SS）\n類似度 0.xxx`
    - 画像 → 動画: `動画フレーム一致（M:SS）\n類似度 0.xxx`
    - 動画 → 画像: `起点の動画（M:SS）に似た候補\n類似度 0.xxx`
    - 画像 → 画像: `起点の画像・表紙に似た候補\n類似度 0.xxx`

## 3. WinUI 3 UI接続 (`Aredoko.WinUI`)

- **右クリックコンテキストメニュー (`SimilarityMenu`)**:
  - 動画行の右クリックメニュー項目を `似た動画・素材を探す`（AutomationId: `FindSimilar{row.Id}`）に変更。
  - 画像・本は従来の `似た画像・素材を探す` を維持。
- **類似検索バナー・ガイダンス**:
  - 動画起点の類似検索時、情報バナータイトルを `似た動画・素材`、ヒントを `動画の代表フレームから似た候補を探しています。検索語の入力や「検索」で通常の検索に戻ります。` に更新。
- **動画プレイヤー自動シーク (`VideoPlayerView`)**:
  - 検索結果をクリックして動画を開いた際、`row.VideoMatchMs` が存在すれば自動的に該当時刻（`Math.Min(startMs, duration - 50ms)`）へシーク。
  - ステータスバーに `該当時刻（M:SS）に移動しました。再生ボタンまたはスペースキーで再生できます。` と通知。

## 4. 検証と品質記録

- **Python単体テスト (`tests/test_similarity_search.py`)**: 21 PASS (16 既存 + 5 新規 `VideoSimilarityTests`)
  - `test_video_to_video_multi_frame_max_aggregation_and_grounding`
  - `test_image_to_video_timepoint_grounding`
  - `test_video_search_kind_filtering`
  - `test_video_unindexed_and_corrupt_frame_fallback`
  - `test_video_similarity_zero_inference_and_sources_unchanged`
- **C# Coreテスト (`tests/Aredoko.Core.Tests`)**: 595 PASS, 0 failure
  - `SimilarityTests.cs`: `CanStart` による video 許可 / audio 拒否、`VideoMatchMs` / `OriginMatchMs` のパース、`AIEvidence` 複合時刻表示、厳格な動画候補検証。
- **WinUIビルド**: x64 Release 0 warnings / 0 errors
- **受入ハーネス (`tools/test_video_similarity_acceptance.py`)**:
  - `--stage cpu`: 全単体テスト、Coreテスト、WinUIビルド、プログラムによる動画類似検索実証（2動画・1画像によるコサイン1.0最大集約と時刻記録）に合格。
  - `--stage gpu` / `--stage gui`: R14 バッチ実行用に準備完了。


## 2026-10-27：モデルの動画直接入力と現行製品経路の区別

利用者からの確認により、Google公式の[マルチモーダルガイド](https://ai.google.dev/gemma/docs/embeddinggemma/multimodal-embeddinggemma-with-sentence-transformers)と[モデルカード](https://ai.google.dev/gemma/docs/embeddinggemma/model_card_2)、導入済みST/Transformersのvideo processorを照合。EmbeddingGemma 2は動画を直接入力でき、抽出済みPIL frame列も一つのvideoとして扱える。共有8,192token枠があり、既定の1fps/max32frames等のsamplingは実装版の設定も確認する。ファイルを丸ごと渡せば長動画の全場面/会話/BGMを無制限に理解するという意味ではない。

**現在の通常Aredokoの索引は最大4代表フレームを個別imageとしてencodeする方式のまま**。そのtext→動画/動画→動画・画像と時刻接続は既存実装。動画そのものの区間入力、動画内音声との統合、長動画分割の通常producer/GUIは未接続。通常DB・既存vectorを勝手に再解釈しない。

新しい内部primitive：`VideoWindow`は最大16秒・1fpsの1〜16 RGB frames・各384px以内・全8MiB以内。時刻/寸法/immutable bytesを検証し、private wireで画素だけを転送する。URL/path/任意decoder入力を許可しない。`video_profile_for`はtext/video専用contractとnamespaceを作り、旧text/cover/audioのkeyを保持。adapterはvisionを残しaudioをloadせず、`model.encode({'video':frames})`を1回呼び、STの再samplingを無効化・140soft tokens/frame・timestamp promptなしを明示する。PIL資源はfinallyでcloseする。

Python9件（開発/基本Python）・既存audio worker14・既存profile関連のCPU確認を実施。RGB時刻/wire上限・悪い入力・旧profile拒否・動画1入力へのbatch・黒frame非skip・model前validationを確認した。**この段階ではGPU/品質/区間索引/検索UIの完了ではない。** 次は個別許可による生成3frameのprivate worker GPU入力確認。その後にguard付きdecoder、長動画分割、atomic索引、検索/時刻根拠、image/audio/video所有モデルの同時常駐防止を一単位ずつ接続する。現行`InferenceOwnership`は2ownerのため、第三ownerを無計画に追加しない。


### 生成3frameの実GPU API確認と区間decoder（2026-10-27）

個別許可後`video-worker-gpu01`で実private workerへ3生成RGB frameを1動画として送信。動画と日本語queryが有限・正規化768Dを返し、cosine0.7425（精度/確率ではない）。child allocator peak965.7MiB、上限3072MiB、元画素不変、所有worker回収済み（既存close方式のexit1）。追加取得/GUI/DB/実動画0。API接続の限定合格で、検索品質や通常索引の完成とはしない。

`video_window_decode.read_video_window`は検証済みseek可能handleから1既知区間だけをFFmpegで読み、RGB384正方・SAR/比率維持letterbox・1fps・最大16frameへ変換する。pipe/fd＋限定demuxer、20秒、出力上限、所有子回収を既存_runで保持。端数末尾は既知のtotal_duration_msでのみ最終frameを保持してsamplingし、短いdecodeから全体EOFを推測しない。初回はoutput側`-t`が3.3秒の末尾frameを落とすことを最小CPU診断で特定。input側の時間上限＋frame数上限へ修正し、赤→青の生成動画で後区間の実画素と3.3秒tailを確認。失敗log01/02も保持。

`PreviewReader.video_input_window`へ内部接続し、既存の原本版・size/mtime/open handle・祖先link・登録/除外の前後検査、取消、slot解放を適用。HTTPにraw clip routeを追加せず、通常索引・DBは更新しない。known durationは将来のproducerが同じ検証済みsourceのprobe結果から与える必要がある。decoder6（開発/基本Python）、source5（両Python）、既存preview22/audio source18 PASS。通常の動画検索は従来方式のまま。次はduration/coverage planと全区間成功後のatomic保存、所有model統合である。


## 2026-10-27：直接動画production job/API・レビュー修正

`VideoDirectFeature`は固定された画像profileから別のtext/video profileを派生し、statusだけではsidecar/workerを起動しない。明示consentで`VideoDirectJobs`を開始し、登録videoだけを共通scopeで選び、最大1000件のbatchを処理する。再開は完了済みrevisionをskip。`video-direct` result sessionは動画indexの変更だけで失効し、通常literal sessionに波及しない。既存代表frame検索とは別経路である。

所有groupのroleはimage/audio/videoに限定し、互いのresident workerを解放・非resident確認してから推論権を渡す。未知role/重複role/常駐済み新登録を拒否し、第三workerの同時常駐を許可しない。backend終了・idle policyへ動画ownerを接続した。

親レビューとTerraによる再点検で次を修正した：
- 動画v1 sidecarをbackup whitelistへ追加。v1は音声pairか動画pairの一方だけ、v0で直接媒体table・片側だけ・両pair混在は拒否。生成動画のlive capture→restoreで全marker/window一致、legacy namespace併存を確認。
- 登録解除rootのpurgeで動画source/windowの両tableも削除し、生成原本bytesを保持。
- 所有jobの取消と最終check/commit/progressを共有gateで直列化。取消が先なら旧公開を保持、最終item commitが先なら取消は不受理。途中まで成功したbatchはそのitemを保持し、再開でskip。gateは長いdecode/stage/copy中には保持しない。
- 初期化にfeature close eventを渡し、catalog guard/fence待ちを中断。closeが無関係なcatalog操作を永久に待たない。

検証：親の所有管理/動画HTTP/既存音声HTTP19 PASS、最終動画job/feature/HTTP/recovery/index37 PASS。Terraのjob/feature/index/search/HTTP41 PASSは一部重複する別run。backup関連30 PASS＋fixture不足1 import ERROR、既存backup27 PASS＋不足ファイル2失敗→正しい固定SHAのfixture/CLI/profile補完後、失敗した2件のみPASS。初回エラーはcheckout不足であり製品不具合ではない。原本変更試験は意図したReaderChangedをlogする。モデル・GPU・GUIは使っていない。

Windows再開手順：生成した短いMP4を独立catalogへ登録し、通常所有backendでstatusがlazyであることを確認→認証付きvideo-ai/startへconsentとroot条件→status完了→video-ai/searchとvideo-direct sessionで区間根拠を確認→cancel/resume/release・画像/音声へ切替時の単一resident・所有終了を確認する。既存モデルのみ使用、通常DB/Alphaを変更しない。未導入モデルを自動取得しない。実encoder品質、長動画/1時間225 decoder起動の性能、WinUI入口と動画起点直接類似は未受入/未実装である。


## 2026-10-27：保存済み直接動画の類似検索（backend/API）

`VideoDirectSimilarity`は専用video namespaceの全windowから最大cosineのpairを選び、候補の`video_match_ms/video_match_end_ms`と起点の`origin_match_ms/origin_match_end_ms`を返す。`mode=video-similar`、`source=video-direct`。自己除外・stable ID tie・root/棚/exclusion・候補favoriteを共通catalogで適用する。起点はfavorite条件で隠さず、root/棚の制約は適用する。

動画では無音skipがないのでdecoded=indexed・ordinal連続・非最終16秒・最終区間上限・全frame数・正規化vector・契約と物理revisionを厳密照合し、不完全な索引を一致候補にしない。原本・index・profile・条件が途中で変われば結果を破棄し再検索案内を返す。モデル利用不可でもcached vectorがあれば利用し、推論groupを取得しない。

APIは認証付きPOST `/api/library/video-ai/similar`（item_idと任意page/limit/view/root_ids/shelf/shelf_ids）。固定結果は `/api/library/results/create` のconditions `{mode:video-similar,item_id:...}`から作成でき、動画namespaceのstampと起点原本を再検証する。GUIにはまだ未接続。

親はTerraの成果物をレビューし、候補を次へ読み込む前に前vectorを解放するよう修正を戻した。weakrefで前候補bufferが次の読込前に消えることを確認。親側でrender時のPreviewUnavailableをVideoSearchChangedに変換し、原本変更を入力エラーにしないよう補強した。

比較はexact all-window-pairで、コストは起点window数×各候補window数×dimension。上限は1要求100,000pair/1item float64 vector payload32MiB。前候補を解放して起点＋現候補を保持し、全結果はScoreSpoolへ。1時間同士は225×225=50,625pair/候補。上限超過は日本語でフォルダー/棚の絞込を案内し、途中順位や偽のsearch_completeを返さない。payload上限はプロセスRSS全体の保証ではなく、大dimensionでは24時間前に上限へ達する。長動画・大規模catalogの性能は未受入。

CPU結果：Terra similarity/index/search30 PASS/7.052s、追加weakref1 PASS。親HTTP5 PASS/3.609s（モデル不可＋image busyでも比較・原本変化session失効）、similarity/HTTP18 PASS/6.560s、最終2回帰PASS/0.460s（range中の候補変更と1候補spool後のcap超過・部分結果非公開）。重複runを合算しない。全て生成MP4・疑似vectorで、画像理解/実動画精度・native表示・GPUの合格ではない。

Windows次工程：通常代表frame類似の入口を維持しつつ、直接動画準備と内容検索・直接動画類似の別入口をCore/WinUIへ。独立DBの生成2動画で、自己除外/両端時刻表示→候補の一致開始へseek→originへ戻れることを確認する。登録範囲変更・モデル不可cached・取消・上限案内も限定確認する。私物/通常DBを使わず、モデル/依存取得はしない。


## 2026-10-27：Core/WinUIの直接動画source接続（未ビルド）

CoreへVideoContentClient/Statusとmode8を追加し、LibraryApiの認証済みclientを使う。ResultSearchConditionsはvideo-direct/video-similarへ共通root/棚/view条件を渡し、画像AI scopeを要求しない。ResultSessionClientは動画類似をSimilaritySearchのdirectVideo parserへ渡す。Protocolはsource=direct-video/contract=direct-video-window:v1と両端を厳密検証し、代表frameの単一時刻と混同しない。区間は0<=start<end<=24h、長さ<=16秒。起点があれば起点両端も必要。表示は小数秒を保つ。

WinUIは既存AI準備画面内にVideoPreparationPanelを追加。開くだけでは索引を開始せず、明示作成/中断、閉じた後の再表示/継続観測を提供する。検索方法は既存indexを保持して8へ動画内容を追加し、種類は動画に合わせる。右クリックには直接内容類似を別項目で追加し、旧「似た動画・素材」（代表frame）は維持。起点/候補区間は既存詳細のAIEvidenceへ。動画playerは既存VideoMatchMsの開始seekを再利用する。

親がコードをレビューし、直接動画/音声類似を開始する時にkindだけでなくmodeも揃えて、元のmode7/8との食い違いを防いだ。履歴keyと復帰に直接動画flagを保持し、類似解除では両direct flagを解除。動画内容のqueryにはruntime準備待ちを適用するが、cached動画類似では適用しない。mode8のエラー案内漏れも相互レビューで修正。

確認済みはXAML XMLの整形式・9項目とソースレビュー、既存generated backend HTTP5 PASS/3.562sまで。.NET SDK/csc/mcsがなく、新規Core tests、C# compile、WinUI/Portable build、native画面/GPUは未実行。147 C#関連sourceを固定HEADで取得したが、画像asset等を含む完全checkoutではない。ビルド可能・操作可能を実証したとはしない。

Windows受入の次手順：
1. 通常開発checkoutを最新branchへ同期し、インストール済み.NET10/cacheで `dotnet run --project tests/Aredoko.Core.Tests -c Release -- --video-content` を実施。既存Core回帰と既存Portableビルド手順を実行し、失敗は診断して対象修正する。Actionsは起動しない。
2. 生成3.3秒/17.5秒MP4二本・独立catalog/設定/LOCALAPPDATAで起動。設定の動画内容欄を開くだけではjob/modelが起動しないこと、明示作成→中断→続き、閉じる/再表示を確認。
3. mode8と種類動画、root/棚/favoriteの範囲を確認。内容query→一致区間表示→候補開始へseek。右クリック直接内容類似→自己除外/双方区間/旧代表frame入口併存を確認。
4. 音声mode7から直接動画類似→検索入力、動画mode8から音声類似、戻る/進むと元の検索に戻る、未保存タグdraftの破棄確認を確認。cached動画類似はモデル利用不可でも使え、再推論しないことを専用ログで確認。
5. 普段DB/Alpha/shortcutを変更せず所有processを正常終了。実encoder精度・長動画/大規模性能・配布全体の受入は別。Windows待ちには独立したCPU残件へ進む。

## 2026-10-27：Windows引継ぎレビューと動画文章検索の不完全索引保護

`859803d`までfast-forward同期（clean、既存branch/PR #5一致）。Core `--video-content`と既存Core runner、既存cacheを使うPortable publish/frontend01がWindowsで成功。新しいcompile errorはなく、既存WUI1001 picker3とSDK IL2104を保持。GUI/GPUはまだ実行していない。

レビューで、cached類似には全coverage検証がある一方、動画の文章検索は欠落window・壊れたvector・marker件数不整合から部分一致を公開し、`ready`と報告することを生成CPU試験で再現。文章検索もordinal/連続区間/16秒境界/総frame/正規化vector/完全markerを全て検証したitemだけを順位へ公開するよう修正。120件のbatch cursorと定数サイズの集計を保ち、全vector集合を保持しない。range描画中の原本消失も500ではなく再検索が必要なVideoSearchChangedへ変換する。

旧codeの追加2回帰は7subtest FAIL/2ERROR（同一run）を保持。修正後は検索/認証HTTP14 PASS。証拠`data/ai-ui/continuation-20261027b/`。これは破損索引を誤一致にしない確認であり、実モデル品質や長動画性能の受入ではない。壊れた索引のfresh判定・明示再生成導線は別途改善余地がある。

### 通常所有pipelineとWinUIの限定受入

frontend01（WinUI source d323db0、backend6ba34e6）と生成無音MP4二本/CPU供給vectorを使用。video-native01はWindows前面化が拒否され入力前に停止、exit0。初期準備を待ったnative02は準備lazy/開始/中断/atomic非公開/再開2件/文章queryの16–17.5秒/詳細/旧代表frame入口併存/直接類似・両区間/自己除外まで確認。7PNG目視。最後は試験でモデルを利用不可にしたまま通常query付きお気に入りへ移り、履歴の前提を満たさず停止したため全体PARTIALを保持。成功済み操作を反復せず、native03はCPU事前索引→モデル不可cached類似→登録フォルダ→戻るの限定10checks/3PNG目視/exit0でPASS。既存のタグ/生成原本不変、全所有process正常終了。実再生/seekは行っていない。

個別GPU許可1バッチのvideo-owned-gpu01では、同じ生成色動画（3.3秒/17.5秒）を実production owner/private workerで全3区間保存し、日本語2問はTop1。index29.250s、child allocator peak1424.1MiB、上限3072MiB。画像worker未使用。raw reportは最後のharnessのread-only available代入でFAILを保持し、実際の索引/文章検索/明示release成功と区別する。harnessを修正したがGPUは再実行していない。保存済み専用DBを基本Python3.11＋モデル利用不可CPU encoderで再openし、cached類似（0推論/両区間）を別review.jsonで確認した。所有子は既存close方式exit1で回収。

CPU再open初回に開発Python3.14を使うと、Python3.11生成のrevisionとWindows statのctime等の意味が異なり、安全に未索引扱いとなった。元の親と同じ基本Python3.11で再確認したもので、原本guardを弱めていない。GPU初回の原本pre SHA記録は欠測で、原本SHA/mtime前後一致まで成功扱いにしない（CPU再open前後は一致）。全結果は限定生成fixtureの配線確認で、実動画の一般品質・音声track・長時間性能・clean Windowsの合格ではない。

### 壊れた索引を次の明示作成で再生成

検索から壊れたcoverageを除外するだけでは、marker一致だけのfresh判定が再生成をskipする問題が残る。freshでも連続区間/件数/総frame/float32 vectorの正規化を1vectorずつ検証し、壊れたitemを次の明示batchへ戻す。既存公開を直接削除せず、従来の全区間stage→atomic置換を使う。planning中の取消もvectorごとに確認する。metadataだけの旧判定より確認量は増えるが、全vectorをRAMへ保持せず、model/decodeは開始しない。

生成index/jobs28 PASS（原本変更の意図した例外logを含む）。追加回帰は欠落・ゼロvector・marker不整合/型、fresh検査中止、明示再作成で正常化を確認。`video-repair01.log`。新しいGUI/GPU受入は行っていない。

2026-10-28：cached動画/音声の内積generatorを同じ乗算順・sum順のmapへ共通化。再索引不要、cap/全pair/取消/世代/原本guardを保全。関連32 PASS、同一Python内のfloat64 bit一致とkernelだけの補助計測は[音声正本](audio-producer-review.md#2026-10-28音声動画の内積ループを同じ計算順で軽量化)。長動画decoderの225プロセス/時間や実動画品質を改善済みとは扱わない。


## 2026-10-28 Work：全区間準備を1つの所有デコーダーで逐次処理

従来の`iter_video_coverage`は16秒windowごとにFFmpegを起動してseek/decodeし、1時間で225回起動した。通常の`PreviewReader.video_coverage_stream`を新しい`VideoCoverageStream`へ切り替え、検証済み同一fdのduration probe1回＋FFmpeg1回で全区間を順に読む。既存の単一区間APIと`iter_video_coverage`は低位の有界decode・比較確認用として維持し、既存の代表frame検索/通常再生を置換しない。

初回nextまで起動しないcontext所有producer。既知総尺からceil(duration/1秒)の出力数を決め、従来と同じfps=1/round=up、SAR補正/384×384 pad/rgb24、既知末尾だけの1秒clone補助を使う。16frame/最大16秒のVideoWindowを1つずつ渡し、最終endはprobed総尺。モデル/profile/vector契約を変えず、自動再索引はしない。固定rgb出力の不足・不完全frame・上限超過・非0exitは成功扱いにしない。全windowを返した後も、実decoder exit0と原本guardを確認した正常exhaustionが必要。失敗すれば従来Indexのprivate stageを回収し、旧公開へrollbackする。

stdout readerは1frame単位のqueue（最大1）と1frame分のpendingに抑え、消費側の推論待ちはbackpressureで止める。1window最大約6.75MiBに加えてqueue/pending/Python一時領域があり、呼出側が保持する旧windowやFFmpeg内部heapまで含む8MiB上限ではない。sourceはregular/最大32GiB、fd/pipeとdemuxer allowlist、max_pixels/alloc/stream/probe上限を継承。20秒/windowの待ち上限、取消・毎frame/毎window・正常終端でのidentity/登録/除外/revision確認を行う。入力path/URLや出力fileをFFmpegへ渡さず、FFREPORTを除去する。閉じる/早期break/失敗時は所有processをkill/waitしreaderをjoin、呼出側のsource handleを勝手に閉じない。未開始threadのstart失敗でもprocessを回収する。

生成3.3秒/17.5秒・16秒境界の赤→青・動くtestsrc2で、旧方式と区間/末尾および**全RGB byteの一致**を確認。新経路の実production Indexで17.5秒/2windowをFFmpeg1回で保存し、途中cancelは旧公開を維持する。疑似decoderが全画素を書いてからexit7になった場合も旧索引不変・stage回収・producer slot解放を確認。短い出力・部分frame・余分なframe・no-progress deadline・precancel・未知duration・原本変更/登録取消・早期close・reader起動失敗の所有回収を確認した。

試験記録：初期stream8 PASS/1.298s。続く関連index/jobs/認証HTTP/source＋追加2件は40 PASS/8.815s（意図した原本更新でjob失敗のlogger出力があり、テストFAILではない）。最終のstream9＋atomic失敗1は通過したが、同runに不存在の`NativeCoverageIndexTests`を指定して11 run中1 runner ERROR/1.828sを保持。`RealVideoIndexTests.test_real_long_video_and_cancel_between_windows`を正しく指定した追加1件はPASS/0.587sで、実productionの起動回数1と取消rollbackを確認した。成功済みの重複runは合算しない。py_compile成功。

既存`tools/package_release.py`はapp直下の.pyを全てcopyするため、新moduleを次の候補に収録する経路はあるが、今回ZIPの作成/installed Alpha更新/Windows起動は行っていない。基本Python3.11/Windows上でのFFmpeg pipe/reader所有終了・実modelとのbackpressureは未確認。長時間、VFR、timestamp gap、全codec、実動画の品質/総RSS/性能は未受入。1時間の実測や「225倍高速化」の証拠ではない。

Windows残確認は、最新sourceのCore/Portable build後、生成2動画と独立DB/settingsで、準備→中断→再開→区間付き文章検索/保存済み類似を限定確認する。専用decoder process1本と正常終了時の残存0を記録し、既存の通常backendへ接続しない。長動画の計測は別の1caseとし、decode/native process数と実model推論時間を分ける。


## 2026-10-28 Work：長い動画の区間進捗をAPI/Core/WinUIへ接続

これまで準備画面は保存済みitem件数だけを表示し、1本の長い動画では内部windowが進んでも0/1のままだった。Indexに任意のprogress callbackを追加し、私有stageへ解析済みvectorを挿入した後だけprepared_ms/prepared_windowsを進める。読み取り前はdecoding、モデル呼出し中はencoding、正常exhaustionとstage commit後から公開commit待ちはsaving。既知durationを共有し、初回probe前の不明値はnullのまま保持する。callback前後も取消を検査し、長いdecode/encodeやprogress更新でpublication gateを保持しない。

既存認証statusへ`item_progress`を任意object/nullとして追加（旧serverにはfield自体がない）。例は以下。preparedは解析済みの私有データであり、indexed/processedは引き続き実commit後のitem件数だけ。

```json
{"item_id":9,"prepared_ms":16000,"total_ms":3600000,"prepared_windows":1,"phase":"encoding"}
```

item_id以外の原本名/絶対pathを追加しない。Jobsのguard下で更新し、statusはdeepcopy。保存成功は既存のcommit/cancel gate内のon_publishedで件数を進めcurrentを消す。取消/失敗もcurrentを消し、新batchはnullから開始する。途中の解析区間を再開可能な保存物とは扱わない。検索/namespace/DB形式・既存resume/fresh/原本guard/単一resident契約は変更しない。

Coreは旧field省略/nullを許し、新objectは厳密int/最大24h/5400区間/ceil(prepared_ms/16000)の整合/既知total以下/phase/stateの整合を確認。総尺不明は先頭decodingだけ、savingは全尺解析後だけ。完了stateに古いcurrentが残る応答も拒否する。WinUI sourceでは現在の動画の解析時刻をProgressBarへ使い、総尺不明/中断待ちはindeterminate。未保存、終了確認、保存中を短い日本語で区別し、完了件数とは混ぜない。panel閉鎖は観測だけを止め、再展開は同じjobのstatusを取得する既存契約を維持。中断した動画は次回初めから準備することもtooltipで案内する。

生成fixture＋疑似encoderのindex/jobs/認証HTTP/featureは**44 PASS/9.514s**。encoderの2区間目を停止して16000/17500ms・1区間解析済み・processed/indexed=0、旧公開不変、status観測の非blocking、観測側のobject変更がjobへ逆流しないことを確認。取消/再開始/保存成功のcurrent消去、progressからencode前取消した場合のrollback、公開前の全phaseでも旧索引を維持することを確認。既存の想定原本変更による失敗logger出力を含むがtest FAILはない。失敗時current消去のassert追加後にその1件だけ**PASS/0.136s**、py_compile成功。重複runは合算しない。

Coreの`--video-content`には旧server互換・未知duration・未保存/saving/終端確認・不正count/時間/phase/terminal stateのsource回帰を追加。**Core/C# compile/WinUI/Portable/nativeはWindows/.NET不在で未実行**。Windowsでは当該Core→前段`--favorite-patch`→buildを実施し、生成の短動画とやや長い動画/独立DBで時刻進捗・保存待ち・中断/再開・panelを閉じて再表示を一つの限定caseにまとめる。実model/GPU許可を自動拡張せず、通常backend/DBへ接続しない。

## 2026-10-28 Work：1時間の生成動画による単一decoder比較（1caseだけ）

Linux x86_64 / Python3.12.14 / FFmpeg6.1.1-3ubuntu5。`testsrc2=s=160x90:r=1:d=3600`をMPEG4/1fps/faststartで生成（生成0.616秒、21,993,463bytes）。独立ProductionCatalogと3D疑似video encoderを使い、同一Indexのproducerだけ旧`iter_video_coverage`へcontext adapterで差替えた旧runと、現在のVideoCoverageStreamの新runを各1回実行した。Source guard・SHA256集計・225回の疑似encode・stage/atomic保存を含む壁時計。実modelの推論は一切行っていない。

| 指標 | 旧・区間ごとdecode | 新・単一decoder |
| --- | ---: | ---: |
| 全225区間の準備/保存 | 17.237230秒 | 3.487139秒 |
| 最初の16秒windowがencoderへ届くまで | 0.141068秒 | 0.122945秒 |
| FFmpeg起動 | 225 | 1 |
| ffprobe起動 | 1 | 1 |
| 保存window数 / 入力frame数 | 225 / 3600 | 225 / 3600 |
| 所有child回収 / producer slot解放 / stage回収 | 全て成功 | 全て成功 |

両runの全RGB SHA256は`86706619c5b723bf5ffea84dffbfec8d4ef750e95155f166da489e02197416af`、保存したordinal/start/end/vectorのJSON digestは`c5096c314c1a9f7b53332b1c2d8243f581366c63d9a179a01c1e1ecc53750ce3`で一致。原生成SHA256`50cfb6bb6ced68575edb304fda50c026657949908a6753245cd4f06864a259c5`とmtimeも前後不変。試験用動画/DBは一時directoryだけを使い、終了時に回収した。raw記録はWork内部の`.codex/aredoko-video-hour-cost.json`（Git対象外）、ここに再開に必要な方法・数値・digestを保持する。

この1caseでは約4.94倍だが、1fps/低解像度・疑似3D encoderの結果であり、高解像度/高fps/全codec/VFR/実GPUモデル・一般の動画準備速度へ外挿しない。総RSSは計測していない。cold/warmを揃えた多数回benchmarkでもない。1時間のCPU caseは実施済みとして無変更で再測定せず、残りはWindows実worker/用途別の限定受入へ進む。


## 2026-10-28 Work：動画内音声の逐次入力→atomic保存→文章検索のCPU基盤

### 入力の所有と時刻

`PreviewReader.video_audio_pcm_stream(id,revision,cancel)`を追加。登録/除外/パス/原本revisionを確認したvideo fdを使い、通常audioと同じ1つのPCM producer slotで所有する。初回と各window/正常EOFでvideo_manifestを再検証し、close/取消/原本・scope変更/異常exitでchild/reader/slotを回収する。raw音声HTTP routeや自動scanは追加しない。

PCMStreamの明示`input_kind='video'`だけが既存videoのdemuxer allowlist/32GiB/max_pixelsを使う。通常audioのformat/512MiBは変更せず、ネットワークやsource pathをFFmpegへ渡さない。先頭音声track `0:a:0`を選び、16kHz/mono/f32leを最大30秒ずつ供給する。`aresample=async=1:first_pts=0`で動画内の音声開始遅延/timestamp gapをsilenceとして保持するが、実audio EOF以降のvideo末尾を推測で埋めない。trackなしをsilenceの成功markerにしない。複数言語trackの選択、音声/映像のrank統合、文字起こしは未実装。

### 保存と検索の明示設定

```python
index = AudioDirectIndex(catalog, audio_encoder, reader=reader, source_kind='video')
revision = reader.video_manifest(video_id)['revision']
index.index_item(video_id, revision)
result = AudioDirectSearch(index).search('覚えている音や会話の特徴', root_ids=[root_id])
```

source_kindはconstructorでaudio/videoだけを受ける固定設定、既定はaudio。video設定ではmanifest/PCM streamをvideo側へ向け、既存の音声atomic stage/source確認/commit・厳密marker/区間/正規化・progress/取消を再利用する。workerの起動/選択は行わず、caller所有の**text/audio** encoderだけを要求する。RGB入力のvideo encoderは受理しない。

音声fileとvideo内PCMは同一text/audio profile/次元/contractの空間で保存する（catalogのglobal item IDで区別）。元videoのkind/タグ/棚/お気に入りを保ち、video設定のqueryはkind=video、通常audio設定はkind=audioの共通scopeだけを検索する。RGB video namespaceとは別のままで、別profile/契約のvectorを混在させない。responseのsource=`video-audio-direct`、行のaudio_match_source=`video-audio`、audio_match_contract=`direct-audio-window:v1`と区間を返す。旧audio類似へvideo設定Indexを誤って渡した場合は拒否し、audio originやUI根拠へ黙って読み替えない。

新schema/DB migrationは不要。既存backup/restoreはPCM namespace内のvideo item行も保持し、root purgeは両audio direct tableを片付け元videoを変更しないことを確認した。検索中の原本変更はAudioSearchChangedとなり、保存前取消は旧公開を保持する。

### 確認と接続の残件

生成Matroskaでvideo3.2秒/先頭audio1秒遅延・audio2.2秒終了を作り、0.5秒のPCMはsilence、1.5秒は有音、decoded PCMはvideo末尾まで伸ばされないことを確認。decodeは1回・fd/pipe限定、原本SHA/mtime/整理metadataは不変。trackなし、旧revision、precancel、slot競合、scope変更、早期close、source容量拒否の回収も確認。通常audioのformat/capが拡張されないこと、reader.start失敗時にも元例外を保ちstdoutをcloseすることを確認した（旧closeの未開始thread.join経路を修正）。

PCM/source/既存video source **25 PASS/2.160s**。動画音声の実decode→疑似encode→保存→query、同一PCM store内でaudio-file/videoの検索非混在・favorite/root/棚scope、取消rollback/原本変更、backup/restore/purgeと既存音声search/similarityは **34 PASS/7.408s**。既存認証HTTPの音声検索/cached類似2件は **PASS/1.335s**。無trackに変わった原本の再生成が旧索引を保ちsilence成功markerを作らない追加1件は **PASS/0.305s**。py_compile成功。重複を合算せず、品質/実model/Windows/.NET/GPU/新配布の確認ではない。

**production job/API/Core/WinUIは未接続**。現在のvideo-aiは映像、audio-aiは音声fileだけのままで、利用者画面からvideo-audioを使える完成機能とはしない。古いCoreが新sourceを誤表示しないよう、既存direct-audio evidenceとは別sourceを明示した。次は同じaudio encoder/inference ownerを一度だけ所有して両media kindの要求を直列化するproduction設計へ接続し、二重worker/二重closeを避ける。trackなし/壊れたdecodeは現時点ではAudioInputUnavailableのため、batch接続では理由分類と読み取れない候補の扱いも必要。続いて専用API/result stamp/Core evidence/動画playerの音声一致seek/WinUI明示入口を接続する。未実装の入口を実装済みと案内せず、namespace・一括favorite・準備時刻進捗と既存残件を維持する。


## 2026-10-28 Work：動画内音声のowned production APIと固定結果

前節の未接続のうちbackendを実装。GET `/api/library/video-audio-ai/status`、POST同prefixの`start/cancel/release/search`を追加し、既存loopback認証・Host/Origin・容量制限・重複JSON/未知field拒否を継承する。startはconsent=trueと通常の共通scope/最大1000件（既定128）。音声file用と同じAudioDirectFeature/Jobs/encoder/inference role/monitorを使い、新worker/owner/DB initを増やさない。Indexのsource-kind viewは既存store/reader/encoderを共有する設定copyでcloseを所有しない。通常音声のAPI/default kindは保全。video専用cancelはvideo実行時だけ受理し、既存audio cancelは共有audio-role jobへ従来どおり適用する。releaseは共有modelに作用する。

未準備videoは登録済みfdの先頭audio trackだけをffprobeで確認する。fd/pipeとvideo allowlist、16KiB出力/10秒/16streams/画素/原本revision/取消/共有PCM slotを制限。trackなしはunavailableへ加え、batch limitを消費せず次のvideoへ進む。全trackなしなら推論0、freshな索引はprobeも不要。probe異常/metadata不正/decode失敗は成功にせずbatch failed、旧索引を保持する。trackなしを永続negative cacheや全無音markerにしない。

固定結果mode `video-audio-direct`は同じ音声stampとscore spool容量予約を使い、profile/保存marker変更時409を返す。文字だけの結果は影響を受けない。scope/kind/source/evidenceは前節どおり、通常audioと混在しない。statusは共有ownerのsource_kindを追加し、Core旧field省略はaudioとして互換保持、video実行中と表示可能にした（未build）。

関連30件は29 PASS/1 FAIL（10.684s）：新testが競合を503と誤期待、既存AIBusyの409を正として修正。修正したHTTP testと追加した全trackなし/専用取消atomic rollback/fresh probe回避・probe異常/cancel/guardを含む **8 PASS/4.765s**。実生成MKV＋疑似encoder＋独立DB/loopbackで確認、同じowner/encoderとclose一回も検証。py_compile成功。重複成功は合算しない。

Core source_kindの表示/parser回帰はsource追加のみで.NET未実行。専用Core client/検索mode/evidence/player seekとWinUI入口は未接続、実model/Windows/native/品質・複数track選択/映像とのrank統合は未受入。映像検索が動画内音声まで検索するという案内には変更しない。
