# P2 native接続（source checkpoint、Windows未検証）

2026-10-22。開始8073866。既存の[結果session backend/API](result-sessions.md)を作り直さず、現行WinUIへ接続した。**実装sourceは接続済みだが、.NET SDK/WindowsがないためCore/Portable build/native受入はUNRUN。P2はPARTIALのまま**。

## 変更

- MainPageは既存7方式とkind/root/view/AI scope/文字一致/区切り条件をResultSearchConditionsへ固定し、検索・明示refreshでは新session、前後pageでは同じsessionのrangeを使う。旧page APIは削除しない。空の本文/候補意味入力は従来どおり空状態、空の一般AI入力は文字一覧。rootの空集合を全folderへ広げない。
- ImageViewerSequenceは現在1件だけを保持する非同期neighborへ接続。60/120のpage境界を越え、混在一覧の画像を検索順に移動するsourceになった。数値は全検索結果内の位置。キャンセル/古い応答/不正方向を拒否。真のneighbor:nullだけを末尾とし、期限切れ・読込失敗は最後の画像を保持して説明する。
- 遅い画像読込中も次の移動が旧foregroundをcancelできる。所有window/closeで取消し、表示成功したitem/ordinalだけを戻り先として記録する。失敗して表示できなかった移動先を戻り先としない。
- viewer close後、同じsessionのrangeで最後のitemを選択・scrollへ復帰。元のitemを見ただけならtag/shelf draftを再読込しない。別itemへ戻る際の未保存変更は既存の破棄確認を通し、取消時は元の選択/draftを保つ。履歴追加で再順位計算しない。
- MainPage停止は所有sessionのcloseを試みてからAPIを解放。最大5秒のbest-effortで、接続喪失時のbackend idle cleanupも維持する。新queryの遅延応答は新sessionを上書き/解放しない。
- session rangeでも旧類似検索の起点/profile/revision/種類/score/件数検証を再利用。AI未導入/容量不足の説明を維持し、画像decoder busyに読み替えない。

## 一覧に未接続の原本がある場合

source pinを全件作成する際、1件の未接続原本で通常一覧全体が失敗する問題を修正。元のmetadata/順位/件数は残し、派生応答のavailability=unavailable（画面「接続・更新を確認」）で表示する。scope/除外/登録の確認は省略しない。private identityや原本bytesは返さない。

最初から読めなかった対象へneighborで移動すると明確なエラーとし、末尾に偽装しない。取得済み物理版が途中で変化した場合・読めなかった対象が元の版で復帰した場合は再検索を要求する。missingになったcatalog記録も保持する。類似検索の起点は引き続き厳密に確認する。

## 確認

- Linux/Pythonの生成媒体のみ。初回21件は20 PASS/1 FAIL（復帰fixtureのmtimeを元の索引版へ戻し忘れ）。失敗logを保持。
- fixture修正後、結果session/原本viewer/再検証/既存XAML stub生成の関連**41 PASS/6.722s**。stub生成はC# compileではない。
- Coreに条件変換、60→61/61→60/120→121、混在ordinal、古い応答、close取消、expiry、方向検査、120件類似range、AI未導入説明のテストを追加。**ソースのみで未実行**。
- source review/diffで既存機能・dirty guard/field名/呼出し型を確認。実C#型検査・XAML build・実GUI/速度/scroll/focusは未検証。新依存/取得/Actions/GUI/GPU/private scanなし。旧Alpha/basic03/shortcutsは更新しない。

## Windowsで次に確認

既存依存でCoreテスト→Portable buildを各1回。新失敗が出たら局所修正し、全検証を反復しない。実機では125件以上の生成画像＋混在結果で60→61/逆方向/120→121、全検索方式、root/scope/filter、close後の選択とscroll、未保存draftの保持/破棄取消、expiry→明示再検索、遅い画像の連打/closeをまとめ確認する。既存GUI capsを新名称でresetしない。

P3では120件block/最大5blockの仮想化とthumbnail/cache・完成形主画面を進める。現在はpage UIを維持したP2接続で、連続scroll/完成形UI/M1/M2/ALPHAを完了としない。
