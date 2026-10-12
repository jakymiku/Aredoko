# WinUI画面の整理と実機検証

2026-10-12。製品WinUI 3を維持し、既存画面を読みやすくする小さな改善。Hallmarkのaudit/anti-pattern/slop-testを画面評価の観点として使い、WinUI design/review/testingの手順で実装・確認した。ネイティブFluentの字体/テーマ/操作を優先し、Web向けCSSやモバイル合格判定をWinUIに転用していない。

<!-- Hallmark · pre-emit critique: P4 H4 E4 S4 R5 V3 -->

## 評価と変更

| 旧画面での課題 | 変更と意図 |
| --- | --- |
| 選択前から右側が空の詳細領域だった | 初期表示と検索更新時は閉じ、作品を選んだ時に詳細を開く。一覧の幅を使う |
| 行のタイトルと補助情報が同じ強さだった | タイトルをSemibold、補助情報をCaptionとsecondaryのテーマ色へ。長いファイル名の一覧を読みやすくする |
| 検索欄/件数/操作欄の関係が弱く、狭い画面で横に詰まった | 検索欄に見出し、検索に標準AccentButtonStyle、件数をヘッダーへ。840 DIP未満で操作群を二段にする |
| 設定の説明が長いと小さいdialogで収まりにくい | AI設定の内容だけを高さ制限付きScrollViewerへ。閉じるボタンは固定のdialog footerに残す |
| AI非対応/失敗時の中央案内が汎用の再接続文だった | 名前・タグ検索やAI索引設定を案内し、古い件数/ページ操作も消す。具体的エラーは既存InfoBarで示す |
| 詳細編集の境界が見分けにくい | ネイティブのCardStroke/角丸/余白で一つの編集領域を示す |

既存のListView.Items/60件paging、AutomationId、タグ保存/未保存確認、async/stale対策、JSON DOM、モデルprofile/index identityは維持した。素材には実際の生成プレビューを使い、表示できないファイルは既存の「プレビューなし」。新ライブラリ/モデル/OS設定変更なし。

## 実機結果

Windowsローカル、生成17ファイル、専用DB/settings。個人ライブラリとAppData設定は使用していない。

```powershell
python tools/test_ai_profile_ui.py --editor-only --output data/ai-ui/profile-editor-02
python tools/test_ai_profile_ui.py --editor-only --layout-checks --output data/ai-ui/ui-polish-02
```

同名outputが存在する時は新しいsuffixを使う。前者はUI整理前の編集回帰11 checks PASS、後者はUI整理後32 checks PASS。どちらもAIをロードしない `actual_model=false / profile_verification=not_run` の軽量バッチ。

- 保存完了表示とAPI反映を待ち、お気に入りの保存、未保存タグで「編集を続ける」、元のDBタグ保持、再起動後のAPI値と実checkboxのonを確認した。
- 1200×820の一覧/タイル、700×620の検索/操作ボタン・件数、同サイズの不足モデルdialogで候補/警告/閉じるが画面内にあることをUIA boundsで確認した。
- 最終6 PNGをすべて目視した。`10-wide-library.png`, `11-wide-tiles.png`, `12-narrow-library.png`, `08-dirty-guard.png`, `09-editor-restart.png`, `13-small-missing-dialog.png`。一覧PNGにはCLI合成のCtrl+F tooltipが写る。
- 所有HWND/PIDを確認したサイズ変更とWM_CLOSEで、4回のGUI終了が正常。最終バッチにcleanup warningなし。所有GUI/API/worker残留なし。
- 開始/終了の生成元ファイルhashが一致。証拠はignoredの `data/ai-ui/ui-polish-02/result.json` とsource-hashes.json、PNG/UI treeに保存し、Gitへ含めない。

初回 `profile-editor-01` は既定の文字検索を再選択する不要なfocusでFAIL。現在値を検査するよう修正して02 PASS。`ui-polish-01` は32 checks PASSだが旧cleanupはforeground依存で警告を残したため、所有HWNDへ通常の閉じる通知を送るcleanupへ改善し02を再確認した。失敗/警告履歴を消さない。

