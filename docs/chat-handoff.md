# Aredoko — GPTチャットへの最新引継ぎ


## 最新：GUIの明示的なAI文章検索（2026-10-13）

開始HEAD **f792d6a334834f1f8281509e74bfeb940b06919d**。同じfeature/Draft PR #5/comparison baseを維持。今回の実装SHAは後続記録/Git/PR headで確認。

- 検索方法に「AI文章」（API source=text）を追加。「AI意味検索」は「AI混合」へ改称、既存index0/1/2とIDs/literal/all/coverは維持、textをindex3へ。種類・検索方法のvisible labelsと根拠説明を追加。名前・タグの意味だけを使い本文/音声は読まないことを表示。
- saved scope/coverage/filter/page/stale/dirty規約を維持。未保存のモード変更をcancelするとmode/query/kindとhint/placeholder/accessibility nameが同期して戻る。モデル/順位/自動routingは変更しない。session-only・初期literal。
- Core **35 PASS**、Python scope12 PASS / 14.098秒・retrieval13 PASS / 4.625秒、最終Release PASS / 30.23秒 / errors0・既存IL2104 2warnings。syntax/CLI/diff PASS。手動WinUIレビュー済み、専用analyzer未実行。全Python155は前回履歴で今回未再実行。
- native03 **65 checks PASS / 6 PNG全目視 / scoped visual PASS / 正常close2 / cleanup warnings0**、Light/Dark wide/narrow・DPI96/Contrast off。実HTTP/AISearch/Release GUI、生成PNG3/2root・隔離設定、CPU契約stub encoderで実GUI sourceとscope/kind/favorites/page0の要求20件、blank/literal復帰・dirty cancel/discard・source bytes/mtime/hashと設定byte不変を確認。実GPU/検索品質・physical keyboard・高DPIは今回未確認。
- native01/02はUIA peer失効/名前substring曖昧でFAIL、各2PNG全目視・正常close1。03まで2 fix cycles、失敗履歴は[検索方法](search-methods.md)。ignored artifacts/DB/私物/credentialsはcommitしない。CI manual-only・Draft未マージ。

### 次の3手

1. 小さな生成fixture＋実CUDAで新mode/nativeとtext-only profileのcover非対応案内を確認。
2. 高DPI/HighContrast/読み上げ・全面keyboardの独立確認。OS設定は勝手に変更しない。
3. 新規固定品質入力/Laya gateを別実験で準備。Laya既定無効、reader/Komgaは後続slice。

---

## 最新：text/pixel根拠別の新規固定評価 holdout v2（2026-10-13）

開始HEAD **7d7facc749103eaf7798a3d0345831fc4163fd33**。同じfeature/Draft PR #5/comparison baseを維持。入力/コードをGPU観測前commit **82427c528fcc273edb601cd62f69fe3c3251ab5e**で凍結し、結果後にqrels/queries/items・モデル・順位・GUIを変更しない。結果・テスト・仕様記録commitは **873bd5ad12a7c9684e3d6c81d93ffdc21d4f825e**。このSHA追記は文書だけの後続commitで、通常push後の最終HEAD/CI観測はGit/PR head・PR説明で確認。

- v2 SHA256 **021e0984797727c6a79c97fb588165ce49db7c4e12fcdb1f265e02a7793b08fa**、30素材（PNG12/CBZ6/灰SVG8/無音WAV4）・日本語30問・220相関行/160query推論。全18unique coversを推論前に目視。metadata/pixel/一致/誤タグ/filename/no-answerを別集計。external statistical holdoutや製品quality gateではなく、以後developmentとして扱う。
- 実CUDA `search-holdout-01` **runtime PASS / 258checks / index27.155秒 / document30/image18/query160**。元bytes/mtime/hash、frozen manifest/Git blob、検索前後vectors不変、所有handles3件全終了。私物/モデルDL/OS変更/Laya/GUI操作なし。
- 種類なしmetadata text12/12・combined10/12、pixel cover6/6・combined0/6・text0/6。一致4問はAI各4/4。kind指定metadata combined11/12だがpixel combined0/6。誤タグのpixel検索cover2/2・combined1/2、分類タグ検索text2/2・combined0/2。no-answerでもAIは最近傍候補を返すためconfidence/存在保証/閾値は未実装。詳細は[search-quality-holdout.md](search-quality-holdout.md)。
- 新規CPU5 PASS / 0.570秒、旧quality CPU5 PASS / 0.187秒、全Python155 PASS / 106.705秒、Core29 PASS、Release PASS / 40.75秒 / errors0・既存IL2104 2warnings。syntax/CLI/diff PASS。GUI source/nativeは今回変更/再実行なし、旧keyboard partial/DPI等の境界は維持。
- CLIは `--suite holdout-v2`、既定baseline-v1とv1 SHA/入力/結果を維持。任意のmanifest/private path入力はなし。評価DB/メディア/結果/weights/handle IDsはignoredでcommitしない。CI manual-only・Draft未マージ。

