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

appearance-04は**次回の再確認用で未実行**。存在するoutputを再使用しない。

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
