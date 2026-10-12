# Aredoko — Codex向け開発引継ぎ（2026-10-11）

## 最新：5万件metadata・258フォルダのCPUと実GUI（2026-10-13）

開始HEAD **33e65d8acdea153af0b6d48d26c3f406f50adafe**。同じfeature / [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5) / comparison baseを維持。今回の提出SHAは後続の提出記録/Git/PR headで確認。

- 50,000生成metadata＋実PNG75件・258登録rootの再実行可能なfixture/CPU計測/GUIモードを追加。残り49,925件に実メディアはなく、私物/1TBのfilesystem走査や実GPU索引ではない。
- 複数rootのkeyset SQLの反復sortを修正。この分布の256root件数取得5回中央値は14,221→1,410ms。ID順、除外、種類、先頭1万対象枠、256行reads、scope/モデル/キャッシュ契約を維持。
- root選択欄を最大160 DIPの標準ScrollViewerへ収め、258番目の保存rootへ到達できるよう修正。先頭256＋保存ID・最大512 controlsの境界は維持し未仮想化。未選択の256以後を新規に探すUIは未実装。
- 最終Python **150 PASS / 92.363秒**、新規3 PASS / 2.328秒、Core **19 PASS**、Release **PASS / 35.82秒 / errors0・既存IL2104 2warnings**。手動WinUIレビュー済み、専用analyzer未実行。
- CPU01/02各14 checks PASS。native01 FAIL（last root到達不可）/4 PNG目視/所有PID終了fallback、bounded viewport修正後native02 **45 checks PASS / 12 PNG全目視 / scoped visual PASS / 2正常close**。Light/Dark・wide/narrow・DPI96/Contrast off、5万件/834ページ・文字検索・grid・saved258 restart・全root件数/最大1万・保存、GPU worker未ロード、生成素材不変。
- 狭幅長パスは一部がscroll境界で切れるため全文同時可視性は未確認。native測定はCLI/UIA/waits/scrollを含みフレーム描画/純粋な操作応答とは異なる。DPI/keyboard/読み上げと疎なroot分布の評価は次へ。詳細・再実行・失敗履歴は[library-scale.md](library-scale.md)。
- docs/status・scope文書とPR説明を更新。CI manual-only・Draft未マージを維持。push後runs/checksをread-only確認し提出記録/PRへ反映する。

### 次の3手

1. 疎な複数root分布を計測し、多数rootの新規選択/全文表示・keyboard/高DPIを確認する。
2. 新しいholdoutを凍結してtext/cover根拠別に混合順位を評価する。既存品質v1はdevelopmentとして扱う。
3. Laya日本語gate再評価。既定無効を維持し、reader/Komga/フォルダ本集約は別sliceで設計する。


---

## 最新：架空日本語の検索品質ベースライン（2026-10-12）

開始HEAD **15bb0c10ce71a2a6a8eb48135e4f03edfe4fef19**。同じfeature / [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5) / comparison baseを維持。提出commitは後続記録/Git/PR headで確認。既存製品検索・モデル・順位・GUI・scopeを変更せず、再実行可能な診断評価だけを追加。

- 固定[manifest](../tests/fixtures/search-quality-v1.json) v1、SHA256 `94260e45459d539285d7cde257214cddc9c39263b454a15b8e3c3b1e2e15afa8`。生成26件（PNG8/CBZ6/SVG8/無音WAV4）、20文（semantic12/visual4/filename-control2/no-answer2）、種類あり/なし、literal/text/cover/allで130結果行。正解2/関連1のgraded qrels、Hit1/Best-grade1/Recall5/MRR/nDCG5、no-answerとfilenameを別集計。関連候補はkind/cover eligibilityへ射影する。実行前に凍結し観測後のtuningなし。
- `python tools/evaluate_search_quality.py --output data/ai-ui/search-quality-01`: **runtime PASS / 164入力・境界検査 / 実CUDA document26/image14/query90 / index19.802秒**。元byte/mtime/hash・検索前後vector bytes・manifest不変、所有process-instance handles3件全終了。既存venv/重みだけ、downloads/私物/OS変更なし。native GUIは今回起動しない。rank品質gateは未定義で、runtime passと品質合格を混同しない。
- semantic12文は種類指定text/combinedでprimary Top1 **12/12**。種類未指定textは関連12/12・primary11/12、combinedは10/12・Recall5=0.972・MRR=0.917・nDCG5=0.921。literalは0/12。combinedのs08（謎解き本）とs09（朝食本）は2位。全modeで同じquery文のvariantsは独立した130問ではない。
- visual4文は画像指定cover Top1 **4/4**、combined2/4・text2/4・literal0/4。種類なしcoverは関連4/4だが同一PNGのCBZ表紙がitem ID同点順で先に出るためprimary0/4（人工的なgrade差）。正解PNG4枚目視、定義した色/形/白背景を確認。filename exactはliteral2/2・AI1/2。no-answer2問でもAIは候補を返すため、confidence/共通閾値/存在保証は未実装のまま。
- SVGは同一灰矩形＋用途を示す架空タグ、WAVは無音＋架空タグで内容理解の証拠ではない。CBZ表紙も単純図形で物語はmetadataだけ。今回のmixed-kind順位の弱点を実本全体へ一般化しない。PyTorch peak allocated931.8MiBは総VRAMでない。今後この20文はdevelopmentとして扱い、改善判定は新しいholdoutで行う。
- metrics/fixture契約 **5 tests PASS / 0.161秒**。全Python **147 tests PASS / 86.923秒**。Python構文/CLI/diff確認PASS。前回C#19・Release35.75秒/IL2104 2warnings・native133/31PNG等は過去の証拠で再実行なし。詳細は [search-quality-baseline.md](search-quality-baseline.md)。
- CI manual-only・Draft未マージを維持。push後実HEADのruns/checksをread-only確認しPR説明へ記録。旧失敗履歴は以下に残す。

### 次の3手

1. 多数の生成metadata・長いrootパス・scope上限とGUI応答性を評価。大量root選択、DPI/keyboard/accessibilityの未検証部分を段階的に確認する。
2. 新しいholdoutを先に凍結し、text/coverそれぞれの根拠がある素材で混合順位を評価。v1の結果へ過適合する重み/閾値変更や自動routingはしない。
3. Layaの日本語品質gateを再評価し合格前は既定無効を維持。reader/Komga/フォルダ本集約は別sliceとして設計する。


今回の実装・評価・文書commitは **83b6ca2be8551543e25f0ccb4d68f46187cead1a**。この追記は同commitを開始HEADとする後続commitで、manifestのGit LF属性と固定SHA256検査も含む（Windows改行変換でも入力の同一性を保持）。同じDraftへ通常push。最終HEADとpush後CI観測はGit/PR head・説明で確認。

---

## 最新：AI対象選択GUI・設定保存・再起動確認（2026-10-12）

開始HEAD **ba9e1ee7474e8ea91e1f48ac7d4fe3dc6e9fdb02**。同じ `feat/winui3-production-mvp-20261011` / [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5) / base `feat/gui-framework-comparison-20261010` を維持。提出commitは後続の提出記録または実Git/PR headで確認。下の旧結果・失敗履歴は当時の記録として保持する。

### 実装と操作

- WinUIの「AI索引」→「AI検索と索引の対象」で登録フォルダ・種類・棚を選択し、「件数を確認」→「保存してAI検索に適用」。候補/最大10,000件の対象枠/文字索引/残りを分けて表示。保存された同じscopeをAI検索と次の索引に明示送信する。文字検索と一覧kind/viewは独立。現在進行中または過去のjob進捗は「索引処理（開始時の対象）」と表示。
- 新GET/POST `/api/library/ai/scope` とローカルuser preferenceを実装。旧profile-only設定は互換の全登録root。profile/resource/scopeは同じ所有lockとatomic replaceで更新し、互いの保存値を保持。設定上限16KiB、明示root配列最大256。job scope保存とは別のユーザー設定。範囲の変更はモデル/索引の削除・hot swapを行わない。
- 件数確認後のdraft変更は再確認が必要。未保存で閉じるとdraft破棄、保存中は編集と閉じる操作を抑止、scan/AI索引中の保存は409。非同期の古い件数応答・閉じた画面への反映を防止。通信エラー時は保存設定を読み直し、要求値/前の値と一致する場合だけ採用し、不明ならAIを止めて確認・再保存を促す。製品の自動書込みretryは行わない。
- `[]`はゼロ件。削除済みrootは警告・明示修復を求め、全rootへ復帰しない。scope単体の破損もAIを止めて選び直せる。JSON全体/基礎設定が破損した場合、scope保存だけでは修復できずモデル選択の保存または設定ファイル修復が必要。モデル選択による全体修復はscopeを空にする。文字検索は独立。
- reflection無効でも動くJSON DOM/deep cloneを維持。native ListView/ItemsWrapGrid、60件paging、metadata editorのdirty/stale規約、既存assets/比較アプリは維持。個別root表示は先頭256と保存済みID（最大512 controls）で、root一覧は未virtualize。大量rootと長いパスは今後評価。

### 今回の検証と失敗履歴

- `python -m unittest discover -s tests -q`: **142 tests PASS / 96.724秒**。settings13 / scope12を含む。atomic保存失敗で旧bytes保持、同時resource/scope保存、restart、token/Origin、busy/空/削除root/不正型をCPUと実HTTPで検証。後の変更はC#/native harnessのみ。最終Python構文とCLI helpもPASS。
- `dotnet run --project tests/Aredoko.Core.Tests -c Release --no-restore`: **19 checks PASS**。初期はgeneric JsonArray.Add(int)がreflection無効で実行時失敗。primitive JsonValueを明示JsonNode castして非generic overloadへ修正し、抑制なしで新規IL2026も解消。
- x64 SelfContained Release最終build05 **PASS / 35.75秒 / 0 errors / 既存SDK/WinRT IL2104 2 warnings**。初回はStackPanel.IsEnabledの誤用でFAIL、各Controlの無効化へ修正。build04はPASSだが最終製品差分の結果は05を使う。manual WinUI review実施（async/ownership/theme/IDs/JSON/authentication/bounded controls）。専用analyzer未導入・未実行、日本語固定文言/MVVM全面移行/AOTは別工程。
- `scope-native-01`: functional **101 checks PASS / 22 PNG / 3正常close / source hash不変**。目視はLight-A-selection/countsの2枚だけで全体visual合格とは扱わない。その後狭幅・restart実検索・削除rootを追加。
- `scope-native-02`: **FAIL / 49 checks / 12 PNG / source hash不変**。Light-Bの保存通信が失敗し旧A設定が残った。保存成功待ち5000ms timeout、原因未確定でbackend tracebackなし。目視はLight-narrow-A-selection/counts、Light-A-saved、failureの4枚のみ。cleanupには所有test PID停止fallback warning。保存応答を読み直す製品処理と15秒待機・失敗観測後だけの明示GUI retryを追加。失敗を成功扱いしない。
- `python tools/test_ai_profile_ui.py --editor-only --scope-checks --output data/ai-ui/scope-native-03`: **133 checks PASS / 全31 PNG目視 / 対象範囲のvisual PASS / 4正常close / cleanup warningなし / retry観測なし**。isolated DB/settings、生成17+2 files/2 roots、既存EG2実CUDA・GUI text-only profileでA/B各audio2件のindex/query、保存・profile/resource保持・Dark restart後B実検索、Light/Dark幅1200x800と700x620、解放後A cached rebuildで未ロード、A/B4文字vector bytes不変。空scope・消えたrootでAIを広げずGPU未ロード、文字検索は動作、消えたIDを明示解除して空へ修復。消失はisolated catalog内だけのfault injection。元source bytes/mtime/hash不変、生成profile/所有processをcleanup。既存重みのみ、ダウンロードなし。
- PNGの設定欄はスクロール領域で別captureにより選択欄/件数/保存feedbackを確認。status/start/cancel/closeは固定で読み取れる。一部検索captureのCtrl+F tooltipと追加HWND縁はharness artifact。今回DPI/Contrast状態は計測していない。ネット応答喪失のreadback分岐は専用fault injection未実施で、native03では自然失敗なし。visual-review.jsonは各ignored実行フォルダに残す。
- 前回native182/29PNG、scope CUDA15（表紙あり）、GPU10k126/HTTP28/解放CUDA30は**過去の結果**で再実行なし。1TB私物、別checkpoint、検索順位品質、総VRAM/ゲームFPS、高DPI/HighContrast/screen-reader、AOT/installer/reader/Komga/OCRは未検証または未実装。Layaは日本語品質gate未達で既定無効の実験API。
- Hosted CIは未実行。既存3workflowはworkflow_dispatchのみを維持し、手動dispatch/課金/runner設定変更なし。push後に実HEADのruns/checksをread-only確認し、結果はPR説明に記録。Draftのまま未マージ。

### 次の3手

1. 架空日本語の検索品質セットを整備。名前一致だけに頼らない期待意図・正解候補を固定し、文字/表紙/combinedの順位を比較する。私物1TBの評価とは分ける。
2. 多数の生成metadata・長いrootパス・scope上限、GUI応答性とDPI/keyboard/accessibilityを評価。必要に応じroot選択の仮想化と表示設定永続化を検討。
3. Layaの日本語品質gateを再評価し、合格条件が揃うまで自動routingを既定有効化しない。reader/Komga/フォルダ本集約は別sliceで設計する。


今回の実装・テスト・文書commitは **2a42b3acaddd943e9fbf51c62de13043022207cc**。この追記は同commitを開始HEADとする文書のみの後続commit。同じDraft PRへ通常push。正確な最終HEADとpush後のread-only CI観測はGit/PR head・PR説明で確認する。

---

## 最新：グリッド実機確認・AI対象選択API/GPU・自動CI抑制（2026-10-12）

開始HEAD **d635c980199e3c6fafb093576127f88ff31a0385**。同じ `feat/winui3-production-mvp-20261011` / [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5) / base `feat/gui-framework-comparison-20261010` を維持。未マージ。提出commitは後続の提出記録と実Git/PR headで確認する。以下が今回の実装・検証で、下の旧失敗履歴を上書きしない。

### 実装

