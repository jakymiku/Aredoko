# R07の次の一点レビュー：長時間producerと保存・検索への接続

2026-10-26。**Astraクラスの設計レビューを推奨**。全ロードマップの作り直しや、新しいフロントエンドの選定は不要。回答後の実装はSol/Antigravityが小区分で進める。

## 確定済みの入力

- [予備評価](audio-input-evaluation.md)：既存固定EG2、生成8本/日英11query/類似2問で全Top1。小規模合成素材の結果であり実録音/実曲/ASR比較は未完。
- [実装済み契約](audio-content-design.md)：検証済みhandleから最大30秒の16kHz mono f32le、取消/原本/登録再確認。text/audio profile・専用key、bounded private worker、完全ゼロだけskip、最大payloadの実CPU pipeも確認済み。
- 本番text/cover profile、legacy索引、既存512D音響保存、通常DBは維持。新workerを自動索引/GUIへは未接続。

## この範囲だけを決める

1. **worker/namespaceの配置**：専用text/audio workerを必要時だけ所有する方式と、将来の全modality profileへの移行を比較する。queryも対応するnamespaceのencoderへ渡す。画像用workerとの同時VRAM・idle release・取消の所有を定義する。768D直接音声を512D音響や既存transcript列へ無条件に格納しない。
2. **長い音声の完了境界**：全PCMを保持せず30秒以下の窓へ分割する。逐次decode/backpressureと時刻根拠、512MiB/24時間上限、所有childのdeadline/取消/回収を決める。反復seekで空窓が得られただけでEOFと判定すると、timestamp gap後の音を落としうる。exact30秒境界/partial tail/無音/破損/不明durationも明示する。
3. **atomic保存と復旧**：1itemの完了後だけ新revisionへ置換し、取消/失敗/解除時は既存索引を保つ。候補0の成功を未処理と区別する。複数namespaceが動く場合のwriter fence・backup snapshot・再起動/restoreとguard順を定義する。
4. **検索への最小接続**：root/棚/favorite/missing等の共通scopeと安定順を維持し、item単位にbest window/時刻を集約する。直接音声には転写文がないため、架空snippetを表示しない。動画/音声プレイヤーへ時刻を渡す。既存結果sessionや文字/視覚順位を壊さない。

## レビュー後の実装単位

1. 生成65秒/正確60秒/途中gapのCPU fixtureで、bounded窓producer・終了/取消を完成させる。
2. 選んだprofile/namespaceへatomic保存し、失敗・無音0候補・source変更・backup fenceをCPUで確認する。
3. 限定検索/時刻根拠へ接続してbuild/関連test。生成音声だけの実GPU一連は、新たに具体的な許可を得てまとめる。
4. 通常設定/GUIへ明示的な導線を追加する。実録音/曲や比較モデルの取得は別の許可・評価とする。

M1の残受入（HC/物理DPI/clean Windows等）とruntime公開review/hostは独立の残件。R07実装開始をM1/M2/全媒体の完成宣言にはしない。P3の全件snapshot待ちの残改善も[current-handoff](current-handoff.md)から継続する。

## 最初の実装単位：逐次PCM producer（2026-10-26）

長時間decodeの部分だけ先行実装。`audio_stream.PCMStream`は検証済みhandleから1所有FFmpeg/1 readerで30秒以下を逐次出力し、queueは1窓、readerの作業1窓、consumerの受取窓でbackpressureをかける。512MiB原本/24時間decoded上限、入力protocol/format制限、10秒のdecoder待ち/30分session、取消・early break・所有回収を維持。全音声のPCMは保持しない。

`aresample=async=1:first_pts=0`でpresentation時刻のgapを無音として維持する。無音/短い窓をEOFと推測せず、全stdout・float整合性・正常exit・最終source guardまで通った場合だけ`complete=True`。窓は暫定であり、consumerはこれより前に既存索引へ公開してはいけない。`PreviewReader.audio_pcm_stream`は原本版・登録・除外を各yield/EOFに再確認し、audio専用slot1つを所有。HTTPへは追加していない。

生成60/65秒、timestamp gapを持つfragmented MP4、非finite/破損/上限、deadline/取消、戻り値ありの非zero終了、入力変更/登録解除/除外、slot解放をCPUで確認。stream12・source18は開発Python3.14/基本Python3.11の両方PASS、既存preview22 PASS。GPU/モデル/通常DB使用0。**worker配置・新namespaceでのatomic保存/backup fence・検索/GUI接続は未実装で、上記レビューの残りを維持する。**

## 次の実装単位：専用namespaceでのatomic保存（2026-10-26）

