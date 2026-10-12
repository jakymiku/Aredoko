# Aredoko — GPTチャットへの最新引継ぎ

更新: 2026-10-12。旧Web試作段階の引継ぎを置き換える。**製品GUIはWinUI 3に決定済みで、EmbeddingGemma 2検索まで実装・実GPU検証済み。最初から作り直さない。**


## 最新の再開地点（2026-10-12・GUI完走／実GPU測定中）

開始HEAD **a4690a1**。同じfeature/Draft PR #5/baseを保持。通常GUIテスト許可は継続、専用DB/settings/生成17素材と既存EG2のみ。

**appearance-09は操作 105 recorded checks PASS / 全17 PNG目視PASS。** Light/Dark双方の実CUDA日本語検索と上限表示、cover非対応の実エラー/文字検索復帰、dirty keep、roots、missing model案内、favorite/native再起動を完走。6正常終了/cleanup warningなし、source hashes全一致。full profile chooserバッチの再実行ではなくeditor/appearance/coverage sliceであり、別checkpoint・HC・高DPI・実ライブラリの証明ではない。

07はDark clickのforeground安全拒否でFAIL（13 PNG全目視、4正常終了+1fallback warning）。所有HWNDへのscoped focusを追加。08は直接API queryをGUI初回lazy queryと競合させてFAIL（14 PNG全目視、5正常終了/warningなし）。GUIの成功Message/項目/件数を待ってから直接API queryするよう修正。07→08→09の2回fix/rerunで終了、過去FAILを変更しない。新規XAML/C#/依存/モデル/個人設定/OS変更なし。

Darkのindex_states/coverage_gpu_statesは別時点で、短時間のcached rebuild開始とcompleteが非同期に入れ替わる（09は後者processed=0）。このsnapshotをcached jobの厳密な開始/終了時刻や推論ゼロの証明に使わない。GUI結果の表示と実CUDA queryは完了確認済み。厳密なcache再利用と処理数は後続専用GPU測定で確認する。

Python103 tests PASS（81.92秒）、C#15 checks PASS、WinUI x64 SelfContained Release PASS（37.04秒/既存IL2104 2警告）。WinUI code reviewはnative Items/60 paging、async/stale/dirty、テーマ/AutomationId、DOM JSON、認証/所有worker/profile identity保持を確認。analyzer未導入。

現在は生成素材だけの実EG2負荷を段階測定中。新規取得なし。CPU1万件synthetic/実GPU17件を作り直さず、GPU測定結果を末尾へ記録する。次の3手: (1) 段階GPU測定のcache/所有worker全体メモリ/終了を確認、(2) 1万件への段階拡張と資源設定、(3) 明示指定の小実サンプル品質評価。私物/1TB/HC/高DPI/reader/Komga/AOT/配布は未検証・未実装の範囲を維持。Layaは実験APIのみ。

## 前段階の再開地点（2026-10-12・通常GUI再開）

開始HEAD **8a62492**。同じfeature/Draft PR #5/baseを保持。実装/検証記録HEAD **5ac973b**。後続は提出文書のみで、最新HEADは実Gitを確認。

**ユーザーが通常のGUIテストを許可し、ゲーム前面維持の制約を解除した。** Sandboxはdisabledなのでlocal target、専用DB/settings/生成17素材。OS/私物/個人設定/依存/重みの変更・取得なし。

AI dialogはmodel設定だけscrollし、索引status/start/cancelを固定行へ。roots scrollも開いた時のwindow高に応じて制限。明暗AI dialogと最大10,000/ボタンbounds、Light dirty/rootsと17件実CUDA日本語検索の上限文を実確認。

