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
