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
