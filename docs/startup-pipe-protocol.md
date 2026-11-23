# 起動前チェックの継承pipe（PZ2・CPU実装）

> **後続の明示所有起動**：[Portable起動経路](portable-startup-check.md)で同じworkerのapp_ready/session_completeまで追加した。preflight-only入口は非起動のまま。下は一回限りのpreflight実装時の記録で、旧結果/制限を保持。Windows build/native受入は現在も未実行。

2026-10-21、基点`51f877469995d2bb1e0d497a5d3a13b1fb868ac3`。将来のnative起動画面と既存検査をつなぐ**一回限りの検査worker**を実装。PZ2 PARTIAL/R13 DOING/ALPHA未完/R14 PARTIAL。root Aredoko.exe/起動画面/portable launch/アプリreadyは未実装。

## 接続と信頼境界

内部入口`tools/launch_release.py --startup-preflight`は、stdin/stdoutが両方pipeの場合だけ同梱rootを既存preflightで検査する。settings/モデルpath等の上書き引数は拒否。利用者向けコマンドではない。通常CLI出力は維持し、socket/公開port/名前付きendpoint/通知file/log/DB/GUIを作らず、backend/frontendを起動しない。

将来のnative親は専用匿名pipeを作り必要な子側handleだけを継承し、不要端を閉じる。絶対exe path/作成時刻/保持process HANDLEの所有証明、継承list、終了確認はnative親の責任で、今回のPython workerで実装済みとはしない。sessionは専用channelの相関IDで、認証tokenや秘密ではない。

最初のhelloを5秒以内に待つ。binary UTF-8 JSONL、改行込み4,096 bytes以下。重複key/余分field/不正format/途中frame/未知command/不一致sessionを拒否。親からは以下だけを受ける。

```json
{"format":"aredoko-startup-pipe-v1","command":"hello","session_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
{"format":"aredoko-startup-pipe-v1","command":"cancel","session_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
```

sessionは親が生成する小文字hex32文字。hello一回、以後は同sessionのcancelのみ。親はresultまで書込端を保持する。検査中のEOFは取消。hello成立前の不正/EOF/timeoutは検査未開始・exit2で、sessionがないためresultを出さない。

## 通知と終了

全通知はformat/session_idを持つ。

| kind | 内容 |
| --- | --- |
| hello | hello受理。検査完了ではない |
| progress | progressへ既存aredoko-startup-progress-v1の厳密なstage/state/sequence/件数/bytesだけを格納 |
| result | statusはpreflight_complete/failed/cancelled、reasonは固定codeまたはnull |

reasonはcancel_requested/owner_eof/protocol_error/hello_timeout/output_backpressure/output_closed/verification_failed。pipe故障時はresultが届く保証はなく、親はEOF/終了code/自分の期限を扱う。例外文/path/token/原本名や内容は送らない。失敗時は最後のstageと固定codeを保持する。日本語説明/ログを開くUIは未接続。

**preflight_completeは検査だけの完了**。backend接続やGUI初期表示ではなく、splashを閉じる根拠ではない。別processで全SHA/guardを省略する再利用ticketにもならない。最終bootstrapは同じ所有workerの起動lifecycleへ接続し、backendと初期画面readyを別途証明する必要がある。

検査callbackは同期writeせず最大32frameのqueueへ渡す。writerだけがI/Oを行い部分writeにも対応。queue飽和は取消し、通知を無制限蓄積したり成功扱いにしない。通常は全段階通知と既存10回/秒間引きを維持。終端result送信確認は最大2秒、送れなければexit2。raw descriptor/daemon I/Oで、親が読み取らなくてもこの一回限りのworkerを終了可能にする。長期常駐processへ埋め込んだり再使用しない。OS I/O/probe終了の即時割込み保証ではない。

## 保全と検証

新moduleは新規配布へ明示コピーしmanifestで保護。旧artifact/旧必須inventory/installed Alphaは変更しない。全SHA/inventory/祖先link/type/hardlink検査を維持。既存協調取消境界を通り、保持probe Popenだけをreap。backend/GUI稼働中の取消へ拡大しない。

Linux/Python3.12.14、生成payload/host Python/一時DBのみで、最終**88件＝83 PASS/Windows5 SKIP/失敗0、7.879秒（新規17件）**。

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests python -B -m unittest test_startup_ipc test_startup_progress test_release_parallel test_release_staging test_release_lifecycle test_release_activation test_release_reporting -q
```

実guard/hash回数同一・件数/bytes・payload bytes/mtime不変、不正/重複/過長/途中frame、hello期限、取消/所有EOF、別child保全/probe reap、通知飽和、部分write、終端enqueue前のthread競合、private例外非漏洩を確認。host実workerで成功通知と親がstdoutを読まない場合の終了、実梱包CLIでruntime未同梱をfailedと通知しpayloadへ書かないことも確認。fake exeはlayout fixtureだけで実行しない。

**Windows pipe属性/ABI/native HANDLE所有/起動画面/初期表示/clean Windows/実速度は未確認**。dotnet/WindowsなしでCore/WinUI buildも未実行。GUI/GPU0、依存/model取得0、Actions0/main mergeなし/private scanなし。旧GUI3/3/失敗記録/P0 2/2終了/OCR保留/全機能を保持。旧shutdownを再実行しない。

次はnative最小入口/即時UI/所有handle→同workerのbackend・portable frontend・ready統合→PZ3全runtime/model導線→PZ4 ZIP/再配置→PZ5明示許可後のnative/clean Windows。viewer新Core/WinUI/HoneyView比較、U09/U11/U13/U14、ALPHA後の実音声/音楽も残す。