**最新appearance-06全体はFAIL。75 successful checks/13 PNG全目視で撮影状態のvisualはPASSだが、Dark fresh cacheの再索引でもcuda deviceを要求したテスト条件で停止。** diskの17 current vector revision/complete17とDarkのmodel loadなしをread-only確認。これはnative全体成功ではない。fresh reuse時のみcudaをbuild条件から外し後の実queryでassertする修正、index state記録を追加。最後はsyntax/helpまででnative未再実行。Dark semantic/追加dirty/roots/missing段階が未到達。04→05→06の2回fix/rerun上限を守り、新依頼の最初に修正後を再確認する。

    python tools/test_ai_profile_ui.py --editor-only --appearance-checks --coverage-checks --output data/ai-ui/appearance-07

新規outputを使う。--coverage-checksはeditor-onlyの例外で既存EG2 text-only/float32/768を実GPUで17件使い、全profile切替を意味しない。06は4正常終了＋1owned PID fallback warning、04にもwarning。所有GUI/API/worker残留なし、sourcehash一致、生成profile cleanup。旧appearance-03 visual FAILと04/05/06全体FAILを消さない。

最終Python **103 tests PASS**、C# **15 checks PASS**、最終WinUI x64 SelfContained Release PASS（既存IL2104 2警告）、syntax/help/diff PASS。analyzer未導入。GUI通しFAILとこれらの成功を区別する。

次の3手: (1) 上記でcache条件と未到達nativeを全PNG込みで確認、(2) 生成素材で実EG2の段階的な負荷/メモリ測定、(3) 10,000超の対象/資源設定と明示小実サンプル品質評価。実GPU1万件/HC/高DPI/reader/AOT/配布/1TBは未確認。Layaは実験APIのみ。詳細はui-polish.md/codex-handoff.md最新節。

## 前段階の再開地点（ゲーム中のバックグラウンド検証）

開始HEAD **1f77172**。同じfeature/Draft PR #5/baseを維持。実装/検証記録HEAD **5be9b88**。後続は提出文書のみで、最新HEADは実Gitで確認。

**ユーザーは別窓でゲーム中で、アクティブwindowを変えないテストを希望。** 今回はnative GUI起動/Activate/入力/OS設定変更を行わず、Hidden/BelowNormalのCPU検証とbuildだけを実行。GPU/新規download/私物走査はなし。この希望が続く間は前景が必要なharnessを実行しない。

AI対象をeligible **10,000件**まで拡張。256件keyset metadata、build IDリスト固定、現行除外/revision再確認、16件進捗checkpoint、候補IDだけのvector取得、全batchをまとめたglobal mean-rrfを実装。GUIはAPI上限を表示し既定値を使い、明示2,000件指定/旧モデルidentity/cache/手動filter/60件pagingを保持。検索metadata/scoreは最大10,000件保持し、全数万件/1TB/constant-memory対応ではない。

生成10,010ファイルのうち10,000件、768次元synthetic text vector、**14 checks PASS**。2,300件cancel後の再起動で残り7,700件だけ生成、末尾top1/paging/filter、次の再起動でdocument encode 0、全source bytes/size/mtime不変。actual_model=false/gpu_used=false/native_gui_run=false。[index-scaling.md](index-scaling.md)に単発時間/peak working setと限界を記録。

**前回appearance-03はUIA68 PASS / visual FAILを保持。** 全3dialogのRequestedTheme修正、新しい1万件のGUI文はbuild/reviewまででnative未再実行。ゲーム終了等で前面操作が可能なとき、新規outputへ `--editor-only --appearance-checks` を実行し全PNGを見て確認する。実GPUの大規模評価、HC/高DPI/reader/AOT/配布/1TBも未確認。Layaは精度未達の実験APIのみ。

最終Python **103 tests PASS**、C# **15 checks PASS**、WinUI x64 SelfContained Release PASS（既存IL2104 2警告）。WinUI review済み、analyzer未導入。

次の3手: (1) 前面操作可能ならLight/Dark dialogと新上限表示のnative確認、(2) GPUを使ってよい時に生成素材で実EG2の段階的なメモリ/負荷測定、(3) 10,000件超の対象選択/資源設定を設計し、明示指定の小実サンプルで品質評価。未指定の私物は走査しない。