### 次の3手

1. GUIでtext-onlyを明示選択できるmodeを設け、混合/画像との違いを説明しnative検証する。自動routing/既定順位変更なし。
2. v1/v2以外の根拠を持つ新規固定入力で次の品質判断を行い、観測した小図形へfusionを過適合させない。
3. Laya日本語gateは別実験で再評価し既定無効維持。reader/Komga/高DPI/全面keyboardは別slice。


---

## 最新：検索可能なフォルダ選択・全文パス・疎な分布（2026-10-13）

開始HEAD **5b4ac4c79c3a012cea72ba2fdaf85acb68f6f716**。同じfeature/Draft PR #5/comparison baseを維持。実装SHAは後続提出記録/Git/PR headで確認。

- 全登録rootを名前/パスで絞り込み32件ずつ表示。256番目以後の未選択rootも新規選択可能。Coreで非表示の選択を保持し、256選択上限/空scope/JSON DOM/保存freeze・古い応答規約を維持。表示のみの変更はdraftを変更しない。
- 「パス」で読み取り専用・折返しの全文欄を表示。狭幅でも全文を目視。tooltip/32行native controlsを使用し、危険なmanaged ItemsSourceを再導入しない。
- Core29 PASS、全Python150 PASS / 101.163秒、Release PASS / 34.02秒 / errors0・既存IL2104 2warnings。手動WinUIレビュー済み、専用analyzer未実行。
- native03 **51 checks PASS / 6 PNG全目視 / scoped visual PASS / 正常close 2回**、keyboard=partial、cleanup warnings=0。 OSが所有窓の前面化を拒否した操作は入力せず、同じowned HWNDのUIAで機能確認を続行。keyboard_skippedへ明記し、全キーボード経路PASSとは扱わない。01ではSpace選択/Enterページ送りが観測済みだが途中失敗の別履歴。
- native01/02はforeground拒否でそれぞれFAIL16checks/2PNG・FAIL5checks/1PNG、全画像目視、owned PID終了fallbackを記録。03は生成901 metadata/75実PNG/258rootで検索・隠れた選択/保存/restart/未保存破棄・全文パスを確認しGPU未ロード。詳細とkeyboard/cleanup境界は[root-picker.md](root-picker.md)。
- 5万生成metadataの疎な2root分布（前方2/後方2/分散500）は最終CLI03 10checks PASS、ID順/件数/上限/元PNG不変。5回median/maxは詳細文書。私物走査/GPU索引/1TB性能保証ではない。
- CI manual-only・Draft未マージ。push後HEADのruns/checksをread-only確認してPR説明へ記録する。

### 次の3手

1. 高DPI/High Contrast/読み上げ・全面keyboardと大量root metadataの応答性を確認。
2. 新しいtext/cover holdoutを凍結して混合順位を評価する。
3. Laya日本語gate再評価、既定無効維持。reader/Komgaは別slice。


今回のフォルダ検索・ページ選択・全文パスの実装/テスト/仕様commitは **2c1b167310574c6b6d9530d01502d19d6f703ccd**。このSHA追記は同commitからの文書だけの後続commit。通常push後の最終HEAD・CIの読み取り観測はGit/PR head・PR説明で確認する。Draft未マージ・comparison baseを維持。

---

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


今回の実装・検証・仕様更新commitは **f440e5916579ce1f1b4e0daca331a00466f236eb**。この提出記録は同commitからの文書のみの後続commit。通常push後の最終HEADとCI runs/checks観測はGit/PR head・PR説明で確認する。Draft/base/main境界は維持。

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

## Chat担当時点：所有AI workerの解放と選択式リソース設定（履歴）

開始HEAD **753ae518b58a2fb97d5e8cc0e353909396e76697**。**同じ`feat/winui3-production-mvp-20261011` / Draft PR #5（base `feat/gui-framework-comparison-20261010`）に追記。** 最新の機能実装コミットは **284fc5883db6edd0c0d3cf1dfd9b13c9f3baed80**（cache待機修正・WinUI変数初期化順を含む）。この引継ぎドキュメント以降の正確なHEADはGitHubで取得する。