```powershell
python -m unittest discover -s tests -q
dotnet run --project tests/Aredoko.Core.Tests -c Release
dotnet build src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Release -p:Platform=x64 -p:SelfContained=true --no-restore -v:minimal
```

Python96 tests、C#13 checks、WinUI Release PASS。従来のSDK IL2104警告2件は抑制していない。native screenshot/UI treeは実行した範囲の証拠で、WinUI analyzerは未導入。

## この段階で未確認だったこと（後続確認は下記）

今回のnativeはdark/通常DPI。Light/HighContrast/高DPI、スクリーンリーダー、ピッカー全体、Native AOT/配布、1TB性能は未確認。数値的な色コントラスト合格も主張しない。標準のテーマ資源を使い、今回の実画面ではラベル/警告が読めることを確認した。

AI失敗時の案内変更はbuild/code reviewまでで、非対応画像modeの実AI操作は今回未実行。全モデル切替/GPUバッチも今回再実行していない。前回profile-picker-06はモデル段階到達・全体FAILとして記録を保持し、今回の別バッチで残った編集/再起動を検証した。モデル結果は[model-profiles.md](model-profiles.md)を参照。

次はtheme/DPIとAIエラー復帰を実機確認。その後、2,000件超のcheckpoint/増分/resource制限と、明示選択された小さな実サンプル評価を進める。本文/OCR/読書/Komgaは別の実装段階。


## 続行: 明暗テーマと実AIエラー復帰（2026-10-12）

開発用launcherへ `-UITheme System|Light|Dark` を追加した。起動したアプリのroot RequestedThemeだけを変え、既定SystemではWindowsに追従する。OS設定/保存設定/個人ライブラリには影響しない。明暗の画面比較を再現する指定で、製品GUIの永続的なテーマ設定ではない。

```powershell
pwsh -File tools/start-winui.ps1 -Database <dedicated-test-db> -AISettings <dedicated-test-settings> -UITheme Light
python tools/test_ai_profile_ui.py --editor-only --appearance-checks --output data/ai-ui/appearance-04
```

この節の時点ではappearance-04未実行だった。現在04/05/06を実行済みで、結果・修正後の残件は末尾に記録。存在するoutputは再使用しない。