`AudioDirectIndex`を内部APIとして追加。呼出元が所有するtext/audio encoderを明示し、そのprofile専用sidecarだけに保存する。選択中のtext/coverや旧768D発話snippet/512D音響とは混在させない。30秒固定の逐次入力をprivate SQLiteへstage（最大16MiB/最大2,880窓）。正常EOF後だけcatalog guard→共有writer fenceの順で予約し、最終原本版・登録/除外・取消を確認して1itemのsource markerと時刻vectorを同一transactionで置換する。silent成功0候補はmarkerへ記録し、未処理と区別する。

新しい`ai_audio_direct_sources`/`ai_audio_direct_windows`のあるaudio sidecarだけ`user_version=1`。既存sidecarは0を維持。backup/restoreの既知schemaとversion確認、inactive root purgeの両table削除も同時更新。decode/encoder待ちではwriter fenceを保持せず、途中のlive backupは以前の完了revisionを見る。vectorのstage読出しは64行ずつで、全window vectorのlistを作らない。検索への公開、通常producer job/GUI、音声workerの起動/idle releaseはまだ未接続。

CPU14（開発/基本Python）PASS：失敗・取消・容量不足・原本変更で旧索引保持、silent marker、名前空間拒否、将来版拒否、stage削除、backup待ち取消、encode中backupの旧revision、旧/新sidecar復元、root purge時の原本保持。既存backup29・profile10もPASS。初回はSQLite接続contextがcloseしない解放漏れと、URI無効のprimary接続からのATTACHを検出し、明示close＋専用read-only接続に修正。次の1 FAILは2窓それぞれで同じroot解除を繰り返したfixtureを1回解除に修正したもの。`data/ai-ui/continuation-20261026b/audio-index/`に診断/修正後ログを保持する。供給PCM/人工vectorによる保存試験であり、実GPU音声検索の精度証拠ではない。

## 内部検索APIの接続（2026-10-26）

`AudioDirectSearch`は同じaudio namespaceのencoderで文章queryを作り、`ProductionCatalog.search`のroot/棚/favorite/除外条件を共通利用する。120itemずつ、vectorはcursorで走査し、1itemのbest window/開始・終了時刻をbounded ScoreSpoolへ保存する。cosine同点はitem ID順、window同点は最初のordinal。追加範囲取得のために再encode/再rankしないresult sinkにも対応する。

各itemの原本版を検証し、登録状態・catalog generation・audio store data_versionが途中変更されたら古い結果を破棄する。結果は`audio_match_ms`/`audio_match_end_ms`/`audio_match_source=direct-audio`で返し、転写していないsnippetを作らない。既存ResultSessions＋IndexStampにも接続でき、音声索引更新時の失効を確認した。通常server/WinUIの検索入口、音声同士の類似、owned workerの設定/idle releaseはまだ未接続。

CPU8（開発は既存7＋追加1、基本Pythonは8）PASS。範囲の継承、1queryから複数range、安定tie、stale/empty/取消、索引途中変更、時刻付きsession保持と更新後失効を確認。供給vectorによる契約試験であり、音声理解の品質評価ではない。

## 所有ジョブとモデル切替の内部基盤（2026-10-26）

`AudioDirectJobs`は明示したaudio encoderを所有し、共通scopeのmissing/fresh判定→既定128件（最大1,000件）のbatch→atomic item保存を行う。次batchはfresh項目を飛ばすため、同じ先頭batchだけを反復しない。件数・対象外/未処理候補・取消/範囲変更を返す。途中の完了itemは保持し、現在のitemは失敗/取消/選択scope変更で公開しない。進捗はbackend lifetime内、再起動後はitem markerで明示batchを再開する。

`InferenceOwnership`はimage/audioの2所有者に限定したlock。明示的に両方へ接続した場合、別ownerのresident workerを解放した後にだけ次を許可する。busy/解放失敗時に同時loadを許可しない。idle release/正常closeも所有範囲で行う。**この段階では通常のproduction handler/WinUIへ未接続**であり、通常アプリが音声用workerを勝手に起動する変更ではない。

所有ジョブ8・所有切替7は開発/基本PythonともPASS。scopeの最終publication validatorも追加1 PASS。待機取消、fresh skip/次batch、未完item保持、scope変更、query busy、切替、idle release、所有closeを人工encoderで確認した。既存実GPU評価の許可は再利用せず、今回の新しい生成2音声pipeline試験は個別回答待ち。

## production APIと実pipelineの限定確認（2026-10-26）