### 変更したこと

1. `app/ai_process.py` は`EncoderProcess.release()`を追加。**自身が所有するアイドル中のsubprocessのみ**を停止し、device/telemetryを消去。次のencodeで同じprofile/重みを再ロードできる。対して`close()`は永続終了フラグとlockで再起動を禁止する。`_stop()`は元ファイル/VectorStoreには触らない。
2. `app/ai_search.py`: 既存の`inference` guard共有、検索/索引worker生存中の解放を即時`AIBusy`、closeとstart/searchの競合防止。statusに`resident/worker_state/resource_policy`を追加。自動解放は**既定0秒（無効）**で、`time.monotonic()`から処理後のアイドル時間を測り、`Event`で終了する。索引待機は**既定0ms（無効）**で**新規推論後のみ**`cancel.wait`を用い、保存済みベクトルだけを再利用するcache rebuildや検索には適用しない。
3. `app/production_server.py`: 既存localhost/token/Originを使った`POST /api/library/ai/release`（本文`{}`、Busyは409）、`GET/POST /api/library/ai/resource`（`{"idle_release_seconds":0..3600,"index_pause_ms":0..2000}`）。失敗時AIだけエラー、文字検索を保持。
4. `app/ai_settings.py`: `settings.json`の`resource`設定を原子的に保存。**従来のversion1/profileのみのJSONにも後方互換**。`profile`選択/adapter/model identity/旧vectorキャッシュと独立。GUIの変更は即時に有効で、再索引不要。
5. `src/Aredoko.WinUI/MainPage.xaml.cs` の既存「AI索引」ダイアログで、**「AIをメモリから解放」**、自動解放0/1/5/15分、索引待機0/50/200/500/1000msの選択・保存、現在の待機/常駐表示。元の索引status/start/cancelは固定領域に維持。利用可能な既定設定でも元ファイル/索引は削除しない。Layaは今回未変更の既定無効実験API。

### テスト・検証を混同しない

