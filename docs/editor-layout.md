# 詳細パネルと保存後フォーカス

## 最新：保存focus・高さを使う詳細と固定保存欄（2026-10-13）

開始HEAD **d93bf21d5a88d8ae8a1ee89b63814ed0e0fa907f**。同じfeature/Draft PR #5/comparison base。今回の実装・検証・仕様commitは **93f90c7244bfa9cea497fbfdd6d11fcf850852ce**。このSHA記録は文書だけの後続commit。通常push後の最終HEAD/CI観測はGit/PR head・PR説明で確認。

- 詳細をNavigationView内の利用可能な高さ全体へ配置。狭幅overlayでも作品名・表紙・編集欄を広く表示し、不透明背景を維持。保存ボタン/編集状態は下部固定、詳細/編集fieldsだけ縦scroll。toolbarの折返しはwindow幅ではなく実content幅で選び、wide Inlineの320幅を引いた場合にも対応。
- SaveAsyncはeditor内の元controlとfocus state、disable直後の退避先を記録。完了時にfocusがそのまま・同一作品・pane openの場合だけ成功/失敗とも復帰。成功後にSaveがdisabledならタグ欄へ。保存中に検索欄へ移った場合はfocusを奪わない。エラーでは編集内容と再試行を維持。モデル/API/順位/source変更なし。
- **editor-native-03 構造化PASS / 93 checks / 実キー入力50 / skip0 / 12PNG全目視 / 指定pane・footer・dialogのvisual PASS / 正常close2 / cleanup警告0**。Light/Dark1200x820と700x620、DPI96/Contrast off。生成65PNG/1root・隔離DB/settings・CPU契約encoder、認証済み実production HTTP＋Release GUI。
- 各themeで成功保存後Shelf focus、意図的409後タグ/DB不変とTags focus、Enter再保存とdisabled Save→Tags、応答を遅延した保存中のUIA Query focus維持を確認。fixtureはcatalog.updateだけをテスト内で置換し、実handlerのHost/token/Origin/body検証と実WinUI response handlingを維持。失敗2件・遅延2件が終端で消費されたことを確認。UIA Query focus移動を物理keyboard成功として数えない。
- 既存Ctrl+F/Tab/Shift+Tab/文字検索/前次ページ/list・grid選択/favorite/Ctrl+S/Esc/dirty cancel・discardも完走。終端AI calls/resident workerなし、settings bytes/source bytes/mtime/hash不変。狭幅Save onscreenをUIAで確認し、wide error/saved・narrow list/grid/dialog/closedを各themeで全目視。thumb/gridのviewport境界で行が一部見えるのは既存scroll。WinAppがtooltipを同時captureした画像には外枠ラベルが付いたが、これは製品UIではない。全面UI/A11y auditではない。
- **editor-native-01/02は各FAIL38checks/実入力17/skip0/4PNG全目視/正常close1**。Lightの保存成功・失敗・retry・選択focus維持は確認したが、overlay→inline resizeでpaneが閉じてTxtTags待機が停止。open値の即時再設定とclose-switch-reopen案はいずれも安定せず最終版から除いた。03は既存BtnDetailsから明示的に再open。**リサイズ時の自動open保持は未実装/既存挙動のまま**で、03 PASSに含めない。2 fix-and-rerun cyclesで終了、追加native試行なし。
- Fresh **Core35 PASS / production Python6 PASS1.918秒**。Release初回25.95秒・修正後24.91秒・最終 **x64 SelfContained Release PASS24.86秒 / errors0 / 既存IL2104 2warnings（抑制なし）**。syntax/help/path/negative focus guards/diff・手動WinUIレビュー済み。project scoped FocusManager.GetFocusedElement(XamlRoot)/Control.FocusState/ContentControl.VerticalContentAlignment/Grid.SetRow等を確認。専用WinUI analyzer未導入・未実行。全Python155/AI/GPUは今回は再実行なし。
- 高DPI/HighContrast/Narrator/全面Tab順/保存中の別ウィンドウ操作は今回未検証。依存/OS設定/モデルDL/私物scanなし。Laya既定無効/元ファイルread-only/CI manual-only/Draft未マージを維持。README/statusを実装済み開発版の案内へ更新、旧Web demoを保持。

### 次の3手

1. resizeのpane自動保持を独立sliceで調査。未保存内容を失わず、明示close/light dismissと自動復帰が競合しない設計にする。
2. 実高DPI/Contrast/Narrator・全面keyboardを別確認。OS設定は明示許可なしで変更しない。
3. CBZ/ZIPのread-onlyページ閲覧を次の小さな縦切りへ。既存PreviewReaderのroot/reparse/stale/ZIP directory/byte/worker制限を引き継ぎ、フォルダ本・Komga・見開き・読書位置同期は別段階。Laya gateは既定無効のまま。

### シャットダウン依頼

ユーザーが就寝中の実装完了後shutdownを明示依頼。テスト・引継ぎ・commit/通常push・PR更新と所有テストapp/server終了を確認後、最後に非表示helperから45秒後 `shutdown.exe /s /t 0` の通常shutdownを要求する予定。`/f`なし、強制終了を暗黙に行う正のshutdownタイムアウトも使わない。helper開始/要求のlocal receiptはignored `data/ai-ui/overnight-shutdown-20261013.json`。電源offの完了はこのセッションから確認不可、開始/受付状況と区別する。


再現: `python tools/test_keyboard_ui.py --output data/ai-ui/editor-native-new`（既存Release buildが必要、新しい出力名を使う）。
