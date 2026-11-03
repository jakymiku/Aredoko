# PortableのWindows準備・検証（2026-10-21）


## 2026-11-02 最新の対になる候補

基本ZIP26/app85123b4、アプリSHA `7e6f883e4264bc49a2509fd24efea26c10bc8914299a6d2e484e6db779702ca4`、生成セット26 SHA `888bace9f09d62c412ab3a29c61b6dcd514b8aec69861e6d0b643c4c5e890cb2`。ホストの専用DBによる通常入口/再起動は限定受入済み、別Windowsは未確認。Sandboxの状態を今回変更・再調査していない。旧25以下を上書きせず、試用sourceを混同しない。


## 2026-11-01 現在のSandboxと検証レポート

以前の有効化（exit3010/InstallState1）は保持。11/1のbootは有効化後だが、現在のread-only WMIはInstallState2、WindowsSandbox.exeなし、WinApp targetはnot running/not attached/stale。原因は未特定。旧「OS再起動だけ待つ」状態からは変わっている。guest未実行・OS設定変更なし。再有効化や他のclean Windowsが必要かはuserと確認してから進め、ホスト成功を代用しない。証拠 `data/ai-ui/continuation-20261101/sandbox-readiness01.json`。

検証セット作成CLIはmanifestの版・作成日時・platformと、ZIP/manifestのSHAを結果templateにも記録する。既存manifestにsource revisionはないためnullで示し、sidecarから推測しない。旧セットを無言で書換えず、新候補ごとに作成する。


## 2026-10-30 最新セット24

現在の試用候補は基本ZIP24/source1e8e7ca。アプリZIP SHA `987946c4212c386061ca3b90a6e588389b711e62aeb94ee643e3090ed43f319d`、対になる生成確認セット `dist/portable-validation-20261029-24.zip` のSHA `317dc8d93c0aad28610a09765d4933de6ef65ef53419ff81d39448a2fc562072`。ホストの通常EXE/小中大/終了・再起動は限定確認済みだが、別Windows/Sandboxは未受入。機能有効化後のOS再起動を利用者の都合で済ませた後、readinessと当該候補の検証可否を確認する。旧セット23/22を上書きしない。


## 2026-10-29e 現在の生成確認セット

基本ZIP23の対になる `dist/portable-validation-20261029-23.zip` を作成。アプリZIP SHAは `9362eb86dbe3af75c59ca79474485057f474e7d3a0412ab072664d83065cb650`、セットSHAは `6d714eed42654a508e2ef33c3698cad274b74e9943295d3436120295ca1cd1d6`。作成時に選択directoryとZIPのmanifest/sums/entry集合・サイズを照合し、別候補の組合せを拒否する（生成6tests PASS）。これはclean Windows実行結果ではない。旧22も保存する。Sandboxは機能有効化後のOS再起動待ち。


## 2026-10-29：開発環境のないWindowsでの受入手順（現行）

**本PCでの通常入口成功と、別Windowsでの受入を区別する。** 基本ZIP22/source68c0100はホストの通常入口から空DB→登録/一覧取得/タグ保存→終了/再起動まで成功。BasicZIP21では日本語/空白を含む別配置から同じユーザー設定も保持した。10/29のread-only確認ではSandbox targetは未起動/stale、OSの`Containers-DisposableClientVM`はInstallState2、既存guestへ接続できず。OS機能の有効化/再起動/VMの新規取得はしていない。別環境の起動確認は未実施。証拠は `data/ai-ui/continuation-20261029d/sandbox-readiness01.json`、新しい候補を使うときはsource/ZIP SHAを記録する。

**10/29追記：ユーザー許可でSandboxを有効化済み、再起動待ち。** 通常のUAC経由DISMがexit3010、InstallState1。`/NoRestart`で再起動を抑止。再起動後にreadinessを確認してからゲスト受入へ進む。現時点でゲスト起動/clean Windows受入は未実施（`sandbox-enable01.json` / `.log`）。

### 持ち出し用の生成データセット

基本ZIP22に対応する `dist/portable-validation-20261029-22.zip`（3,134bytes、SHA256 `adc2ec99dd400055b0c3f58797b2a66fc73a365e0487a73812636c1e72701892`）を作成した。アプリ本体とは別に渡す。PNG2枚/2ページCBZ1冊、候補ZIPと原本のSHA、短い確認手順、未記入の結果テンプレートの6filesだけで、実行ファイル/スクリプト/私物は入らない。全ZIP memberと元生成fileを照合済み。生成しただけで別Windows受入にしない。

次の候補へ作り直すときは、既存出力へ上書きせず次を実行する。

```powershell
python tools/prepare_windows_validation.py --release dist/portable-basic-20261029-22/Aredoko --output dist/portable-validation-new-candidate
```

`--release`は封印済み基本版、隣の`Aredoko-windows-x64.zip`と組にする。追加取得/アプリ起動/設定変更は行わない。実際の別Windows確認は下記の手順で行い、結果テンプレートのコピーへ成功/失敗/未実施を記録する。

### 基本版の最小確認

