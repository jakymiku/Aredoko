# Portable起動経路と帰宅後チェックの準備

基点`f2eb4574a263fa2f4b09cf94193fb529cd321059`。2026-10-21の「帰宅後に起動チェックできるまで進める」依頼に対応。ソース/CPU検証とWindows用準備手順を用意した。**Windows build/PowerShell実行/native起動画面/clean Windowsは未実行**。既存Alphaを更新した、実機へEXEを配置した、製品ZIPが完成したとは報告しない。PZ2 PARTIAL/R13 DOING/ALPHA未完/R14 PARTIAL。

## 帰宅後の入口

リポジトリ直下の[起動チェック手順](../STARTUP_CHECK.md)を参照。最新branchを取り込んだ後、`Prepare-Portable.cmd`で新規出力へ準備し、開いたAredokoフォルダの`Check-Startup.cmd`をユーザーが開く。準備は本体を自動起動しない。旧GUI3/3の上限をリセットする自動GUI flowではない。

準備は既存runtime入り配布を明示利用する。既知の封印済み02があれば読取のみで再利用し、なければフォルダ選択。既存の.NET SDK/cacheだけでCoreテスト、Portable publish、小型bootstrap compile/非GUI self-test、runtimeコピー、実import/media probeを一回ずつ行う。足りない依存は取得せず停止。コピー/ログ/新成果物だけを書き、新規先以外は上書きしない。初回チェック用はZIP省略。ZIP作成APIも全entry SHA/CRC/再inventoryを生成fixtureで確認した。

## 実装

| 部品 | 役割 |
| --- | --- |
| src/Aredoko.Bootstrap | 小型Windows Forms/native controlの起動画面。Shown時にRefreshしてからworkerを開始。全検査/Python/WinUI準備をUI threadで待たない |
| startup_ipc.serve_owned | 同じworkerがpreflightからbackend/frontendの通常終了まで所有。preflight-only入口は非起動のまま |
| portable_frontend | 明示Portable receiptと全payload/自己完結runtimeconfigを検査。専用stdoutでnonce/instance一致のreadyを待つ |
| StartupReady/MainPage | 所有backendへ接続→初期一覧成功→Show→Rendering callback後にready。Loaded依存でhidden windowが停止しないよう初期化を明示呼出 |
| prepare_portable/package_release | Portable build receiptとx64 GUI CLR bootstrapを要求。旧MSIXは既存activationを維持し、黙った直接EXE fallbackをしない |

bootstrapはWindows標準.NET FrameworkとWindows Formsを使う。**CLR初期化がゼロのC/C++専用入口ではない**。大きい製品.NET10/WinUI/Pythonの初期化より前に小さい画面を出すための実装で、WebViewを使わず本体GUIはWinUI 3を維持。Framework/compilerが利用できなければ自動導入しない。起動1秒/初描画/低メモリは未測定・未保証。

- [Microsoft: Windows 11同梱Framework](https://learn.microsoft.com/en-us/dotnet/framework/install/on-windows-10)
- [Microsoft: csc.exeの場所/オプション](https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/compiler-options/)
- [Microsoft: AppWindow.Hide](https://learn.microsoft.com/en-us/windows/windows-app-sdk/api/winrt/microsoft.ui.windowing.appwindow.hide)
- [Microsoft: CompositionTarget.Rendering](https://learn.microsoft.com/en-us/windows/windows-app-sdk/api/winrt/microsoft.ui.xaml.media.compositiontarget.rendering)

Rendering callbackは物理画面へ提示された時刻の測定ではない。初期一覧を読み込めなかった場合や別backend instanceの場合はreadyを送らず失敗する。source設定だけ/process開始だけ/全hash完了だけで起動画面を閉じない。

## 所有・取消・データ

bootstrapは専用pipe2本とstderr log handleだけをSTARTUPINFOEX handle listで継承する。python.exeを絶対path、CREATE_NO_WINDOW、-I/-X utf8/-B/-uで起動し、作成HANDLEを保持してimage path/作成時刻を照合する。pythonwの標準streamがNoneになる条件に依存しない。祖先reparse/type/単一hardlinkを確認し、名前/PID検索で他processを終了しない。実Win32 ABIは未確認。

既存全SHA/祖先guard、stage通知、協調取消、port/instance/DB lease/所有backend stdin EOFを維持。backend待機と初期画面待機にも取消を接続。ready前は今回の子だけcleanupする。ready確定後の親EOF/取消は対話中GUIの未保存編集を強制破棄せず、通常終了までworkerがbackendを管理する。通常のOS shutdownを起動画面がブロックしない。二回目のcloseで親を閉じても子側の所有EOFが残る。ローカルlogはpathを含み得るがprotocol stdoutへ例外/tokenを流さない。

`--startup-check`は毎回新しい`LOCALAPPDATA/Aredoko/startup-check/<session>`を使い、既存launch-settingsを一切読み込まない。専用DB/モデルroot/AI settings/viewer settingsと通常データを分離し、私物走査や推論を始めない。各回新規なので、このモードは保存済みtagのrestart受入ではない。通常Aredoko.exeは従来のユーザーデータ/明示model rootを使う。

portable packageだけにroot Aredoko.exe/Check-Startup.cmdと適切な案内を置く。Aredoko.cmdもroot exeへつなぎ、MSIX専用shortcut installerをportableの通常入口に混ぜない。旧MSIX package/Alpha/証明書/登録/封印済み02は無変更。

## 実行した検証と残り

Linux/Python3.12.14、host Python/生成payload/一時DBのみ。fake PE/runtimeは構造fixtureで、Windows実行ファイルを動かした証拠ではない。関連コマンド:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests python -B -m unittest test_portable_startup test_startup_ipc test_startup_progress test_release_parallel test_release_staging test_release_lifecycle test_release_activation test_release_reporting -q
```

新規13件は、Portable receipt/未知・変更payload/旧MSIX誤用/自己完結/runtime必須file/PE構造/新規ZIP照合・上書き拒否、実backend＋host ready子processのnonce/instance/失敗・重複field・timeout/途中取消/DB lease解放/ready後取消保全、smoke専用dataを扱う。既存release/IPC/source guardも回帰確認する。最終件数/時間は最新handoffに記録。最初の12件は既存ZIPの拒否がStoragePathErrorだったため期待と不一致で1 ERROR、専用FileExistsErrorへ整理して修正。初回失敗を隠さず、途中結果を最終へ加算しない。

Windows compiler/Framework loader/Win32 struct ABI/handle inheritance/PowerShell構文/Core実行/WinUI publish/初表示・応答・キャンセル・通常終了は未確認。新しいZIPの5GB級実runtimeコピーやclean Windowsも未実行。次はWindows既存依存で準備scriptを一回実行しbuild/logを確認→ユーザーの手動起動チェック→具体artifactで残りのnative/clean Windows受入。GUI自動再試行の旧上限は保持。

PZ3の既存model選択/公式手動/app downloadと進捗停止再開は未実装。今回の明示runtime梱包/ZIP基盤だけでPZ3/PZ4/PZ5を完了にしない。viewer新Core/WinUI/実描画/HoneyView比較、U09/U11/U13/U14、ALPHA後の実音声/音楽を保持。Actions0、DL0、GPU0、GUI0、main mergeなし、旧shutdown再実行なし。