Windows App SDKではOnLaunchedのArgumentsは非対応で、[公式のLaunchActivatedEventArgs.Argumentsの注意書き](https://learn.microsoft.com/en-us/windows/windows-app-sdk/api/winrt/microsoft.ui.xaml.launchactivatedeventargs.arguments)に従いEnvironment.GetCommandLineArgsから指定を読む。値はLight/Dark以外Systemに戻す。最初の環境変数方式もpackaged activationへ引き継がれなかったため削除し、winapp --argsで渡す。

### 到達結果と未完部分

- 最終native `appearance-03/result.json`: **UIA 68 checks PASS**、**visual-review.jsonはvisual_pass=false**。UIAだけのPASSを全体完了としない。
- text-only実profileのcover非対応をLight/Dark両方、missing profileの意味検索エラーをLightで検証。実503→具体的な中央案内、件数/ページの消去、前後ボタン無効、文字検索で実1件/InfoBar成功子テキストへ復帰。favorite保存/dirty keep/再起動も再確認。
- 700×620のエラー案内/操作、AI dialog候補/警告/閉じるboundsを実UIAで確認。9 PNGを全目視。Light/Dark本体、詳細drawer、エラー文は読みやすい。エラーPNGはCLI合成のCtrl+F tooltipを含む。
- **16-Light-dialog.pngはLight画面上でDark dialogだった。** 全3dialogへRequestedTheme=ActualThemeを追加してRelease build/code reviewを確認したが、この最後の修正はnative未再実行。高DPI/HCは未確認。各phaseのread-only記録はDPI96/HighContrast=false。
- 6回正常終了、cleanup warningなし、生成元開始/終了hash一致、所有test GUI/API/workerなし。generated17/専用DB/settingsだけ。重み/依存取得・GPU推論・私物走査・個人AppData設定変更なし。通常のアプリ診断ログは使用した。
- appearance-01はUIA二重候補でFAIL、02はInfoBar本体のvalue待ちでFAIL。実popup HWNDとInfoBar子Title/Messageの判定へ修正し03の操作は成功。01/02は要求Lightでも本体Darkで、03のプロセス引数からLight表示を確認した。失敗履歴を保持する。
- Python96/C#13/最後のWinUI x64 SelfContained Release PASS（既存IL2104 2件）、py_compile/launcher構文/diffチェック。最後のdialog修正もビルド済み。Sandbox/analyzerなし、reader/AOT/配布/1TB未検証。

再試行を止めた根拠: winui-ui-testing/SKILL.mdは “Maximum **two** fix-and-rerun cycles; then report remaining failures.” と指定する。今回01→02→03で2回を使用したため、新しいdialog修正の目視再確認を最優先の残件として記録した。操作68項目を視覚合格に転用しない。

次は修正後のLight/Dark dialogを同じlocal targetで新規outputへ再確認。その後2,000件超の索引をcheckpoint/増分/resource制限込みで拡張する。高DPI/HCは用意された環境で確認し、ユーザーのOS設定を変更して検証範囲を埋めない。


## 通常GUI検証の再開結果（2026-10-12）

開始8a62492。ユーザーが通常テストを許可したため、ゲーム前面制約を解除。Sandbox featureはread-only CIMでInstallState=2（disabled）、snapshotはstale/stoppedだった。機能有効化はせず同じlocal targetで実行。生成17素材、専用DB/settings、既存EG2重みだけ。OS/私物/個人設定/依存/重みの変更・取得なし。

製品変更: AI dialogのmodel設定だけをscrollし、現在の索引statusと開始/中断を別の固定Grid行へ移した。700×620でも開始ボタンを実clickでき、状態・上限・中断/閉じるが見える。フォルダ管理scrollもwindow高に応じた上限へ。既存AutomationIds、ActualTheme、native Items/60 paging/async/dirty/JSON DOM/認証/モデルidentityは保持。

`--editor-only --appearance-checks --coverage-checks` は通常のeditor-only例外として、生成17件を実CUDAで索引/日本語検索する。実模型は既存EG2のtext-only/float32設定（768次元）、独立した別checkpointではない。profile_verification=not_runは全モデル選択バッチ未実行という意味で、actual_model=true。cover非対応とliteral復帰を先に検証する。

- appearance-04: Light dialogは正しくLight/最大10,000表示。ただしStartAIIndexがscroll外でzero size、全体FAIL。6 PNG全目視、3正常終了＋1owned PID fallback warning。GPU索引未到達。
- appearance-05: 固定status/start/cancel bounds、Light 17件GUI CUDA索引、日本語top1とGUI検索上限文まで成功。既存literal helperの「既定literalを検査するだけ」という条件を追加coverage段階にも使ったため全体FAIL。8 PNG全目視、4正常終了/warningなし。
- appearance-06: **75 recorded successful checks、全体はFAIL**。13 PNGすべて目視。明暗AI dialogの正しいtheme/最大10,000と固定buttons、両テーマの実cover503案内/literal復帰、Lightの17件CUDA索引/日本語top1/semantic上限文、Light dirty keep/DB tag不変、Light roots/閉じるbounds、favorite保存/dirty/native再起動まで確認。
- 06のDark再起動後は保存済み17件がfreshなので、再索引で推論不要。テストが常にdevice=cudaを要求して失敗。read-only disk確認は17 text vectors/17 current revisions一致・complete17、Dark API logにはモデルloadがない。空のlazy encoder deviceが原因という説明はこのdisk/logとソースからの推定で、失敗時のDark runtime statusを直接記録したものではない。post-run-check.jsonはこの確認だけで、native成功へ転用しない。
- buildの期待をfresh reuse時だけ推論不要へ変更し、後の実semantic queryでCUDAをassertするよう修正。index stateも結果へ記録する。**最後のテスト修正はpy_compile/--helpのみ、native未再実行。** Dark semantic/追加dirty/rootsと最後のmissing-error段階は06で未到達。all-profile通し/高DPI/HC/reader/AOT/配布/実GPU大規模/1TBは未検証。
- 06は4正常終了＋1owned PID fallback warning。初回04と06のwarningを消さない。所有GUI/API/embedding worker残留なしをread-only process確認、sourcehash全一致、生成profileのみcleanup。新GUIテストの27 PNGをすべて見た（04:6/05:8/06:13）。通常のapp診断ログは使用する。

06/result.jsonのpass=falseは保持し、visual-review.jsonのvisual_pass=trueは**撮影された13状態の表示だけ**。旧appearance-03 visual FAILを後から変更しない。今回の明暗AI dialog表示は新しい証拠で確認したが、新batch全体がPASSとは扱わない。

winui-ui-testing/SKILL.mdの “Maximum **two** fix-and-rerun cycles; then report remaining failures.” に従い04→05→06で停止。次回は存在しない新規output（例appearance-07）で、修正後のcache条件と未到達状態を最優先確認する。

    python tools/test_ai_profile_ui.py --editor-only --appearance-checks --coverage-checks --output data/ai-ui/appearance-07

実GPUで1万件索引したわけではない。1万件CPU synthetic測定は前段階の結果を保持する。次はnative残件、実EG2負荷を段階測定、明示小実サンプルと用意されたHC/高DPIの順。追加資源制限/idle検出はまだない。Layaは実験APIのみ。


最終Python103 tests/C#15 checks/WinUI x64 SelfContained Release/構文/help/diff PASS。Releaseは既存IL2104 2警告を維持し抑制なし。WinUI reviewは新Gridのnative API/自然なテーマ/既存AutomationIds/async・dirty/native Items/JSON DOM/認証の保持を確認。WinUI analyzer未導入。これらの成功とappearance-06全体FAILを区別する。


## 通し確認の完了（2026-10-12・appearance-09）
開始HEAD **a4690a1**。同じfeature/Draft PR #5/baseを保持。通常GUIテスト許可は継続、専用DB/settings/生成17素材と既存EG2のみ。

**appearance-09は操作 105 recorded checks PASS / 全17 PNG目視PASS。** Light/Dark双方の実CUDA日本語検索と上限表示、cover非対応の実エラー/文字検索復帰、dirty keep、roots、missing model案内、favorite/native再起動を完走。6正常終了/cleanup warningなし、source hashes全一致。full profile chooserバッチの再実行ではなくeditor/appearance/coverage sliceであり、別checkpoint・HC・高DPI・実ライブラリの証明ではない。

07はDark clickのforeground安全拒否でFAIL（13 PNG全目視、4正常終了+1fallback warning）。所有HWNDへのscoped focusを追加。08は直接API queryをGUI初回lazy queryと競合させてFAIL（14 PNG全目視、5正常終了/warningなし）。GUIの成功Message/項目/件数を待ってから直接API queryするよう修正。07→08→09の2回fix/rerunで終了、過去FAILを変更しない。新規XAML/C#/依存/モデル/個人設定/OS変更なし。

Darkのindex_states/coverage_gpu_statesは別時点で、短時間のcached rebuild開始とcompleteが非同期に入れ替わる（09は後者processed=0）。このsnapshotをcached jobの厳密な開始/終了時刻や推論ゼロの証明に使わない。GUI結果の表示と実CUDA queryは完了確認済み。厳密なcache再利用と処理数は後続専用GPU測定で確認する。

Python103 tests PASS（81.92秒）、C#15 checks PASS、WinUI x64 SelfContained Release PASS（37.04秒/既存IL2104 2警告）。WinUI code reviewはnative Items/60 paging、async/stale/dirty、テーマ/AutomationId、DOM JSON、認証/所有worker/profile identity保持を確認。analyzer未導入。
