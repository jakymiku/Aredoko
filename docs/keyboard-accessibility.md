# 詳細パネルのキーボード操作・アクセシビリティ

2026-10-13。詳細内のEscと一覧へのフォーカス復帰を追加。検証は**一部完了、native batch全体はFAIL**。Dark側の残り操作を成功扱いにしない。

## 変更

- 詳細paneのBorderに通常のKeyDownを置き、未処理Escだけを受け取る。既に処理済みのキー、他の画面、開いているContentDialogのEscは横取りしない。
- 閉じるボタンとEscは同じasync処理を使う。ready/saving/dialogOpen/paneと既存transition semaphoreを確認し、未保存確認で取消されたら編集を保持。破棄または保存済みなら従来通り選択とeditorを閉じ、一覧へkeyboard focusを戻す。
- 閉じるボタンのtooltipにEscを表示。タグと棚のAutomationProperties.Nameを既存のvisible Headerに合わせて明示。既存のCtrl+F/Ctrl+S、semantic controls、ThemeResource、native ListView/ItemsWrapGridとread-only source規約を維持。
- 独立した `tools/test_keyboard_ui.py` を追加。新規 `data/ai-ui` 配下の生成65PNG・1root/隔離DB/settings、実HTTP/Release GUI、CPU契約encoderだけを使用。AIモデル/重みのロードは行わない。起動済みappやbusy portに接続しない。入力直前にowned process-instance/HWND/PIDとforegroundを確認し、Windowsのactivation拒否は明示skipする。input queuesの接続、system keys、他app操作、OS変更は行わない。

## 実行と証拠

```powershell
dotnet build src/Aredoko.WinUI -c Release -p:Platform=x64 -p:SelfContained=true --no-restore
dotnet run --project tests/Aredoko.Core.Tests -c Release
python -m unittest discover -s tests -p test_production.py -v
python tools/test_keyboard_ui.py --output data/ai-ui/keyboard-native-new
```

| run | 全体 | 記録check数 | 実入力 / skip | PNG | 正常close |
|---|---|---:|---|---|---:|
| native01 | FAIL | 17 | 7 / 0 | 1全目視 | 1 |
| native02 | FAIL | 14 | 4 / 4 | 1全目視 | 1 |
| native03 | FAIL | 50 | 26 / 0 | 4全目視 | 2 |

- native01はListView本体のUIA Focusが子作品へ渡るため、CLIのroot focus確認で停止。native02で子作品を指定したが、Homeは先頭への移動であり未選択行の選択を確定せず、editor待機で停止。02の4操作はWindows activation拒否でskipし、UIAに分けて記録した。
- native03は子作品をSpaceで選択するよう修正し、Lightの予定経路を完走した。Darkの検索/次ページまで進んだ後、前ページボタンの `send-keys --target` でUIA peer失効が報告され停止。直前のinspect/focusでも防げず、原因の確定/修正は未完了。app crashや製品のページ移動不良が確認されたという意味ではない。
- 2 fix-and-rerun cyclesで停止。01/02の各1PNGと03の4PNG、合計6PNGを全て個別に目視。03ではLightの1200x820保存・700x620未保存dialog/閉じたgridとDarkの前ページ直前を観測。見出し/検索controls/案内/dialog buttonsに意図しないclipping/overlapなし。list/grid行はスクロール境界で一部だけ見え、detail editorの下部は独立scroll。この範囲だけのvisual確認で全面auditではない。
- 元65PNG bytes/mtime/hashは全runで不変。cleanup warning/errorなし、所有appは01/02各1回、03は2回とも正常終了。end-of-batchのAI counter/settings-byte/全体PASS assertionは03で未到達であり、成功扱いにしない。CPU stubの設計上、このsliceは実GPU検証ではない。

## native03で実際に確認できた操作

- **Light**：Ctrl+F→検索欄、Tab→検索ボタン/Shift+Tab→検索欄、文字入力による最後の1件検索、全65件への復帰、Enterで次/前ページ、Spaceでリスト作品選択。
- タグ文字入力、Tabで棚へ移動、Spaceでお気に入り変更、Ctrl+Sでタグとお気に入りがDBへ保存されることを確認。
- 保存済みeditorでEsc→閉じる→最初の作品のHasKeyboardFocus=Trueを確認（ListView本体はFalse）。Enterでgridへ切替、Spaceでgrid作品選択。
- 未保存editorのEsc→ContentDialog、dialogのEsc→編集内容を保持して戻る。再度Escで確認、CloseButtonからShift+Tab/Enter→破棄して閉じる。保存済みタグが書き換わらないことを確認。
- Main toolbar10・editor6・dialog2の指定interactive controlsは実UIA treeでIDとnonempty Nameを確認。**Dark**はmain10の名前とCtrl+F/Tab/Shift+Tab/文字検索/次ページまで。Dark editor/grid/保存/Esc/dialogは未到達。
- 両themeとも実DPI96/HighContrast off。高DPI・Contrast theme・Narrator/読み上げ・全面Tab順・連打や同時遷移は未検証。Light/Darkの色が正しいだけでHighContrast合格とは扱わない。WindowsSandbox executableは利用不可、local owned appで確認した。

## ビルド・レビューと次の3手

- Core **35 PASS**、production Python **6 PASS / 2.161秒**。初回x64 SelfContained Release **PASS / 40.27秒**、最終 **PASS / 31.42秒 / errors0 / 既存IL2104 2warnings（抑制なし）**。syntax/CLI guards/diff検査・手動WinUIレビュー済み。専用WinUI analyzerは未導入・未実行。全Python155/AI/GPU suitesは過去の別証拠で今回再実行なし。
- 変更はUIイベント/フォーカス調停とaccessibility metadataのみ。MVVM移行、日本語文字列のresource化、AOT・全体UIは範囲外。既存SaveAsyncはeditorを無効化するため、保存後のfocus outlineがページボタン側に現れた。editor内のfocus保持は次の改善候補。
1. owned focus/peer失効を分析し、`focus` 後の再targetを避けるなど入力経路を見直してDark未到達分を独立確認する。今回の失敗履歴を保持し、入力ガードを弱めない。
2. 保存後のeditor focus保持、実高DPI/Contrast/Narratorと全面keyboardを別の検証として進める。OS設定は勝手に変更しない。
3. reader/Komga/フォルダ本、または未観測の固定品質入力を次sliceとして設計。Laya既定無効を維持。

DB/media/settings/PNG/生JSON/owned handlesはignored、私物/モデルDL/依存/OS変更なし。Draft PR #5/comparison base、manual-only CI、未マージを維持。
