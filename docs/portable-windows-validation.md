# PortableのWindows準備・検証（2026-10-21）

> **後続の手動確認は起動失敗（20:41 Initial screen timed out）です。** 下記は準備時点の記録であり起動成功の証拠ではありません。最新の診断状況は[codex-handoff](codex-handoff.md)冒頭を参照。元の配布は保持し、新しい診断用frontendだけ別途build済み。原因特定・GUI再検証は未完了。

Work HEAD`68db65b`を実機へ取り込み、既存runtime/cacheだけで準備した。**本体や起動画面はまだ起動していない。** インストール済みAlphaと旧配布は更新していない。

## このPCで次に開くファイル

リポジトリから`dist/portable-wincheck-20261021-02/Aredoko/Check-Startup.cmd`を開く。今回は既に準備済みなのでPrepare-Portable.cmdをやり直す必要はない。

- 小さな起動画面で処理段階/実件数が進むか、本体の空ライブラリへ移るかを確認。
- 本体を普通に閉じ、もう一度開いて起動画面のキャンセルを確認。
- 各回が専用の空DB/設定で、私物scan・モデル取得・推論をしない。毎回新規なのでタグのrestart保持試験ではない。
- 通常利用の入口は同じフォルダのAredoko.exeで、従来のユーザーデータを使う。まず上の専用起動確認を行う。
- エラー画面の「ログを開く」で今回の理由を確認する。旧GUI3/3上限は解除していない。今回も自動GUIを実行していない。

## 実行結果

| 検査 | Windows実結果 |
| --- | --- |
| Core Release | 759 PASS、新しいcache/position-writer回帰も実行 |
| WinUI Portable x64 | publish成功、3 WUI1001+2 SDK IL2104、抑制なし |
| 小型bootstrap | 標準.NET Framework csc compile/非GUI self-test成功、391,168 bytes |
| 実bootstrapのWin32 owner | 実classをreflectionで呼び、保持HANDLE/handle-list継承/UTF8往復/正常終了PASS、Form生成なし |
| 起動/取消/配布CPU | 103 PASS、SKIP0、106.053秒 |
| viewer媒体回帰 | 81中78 PASS/3 SKIP、39.744秒。symlink権限2件、open-file置換1件がSKIP |
| 新配布 | 24,325 files / 5,554,199,143 bytes、manifest全照合/同梱Python・media実probe PASS |
| GUI/GPU/実描画/clean Windows/ZIP | 未実行・未作成、完成認定しない |

ログは`data/ai-ui/work-portable-20261021-01.log`と`work-portable-20261021-02.log`と`dist/portable-wincheck-20261021-02/`のcore-tests/frontend-build/bootstrap-build/bootstrap-cpu/runtime-check.log、preparation.json/windows-validation.json。起動回帰は`work-startup-cpu-20261021-*.log`（01/02/03）、viewerは`work-viewer-cpu-20261021-01.log`。01準備拒否・01テスト手動停止・02診断timeoutも保存している。

標準コンパイラの正当なWinSxS hardlinkをstorage fileと混同した問題、Windows4KiB pipeを超える不正入力fixtureの先書込み停止を修正。payload/原本/DBのhardlink/link/reparse/SHA拒否やprotocol4KiB制限は緩めない。Windows APIでOS directoryを取得し、build用inbox cscだけを狭く区別する。テストfixtureは読取と並行して完全な4097-byte入力を送り、完了も確認する。

非GUIWin32試験の再現は、既存inbox cscで`tests/BootstrapNativeCpu.cs`を`/target:exe /platform:x64 /codepage:65001`で新しい出力先へcompileし、引数に配布Aredoko.exe/同梱python.exe/新しいchild log先を渡す。アプリのMainは呼ばず、実Native.Startだけを実行する。初回helper compileはsource指定の誤りで失敗し、絶対Windows pathに修正後PASS（製品不具合ではない）。

今回の新配布をin-placeで変更しない。配布内docsは準備時snapshotであり、最新の受入状況はrepoの[handoff](codex-handoff.md)と出力直下のJSONを参照する。モデル導入3経路、ZIP/再配置/通常DBの保存・restart、実GUI、HoneyView比較、clean Windows、U09/U11/U13/U14、ALPHA後実音声/音楽は残る。Actions/DL/GPU/GUI/OS設定/旧shutdownなし。

既存準備PS1のUTF8 BOMは変更せず保持。Windows PowerShell5.1のParserで構文/日本語を確認し、準備script自体は再実行しない。最初のparser helper起動は既定execution policyで拒否され、既存CMDと同じprocess-only Bypass指定後に確認した。OSの実行ポリシー変更はない。