1. 開発用Python/.NET SDK/WinApp CLI/Aredoko登録がないWindows x64のテスト用ユーザーで行う。通常データを持ち込まず、生成PNG2枚と小CBZのみ用意する。OS版と既存runtimeの有無を記録する。
2. 受け取ったZIPのSHAとsourceを照合し、空白・日本語を含む新しい場所へすべて解凍する。旧版や実データへ上書きしない。追加環境を先に導入して不足を隠さない。
3. 通常の`Aredoko.exe`から起動する。起動進捗→ライブラリ/初回案内を確認し、手動backend起動や開発用コマンドを使わない。AIを準備せず基本操作へ進む。
4. 生成素材フォルダを登録し、「一覧のみ」を読み込む。ファイル名検索→画像/本の閲覧→タグ・棚・お気に入りの保存を確認する。
5. アプリを普通に閉じ、もう一度`Aredoko.exe`を開く。保存内容とフォルダ登録が残り、元PNG/CBZのSHAが変わらないことを確認する。
6. 終了後、同じZIPを別の場所へ解凍し、その`Aredoko.exe`から起動する。同じユーザーの保存内容を保持することを確認する。通常の起動確認を`Check-Startup.cmd`の空DBで代用しない。
7. 失敗時はOS版、候補のSHA/source、失敗段階、表示文とログの場所を記録する。試験を成功にせず、必要な依存/起動経路の不足として切り分ける。OS設定変更やinstaller実行は既存の許可ルールに従う。

任意AI環境は、基本版の受入後に別項目として取得/配置/索引/検索/再起動を確認する。基本版が動いたことをAI環境の配布完了にしない。実runtimeの条項/host/registryとモデル条件が未完の現在、未確認の取得先や自動導入を成功扱いしない。下記10/21の記録は当時の履歴。


> **起動タイムアウトは修正版で解消し、fresh smokeのready/通常close/早期cancelを実機確認済みです。** 最新入口は `dist/portable-startup-diagnostic-20261021-02/Aredoko/Check-Startup.cmd`。[修正・実測・限界](portable-startup-console-fix.md)。以下の旧準備/失敗記録は履歴です。

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

## 2026-11-04 Sandbox基本版の限定受入

ユーザーが手動DISM等でSandbox起動を回復後、基本ZIP28/app37c2271を開発環境のないゲストで通常Aredoko.exeから確認した。WinAppのagent準備はE_ACCESSDENIED、画面なしguestが残り、別wsb起動は単一起動制限に拒否された。wsb listの同一IDへ通常connectするとdesktopが表示され、ExistingLogin exec/shareは成功。agent/System実行の回避・OS設定変更・ホスト再起動は行わず、以後のGUIはcomputer-useによる視覚確認（後半はユーザー指定6.1 Terra）。準備済みwsbそのものの起動成功やnetwork無効化の保証とは区別する。

共有は候補をC:\Aredoko、生成kitをC:\AredokoValidationへ読み取り専用、専用evidenceのみC:\AredokoEvidenceへ書込可。通常EXE起動→初回案内→生成media登録→一覧のみscan3件→PNG表示→CBZ1/2から2/2（緑）→タグsandbox-acceptance-20261104明示保存→タグ検索1件→通常終了→同じEXE再起動→登録3件/タグ保持→CBZ2/2復元→通常終了まで視覚確認。初回/再起動wsb execは両exit0。独立guestのAppDataを専用証拠へコピーし、親でSQLite integrity_check=ok、items3件/CBZの保存タグ、reader_progress.page=1（0始まり）を再確認。

証拠: data/ai-ui/continuation-20261103/sandbox-basic28/evidence/acceptance-summary.json、guest-appdata（DB/logs）、inventory.txt、appdata-paths.txt。秘密を含み得るrawはignoredのままGitへ含めない。ゲスト自体は停止しない。モデル取得/AI/GPU/音声動画/別物理Windows/更新移行/全P6・P7は未受入。後続source12b6568のZIP29は別候補なのでこの結果を転記しない。

### 2026-11-04 ZIP29への別配置更新

同じゲストでZIP28を停止後、基本ZIP29/source12b65680276ddba927934e89d777672cb2661903をC:\Aredoko29へ別read-only共有。通常Aredoko.exeを起動し、既存guest AppDataの3件/タグ保持、CBZ2/2緑ページ復元、タグ検索1件、詳細の検索根拠展開（入力語一致）を視覚確認。再scan/新しい保存を反復せず、通常終了・wsb exit0。コピーDB integrity_check=ok。証拠は同evidence/update29-result.json・update29-appdata。後続の元ファイル状態案内は未収録。ゲスト停止/OS設定/AI取得は行わない。

### 2026-11-04 ZIP30の通常入口・viewer内整理

source138964e7f33cfaae4d94605a0904c473afd83d57、別read-only共有C:\Aredoko30。通常EXEからall/空文字検索→生成blue画像→viewer star登録→成功表示→通常viewer close→一覧star/詳細checkbox同期→app通常終了exit0。元のguest AppDataを継続し、guest内同梱Pythonによるread-only DB検査はintegrity ok、blueだけfavorite=1、green/CBZ=0、既存CBZタグとreader_progress.page=1保持。証拠は同evidence/update30-result.json・update30-db-check.json・update30-appdata。host UIAの保存拒否/保存中close競合とは別結果。ゲストを停止しない。

### 2026-11-04 ZIP31の本ビューア操作

sourcebb59c405074c93e7b3176182a789fa85c4ef6769、C:\Aredoko31の通常EXEから既存guest専用DBを使用。本CBZの2/2緑ページ復元→viewer star登録成功→通常close→一覧star/詳細checkbox/既存tag確認→app通常終了。guest内同梱Pythonのread-only DBはintegrity ok、blue favorite=1/green=0/CBZ=1、CBZタグとpage index1保持。追加起動のEnter観察を含む2入口は各wsb exit0。evidence/update31-result.json・update31-db-check.json・update31-appdata。

Enter観察：blue入力で自動検索が先に1件へ更新、Return後も1件維持。空欄で自動検索が3件へ戻り、Return後も3件維持。guestへ通常キー入力できた事実と、Enter単独で検索を起動した証明を区別する。実日本語IMEとEnter単独の機能受入は未検証。ホスト前面化失敗D04の合格への読み替えはしない。Sandbox内の保存途中close/API拒否のfixtureは今回反復していない。