- CPU専用`tests/test_ai_release.py`: 偽encoder/所有subprocess、解放→再検索、VectorStore行不変、検索・索引のbusy、close後再起動禁止、timer/索引待機キャンセル、API token/Origin/不正値、文字検索。**[Actionsの専用CI](https://github.com/jakymiku/Aredoko/actions/runs/38233333368) PASS。**
- `tests/test_ai_settings.py`: 古いprofile-only JSON、保存後のprofile切替でresource維持、型や範囲外拒否。その他既存AI/GUI比較コードを変更せず。**WindowsフルCI/WinUI Release結果は各Actionsの最終ジョブで確認すること。**
- 並列CI環境で以前の`test_ai_scaling.py`の2,105件CPU索引が60秒以内に終わらず失敗したため、**テスト用join上限だけ180秒**へ調整。製品のworker推論タイムアウト/対象上限や既存テストの正当性判定は変更しない。
- ビルド履歴: 追加WinUI GUIの初回CIでlocal変数 `polling` の未初期化参照 CS0165 を検出。`polling` と `indexLimit` をイベントハンドラ登録前に移動。**修正後WinUI Releaseの最終結果は最新Actionsで確認する（未実機検証）**。
- **今回やっていない**: 以前PASSした実GPU 10,000件126項目・HTTP 28項目の再実行、実VRAMの解放量測定、Windows実画面の新AI dialog操作、一般検索精度/別checkpoint/1TBや個人メディア走査。GPU/FPS上限は保証しない。新たなモデルや依存DL・OS変更なし。元ファイル不変、mainマージ/force pushなし。

次の3手: (1) 生成素材の実GPUでquery→解放→所有worker消滅→再queryとベクトルhash確認、(2) Windows実画面でAI dialogのLight/Dark・狭幅・busy表示と設定保存・旧profile JSONを確認、(3) 未検証の1万件超の対象root/種類/棚/coverage設計と架空日本語品質セットを検討（上限は撤廃しない）。

---

更新: 2026-10-12。旧Web試作段階の引継ぎを置き換える。**製品GUIはWinUI 3に決定済みで、EmbeddingGemma 2検索まで実装・実GPU検証済み。最初から作り直さない。**


## 大きめ生成素材で実GPU1万件・HTTP検索確認（2026-10-12）

開始HEAD **44ecd51**。実装/結果コミット **82134643ce11018919048094f779e569f77ec148**。後続は提出文書のみ、最新HEADは実Gitで確認。同じfeature/Draft PR #5/baseを保持。`gpu-large-10k-01`は**126 checks PASS**、既存default EG2/text+cover/auto-bf16/768次元で実CUDA索引。生成10,000件（架空WAVメタデータ9,062、PNG625、1ページCBZ313）。cover938枚は768×768px、tag30個×60文字、実encoderの文字入力1865..1881文字とPNG寸法を記録・検証。

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


## 前段階の再開地点（2026-10-12・GUI完走／実GPU2,304件確認）

開始HEAD **a4690a1**。GUI検証コミット **b7de729**、実GPU測定/記録コミット **7d28a6e**。後続は提出文書のみ、最新HEADは実Gitで確認。同じfeature/Draft PR #5/baseを保持。通常GUIテスト許可は継続、専用DB/settings/生成17素材と既存EG2のみ。

**appearance-09は操作 105 recorded checks PASS / 全17 PNG目視PASS。** Light/Dark双方の実CUDA日本語検索と上限表示、cover非対応の実エラー/文字検索復帰、dirty keep、roots、missing model案内、favorite/native再起動を完走。6正常終了/cleanup warningなし、source hashes全一致。full profile chooserバッチの再実行ではなくeditor/appearance/coverage sliceであり、別checkpoint・HC・高DPI・実ライブラリの証明ではない。

07はDark clickのforeground安全拒否でFAIL（13 PNG全目視、4正常終了+1fallback warning）。所有HWNDへのscoped focusを追加。08は直接API queryをGUI初回lazy queryと競合させてFAIL（14 PNG全目視、5正常終了/warningなし）。GUIの成功Message/項目/件数を待ってから直接API queryするよう修正。07→08→09の2回fix/rerunで終了、過去FAILを変更しない。新規XAML/C#/依存/モデル/個人設定/OS変更なし。

Darkのindex_states/coverage_gpu_statesは別時点で、短時間のcached rebuild開始とcompleteが非同期に入れ替わる（09は後者processed=0）。このsnapshotをcached jobの厳密な開始/終了時刻や推論ゼロの証明に使わない。GUI結果の表示と実CUDA queryは完了確認済み。厳密なcache再利用と処理数は後続専用GPU測定で確認する。

Python103 tests PASS（81.92秒）、C#15 checks PASS、WinUI x64 SelfContained Release PASS（37.04秒/既存IL2104 2警告）。WinUI code reviewはnative Items/60 paging、async/stale/dirty、テーマ/AutomationId、DOM JSON、認証/所有worker/profile identity保持を確認。analyzer未導入。

**gpu-02:実EG2文字+表紙2,304件、86 checks PASS**。64→256→1,024→2,304、中断1,120から残り1,184だけ推論、fresh再起動cache build全推論0→queryだけCUDA。text2,304/cover216、source bytes/size/mtime不変、所有worker tree handle全終了。RAM sample peak controller40.1MiB/worker tree2062.2MiB、torch CUDA確保peak931.8MiB（総VRAMではない）。96×128の生成小表紙/短いmetadata、GPU baseline48%で独占なし。gpu-01のworker RAMはlauncherのみで使用禁止。詳細・秒・再現はindex-scaling.md最新節。実GPU1万件/1TBを合格にしない。新規取得なし。次の3手: (1) 生成768px表紙/長文metadataで1万件へ段階測定、(2) 負荷/idle解放・上限超対象選択を実装、(3) 明示小実サンプル品質評価。私物/1TB/HC/高DPI/reader/Komga/AOT/配布は未検証・未実装の範囲を維持。Layaは実験APIのみ。

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
最新は生成1万件の実EG2文字+768px表紙/長い日本語tagのGPU検証と、HTTPのpaging/種類/お気に入り検索までPASSです。増分・中断5096から残4904だけ再開・fresh cache全推論0・所有worker終了を確認。前回native appearance-09も105 checks/17 PNG目視PASSであり、appearance-06等の過去FAILは履歴として残しています。まずdocs/ai-resource-policy.mdに従って明示worker解放を実装し、実GPUで停止/再ロード/競合を検証してください。次に選択式idle解放/索引待機/上限超の対象選択、明示小実サンプルの品質評価へ。私物を未指定で走査せず、全1TBやGUI1万件負荷を検証済みとは扱わないでください。
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