`AudioDirectFeature`をlazyな入口としてhandlerへ接続。status取得だけではaudio DB/workerを作らない。認証済みの`GET audio-ai/status`、明示consent付き`POST audio-ai/start`、cancel/release/searchを追加し、未知field/重複JSONを拒否する。既存AISearchとaudio ownerは同じ所有lockを使う。音声を使わなければ通常のprofile/索引動作を維持する。音声ownerのcloseは画像jobの全batch終了を待たず、音声用の所有encoderだけを停止する。

共通結果sessionの`mode=audio-direct`を追加。条件別のindex stampで音声索引の更新は音声sessionだけを失効させ、文字一覧を無関係に失効させない。score spoolの256MiB予約も行う。resource設定のidle秒をaudio ownerへ継承する。**この時点のWinUI入口は未接続**。

HTTP5（開発4＋修正後対象1、基本Python5）、既存result34/release11/production8 PASS。HTTPの1 FAILはrangeの必須offset/limitをfixtureが省略して400になったものを修正。終了時の画像owner待ちを避ける修正は対象1 PASS。証拠は既存audio-indexディレクトリ。

個別許可後、`check_direct_audio_pipeline.py --gpu`を生成001/002の2音声・日本語2問で1回実施。既存固定EG2のaudio-only adapter→逐次PCM→専用DB atomic保存→時刻付き検索が通り、2問ともTop1。load32.718s、index1.875/0.485s、PyTorch peak allocated1,175,973,888/reserved1,199,570,944bytes（driver/native除く）。3GiB空き条件・allocator約3GiB上限、元生成SHA/mtime不変、終了exit0、追加取得/GUI/通常DB/Alpha変更0。証拠`data/ai-ui/continuation-20261026b/audio-pipeline-gpu01`。実worker processでのGPU一連・長時間・録音/曲・一般品質を証明するものではなく、許可は消費済み。

## WinUI入口の追加（2026-10-26）

既存の検索方法indicesを維持して7へ「音声の内容（AI）」を追加。種類を音声・音楽へ揃え、文字/画像向けのAI scopeやRRF/文字全語一致条件を音声へ流用しない。フォルダ・棚・お気に入りは共通条件で維持する。右詳細・プレイヤーには既存の一致開始時刻を渡し、直接音声の根拠は「発話」ではなく「音声の内容一致」と表示する。

AI準備のscroll領域へ折りたたみ式`AudioPreparationPanel`を追加。展開時のstatusだけではmodel/DBを起動しない。現在の検索フォルダ/棚を対象に、明示作成・中断・進捗・続きのbatchを操作できる。dialogを閉じるとpollだけを終了し、所有jobは続行する。遅いstatus応答が新しいcommandを上書きしない世代と取消を持つ。本文の作業領域は変更しない。

Core全体PASS（旧「7は無効」の試験を新しい境界8へ更新）、Portable build PASS。新しいIL2026はJsonValueの明示生成へ修正済み。既存WUI1001 picker警告3のみ。WinUI reviewで色/配置/bindingの追加差分、所有timer/取消、アクセス名・操作経路を確認。GUI受入は新候補を作成後、個別質問してから実施する。silent成功を未索引と誤表示しないfresh数も追加し、関連CPU検索9/HTTP response1 PASS。


## 限定nativeの結果と配布候補（2026-10-26）

frontend01/native01は準備・中断・再開・2item保存を確認後、検索方法popupの重複UIA optionで停止。frontend02/sourcecaee977/native02は展開時StartBringIntoViewによりbody/操作が見えることと同じ準備flowを確認し、popup展開後にcomboのfocus provider取得が失敗して停止した。実キーは未送信。両方exit0/所有process回収、PNGを目視し、**検索方法切替・結果の時刻表示は未検証**。2回目を総合PASSとしない。

harnessはpopupを開く前にfocusを与えるよう修正。`--audio-search-only`で生成2WAVを供給CPU encoderで事前索引化し、成功済みの準備flowを反復せず検索入口だけ確認できる。構文確認のみ、新たなGUI試行には別の回答が必要。証拠`data/ai-ui/continuation-20261026b/audio-native01`/`audio-native02`。

基本ZIP07（sourcecaee977、806files/661,173,728bytes）はfrontend02を収録。全manifest/ZIP照合と同梱Pythonによる基本CPU23・owned EOF exit0 PASS。通常EXE入口GUI/clean Windowsは未検証。生成2音声GPU成功を実private worker/実録音/音楽/音声類似の一般品質合格へ拡張しない。


## 音声検索GUIの残確認（2026-10-27）