## 前段階の再開地点（テーマとAIエラー復帰）

開始HEAD 988d55e。同じfeature/Draft PR #5/base、チャット側f4273ffとモデル/旧索引互換を保持。実装/検証記録HEADは8418d68。後続は提出文書で、最新HEADは実際のGitを確認すること。

開発起動の `-UITheme System|Light|Dark` を追加した。Windows全体の設定を変えず、アプリのrootだけへ適用する。既定Systemで通常のテーマ追従を維持し、保存設定は追加しない。WinUIのOnLaunched.Argumentsは非対応なので、実プロセスのcommand-line argumentsから限定した値だけを読む。

**native appearance-03はUIA 68 checks PASS、視覚レビューはFAIL。** 生成17素材/専用DB/settingsで、文字専用profileの実cover非対応エラーをLight/Dark両方、missing profileの実意味検索エラーをLightで再現。中央の具体的案内、古い件数/ページの消去、前後ボタン無効、名前・タグへの復帰/1件の実作品表示/InfoBar成功文まで確認した。favorite保存/dirty keep/native再起動も再確認。9 PNGを全目視し6回正常終了/cleanup warningなし/元ファイルhash不変。

目視でLight画面のAI dialogだけDarkになる不一致を発見し、全3 ContentDialog（未保存確認/フォルダ管理/AI設定）に `RequestedTheme=ActualTheme` を追加した。**最後の表示修正はRelease build/code reviewまでで、native未再実行。** winui-ui-testing skillの最大2回fix/rerunへ達したため、残件として記録。68項目のUIA成功をテーマ完了と扱わない。ignored visual-review.jsonはvisual_pass=false。

appearance-01は候補のUIA二重公開でFAIL、02はInfoBar本体に存在しない値を待ってFAIL（実復帰は画面/子Title・Messageに表示）。候補を所有PopupHost HWNDへ限定し、成功判定を実子テキストへ修正して03のUIAはPASS。01の環境変数、02のOnLaunched.Argumentsはテーマ指定が届かず、03でプロセス引数のLight/Dark本体表示を実確認した。過去failureを消さない。

Python96/C#13/WinUI x64 SelfContained Release PASS（既存IL2104 2件）。actual_model=false/profile_verification=not_run、AI推論/重み取得なし。モデルcapabilityチェックは推論前に失敗する実APIで、CUDA索引/品質の再検証ではない。実DPIは96/HighContrast=false、OS設定変更なし。高DPI/HC/reader/配布/1TBは未確認。私物/個人AppData設定は変更せず、既存のアプリ診断ログは使用した。所有test GUI/API/workerなし、生成profileのみcleanup。

**次の3手:** ① `--editor-only --appearance-checks` を新規outputへ実行しLight/Dark dialogの修正後実画面を最優先確認、②2,000件超をcheckpoint/増分/resource上限込みで段階拡張し生成大規模集合で測定、③明示実サンプル評価と用意された高DPI/Contrast環境での確認。私物サンプル未指定時は生成素材。Layaは実験APIのみ。詳細はdocs/ui-polish.md、docs/codex-handoff.md末尾。同じDraft PR #5/baseを維持。

## そのままチャットへ貼る依頼文