- ユーザーのグリッド表示希望を反映。既存のタイル表示は安全なnative `ListView` + `ItemsWrapGrid` で既に実装されていたため、切替ボタンを「グリッド表示」/「リスト表示」と明確化。60件paging・画像/CBZ/ZIPの限定プレビュー・キャッシュ・選択復元を維持し、managed ItemsSourceを再導入しない。表示設定のrestart永続化は未実装（今はセッション内）。
- 登録済みroot ID・種類・完全一致の棚でAI対象を指定する **CPU/API sliceを実装**。新 `POST /api/library/ai/coverage` はモデルを起動せず候補/対象枠/fresh/残りを数える。index/searchに任意scopeを追加。`[]`はゼロ件、未登録/削除済みID・不正型・未知キー・明示scope:nullは400、勝手な全root復帰なし。token/Origin・読み取り専用sourceを保持。
- scopeで絞り、present・除外適用後、ID順の最大10,000件が共通対象枠。追加の検索kind/viewはその枠の後に適用。省略scopeは従来の互換経路。256行keyset読み取り、count側も全候補をメモリに保持しない。候補件数は上限前、freshは同一profile/revisionのtext vectorレコード数で、表紙成功/品質/破損vector検査とは区別する。
- job開始時にscopeをコピーし進捗/ai_stateへ保存、処理・publish前にも範囲/presence/除外/revisionを確認。job scopeはrestart後も残る。同じmodel/vector identityを維持し、対象を切り替えても他範囲のvectorを削除しない。**GUI選択欄・ユーザーscope設定の永続化はまだない**。過去job state保存とユーザーの次回対象設定保存を混同しない。
- `.github/workflows` の3本は一時的に **workflow_dispatchのみ**へ変更し、自動push/PR起動の重複通知を抑制。jobs/stepsを保持、課金・上限・runner・通知設定は変更しない。ユーザーが課金しなくてもローカル開発は続けられる。default branchへ未マージなので手動Run workflowボタンの表示は未確認。CI PASSとは扱わず、手動dispatchもしていない。

### 今回の検証

- `resource-native-07`: **FAIL / 57 checks / 9 PNGすべて目視**。旧20px最低高さでは実際の完全な19px Text peerも拒否。最初の1px断片は正しく拒否され、スクロール後の全19pxが実測された。19pxを許可する観測回帰を追加（UI geometry 9件）。3正常終了＋所有test PID停止1回のwarning。全体visual PASSではない。
- `python tools/test_ai_profile_ui.py --output data/ai-ui/resource-grid-native-08 --editor-only --layout-checks --appearance-checks --coverage-checks --resource-checks`: **182 assertions PASS / 29 PNGすべて目視 / scoped visual PASS / 9正常終了 / cleanup warningなし / source hash不変**。生成17件、専用DB/settings、DPI96・Contrast OFF。既存EG2の生成GUI用text-only profile。グリッドはDarkで1200px広幅4列、700×620px狭幅2列、表紙・選択・詳細・リストへの復帰を実確認。Light/Darkのリソース保存/解放メッセージ全文、restart値、文字検索復帰・未保存編集・お気に入り・folder dialogを確認。scroll contentの全項目が常に同時表示される保証ではない。一部PNGのCtrl+F tooltip/別HWNDの端はharnessのcapture artifactとして記録。
- 07→08は今回1修正再試験。06の1px誤判定/visual未合格を08で解消したが、過去runの結果はそのまま残す。ignored各runの `visual-review.json` に目視範囲/結果を記録。19px guardは96-DPI単行用で、他DPI・折返し全文を保証しない。
- 新しいscope CPU **11 tests PASS / 8.818秒**。2 roots、空/不正/削除ID、棚のSQLパラメータ、missing/exclusion、同一cap、scope切替reuse、job中のscope変更/publish再検査、263件の256+7行freshness集計と60件paging、restart/auth/Originを確認。HTTP null本文を修正後 **11 tests PASS / 8.731秒**。偽encoderのみで意味品質試験ではない。
- `python tools/test_ai_scope_gpu.py --output data/ai-ui/scope-gpu-01`: **実CUDA 15 checks PASS**。生成6ファイル/2 roots、選択したPNG4件のみdocument4/image4/query3、text/cover queryが指定rootを越えない、scope切替cache再利用・vector digest/model key/path不変、job scope restart復元、restart count/cached rebuildでworker未ロード、所有process-instance handle **3件全終了**、source byte/mtime/hash不変。検索順位の品質保証ではない。既存重み/環境だけでダウンロードなし。
- 全Python **137 tests PASS / 88.077秒**。C# `dotnet run --project tests/Aredoko.Core.Tests -c Release --no-restore`: **15 checks PASS**。WinUI x64 SelfContained Release **PASS / 33.58秒 / 0 errors / 既存IL2104 2 warnings（抑制なし）**。最終nullテスト修正後はscope11件だけ再確認、全suiteの結果と区別する。
- WinUI manual review: 今回のproduct UI差分は文言のみ。native Items/ItemsWrapGrid/60 paging、async stale/dirty/selection、theme/accessibility IDs、JSON DOM、認証/所有worker境界を再確認。専用analyzerは未導入・未実行。日本語固定文言・MVVMの全面移行は別工程。Release JIT成功はAOTの検証ではない。
- GPU10k126/HTTP28・専用解放GPU30は**以前の検証**で今回再実行なし。1TB/私物、ANN、別checkpoint、総VRAM/ゲームFPS、高DPI/HighContrast/screen-reader/AOT/installer/Komga/reader/OCRは未検証または未実装。Layaは品質gate未達で既定無効の実験API。

### 次の3手

1. [AI対象選択の契約](ai-coverage-selection.md)をWinUIのAI画面へ接続。登録root/種類/棚を明示選択し、CPU件数を表示、dirty/stale/busyを守って同じscopeをindex/searchへ渡す。文字検索は独立のままにする。
2. ユーザーのscope preferenceをprofile/resourceと同じatomic設定更新規約で保存。削除済みrootは通知・再選択、全rootへfallbackしない。job state保存と区別してrestart・同時保存をテストし、Light/Dark/狭幅を実操作・全PNG目視する。
3. 架空日本語検索の品質セットを整備し、表紙/文字/種類の評価を進める。Layaの品質gateを再検討するが、自動routingを既定有効化しない。CIは自動起動を抑えたままローカル検証を続け、必要時だけ無料枠/制限を確認して復帰する。

今回の実装・検証・文書の提出commitは **893bb08014ba31936b78e055059a813c20116f8f**。この追記は同commitを開始HEADとする文書のみの後続commit。同じDraft PRへまとめて通常pushし、正確な最終HEADはPR head / `git rev-parse HEAD` で確認する。


---

## 最新：リソース操作155項目確認・1px誤判定を特定・CI停止原因判明（2026-10-12）

開始HEAD **e3caae44c38f4d3c602e1b1075add2bee9cd5c53**。同じ `feat/winui3-production-mvp-20261011` / [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5) / baseを維持。今回の変更はnative試験helper、回帰テスト、文書のみ。製品C#/XAML/API、model/vector identity、10,000件上限は変更していない。

### 今回の結果と残っている表示問題

- `resource-native-04`: **FAIL / 36 checks / 6 PNGすべて目視**。WindowsがStartAIIndexへのforeground focusを拒否した。所有HWNDの標準UIA Invokeで実ボタンのClick handlerを呼ぶ形へ修正し、設定操作の不要なfocusを除いた。3正常終了＋所有test PID停止1回のcleanup warning。
- `resource-native-05`: **FAIL / 55 checks / 9 PNGすべて目視**。設定操作に時間がかかり、保存した60秒idle policyがworkerを解放し、手動解放ボタンが無効だった。生成fixtureの明示queryでworkerを準備してから手動操作を試験する順序へ修正。3正常終了＋所有test PID停止1回のcleanup warning。
- `python tools/test_ai_profile_ui.py --output data/ai-ui/resource-native-06 --editor-only --appearance-checks --coverage-checks --resource-checks`: **155機能assertions PASS / 23 PNGすべて目視 / 8正常終了 / cleanup warningなし / source hash不変**。Light/Dark、700×620px、DPI96・Contrast OFF、生成17件・専用DB/settings。旧profile-only設定から開始し、60秒/50ms保存、manual release後のresident/device/telemetry消去、GUI意味検索による実CUDA再ロード、restart後の保存値とlazy unloaded状態、文字検索復帰・未保存編集・お気に入りを確認。既存EG2重みのGUI用text-only profileで、別checkpointの試験ではない。
- **全体のvisual PASSではない**。06の `23-Light-resource-released.png` / `23-Dark-resource-released.png` には解放メッセージが写らない。UIAは両方で `IsOffscreen=false` だがText peerのheightが**1px**だった（Light y340 / fixed heading y353、Dark y392 / fixed heading y405）。正の高さだけを許可したhelperが、スクロール下端の断片を可視扱いしたと特定。restartの1分/50msの選択値は両テーマで実際に映るが、スクロール途中でheaderが外れる画像もある。
- `tools/ui_geometry.py` を追加してTextに最低20px、Button/ComboBoxに最低32pxを要求する96-DPI試験guardへ修正。実測のLight/Dark 1px例、上下clip、offscreen、無効buttonの可視性など **CPU回帰8 tests PASS**。**この最終guardを使用したnative再実行はまだ行っていない**。多行Textや他DPIを含む完全可視保証ではなく、画像の目視は引き続き必要。
- winui-ui-testing SKILLの **Maximum two fix-and-rerun cycles** に従い、今回04→05→06の2修正再試験で停止。ignoredの各runに `visual-review.json`（visual_pass=false）を保存し、機能PASSを表示合格へ読み替えない。所有GUI/APIの正常終了は06の結果で確認、04/05のfallback履歴を残す。
- 前回の実GPU専用30 checks、Python117 tests / C#15 checks / SelfContained Release（IL2104警告2件）は過去の検証結果。今回製品コードは変えていない。WinUI manual code reviewでasync dialog配線、JSON-DOM、テーマ資源、Name/ID、busy/releasing guardを再確認。専用analyzerは未導入・未実行。GPU10k126 checks / HTTP28、総VRAM/ゲームFPS、1TB/私物、HighContrast/高DPI/AOT/installerを今回確認したとは扱わない。

### GitHub CIの原因

開始HEAD e3caae4のcheck-run annotationsを認証済みGitHub APIで読んだ。**最近の支払い失敗、または利用上限の引上げが必要なためjobが開始されなかった**というGitHub側の注釈を、PRとpush両方の全4ジョブで確認した。コードのテストが走って落ちた証拠ではなく、CIは合格していない。