同じfrontend02/sourcecaee977で個別許可を得た2試行。audio-search01はmode切替と時刻付き結果まで表示したが、debounceによる一覧差替え中に旧SelectionItemPatternを操作してharness停止（正常exit0）。明示検索・AIEvidence待ち・所有画面の実クリックへ修正後、audio-search02は9checks/2PNG目視/正常exit0/原生成SHA・mtime不変でPASS。検索方法が音声へ固定され、2候補・内容一致0:00・明示詳細・音声を再生ボタンを確認した。実際の再生は行わず、CPU供給vectorのGUI接続検証である。成功済み準備flowは反復していない。

目視で詳細に旧「音声内容の自動索引は未対応」が残ることを発見。実装済みの設定→AI検索の準備→音声の内容検索へ案内を修正し、音響類似と文章内容検索の索引を混同しない説明へ分離。Core runner/Portable build PASS、既存WUI1001警告3。旧案内を期待したCore2箇所とMSIX Before hook指定による開発build失敗は修正前ログを保持。証拠`data/ai-ui/continuation-20261027/`。案内文修正後の別GUIは未実施。


## 実private workerの限定確認（2026-10-27）

`EncoderProcess`へ任意の明示GPU allocator予算を追加。未指定の通常動作は維持し、設定された音声ownerへ継承する。workerはmodel load前に空き容量とbudgetを確認し、CUDAがない/空き不足ではloadしない。driver/native allocationまでの絶対VRAM上限ではない。CPU契約14件は開発/基本Python双方PASS、既存HTTP5もPASS。

個別回答後、既存生成001/002の2音声だけで `check_direct_audio_pipeline.py --gpu --owned-worker` を1回実行。実production owner→検証済み原本decode→実private audio worker→atomic保存→日本語2問が全Top1。index全体16.156s、child PyTorch peak1121.5MiB、allocator上限3072MiB、画像workerは起動せず。owner.closeでworker停止を確認（既存の所有kill終了方式なのでexit1、graceful終了とは呼ばない）。原生成SHA/mtime不変、追加取得/GUI/再生/通常DB変更0。証拠`data/ai-ui/continuation-20261027/audio-owned-gpu01`。実録音/実曲/音声類似の一般品質や配布先Windowsを証明しない。


## 直接音声ベクトル同士の類似検索backend（2026-10-27）

`AudioDirectSimilarity`は別namespaceの768D direct-audio windowだけを比較し、起点自身を除外、全window pairの最大cosineと起点/候補双方の開始・終了時刻を返す。512D音響/画像/文字vectorを混ぜず、推論やPCM再decodeを行わない。起点はroot/棚/除外を守り、候補だけfavorite viewを適用する。保持は2itemのframe集合各32MiB以内＋120metadataと既存score spool。超過時は結果を黙って切らずエラー。全pair比較なので長音声の処理時間改善は今後の課題。

所有audio jobへcached queryを接続。モデル未配置でも既知profileの保存済みvectorから比較可能。`POST audio-ai/similar`と`mode=audio-similar`のfrozen result sessionへ認証/厳密field確認/独自stampを適用。原本・登録/除外・namespace更新・取消を検証し、起点変更後もsessionを失効させる。GUI入口はこの段階では未接続。

新規CPU7（開発/基本Python）＋追加stamp1、HTTP6 PASS。既存spoolの取消済みcontext入場時の解放漏れを検出し、`__enter__`失敗時もcloseするよう修正・focused1 PASS。初回ログは保持。供給vectorによる契約確認であり、実音楽の類似品質評価ではない。


## WinUIの直接音声類似入口（2026-10-27）

音声の右クリックへ「内容が似た音声・曲を探す」を追加。既存の音響特徴ルートは維持。新入口は`audio-similar`として通常のroot/棚/favorite条件を保持し、視覚AI scope・runtime整合性確認・モデルloadを要求しない。起点と候補の両時刻をstrict Core parserで検証し、sourceがlegacyと混ざる応答を拒否する。画面履歴にdirect/legacyの別を保持して戻る/進むを復元する。

Core runner/Portable publish PASS。Coreにはroots変数のshadowによる初回compile失敗を保持しaudioRootsへ修正済み。既存WUI1001 picker3とSDK由来IL2104を維持。result sessionの256MiB ranking予約も追加、focused capacity1 PASS。新候補`data/ai-ui/continuation-20261027/frontend01`へreceipt作成済み。GUIは個別質問への回答後、専用生成WAV/CPU供給vector・モデル利用不可の条件で右クリック/両時刻/詳細/画面履歴だけ確認する。音楽の意味品質はこの接続では評価しない。