```text
Aredokoの開発を現在の実装から引き継いでください。
リポジトリ: https://github.com/jakymiku/Aredoko （非公開）
作業ブランチ: feat/winui3-production-mvp-20261011
最新引継ぎ: https://github.com/jakymiku/Aredoko/blob/feat/winui3-production-mvp-20261011/docs/chat-handoff.md
Draft PR: https://github.com/jakymiku/Aredoko/pull/5

まず、このブランチのAGENTS.md、docs/chat-handoff.md、docs/codex-handoff.mdの最新節、Issue #4、PR #5を確認してください。mainや古いWeb試作の状態を現状と混同しないでください。
WinUI 3製品MVP、EmbeddingGemma 2の曖昧検索、交換可能なモデルprofile、混合順位改善は実装済みです。Layaは精度不足のため明示実験APIだけで、GUIの自動切替や種類絞込みには使っていません。
AI対象10,000件、256件取得・16件進捗保存・旧cache/global fusionを保持し、CPU生成1万件cancel/restart/searchは確認済みです。通常GUIテストを許可された最新作業は、固定index actionsと明暗AI dialog、Lightの3dialog/17件CUDA検索/10,000表示まで確認。ただしappearance-06全体はDark fresh cacheにもcudaを要求したテスト条件でFAILです。最後の条件修正はnative未再実行なので、まず --editor-only --appearance-checks --coverage-checks を新規outputへ実行し全PNGを見て未到達Dark/missingまで確認してください。過去visual/通しFAILを消さず、実GPU大規模/高DPI/HC/1TBを未確認と区別してください。OS設定/私物を勝手に変更せず、起動時profile/旧索引互換/hot swapなし/自動DLなしを保持してください。
既存資産・手動検索・タグ保存を維持し、実装できる環境なら必要なテスト、コミット、同じDraft PRの更新まで進め、進捗を引継ぎへ記録してください。直接編集やWindows実行ができない場合は、実コードに対応した変更ファイルか適用可能な差分と、PCで実行する検証手順を返してください。未実行のテストを成功と報告しないでください。
非公開リポジトリを読めない場合はアクセスできないと明記し、ユーザーが共有するこのブランチのソースを使ってください。仕様だけから実装済みコードを想像して書き直さないでください。
```

## 現在のGit状態