- [owned-worker CPU](https://github.com/jakymiku/Aredoko/actions/runs/38241656866/job/114785481774)
- [Prototype tests](https://github.com/jakymiku/Aredoko/actions/runs/38241656890/job/114785481991) / [browser smoke](https://github.com/jakymiku/Aredoko/actions/runs/38241656890/job/114785482614)
- [AI profile/build](https://github.com/jakymiku/Aredoko/actions/runs/38241656885/job/114785481732)

ユーザー側でGitHubのBilling & plansを確認する必要がある。支払い/利用上限の変更、有料runner、CIの不要な再実行は行っていない。既存認証情報は読み取り要求のためだけにメモリ内で扱い、出力・ファイル・commitへ保存していない。古いHEADの取得不能logの原因を同じと断定せず、その履歴は下に保持する。

### 次の3手

1. 修正済み最低高さguardを使う新しい生成native runで、解放メッセージが完全に映るLight/Dark PNGを取得する。まず23の1px誤判定を解消し、固定status/start/cancelと各設定値の表示を目視する。現時点で製品layout故障とは断定しない。
2. [AI対象選択の仕様案](ai-coverage-selection.md)に沿って、登録root/種類/棚と候補件数のCPU/API sliceを実装する。**仕様案のみで未実装**。scopeをmodel identityに入れず、10,000上限・cache再利用・token/Origin・登録同意を維持。scopeありではindex/searchの同じ対象枠へ検索filterを適用し、検索だけ別の先頭10,000件を選び直さない。
3. 対象選択を生成少数件の実CUDA/WinUIへ接続し、架空日本語検索の品質セットを進める。Layaは精度gate未達の既定無効実験API。実素材走査/移動、Komga、OCR、folder-to-bookを勝手に追加しない。CIの再確認はユーザーのGitHub account制限解消後。

`python -m unittest discover -s tests -q`: **125 tests PASS / 79.968秒**。新しいUIA回帰8件を含む既存CPU/API/scanner/settings/owned-worker全体。CLI rate範囲外テストの想定argparseエラー出力を含むがsuiteはexit0/OK。native helper/geometry/testのPython構文も確認。C#契約とReleaseビルドは製品コード未変更のため今回再実行せず、前回結果を区別して保持。実装・検証・仕様の提出commit **05f4ba3c4a1defb615cd56f7ecf1af743778e9b9**。この追記の作成時HEADも同値。後続の文書追記commitを含む正確な最終HEADは `git rev-parse HEAD` / PR headで確認する。

---

## 最新：Chat分を取り込み、AI解放GPU合格・GUI機能確認、表示検査は未完（2026-10-12）

再開前ローカルHEAD `753ae518b58a2fb97d5e8cc0e353909396e76697`、Chat提出HEAD `e63a5f955459f29e1b6082d44ecc3b21b1a69189`。同じ `feat/winui3-production-mvp-20261011` / [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5)、base `feat/gui-framework-comparison-20261010` を保持し、Chatの29コミットをfast-forwardで取り込んだ。以下は今回の新しい確認。旧GPU10k 126 checks / HTTP28は今回再実行していない。

### 修正したこと

- resource設定を保存してから動作中のpolicyへ反映する。壊れたJSONや書き込み失敗は409、動作中の設定を維持。profile/resourceのread-modify-writeを同じsettingsインスタンスのlockで直列化し、同時保存で片方が失われることを防ぐ（別プロセス間の排他を保証する設計ではない）。
- idle timerの事前確認後に検索が完了したり設定が無効化された場合、inference/guard内でidle条件を再検査して誤解放を防ぐ。
- WinUIの新ComboBoxに読み上げName/選択肢ID、設定パネルと固定行にUIA ID。保存中は選択を固定し、解放中のtimer更新でボタンを再有効化しない。モデル・catalog・vector identityを変更しない。

### 実行した確認

- `python -m unittest discover -s tests -v`: **117 tests PASS / 73.187秒**。保存失敗時のpolicy不変、profile/resource同時保存、idle条件再検査の回帰を追加。C#契約 **15 checks PASS**。
- x64 SelfContained Releaseビルド **PASS**。既存のSDK/WinRT IL2104 **2 warnings**を保持、無効化していない。WinUI manual code review実施（async/dialog配線、JSON-DOM、token/Origin、native行、テーマ、操作ID）。WinUI専用analyzerは未導入のため未実行。日本語固定文言、多言語化/AOT/installerは今後。
- `python tools/test_ai_release_gpu.py --output data/ai-ui/resource-gpu-02`: **30 checks PASS**。既存EG2既定text+cover/auto-bf16/768、生成17件、document17 / valid cover12 / damaged image skip1 / query4。手動解放→所有launcher/実worker終了→query再ロード、query guardを試験gateで保持した重複releaseの即時409、1秒idle自動解放→再ロード、source/vector hash不変、再索引なしを確認。所有process-instance handle **9件すべて終了**。
- query再ロード **10.55秒 / 12.41秒**（手動後/idle後）、PyTorch peak allocated **931.8MiB**。これは総VRAM量でもゲームへの影響測定でもない。プロセス終了は実測したが、他アプリを含む総VRAM/物理メモリの減少量は測定していない。
- `python tools/test_ai_profile_ui.py --output data/ai-ui/resource-native-02 --editor-only --appearance-checks --coverage-checks --resource-checks`: **機能の153 assertionsは通過**。Light/Dark、700×620px、DPI96/Contrast OFF。60秒/50ms保存、手動解放後のresident/device/telemetry消去・ボタン無効化、実CUDA再検索、restart後保存値復元とlazy unloaded状態、既存17件検索/dirty/favoritesを確認。**8回正常終了 / cleanup warningなし**。旧profile-only設定から開始。GUIは生成テスト用text-only profile、別checkpointではない。**23枚すべて目視した結果、解放メッセージとrestart選択値の撮影時のスクロール位置が不十分で、GUI全体のvisual PASSとは認めない。**
- 厳格化した `resource-native-03` は **FAIL / 44 assertions後 / 8枚すべて目視**。`AIIdleRelease cannot be brought into settings viewport`。WinUI ScrollViewerのUIA boundsはcontent extentを含み、Grid/StackPanelはIDだけではUIA peerを生成しないため、固定パネルIDを探すテスト側が失敗した。観測済みTextBlock peer（dialog title / 現在のAI索引）でviewportを挟むようhelperを静的に修正・構文確認したが、**この最終helperは実画面再実行していない**。新GUIの完全可視検査は次回優先。03のcleanupは3回正常終了＋失敗時の所有test PID停止1回（warning）で、02の8回正常終了と混同しない。
- 試験履歴: `resource-gpu-01`は計測器が破損PNGの正常skipを例外にしたためFAIL→計測器のみ修正。`resource-native-01`はスクロールしない可視検査でFAIL、02は構造化検査通過後に目視で不足発見、03は上記FAIL。winui-ui-testing SKILLの「Maximum two fix-and-rerun cycles」に従い今回は再試行を止めた。失敗をPASSに読み替えない。
- 生成データ/DB/settings/モデル/log/画像はgitignore下、個人AppData/素材は未使用。既存runtime/weightsのみ、DL/依存変更なし。

### GitHubと次の3手

実装・検証提出コミット **84535632f4b261e57389ee78c9d0f6e3cae74329** を通常push済み、Draft PR #5更新済み。後続の文書コミットを含む正確なHEADは `git rev-parse HEAD` とGitHubのPR headで確認する。

提出8453563のCI最終状態も取得: [owned-worker CPU](https://github.com/jakymiku/Aredoko/actions/runs/38241308142)、[Prototype checks](https://github.com/jakymiku/Aredoko/actions/runs/38241308023)、[AI profile/build](https://github.com/jakymiku/Aredoko/actions/runs/38241308108) は **すべて completed/failure**。4ジョブのstep/log URLがnull、CPU job log取得はBlobNotFound404。**原因不明、CI合格ではない**。課金・runner・コードのどれが原因かはこの証拠だけでは断定できない。文書のみの後続HEADのCIは未確認。

Chat HEAD e63a5f9のActions: AI profile/build checks成功、prototype testsジョブ成功。owned-worker CPUジョブとbrowser-smokeはfailure、step/logは取得不能（Azure Blob404）で原因未確定。ローカルの上記PASSと区別する。今回の提出HEADのCIは最終ジョブを別途確認し、未確認の成功を推測しない。

1. 修正したviewport helperで新しい生成テストrunを行い、AI解放メッセージ/各選択値が実際に映るLight/Dark画像と設定復元を確認する。03の失敗はテストpeer探索の問題であり、製品レイアウト故障とはまだ断定しない。
2. 現在HEADのGitHub CI最終状態を確認し、実行前failure/log欠落なら原因を特定する。ローカルPASSをCI成功と混同しない。
3. 上記の確認後に、10,000件超へ向け明示root/種類/棚とcoverage選択の仕様、架空日本語品質評価を進める。既存上限は維持。個人サンプル/1TB、Komga、OCR、folder-to-book、ゲームFPS、高DPI/Contrast/AOTは未検証。Layaは精度gate未達の既定無効実験APIを維持。

---

## Chat担当時点：AI worker解放／リソース設定（履歴）

**直近の変更は `docs/chat-handoff.md` の最新節と `docs/ai-resource-policy.md` 冒頭を必ず参照。** 製品版WinUI 3＋実GPU10,000件 / HTTP28 checksは従来の検証済み資産として維持。今回は**新AIモデルとGPU再測定は行っていない**。

- `app/ai_process.py`: 同じencoder lockで`release()`（一時的な所有worker解放）と`close()`（終了フラグを先に立てる永続停止）を区別。device/telemetry reset。検索でlazy reload。close後の再spawnは禁止。
- `app/ai_search.py`: 既存`inference`と索引生存をnonblockingで検査し、実行中の解放を409 Busyへ。statusのresident/worker_state。単調時計による**任意**idle解放（初期0秒OFF）、新規推論後だけのキャンセル可能な**任意**待機（初期0ms OFF、cache rebuildは待機なし）、close時timer停止。モデルidentity/ベクトルは不変。
- `app/production_server.py`: 認証済みPOST `/api/library/ai/release`, GET/POST `/api/library/ai/resource`; `app/ai_settings.py`: version1/profile-only JSONとの後方互換・独立resource設定をatomic保存。0..3600秒 / 0..2000ms、型/範囲外を拒否。
- `src/Aredoko.WinUI/MainPage.xaml.cs`: 既存小窓の固定索引status/start/cancelを保ちつつ、手動解放・自動解放時間・索引待機選択/保存/注意文を追加。GUI画面操作は未実行。
- 新規`tests/test_ai_release.py`＋`.github/workflows/ai-release-checks.yml`、既存`tests/test_ai_settings.py`、`docs/ai-resource-policy.md`更新。**専用Windows CPU CI PASS** [run 38233333368](https://github.com/jakymiku/Aredoko/actions/runs/38233333368)。一般Pythonテスト/WinUI Releaseの最終結果はworkflowで確認し、未完了をPASS扱いしない。
- 既存CPU2,105件の`tests/test_ai_scaling.py`は同時に走るWindows CIで旧join60sを超えたため**テストjoinのみ180sに調整**。製品timeout/IndexStore/GPU仕様変更なし。実GPU10,000件126 checksを不要に再実行しない。
- Layaは未変更（experimental/disabled-by-default）。main未マージ、既存Draft PR #5/base/安全なテスト素材境界を保持。
- **残件・次の3手**: ①実GPU所有subprocessの停止/再ロードと元source/vectorのhash不変をユーザー側で確認、②新WinUI AI dialogのLight/Dark・狭幅・busy/保存設定を実機確認、③10,000超のroot/種類/棚/coverage選択と架空日本語品質セットを設計（上限の無制限解放や自動Laya適用は禁止）。

最新実装コミット: **284fc5883db6edd0c0d3cf1dfd9b13c9f3baed80**。この文書更新分を含む最終HEADは`git rev-parse HEAD`で確認し、報告/PR本文に正確な値を反映する。

---

> **最初に読む文書。** 2026-10-10時点の旧 `docs/status.md` / README には「GUI未決定」「ネイティブGUI未実装」という古い記述が残っている。現在の方針・分岐状況はこのファイルと [Issue #4](https://github.com/jakymiku/Aredoko/issues/4) を優先する。ファイル上の実装が異なるときは実際のコードを調査してから更新する。

## 今、何をしているのか
- 目的: **Aredoko**（Windows用のローカルメディアライブラリ検索・整理アプリ）の**製品版MVPをWinUI 3 + C#で新規実装する**。以前はGUI方式としてTauri + Reactも評価したが、2026-10-11にユーザー判断で**WinUI 3を先行採用**した。Tauriの比較コードは削除しない。
- 理由: Tauri/WinUI双方の実機GUI基本操作が完走し、WinUIのPrivate Bytes（アプリ本体関連プロセス）が一貫して小さかった。CPUは操作回数の差や負荷条件が統一できておらず優劣は未確定。安定性に関しては**WinUIだから無条件に安全と証明されたわけではない**。過去にWinUI試作固有のクラッシュも修正済み。
- GUI: Fluent 2 / Windows 11らしいモダンで密度の高いUI。左ナビ・上部検索・中央の大きい作品一覧・右の詳細/タグ編集。狭い画面は詳細をドロワーに。Mica等の見栄えは安定性・操作性を損なわない範囲。
- 開発実務: **製品用の最初の縦切り実装と実機GUI検証まで完了**。登録・走査・文字検索・整理・再起動保持に加え、画像/CBZ/ZIPのプレビューが動く。EmbeddingGemma2の最初のAI索引/検索APIとGUI接続も追加。最新の生成17素材のGUI AI検索通し確認はPASS（詳細は末尾）。Issue #4全体の完成宣言ではない。最新結果と残課題は末尾、起動手順は [winui-mvp.md](winui-mvp.md)。

## GitHub上の資産と現在位置
| 作業 | 場所 | 状態・意味 |
| --- | --- | --- |
| 公式デフォルト | `main` | 既存デモの安定基点。直接改変しない |
| UI設計/試作 | [PR #1](https://github.com/jakymiku/Aredoko/pull/1) · `feat/compact-library-ui-20261010` | **Draft / 未マージ**。Web試作のモダンUIや未保存確認、エラー・ドロワーUXの参考 |
| フォルダ索引 | [PR #2](https://github.com/jakymiku/Aredoko/pull/2) · `feat/library-index-foundation-20261010` | **Draft / 未マージ**。読み取り専用の `app/library_index.py`, `tools/index_library.py` とテスト・ドキュメント。製品版で必要なら**差分を調べて安全に取り込む** |
| GUIフレームワーク比較 | [PR #3](https://github.com/jakymiku/Aredoko/pull/3) · `feat/gui-framework-comparison-20261010` | **Draft / 未マージ**。WinUI 3 / Tauri + Reactの試作、Windowsテスト用BAT、自動操作ドライバー、CSV/HTML計測 |
| **製品版MVP** | **`feat/winui3-production-mvp-20261011`** | **現在作成済みの作業ブランチ**。PR #3のHEADから分岐し、比較試作を参照できる。**このブランチに新規ソースを追加して進める** |
| 実装タスク | [Issue #4](https://github.com/jakymiku/Aredoko/issues/4) | Codexへ渡す実装目標、スコープ、禁止事項、合格基準 |

**注意:** PR #3 → PR #1 → mainという祖先関係に対し、PR #2はmainをベースとする独立ブランチ。製品版ブランチからPRを作る際は差分に比較用コードが含まれる。適切なPRベースを選び、旧PRの無断マージ・履歴書き換え・強制pushを避ける。

## 引継ぎ受領時点の既存資産（2026-10-11実装開始前）
- **Python標準ライブラリ＋SQLite / localhost API**: `app/catalog.py`, `app/server.py` など。50,000件の架空レコード、60件ページ、タイトル/タグ検索、種類フィルタ、詳細、タグ・棚・お気に入り・確認済みの単体/一括保存。セッショントークン付きのlocalhost API。Webデモとテストあり。**これはAI意味検索ではない**。
- **比較用 WinUI 3**: `experiments/gui-compare/winui3/overrides/` が元となるC#/XAML。`winui3/generated/` はユーザーWindows上で公式CLIにより作成された**ローカル生成物**。再生成・削除禁止。
- **比較用 Tauri**: `experiments/gui-compare/tauri-react/`。製品版採用ではない。比較用コードや測定履歴は残す。
- **実機テスト（ユーザー報告と提出ZIPによる）**: **Tauri・WinUI双方とも**GUI自動操作の事前チェック（検索/スクロール/詳細/タグ保存）と5種類の計測を完走した。CIのビルド・ヘッドレステスト成功だけでなくWindows GUI基本操作の通過実績がある。ただしこれは**比較試作**であり、サムネイル/読書ビューア/実ファイル索引の製品版動作を保証しない。
- **比較の暫定傾向**: WinUIのPrivate BytesがTauriより小さい傾向。CPU測定は操作回数差や検索/描画負荷の差があるため最終的な順位を確定していない。GPU/FPS/起動時間は測定していない。最適化競争は一旦打ち切る。
- **別PRに安全な索引エンジン**: PR #2はフォルダ/サブフォルダの読み取り専用走査、除外、リパースポイント回避、追加/変更/消失検知、一時DBテストなど。現在のGUI側とは**未統合**。
- **Windows実機で発見した重要な落とし穴**: WinUI ReleaseではJSONのリフレクション型シリアライザが無効な構成があり、比較試作は`BenchJson.cs`のJSON-DOMで回避。WinUIの管理`ObservableCollection<MediaRow>`を`ListView.ItemsSource`へ割当てた版で0x80004003系クラッシュ（`WinRT.ComWrappersSupport`）を確認し、`ListViewItem`ネイティブ行作成で回避。作品切替時の誤dirty判定、Tauriのスクロール位置/ページ遷移、テスト用UIA入力とデバウンスも修正した。**これらを製品版で無検証のまま再発させない。**
- **ユーザー側ツール**: Windows 11、Python 3.14系/.NET SDK 10/WinApp CLI/PowerShell 7、Node/Rustも比較キット用に確認済み。環境差は必ず自分で確認。旧作業フォルダ例`C:\AI\Aredoko`、比較用`C:\AI\Aredoko-gui-compare`。

## 実装開始前の未完成項目（最新状況は末尾）
- 製品版`WinUI 3`アプリ（製品用起動、見た目・画面遷移、ルート登録GUI、個人ライブラリの表示）は**未実装**。
- PR #2の実ファイル索引とPythonカタログ、WinUIの作品一覧は**未接続**。5万件のダミーGUIが動くことと、本物のフォルダが取り込めることは別。
- 実際の画像/動画/本のサムネイル、読書（画像フォルダ/ZIP/CBZ/PDF）、Komga、AI意味検索/タグ推定/OCR、オフラインドライブ追跡は**これから**。`EmbeddingGemma 2`は候補であり採用・モデル自動DLは未承認。
- セットアップ型配布、署名、インストーラー、動作確認済みのWinUI製品版Releaseは**未達**。
- 新しい実装をしないまま、旧`README.md`や`docs/status.md`を書き換えただけで「MVP完成」と報告しない。

## Codexが実際に取る次の手順
1. `git status`、現在branch/HEAD、`git log`、既存の未コミットファイルを調べる。意図しない上書き厳禁。ブランチは上記製品版ブランチを使用。
2. [Issue #4](https://github.com/jakymiku/Aredoko/issues/4)、`docs/spec.md`、`docs/api.md`、`docs/ui-audit.md`、比較用WinUIのXAML/C#、PR #2の索引実装を把握する。
3. 最初のコミットは**比較用とは別フォルダに、起動できるWinUI 3製品版の骨格＋ローカルAPI接続＋ログ/エラー表示**。Windows環境がなければ検証不能を明記し、実行環境に依存しないテストは先に作る。
4. 次に、**許可されたテスト用フォルダだけ**登録→PR #2の読み取り専用索引でスキャン→作品一覧/検索へ表示。スキャン進捗とキャンセルの実装は実測・設計に応じた範囲で。
5. その次に、作品の詳細/タグ/お気に入り/未確認の編集・保存・再起動後保持。旧APIの機能を退行させず、実ファイルを移動・削除・リネーム・変換しない。
6. Fluent UIを磨く。コンパクト検索/広い一覧/詳細編集/レスポンシブドロワーの一貫性、仮想化・アクセシビリティ・キーボード操作を見直す。
7. 各段階でテスト、コミット、残タスクを記録。製品版ブランチから**Draft PR**を作り、実機確認済み/未確認を分けて書く。**ユーザーの指示なくmainや既存PRをマージしない。**

## セキュリティ・データの境界
- 元メディアを**書換え・リネーム・削除・移動しない**。実ファイル走査はユーザーがGUIで指定した範囲のみ。キャッシュ/サムネイル/DBは別保存先へ。
- 購入作品、私物ファイル、個人パス、ローカルDB、アクセストークン、AIモデルをGitにコミットしない。ネット送信・モデルダウンロードなし。localhost外にサーバーを公開しない。
- Git管理下の比較試作や`generated`ディレクトリを壊さない。SDKやOS設定を勝手に変えたり、管理者権限の変更・常駐処理を無断導入しない。
- 不確実なAPI・WinUIの仕様は実コード/テスト・公式ドキュメントで確かめる。修正作業は**実装と検証**まで。曖昧な成功報告をしない。

## 参照先
[PR #1 UI試作](https://github.com/jakymiku/Aredoko/pull/1) · [PR #2 索引](https://github.com/jakymiku/Aredoko/pull/2) · [PR #3 GUI比較](https://github.com/jakymiku/Aredoko/pull/3) · [Issue #4 MVP実装指示](https://github.com/jakymiku/Aredoko/issues/4)

> Codexが作業を終える都度、この文書の「今どこまで進んだか」を更新する。単発チャットを唯一の作業記録にしない。

## 実装進捗 2026-10-11（Codex）
- 開始HEAD: `9c1b2aa` の製品版ブランチを確認。既存PRは未マージ。
- 公式インストール済みテンプレートから src/Aredoko.WinUI を新規作成。比較用generatedには触れていない。
- 最初の起動骨格にAPI接続と再試行/失敗表示を追加。テンプレートのNuGet参照を復元済みバージョンに固定。
- dotnet build src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Release -p:Platform=x64 --no-restore -v:q: 成功、警告0/エラー0。
- この時点ではGUI操作未検証。続いて読み取り専用索引との統合を実装中。

### 製品版の縦切り実装（実機検証済み）
- 起動骨格コミット: `acfb0c2`。以後、独立した製品DB/API、PR #2から必要な索引ファイルだけを移植、WinUI一覧/タイル/検索/詳細保存/フォルダ登録を追加。
- Python 28テスト成功。再起動時のSQLite接続リークをテストで検出して修正。元ファイル不変、永続化、消失/未接続、キャンセルのロールバック、再起動復旧、同意・トークンを検証。
- .NET Releaseの8チェック成功（リフレクションJSON無効、Unicode、dirty、古い検索応答）。WinUI Releaseビルド成功、SDK由来IL2104警告2件が残る。
- 開発用起動スクリプトと制約は docs/winui-mvp.md。Sandbox実行ファイルなしのためローカルWindowsで実機GUIテスト実施。検証用75ファイルの登録・同意・走査・一覧・検索・タグ/お気に入り保存・タイル切替・ページ移動・未保存の継続/破棄に成功。実スクリーンショットを確認。ランチャー経由の終了/再起動後にWinUI上で保存タグを確認。
- 起動骨格 `acfb0c2` に続く実装コミットはこの節を含むコミット（`git log -1`で確認）。PRは比較ブランチをbaseとする積み重ね方式。既存PRをマージせず、元デモ/API/比較generatedを保持。
- 手動コードレビュー実施: 再起動時のDB接続リーク、選択解除後の古い編集表示、ナビの二重破棄確認を修正。JSON/編集状態/API通信は純粋C#層に分離。画面調停はcode-behind、MVVM Toolkit未導入。
- 未検証/制約: 高DPI・ライトテーマ・狭幅の実機操作、フォルダピッカー自体の操作、スクリーンリーダー、1TB/数万件の実ファイル負荷、Native AOT、配布インストーラー。WinUI analyzer未導入なので解析未実施（無断依存追加なし）。SDK IL2104警告2件を抑制せず残している。日本語文言のリソース化は後続。
- 機能上の残り: フォルダを本単位にまとめる機能、サムネイル/読書、AI/OCR/Komga、ネイティブ一括編集、移動同定、複数棚の詳細仕様。現状はファイル単位。スキャン再開は最初からの原子的再走査。長時間走査中のメタデータ保存はSQLiteロックで失敗し得るので編集内容を保持して再試行する。
- 次の3手: (1) Draft PRをレビューしてこの基盤を固める、(2) 高DPI/狭幅/ピッカー/アクセシビリティと大規模スキャン中の応答性を検証・改善、(3) 画像フォルダ/ZIPを作品として扱う仕様とサムネイル縦切りを実装。

### 今回の提出
- 実装HEAD: `eb461f0`（起動骨格 `acfb0c2`）。この追記のみの後続コミットを最終HEADとしてpush。
- [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5) 作成済み。base: `feat/gui-framework-comparison-20261010`。未マージ。
- テスト用GUIとバックエンドは検証終了後に停止。通常起動は `pwsh -File tools/start-winui.ps1`。

### 次の段階（開始）
- 開始HEAD `4de6c67`、作業ツリーcleanを確認。既存Draft PR #5の製品ブランチで続行。
- 画像/CBZ/ZIPのサムネイル縦切りと基盤の競合修正を実装中。追加依存なし。元素材は読み取りのみ、ZIP展開保存なし。私物スキャンなし。
- スキャン中の保存は即座に409を返して編集を保持する方針。サムネイルは読み取り8MiB、デコード16MP、同時2、256px、メモリキャッシュ64件を上限とする。

### 画像/CBZ/ZIPプレビューと競合修正（完了）
- バックエンド実装コミット: b71c30b。UI実装HEADは後続の提出記録に記載。既存Draft PR #5を更新し、base/Draftを維持。
- 登録済み画像とCBZ/ZIPの自然順先頭画像を一覧/タイル/詳細へ表示。源8MiB・16MP・同時2・256px・派生PNGのLRU64件。アーカイブ512MiB/中央ディレクトリ4MiB/1万エントリ/圧縮比200の境界。元メディア不変、展開保存なし。選択/キャンセルで古い応答を捨てる。
- スキャン中の更新/登録/除外変更は即409。GUIは編集を保持して終了後に再保存可能。検索/種類の最終条件再適用、ナビ/保存/未保存確認の調停、除外設定の既存値読込を修正。
- Python python -m unittest discover -s tests -q: **40テスト成功**。源不変・自然順・破損/過大/圧縮境界・差分再走査・リパース置換・同時上限・実スキャン中の拒否/再試行・HTTP保護を検証。
- C# dotnet run --project tests/Aredoko.Core.Tests -c Release: **13チェック成功**。LRUと画素上限/整数オーバーフローも追加。WinUI Releaseビルド成功、SDK IL2104警告2件は未解消で抑制なし。
- ローカルWindows実機: tools/test-preview-ui-local.ps1 成功。画像/CBZ表紙、タイル/詳細、破損代替、連続検索の最終条件、タグ保存、700pxの詳細開閉、元ファイルの全ハッシュ不変。初回は縮幅後に詳細へ戻れず失敗、詳細ボタンと常時見える閉じるボタンを追加して再実行成功。スクリーンショットも目視確認済み。
- 元の tools/test-winui-local.ps1 も新規DBで再実行成功（登録/走査/選択clean/タグ・お気に入り/検索/タイル/ページ/未保存の継続と破棄）。Sandbox実行ファイルなしのためローカル実機。私物スキャンなし。
- WinUIコードレビュー実施。Windows標準コーデックと純粋C#方針層を利用。WinUI analyzer未導入なので解析未実施。文言リソース化/MVVM拡張/高DPI/ライトテーマ/スクリーンリーダー/ピッカー本体/1TB実負荷/Native AOTは未検証。700pxドロワーは確認済み。
- 残り: ファイル単位の索引。画像フォルダの作品化、PDF/動画/音楽プレビュー、読書/OCR/Komga/AI、永続サムネイルキャッシュ、移動同定、配布は未実装。以前の節の「サムネイル未実装」「狭幅未検証」「保存タイムアウト」はこの追記で更新。
- AI検索時期の質問を受け、次はAI試作を優先する案: [ai-search-plan.md](ai-search-plan.md)。EmbeddingGemma 2は検索、Layaは意図/種類の補助。laya-mlxはMac向けなのでWindowsでは本家Layaを検証。依存/モデルはまだ導入していない。
- **次の3手:** (1) 分離AI環境・依存・モデルの具体的導入案を提示、明示承認後にGPU動作/VRAMを測る、(2) 数百〜数千件の名前/タグ/画像/表紙をEmbeddingGemma 2で索引化してWinUI意味検索と日本語評価を実装、(3) Laya多言語の意図/種類補助を比較評価し、数万件向け差分索引・中断再開を固める。

### プレビュー段階の提出
- 実装HEAD: 86eed50（バックエンド b71c30b）。この提出記録のみの後続コミットをpush。
- Draft PR #5: https://github.com/jakymiku/Aredoko/pull/5 。比較ブランチbaseを維持、未マージ。
- 検証用アプリを閉じ、ランチャー終了コード0と専用バックエンド停止を確認。AI環境/モデルは未導入。


### AI検索段階（2026-10-12開始）
- 開始HEAD 701730d、製品ブランチclean。Issue #4/AGENTS確認済み。
- ユーザーが専用AI環境・EmbeddingGemma2取得・生成素材GPU検証を明示承認。追加条件: 回線85Mbpsのため合計約6MB/s以下。ローカルCONNECTプロキシで全依存/モデルTLS受信を共通制限し、Xet/transfer高速経路を無効にして実行中。システムPython/ドライバーは変更しない。
- Python3.11既存、RTX4070Ti12GBを実機確認。固定CUDA版torch2.9.1、sentence-transformers6.1.0、transformers5.19.0、EmbeddingGemma2固定revisionで分離。AI索引/API/GUIを実装中、意味検索成功はまだ未確認。

### EmbeddingGemma2初回実装・実測（2026-10-12）
- 専用.venv-ai、固定モデルを承認済み手順で導入。依存/モデルのTLS受信は合計6,000,000bytes/sの共通上限。初回取得4,482,870,732TLS bytes/968.3秒（インストール時間含む）、追加torchvisionも同じ上限。システムPython/SDK/GPUドライバー変更なし。Layaは導入していない。
- stdlibカタログから分離Pythonプロセスでオフライン推論。SentenceTransformer text+vision、audio encoder無効、bf16 CUDA（CPUはfloat32）。入力は名前/タグ/相対名と、既存安全リーダーの画像/CBZ/ZIP先頭画像。PDF/動画/音楽の中身や本の本文は未解析。
- sibling AI SQLiteに768次元の正規化float32、text/cover別、固定モデルprofileとsource/metadata指紋を保存。初版は登録済みpresent対象の先頭最大2,000件。途中キャンセル/再起動中断状態/保存済み分再利用、更新済みタグや源の旧vector除外、現在の除外/お気に入り等フィルタを実装。AIキャッシュ破損時も通常検索は起動可能。
- GET /api/library/ai/status、POST index/cancel/search追加、既存token/Origin保護。実推論中の競合を拒否。WinUIにAI索引の進捗/作成/中断画面、AI意味検索とAI画像・表紙の切替を追加。空検索は通常一覧を表示。通常検索/API/Web比較は維持。
- 実モデルの生成17件検証成功: 日本語言い換え「傘が必要な暗い都会の景色」→雨の夜の街並み.wav（名前だけの入力）、cover専用で「青い画像」→image-01.png、「赤い表紙の本」→book-03.cbzが各1位。破損源はテキストのみ、元ファイル全ハッシュ不変。最終warm検索104–106ms、PyTorch peak allocated 931.8MiB（OS/プロセス全GPU消費ではない）。初回全検証40秒、warmファイルキャッシュの回では約12–16秒。個人ライブラリ/数千件への速度や精度は未実測。
- textとcoverのcosine最大値で混ぜた初回は色順位が名前側に偏った。coverのみの明示モードで上記色条件が改善。複合検索の順位補正・意図判定は未完成。意味検索は全候補を類似順で返し、適合閾値はまだ校正していない。
- Python **51テスト成功**、C# **13チェック成功**。新テストの既知vectorはAPI/永続化の検証であり精度証拠ではない。別途tools/test_ai_model.pyで実CUDAモデルを検証。Releaseビルド成功、SDK IL2104警告2件は引き続き未解消。analyzer追加なし。
- 元のnativeメタデータ回帰テストは新しい検索切替を加えた版でも成功。**AI GUI通しテストはFAIL/未完了**: 初回は非同期登録待ち不足、1回目再実行はフォルダ画面終了直後の待ち不足を修正。2回目再実行でGUIから17件の実CUDA索引作成が成功したが、テストCLIがAI意味検索という同じ表示名のListItem/Textを重複検出し停止。選択肢にModeLiteral/ModeSemantic/ModeVisualの専用AutomationIdを追加しビルド済みだが、その修正後のGUI再実行は未実施。winui-ui-testingスキルの最大2 fix-and-rerun cyclesに従い、再試行を打ち切って失敗を残す。検索画面のタグ保存/dirty keep/文字モード戻しについて新AI通しテスト成功は主張しない。
- AI GUI失敗時スクリーンショットとJSON結果を保存して目視確認（generated test artifacts、Git対象外）。源カバーと一覧/詳細/検索切替のUIを確認。Sandbox不在でローカルWindows。アプリ終了時に所有AIプロセス2つとAPIポートが消えることを確認済み（親終了監視）。
- **次の3手:** (1) 専用IDを使うAI GUI通しテストを次回再実行し、選択/保存/未保存保持/モード切替を完走、(2) 明示選択した小規模サンプルで日本語・同人誌表紙の精度と混合順位、2,000件の初回速度を評価、(3) Laya multilingualの具体的導入案を作り検索意図/種類補助を比較し、索引上限拡大/大規模応答性へ進む。今後のダウンロードも6MB/s上限を維持。

### AI初回実装の提出
- 実装HEAD: 8dd25ff。後続はこの提出記録のみ。Draft PR #5の同じbaseへpush、未マージ。
- 実CUDA検索・51 Pythonテスト・13 C#チェック・Releaseビルド成功。AI GUI通しテストは選択肢専用ID追加後の再実行待ち。
- 検証用GUI/API/所有AIワーカー停止確認。導入済みモデル/環境はローカルのみ、Git対象外。


### AI GUI通し検証の続行 2026-10-12（完了）
- 開始HEAD: `28c5923`、作業ツリーclean。Issue #4とAGENTSを再確認、既存Draft PR #5のブランチで続行。
- 検索メニューがmain/PopupHost双方から同じUIA peerを露出するためAutomationIdだけでも2件に一致。テストを実際のPopupHost HWNDに限定し、非同期出現と選択値を待つ方式に修正。アプリ本体の追加変更なし。
- 新しい生成素材用DBでnative AI通しテスト **PASS**。GUIから17件CUDA索引、日本語言い換え検索、結果選択/タグ保存、AI画面を開く際の未保存確認で「編集を続ける」が内容を保持、名前・タグ検索への復帰、画像・表紙の色検索/タイル表示まで完走。生成素材の全ハッシュ不変。3枚の実スクリーンショットを目視確認。
- Python51テスト、C#13チェック成功。Windows Release成功。初回buildのSDK IL2104警告2件は未解消、incremental build警告0を修正の証拠としない。analyzer未導入。
- アプリ終了後に所有モデルワーカー2つ/APIポートが停止、ランチャー終了0を確認。同じ検証DBを再起動してタグ/AIベクトル保持も **PASS**。GUI編集欄に保存タグを読戻し、再索引なしの表紙検索がCUDAで青い先頭候補を返した。再起動用2枚も実画像を目視確認。

- 再起動検証で待機ヘルパーのIsEnabledがCLIの文字列Falseをtruthyと扱う問題を検出してTrueとの比較に修正。初回モデル読込中の検証API競合はテスト側の待機不備。修正後の冷間起動で検証完走。tools/test-ai-ui-local.ps1 -RestartOnlyを追加。
- WinUIコードレビュー: 今回アプリのXAML/C#追加変更なし。既存AIダイアログの非同期調停/未保存保持とテストのwindow scope/value waitを手動確認。以前のcode-behind/リソース化/analyzer/AOT制約は残る。
- Layaの具体的な実験設計を docs/laya-evaluation.md に追加。Windows向けupstream PyTorch/multilingualを候補に、日本語意図判定と検索順位改善を別々に評価。confidence未校正のため閾値だけで自動フィルタしない。既存依存を固定し共有6MB/sを再利用。Layaの実インストール/ダウンロード/推論はまだ行っていない。
- **次の3手:** (1) Layaのモデルrevision/正確な容量と依存差分を確定して明示セットアップを用意、ローカル日本語分類/フォールバックを比較、(2) 明示選択したサンプルで意味/画像検索の順位・混合方式と最大2,000件の初回速度を評価、(3) 測定に基づき上限拡大/大規模索引の応答性、作品フォルダ単位/本文OCRを順に進める。現状は最大2,000件の開発プレビュー、数万件/1TB規模や実作品精度は未検証。

### AI GUI検証の提出
- 検証実装HEAD: `5d0f46a`（AI本体: `8dd25ff`）。後続はこの提出記録のみ。既存Draft PR #5の同じbaseへpush、未マージ。
- 実CUDAのGUI通し/再起動保持PASS、Python51テスト/C#13チェック成功、Windows Release成功。スクリーンショット5枚を目視確認。生成素材は全ハッシュ不変。Layaは評価設計のみ。
- 最終の検証アプリ/API/所有モデルワーカー停止、ランチャー終了0を確認。作業内容をPR説明へ反映。

### モデル交換対応（2026-10-12完了）
- 開始HEAD fa30b9c、clean/Issue #4/AGENTS確認。ユーザー要望によりEmbeddingGemma 2固定設定をモデルprofileへ分離。
- 起動時の設定ファイル選択、adapter/次元/入力能力/immutable revision/promptを検証し、異なるprofileの索引を別DBへ保存。既存標準profileは既存AI DBを再利用する設計。新しいモデルやLayaのダウンロードは行っていない。

- app/ai_profiles.py に検証済みJSON profile、app/ai_adapters.py に登録式loader、app/ai_vectors.py にモデル非依存vector契約を追加。EmbeddingGemma2 text/coverと汎用Sentence Transformers text-onlyを分離。既存標準profileはlegacyキー/DBを維持。他profileはID/revision/adapter/次元/入力/prompt/precision/前処理契約の識別で別DB。label/同一重みの配置変更のみは再利用。workerの実次元/完全profile照合、返却vector検証で混在を拒否。
- tools/start-winui.ps1 -AIProfile <JSON> / backend --ai-profileで再起動時に選択。切替時に新索引を作成、戻すと元の索引を再利用。GUI AI索引画面に選択モデルと対応入力を表示。text-onlyの画像モードは説明付きで失敗し、通常検索を維持。GUIモデルピッカー/稼働中切替は未実装。
- 明示setupにも-AIProfileを追加、既存pin/合計6MB/s制限を再利用。download途中の再開用source記録と別revisionの上書き防止。今回追加download/installなし。互換派生モデルは設定交換、異なる構造はadapter追加が必要。どんな非検閲モデルでも自動互換とは主張しない。
- Python **61テストPASS**、C# **13チェックPASS**、Windows Release PASS（既存SDK IL2104 2件）。不同次元/同次元別revisionの分離、旧profileへの復帰、prompt/能力/誤handshake/不正設定/取得中断を検証。汎用adapterはモック契約のみで別実モデル未検証。
- 既存ローカル重みを用いた実CUDA検証PASS: 標準text+vision → text-only/float32 → 標準へ戻し、索引分離と再構築なし再利用、2件の生成名前で日本語top hit/源hash不変を確認。これは2つの設定の試験であり、別重みや将来の派生モデルの精度証明ではない。
- native GUI PASS: explicit profileで生成17素材の新規索引/意味検索/表紙検索/保存/dirty keep/文字モード復帰。native legacy互換 PASS: 変更前の17件AI DBをそのまま開き、保存タグとCUDA表紙検索を再索引なしで使用。モデル表示を含む6枚の実スクリーンショットを目視確認。私物フォルダ未走査。
- WinUIコードレビュー: 新規XAML/API追加なし、TextBlockのモデル表示と非同期dialog調停を確認。JSON DOM/既存テーマ/AutomationId維持。WinUI analyzerなし、AOT/高DPI等の旧未検証項目は継続。
- 開発手順 docs/model-profiles.md、default sample config/ai-profiles/embeddinggemma-2.json。model/revision/次元/prompt変更が再索引条件、既存タグ/棚とは別管理。モデルmarkerは由来の宣言で全重みの暗号学的検証ではない。
- **次の3手:** (1) Layaもembeddingとは別の判断用interfaceに分離してoffline評価セット/明示setupを実装、(2) GUIのモデルprofile選択/不足モデル案内を追加、(3) 実サンプルで順位/索引速度を評価し2,000件を超える索引へ拡張。Laya実導入/別checkpoint取得はまだなし。モデル交換の基盤は完了。

- 最終互換性レビューでlegacy条件を現在のDEFAULT_PROFILEから切り離して歴史的設定へ固定。将来defaultモデル/前処理契約を変えても旧DBを誤再利用しない回帰テストを追加。前処理変更はVECTOR_CONTRACT更新が必要。

### モデル交換対応の提出
- 実装HEAD: `64b0af9`（本体 `6fa3e69`＋将来default変更の互換性固定）。後続はこの記録のみ。既存Draft PR #5へpush、未マージ。
- 61 Pythonテスト、13 C#チェック、WinUI Release、実GPU profile切替、新規GUI通し/旧索引GUI互換の検証成功。所有AIワーカー/API/GUIの終了確認、ランチャー終了0。追加モデル取得なし。
- 最新仕様/制約/次の3手は上記と docs/model-profiles.md。別実モデルや将来checkpointは未検証、Layaは次段階。


### Laya判断実験（2026-10-12開始）
- 開始HEAD 2ea24f0、clean/Issue #4/AGENTS確認、Draft PR #5継続。EmbeddingGemma 2公式カードはpost-training alignment/safety tuning/output moderationなし、学習データのフィルタありと明記。Aredokoの検索に内容拒否処理なし。
- 固定Laya 0.4.2/多言語revision 1720e3e3357cfe1e281542e223f8273b0890ca34、モデル678,201,614bytes+wheel380,522bytes。既存依存は条件を満たしpip check成功。ユーザーが新しいLaya取得/GPU検証を明示承認、共有6MB/s制限で取得中。
- 計画モード/既存依存不変更/--no-deps/固定hash/モデル整合性/中断再開/別revision拒否を実装、setup4テストPASS。embedding profileとは別の判断interface/owned offline worker/提案専用APIを実装中。現時点で実モデル精度・GUI提案は未検証。


### Laya独立判断provider・実GPU評価（2026-10-12完了）
- 実装HEADはこの節を含むコミットを後続の提出記録で確定する。製品ブランチ/既存Draft PR #5/baseを維持。既存WinUI/Web/embedding profile/旧索引/タグ・棚・手動検索を保持。
- app/search_intent.py にベクトル検索とは別の判断interface、app/laya_process.py / laya_worker.py にowned stdin/stdout worker、app/laya_config.py に固定ID/revision/package/全artifact SHA256。300文字・応答32,768文字・同時1・冷間60s/推論5s・失敗cooldown30s。推論はローカルのみ、HF offline+Python socket接続遮断、ネットワーク接続試行0。Laya 0.4.2 +固定多言語重みを明示承認後に取得。共有6,000,000bytes/s、679,568,032TLS bytes/180.14s。既存依存バージョン全不変/pip check成功、system/driver変更なし。
- tools/setup-laya.ps1 は無指定planのみ。-InstallAndDownloadで--no-deps/固定wheel hash/取得中断再開/別revision上書き拒否/モデル全hash検証。upstream tokenizerのリスト→mapping互換修正を許す場合も全original configを復元して固定hashと照合。最初の再起動実験first-01でその差を検知、修正してfirst-02/03成功。
- GET /api/library/intent/status、POST /api/library/intent/suggestに既存token/Origin保護。既定は無効、--laya-intent / tools/start-winui.ps1 -LayaIntentで開発者が明示起動。結果はexperimental提案のみ、手動source/kindをrequestedとして保持、検索本体は呼ばず種類で絞らない。missing/busy/timeout/malformedはnull提案で通常検索維持。GUI提案control・自動切替/フィルタは追加していない。
- 固定36件の架空日本語fixtureを追加（development24/held-out12）。実CUDA: 意図16/24+10/12=26/36、種類16/24+6/12=22/36、両方14/36。全36推論成功。プロンプト/閾値を結果に合わせて調整していない。漫画→archive、種類不明→archive等の誤分類を記録。held-outは評価済みであり、以後の調整で未見検証と再主張しない。
- 生成17素材/6検索の実EmbeddingGemma比較: Laya source提案を実験内だけで適用。赤表紙は期待順位2→1、青表紙は1→2、残り4は同順位。top1はmixedもLayaも5/6、全体改善を確認できずGUI採用条件未達。sourcehash不変、私物未走査。本文/OCR/音声動画内容は依然未解析。
- 実測first-03: 冷間first query13,133ms、残り35の中央値40.65ms/p95 43.78ms、PyTorch GPU peak allocated1,501MiB（driver全使用量ではない）。実interpreter Working Set1,965MiB/peak2,707MiB、Private Bytes5,766MiB（commitでresident RAMとは異なる）。first-02の3MiBはvenv redirector誤計測で無効。CPU/量子化/idle unload未検証。
- Windows venv redirector/実interpreterの2プロセスを区別し、workerでAPI親と直接OS親の両方を監視。tools/test_laya_api.py 実CUDA/HTTP PASS: cold読込中literal12.78ms、競合fallback5.76ms、異なる手動条件を保持、強制timeoutでrealworker終了/文字検索継続、os._exitによるowner突然終了でもrealworker終了。終了後CIMで全所有laya/embedding workerなしを確認。
- Python **76 tests PASS**（新setup4/intent11、既存61を保持）、C# **13 checks PASS**、WinUI Release PASS（旧SDK IL2104警告2件を抑制せず維持）。launcher構文PASS。コードレビュー: XAML/C#変更なし、JSON/非同期GUI/テーマ/AutomationIdの既存コードを維持。stdlib APIにtorch等をimportせず、全外部推論依存をworkerへ分離、有限probability/label/truncation/worker identity/provenance/busy/閉鎖・再起動境界を手動確認。analyzerなし、今回native GUI操作なし。既存GUI実機成功は前節の証拠を参照。
- ローカルignored evidence: data/laya-setup/result.json、data/laya-evaluation/first-03/result.json、api-01/result.json。docs/laya-evaluation.mdに手順・全結果・不採用理由と次の評価条件を記録。モデル/venv/DB/スクリーンショット/私物はcommit対象外。
- **次の3手:** (1) Laya質問/選択肢をdevelopment文で改善、選択肢順序/棄権と新しいheld-out集合を用意し、種類の推測は当面提案のみ、(2) text/cover混合順位を別途改善して実検索の総合利益を再測定、(3) GUIモデルprofile選択と明示サンプル/2,000件超の索引規模を進める。精度・順位・初回待ち・メモリを満たしてからGUI提案を追加する。
- 最終レビューで既存material条件を提案APIが拒否する不整合を修正。手動kindは既存TYPESを正として素材も保持し、判断ラベルの種類数で制限しない。質問/fixture/実測分類には変更なし。intent11テスト再実行PASS。


### Laya実験の提出
- 実装HEAD: 1e49592。後続はこの提出記録のみ。同じ製品ブランチとDraft PR #5へpush、base維持/未マージ。
- GPU推論・独立API/競合/timeout/親終了の検証PASS。Layaの日本語精度・検索順位の改善はGUI採用条件未達、提案APIは開発者の明示起動のみ。通常検索/GUIを保持。
- Python76/C#13/WinUI Release PASS、SDK IL2104 2件は既存のまま。質問/fixture変更なく最終manual material条件だけ修正・intent11再検証PASS。
- 検証用APIと所有Laya/EmbeddingGemmaプロセスは停止済み。モデルとvenvはローカルに保持、private/generatedデータはGit対象外。


### 日本語判定・混合順位改善（2026-10-12開始）
- 開始HEAD d7d7fb9/clean、Issue #4/AGENTS/PR #5 base確認。既存ローカル重みのみ使用、追加取得や私物走査なし。下着デザイン等の非露骨な架空素材検索を評価へ追加。内容による拒否処理は追加しない。
- v1質問を保ち、英語/短い日本語のv2候補と順序一致確認を実装中。判断契約hashに質問文と選択肢順序を含め、workerと照合。kind material候補を追加。旧24+新8のdevelopment32で候補を選び、旧held-out12はregressionに改称、新held-out24を選定後の検証に限定する。現時点で候補改善は未確認。

### 日本語判定・混合順位改善の完了（2026-10-12）
- 実装HEADは後続提出記録で確定。同じ製品feature/Draft PR #5/base維持。追加download/installなし、導入済み固定GPUモデルのみ、私物走査なし。内容拒否処理なし。
- AI意味検索の既定をmean-rrf（k60・cosine同点は平均順位・利用可能modalityで平均）へ変更。旧maxと明示text/cover cosineを維持し、launcher -AIRanking max/API rankingで復帰可能。候補filter/fingerprint/negative score維持。vector schema/profile/namespaceは変更せず再索引不要。応答ranking/score_kind追加、semantic_scoreは尺度が方式で異なりconfidenceではない。docs/ai-ranking.md。
- 実EmbeddingGemma CUDA/生成23素材14文×kind有無28条件: top1 max25→fusion27（旧6文12条件10→12、新8文16条件15→15）、悪化0。赤表紙期待CBZ2→1、青表紙1維持。「下着のデザインテンプレート」架空PSD名前・タグで両kind条件1位。ランジェリーひな形の未指定条件はPSD2位/関連PDF1位のまま。音声動画/PSD/PDF内部は依然読まず、個人ライブラリ精度/1TB速度未検証。sourcehash不変。
- Laya registry候補/質問・順序hash/判断契約v2、二順序推論とhead別棄権、cover＋未対応kind(audio/video/material)矛盾時intent棄権を実装。手動source/kind保持、確率閾値/自動検索なし。旧intent＋新日本語kindのhybridをdevelopment32で選定してから、新24を検証。旧held12はlegacy-regression、新24も以後未見扱い不可。
- 実Laya fresh24: v1 intent raw/effective17/17、kind11/12 → hybrid intent17/17、kind13/15。hybrid intent提示18/正解14、kind提示18/正解12、各6件棄権。warm81.53ms/cold12,937ms/PyTorch GPU peak1,506.02MiB/networkcalls0。種類は小幅改善、GUI gate未達。既定無効の-LayaIntent実験APIだけhybrid/order-checkを採用、GUI control/自動mode/filter追加なし。docs/laya-evaluation.md。
- 実HTTP新契約PASS: cold中literal10.42ms、競合5.98ms、manual保持/order証拠/timeout realworker停止/literal継続/os._exit親終了停止。モデル/依存変更なし。
- Python **90 tests PASS**、C# **13 checks PASS**、WinUI Release PASS（旧SDK IL2104 2件、抑制なし）、launcher/native-test構文PASS。新規native GUI実機PASS: generated17登録/索引CUDA/意味検索/保存/dirty keep/文字復帰/赤表紙fusion第一候補/max復帰/青coverタイル/sourcehash。4枚実スクリーンショット目視確認。Sandboxなしでlocal、今回再起動GUIは未実行（過去結果は前節）。検証用API/GUI/worker終了済み。
- WinUIコードレビュー: XAML/C#変更なし。既存async検索・stale判定・native ListView/60paging・JSON DOM・token/Origin・ThemeResource/AutomationIdを確認。追加計算は既存2,000上限内、Laya/torchは隔離workerのみ。WinUI analyzerなし、高DPI/Light/HighContrast/reader/ピッカー全体/AOT/配布は継続未検証。
- ignored証拠: data/ai-smoke/ranking-01、data/ai-ui/ranking-01/full、data/laya-evaluation/v2-dev-01/v2-hybrid-guard-dev-01/v2-heldout-01/api-v2-01。fake fixtureだけGit管理し、models/venv/DB/個人paths/PNG証拠はcommit対象外。
- **次の3手:** (1) GUIでモデルprofile選択と不足時案内を追加（既存旧索引互換/手動mode維持）、(2) ユーザー選択の実サンプルで混合順位と追加の未見日本語判定セットを評価（Layaは精度を満たすまでGUI提案保留）、(3) 2,000件超の索引を段階的checkpoint/増分・resource上限で拡張。本文/OCR/音声動画内容は別段階。

### 混合順位・Laya v2の提出
- 実装HEAD: e21c7aa。この後続コミットは提出記録のみ。同じfeatureブランチ/Draft PR #5へpushし、stacked base維持・未マージ。
- Python90/C#13/WinUI Release/実CUDA評価/実HTTP lifecycle/WinUI local生成17素材フローPASS、4枚目視確認。旧SDK IL2104 2件は継続。所有API/GUI/embedding/Laya worker停止を確認。
- mean-rrfはGUI意味検索の既定、maxへ復帰可・旧vector再利用。Layaは新未見24の精度不足でGUI採用保留、明示実験APIのみ。最新仕様と次の3手は直前節・docs/ai-ranking.md・docs/laya-evaluation.md。

### GPTチャットへの引継ぎ（2026-10-12）
- ユーザーがCodex残量節約のためGitHub Markdownへ進捗と再開手順を残すよう依頼。開始HEAD afb189c/clean、機能実装HEAD e21c7aa。今回は文書のみで新規機能/テスト再実行なし。
- docs/chat-handoff.mdをWinUI/AI実装済みの最新状態へ更新。古い「GUI未決定/AI未実装/Web監査が次」を置換。完了機能・90Python/13C#/Release/実GPU/native結果・Laya精度制約・未検証・主要ファイル・コマンド・そのまま貼れる依頼文を収録。
- 次の3手はGUI profile選択/不足案内、選択された実サンプルと新しい未見集合、2,000超の索引。チャットにPC/モデル/venv/スキルが転送されるとは扱わず、private repoアクセス不可時は実ソース共有が必要と明記。
- 同じfeature/Draft PR #5へ文書更新をpush。base/既存PR/未マージを維持。文書差分チェックのみ実行、前回の機能検証結果は再実行結果ではない。

### 2026-10-12: WinUIのモデルprofile選択（GPT引継ぎ作業）
- 開始HEAD `9190114`。変更は同じ `feat/winui3-production-mvp-20261011` と既存Draft PR #5に追加。従来のモデルprofile、旧default index、mean-rrf、Laya experimental API、個人データ不変更。
- `app/ai_settings.py`でGUI用ローカルprofile選択を検証・atomic保存し、起動時引数 `-AIProfile` を優先する。無効profileやモデル重み不足を表示し、**実行中のworker切替とモデルDLはしない**。選択肢は既定とignored `data/ai-profiles/*.json`。settingはユーザーの `%LOCALAPPDATA%/Aredoko/settings.json`（テスト時 `--ai-settings`）。
- `app/production_server.py` の認証済みprofile GET/POST経路と `src/Aredoko.WinUI/MainPage.xaml.cs` の「AI索引」ダイアログにprofileセレクタ、再起動案内、不足・無効モデルの警告を追加。既存のAPIと編集ロック・dirty制御は変更せず、AI使用不能でもliteral文字検索可能。
- `tests/test_ai_settings.py`と `.github/workflows/ai-profile-checks.yml`、`docs/model-profiles.md`を追加/更新。テストは一時フォルダ・架空DB、no download/ no user media。
- テスト状況: Windows CIによるPython AI単体テストとC# Releaseチェックを実施。WinUI Releaseでは.NET linkerの `NETSDK1102`（SelfContained未指定）が初回CIで出たため、CIビルド引数を `-p:SelfContained=true` に修正。**最終CI結果は対応するGitHub Actionsで確認**。GUI画面の実機操作・再起動後の実モデルロードは未検証。成功と混同しない。
- 次の3手: ①JakyのWindows実機で `tools/start-winui.ps1` からAI索引→候補を設定→終了/再起動してactive表示と旧索引復帰、text-only cover拒否、missing/invalidからliteral復帰を検証、②UIの説明文/高DPI・ライトテーマ・アクセシビリティを確認、③新しい実サンプル/未見データで順位を確認し2,000件上限拡張の設計を進める。

### チャット実装を実機へ戻す検証（2026-10-12開始）
- ローカル9190114/cleanからGitHubのf4273ffへfast-forwardし、チャット側のGUI profile選択/API設定/CI修正を全保持。Issue #4/AGENTS/PR #5を確認、base/Draft維持。
- 取り込んだ状態でPython96/C#13/WinUI Release（SelfContained=true）PASS、旧IL2104 2件。native確認は別作業。私物未走査・追加取得なし。
- 最初の画面probeはno-buildのPlatform指定がなく旧bin/Releaseを起動したためモデル欄がなく失敗。実機対象をPlatform=x64/SelfContained=trueへ揃えて最新dialogの表示・目視確認に成功。旧出力の結果を新コードの不具合・成功としない。
- launcherもCIと同じx64/self-contained指定へ揃え、テスト用-AISettingsを公開し個人AppDataを変更しない。profile候補のAutomationIdと人向けactiveモデル名、保存中の重複操作防止を追加中。実CUDA再起動/旧索引復帰/不足・破損のnative検証はこれから。

### GUI profile実装の実機確認・残件（2026-10-12）
- 実装HEADは後続提出記録で確定。f4273ffのチャット側実装を維持。launcher x64/SelfContainedをCI/実機と統一、-AISettingsで専用保存先を指定可能にした。候補AutomationId、人向けactiveラベル、保存中重複操作防止を追加。新規download/installなし、私物未走査。
- Python96/C#13/WinUI Release PASS、既存SDK IL2104 2件、launcher parse/diffチェックPASS。変更後ReleaseもPASS、初回フルと増分0警告は別で、IL2104解消とは主張しない。
- native baseline probeは古いbin出力のためモデル欄なしでFAIL。Platform指定して最新dialog表示を確認。新native harnessは01ウィンドウ生成待ちでFAIL→02はGUI17件CUDA索引/profile保存/no hot swap後に検索方法PopupHost検出FAIL→03も同じpopup問題でFAIL。window/popupの2回修正再実行後はwinui-ui-testing skillの上限により同じ通し再試行を止め、未達を報告した。GUI selector保存は確認、text-only/missing/invalid再起動画面と最新dirty通しは未完。probe旧/最新、02保存後/失敗、03失敗の計5枚を目視確認。成功/失敗の両証拠を含み、通し成功と誤称しない。
- 新 tools/test_profile_preference_gpu.py の独立実HTTP/CUDAはPASS。03でGUI保存したtest preference/生成17DBのコピーを使用してtext-only次回適用/別索引17/日本語hit/cover非対応、設定保存hot swapなし、default復帰の旧17vector＋cover再利用（再構築なし）、不足/invalidでAI unavailable/literal17、corrupt保存に対しexplicit -AIProfile優先、sourcehash不変。GUIの通し成功ではなくAPI/GPUの証拠。同じ既存EG2重みの2profileで、別checkpoint未検証。
- ignored証拠 data/ai-ui/profile-probe-01/dialog-latest.png、profile-picker-01/02/03（全FAIL/部分到達）とdata/ai-smoke/profile-preference-01/result.json（PASS）。生成profileは厳密に作成したファイルだけcleanup。個人AppData設定未変更、検証用GUI/API/worker終了確認。
- コードレビュー: JSON DOM/async・native ListView・dirty guard/Origin-token/immutable index keyを維持。新C# APIは既存ComboBoxItem/AutomationPropertiesのみ、テーマstyleは既存platform。analyzer/Sandboxなし、高DPI/Light/HC/reader/AOT/配布未検証。ScrollViewer APIを調べたが現サイズのdialogは表示できたため不要なレイアウト変更なし。表示リソース化は将来課題。
- **次の3手:** (1) 保存済みfailure-tree.jsonからPopupHostの公開境界を診断し、新ターンでnative全profile再起動/不足/破損/dirty回帰、(2) 小さいwindow/DPI/themeの警告表示を検証、(3) 明示選択の実サンプル・新未見分類集合と2,000超の索引へ。Layaは依然実験APIだけ。

### 実機へ戻した作業の提出
- 実装HEAD 9e8efad。後続はこの記録のみ。f4273ffまでのチャット変更を全保持し、同じfeature/Draft PR #5へ通常push、base維持・未マージ。
- 新ランチャー起動指定/保存中操作を実装、96Python/13C#/Release・独立HTTP/CUDA再起動PASS。nativeはモデル選択/保存/索引まで確認、検索方法popup問題で通しFAILのまま。次回は残件を再開し、今回の部分到達を完全成功と扱わない。
- 文書差分チェック/実装レビュー済み。生成設定だけcleanup、所有GUI/API/worker停止。最新の次の3手は直前節。


### native profile回帰の再開（2026-10-12）
- ユーザーの「確認したよ続きをお願い」で前回残件を再開。開始HEAD b77506e/clean、Issue #4/PR #5/最新remote一致を確認。既存Draft/base/チャット実装を保持。新規取得・私物走査・個人AppData設定変更なし。
- 保存済み03のUIツリーで検索方法PopupHostがmain windowのchild paneとして公開され、list-windowsの独立window列挙条件が合わないと判明。検索方法を実キーボード操作＋選択値のUIA assertionに変更。
- 04はGUI索引操作後にidleのままでFAIL。ダイアログ準備を待って実クリックするよう修正し05を実行中。05はGUI17件CUDA索引/次回profile保存/no hot swap/日本語検索/再起動でtext-only適用まで到達。通し成功はまだ未確定。
- 次は文字専用索引/cover案内、default旧vector復帰、missing/invalid/override、dirty保護とfavorite再起動保持。結果・PNG目視・cleanupを確認後に記録を更新する。


### native profile再開の結果（2026-10-12）
- 開始b77506e/remote一致。C#/XAML/API/worker無変更、生成素材だけ。検索方法をfocus＋keyboard＋選択表示値assertionへ変更し、UIA child PopupHostの独立window検出依存を解消。dialog準備待ちとindex実クリック、API cleanupのfinallyを修正。
- 04 FAIL（index操作後idle）→05 FAIL（keyboardの前景安全拒否）→06は全モデル段階到達: default GUI17件CUDA索引/次回text設定/no hot swap、日本語検索、text-only再起動/別索引17/画像非対応GUI案内/literal復帰、default旧17vector再利用、missing/invalid再起動の警告/索引不可/文字検索、corrupt settingsへのexplicit override/GUI default再保存。
- **06通しはFAIL**: favorite保存直後のAPI確認が早すぎた。PNG/失敗UI tree/終了後read-only SQLiteでfavorite保存成立を確認（post-run-check.json PASS）。dirty keepとfavoriteのnative再起動は未到達。保存表示・APIの反映待ち、実tree toggle assertion、--editor-only、初期sourcehash記録＋finally hashを準備したが、**最後の修正はnative未再実行**。py_compile/--help/diffチェックPASS。skillの2回fix/rerun上限を守り、未達を残す。
- 全新PNGを目視:04 failure、05保存/text/失敗3枚、06の7モデル状態＋failure8枚。1200×820/96 DPI/darkの説明・警告は読める。02はUI pollよりAPI完了が先で「作成中」snapshot、04 PNGにはCLI合成tooltipあり。small-window/DPI/theme/readerは未確認、画像非対応時の中央汎用再接続案内は改善候補。
- Python96 tests/C#13 checks/x64 SelfContained Release PASS（既存IL2104 2件、抑制なし）。WinUI review:製品無変更、JSON DOM/native ListView/async/dirty/認証/モデルindex分離を維持。test側のUIA enableと保存完了を区別し、最終修正の実機確認は後続。analyzer/Sandboxなし。
- ignored証拠 data/ai-ui/profile-picker-04/05/06/result.json は全体FAIL（モデル段階到達を全体PASSと誤称しない）。06/post-run-check.json PASSでdisk favorite/UI tree on、source17のsize/mtimeと別fresh生成payload一致。06開始byte hashの保存なし、全byte hash不変とは主張しない。別生成ZIPはcontainer timestampが異なる。前回HTTP/CUDA profile-preference-01 PASSは再実行していない。
- 個人AppData/私物は無変更、download/installなし。05の所有API残留を確認して停止、cleanupを修正、06終了後の所有GUI/API/workerなし。作成test profileのみcleanup。read-only favorite monitorは最終段階未到達で停止、証拠に含めない。
- **次の3手:** (1) tools/test_ai_profile_ui.py --editor-only --output data/ai-ui/profile-editor-01 でdirty/favorite再起動だけ確認（重いモデル段階は再実装不要）、(2) 小window/DPI/themeの警告表示と非対応検索の案内、(3) 明示実サンプル評価と2,000件超索引。Layaは精度未達の実験APIのみ。


### nativeモデル切替確認の提出
- 実装/検証記録HEAD **0271dc1**。後続はこの提出記録のみ。同じfeature/Draft PR #5/baseへ通常push、未マージ。b77506eから続行しチャット変更を保持。
- nativeモデル段階は確認済み（default/text-only/旧索引復帰/missing/invalid/override）。全体は最後の保存待ちでFAIL、dirty/favorite再起動は未完。最終save-wait/editor-only修正はnative未再実行。この境界をdocs/model-profiles.md/chat-handoff.md/PRにも記録。
- Python96/C#13/x64 SelfContained Release（既存IL2104 2件）/py_compile/--help/diff PASS。製品本体無変更、12新PNG目視。所有test GUI/API/worker停止、生成profile cleanup、私物/個人設定/依存/重み変更なし。
- **最初に行う作業:** python tools/test_ai_profile_ui.py --editor-only --output data/ai-ui/profile-editor-01 。同名folderが既にある場合は新規suffixを使う。実GUIと保存済みPNGを見てdirty keep/次回favoriteを確認し、成功前に全体PASSへ書き換えない。


### 編集回帰の完了とWinUI画面整理（2026-10-12）
- 開始HEAD **aee9421** / 同じfeature/Draft PR #5/base。AGENTS/Issue #4/前回引継ぎを確認し、チャット側f4273ffと既存モデル/launcherを保持。実装HEADは後続提出節に記録。
- 前回未到達だった編集段階を `--editor-only` で確認。profile-editor-01は既定literalの不要なfocusでFAIL、現在値をUIA確認するよう修正して02は11 checks PASS。保存表示/APIを待ちfavorite保存、dirty keepの実text/DB保持、再起動後favorite API値/UI checkbox onを確認。
- 製品UI: 選択前/検索更新時の詳細paneを閉じ一覧幅を使う。検索見出し/Accentボタン/ヘッダー件数、タイトルSemibold/補助Caption、テーマ色の詳細枠。840 DIP未満は操作群を二段へ。AI dialog内容をScrollViewerにし、検索失敗時は名前・タグ検索/AI設定を案内して古い件数とページ操作を消す。
- native `--editor-only --layout-checks` のui-polish-02は **32 checks PASS**。1200×820一覧/タイル、700×620操作欄、不足profile dialogの候補/警告/閉じるbounds、保存/dirty/restart/生成元hash不変。最終6 PNGを全目視。ui-polish-01も32 checks PASSだが旧cleanup warningあり、foreground不要の所有HWND WM_CLOSEに改善した02は **4回正常終了/cleanup warningなし**。初回失敗と途中警告は証拠に保持。
- Python **96 tests PASS**、C# **13 checks PASS**、x64 SelfContained Release PASS（既存IL2104 2件）。py_compile/diff check。WinUI code reviewでnative Items/60paging、JSON DOM、async/stale/dirty、loopback認証、モデルindex identityを維持。analyzer未導入。
- 検証境界: editor/layoutは `actual_model=false/profile_verification=not_run`。前回06のモデル段階到達/全体FAILは歴史として保持し、今回の別バッチで未到達編集を確認。全GPU/profile通し、新AIエラー文での非対応mode操作は今回未実行。dark/通常DPIのみ、Light/HC/高DPI/reader/AOT/配布/1TB性能未確認。
- ignored証拠: data/ai-ui/profile-editor-01（FAIL）、02（PASS）、ui-polish-01/02（PASS）。生成test17/専用DB/settingsのみ。私物/個人AppData変更、download/installなし。所有GUI/API/embedding/Laya workerなし、作成test profileのみcleanup。docs/ui-polish.mdを追加し、chat/model引継ぎの最新再開地点を更新。
- **次の3手:** (1) Light/HighContrast/高DPIとAI非対応mode案内→文字検索復帰の実機確認、(2) 2,000件超をcheckpoint/増分/resource上限で段階拡張、(3) 明示選択の小さい実サンプルで検索品質評価。未指定時は生成素材。Layaは精度未達の明示実験APIのみ、本文/OCR/読書/Komgaは後続。


### UI整理と編集回帰の提出
- 実装/検証記録HEAD **1945aa7**（1945aa76410a2639851b6b5ea2420f97714b6722）。後続はこの提出文書のみ。同じfeature/Draft PR #5へ通常push、base維持・未マージ。
- 未到達の編集/再起動は別native軽量バッチで完了。最終ui-polish-02は32 checks PASS、4回正常終了、生成元hash不変、6 PNG目視。過去の全モデルバッチFAILと今回のeditor/layout PASSを分けて記録。
- Python96/C#13/WinUI Release（既存IL2104 2件）/py_compile/diff PASS。Light/HC/高DPIと新AIエラー案内操作は次回。私物/AppData/モデル/依存変更なし、所有test GUI/API/worker停止済み。


### テーマとAIエラー復帰の確認を開始（2026-10-12）
- 開始HEAD 988d55e/clean、AGENTS/Issue #4/PR #5のDraft/baseを確認。次の作業としてLight/Darkと実AI非対応エラー→文字検索復帰を検証する。
- Windows全体のテーマ/Contrast/DPI設定は変更しない。限定したprocess-local UITheme起動指定を追加し通常はSystemへ追従。実DPI/Contrastはread-onlyで記録し、未実行の高DPI/HCを成功扱いしない。
- generated17と隔離DB/settingsだけ、追加download/installなし。実機テスト/build/reviewの結果は後続に追記する。


### テーマ・AIエラー復帰の結果（2026-10-12）
- 開始988d55e、同じfeature/Draft PR #5/base。実装HEADは提出節に記録。限定のUITheme System/Light/Darkをwinapp --argsで渡し、実プロセスargsからWindowRoot.RequestedThemeへ適用。既定System追従。環境変数/OnLaunched.Arguments方式は実機で届かず削除。公式注意書きをdocs/ui-polish.mdにリンク。
- 新--appearance-checksはeditor-only必須。text-only profileの実cover503をLight/Dark、missing profileの実意味検索失敗をLightで確認し、中央案内/件数ページ消去/前後disabled/文字検索復帰1件/InfoBar子Title・Message成功をassert。モデル推論なし。既存favorite/dirty/native再起動も再確認。
- 01 FAIL（二重候補）、02 FAIL（InfoBar本体のvalueがない）、03 **UIA68 checks PASS / visual FAIL**。候補を所有PopupHost HWNDへ限定し、InfoBar実子テキストを検査。9 PNG全目視、700×620本体の明暗/詳細drawer/案内は読めるが、16-Light-dialogは暗い。03/result.jsonはUIA pass=trueを保持し、別visual-review.jsonでvisual_pass=falseを保存。
- 全3ContentDialog（dirty/roots/AI）へRequestedTheme=ActualThemeを追加。**最後の表示修正はbuild/code reviewのみ、native未再実行。** skill winui-ui-testingは “Maximum **two** fix-and-rerun cycles; then report remaining failures.” と指定、今回は2回に達し停止。68項目で見栄え合格/全体完了とはしない。
- Python96/C#13/最終x64 SelfContained Release PASS（旧IL2104 2件）。py_compile/launcher構文/diff確認。WinUI review:新APIはrestored projectで確認、theme resources/自然なnative Items/60paging/async・dirty/JSON DOM/認証/index identityを維持。analyzerなし。
- read-only DPI96/HC=false、OSテーマ/拡大率/Contrast設定無変更。高DPI/HC/reader/AOT/配布/1TB未検証。actual_model=false/profile_verification=not_run、重み/依存取得/私物走査/個人AppData設定変更なし。既存アプリ診断ログは使用。生成17元hash不変、所有6GUI正常終了/cleanup warningなし、API/GPUworkerなし、生成profileのみcleanup。
- **次の3手:** (1) python tools/test_ai_profile_ui.py --editor-only --appearance-checks --output data/ai-ui/appearance-04 で修正後Light/Dark dialogを実画面確認（04未実行、存在時は新suffix）、(2) 2,000件超をcheckpoint/増分/resource制限で段階拡張し生成大規模集合で測定、(3) 明示実サンプル評価と用意された高DPI/HC環境での確認。モデル段階やGPU導入を作り直さない。


### テーマ・エラー復帰の提出
- 実装/検証記録HEAD **8418d68**（8418d68f2fa6839be201df164988482c00859a6b）。後続は提出文書のみ。同じfeature/Draft PR #5/base、通常push・未マージ。
- native appearance-03は操作68 checks PASS、9 PNGのvisual reviewはLight dialogのDark不一致でFAIL。全3dialogのRequestedTheme修正は最終Release build PASSだがnative未再実行。最大2回fix/rerunに達し、次回の最初はappearance-04等新規outputで修正後dialogを確認する。
- Python96/C#13/最終Release（既存IL2104 2件）/py_compile/launcher構文/diff PASS。私物/個人設定/モデル/依存/OS設定無変更、生成元hash不変、所有test GUI/API/worker停止済み。高DPI/HC/1TB未確認。


### ゲームの前面表示を維持して索引拡張を開始（2026-10-12）
- 開始HEAD 1f77172/clean、AGENTS/Issue #4/PR #5を確認。同じfeature/Draft/baseを保持。
- ユーザーは別窓でゲーム中で、アクティブwindowを切り替えないテストを希望。既存native harnessは起動時Activate/実入力を含むため実行しない。Light dialog修正後の目視再確認は保留し、独立した索引拡張をバックグラウンドで進める。GUIを前面化しない確実な起動経路は現時点でない。
- 1万件上限、256件のkeyset metadata取得、build候補はIDだけ固定、保存済みvector再利用、current除外再確認、進捗16件間隔、候補ID限定vector読出しとglobal fusionを実装中。GPU/依存取得/私物走査なし、生成データ/決定論encoderで検証する。結果は後続へ記録。


### バックグラウンド索引拡張の結果（2026-10-12）
- 開始HEAD **1f77172**、同じfeature/Draft PR #5/base。ユーザーがゲーム中のためnative GUI起動/Activate/入力は行わず、Hidden/BelowNormalのCPU検証とbuildだけ。Windows/個人設定/モデル/依存変更、新規取得、私物走査なし。現行worker/モデルprofile/Layaを作り直していない。
- AI eligible上限 **10,000件**。256件keyset metadata取得、候補IDのみ固定、batch取得時の現行metadata、publish前presence/revision/除外再確認。vectorのatomic per-item commitを保持し進捗16件間隔（最大15件表示遅れ）。検索は候補ID限定の256件BLOB取得、global scoreをまとめて一度fusion。検索metadata/scoreとbuild IDは最大10,000件保持で、constant memory/全数万件ではない。
- API既定値とstatus/search coverage、GUIの上限表示を10,000へ。明示2,000指定・旧default namespace/vector schema・manual filters/60 paging・max rollback・モデル交換identityを維持。現行除外がeligible枠を消費するバグも修正。catalog全体の同一時点snapshot/新規GPU負荷制限は実装していない。
- 生成10,010 source / 対象10,000 / synthetic 768次元text-only、**smoke-01:14 checks PASS**。2,300件cancel→再起動後残り7,700件のみ推論→全件complete、末尾top1/ページ末40件/favorite、再起動再索引document0、全source byte/size/mtime digest一致。scan3.15秒、start0.33秒、cancelまで28.50秒、resume97.40秒、検索1.23秒、cache確認9.72秒、全process peak53.34MiB。このゲーム併走/低優先度の単発測定はSQLite/catalog/ranking plumbingのみ、EG2/CUDA/画像/2modality/1TBの性能ではない。docs/index-scaling.mdに再現手順/限界。
- 新単体テスト: 2,105件で旧2,000vector→追加105/タグ1件再生成/再起動、先頭300除外、256境界超cancel/進捗保存、推論中除外とタグ変更、270件/2modality global RRF。認証HTTP既定10,000/明示2,000/不正limit、C# coverage optional/旧literal応答を確認。
- **最終Python103 tests PASS**（unit-02、66.35秒）。初回unit-01は102 PASS、HTTP追加後test_ai_searchだけ13 PASSも確認。C# **15 checks PASS**（core-01）。WinUI x64 SelfContained Release **PASS、既存IL2104 2警告/0error**（build-01、33.20秒）。WinUI review:新control/APIなし、既存native Items/60 paging/async stale/dirty/JSON DOM/theme/auth/index namespaceを維持。日本語stringsの既存resource未分離を拡大整理しない、analyzer未導入。syntax/help/diff結果は提出節に記録。
- ignored証拠 data/index-scaling/{unit-01,unit-02,http-01,core-01,build-01,smoke-01} とsmoke-01.out/err。actual_model=false/gpu_used=false/native_gui_run=false、所有CPUテスト/scan/index threadsは正常終了。production API/GUI/GPUworkerは今回起動していない。生成dummy WAVは音声として未読。
- 前回appearance-03のUIA68 PASS / visual FAILは保持。全3dialogのRequestedTheme最終修正と今回上限文はbuild/reviewのみ、native未再実行。今回保留の理由はゲーム前面維持というユーザー希望。前回skill fix/rerun上限による停止と混同しない。HC/高DPI/reader/AOT/配布/実ライブラリ/1TBは未確認。
- **次の3手:** (1) ゲーム終了など前面操作可能な時に新規outputで --editor-only --appearance-checks、Light/Dark dialogと10,000表示を全PNG目視、(2) GPUを使ってよい時に生成素材の実EG2負荷/メモリを段階測定、(3) 10,000件超の対象選択/資源設定と明示小実サンプル品質評価。私物未指定なら生成素材、Layaは精度未達の実験APIのみ。


### バックグラウンド索引拡張の提出
- 実装/検証記録HEAD **5be9b88**（5be9b88ec6322c40013a251b561fc892006b4902）。後続は提出文書のみ。同じfeature/Draft PR #5/baseへ通常push、未マージ。最新HEADは実際のGitで確認。
- 最終Python103/C#15/WinUI Release（既存IL2104 2警告）PASS、1万件CPU synthetic14 checks PASS、変更Python py_compile/測定tool --help/git diff --check PASS。WinUI review済み、analyzerなし。現在の索引上限/候補batch/checkpointと測定・未実行境界はdocs/index-scaling.md/chat-handoff.md/PRへ記録。
- ユーザーのゲーム前面維持に従いnative GUI/GPUテストは未起動。Light dialog修正後と新上限文はnative未確認、appearance-03 visual FAILを保持。生成のみ、source hash/size/mtime不変、新規取得/私物/OS/モデル/個人設定変更なし。所有CPU測定と回帰processは終了済み。
- 次は前面操作可能時のdialog/new coverage実機確認、GPU使用可能時の実EG2段階測定、10,000超の対象/資源設定と明示小実サンプル評価。ゲーム中はHidden/BelowNormalのCPU検証を優先し、既存harnessのActivate/入力を行わない。


### 通常GUI検証を再開（2026-10-12）
- 開始HEAD 8a62492/clean、AGENTS/Issue #4/同じDraft PR #5/baseを確認。ユーザーが通常テストを許可し、ゲーム前面維持による保留を解除。
- Sandbox snapshotはstale/stopped、read-only Win32_OptionalFeatureでContainers-DisposableClientVM InstallState=2（disabled）を確認。OS機能は有効化せず同じlocal targetを使う。既存harnessを拡張し明暗AI/dirty/roots dialogとAPI上限、任意coverage-checksで生成17件の実CUDA索引/意味検索後の上限表示を確認する。
- 所有PID/HWND、専用DB/settings、生成素材のみ。新規model/download/依存導入なし。実機/PNG目視/cleanupの結果は後続へ記録し、旧appearance-03 visual FAILは履歴として残す。

- appearance-04はLight dialogが正しくLight/上限10,000を表示したが、小画面のStartAIIndexがscroll内容の外でzero sizeのためFAIL。6 PNGを全目視、sourcehash一致、3正常終了＋1owned PID fallbackのcleanup warning。GPU索引未到達。固定index status/action rowsを追加しmodel選択の部分だけscrollするよう修正、button boundsもassertして05へ再実行（fix/rerun 1回目）。

- appearance-05は固定status/start/cancelの小画面boundsと実Light表示、17件GUI CUDA索引、日本語top1/semantic上限10,000表示までPASS。ただし既存editor-only literal helperは既定literalの検査専用で、追加coverage段階のsemanticから切替をしておらずそこで全体FAIL。8 PNG全目視、4正常終了/cleanup warningなし、sourcehash一致。明示popup literal切替を追加し、roots scrollもwindow高に合わせて06へ再実行（fix/rerun 2回目、最後）。Dark/3dialogは未到達のまま記録し、Lightの部分成功を全体成功へ転用しない。


### 通常GUI再開の到達結果
- 開始8a62492。同じfeature/Draft PR #5/base、ユーザーの通常テスト許可で前面制約解除。local/生成17/専用DB settings/既存EG2だけ。Sandboxはdisabled(CIM InstallState2)/snapshot stale、OSは変更しない。
- 製品: 小画面の隠れたindex actionを修正、model optionsだけscroll、status/start/cancel固定Grid行。roots scroll高もwindowへ。skill winui-designのfind-ui/実project API確認、Release後winui-code-review実施。Error hidden actionを解消、既存SDK警告2件維持、analyzer未導入。native Items/60paging/async/stale/dirty/JSON DOM/theme/auth/identity無変更。
- 04全体FAIL（Start zero size）、05全体FAIL（追加semantic後にliteral helperが切替なし）、06全体FAIL（Dark fresh再索引にもdevice cudaを要求）。04:6/05:8/06:13 PNGを全目視。06は75 successful recorded checks、撮影13状態だけvisual PASS。明暗AI theme/10,000と固定action bounds、Lightのdirty/rootsと17件GUI CUDA/日本語top1/semantic上限文、favorite/dirty/native restartを確認。
- 06 disk read-only post-run-check: catalog17/text17/fresh17/state complete17/skipped0、Dark API weights loadなし。このcache/lazy解釈はdisk/log/sourceからの推定で、失敗時Dark runtime statusは直接記録していない。fresh buildでcudaを条件にしない修正と後のqueryでcuda assert、index states記録を追加。**最終harness修正はpy_compile/--helpのみ、native未再実行。** Dark semantic/追加dirty/roots/missingとfull profile batchは未到達。
- 04→05→06はwinui-ui-testingの “Maximum **two** fix-and-rerun cycles; then report remaining failures.” に従い停止。初回skill上限の残件から今回新依頼で再開したが、この依頼内の3回目以降へは進めない。旧03/04/05/06のFAILは保持。再開は新規appearance-07等で同じlocal target。
- 最終Release build PASS（appearance-build-02、27.67秒、既存IL2104 2警告）、C#15 PASS、構文/help/diffチェック。Python最終結果は提出節に記録。WinUI analyzer/HC/高DPI/reader/AOT/配布/実GPU1万件/1TBは未確認。text-only/float32/768の既存EG2を17件のみ、別checkpointではない。Light最終doc telemetry peak1045.9MiBはworkerの記録で全appメモリではない。
- 04:3正常＋1owned PID fallback warning、05:4正常/warningなし、06:4正常＋1warning。新sourcehash全一致、generated profile cleanup、所有GUI/API/embedding workerなしをread-only確認。私物/個人AppData設定/OS/依存/モデル変更・取得なし。新証拠 data/ai-ui/appearance-04/05/06 (全体FAIL)、visual-review、06/post-run-check、appearance-build-01/02.outとunit logはignored。通常app診断ログ使用。
- **次の3手:** (1) python tools/test_ai_profile_ui.py --editor-only --appearance-checks --coverage-checks --output data/ai-ui/appearance-07（新規のみ）で最終cache修正と未到達状態を全PNG確認、(2) 実EG2の生成段階的な負荷/メモリ測定、(3) 10,000超の対象/資源設定と明示小実サンプル評価。ゲーム前面制約は現在解除、Layaは実験APIのみ。

- 最終Python **103 tests PASS**（appearance-unit、68.88秒）、C# **15 checks PASS**、最終WinUI x64 SelfContained Release **PASS（IL2104 2警告）**。最後のharness修正はpy_compile/--help/git diff --check PASS、native未再実行。生成privateではない素材だけ、所有test processは終了済み。


### 通常GUI再開の提出
- 実装/検証記録HEAD **5ac973b**（5ac973bdb9650ba1a0d0c634c17ae178397779ab）。後続は提出文書のみ。同じfeature/Draft PR #5/baseへ通常push、未マージ。最新HEADは実Gitを確認。
- 最終Python103/C#15/WinUI Release（旧IL2104 2警告）/syntax/help/diff PASS。GUI明暗AI/上限/固定action、Light3dialogと17件CUDA検索は確認。最新appearance-06は75 recorded successful checks/13 PNG全目視だが全体FAIL、最終cache期待修正はnative未再実行。撮影状態visualと全体結果を区別。旧FAIL/cleanup warningsを消さない。
- 所有GUI/API/GPUworker/test process終了、sourcehash不変、生成profileのみcleanup。私物/個人設定/モデル/依存/OS変更や取得なし。新規outputで最終cache条件/Dark残件確認から続行、実GPU大規模/高DPI/HC/1TBは後続。


### GUI確認と実GPU負荷測定を再開（2026-10-12）
- 開始HEAD a4690a1/clean、AGENTS/Issue #4/同じDraft PR #5/baseを確認。通常GUIテスト許可を保持、生成素材/専用DB/settingsのみ。
- appearance-07はLight CUDA/検索/dirty/roots確認後、Darkの実clickでforeground安全チェックにより停止。全体FAILを保存、元source hash一致。
- build直前に所有HWNDへscoped focus（前面/keyboard focusを検証）を追加。wrong-window click拒否を維持し、同じlocal targetで新規appearance-08へ再確認する（fix/rerun 1回目）。
- 後続は既存EG2/生成素材だけで段階的な実GPU測定。新規取得/依存/OS/個人設定/私物走査なし。結果は後続へ記録。
- appearance-08はDark cached rebuild/device空と実CUDA queryまで確認後、GUI結果がbusyエラーでItemなしとなりFAIL。harnessの直接API queryがGUI初回lazy推論と重なる順序を修正し、GUI成功Message/件数/項目を先に待つ。製品の競合拒否は保持。新規09へfix/rerun 2回目、これ以上のnative再実行は今回行わない。

### 修正後GUI確認の結果
開始HEAD **a4690a1**。同じfeature/Draft PR #5/baseを保持。通常GUIテスト許可は継続、専用DB/settings/生成17素材と既存EG2のみ。

**appearance-09は操作 105 recorded checks PASS / 全17 PNG目視PASS。** Light/Dark双方の実CUDA日本語検索と上限表示、cover非対応の実エラー/文字検索復帰、dirty keep、roots、missing model案内、favorite/native再起動を完走。6正常終了/cleanup warningなし、source hashes全一致。full profile chooserバッチの再実行ではなくeditor/appearance/coverage sliceであり、別checkpoint・HC・高DPI・実ライブラリの証明ではない。

07はDark clickのforeground安全拒否でFAIL（13 PNG全目視、4正常終了+1fallback warning）。所有HWNDへのscoped focusを追加。08は直接API queryをGUI初回lazy queryと競合させてFAIL（14 PNG全目視、5正常終了/warningなし）。GUIの成功Message/項目/件数を待ってから直接API queryするよう修正。07→08→09の2回fix/rerunで終了、過去FAILを変更しない。新規XAML/C#/依存/モデル/個人設定/OS変更なし。

Darkのindex_states/coverage_gpu_statesは別時点で、短時間のcached rebuild開始とcompleteが非同期に入れ替わる（09は後者processed=0）。このsnapshotをcached jobの厳密な開始/終了時刻や推論ゼロの証明に使わない。GUI結果の表示と実CUDA queryは完了確認済み。厳密なcache再利用と処理数は後続専用GPU測定で確認する。

Python103 tests PASS（81.92秒）、C#15 checks PASS、WinUI x64 SelfContained Release PASS（37.04秒/既存IL2104 2警告）。WinUI code reviewはnative Items/60 paging、async/stale/dirty、テーマ/AutomationId、DOM JSON、認証/所有worker/profile identity保持を確認。analyzer未導入。

- 実GPU段階測定を開始。GPU-01のCPU worker値はvenv起動launcherだけで実モデルprocessを含まないため、全体メモリ値として使用禁止。所有子process treeのsampleとprocess-instance handle終了確認を追加し、修正後は新しいoutputで確認する。結果は後続。


### 実GPU段階測定の結果
GUI確認実装/検証記録コミット **b7de729**、この後は同じDraft PR #5/baseを保持。
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

次の3手: (1) 生成768px表紙/長文metadata→1万件段階測定、(2) 負荷/idle解放と上限超の対象選択、(3) 明示小実サンプルの品質評価。

### GUI・GPU確認の提出
- GUI確認コミット b7de729、実GPU測定/記録コミット **7d28a6ea558bdf68b30a58b6094c29995961516e**。後続は提出文書のみ。同じfeature/Draft PR #5/baseへ通常push、未マージ。
- appearance-09:105 recorded checks/全17 PNG目視PASS、6正常終了/warningなし。07/08のFAIL/cleanup warning、以前のFAILは保持。全profile chooserや高DPI/HC/reader/AOT/配布を合格にしない。
- gpu-02:86 checks PASS、生成2,304 text/216 cover、document/image重複推論なし、中断1,120→残り1,184、fresh cache全推論0→queryだけCUDA。実worker treeも含むRAM/終了確認、10 process-instance handles全終了。gpu-01のlauncher-only RAMは使用禁止。
- Python103/C#15/WinUI x64 SelfContained Release（旧IL2104 2件）PASS、CLI guard5/py_compile/help/diff PASS。WinUI code review済み、analyzer未導入。ソースhash/size/mtime不変、所有GUI/API/GPUプロセス終了を確認。私物/個人設定/OS/依存/モデルの変更・取得なし。
- 次の3手: (1) 生成768px表紙/長文metadata→実GPU1万件段階測定、(2) 負荷/idle解放・対象上限超の選択、(3) 明示小実サンプルの品質評価。全1TB/一般的検索精度は未確認、Layaは既定無効の実験APIのみ。


### 大きめ生成素材の段階測定を開始（2026-10-12）
開始HEAD **44ecd51**、同じfeature/Draft PR #5/base、clean worktreeから再開。既存default EG2/profile/cacheを保持。測定toolに生成cover寸法32..768と60文字の日本語tag数0..30を追加し、catalogの公開update validation経由で新規生成行だけ設定。初期小規模768×768/30tagを測定後、資源/速度に応じて実GPU1万件へ進める。build timeoutは測定tool内だけ最大3600秒へ延長、製品動作は変更しない。現時点では新条件は未検証。モデル/依存の取得なし、私物/個人設定/OS変更なし。

- gpu-large-preflight-01:768×768/30tags（60文字各）/文字入力1865..1881で生成128件、49 checks PASS、document128/image12/query9、CUDA peak allocated994MiB、所有6process instance終了、source不変、cache推論0。新条件で小規模合格後、64→256→1024→2304→5000→10000の実GPU測定を開始。進行中はresult.pass=false、最終結果とexitを後続に記録する。


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


### 実GPU1万件・HTTP検証の提出
実装/結果コミット **82134643ce11018919048094f779e569f77ec148**。後続は提出文書のみ、最新HEADは実Gitで確認。同じfeature/Draft PR #5/baseへ通常push、未マージ。gpu-large-10k-01は126 checks PASS、text10000/cover938、document10000/image938/query21、所有9handles全終了。HTTPは28 checks PASS/query7だけ/所有3handles全終了、注釈復元/vector/source/既存result digest不変。benchmark guard9/API guard5 PASS。Python103 tests PASS（78.438秒）、C#15 checks PASS、WinUI x64 SelfContained Release PASS（37.72秒、既存IL2104 2警告を抑制せず保持）。WinUI code reviewの変更関連確認済み、analyzer未導入。GUIは今回変更/再実行せず前回105checks/17PNG目視PASSを保持。私物/個人設定/OS/モデル/依存変更・取得なし、検証worker残留なし。
次の3手: 明示worker解放の実装/実GPU停止再ロード競合検証、選択式idle解放/索引待機/上限超対象選択、小さな明示実サンプル品質評価。ai-resource-policy.mdは未実装の次段階仕様。全1TB/GUI1万件負荷/一般的検索精度/別checkpoint/Laya改善/reader/Komga/AOT/配布を合格にしない。


### 応答停止後の実機再開（2026-10-12）
開始local HEAD753ae51、remote e63a5f9へcleanな状態からff-onlyで29コミット取込み。チャット側は手動解放・自動idle・新規推論だけの待機・設定互換・WinUI controlまで実装済み。初期local Python115/C#15/Release PASS（既存IL2104 2警告）。最新e63a5f9のActionsはWinUI関連workflow success、CPU lifecycle failure、Prototypeのtests job success/browser-smoke failure。失敗2jobのlog取得はBlobNotFoundで原因未確定、CI成功と断定しない。
追加reviewで設定保存失敗時にruntime policyだけ変わる問題とprofile/resource同時保存のlost update、idle判定後の新activity/disable競合を修正しregressionを追加。実GPUと新GUI確認はこれから、過去1万件試験は再実行しない。
