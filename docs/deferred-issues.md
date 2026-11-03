# 不具合・要確認の対応待ち一覧

2026-11-02。利用者指定に従い、致命的でない問題はここへ集約し、改善実装を止めず後でまとめて対応する。保存消失・原本破損・起動不能・検索範囲漏れが判明した場合は先送りしない。未検証と再現済みを区別する。

| ID | 状態・影響 | 根拠と次の確認 | 優先度 |
| --- | --- | --- | --- |
| D01 | コード上の懸念。登録フォルダの表示状態変更が失敗した場合の案内が不明確 | MainPage.xaml.cs FolderStateFilter_Changedはasync voidからRefreshSearchRootsAsyncを直接await。接続切断時の例外境界を後で確認。実機再現なし、現時点でクラッシュと断定しない | 通常 |
| D02 | 開発ツールの操作確認を保留。製品機能の不具合ではない | agent-desktop v1.0.2のstate file置換1175。既存WinAppへ戻して開発を継続。新しい根拠なしに単独再試行しない | 低 |

前回の登録UI・複数登録/部分失敗は実装済みのGUI未検証であり、未修正バグとして二重登録しない。詳細はcurrent-handoffを参照。

D03（試験側・修正済み/再実行待ち）：registration-filter01は件数の旧文言「全記録」を期待して停止。実candidateは「全」。登録/scan操作前、所有process exit0。期待値のみ修正し、新許可なしに再実行していない。製品の登録失敗と断定しない。

D03追記：ユーザー追加許可後のregistration-filter02は10checks/exit0で受入。D03は解決済み（初回FAILは保持）。登録/部分失敗/filter/resetはa0ac6cbで限定確認済み。


D04（2026-11-03・試験環境/未受入）：frontend02/source3ff0849のkeyboard-entry01は、owned HWNDへの通常SetForegroundWindowがfalseで停止。生成fixture/起動は成功し、キー入力前に中止、appは正常終了。検索/登録のEnter、実日本語IMEは未検証。入力attach/権限回避/他appへのsend-inputは行わず、同じ前面化失敗を変更なしで再試行しない。source build/publish成功とは区別し、次回テスト窓を通常操作で前面にできる状況で1batchへ戻る。

D04追記：keyboard-entry02（同じEnter確認、frontend03/source37c2271）で通常UIA focusを先に試すと、WinApp自体が「非foregroundなのでfocus拒否」と入力前に停止/exit0。focusはactivationの代わりにならないと確認し、一時的な前置focus変更は撤去。関連試行は計2回、キー入力0。別名の再試行で枠をリセットせず、手動でテスト窓を通常前面にできる状況まで実キー確認を保留する。

D04追記（2026-11-04）：Sandboxの操作可能なdesktopでは通常Return入力は送れた。ただしblue→1件/空欄→3件は自動検索が先行しており、Return後の状態保持だけを観測。Enterが独立して検索を起動した因果証明と実日本語IMEは引き続き未検証。evidence/update31-result.jsonにこの限界を明記。hostの初回2失敗をPASSへ上書きせず、環境前面化の問題と製品機能の受入を分ける。