- 今回の開始HEADは `8a62492`、実装/検証記録HEADは `5ac973b`。後続は提出文書のみで最新HEADは実Gitを確認すること。前段階の索引拡張は `5be9b88`、テーマ修正は `8418d68`。
- HEADブランチ: `feat/winui3-production-mvp-20261011`。
- Draft PR [#5](https://github.com/jakymiku/Aredoko/pull/5)、base `feat/gui-framework-comparison-20261010`。未マージ。PR #1/#2/#3も保持し、mainへmerge・force-push・squashしない。
- 引継ぎ開始時点はclean、機能作業の未コミット残りなし。テスト用API/GUI/GPU workerは停止済み。
- 元PCのプロジェクトはユーザー指定の `C:\AI\Aredoko`。別チャットの実行環境へこのフォルダ、localhost、GPU、venv、モデルが自動で移る前提にしない。
- 非公開GitHubの閲覧可否と、コード編集・push可否は実際の利用環境で確認する。読めない場合はブランチのコードZIP等をユーザーから受け取る。venv/models/DB/私物をZIPへ含めない。

## ユーザーの目的・決定

指定した複数フォルダの画像・動画・音楽・素材・購入同人誌を、曖昧な文章で探し、タグ/仮想棚で整理するWindows GUIアプリ「あれどこ / Aredoko」。数万ファイル・1TB以上が将来の対象。PCはCore i7-13700K、RAM32GB、RTX4070Ti 12GB。

画像フォルダ・ZIP・CBZが混在、PDFは少数。Komgaは読む時に起動する。将来の読書/Komga検索補完は希望だが未実装。ツール/OSS検索は別企画。ダウンロードフォルダ限定ではなく、ユーザーが明示選択したフォルダを使う。元ファイルの移動・変換を強制せず、タグ等をアプリDBへ保存する。移動後の追跡は未実装。

ユーザーは後発の互換モデル（非検閲モデル等）へ交換しやすい構造を希望。任意のモデルが無条件に互換という意味ではない。アプリに検索内容の拒否処理は追加していない。「下着のデザインテンプレート」は架空PSDの名前/タグ入力から1位で検索できたが、実PSD内部や私物精度の検証ではない。

## 実装済み

| 範囲 | 現状 |
| --- | --- |
| 製品GUI | 独立したWinUI 3/C#アプリ。登録同意→read-only走査→一覧/検索→タグ・棚・お気に入り・確認済み保存。60件paging、詳細pane、未保存確認、async stale検索対策 |
| プレビュー | 画像、CBZ/ZIPの先頭画像。サイズ/画素/並行処理を制限、archiveを展開しない |
| 通常検索 | Python stdlib + SQLite APIによる名前・タグ検索。AI不足/失敗でも独立して利用可能 |
| AI検索 | ローカルEmbeddingGemma 2/CUDA。名前/タグtextと画像/表紙coverを別vector保存。AI索引dialog、意味検索、画像・表紙検索 |
| 索引 | eligible上限10,000件。256件metadata/vector取得、16件進捗保存、増分/cancel/restart、除外/manual filter/旧cache互換。CPU生成1万件PASS、実GPU大規模/全数万件は未完 |
| モデル交換 | 検証済みJSON profile +登録adapter、起動時-AIProfile。vector-space identityごとに索引分離、旧default互換。text-only adapterは契約実装済み、別重み未検証 |
| 混合順位 | AI意味検索の既定mean-rrf。k60、cosine同点平均順位、利用可能modality平均。maxへrollback可、明示text/coverはcosine。再索引不要 |
| Laya | 固定0.4.2/多言語重み、owned offline worker、独立suggestion API。起動既定無効、-LayaIntentで明示有効。hybrid質問＋順序棄権。GUI採用保留 |
| 過去資産 | Webデモ、read-only索引試作、GUI比較アプリを保持。製品とは区別 |

## 検証済みの範囲と限界（順位改善時点の履歴・最新結果は上記）

- 最新実装でPython **90 tests PASS**、C# **13 checks PASS**、WinUI Release build PASS。旧SDK IL2104警告2件は未解消・抑制していない。
- 実EmbeddingGemma CUDA、生成23素材/28条件: 期待top1 **25→27**、期待順位悪化0。赤表紙2→1、青表紙1維持。新validation16条件は15→15で、改善2件は既知development条件。個人ライブラリの性能保証ではない。
- 最新WinUI実機local生成17素材: 登録/走査/CUDA索引/意味検索/タグ保存/dirty keep/文字復帰/赤表紙融合/max復帰/青coverタイルPASS。4枚目視確認、sourcehash不変。
- 過去段階でGUI restart保存・vector再利用、旧索引互換、profile切替もPASS。最新順位更新でrestartは再実行していない。
- Laya development32で選定後、新held-out24を評価: hybrid effective intent17/24、kind15/24（v1 kind12/24）、各head6件棄権。warm中央値81.53ms、cold12.94秒。精度不足なのでGUI提案/自動mode/filterを追加しない。
- 新Laya HTTP契約・cold中literal・busy fallback・timeout・親終了でrealworker停止PASS。Windows venv redirectorと実Pythonを区別し、ownerと即時親の両方を監視する。
- 旧held-out12と新24はいずれも評価済み。今後調整するなら別の未見集合を先に作る。確率や類似度をconfidence/正解率とみなさない。
- Sandbox/WinUI analyzerなし。高DPI/Light/HighContrast/reader/ピッカー全体/AOT/配布未検証。CPU/量子化/idle unload、1TB throughput、実私物精度も未検証。
- 本文/OCR、PDF内部、音声/動画内容、PSD/SVG等の内部は未解析。関連表示、読書ビューア、Komga、画像フォルダを一冊にまとめる処理、移動追跡、複数棚は未完。

## GUIモデルprofile選択の実装計画（実装済み・当時の履歴）

1. [model-profiles.md](model-profiles.md) と既存launcher/API/dialogコードを読み、設定をGUIから選ぶ最小経路を設計する。既定profileへ戻す操作、現モデル/対応入力の表示、無効JSON/重み不足の案内を含める。
2. 選んだ設定はまず次回起動に適用。進行中の検索/索引・未保存タグの調停を維持する。既存-AIProfile引数との優先順位と設定保存先を明記し、選択だけでDL/依存導入しない。JSONをアプリ設定として扱い、任意Pythonコードやremote codeを許可しない。
3. 設定と既存vector identityを共通実装で扱い、GUI側に別の互換性判定を作らない。別profile索引・旧default復帰・text-only画像検索案内・invalid/missingでもliteralを維持する回帰を確認する。
4. 対応環境でPython/C#/Releaseと生成素材GUIフローを検証、コミット、同じDraft PR更新、引継ぎを記録。実GPU重みがない環境ではmock契約と実モデル検証を区別する。

その次は、ユーザー選択の実サンプルで順位を評価し、2,000件超をcheckpoint/増分・resource上限で拡張する。実サンプル指定がない間は生成素材で進める。

## 守るべき実装上の境界

- AGENTS.mdを優先し、既存資産を削除/再scaffoldしない。特に `experiments/gui-compare/winui3/generated` を触って作り直さない。
- ソースの移動/削除/rename/reencode/archive展開なし。私物走査は明示フォルダ選択後のみ。モデル/DB/cache/venv/個人paths/credentialsをGitへ含めない。
- APIはloopback/token/Originを維持。torch等はowned workerへ隔離、stdlib catalogを重くしない。通常検索fallback、同時数/出力/timeout制限を維持する。
- .NET Releaseでreflection JSONが無効なためJsonDocument/JsonNode/Utf8JsonWriter経路を保つ。過去のWinRT/ComWrappers crashを起こしたmanaged ListView.ItemsSourceへ安易に戻さず、現在のnative Items/60pagingを維持する。
- AI index identityをmodel ID/revision/dimension/modalities/prompts/precision/preprocessingから分離しない。未保存編集・async選択競合・stale search対策を崩さない。
- 新しいcheckpoint、package、OS変更は今回の文書引継ぎの範囲外。過去にEG2と固定Layaの取得は承認済み、今後の新規取得は必要性/対象を確認。全DL合計 **6,000,000bytes/s以下** を維持する。

## コード・資料の入口

- 詳細履歴: [codex-handoff.md](codex-handoff.md) の末尾。仕様: [winui-mvp.md](winui-mvp.md)、[model-profiles.md](model-profiles.md)、[ai-ranking.md](ai-ranking.md)、[laya-evaluation.md](laya-evaluation.md)。旧README/spec/statusの時点が古い場合は最新コードと本資料を優先。
- WinUI: `src/Aredoko.WinUI/MainPage.xaml`, `MainPage.xaml.cs`, `MainWindow.xaml.cs`。共通C#: `src/Aredoko.Core/LibraryApi.cs`, `Protocol.cs`。
- API/catalog: `app/production_server.py`, `production.py`, `library_index.py`。launcher: `tools/start-winui.ps1`。
- embedding: `app/ai_profiles.py`, `ai_adapters.py`, `ai_process.py`, `ai_worker.py`, `ai_search.py`, `ai_ranking.py`、`config/ai-profiles/embeddinggemma-2.json`。
- Laya: `app/search_intent.py`, `intent_questions.py`, `laya_config.py`, `laya_process.py`, `laya_worker.py`。検証定義: `tests/fixtures/laya-ja-v2.json`。

## 起動・検証コマンド（repo root）

```powershell
python -m unittest discover -s tests -q
dotnet run --project tests/Aredoko.Core.Tests -c Release
dotnet build src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Release -p:Platform=x64
pwsh -File tools/start-winui.ps1 -Database data/chat-test/catalog.sqlite
# 既存local JSON profileで起動（不足時もダウンロードしない）
pwsh -File tools/start-winui.ps1 -Database data/chat-test/catalog.sqlite -AIProfile data/ai-profiles/custom.json
# 旧順位へ戻す
pwsh -File tools/start-winui.ps1 -Database data/chat-test/catalog.sqlite -AIRanking max
```

元PCのGPU用 `.venv-ai` と `models` はGit対象外。別環境にあるとは限らない。実GPUテストの新outputは既存証拠と重ならないignoredディレクトリを指定する。`tools/evaluate_ranking.py`, `evaluate_intent_v2.py`, `test_laya_api.py`, `test-ai-ui-local.ps1` の引数/生成素材条件を読んでから使う。元PCの `data/ai-smoke/ranking-01`, `data/ai-ui/ranking-01`, `data/laya-evaluation/v2-heldout-01` 等はローカル証拠でGitHubに実体はない。

## スキルの扱い

元PCにはHallmark、Web Design Guidelines、WinUI setup/design/dev-workflow/code-review/ui-testing/packaging等を導入済み。スキル本体が別GPTチャットへ自動で渡る前提にしない。利用可能なら対応するSKILL.mdを読んで適用する。ない場合も上記の検証・安全境界・Fluent/アクセシビリティ・async/dirty制御を守り、正式スキル監査を実施したと報告しない。XAML変更時はWinUI design、ビルド後commit前はcode-review、実機検証はui-testingが対応する。

この引継ぎだけでソース読取は代替できない。アクセスできるコードと実行環境を確認してから、次の実装を始めること。

## 開発追記：WinUI GUIモデルprofile選択（2026-10-12）

**今回実装した変更**（最終の実機検証は別途必要）:
- `app/ai_settings.py`: 既定profileと `data/ai-profiles/*.json` のローカル候補一覧、JSONとモデルidentityの既存検証、`.venv-ai` /重みフォルダ/ revision markerの欠落・不一致診断、設定ファイルの原子的保存。`%LOCALAPPDATA%/Aredoko/settings.json` はGit管理対象外。モデル/索引実体は変えず、選択を**次回起動から**適用。既定へ復帰できる。候補のprofileは任意Python import/remote code不可、自動DLなし。
- `app/production_server.py`: トークン保護 `GET /api/library/ai/profiles` と Origin+トークン保護 `POST /api/library/ai/profile`（IDだけ受理）を追加。起動時は **明示 `-AIProfile` > GUI保存 > 既定**。保存設定が破損しても引数優先。選んだprofileが消失・無効ならoptional AIを停止して通常文字検索を維持。ローカル確認用`--ai-settings`を追加。
- `src/Aredoko.WinUI/MainPage.xaml.cs`: 既存「AI索引」ダイアログにprofile候補、対応入力（文字/表紙）、不足・無効警告、次回起動用の保存ボタン、起動引数優先・再起動必要のメッセージを追加。作業中のworkerはhot swapしない。text-only時のcover非対応は従来のbackend契約を維持。
- `tests/test_ai_settings.py`: 一時フォルダ・一時SQLite・疑似HTTPでプロファイル復帰、保存設定と起動引数の優先、不正パス/壊れたJSON、重み・リビジョン不足、APIのOrigin/token保護、文字検索維持を検査。`.github/workflows/ai-profile-checks.yml`でWindows Python/C#とWinUI Releaseを検証。

**現在の境界**:
- GUIの実機クリック操作、再起動後の実GPU worker起動、別重みの精度/互換性はこの環境から実行できず**未検証**。CI上のWinUI Release成功もGUI実機動作保証ではない。
- Layaは今回一切変更せず、明示実験APIのみ。既存のmean-rrf/再索引分離/旧default互換を維持。
- 実行は `pwsh -File tools/start-winui.ps1` →「AI索引」→候補選択→「次回起動に設定」→アプリ終了→同じコマンドで再起動。すでに `-AIProfile` を渡す場合はそれが優先する。
- Codexへの次の指示: (1) Windows実機でdefault/custom/text-only/不足時の画面と再起動切替、(2) GUIに表示される警告の読みやすさ/高DPIを確認、(3) 完了後は実サンプル精度と2,000件超索引へ進む。
